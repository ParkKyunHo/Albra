# src/strategies/zlhma_ema_cross_strategy_fixed.py
"""
ZLHMA 50-200 EMA Golden/Death Cross Strategy
AlbraTrading 시스템 호환 버전 - BaseStrategy 인터페이스 준수
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import logging
import asyncio

from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class ZLHMAEMACrossStrategy(BaseStrategy):
    """ZLHMA 50-200 EMA Cross Strategy - 실전 버전"""
    
    def __init__(self, binance_api, position_manager, config: Dict, config_manager=None):
        """전략 초기화"""
        super().__init__(binance_api, position_manager, config)
        
        self.name = "ZLHMA_EMA_CROSS"
        self.strategy_name = "ZLHMA_EMA_CROSS"
        
        # ZLHMA 파라미터
        self.zlhma_period = config.get('zlhma_period', 14)
        
        # EMA 파라미터
        self.fast_ema_period = config.get('fast_ema_period', 50)
        self.slow_ema_period = config.get('slow_ema_period', 200)
        
        # ADX 필터
        self.adx_period = config.get('adx_period', 14)
        self.adx_threshold = config.get('adx_threshold', 25)
        
        # 리스크 관리
        self.stop_loss_atr = config.get('stop_loss_atr', 1.5)
        self.take_profit_atr = config.get('take_profit_atr', 5.0)
        self.trailing_stop_activation = config.get('trailing_stop_activation', 0.03)  # 3%
        self.trailing_stop_distance = config.get('trailing_stop_distance', 0.10)  # 10%
        
        # 신호 강도 임계값
        self.signal_strength_threshold = config.get('signal_strength_threshold', 2.5)
        
        # 거래할 심볼 목록
        self.symbols = config.get('symbols', ['BTCUSDT'])
        
        # 최소 신호 간격
        self.min_signal_interval = config.get('min_signal_interval', 4)  # 4시간
        
        # 데이터 캐시
        self.klines_cache = {}
        self.indicators_cache = {}
        self._last_check_time = {}
        self._last_candle_time = {}
        
        logger.info(f"ZLHMA EMA Cross 전략 초기화 완료")
        logger.info(f"  - ZLHMA Period: {self.zlhma_period}")
        logger.info(f"  - EMA Periods: {self.fast_ema_period}/{self.slow_ema_period}")
        logger.info(f"  - ADX Threshold: {self.adx_threshold}")
        logger.info(f"  - 거래 심볼: {', '.join(self.symbols)}")
    
    def calculate_wma(self, values: pd.Series, period: int) -> pd.Series:
        """Weighted Moving Average 계산"""
        weights = np.arange(1, period + 1)
        wma = values.rolling(period).apply(
            lambda x: np.dot(x, weights) / weights.sum(), raw=True
        )
        return wma
    
    def calculate_hma(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Hull Moving Average 계산"""
        half_length = int(period / 2)
        sqrt_length = int(np.sqrt(period))
        
        wma_half = self.calculate_wma(df['close'], half_length)
        wma_full = self.calculate_wma(df['close'], period)
        raw_hma = 2 * wma_half - wma_full
        hma = self.calculate_wma(raw_hma, sqrt_length)
        
        return hma
    
    def calculate_zlhma(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Zero Lag Hull Moving Average 계산"""
        hma = self.calculate_hma(df, period)
        lag = int((period - 1) / 2)
        zlhma = hma + (hma - hma.shift(lag))
        return zlhma
    
    def calculate_adx(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """ADX 계산"""
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift(1))
        low_close = abs(df['low'] - df['close'].shift(1))
        
        df['tr'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        df['dm_plus'] = np.where(
            (df['high'] - df['high'].shift(1)) > (df['low'].shift(1) - df['low']),
            np.maximum(df['high'] - df['high'].shift(1), 0), 0
        )
        df['dm_minus'] = np.where(
            (df['low'].shift(1) - df['low']) > (df['high'] - df['high'].shift(1)),
            np.maximum(df['low'].shift(1) - df['low'], 0), 0
        )
        
        atr = df['tr'].rolling(period).mean()
        di_plus = 100 * (df['dm_plus'].rolling(period).mean() / atr)
        di_minus = 100 * (df['dm_minus'].rolling(period).mean() / atr)
        
        dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus)
        df['adx'] = dx.rolling(period).mean()
        
        return df
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """지표 계산"""
        try:
            # ZLHMA
            df['zlhma'] = self.calculate_zlhma(df, self.zlhma_period)
            
            # EMA
            df['ema_fast'] = df['close'].ewm(span=self.fast_ema_period, adjust=False).mean()
            df['ema_slow'] = df['close'].ewm(span=self.slow_ema_period, adjust=False).mean()
            
            # ADX
            df = self.calculate_adx(df, self.adx_period)
            
            # ATR (손절/익절용)
            high_low = df['high'] - df['low']
            high_close = abs(df['high'] - df['close'].shift(1))
            low_close = abs(df['low'] - df['close'].shift(1))
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            df['atr'] = tr.rolling(14).mean()
            
            # RSI (추가 - BaseStrategy와 호환성)
            df['rsi'] = self._calculate_rsi(df['close'], 14)
            
            # Momentum
            df['momentum'] = ((df['close'] - df['close'].shift(20)) / 
                              df['close'].shift(20) * 100).abs()
            
            # Volume
            df['volume_ma'] = df['volume'].rolling(window=20).mean()
            df['volume_ratio'] = df['volume'] / df['volume_ma']
            
            return df
            
        except Exception as e:
            logger.error(f"지표 계산 실패: {e}")
            return df
    
    def _calculate_rsi(self, prices: pd.Series, period: int) -> pd.Series:
        """RSI 계산"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    async def run_cycle(self):
        """전략 실행 사이클 - TFPE와 동일한 구조"""
        try:
            # 캔들 종가 체크
            is_check_time, candle_time = await self._is_candle_close_time()
            if not is_check_time or not candle_time:
                return
            
            # 각 심볼에 대해 체크
            for symbol in self.symbols:
                # 이미 체크했는지 확인
                if symbol in self._last_candle_time and self._last_candle_time[symbol] >= candle_time:
                    continue
                
                self._last_candle_time[symbol] = candle_time
                
                # 포지션 확인
                position = self.position_manager.get_position(symbol)
                
                if position and position.status == 'ACTIVE':
                    # 포지션 관리
                    if not position.is_manual and position.strategy_name == self.strategy_name:
                        await self._manage_position(position)
                else:
                    # 진입 체크
                    if await self.can_enter_position(symbol):
                        await self._check_new_entry(symbol)
            
        except Exception as e:
            logger.error(f"ZLHMA 사이클 실행 실패: {e}")
    
    async def _is_candle_close_time(self) -> Tuple[bool, Optional[datetime]]:
        """캔들 종가 체크 시간인지 확인"""
        current_time = datetime.now()
        current_minute = current_time.minute
        current_second = current_time.second
        
        # 15분 캔들 체크 (0, 15, 30, 45분)
        if current_minute % 15 == 0 and current_second < 30:
            candle_time = current_time.replace(minute=(current_minute // 15) * 15, second=0, microsecond=0)
            return True, candle_time
        
        return False, None
    
    async def fetch_and_prepare_data(self, symbol: str) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
        """데이터 수집 및 준비"""
        try:
            # 4시간봉 데이터 (추세 확인용)
            df_4h = await self.binance_api.get_klines(symbol, '4h', limit=200)
            
            # 15분봉 데이터 (진입 신호용)
            df_15m = await self.binance_api.get_klines(symbol, '15m', limit=500)
            
            if df_4h.empty or df_15m.empty:
                logger.error(f"데이터 수집 실패: {symbol}")
                return None, None
            
            # 지표 계산
            df_4h = self.calculate_indicators(df_4h)
            df_15m = self.calculate_indicators(df_15m)
            
            return df_4h, df_15m
            
        except Exception as e:
            logger.error(f"데이터 준비 실패 ({symbol}): {e}")
            return None, None
    
    async def check_entry_signal(self, symbol: str, df_4h: pd.DataFrame, 
                                df_15m: pd.DataFrame, current_index: int) -> Tuple[bool, Optional[str]]:
        """진입 신호 체크 - BaseStrategy 인터페이스"""
        try:
            if current_index < self.slow_ema_period:
                return False, None
            
            # 최근 3개 캔들 데이터
            current = df_15m.iloc[current_index]
            prev1 = df_15m.iloc[current_index - 1]
            prev2 = df_15m.iloc[current_index - 2]
            
            # ADX 필터
            if pd.isna(current['adx']) or current['adx'] < self.adx_threshold:
                return False, None
            
            signal_strength = 0
            signal_type = None
            signals = []
            
            # LONG 신호 확인
            # 1. EMA 골든크로스
            if (current['ema_fast'] > current['ema_slow'] and 
                prev1['ema_fast'] <= prev1['ema_slow']):
                signals.append('EMA_GOLDEN_CROSS')
                signal_strength += 2.0
                signal_type = 'long'
            
            # 2. ZLHMA 상승 모멘텀 (LONG)
            if (signal_type == 'long' and 'zlhma' in current and 
                current['zlhma'] > prev1['zlhma'] > prev2['zlhma']):
                signals.append('ZLHMA_UPWARD_MOMENTUM')
                signal_strength += 1.0
            
            # 3. 가격이 ZLHMA 위 (LONG)
            if signal_type == 'long' and current['close'] > current['zlhma']:
                signals.append('PRICE_ABOVE_ZLHMA')
                signal_strength += 0.5
            
            # SHORT 신호 확인
            # 1. EMA 데드크로스
            if (current['ema_fast'] < current['ema_slow'] and 
                prev1['ema_fast'] >= prev1['ema_slow']):
                signals.append('EMA_DEATH_CROSS')
                signal_strength += 2.0
                signal_type = 'short'
            
            # 2. ZLHMA 하락 모멘텀 (SHORT)
            if (signal_type == 'short' and 'zlhma' in current and
                current['zlhma'] < prev1['zlhma'] < prev2['zlhma']):
                signals.append('ZLHMA_DOWNWARD_MOMENTUM')
                signal_strength += 1.0
            
            # 3. 가격이 ZLHMA 아래 (SHORT)
            if signal_type == 'short' and current['close'] < current['zlhma']:
                signals.append('PRICE_BELOW_ZLHMA')
                signal_strength += 0.5
            
            # 신호 강도 확인
            if signal_strength >= self.signal_strength_threshold and signal_type:
                logger.info(f"📊 ZLHMA 신호 감지: {symbol} {signal_type}")
                logger.info(f"   충족 조건 ({signal_strength:.1f}/{self.signal_strength_threshold}): {', '.join(signals)}")
                logger.info(f"   ADX: {current['adx']:.1f}, ATR: {current['atr']:.2f}")
                
                return True, signal_type
            
            return False, None
            
        except Exception as e:
            logger.error(f"진입 신호 체크 실패: {e}")
            return False, None
    
    async def check_exit_signal(self, position, df_15m: pd.DataFrame, 
                               current_index: int) -> Tuple[bool, str]:
        """청산 신호 체크 - BaseStrategy 인터페이스"""
        try:
            if current_index < 2:
                return False, ""
            
            current = df_15m.iloc[current_index]
            symbol = position.symbol
            
            # ATR 기반 손절/익절
            current_price = current['close']
            current_atr = current['atr'] if not pd.isna(current['atr']) else current_price * 0.02
            
            if position.side.upper() == 'LONG':
                stop_loss = position.entry_price - (current_atr * self.stop_loss_atr)
                take_profit = position.entry_price + (current_atr * self.take_profit_atr)
                
                if current_price <= stop_loss:
                    return True, f"손절 (SL: {stop_loss:.2f})"
                elif current_price >= take_profit:
                    return True, f"익절 (TP: {take_profit:.2f})"
                
                # EMA 데드크로스
                if current['ema_fast'] < current['ema_slow']:
                    return True, "EMA 데드크로스"
                
                # ZLHMA 아래로 돌파
                if current['close'] < current['zlhma']:
                    return True, "ZLHMA 하향 돌파"
                
            else:  # SHORT
                stop_loss = position.entry_price + (current_atr * self.stop_loss_atr)
                take_profit = position.entry_price - (current_atr * self.take_profit_atr)
                
                if current_price >= stop_loss:
                    return True, f"손절 (SL: {stop_loss:.2f})"
                elif current_price <= take_profit:
                    return True, f"익절 (TP: {take_profit:.2f})"
                
                # EMA 골든크로스
                if current['ema_fast'] > current['ema_slow']:
                    return True, "EMA 골든크로스"
                
                # ZLHMA 위로 돌파
                if current['close'] > current['zlhma']:
                    return True, "ZLHMA 상향 돌파"
            
            return False, ""
            
        except Exception as e:
            logger.error(f"청산 신호 체크 실패: {e}")
            return False, ""
    
    async def _check_new_entry(self, symbol: str):
        """신규 진입 체크"""
        try:
            # 데이터 준비
            df_4h, df_15m = await self.fetch_and_prepare_data(symbol)
            
            if df_4h is None or df_15m is None:
                return
            
            # 마지막 완성된 캔들 사용
            current_index = len(df_15m) - 2
            
            if current_index < self.slow_ema_period:
                return
            
            # 진입 신호 체크
            signal, direction = await self.check_entry_signal(
                symbol, df_4h, df_15m, current_index
            )
            
            if not signal:
                return
            
            # 손절/익절 계산
            current_price = df_15m.iloc[current_index]['close']
            current_atr = df_15m.iloc[current_index]['atr']
            
            if direction == 'long':
                stop_loss = current_price - (current_atr * self.stop_loss_atr)
                take_profit = current_price + (current_atr * self.take_profit_atr)
            else:
                stop_loss = current_price + (current_atr * self.stop_loss_atr)
                take_profit = current_price - (current_atr * self.take_profit_atr)
            
            # 진입 실행
            success = await self.execute_entry(symbol, direction, stop_loss, take_profit)
            
            if success:
                logger.info(f"✅ {symbol} ZLHMA 진입 완료")
                
        except Exception as e:
            logger.error(f"신규 진입 체크 실패 ({symbol}): {e}")
    
    async def _manage_position(self, position):
        """포지션 관리"""
        try:
            symbol = position.symbol
            
            # 데이터 준비
            df_4h, df_15m = await self.fetch_and_prepare_data(symbol)
            
            if df_4h is None or df_15m is None:
                return
            
            # 마지막 완성된 캔들 사용
            current_index = len(df_15m) - 2
            
            # 청산 신호 체크
            should_exit, reason = await self.check_exit_signal(
                position, df_15m, current_index
            )
            
            if should_exit:
                logger.info(f"🚨 청산 신호 감지: {symbol} - {reason}")
                
                # 청산 실행
                success = await self.execute_exit(position, reason)
                
                if success:
                    logger.info(f"✅ {symbol} 청산 완료: {reason}")
                
        except Exception as e:
            logger.error(f"포지션 관리 실패 ({position.symbol}): {e}")
    
    def get_strategy_info(self) -> Dict:
        """전략 정보 반환"""
        return {
            'name': self.name,
            'description': 'ZLHMA 50-200 EMA Golden/Death Cross Strategy',
            'parameters': {
                'zlhma_period': self.zlhma_period,
                'fast_ema': self.fast_ema_period,
                'slow_ema': self.slow_ema_period,
                'adx_threshold': self.adx_threshold,
                'signal_strength_threshold': self.signal_strength_threshold
            },
            'risk_management': {
                'stop_loss_atr': self.stop_loss_atr,
                'take_profit_atr': self.take_profit_atr,
                'leverage': self.leverage,
                'position_size': self.position_size
            }
        }
