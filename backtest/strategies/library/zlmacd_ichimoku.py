"""
ZL MACD + Ichimoku Combined Strategy

This strategy combines Zero Lag MACD with Ichimoku Cloud for trend following
with multiple confirmation signals.
"""

import numpy as np
import pandas as pd
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from ...core.events import MarketEvent, SignalEvent
from ..base import BaseStrategy, StrategyParameters
from ..indicators import Indicators


@dataclass
class ZLMACDIchimokuParameters(StrategyParameters):
    """Parameters specific to ZLMACD Ichimoku strategy."""
    # ZL MACD parameters
    zlmacd_fast: int = 12
    zlmacd_slow: int = 26
    zlmacd_signal: int = 9
    
    # Ichimoku parameters
    tenkan_period: int = 9
    kijun_period: int = 26
    senkou_b_period: int = 52
    chikou_shift: int = 26
    cloud_shift: int = 26
    
    # Entry/Exit parameters
    min_signals_required: int = 3  # Minimum signals for entry
    use_cloud_exit: bool = True
    use_kijun_exit: bool = True
    
    # Risk parameters
    atr_period: int = 14
    atr_stop_multiplier: float = 1.5
    trailing_stop_activation: float = 0.03  # 3% profit to activate
    trailing_stop_distance: float = 0.10  # 10% from peak
    
    # Pyramiding
    enable_pyramiding: bool = True
    pyramid_levels: int = 3
    pyramid_size_reduction: float = 0.5  # Each level is 50% smaller
    
    # Market filter
    adx_period: int = 14
    adx_threshold: float = 25
    
    # Partial exits
    partial_exit_1_pct: float = 5.0  # First exit at 5% profit
    partial_exit_1_size: float = 0.25  # Exit 25% of position
    partial_exit_2_pct: float = 10.0
    partial_exit_2_size: float = 0.35
    partial_exit_3_pct: float = 15.0
    partial_exit_3_size: float = 0.40
    
    # Cross window tracking
    cross_window: int = 10  # Bars to consider cross valid


class ZLMACDIchimokuStrategy(BaseStrategy):
    """
    Advanced trend following strategy combining ZL MACD and Ichimoku Cloud.
    
    Entry signals:
    1. ZL MACD cross (golden/dead cross)
    2. Price position relative to cloud
    3. Tenkan/Kijun relationship
    4. Cloud color (bullish/bearish)
    
    Exit signals:
    1. Cloud penetration
    2. Kijun-sen touch
    3. Stop loss (ATR-based)
    4. Trailing stop
    5. Partial profit taking
    """
    
    def __init__(self, parameters: Optional[ZLMACDIchimokuParameters] = None):
        """Initialize strategy with parameters."""
        params = parameters or ZLMACDIchimokuParameters()
        super().__init__(params)
        
        # Strategy state
        self.last_golden_cross_bar = -999
        self.last_dead_cross_bar = -999
        self.current_bar = 0
        
        # Position tracking
        self.entry_price = None
        self.highest_price = None
        self.lowest_price = None
        self.trailing_stop_price = None
        self.partial_exits_done = {'level1': False, 'level2': False, 'level3': False}
        self.pyramid_count = 0
        
        # Indicator buffers
        self.zlmacd_buffer = []
        self.zlmacd_signal_buffer = []
        self.atr_buffer = []
        
    @property
    def name(self) -> str:
        """Strategy name."""
        return "ZLMACD_ICHIMOKU"
    
    @property
    def required_indicators(self) -> List[str]:
        """Required indicators for pre-calculation."""
        return ['zlmacd', 'ichimoku', 'atr', 'adx']
    
    def generate_signal(self, market_event: MarketEvent) -> Optional[SignalEvent]:
        """
        Generate trading signal based on ZL MACD and Ichimoku.
        
        Args:
            market_event: Current market data
            
        Returns:
            SignalEvent if conditions are met, None otherwise
        """
        self.current_bar += 1
        
        # Need minimum data for indicators
        if self.current_bar < self.parameters.senkou_b_period + self.parameters.cloud_shift:
            return None
        
        # Get current price
        price = market_event.close
        
        # Update position tracking
        if self.entry_price:
            if self.position_type == 'LONG':
                self.highest_price = max(self.highest_price or price, price)
            else:
                self.lowest_price = min(self.lowest_price or price, price)
        
        # Check for exit signals first
        exit_signal = self._check_exit_conditions(market_event)
        if exit_signal:
            self._reset_position_tracking()
            return exit_signal
        
        # Check for partial exit
        partial_exit = self._check_partial_exit(market_event)
        if partial_exit:
            return partial_exit
        
        # Check for new entry signals
        if self.can_trade():
            entry_signal = self._check_entry_conditions(market_event)
            if entry_signal:
                self._initialize_position_tracking(price, entry_signal.signal_type)
                return entry_signal
        
        # Check for pyramiding opportunity
        if self.parameters.enable_pyramiding and self.pyramid_count < self.parameters.pyramid_levels:
            pyramid_signal = self._check_pyramid_conditions(market_event)
            if pyramid_signal:
                self.pyramid_count += 1
                return pyramid_signal
        
        return None
    
    def calculate_indicators(self, market_data: pd.Series) -> Dict[str, float]:
        """Calculate all required indicators."""
        indicators = super().calculate_indicators(market_data)
        
        # For this implementation, we'll use pre-calculated indicators
        # In production, these would be calculated from price history
        
        # Placeholder values - in real implementation, calculate from buffers
        indicators['zlmacd'] = market_data.get('zlmacd', 0)
        indicators['zlmacd_signal'] = market_data.get('zlmacd_signal', 0)
        indicators['tenkan_sen'] = market_data.get('tenkan_sen', 0)
        indicators['kijun_sen'] = market_data.get('kijun_sen', 0)
        indicators['cloud_top'] = market_data.get('cloud_top', 0)
        indicators['cloud_bottom'] = market_data.get('cloud_bottom', 0)
        indicators['cloud_color'] = market_data.get('cloud_color', 0)
        indicators['atr'] = market_data.get('atr', 0)
        indicators['adx'] = market_data.get('adx', 0)
        
        return indicators
    
    def _check_entry_conditions(self, market_event: MarketEvent) -> Optional[SignalEvent]:
        """Check for entry conditions."""
        indicators = market_event.indicators
        price = market_event.close
        
        # Market filter - need trending market
        if indicators.get('adx', 0) < self.parameters.adx_threshold:
            return None
        
        # Check for long entry
        long_signals = self._count_long_signals(price, indicators)
        if long_signals >= self.parameters.min_signals_required:
            strength = min(1.0, long_signals / 4.0)  # Normalize to 0-1
            return self.create_signal(
                timestamp=market_event.timestamp,
                symbol=market_event.symbol,
                signal_type='BUY',
                strength=strength,
                metadata={
                    'entry_reason': 'ZLMACD_ICHIMOKU_LONG',
                    'signals_count': long_signals,
                    'current_price': price,
                    'atr': indicators.get('atr', 0)
                }
            )
        
        # Check for short entry
        short_signals = self._count_short_signals(price, indicators)
        if short_signals >= self.parameters.min_signals_required:
            strength = min(1.0, short_signals / 4.0)
            return self.create_signal(
                timestamp=market_event.timestamp,
                symbol=market_event.symbol,
                signal_type='SELL',
                strength=strength,
                metadata={
                    'entry_reason': 'ZLMACD_ICHIMOKU_SHORT',
                    'signals_count': short_signals,
                    'current_price': price,
                    'atr': indicators.get('atr', 0)
                }
            )
        
        return None
    
    def _count_long_signals(self, price: float, indicators: Dict[str, float]) -> int:
        """Count bullish signals."""
        signals = 0
        
        # 1. ZL MACD golden cross (current or recent)
        if self._check_golden_cross(indicators):
            signals += 1
        
        # 2. Price above cloud
        if price > indicators.get('cloud_top', 0):
            signals += 1
        
        # 3. Tenkan above Kijun
        if indicators.get('tenkan_sen', 0) > indicators.get('kijun_sen', 0):
            signals += 1
        
        # 4. Bullish cloud (green)
        if indicators.get('cloud_color', 0) == 1:
            signals += 1
        
        return signals
    
    def _count_short_signals(self, price: float, indicators: Dict[str, float]) -> int:
        """Count bearish signals."""
        signals = 0
        
        # 1. ZL MACD dead cross (current or recent)
        if self._check_dead_cross(indicators):
            signals += 1
        
        # 2. Price below cloud
        if price < indicators.get('cloud_bottom', 0):
            signals += 1
        
        # 3. Tenkan below Kijun
        if indicators.get('tenkan_sen', 0) < indicators.get('kijun_sen', 0):
            signals += 1
        
        # 4. Bearish cloud (red)
        if indicators.get('cloud_color', 0) == 0:
            signals += 1
        
        return signals
    
    def _check_golden_cross(self, indicators: Dict[str, float]) -> bool:
        """Check for ZL MACD golden cross."""
        # Update buffers
        self.zlmacd_buffer.append(indicators.get('zlmacd', 0))
        self.zlmacd_signal_buffer.append(indicators.get('zlmacd_signal', 0))
        
        if len(self.zlmacd_buffer) < 2:
            return False
        
        # Keep buffer size manageable
        if len(self.zlmacd_buffer) > 100:
            self.zlmacd_buffer.pop(0)
            self.zlmacd_signal_buffer.pop(0)
        
        # Check for cross
        current_above = self.zlmacd_buffer[-1] > self.zlmacd_signal_buffer[-1]
        prev_above = self.zlmacd_buffer[-2] <= self.zlmacd_signal_buffer[-2]
        
        if current_above and prev_above:
            self.last_golden_cross_bar = self.current_bar
            return True
        
        # Check if cross was recent
        return (self.current_bar - self.last_golden_cross_bar) <= self.parameters.cross_window
    
    def _check_dead_cross(self, indicators: Dict[str, float]) -> bool:
        """Check for ZL MACD dead cross."""
        if len(self.zlmacd_buffer) < 2:
            return False
        
        # Check for cross
        current_below = self.zlmacd_buffer[-1] < self.zlmacd_signal_buffer[-1]
        prev_below = self.zlmacd_buffer[-2] >= self.zlmacd_signal_buffer[-2]
        
        if current_below and prev_below:
            self.last_dead_cross_bar = self.current_bar
            return True
        
        # Check if cross was recent
        return (self.current_bar - self.last_dead_cross_bar) <= self.parameters.cross_window
    
    def _check_exit_conditions(self, market_event: MarketEvent) -> Optional[SignalEvent]:
        """Check for exit conditions."""
        if not self.entry_price:
            return None
        
        indicators = market_event.indicators
        price = market_event.close
        
        # Check stop loss
        if self._check_stop_loss(price, indicators):
            return self.create_signal(
                timestamp=market_event.timestamp,
                symbol=market_event.symbol,
                signal_type='SELL' if self.position_type == 'LONG' else 'BUY',
                strength=1.0,
                metadata={'exit_reason': 'STOP_LOSS'}
            )
        
        # Check trailing stop
        if self._check_trailing_stop(price):
            return self.create_signal(
                timestamp=market_event.timestamp,
                symbol=market_event.symbol,
                signal_type='SELL' if self.position_type == 'LONG' else 'BUY',
                strength=1.0,
                metadata={'exit_reason': 'TRAILING_STOP'}
            )
        
        # Check cloud exit
        if self.parameters.use_cloud_exit and self._check_cloud_exit(price, indicators):
            return self.create_signal(
                timestamp=market_event.timestamp,
                symbol=market_event.symbol,
                signal_type='SELL' if self.position_type == 'LONG' else 'BUY',
                strength=1.0,
                metadata={'exit_reason': 'CLOUD_EXIT'}
            )
        
        # Check Kijun exit
        if self.parameters.use_kijun_exit and self._check_kijun_exit(price, indicators):
            return self.create_signal(
                timestamp=market_event.timestamp,
                symbol=market_event.symbol,
                signal_type='SELL' if self.position_type == 'LONG' else 'BUY',
                strength=0.8,
                metadata={'exit_reason': 'KIJUN_EXIT'}
            )
        
        return None
    
    def _check_stop_loss(self, price: float, indicators: Dict[str, float]) -> bool:
        """Check if stop loss is hit."""
        if not self.entry_price:
            return False
        
        atr = indicators.get('atr', 0)
        if atr == 0:
            return False
        
        stop_distance = atr * self.parameters.atr_stop_multiplier
        
        if self.position_type == 'LONG':
            stop_price = self.entry_price - stop_distance
            return price <= stop_price
        else:  # SHORT
            stop_price = self.entry_price + stop_distance
            return price >= stop_price
    
    def _check_trailing_stop(self, price: float) -> bool:
        """Check if trailing stop is hit."""
        if not self.entry_price or not self.highest_price:
            return False
        
        if self.position_type == 'LONG':
            # Check if we should activate trailing stop
            profit_pct = (self.highest_price - self.entry_price) / self.entry_price
            
            if profit_pct >= self.parameters.trailing_stop_activation:
                # Calculate trailing stop price
                self.trailing_stop_price = self.highest_price * (1 - self.parameters.trailing_stop_distance)
                
                # Check if price hit trailing stop
                return price <= self.trailing_stop_price
        
        else:  # SHORT
            # Check if we should activate trailing stop
            profit_pct = (self.entry_price - self.lowest_price) / self.entry_price
            
            if profit_pct >= self.parameters.trailing_stop_activation:
                # Calculate trailing stop price
                self.trailing_stop_price = self.lowest_price * (1 + self.parameters.trailing_stop_distance)
                
                # Check if price hit trailing stop
                return price >= self.trailing_stop_price
        
        return False
    
    def _check_cloud_exit(self, price: float, indicators: Dict[str, float]) -> bool:
        """Check if price penetrates cloud adversely."""
        if self.position_type == 'LONG':
            # Exit long if price falls below cloud top
            return price < indicators.get('cloud_top', float('inf'))
        else:  # SHORT
            # Exit short if price rises above cloud bottom
            return price > indicators.get('cloud_bottom', 0)
    
    def _check_kijun_exit(self, price: float, indicators: Dict[str, float]) -> bool:
        """Check if price touches Kijun-sen."""
        kijun = indicators.get('kijun_sen', 0)
        if kijun == 0:
            return False
        
        if self.position_type == 'LONG':
            # Exit long if price falls to Kijun
            return price <= kijun
        else:  # SHORT
            # Exit short if price rises to Kijun
            return price >= kijun
    
    def _check_partial_exit(self, market_event: MarketEvent) -> Optional[SignalEvent]:
        """Check for partial profit taking."""
        if not self.entry_price:
            return None
        
        price = market_event.close
        
        if self.position_type == 'LONG':
            profit_pct = ((price - self.entry_price) / self.entry_price) * 100
        else:  # SHORT
            profit_pct = ((self.entry_price - price) / self.entry_price) * 100
        
        # Check each partial exit level
        if not self.partial_exits_done['level1'] and profit_pct >= self.parameters.partial_exit_1_pct:
            self.partial_exits_done['level1'] = True
            return self._create_partial_exit_signal(
                market_event, self.parameters.partial_exit_1_size, 'PARTIAL_EXIT_1'
            )
        
        if not self.partial_exits_done['level2'] and profit_pct >= self.parameters.partial_exit_2_pct:
            self.partial_exits_done['level2'] = True
            return self._create_partial_exit_signal(
                market_event, self.parameters.partial_exit_2_size, 'PARTIAL_EXIT_2'
            )
        
        if not self.partial_exits_done['level3'] and profit_pct >= self.parameters.partial_exit_3_pct:
            self.partial_exits_done['level3'] = True
            return self._create_partial_exit_signal(
                market_event, self.parameters.partial_exit_3_size, 'PARTIAL_EXIT_3'
            )
        
        return None
    
    def _create_partial_exit_signal(
        self,
        market_event: MarketEvent,
        exit_size: float,
        exit_reason: str
    ) -> SignalEvent:
        """Create a partial exit signal."""
        return self.create_signal(
            timestamp=market_event.timestamp,
            symbol=market_event.symbol,
            signal_type='SELL' if self.position_type == 'LONG' else 'BUY',
            strength=exit_size,  # Use strength to indicate partial size
            metadata={
                'exit_reason': exit_reason,
                'partial_exit': True,
                'exit_size': exit_size
            }
        )
    
    def _check_pyramid_conditions(self, market_event: MarketEvent) -> Optional[SignalEvent]:
        """Check if we should add to position (pyramiding)."""
        if not self.entry_price:
            return None
        
        price = market_event.close
        indicators = market_event.indicators
        
        # Calculate profit percentage
        if self.position_type == 'LONG':
            profit_pct = ((price - self.entry_price) / self.entry_price) * 100
            
            # Pyramid at specific profit levels
            pyramid_levels = [4, 6, 9]  # Add at 4%, 6%, 9% profit
            if self.pyramid_count < len(pyramid_levels) and profit_pct >= pyramid_levels[self.pyramid_count]:
                # Check if we still have favorable conditions
                if self._count_long_signals(price, indicators) >= self.parameters.min_signals_required - 1:
                    size_multiplier = (1 - self.parameters.pyramid_size_reduction) ** self.pyramid_count
                    return self.create_signal(
                        timestamp=market_event.timestamp,
                        symbol=market_event.symbol,
                        signal_type='BUY',
                        strength=self.parameters.position_size * size_multiplier,
                        metadata={
                            'entry_reason': 'PYRAMID_LONG',
                            'pyramid_level': self.pyramid_count + 1
                        }
                    )
        
        return None
    
    def _initialize_position_tracking(self, price: float, signal_type: str):
        """Initialize position tracking variables."""
        self.entry_price = price
        self.position_type = 'LONG' if signal_type == 'BUY' else 'SHORT'
        self.highest_price = price if self.position_type == 'LONG' else None
        self.lowest_price = price if self.position_type == 'SHORT' else None
        self.trailing_stop_price = None
        self.partial_exits_done = {'level1': False, 'level2': False, 'level3': False}
        self.pyramid_count = 0
    
    def _reset_position_tracking(self):
        """Reset position tracking variables."""
        self.entry_price = None
        self.position_type = None
        self.highest_price = None
        self.lowest_price = None
        self.trailing_stop_price = None
        self.partial_exits_done = {'level1': False, 'level2': False, 'level3': False}
        self.pyramid_count = 0
    
    def reset(self):
        """Reset strategy state."""
        super().reset()
        self.last_golden_cross_bar = -999
        self.last_dead_cross_bar = -999
        self.current_bar = 0
        self._reset_position_tracking()
        self.zlmacd_buffer = []
        self.zlmacd_signal_buffer = []
        self.atr_buffer = []