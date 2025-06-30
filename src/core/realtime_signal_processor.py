# src/core/realtime_signal_processor.py
import asyncio
import logging
from typing import Dict, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass
from collections import deque
import numpy as np

from ..strategies.signal import Signal, SignalType, SignalStrength

logger = logging.getLogger(__name__)

@dataclass
class QuickIndicators:
    """빠른 계산을 위한 지표"""
    symbol: str
    price: float
    rsi: Optional[float] = None
    price_change_1m: Optional[float] = None
    price_change_5m: Optional[float] = None
    volume_ratio: Optional[float] = None
    volatility: Optional[float] = None
    price_position: Optional[float] = None  # Donchian 가격 위치
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class RealtimeSignalProcessor:
    """실시간 신호 처리 및 빠른 지표 계산 - 개선된 버전"""
    
    def __init__(self, strategy, position_manager):
        self.strategy = strategy
        self.position_manager = position_manager
        
        # 가격 히스토리 (빠른 지표 계산용)
        self.price_history = {}  # symbol -> deque of (timestamp, price)
        self.volume_history = {}  # symbol -> deque of (timestamp, volume)
        
        # RSI 계산용 데이터
        self.rsi_gains = {}  # symbol -> deque of gains
        self.rsi_losses = {}  # symbol -> deque of losses
        
        # 개선된 쿨다운 관리
        self.position_entry_time = {}  # symbol -> entry_time (포지션 진입 시간)
        self.last_check_time = {}  # symbol -> last_check_time (마지막 체크 시간)
        self.cooldown_seconds = 30  # 포지션 진입 후 쿨다운
        self.check_interval_seconds = 5  # 일반 체크 간격
        
        # 효율적인 체크를 위한 지표 범위
        self.check_zones = {
            'rsi_long_zone': (30, 45),      # RSI 롱 체크 구간
            'rsi_short_zone': (55, 70),     # RSI 숏 체크 구간
            'price_position_long': 0.35,    # 가격 위치 롱 체크
            'price_position_short': 0.65,   # 가격 위치 숏 체크
            'zone_buffer': 0.05             # 구간 버퍼 (5%)
        }
        
        # 처리중인 심볼 (중복 처리 방지)
        self.processing_symbols: Set[str] = set()
        self._processing_lock = asyncio.Lock()
        
        # 통계
        self.stats = {
            'price_updates': 0,
            'zone_checks': 0,
            'full_checks': 0,
            'signals_found': 0
        }
        
        logger.info("실시간 신호 프로세서 초기화 (개선된 버전)")
    
    async def on_price_update(self, symbol: str, price: float):
        """실시간 가격 업데이트 처리 - 효율성 개선"""
        try:
            self.stats['price_updates'] += 1
            
            # 가격 히스토리 업데이트
            self._update_price_history(symbol, price)
            
            # 빠른 지표 계산
            indicators = self._calculate_quick_indicators(symbol, price)
            
            # 효율적인 구간 체크
            if self._is_in_check_zone(symbol, indicators):
                self.stats['zone_checks'] += 1
                
                # 쿨다운 체크 (개선됨)
                if self._should_check_signal(symbol):
                    # 전체 신호 체크 트리거
                    await self._trigger_full_check(symbol, indicators)
                    
        except Exception as e:
            logger.error(f"가격 업데이트 처리 실패 ({symbol}): {e}")
    
    def _is_in_check_zone(self, symbol: str, indicators: QuickIndicators) -> bool:
        """효율적인 체크 구간 판단"""
        # 이미 포지션이 있으면 스킵
        if self.position_manager.is_position_exist(symbol):
            return False
        
        # RSI 체크 구간
        if indicators.rsi:
            # 롱 구간
            if self.check_zones['rsi_long_zone'][0] <= indicators.rsi <= self.check_zones['rsi_long_zone'][1]:
                return True
            # 숏 구간
            if self.check_zones['rsi_short_zone'][0] <= indicators.rsi <= self.check_zones['rsi_short_zone'][1]:
                return True
        
        # 가격 위치 체크 (Donchian 모드)
        if hasattr(self.strategy, 'trend_mode') and self.strategy.trend_mode == 'donchian':
            if hasattr(indicators, 'price_position') and indicators.price_position:
                # 극단 위치
                if indicators.price_position <= self.check_zones['price_position_long']:
                    return True
                if indicators.price_position >= self.check_zones['price_position_short']:
                    return True
        
        # 급격한 가격 변화
        if indicators.price_change_1m and abs(indicators.price_change_1m) >= 0.01:  # 1% 급변
            return True
        
        return False
    
    def _should_check_signal(self, symbol: str) -> bool:
        """신호 체크 여부 판단 - 개선된 쿨다운 로직"""
        current_time = datetime.now()
        
        # 1. 포지션이 있는 경우 - 진입 후 쿨다운 적용
        if symbol in self.position_entry_time:
            time_since_entry = (current_time - self.position_entry_time[symbol]).total_seconds()
            if time_since_entry < self.cooldown_seconds:
                return False
            # 쿨다운 후 제거
            del self.position_entry_time[symbol]
        
        # 2. 포지션이 없는 경우 - 체크 간격만 적용
        if symbol in self.last_check_time:
            time_since_check = (current_time - self.last_check_time[symbol]).total_seconds()
            if time_since_check < self.check_interval_seconds:
                return False
        
        return True
    
    async def on_kline_closed(self, symbol: str, interval: str, kline: Dict):
        """캔들 완성시 처리"""
        try:
            # 15분봉 완성시 전체 체크
            if interval == '15m':
                # 포지션이 없고 쿨다운이 없으면 체크
                if not self.position_manager.is_position_exist(symbol):
                    if symbol not in self.position_entry_time:
                        await self._trigger_full_check(symbol, reason="15m_candle_closed")
                
            # 1분봉 완성시 RSI 업데이트
            elif interval == '1m':
                self._update_rsi_data(symbol, kline)
                
        except Exception as e:
            logger.error(f"캔들 처리 실패 ({symbol}): {e}")
    
    def _update_price_history(self, symbol: str, price: float):
        """가격 히스토리 업데이트"""
        if symbol not in self.price_history:
            self.price_history[symbol] = deque(maxlen=300)  # 5분 데이터
            
        self.price_history[symbol].append((datetime.now(), price))
    
    def _calculate_quick_indicators(self, symbol: str, current_price: float) -> QuickIndicators:
        """빠른 지표 계산 - 가격 위치 추가"""
        indicators = QuickIndicators(symbol=symbol, price=current_price)
        
        if symbol not in self.price_history or len(self.price_history[symbol]) < 2:
            return indicators
        
        prices = self.price_history[symbol]
        current_time = datetime.now()
        
        # 1분전 가격 변화
        one_min_ago = current_time - timedelta(minutes=1)
        for timestamp, price in reversed(prices):
            if timestamp <= one_min_ago:
                indicators.price_change_1m = (current_price - price) / price
                break
        
        # 5분전 가격 변화
        five_min_ago = current_time - timedelta(minutes=5)
        for timestamp, price in reversed(prices):
            if timestamp <= five_min_ago:
                indicators.price_change_5m = (current_price - price) / price
                break
        
        # 간단한 변동성 계산
        recent_prices = [p for _, p in list(prices)[-20:]]  # 최근 20개
        if len(recent_prices) > 1:
            indicators.volatility = np.std(recent_prices) / np.mean(recent_prices)
        
        # RSI (캐시된 값 사용)
        if symbol in self.rsi_gains and symbol in self.rsi_losses:
            indicators.rsi = self._calculate_rsi_from_cache(symbol)
        
        # 가격 위치 계산 (Donchian용)
        if len(recent_prices) >= 20:
            high_20 = max(recent_prices)
            low_20 = min(recent_prices)
            if high_20 > low_20:
                indicators.price_position = (current_price - low_20) / (high_20 - low_20)
        
        return indicators
    
    def _calculate_rsi_from_cache(self, symbol: str) -> Optional[float]:
        """캐시된 데이터로 RSI 계산"""
        if symbol not in self.rsi_gains or not self.rsi_gains[symbol]:
            return None
            
        avg_gain = np.mean(list(self.rsi_gains[symbol]))
        avg_loss = np.mean(list(self.rsi_losses[symbol]))
        
        if avg_loss == 0:
            return 100.0
            
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _update_rsi_data(self, symbol: str, kline: Dict):
        """RSI 계산용 데이터 업데이트"""
        if symbol not in self.rsi_gains:
            self.rsi_gains[symbol] = deque(maxlen=14)
            self.rsi_losses[symbol] = deque(maxlen=14)
            return
            
        # 가격 변화 계산
        change = kline['close'] - kline['open']
        
        if change > 0:
            self.rsi_gains[symbol].append(change)
            self.rsi_losses[symbol].append(0)
        else:
            self.rsi_gains[symbol].append(0)
            self.rsi_losses[symbol].append(abs(change))
    
    async def _trigger_full_check(self, symbol: str, indicators: Optional[QuickIndicators] = None, reason: str = ""):
        """전체 신호 체크 트리거 - 비동기 실행 개선"""
        async with self._processing_lock:
            # 중복 처리 방지
            if symbol in self.processing_symbols:
                return
                
            self.processing_symbols.add(symbol)
            self.last_check_time[symbol] = datetime.now()
        
        try:
            self.stats['full_checks'] += 1
            logger.info(f"📊 실시간 신호 체크: {symbol} (사유: {reason or 'zone_check'})")
            
            if indicators:
                rsi_str = f"{indicators.rsi:.1f}" if indicators.rsi is not None else "N/A"
                price_change_str = f"{indicators.price_change_1m:.2%}" if indicators.price_change_1m is not None else "N/A"
                logger.debug(f"  RSI: {rsi_str}, 가격변화: {price_change_str}")
            
            # 전략의 체크 메서드를 비동기로 실행
            if hasattr(self.strategy, '_check_new_entry'):
                # 비동기 태스크로 실행 (논블로킹)
                asyncio.create_task(self._execute_strategy_check(symbol))
            else:
                logger.warning(f"전략에 _check_new_entry 메서드가 없습니다")
                
        except Exception as e:
            logger.error(f"전체 신호 체크 실패 ({symbol}): {e}")
        finally:
            # 처리 완료 표시
            await asyncio.sleep(0.1)
            self.processing_symbols.discard(symbol)
    
    async def _execute_strategy_check(self, symbol: str):
        """전략 체크 실행 - 신호 발견시 즉시 진입"""
        try:
            # 전략의 진입 체크 실행
            await self.strategy._check_new_entry(symbol)
            
            # 포지션이 생성되었는지 확인
            if self.position_manager.is_position_exist(symbol):
                # 포지션 진입 시간 기록 (쿨다운용)
                self.position_entry_time[symbol] = datetime.now()
                self.stats['signals_found'] += 1
                logger.info(f"✅ {symbol} 포지션 진입 완료 - 쿨다운 시작")
                
        except Exception as e:
            logger.error(f"전략 체크 실행 실패 ({symbol}): {e}")
    
    def update_check_zones(self, zones: Dict):
        """체크 구간 업데이트"""
        self.check_zones.update(zones)
        logger.info(f"체크 구간 업데이트: {zones}")
    
    def get_stats(self) -> Dict:
        """통계 조회"""
        return {
            **self.stats,
            'processing_symbols': len(self.processing_symbols),
            'symbols_in_cooldown': len(self.position_entry_time),
            'price_history_symbols': len(self.price_history)
        }
    
    def get_quick_indicators(self, symbol: str) -> Optional[QuickIndicators]:
        """현재 빠른 지표 조회"""
        if symbol not in self.price_history or not self.price_history[symbol]:
            return None
            
        current_price = self.price_history[symbol][-1][1]
        return self._calculate_quick_indicators(symbol, current_price)