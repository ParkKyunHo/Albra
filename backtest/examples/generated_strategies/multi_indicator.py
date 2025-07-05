
"""
Generated strategy from natural language description.
"""

from typing import Optional, Dict, Any, List
from backtest.strategies.base import BaseStrategy, StrategyParameters
from backtest.core.events import MarketEvent, SignalEvent


class ICHIMOKUCrossOver(BaseStrategy):
    """
    
    이치모쿠 구름 위에서 MACD 골든크로스가 발생하면 매수합니다.
    추가로 RSI가 50 이상이고 ADX가 25 이상일 때만 진입합니다.
    가격이 구름 아래로 떨어지거나 MACD 데드크로스 발생 시 청산합니다.
    손절은 2%, 익절은 10%로 설정하고, 3% 수익 시 트레일링 스톱을 활성화합니다.
    일일 손실 한도는 3%이며, 리스크 기반으로 포지션을 계산합니다.
    
    
    Generated from natural language description.
    """
    
    def __init__(self):
        """Initialize strategy."""
        super().__init__(StrategyParameters(
            position_size=0.1,
            stop_loss=0.02,
            take_profit=0.05,
            use_trailing_stop=True
        ))
        
        # Strategy-specific parameters
        pass
    
    @property
    def name(self) -> str:
        """Strategy name."""
        return "ICHIMOKU_CrossOver"
    
    @property
    def required_indicators(self) -> List[str]:
        """Required indicators for this strategy."""
        return ['ichimoku', 'sma', 'ema']
    
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
