"""
Portfolio Management Module

This module handles portfolio state, position management, and trade tracking
for the backtesting system.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import pandas as pd
import numpy as np

from .events import SignalEvent, OrderEvent, FillEvent


logger = logging.getLogger(__name__)


@dataclass
class Position:
    """
    Represents a trading position.
    
    Attributes:
        symbol: Trading symbol
        quantity: Position size (positive for long, negative for short)
        entry_price: Average entry price
        entry_time: When position was opened
        current_price: Latest market price
        realized_pnl: Realized profit/loss
        unrealized_pnl: Unrealized profit/loss
        commission_paid: Total commission paid
    """
    symbol: str
    quantity: float
    entry_price: float
    entry_time: datetime
    current_price: float
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    commission_paid: float = 0.0
    
    @property
    def market_value(self) -> float:
        """Current market value of the position."""
        return abs(self.quantity) * self.current_price
    
    @property
    def side(self) -> str:
        """Position side (LONG or SHORT)."""
        return 'LONG' if self.quantity > 0 else 'SHORT'
    
    @property
    def pnl_percent(self) -> float:
        """Unrealized P&L as percentage."""
        if self.entry_price == 0:
            return 0.0
        
        if self.quantity > 0:  # Long position
            return ((self.current_price - self.entry_price) / self.entry_price) * 100
        else:  # Short position
            return ((self.entry_price - self.current_price) / self.entry_price) * 100
    
    def update_price(self, price: float):
        """Update current price and unrealized P&L."""
        self.current_price = price
        
        if self.quantity > 0:  # Long position
            self.unrealized_pnl = self.quantity * (price - self.entry_price)
        else:  # Short position
            self.unrealized_pnl = abs(self.quantity) * (self.entry_price - price)


@dataclass
class Trade:
    """
    Represents a completed trade.
    
    Attributes:
        symbol: Trading symbol
        entry_time: When trade was entered
        exit_time: When trade was exited
        side: LONG or SHORT
        quantity: Trade size
        entry_price: Entry price
        exit_price: Exit price
        pnl: Profit/loss
        pnl_percent: P&L as percentage
        commission: Total commission paid
        duration: Trade duration
    """
    symbol: str
    entry_time: datetime
    exit_time: datetime
    side: str
    quantity: float
    entry_price: float
    exit_price: float
    pnl: float
    pnl_percent: float
    commission: float
    
    @property
    def duration(self) -> pd.Timedelta:
        """Trade duration."""
        return self.exit_time - self.entry_time
    
    @property
    def is_winner(self) -> bool:
        """Whether the trade was profitable."""
        return self.pnl > 0


class Portfolio:
    """
    Portfolio manager for tracking positions, cash, and trades.
    
    This class maintains the state of the portfolio throughout the backtest,
    including open positions, cash balance, and completed trades.
    """
    
    def __init__(self, initial_capital: float = 10000, commission: float = 0.001):
        """
        Initialize the portfolio.
        
        Args:
            initial_capital: Starting capital
            commission: Commission rate (as decimal)
        """
        self.initial_capital = initial_capital
        self.commission = commission
        
        # Current state
        self.cash = initial_capital
        self.positions: Dict[str, Position] = {}
        self.closed_trades: List[Trade] = []
        
        # Transaction history
        self.transaction_history: List[Dict] = []
        
        # Risk parameters
        self.max_position_size = 0.1  # Max 10% per position
        self.use_leverage = True
        self.max_leverage = 10
        
        logger.info(f"Portfolio initialized with capital: {initial_capital}")
    
    def reset(self):
        """Reset portfolio to initial state."""
        self.cash = self.initial_capital
        self.positions = {}
        self.closed_trades = []
        self.transaction_history = []
    
    def update_market_prices(self, prices: Dict[str, float]):
        """
        Update market prices for all positions.
        
        Args:
            prices: Dictionary of symbol -> price
        """
        for symbol, price in prices.items():
            if symbol in self.positions:
                self.positions[symbol].update_price(price)
    
    def generate_order(self, signal: SignalEvent) -> Optional[OrderEvent]:
        """
        Generate an order from a trading signal.
        
        Args:
            signal: Trading signal event
            
        Returns:
            Order event or None if order cannot be generated
        """
        # Check if we already have a position
        existing_position = self.positions.get(signal.symbol)
        
        # Determine order quantity based on signal strength and risk management
        quantity = self._calculate_order_quantity(signal, existing_position)
        
        if quantity == 0:
            logger.debug(f"Zero quantity calculated for {signal}")
            return None
        
        # Determine order direction
        if signal.signal_type == 'BUY':
            direction = 'BUY'
        elif signal.signal_type == 'SELL':
            direction = 'SELL'
        else:
            return None
        
        # Create order event
        order = OrderEvent(
            timestamp=signal.timestamp,
            symbol=signal.symbol,
            order_type='MARKET',  # Using market orders for simplicity
            direction=direction,
            quantity=abs(quantity),
            metadata={
                'signal_strength': signal.strength,
                'strategy': signal.strategy_name
            }
        )
        
        logger.info(f"Generated order: {order}")
        return order
    
    def update_fill(self, fill: FillEvent):
        """
        Update portfolio based on order fill.
        
        Args:
            fill: Order fill event
        """
        symbol = fill.symbol
        
        # Update cash
        if fill.direction == 'BUY':
            self.cash -= fill.total_cost
        else:  # SELL
            self.cash += (fill.quantity * fill.price) - fill.commission
        
        # Update or create position
        if symbol in self.positions:
            self._update_position(fill)
        else:
            self._create_position(fill)
        
        # Record transaction
        self.transaction_history.append({
            'timestamp': fill.timestamp,
            'symbol': symbol,
            'direction': fill.direction,
            'quantity': fill.quantity,
            'price': fill.price,
            'commission': fill.commission,
            'cash_after': self.cash
        })
    
    def close_all_positions(self) -> List[OrderEvent]:
        """
        Generate orders to close all open positions.
        
        Returns:
            List of order events to close positions
        """
        orders = []
        
        for symbol, position in self.positions.items():
            # Determine close direction
            direction = 'SELL' if position.quantity > 0 else 'BUY'
            
            order = OrderEvent(
                timestamp=datetime.now(),
                symbol=symbol,
                order_type='MARKET',
                direction=direction,
                quantity=abs(position.quantity),
                metadata={'reason': 'close_all'}
            )
            orders.append(order)
        
        return orders
    
    def get_total_equity(self) -> float:
        """Calculate total portfolio equity (cash + positions value)."""
        positions_value = sum(pos.market_value for pos in self.positions.values())
        unrealized_pnl = sum(pos.unrealized_pnl for pos in self.positions.values())
        return self.cash + positions_value + unrealized_pnl
    
    def get_positions_summary(self) -> Dict[str, Dict]:
        """Get summary of all open positions."""
        summary = {}
        
        for symbol, position in self.positions.items():
            summary[symbol] = {
                'quantity': position.quantity,
                'side': position.side,
                'entry_price': position.entry_price,
                'current_price': position.current_price,
                'market_value': position.market_value,
                'unrealized_pnl': position.unrealized_pnl,
                'pnl_percent': position.pnl_percent
            }
        
        return summary
    
    def get_closed_trades(self) -> pd.DataFrame:
        """Get DataFrame of all closed trades."""
        if not self.closed_trades:
            return pd.DataFrame()
        
        trades_data = []
        for trade in self.closed_trades:
            trades_data.append({
                'symbol': trade.symbol,
                'entry_time': trade.entry_time,
                'exit_time': trade.exit_time,
                'side': trade.side,
                'quantity': trade.quantity,
                'entry_price': trade.entry_price,
                'exit_price': trade.exit_price,
                'pnl': trade.pnl,
                'pnl_percent': trade.pnl_percent,
                'commission': trade.commission,
                'duration': trade.duration.total_seconds() / 3600  # Hours
            })
        
        return pd.DataFrame(trades_data)
    
    def _calculate_order_quantity(self, signal: SignalEvent, existing_position: Optional[Position]) -> float:
        """
        Calculate order quantity based on signal and risk management.
        
        Args:
            signal: Trading signal
            existing_position: Current position (if any)
            
        Returns:
            Order quantity (positive for buy, negative for sell)
        """
        # Get available capital
        available_capital = self.cash * self.max_position_size
        
        # Adjust by signal strength
        position_value = available_capital * signal.strength
        
        # Estimate price (would be from market data in real implementation)
        estimated_price = signal.metadata.get('current_price', 1.0)
        
        # Calculate base quantity
        quantity = position_value / estimated_price
        
        # Handle existing position
        if existing_position:
            if signal.signal_type == 'BUY' and existing_position.quantity > 0:
                # Adding to long position (pyramiding)
                quantity *= 0.5  # Reduce size for pyramiding
            elif signal.signal_type == 'SELL' and existing_position.quantity < 0:
                # Adding to short position
                quantity *= 0.5
            elif signal.signal_type == 'BUY' and existing_position.quantity < 0:
                # Closing short and going long
                quantity = abs(existing_position.quantity) + quantity
            elif signal.signal_type == 'SELL' and existing_position.quantity > 0:
                # Closing long and going short
                quantity = -existing_position.quantity - quantity
        
        # Apply direction
        if signal.signal_type == 'SELL':
            quantity = -abs(quantity)
        
        return quantity
    
    def _create_position(self, fill: FillEvent):
        """Create a new position from a fill event."""
        quantity = fill.quantity if fill.direction == 'BUY' else -fill.quantity
        
        position = Position(
            symbol=fill.symbol,
            quantity=quantity,
            entry_price=fill.price,
            entry_time=fill.timestamp,
            current_price=fill.price,
            commission_paid=fill.commission
        )
        
        self.positions[fill.symbol] = position
        logger.info(f"Created new position: {position.symbol} {position.side} {abs(position.quantity)} @ {position.entry_price}")
    
    def _update_position(self, fill: FillEvent):
        """Update an existing position with a new fill."""
        position = self.positions[fill.symbol]
        fill_quantity = fill.quantity if fill.direction == 'BUY' else -fill.quantity
        
        # Check if this closes the position
        if np.sign(position.quantity) != np.sign(fill_quantity) and abs(fill_quantity) >= abs(position.quantity):
            # Position is closed
            self._close_position(fill)
        else:
            # Update position
            new_quantity = position.quantity + fill_quantity
            
            if new_quantity == 0:
                # Exact close
                self._close_position(fill)
            else:
                # Partial close or addition
                if np.sign(position.quantity) != np.sign(new_quantity):
                    # Partial close and reverse
                    self._close_position(fill, partial_quantity=abs(position.quantity))
                    remaining_quantity = fill_quantity + position.quantity
                    
                    # Create new position with remaining
                    new_fill = FillEvent(
                        timestamp=fill.timestamp,
                        symbol=fill.symbol,
                        direction='BUY' if remaining_quantity > 0 else 'SELL',
                        quantity=abs(remaining_quantity),
                        price=fill.price,
                        commission=0,  # Commission already accounted
                        slippage=0,
                        order_id=fill.order_id + '_new'
                    )
                    self._create_position(new_fill)
                else:
                    # Adding to position
                    new_entry_price = (
                        (position.entry_price * abs(position.quantity) + fill.price * abs(fill_quantity)) /
                        (abs(position.quantity) + abs(fill_quantity))
                    )
                    position.quantity = new_quantity
                    position.entry_price = new_entry_price
                    position.commission_paid += fill.commission
    
    def _close_position(self, fill: FillEvent, partial_quantity: Optional[float] = None):
        """Close a position and record the trade."""
        position = self.positions[fill.symbol]
        
        # Determine close quantity
        close_quantity = partial_quantity or abs(position.quantity)
        
        # Calculate P&L
        if position.quantity > 0:  # Long position
            pnl = close_quantity * (fill.price - position.entry_price)
        else:  # Short position
            pnl = close_quantity * (position.entry_price - fill.price)
        
        pnl_percent = (pnl / (position.entry_price * close_quantity)) * 100
        
        # Create trade record
        trade = Trade(
            symbol=position.symbol,
            entry_time=position.entry_time,
            exit_time=fill.timestamp,
            side=position.side,
            quantity=close_quantity,
            entry_price=position.entry_price,
            exit_price=fill.price,
            pnl=pnl - position.commission_paid - fill.commission,
            pnl_percent=pnl_percent,
            commission=position.commission_paid + fill.commission
        )
        
        self.closed_trades.append(trade)
        
        # Remove or update position
        if partial_quantity is None:
            del self.positions[fill.symbol]
            logger.info(f"Closed position: {trade.symbol} P&L: ${trade.pnl:.2f} ({trade.pnl_percent:.2f}%)")
        else:
            position.quantity -= close_quantity if position.quantity > 0 else -close_quantity
            position.realized_pnl += pnl