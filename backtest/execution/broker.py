"""
Simulated Broker Module

This module simulates broker functionality including order execution,
slippage modeling, and transaction costs.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
import numpy as np
import pandas as pd

from ..core.events import OrderEvent, FillEvent


logger = logging.getLogger(__name__)


class SimulatedBroker:
    """
    Simulated broker for backtesting.
    
    This class simulates realistic order execution including:
    - Market impact and slippage
    - Commission calculation
    - Order validation
    - Fill price determination
    """
    
    def __init__(
        self,
        slippage: float = 0.001,
        commission: float = 0.001,
        min_commission: float = 0.0,
        maker_fee: float = 0.0006,
        taker_fee: float = 0.001,
        use_maker_taker: bool = False
    ):
        """
        Initialize the simulated broker.
        
        Args:
            slippage: Expected slippage as decimal (0.001 = 0.1%)
            commission: Fixed commission rate
            min_commission: Minimum commission per trade
            maker_fee: Maker fee (for limit orders)
            taker_fee: Taker fee (for market orders)
            use_maker_taker: Whether to use maker/taker fee model
        """
        self.slippage = slippage
        self.commission = commission
        self.min_commission = min_commission
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.use_maker_taker = use_maker_taker
        
        # Execution tracking
        self.total_orders = 0
        self.filled_orders = 0
        self.rejected_orders = 0
        self.total_slippage_cost = 0.0
        self.total_commission_paid = 0.0
        
        # Order book simulation (simplified)
        self.current_prices: Dict[str, float] = {}
        self.market_depth: Dict[str, Dict[str, List[tuple]]] = {}
        
        # Pending orders
        self.pending_orders: Dict[str, OrderEvent] = {}
        
        logger.info(f"SimulatedBroker initialized with slippage={slippage}, commission={commission}")
    
    def reset(self):
        """Reset broker state for new backtest."""
        self.total_orders = 0
        self.filled_orders = 0
        self.rejected_orders = 0
        self.total_slippage_cost = 0.0
        self.total_commission_paid = 0.0
        self.current_prices = {}
        self.market_depth = {}
        self.pending_orders = {}
    
    def update_market_price(self, symbol: str, price: float):
        """
        Update current market price for a symbol.
        
        Args:
            symbol: Trading symbol
            price: Current market price
        """
        self.current_prices[symbol] = price
    
    def execute_order(self, order: OrderEvent) -> Optional[FillEvent]:
        """
        Execute an order and return fill event.
        
        Args:
            order: Order to execute
            
        Returns:
            FillEvent if order is filled, None if rejected
        """
        self.total_orders += 1
        
        # Validate order
        if not self._validate_order(order):
            self.rejected_orders += 1
            logger.warning(f"Order rejected: {order}")
            return None
        
        # Get current market price
        market_price = self.current_prices.get(order.symbol)
        if market_price is None:
            logger.error(f"No market price available for {order.symbol}")
            self.rejected_orders += 1
            return None
        
        # Determine fill price based on order type
        if order.order_type == 'MARKET':
            fill_price = self._calculate_market_fill_price(order, market_price)
        else:  # LIMIT
            fill_price = self._calculate_limit_fill_price(order, market_price)
            if fill_price is None:
                # Limit order not filled, add to pending
                order_id = str(uuid.uuid4())
                self.pending_orders[order_id] = order
                logger.info(f"Limit order added to pending: {order_id}")
                return None
        
        # Calculate actual fill quantity (considering liquidity)
        fill_quantity = self._calculate_fill_quantity(order, fill_price)
        
        # Calculate costs
        slippage_cost = self._calculate_slippage_cost(order, market_price, fill_price, fill_quantity)
        commission_cost = self._calculate_commission(order, fill_price, fill_quantity)
        
        # Create fill event
        fill = FillEvent(
            timestamp=order.timestamp,
            symbol=order.symbol,
            direction=order.direction,
            quantity=fill_quantity,
            price=fill_price,
            commission=commission_cost,
            slippage=slippage_cost,
            order_id=str(uuid.uuid4()),
            metadata={
                'order_type': order.order_type,
                'market_price': market_price,
                'price_improvement': market_price - fill_price if order.direction == 'BUY' else fill_price - market_price
            }
        )
        
        # Update statistics
        self.filled_orders += 1
        self.total_slippage_cost += slippage_cost
        self.total_commission_paid += commission_cost
        
        logger.info(f"Order filled: {fill}")
        
        return fill
    
    def check_pending_orders(self, symbol: str) -> List[FillEvent]:
        """
        Check if any pending limit orders can be filled.
        
        Args:
            symbol: Symbol to check
            
        Returns:
            List of fill events for executed orders
        """
        fills = []
        market_price = self.current_prices.get(symbol)
        
        if market_price is None:
            return fills
        
        orders_to_remove = []
        
        for order_id, order in self.pending_orders.items():
            if order.symbol != symbol:
                continue
            
            # Check if limit order can be filled
            can_fill = False
            if order.direction == 'BUY' and market_price <= order.price:
                can_fill = True
            elif order.direction == 'SELL' and market_price >= order.price:
                can_fill = True
            
            if can_fill:
                # Execute the order
                fill = self.execute_order(order)
                if fill:
                    fills.append(fill)
                    orders_to_remove.append(order_id)
        
        # Remove filled orders
        for order_id in orders_to_remove:
            del self.pending_orders[order_id]
        
        return fills
    
    def _validate_order(self, order: OrderEvent) -> bool:
        """
        Validate order parameters.
        
        Args:
            order: Order to validate
            
        Returns:
            True if order is valid
        """
        # Check quantity
        if order.quantity <= 0:
            logger.error(f"Invalid order quantity: {order.quantity}")
            return False
        
        # Check limit price for limit orders
        if order.order_type == 'LIMIT' and order.price is None:
            logger.error("Limit order missing price")
            return False
        
        # Additional validation can be added here
        # - Check margin requirements
        # - Check position limits
        # - Check trading hours
        
        return True
    
    def _calculate_market_fill_price(self, order: OrderEvent, market_price: float) -> float:
        """
        Calculate fill price for market order including slippage.
        
        Args:
            order: Market order
            market_price: Current market price
            
        Returns:
            Fill price including slippage
        """
        # Random slippage factor
        slippage_factor = np.random.uniform(0, self.slippage)
        
        # Adverse selection: buys fill higher, sells fill lower
        if order.direction == 'BUY':
            fill_price = market_price * (1 + slippage_factor)
        else:  # SELL
            fill_price = market_price * (1 - slippage_factor)
        
        # Add market impact for large orders
        market_impact = self._calculate_market_impact(order.quantity, market_price)
        if order.direction == 'BUY':
            fill_price += market_impact
        else:
            fill_price -= market_impact
        
        return fill_price
    
    def _calculate_limit_fill_price(self, order: OrderEvent, market_price: float) -> Optional[float]:
        """
        Calculate fill price for limit order.
        
        Args:
            order: Limit order
            market_price: Current market price
            
        Returns:
            Fill price if order can be filled, None otherwise
        """
        # Check if limit order can be filled
        if order.direction == 'BUY':
            if market_price <= order.price:
                # Buy limit filled at order price or better
                return min(order.price, market_price)
            else:
                return None
        else:  # SELL
            if market_price >= order.price:
                # Sell limit filled at order price or better
                return max(order.price, market_price)
            else:
                return None
    
    def _calculate_fill_quantity(self, order: OrderEvent, fill_price: float) -> float:
        """
        Calculate actual fill quantity considering liquidity.
        
        Args:
            order: Order being filled
            fill_price: Execution price
            
        Returns:
            Actual fill quantity
        """
        # For simplicity, assume full fill in backtesting
        # In reality, large orders might be partially filled
        return order.quantity
    
    def _calculate_slippage_cost(self, order: OrderEvent, market_price: float, 
                                 fill_price: float, quantity: float) -> float:
        """
        Calculate slippage cost.
        
        Args:
            order: Executed order
            market_price: Market price at order time
            fill_price: Actual fill price
            quantity: Fill quantity
            
        Returns:
            Slippage cost in currency units
        """
        if order.direction == 'BUY':
            slippage_per_unit = fill_price - market_price
        else:  # SELL
            slippage_per_unit = market_price - fill_price
        
        return max(0, slippage_per_unit * quantity)
    
    def _calculate_commission(self, order: OrderEvent, fill_price: float, quantity: float) -> float:
        """
        Calculate commission for the trade.
        
        Args:
            order: Executed order
            fill_price: Fill price
            quantity: Fill quantity
            
        Returns:
            Commission amount
        """
        trade_value = fill_price * quantity
        
        if self.use_maker_taker:
            # Use maker/taker fee model
            if order.order_type == 'MARKET':
                commission = trade_value * self.taker_fee
            else:  # LIMIT
                commission = trade_value * self.maker_fee
        else:
            # Use fixed commission rate
            commission = trade_value * self.commission
        
        # Apply minimum commission
        return max(commission, self.min_commission)
    
    def _calculate_market_impact(self, quantity: float, price: float) -> float:
        """
        Calculate market impact for large orders.
        
        Args:
            quantity: Order size
            price: Current price
            
        Returns:
            Price impact
        """
        # Simple square-root market impact model
        # Impact increases with square root of order size
        typical_volume = 1000  # Assume typical order size
        impact_coefficient = 0.0001  # 1 basis point per typical order
        
        relative_size = quantity / typical_volume
        impact = impact_coefficient * np.sqrt(relative_size) * price
        
        return impact
    
    def get_execution_statistics(self) -> Dict[str, Any]:
        """
        Get broker execution statistics.
        
        Returns:
            Dictionary of execution metrics
        """
        fill_rate = self.filled_orders / self.total_orders if self.total_orders > 0 else 0
        avg_slippage = self.total_slippage_cost / self.filled_orders if self.filled_orders > 0 else 0
        avg_commission = self.total_commission_paid / self.filled_orders if self.filled_orders > 0 else 0
        
        return {
            'total_orders': self.total_orders,
            'filled_orders': self.filled_orders,
            'rejected_orders': self.rejected_orders,
            'pending_orders': len(self.pending_orders),
            'fill_rate': fill_rate,
            'total_slippage_cost': self.total_slippage_cost,
            'total_commission_paid': self.total_commission_paid,
            'avg_slippage_per_trade': avg_slippage,
            'avg_commission_per_trade': avg_commission
        }