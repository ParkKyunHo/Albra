"""
Risk Management Module

This module provides comprehensive risk management functionality including
position sizing, risk limits, and portfolio protection mechanisms.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from dataclasses import dataclass, field

from ..core.events import SignalEvent, RiskEvent, MarketEvent
from ..core.portfolio import Portfolio


logger = logging.getLogger(__name__)


@dataclass
class RiskParameters:
    """Risk management parameters."""
    max_position_size: float = 0.1  # Max 10% per position
    max_portfolio_risk: float = 0.02  # Max 2% portfolio risk per trade
    max_leverage: float = 10.0  # Maximum leverage
    max_drawdown: float = 0.2  # Maximum drawdown before halt
    daily_loss_limit: float = 0.05  # Daily loss limit
    position_limit: int = 10  # Maximum number of positions
    correlation_limit: float = 0.7  # Maximum correlation between positions
    
    # Dynamic risk adjustment
    use_dynamic_sizing: bool = True
    kelly_fraction: float = 0.25  # Fraction of Kelly criterion to use
    
    # Risk metrics calculation periods
    volatility_lookback: int = 20
    correlation_lookback: int = 60


class RiskManager:
    """
    Comprehensive risk management system.
    
    This class handles all aspects of risk management including:
    - Position sizing
    - Risk limit enforcement
    - Drawdown protection
    - Correlation management
    - Dynamic risk adjustment
    """
    
    def __init__(self, parameters: Optional[RiskParameters] = None):
        """
        Initialize risk manager.
        
        Args:
            parameters: Risk management parameters
        """
        self.params = parameters or RiskParameters()
        
        # Risk state tracking
        self.current_drawdown = 0.0
        self.max_drawdown_reached = 0.0
        self.daily_loss = 0.0
        self.last_reset_date = datetime.now()
        
        # Historical data for risk calculations
        self.price_history: Dict[str, List[float]] = {}
        self.returns_history: Dict[str, List[float]] = {}
        self.correlation_matrix: Optional[pd.DataFrame] = None
        
        # Risk events
        self.risk_events: List[RiskEvent] = []
        
        logger.info(f"RiskManager initialized with parameters: {self.params}")
    
    def reset(self):
        """Reset risk manager state."""
        self.current_drawdown = 0.0
        self.max_drawdown_reached = 0.0
        self.daily_loss = 0.0
        self.last_reset_date = datetime.now()
        self.price_history = {}
        self.returns_history = {}
        self.correlation_matrix = None
        self.risk_events = []
    
    def check_risk_limits(self, portfolio: Portfolio, market_event: MarketEvent) -> List[RiskEvent]:
        """
        Check all risk limits and generate risk events.
        
        Args:
            portfolio: Current portfolio state
            market_event: Latest market data
            
        Returns:
            List of risk events
        """
        events = []
        
        # Update price history
        self._update_price_history(market_event.symbol, market_event.close)
        
        # Check drawdown
        drawdown_event = self._check_drawdown(portfolio)
        if drawdown_event:
            events.append(drawdown_event)
        
        # Check daily loss limit
        daily_loss_event = self._check_daily_loss(portfolio)
        if daily_loss_event:
            events.append(daily_loss_event)
        
        # Check position concentration
        concentration_event = self._check_position_concentration(portfolio)
        if concentration_event:
            events.append(concentration_event)
        
        # Check leverage
        leverage_event = self._check_leverage(portfolio)
        if leverage_event:
            events.append(leverage_event)
        
        # Reset daily loss if new day
        if market_event.timestamp.date() > self.last_reset_date.date():
            self.daily_loss = 0.0
            self.last_reset_date = market_event.timestamp
        
        self.risk_events.extend(events)
        return events
    
    def approve_signal(self, signal: SignalEvent, portfolio: Portfolio) -> bool:
        """
        Approve or reject a trading signal based on risk criteria.
        
        Args:
            signal: Trading signal to evaluate
            portfolio: Current portfolio state
            
        Returns:
            True if signal is approved, False otherwise
        """
        # Check if we're in risk-off mode
        if self.current_drawdown > self.params.max_drawdown * 0.8:
            logger.warning(f"Signal rejected: Near max drawdown ({self.current_drawdown:.2%})")
            return False
        
        # Check position limit
        if len(portfolio.positions) >= self.params.position_limit:
            logger.warning(f"Signal rejected: Position limit reached ({self.params.position_limit})")
            return False
        
        # Check daily loss limit
        if self.daily_loss > self.params.daily_loss_limit * 0.8:
            logger.warning(f"Signal rejected: Near daily loss limit ({self.daily_loss:.2%})")
            return False
        
        # Check correlation with existing positions
        if not self._check_correlation_limit(signal.symbol, portfolio):
            logger.warning(f"Signal rejected: Correlation limit exceeded")
            return False
        
        return True
    
    def calculate_position_size(
        self,
        signal: SignalEvent,
        portfolio: Portfolio,
        current_price: float,
        stop_loss: Optional[float] = None
    ) -> float:
        """
        Calculate optimal position size based on risk parameters.
        
        Args:
            signal: Trading signal
            portfolio: Current portfolio
            current_price: Current market price
            stop_loss: Stop loss price (optional)
            
        Returns:
            Position size in base currency units
        """
        available_capital = portfolio.get_total_equity()
        
        # Base position size from parameters
        base_size = available_capital * self.params.max_position_size
        
        # Adjust by signal strength
        signal_adjusted_size = base_size * signal.strength
        
        # Apply Kelly criterion if enabled
        if self.params.use_dynamic_sizing:
            kelly_size = self._calculate_kelly_size(signal.symbol, available_capital)
            if kelly_size > 0:
                signal_adjusted_size = min(signal_adjusted_size, kelly_size)
        
        # Risk-based sizing using stop loss
        if stop_loss:
            risk_based_size = self._calculate_risk_based_size(
                available_capital, current_price, stop_loss
            )
            signal_adjusted_size = min(signal_adjusted_size, risk_based_size)
        
        # Adjust for current market conditions
        volatility_adjusted_size = self._adjust_for_volatility(
            signal.symbol, signal_adjusted_size
        )
        
        # Adjust for portfolio heat
        heat_adjusted_size = self._adjust_for_portfolio_heat(
            portfolio, volatility_adjusted_size
        )
        
        # Convert to units
        position_units = heat_adjusted_size / current_price
        
        return position_units
    
    def _update_price_history(self, symbol: str, price: float):
        """Update price history for risk calculations."""
        if symbol not in self.price_history:
            self.price_history[symbol] = []
            self.returns_history[symbol] = []
        
        self.price_history[symbol].append(price)
        
        # Calculate return if we have previous price
        if len(self.price_history[symbol]) > 1:
            prev_price = self.price_history[symbol][-2]
            ret = (price - prev_price) / prev_price
            self.returns_history[symbol].append(ret)
        
        # Keep only necessary history
        max_lookback = max(self.params.volatility_lookback, self.params.correlation_lookback)
        if len(self.price_history[symbol]) > max_lookback + 1:
            self.price_history[symbol].pop(0)
        if len(self.returns_history[symbol]) > max_lookback:
            self.returns_history[symbol].pop(0)
    
    def _check_drawdown(self, portfolio: Portfolio) -> Optional[RiskEvent]:
        """Check drawdown limits."""
        equity = portfolio.get_total_equity()
        peak_equity = max(portfolio.initial_capital, equity)  # Simplified peak tracking
        
        drawdown = (peak_equity - equity) / peak_equity
        self.current_drawdown = drawdown
        self.max_drawdown_reached = max(self.max_drawdown_reached, drawdown)
        
        if drawdown > self.params.max_drawdown:
            return RiskEvent(
                timestamp=datetime.now(),
                risk_type='DRAWDOWN',
                severity='CRITICAL',
                message=f"Maximum drawdown exceeded: {drawdown:.2%}",
                action="HALT_TRADING",
                metadata={'drawdown': drawdown, 'limit': self.params.max_drawdown}
            )
        elif drawdown > self.params.max_drawdown * 0.8:
            return RiskEvent(
                timestamp=datetime.now(),
                risk_type='DRAWDOWN',
                severity='HIGH',
                message=f"Approaching max drawdown: {drawdown:.2%}",
                action="REDUCE_RISK",
                metadata={'drawdown': drawdown, 'limit': self.params.max_drawdown}
            )
        
        return None
    
    def _check_daily_loss(self, portfolio: Portfolio) -> Optional[RiskEvent]:
        """Check daily loss limits."""
        # This is simplified - in production, track intraday P&L properly
        current_equity = portfolio.get_total_equity()
        daily_pnl_pct = (current_equity - portfolio.initial_capital) / portfolio.initial_capital
        
        if daily_pnl_pct < 0:
            self.daily_loss = abs(daily_pnl_pct)
        
        if self.daily_loss > self.params.daily_loss_limit:
            return RiskEvent(
                timestamp=datetime.now(),
                risk_type='DAILY_LOSS',
                severity='HIGH',
                message=f"Daily loss limit exceeded: {self.daily_loss:.2%}",
                action="HALT_TRADING_TODAY",
                metadata={'daily_loss': self.daily_loss, 'limit': self.params.daily_loss_limit}
            )
        
        return None
    
    def _check_position_concentration(self, portfolio: Portfolio) -> Optional[RiskEvent]:
        """Check position concentration limits."""
        if not portfolio.positions:
            return None
        
        total_equity = portfolio.get_total_equity()
        positions_summary = portfolio.get_positions_summary()
        
        for symbol, position_data in positions_summary.items():
            position_value = position_data['market_value']
            concentration = position_value / total_equity
            
            if concentration > self.params.max_position_size * 1.5:
                return RiskEvent(
                    timestamp=datetime.now(),
                    risk_type='POSITION_SIZE',
                    severity='HIGH',
                    message=f"Position concentration too high: {symbol} = {concentration:.2%}",
                    action="REDUCE_POSITION",
                    metadata={'symbol': symbol, 'concentration': concentration}
                )
        
        return None
    
    def _check_leverage(self, portfolio: Portfolio) -> Optional[RiskEvent]:
        """Check leverage limits."""
        total_position_value = sum(
            pos['market_value'] for pos in portfolio.get_positions_summary().values()
        )
        equity = portfolio.get_total_equity()
        
        if equity > 0:
            leverage = total_position_value / equity
            
            if leverage > self.params.max_leverage:
                return RiskEvent(
                    timestamp=datetime.now(),
                    risk_type='LEVERAGE',
                    severity='CRITICAL',
                    message=f"Leverage limit exceeded: {leverage:.1f}x",
                    action="REDUCE_LEVERAGE",
                    metadata={'leverage': leverage, 'limit': self.params.max_leverage}
                )
        
        return None
    
    def _check_correlation_limit(self, symbol: str, portfolio: Portfolio) -> bool:
        """Check if adding position would exceed correlation limits."""
        if not portfolio.positions or symbol not in self.returns_history:
            return True
        
        # Calculate correlation with existing positions
        symbol_returns = pd.Series(self.returns_history[symbol][-self.params.correlation_lookback:])
        
        for existing_symbol in portfolio.positions:
            if existing_symbol == symbol or existing_symbol not in self.returns_history:
                continue
            
            existing_returns = pd.Series(
                self.returns_history[existing_symbol][-self.params.correlation_lookback:]
            )
            
            if len(symbol_returns) > 10 and len(existing_returns) > 10:
                correlation = symbol_returns.corr(existing_returns)
                
                if abs(correlation) > self.params.correlation_limit:
                    logger.info(f"High correlation detected: {symbol} vs {existing_symbol} = {correlation:.2f}")
                    return False
        
        return True
    
    def _calculate_kelly_size(self, symbol: str, available_capital: float) -> float:
        """Calculate position size using Kelly criterion."""
        if symbol not in self.returns_history or len(self.returns_history[symbol]) < 20:
            return 0
        
        returns = np.array(self.returns_history[symbol])
        
        # Calculate win rate and average win/loss
        winning_returns = returns[returns > 0]
        losing_returns = returns[returns < 0]
        
        if len(winning_returns) == 0 or len(losing_returns) == 0:
            return 0
        
        win_rate = len(winning_returns) / len(returns)
        avg_win = np.mean(winning_returns)
        avg_loss = abs(np.mean(losing_returns))
        
        # Kelly formula: f = p - q/b
        # where p = win rate, q = loss rate, b = win/loss ratio
        if avg_loss > 0:
            kelly_fraction = win_rate - (1 - win_rate) / (avg_win / avg_loss)
            kelly_fraction = max(0, min(kelly_fraction, 1))  # Bound between 0 and 1
            
            # Apply Kelly fraction parameter (fractional Kelly)
            kelly_size = available_capital * kelly_fraction * self.params.kelly_fraction
            
            return kelly_size
        
        return 0
    
    def _calculate_risk_based_size(self, capital: float, entry_price: float, stop_loss: float) -> float:
        """Calculate position size based on stop loss risk."""
        risk_per_trade = capital * self.params.max_portfolio_risk
        price_risk = abs(entry_price - stop_loss)
        
        if price_risk > 0:
            position_value = risk_per_trade * entry_price / price_risk
            return position_value
        
        return capital * self.params.max_position_size
    
    def _adjust_for_volatility(self, symbol: str, base_size: float) -> float:
        """Adjust position size based on volatility."""
        if symbol not in self.returns_history or len(self.returns_history[symbol]) < self.params.volatility_lookback:
            return base_size
        
        # Calculate recent volatility
        recent_returns = self.returns_history[symbol][-self.params.volatility_lookback:]
        volatility = np.std(recent_returns) * np.sqrt(252)  # Annualized
        
        # Target volatility approach
        target_volatility = 0.15  # 15% target
        if volatility > 0:
            vol_scalar = min(1.0, target_volatility / volatility)
            return base_size * vol_scalar
        
        return base_size
    
    def _adjust_for_portfolio_heat(self, portfolio: Portfolio, base_size: float) -> float:
        """Adjust position size based on portfolio heat (open risk)."""
        # Reduce size if we have many open positions
        num_positions = len(portfolio.positions)
        
        if num_positions >= self.params.position_limit * 0.8:
            # Reduce size as we approach position limit
            reduction_factor = 1 - (num_positions / self.params.position_limit) * 0.5
            return base_size * reduction_factor
        
        return base_size