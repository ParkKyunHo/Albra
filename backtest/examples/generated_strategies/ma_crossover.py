
"""
Generated strategy from natural language description.
"""

from typing import Optional, Dict, Any, List
from backtest.strategies.base import BaseStrategy, StrategyParameters
from backtest.core.events import MarketEvent, SignalEvent


class CrossOver(BaseStrategy):
    """
    
    20일 이동평균선과 50일 이동평균선의 골든크로스에서 매수하고,
    데드크로스에서 매도합니다. 손절은 2%, 익절은 5%로 설정하고,
    포지션 크기는 계좌의 10%로 고정합니다.
    
    
    Generated from natural language description.
    """
    
    def __init__(self):
        """Initialize strategy."""
        super().__init__(StrategyParameters(
            position_size=0.1,
            stop_loss=0.02,
            take_profit=0.05,
            use_trailing_stop=False
        ))
        
        # Strategy-specific parameters
        pass
    
    @property
    def name(self) -> str:
        """Strategy name."""
        return "CrossOver"
    
    @property
    def required_indicators(self) -> List[str]:
        """Required indicators for this strategy."""
        return ['sma', 'ema']
    
    def generate_signal(self, market_event: MarketEvent) -> Optional[SignalEvent]:
        """Generate trading signal."""
        # Calculate indicators
        indicators = {}
        
        # Check entry conditions
        # Long entry conditions
        if (fast_ma > slow_ma and prev_fast_ma <= prev_slow_ma):
            return self.create_signal(
                timestamp=market_event.timestamp,
                symbol=market_event.symbol,
                signal_type='BUY',
                strength=1.0
            )
        
        # Check exit conditions
        # Exit conditions are handled by position manager
        # (stop loss, take profit, trailing stop)
        
        return None
