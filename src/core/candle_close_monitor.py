# src/core/candle_close_monitor.py
"""
캔들 종가 모니터 - 캔들 완성 즉시 이벤트 발생
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional, Callable
from collections import defaultdict

logger = logging.getLogger(__name__)

class CandleCloseMonitor:
    """15분 캔들 완성을 정확히 감지하는 모니터"""
    
    def __init__(self):
        self.is_running = False
        self.monitored_symbols: Set[str] = set()
        self.callbacks: Dict[str, List[Callable]] = defaultdict(list)
        self.last_candle_time: Dict[str, datetime] = {}
        
    def add_symbol(self, symbol: str):
        """모니터링할 심볼 추가"""
        self.monitored_symbols.add(symbol)
        logger.info(f"캔들 모니터에 {symbol} 추가됨")
    
    def remove_symbol(self, symbol: str):
        """모니터링 심볼 제거"""
        self.monitored_symbols.discard(symbol)
        if symbol in self.last_candle_time:
            del self.last_candle_time[symbol]
    
    def on_candle_close(self, callback: Callable):
        """캔들 완성 콜백 등록"""
        self.callbacks['candle_close'].append(callback)
    
    async def start(self):
        """모니터 시작"""
        self.is_running = True
        logger.info("캔들 종가 모니터 시작")
        
        while self.is_running:
            try:
                current_time = datetime.now()
                current_second = current_time.second
                current_minute = current_time.minute
                
                # 15분 캔들이 막 완성된 시점인지 체크 (00, 15, 30, 45분의 0~5초)
                if current_minute % 15 == 0 and current_second < 5:
                    candle_time = current_time.replace(second=0, microsecond=0)
                    
                    # 각 심볼에 대해 체크
                    for symbol in self.monitored_symbols.copy():
                        # 이미 이 캔들을 처리했는지 확인
                        if symbol not in self.last_candle_time or self.last_candle_time[symbol] < candle_time:
                            self.last_candle_time[symbol] = candle_time
                            
                            # 콜백 실행
                            await self._trigger_callbacks(symbol, candle_time)
                    
                    # 다음 체크까지 대기 (중복 방지)
                    await asyncio.sleep(10)
                else:
                    # 다음 15분 캔들까지 대기 시간 계산
                    next_candle_minute = ((current_minute // 15) + 1) * 15
                    if next_candle_minute >= 60:
                        next_candle_time = current_time.replace(hour=current_time.hour + 1, minute=0, second=0, microsecond=0)
                    else:
                        next_candle_time = current_time.replace(minute=next_candle_minute, second=0, microsecond=0)
                    
                    wait_seconds = (next_candle_time - current_time).total_seconds()
                    
                    # 최대 60초까지만 대기 (긴 대기 시간 방지)
                    wait_seconds = min(wait_seconds, 60)
                    
                    logger.debug(f"다음 캔들까지 {int(wait_seconds)}초 대기")
                    await asyncio.sleep(wait_seconds)
                    
            except Exception as e:
                logger.error(f"캔들 모니터 에러: {e}")
                await asyncio.sleep(1)
    
    async def _trigger_callbacks(self, symbol: str, candle_time: datetime):
        """캔들 완성 콜백 실행"""
        logger.info(f"📊 {symbol} 15분 캔들 완성: {candle_time.strftime('%H:%M')}")
        
        for callback in self.callbacks['candle_close']:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(symbol, candle_time)
                else:
                    callback(symbol, candle_time)
            except Exception as e:
                logger.error(f"캔들 완성 콜백 에러: {e}")
    
    async def stop(self):
        """모니터 중지"""
        self.is_running = False
        logger.info("캔들 종가 모니터 중지됨")
    
    def get_next_candle_time(self, timeframe_minutes: int = 15) -> datetime:
        """다음 캔들 시간 계산"""
        current_time = datetime.now()
        current_minute = current_time.minute
        
        # 다음 timeframe 분 계산
        next_candle_minute = ((current_minute // timeframe_minutes) + 1) * timeframe_minutes
        
        if next_candle_minute >= 60:
            # 다음 시간으로 넘어가는 경우
            next_candle_time = current_time.replace(
                hour=(current_time.hour + 1) % 24,
                minute=0,
                second=0,
                microsecond=0
            )
            # 날짜가 바뀔 수 있음
            if current_time.hour == 23:
                next_candle_time = next_candle_time + timedelta(days=1)
        else:
            next_candle_time = current_time.replace(
                minute=next_candle_minute,
                second=0,
                microsecond=0
            )
        
        return next_candle_time
    
    def is_candle_complete(self, candle_time: datetime, timeframe_minutes: int = 15) -> bool:
        """특정 시간의 캔들이 완성되었는지 확인"""
        current_time = datetime.now()
        
        # 캔들 시간을 timeframe에 맞춰 정규화
        candle_minute = (candle_time.minute // timeframe_minutes) * timeframe_minutes
        normalized_candle_time = candle_time.replace(
            minute=candle_minute,
            second=0,
            microsecond=0
        )
        
        # 현재 시간이 캔들 종료 시간보다 크면 완성
        candle_end_time = normalized_candle_time + timedelta(minutes=timeframe_minutes)
        return current_time >= candle_end_time
