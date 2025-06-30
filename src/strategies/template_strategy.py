"""
전략 템플릿 - Multi-Strategy Position Management 지원
이 템플릿을 복사하여 새로운 전략을 구현하세요.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import asyncio
from datetime import datetime

from src.strategies.base_strategy import BaseStrategy
from src.strategies.signal import TradingSignal


class TemplateStrategy(BaseStrategy):
    """
    전략 템플릿 클래스
    
    이 템플릿은 Multi-Strategy Position Management를 올바르게 구현하는
    예제를 제공합니다. 새로운 전략 개발 시 이 템플릿을 복사하여 사용하세요.
    """
    
    def __init__(self, binance_api, position_manager, config):
        """전략 초기화"""
        super().__init__(binance_api, position_manager, config)
        
        # 전략명 설정 (필수! 고유해야 함)
        self.strategy_name = "TEMPLATE_STRATEGY"
        
        # 전략 설정 로드
        strategy_config = config.get('strategies', {}).get('template_strategy', {})
        
        # 기본 파라미터
        self.leverage = strategy_config.get('leverage', 10)
        self.position_size = strategy_config.get('position_size', 20)
        
        # 전략별 파라미터 (예시)
        self.fast_period = strategy_config.get('fast_period', 10)
        self.slow_period = strategy_config.get('slow_period', 20)
        self.signal_threshold = strategy_config.get('signal_threshold', 0.7)
        
        # 초기화 로그
        self.logger.info(f"[{self.strategy_name}] 전략 초기화 완료")
        self.logger.info(f"[{self.strategy_name}] 레버리지: {self.leverage}x, 포지션 크기: {self.position_size}%")
    
    async def check_entry_signal(self, symbol: str) -> Optional[TradingSignal]:
        """
        진입 신호 체크
        
        Args:
            symbol: 거래 심볼
            
        Returns:
            TradingSignal 또는 None
        """
        try:
            # 1. 이미 포지션이 있는지 확인 (중요: strategy_name 전달)
            existing_position = self.position_manager.get_position(symbol, self.strategy_name)
            if existing_position:
                self.logger.debug(f"[{self.strategy_name}] {symbol} 이미 포지션 존재")
                return None
            
            # 2. 지표 계산
            indicators = await self._calculate_indicators(symbol)
            if not indicators:
                return None
            
            # 3. 진입 조건 체크
            signal = self._check_entry_conditions(indicators)
            if signal:
                self.logger.info(f"[{self.strategy_name}] {symbol} 진입 신호 감지: {signal.side}")
            
            return signal
            
        except Exception as e:
            self.logger.error(f"[{self.strategy_name}] 진입 신호 체크 오류: {e}")
            return None
    
    async def check_exit_signal(self, symbol: str, position) -> bool:
        """
        청산 신호 체크
        
        Args:
            symbol: 거래 심볼
            position: 현재 포지션
            
        Returns:
            청산 여부 (True/False)
        """
        try:
            # 포지션이 이 전략의 것인지 확인
            if position.strategy_name != self.strategy_name:
                return False
            
            # 지표 계산
            indicators = await self._calculate_indicators(symbol)
            if not indicators:
                return False
            
            # 청산 조건 체크
            should_exit = self._check_exit_conditions(indicators, position)
            
            if should_exit:
                self.logger.info(f"[{self.strategy_name}] {symbol} 청산 신호 감지")
            
            return should_exit
            
        except Exception as e:
            self.logger.error(f"[{self.strategy_name}] 청산 신호 체크 오류: {e}")
            return False
    
    async def execute_trade(self, signal: TradingSignal) -> bool:
        """
        거래 실행
        
        Args:
            signal: 거래 신호
            
        Returns:
            실행 성공 여부
        """
        try:
            symbol = signal.symbol
            
            # 포지션 중복 체크 (중요: strategy_name 전달)
            if self.position_manager.is_position_exist(symbol, self.strategy_name):
                self.logger.warning(f"[{self.strategy_name}] {symbol} 포지션이 이미 존재")
                return False
            
            # 포지션 크기 계산
            position_size = self._calculate_position_size(signal)
            
            # 손절/익절 계산
            stop_loss = self._calculate_stop_loss(signal)
            take_profit = self._calculate_take_profit(signal)
            
            # 주문 실행
            self.logger.info(f"[{self.strategy_name}] {symbol} {signal.side} 주문 실행")
            order_result = await self._place_order(
                symbol=symbol,
                side=signal.side,
                size=position_size,
                leverage=self.leverage
            )
            
            if order_result and order_result.get('status') == 'FILLED':
                # 포지션 등록 (중요: strategy_name 전달)
                await self.position_manager.add_position(
                    symbol=symbol,
                    side=signal.side,
                    entry_price=float(order_result['avgPrice']),
                    size=position_size,
                    leverage=self.leverage,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    strategy_name=self.strategy_name  # 필수!
                )
                
                self.logger.info(f"[{self.strategy_name}] {symbol} 포지션 진입 완료")
                return True
                
        except Exception as e:
            self.logger.error(f"[{self.strategy_name}] 거래 실행 오류: {e}")
        
        return False
    
    async def close_position(self, symbol: str, reason: str = "전략 신호") -> bool:
        """
        포지션 청산
        
        Args:
            symbol: 거래 심볼
            reason: 청산 사유
            
        Returns:
            청산 성공 여부
        """
        try:
            # 포지션 조회 (중요: strategy_name 전달)
            position = self.position_manager.get_position(symbol, self.strategy_name)
            if not position:
                self.logger.warning(f"[{self.strategy_name}] {symbol} 포지션 없음")
                return False
            
            # 청산 주문 실행
            close_result = await self._place_close_order(position)
            
            if close_result and close_result.get('status') == 'FILLED':
                exit_price = float(close_result['avgPrice'])
                
                # 포지션 제거 (중요: strategy_name 전달)
                self.position_manager.remove_position(
                    symbol=symbol,
                    reason=reason,
                    exit_price=exit_price,
                    strategy_name=self.strategy_name  # 필수!
                )
                
                self.logger.info(f"[{self.strategy_name}] {symbol} 포지션 청산 완료: {reason}")
                return True
                
        except Exception as e:
            self.logger.error(f"[{self.strategy_name}] 포지션 청산 오류: {e}")
        
        return False
    
    async def _calculate_indicators(self, symbol: str) -> Optional[Dict]:
        """
        지표 계산
        
        이 메서드에서 전략에 필요한 모든 지표를 계산합니다.
        """
        try:
            # 캔들 데이터 조회
            klines = await self.binance_api.get_klines(
                symbol=symbol,
                interval=self.timeframe,
                limit=100
            )
            
            if not klines or len(klines) < self.slow_period:
                return None
            
            # 가격 데이터 추출
            closes = [float(k[4]) for k in klines]
            
            # 지표 계산 (예시)
            indicators = {
                'current_price': closes[-1],
                'fast_ma': sum(closes[-self.fast_period:]) / self.fast_period,
                'slow_ma': sum(closes[-self.slow_period:]) / self.slow_period,
                # 추가 지표...
            }
            
            return indicators
            
        except Exception as e:
            self.logger.error(f"[{self.strategy_name}] 지표 계산 오류: {e}")
            return None
    
    def _check_entry_conditions(self, indicators: Dict) -> Optional[TradingSignal]:
        """
        진입 조건 체크
        
        전략별 진입 로직을 구현합니다.
        """
        # 예시: 골든크로스/데드크로스
        fast_ma = indicators['fast_ma']
        slow_ma = indicators['slow_ma']
        current_price = indicators['current_price']
        
        # 롱 신호
        if fast_ma > slow_ma and current_price > fast_ma:
            return TradingSignal(
                symbol=indicators.get('symbol', 'UNKNOWN'),
                side='LONG',
                strength=0.8,
                strategy=self.strategy_name,
                indicators=indicators
            )
        
        # 숏 신호
        elif fast_ma < slow_ma and current_price < fast_ma:
            return TradingSignal(
                symbol=indicators.get('symbol', 'UNKNOWN'),
                side='SHORT',
                strength=0.8,
                strategy=self.strategy_name,
                indicators=indicators
            )
        
        return None
    
    def _check_exit_conditions(self, indicators: Dict, position) -> bool:
        """
        청산 조건 체크
        
        전략별 청산 로직을 구현합니다.
        """
        # 예시: 반대 신호 발생 시 청산
        fast_ma = indicators['fast_ma']
        slow_ma = indicators['slow_ma']
        
        if position.side == 'LONG' and fast_ma < slow_ma:
            return True
        elif position.side == 'SHORT' and fast_ma > slow_ma:
            return True
        
        return False
    
    def _calculate_position_size(self, signal: TradingSignal) -> float:
        """포지션 크기 계산"""
        # 기본 크기 사용 (추가 로직 구현 가능)
        return self.position_size
    
    def _calculate_stop_loss(self, signal: TradingSignal) -> float:
        """손절가 계산"""
        # 예시: 2% 손절
        if signal.side == 'LONG':
            return signal.indicators['current_price'] * 0.98
        else:
            return signal.indicators['current_price'] * 1.02
    
    def _calculate_take_profit(self, signal: TradingSignal) -> float:
        """익절가 계산"""
        # 예시: 4% 익절
        if signal.side == 'LONG':
            return signal.indicators['current_price'] * 1.04
        else:
            return signal.indicators['current_price'] * 0.96
    
    def get_status(self) -> Dict:
        """전략 상태 반환"""
        return {
            'name': self.strategy_name,
            'enabled': True,
            'leverage': self.leverage,
            'position_size': self.position_size,
            'parameters': {
                'fast_period': self.fast_period,
                'slow_period': self.slow_period,
                'signal_threshold': self.signal_threshold
            }
        }


# 사용 예제
if __name__ == "__main__":
    # 이 부분은 테스트용입니다
    print("전략 템플릿 - Multi-Strategy Position Management 지원")
    print("이 파일을 복사하여 새로운 전략을 구현하세요.")
    print("\n주요 체크포인트:")
    print("1. strategy_name을 고유하게 설정했는가?")
    print("2. 모든 position_manager 메서드에 strategy_name을 전달했는가?")
    print("3. config.yaml에 전략 설정을 추가했는가?")
    print("4. strategy_factory.py에 전략을 등록했는가?")
