"""
Base Strategy Class

This module defines the abstract base class for all trading strategies.
All custom strategies must inherit from BaseStrategy and implement
the required methods.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Tuple
import pandas as pd
import numpy as np
from dataclasses import dataclass, field

from ..core.events import MarketEvent, SignalEvent, FillEvent


logger = logging.getLogger(__name__)


@dataclass
class StrategyParameters:
    """
    Container for strategy parameters.
    
    This class helps manage strategy parameters and provides
    validation and serialization capabilities.
    """
    lookback_period: int = 20
    entry_threshold: float = 0.0
    exit_threshold: float = 0.0
    stop_loss: float = 0.02
    take_profit: float = 0.05
    position_size: float = 0.1
    max_positions: int = 1
    use_trailing_stop: bool = False
    trailing_stop_distance: float = 0.01
    
    def validate(self) -> bool:
        """Validate parameter values."""
        if self.lookback_period <= 0:
            raise ValueError("Lookback period must be positive")
        if not 0 < self.position_size <= 1:
            raise ValueError("Position size must be between 0 and 1")
        if self.stop_loss < 0:
            raise ValueError("Stop loss must be non-negative")
        if self.take_profit < 0:
            raise ValueError("Take profit must be non-negative")
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert parameters to dictionary."""
        return {
            'lookback_period': self.lookback_period,
            'entry_threshold': self.entry_threshold,
            'exit_threshold': self.exit_threshold,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'position_size': self.position_size,
            'max_positions': self.max_positions,
            'use_trailing_stop': self.use_trailing_stop,
            'trailing_stop_distance': self.trailing_stop_distance
        }


class BaseStrategy(ABC):
    """
    Abstract base class for trading strategies.
    
    This class provides the framework for implementing trading strategies.
    Subclasses must implement the generate_signal method and can override
    other methods for custom behavior.
    """
    
    def __init__(self, parameters: Optional[StrategyParameters] = None):
        """
        Initialize the strategy.
        
        Args:
            parameters: Strategy parameters (uses defaults if None)
        """
        self.parameters = parameters or StrategyParameters()
        self.parameters.validate()
        
        # Strategy state
        self.is_initialized = False
        self.current_positions = 0
        self.historical_signals: List[SignalEvent] = []
        
        # Data buffers for indicators
        self.price_history: List[float] = []
        self.indicator_history: Dict[str, List[float]] = {}
        
        # Performance tracking
        self.total_signals = 0
        self.winning_trades = 0
        self.losing_trades = 0
        
        logger.info(f"Strategy {self.__class__.__name__} initialized with parameters: {self.parameters.to_dict()}")
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the strategy name."""
        pass
    
    @property
    @abstractmethod
    def required_indicators(self) -> List[str]:
        """
        Return list of required indicators.
        
        This helps the backtesting engine pre-calculate necessary indicators.
        """
        pass
    
    @abstractmethod
    def generate_signal(self, market_event: MarketEvent) -> Optional[SignalEvent]:
        """
        Generate trading signal based on market data.
        
        This is the main method that must be implemented by all strategies.
        
        Args:
            market_event: Current market data
            
        Returns:
            SignalEvent if a signal is generated, None otherwise
        """
        pass
    
    def calculate_indicators(self, market_data: pd.Series) -> Dict[str, float]:
        """
        Calculate indicators for the current market data.
        
        This method can be overridden to calculate custom indicators.
        
        Args:
            market_data: OHLCV data for current timestamp
            
        Returns:
            Dictionary of indicator values
        """
        indicators = {}
        
        # Update price history
        self.price_history.append(market_data['close'])
        if len(self.price_history) > self.parameters.lookback_period * 2:
            self.price_history.pop(0)
        
        # Calculate basic indicators if we have enough data
        if len(self.price_history) >= self.parameters.lookback_period:
            prices = np.array(self.price_history)
            
            # Simple Moving Average
            indicators['sma'] = np.mean(prices[-self.parameters.lookback_period:])
            
            # Price change
            indicators['price_change'] = (prices[-1] - prices[-2]) / prices[-2] if len(prices) > 1 else 0
            
            # Volatility (standard deviation)
            indicators['volatility'] = np.std(prices[-self.parameters.lookback_period:])
        
        return indicators
    
    def on_fill(self, fill_event: FillEvent):
        """
        Handle order fill notification.
        
        This method is called when an order is filled and can be used
        to update strategy state.
        
        Args:
            fill_event: Order fill details
        """
        if fill_event.direction == 'BUY':
            self.current_positions += 1
        else:
            self.current_positions = max(0, self.current_positions - 1)
        
        logger.debug(f"Strategy {self.name} processed fill: {fill_event}")
    
    def reset(self):
        """Reset strategy state for a new backtest run."""
        self.is_initialized = False
        self.current_positions = 0
        self.historical_signals = []
        self.price_history = []
        self.indicator_history = {}
        self.total_signals = 0
        self.winning_trades = 0
        self.losing_trades = 0
        
        logger.info(f"Strategy {self.name} reset")
    
    def can_trade(self) -> bool:
        """
        Check if the strategy can generate new trades.
        
        Returns:
            True if trading is allowed, False otherwise
        """
        return self.current_positions < self.parameters.max_positions
    
    def get_signal_strength(self, signal_value: float) -> float:
        """
        Convert raw signal value to normalized strength (0-1).
        
        Args:
            signal_value: Raw signal value
            
        Returns:
            Normalized signal strength between 0 and 1
        """
        # Simple sigmoid normalization
        return 1 / (1 + np.exp(-signal_value))
    
    def create_signal(
        self,
        timestamp: pd.Timestamp,
        symbol: str,
        signal_type: str,
        strength: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SignalEvent:
        """
        Helper method to create a signal event.
        
        Args:
            timestamp: Signal timestamp
            symbol: Trading symbol
            signal_type: BUY, SELL, or HOLD
            strength: Signal strength (0-1)
            metadata: Additional signal information
            
        Returns:
            SignalEvent object
        """
        signal = SignalEvent(
            timestamp=timestamp,
            symbol=symbol,
            signal_type=signal_type,
            strength=min(1.0, max(0.0, strength)),
            strategy_name=self.name,
            metadata=metadata or {}
        )
        
        self.historical_signals.append(signal)
        self.total_signals += 1
        
        return signal
    
    def get_parameters(self) -> Dict[str, Any]:
        """Get current strategy parameters."""
        return self.parameters.to_dict()
    
    def set_parameters(self, params: Dict[str, Any]):
        """
        Update strategy parameters.
        
        Args:
            params: Dictionary of parameter values
        """
        for key, value in params.items():
            if hasattr(self.parameters, key):
                setattr(self.parameters, key, value)
        
        self.parameters.validate()
        logger.info(f"Strategy {self.name} parameters updated: {params}")
    
    def get_state(self) -> Dict[str, Any]:
        """
        Get current strategy state.
        
        Returns:
            Dictionary containing strategy state
        """
        return {
            'name': self.name,
            'parameters': self.parameters.to_dict(),
            'is_initialized': self.is_initialized,
            'current_positions': self.current_positions,
            'total_signals': self.total_signals,
            'price_history_length': len(self.price_history),
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades
        }


class IndicatorMixin:
    """
    Mixin class providing common technical indicators.
    
    This class can be mixed into strategies to provide easy access
    to common technical indicators.
    """
    
    @staticmethod
    def sma(prices: np.ndarray, period: int) -> float:
        """Simple Moving Average."""
        if len(prices) < period:
            return np.nan
        return np.mean(prices[-period:])
    
    @staticmethod
    def ema(prices: np.ndarray, period: int) -> float:
        """Exponential Moving Average."""
        if len(prices) < period:
            return np.nan
        
        multiplier = 2 / (period + 1)
        ema = prices[0]
        
        for price in prices[1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    @staticmethod
    def rsi(prices: np.ndarray, period: int = 14) -> float:
        """Relative Strength Index."""
        if len(prices) < period + 1:
            return np.nan
        
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    @staticmethod
    def bollinger_bands(prices: np.ndarray, period: int = 20, std_dev: int = 2) -> Tuple[float, float, float]:
        """
        Bollinger Bands.
        
        Returns:
            Tuple of (upper_band, middle_band, lower_band)
        """
        if len(prices) < period:
            return np.nan, np.nan, np.nan
        
        middle = np.mean(prices[-period:])
        std = np.std(prices[-period:])
        
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        
        return upper, middle, lower
    
    @staticmethod
    def macd(prices: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[float, float, float]:
        """
        MACD indicator.
        
        Returns:
            Tuple of (macd_line, signal_line, histogram)
        """
        if len(prices) < slow + signal:
            return np.nan, np.nan, np.nan
        
        # Calculate EMAs
        ema_fast = pd.Series(prices).ewm(span=fast, adjust=False).mean().iloc[-1]
        ema_slow = pd.Series(prices).ewm(span=slow, adjust=False).mean().iloc[-1]
        
        macd_line = ema_fast - ema_slow
        
        # For signal line, we need historical MACD values
        macd_values = []
        for i in range(signal):
            idx = -(signal - i)
            if len(prices) + idx >= slow:
                ema_f = pd.Series(prices[:idx]).ewm(span=fast, adjust=False).mean().iloc[-1]
                ema_s = pd.Series(prices[:idx]).ewm(span=slow, adjust=False).mean().iloc[-1]
                macd_values.append(ema_f - ema_s)
        
        signal_line = np.mean(macd_values) if macd_values else macd_line
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    @staticmethod
    def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
        """Average True Range."""
        if len(high) < period + 1:
            return np.nan
        
        tr_list = []
        for i in range(1, len(high)):
            tr = max(
                high[i] - low[i],
                abs(high[i] - close[i-1]),
                abs(low[i] - close[i-1])
            )
            tr_list.append(tr)
        
        return np.mean(tr_list[-period:]) if tr_list else np.nan