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
        self.min_signal_interval = config.get('min_signal_interval', 1)  # 1시간
        
        # 데이터 캐시
        self.klines_cache = {}
        self.indicators_cache = {}
        self._last_check_time = {}
        self._last_candle_time = {}
        
        # Kelly Criterion 파라미터
        self.kelly_min = config.get('kelly_min', 0.05)  # 최소 포지션 크기 5%
        self.kelly_max = config.get('kelly_max', 0.20)  # 최대 포지션 크기 20%
        self.kelly_window = config.get('kelly_window', 30)  # 켈리 계산용 거래 기록 수
        self.recent_trades = []  # 최근 거래 기록 (켈리 계산용)
        
        # Pyramiding 파라미터
        self.pyramiding_enabled = config.get('pyramiding_enabled', True)
        self.max_pyramiding_levels = config.get('max_pyramiding_levels', 3)
        self.pyramiding_levels = config.get('pyramiding_levels', [0.03, 0.06, 0.09])  # 3%, 6%, 9% 수익에서 추가 진입
        self.pyramiding_positions = {}  # 심볼별 피라미딩 포지션 관리
        
        # Partial Exit 파라미터
        self.partial_exit_enabled = config.get('partial_exit_enabled', True)
        self.partial_exits = config.get('partial_exits', [
            (0.05, 0.25),   # 5% 수익에서 25% 청산
            (0.10, 0.35),   # 10% 수익에서 추가 35% 청산 (누적 60%)
            (0.15, 0.40),   # 15% 수익에서 나머지 40% 청산 (총 100%)
        ])
        self.accumulated_reduction = {}  # 심볼별 누적 청산 비율
        
        # 일일 손실 한도
        self.daily_loss_limit = config.get('daily_loss_limit', 0.03)  # 3%
        self.daily_loss = {}
        self.last_trade_date = {}
        self.trading_suspended_until = {}  # 심볼별 거래 중단 시간
        
        # 레버리지 (config 우선, 백테스트 기본값 8)
        self.leverage = config.get('leverage', 8)  # 기본 8배 레버리지
        
        # 트레일링 스톱 관련 (백테스트와 동일)
        self.trailing_stop_active = {}  # 심볼별 트레일링 스톱 활성화 여부
        self.trailing_stop_price = {}   # 심볼별 트레일링 스톱 가격
        self.highest_price = {}         # 심볼별 최고가
        self.lowest_price = {}          # 심볼별 최저가
        self.trailing_stop_activation_pct = 0.05  # 5% 수익 시 활성화 (백테스트)
        self.trailing_stop_distance_pct = 0.02    # 2% 트레일 (백테스트)
        
        # 연속 손실 추적
        self.consecutive_losses = {}  # 심볼별 연속 손실 횟수
        self.last_trade_result = {}   # 심볼별 마지막 거래 결과
        
        # 심볼별 ADX 임계값 조정 (백테스트와 동일)
        if any('BTC' in symbol for symbol in self.symbols):
            self.adx_threshold_btc = config.get('adx_threshold', 25)
        if any('ETH' in symbol for symbol in self.symbols):
            self.adx_threshold_eth = config.get('adx_threshold_eth', 20)
        if any('XRP' in symbol for symbol in self.symbols):
            self.adx_threshold_xrp = config.get('adx_threshold_xrp', 15)
        
        # 거래 비용 (백테스트와 동일)
        self.slippage_xrp = 0.002  # XRP는 0.2%
        self.slippage_default = 0.001  # 기타는 0.1%
        self.commission = 0.0006  # 수수료 0.06%
        
        # 가중치 시스템 파라미터
        self.weight_thresholds = {
            'strong': 4.0,   # 강한 신호 (진입 허용)
            'medium': 2.5,   # 중간 신호 (홀드)
            'weak': 1.0      # 약한 신호 (관망)
        }
        
        logger.info(f"ZLHMA EMA Cross 전략 초기화 완료 (1시간봉 백테스트 버전)")
        logger.info(f"  - Timeframe: 1H (고정)")
        logger.info(f"  - ZLHMA Period: {self.zlhma_period}")
        logger.info(f"  - EMA Periods: {self.fast_ema_period}/{self.slow_ema_period}")
        logger.info(f"  - ADX Threshold: {self.adx_threshold}")
        logger.info(f"  - Kelly Criterion: {self.kelly_min}-{self.kelly_max}")
        logger.info(f"  - Pyramiding: {self.pyramiding_enabled} (max {self.max_pyramiding_levels} levels)")
        logger.info(f"  - Partial Exit: {self.partial_exit_enabled}")
        logger.info(f"  - Trailing Stop: {self.trailing_stop_activation_pct*100}% activation, {self.trailing_stop_distance_pct*100}% trail")
        logger.info(f"  - Leverage: {self.leverage}x")
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
            df['atr_pct'] = (df['atr'] / df['close']) * 100  # 백테스트와 동일
            
            # ZLHMA 기울기 (모멘텀) - 백테스트와 동일
            df['zlhma_slope'] = df['zlhma'].diff() / df['zlhma'].shift(1) * 100
            
            # 가격 위치 (ZLHMA 대비) - 백테스트와 동일
            df['price_position_zlhma'] = (df['close'] - df['zlhma']) / df['zlhma'] * 100
            
            # RSI (추가 - BaseStrategy와 호환성)
            df['rsi'] = self._calculate_rsi(df['close'], 14)
            
            # Momentum
            df['momentum'] = ((df['close'] - df['close'].shift(20)) / 
                              df['close'].shift(20) * 100).abs()
            
            # Volume
            df['volume_ma'] = df['volume'].rolling(window=20).mean()
            df['volume_ratio'] = df['volume'] / df['volume_ma']
            
            # NaN 처리 (백테스트와 동일)
            df = df.fillna(0)
            
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
    
    def calculate_kelly_position_size(self, symbol: str) -> float:
        """Kelly Criterion에 따른 포지션 크기 계산"""
        if len(self.recent_trades) < 10:  # 최소 거래 수
            return self.kelly_min
        
        # 최근 거래에서 승률과 손익비 계산
        recent = self.recent_trades[-self.kelly_window:]
        wins = [t for t in recent if t['pnl'] > 0]
        losses = [t for t in recent if t['pnl'] < 0]
        
        if not wins or not losses:
            return self.kelly_min
        
        win_rate = len(wins) / len(recent)
        avg_win = np.mean([t['pnl_pct'] for t in wins])
        avg_loss = abs(np.mean([t['pnl_pct'] for t in losses]))
        
        # Kelly 공식: f = (p * b - q) / b
        # p: 승률, q: 패율, b: 손익비
        b = avg_win / avg_loss if avg_loss > 0 else 1
        p = win_rate
        q = 1 - p
        
        kelly = (p * b - q) / b if b > 0 else 0
        
        # 안전 마진 적용 (Kelly의 25%)
        kelly *= 0.25
        
        # 범위 제한
        position_size = max(self.kelly_min, min(kelly, self.kelly_max))
        
        logger.info(f"Kelly Criterion 계산: win_rate={win_rate:.2f}, avg_win={avg_win:.2f}%, avg_loss={avg_loss:.2f}%, kelly={kelly:.2f}, final={position_size:.2f}")
        
        return position_size
    
    def calculate_signal_weight(self, row: pd.Series, symbol: str) -> float:
        """신호 가중치 계산 - 백테스트와 동일"""
        weight = 0
        
        # 심볼별 ADX 임계값 설정
        adx_threshold = self.adx_threshold  # 기본값
        if 'BTC' in symbol:
            adx_threshold = getattr(self, 'adx_threshold_btc', 25)
        elif 'ETH' in symbol:
            adx_threshold = getattr(self, 'adx_threshold_eth', 20)
        elif 'XRP' in symbol:
            adx_threshold = getattr(self, 'adx_threshold_xrp', 15)
        
        # 1. EMA 크로스 (기본 가중치)
        if row.get('ema_cross_up', False):
            weight += 2.0
        elif row.get('ema_cross_down', False):
            weight -= 2.0
        
        # 2. ADX 필터 (추세 강도) - 백테스트와 동일
        if pd.notna(row.get('adx', 0)) and row['adx'] > adx_threshold:
            weight *= 1.5  # 강한 추세에서 가중치 증가
        elif pd.notna(row.get('adx', 0)) and row['adx'] < adx_threshold * 0.7:
            weight *= 0.5  # 약한 추세에서 가중치 감소
        
        # 3. ZLHMA 모멘텀 (백테스트: zlhma_slope 필드 사용)
        zlhma_slope = row.get('zlhma_slope', 0)
        if pd.isna(zlhma_slope):
            zlhma_slope = 0
        
        if abs(zlhma_slope) > 0.5:  # 강한 모멘텀
            if zlhma_slope > 0 and weight > 0:
                weight += 1.0
            elif zlhma_slope < 0 and weight < 0:
                weight -= 1.0
        
        # 4. RSI 필터
        rsi_value = row.get('rsi', 50)
        if pd.notna(rsi_value):
            if weight > 0 and rsi_value > 70:  # 과매수 구간에서 매수 신호 약화
                weight *= 0.7
            elif weight < 0 and rsi_value < 30:  # 과매도 구간에서 매도 신호 약화
                weight *= 0.7
        
        # 5. 볼륨 확인
        volume_ratio = row.get('volume_ratio', 1.0)
        if pd.notna(volume_ratio):
            if volume_ratio > 1.5:  # 거래량 증가
                weight *= 1.2
            elif volume_ratio < 0.5:  # 거래량 감소
                weight *= 0.8
        
        # 6. 가격 위치 (ZLHMA 대비) - 백테스트: price_position_zlhma 필드 사용
        price_position_zlhma = row.get('price_position_zlhma', 0)
        if pd.isna(price_position_zlhma):
            price_position_zlhma = 0
            
        if weight > 0 and price_position_zlhma > 2:  # 과도하게 위
            weight *= 0.8
        elif weight < 0 and price_position_zlhma < -2:  # 과도하게 아래
            weight *= 0.8
        
        return weight
    
    def should_add_pyramiding(self, symbol: str, position, current_price: float) -> bool:
        """피라미딩 추가 여부 판단"""
        if not self.pyramiding_enabled or not position:
            return False
        
        # 현재 포지션의 피라미딩 레벨 확인
        current_levels = self.pyramiding_positions.get(symbol, [])
        if len(current_levels) >= self.max_pyramiding_levels:
            return False
        
        # 현재 수익률 계산
        pnl_pct = (current_price - position.entry_price) / position.entry_price
        if position.side == 'SHORT':
            pnl_pct = -pnl_pct
        
        # 다음 피라미딩 레벨 확인
        next_level_idx = len(current_levels)
        if next_level_idx < len(self.pyramiding_levels):
            required_pnl = self.pyramiding_levels[next_level_idx]
            return pnl_pct >= required_pnl
        
        return False
    
    def update_trailing_stop(self, symbol: str, position, current_price: float):
        """트레일링 스톱 업데이트 - 백테스트와 동일"""
        if not position:
            return
        
        try:
            if position.side.upper() == 'LONG':
                # 최고가 업데이트
                if symbol not in self.highest_price or current_price > self.highest_price[symbol]:
                    self.highest_price[symbol] = current_price
                
                # 수익이 5% 이상이면 트레일링 스톱 활성화
                pnl_pct = (current_price - position.entry_price) / position.entry_price
                if pnl_pct >= self.trailing_stop_activation_pct and not self.trailing_stop_active.get(symbol, False):
                    self.trailing_stop_active[symbol] = True
                    self.trailing_stop_price[symbol] = self.highest_price[symbol] * (1 - self.trailing_stop_distance_pct)
                    logger.info(f"🔔 {symbol} 트레일링 스톱 활성화: {self.trailing_stop_price[symbol]:.2f}")
                
                # 트레일링 스톱 업데이트
                if self.trailing_stop_active.get(symbol, False):
                    new_stop = self.highest_price[symbol] * (1 - self.trailing_stop_distance_pct)
                    if symbol not in self.trailing_stop_price or new_stop > self.trailing_stop_price[symbol]:
                        self.trailing_stop_price[symbol] = new_stop
                        logger.debug(f"{symbol} 트레일링 스톱 업데이트: {new_stop:.2f}")
            
            elif position.side.upper() == 'SHORT':
                # 최저가 업데이트
                if symbol not in self.lowest_price or current_price < self.lowest_price[symbol]:
                    self.lowest_price[symbol] = current_price
                
                # 수익이 5% 이상이면 트레일링 스톱 활성화
                pnl_pct = (position.entry_price - current_price) / position.entry_price
                if pnl_pct >= self.trailing_stop_activation_pct and not self.trailing_stop_active.get(symbol, False):
                    self.trailing_stop_active[symbol] = True
                    self.trailing_stop_price[symbol] = self.lowest_price[symbol] * (1 + self.trailing_stop_distance_pct)
                    logger.info(f"🔔 {symbol} 트레일링 스톱 활성화: {self.trailing_stop_price[symbol]:.2f}")
                
                # 트레일링 스톱 업데이트
                if self.trailing_stop_active.get(symbol, False):
                    new_stop = self.lowest_price[symbol] * (1 + self.trailing_stop_distance_pct)
                    if symbol not in self.trailing_stop_price or new_stop < self.trailing_stop_price[symbol]:
                        self.trailing_stop_price[symbol] = new_stop
                        logger.debug(f"{symbol} 트레일링 스톱 업데이트: {new_stop:.2f}")
                        
        except Exception as e:
            logger.error(f"트레일링 스톱 업데이트 실패 ({symbol}): {e}")
    
    def check_trailing_stop(self, symbol: str, position, current_price: float) -> bool:
        """트레일링 스톱 히트 체크"""
        if not self.trailing_stop_active.get(symbol, False):
            return False
        
        try:
            trailing_stop = self.trailing_stop_price.get(symbol)
            if not trailing_stop:
                return False
            
            if position.side.upper() == 'LONG':
                return current_price <= trailing_stop
            else:  # SHORT
                return current_price >= trailing_stop
                
        except Exception as e:
            logger.error(f"트레일링 스톱 체크 실패 ({symbol}): {e}")
            return False
    
    def calculate_partial_exit_size(self, symbol: str, position, current_price: float) -> Tuple[float, str]:
        """부분 청산 크기 계산"""
        if not self.partial_exit_enabled or not position:
            return 0, ""
        
        # 현재 수익률 계산
        pnl_pct = (current_price - position.entry_price) / position.entry_price
        if position.side == 'SHORT':
            pnl_pct = -pnl_pct
        
        # 이미 청산된 비율 확인
        accumulated = self.accumulated_reduction.get(symbol, 0)
        
        # 부분 청산 확인
        for exit_level, exit_ratio in self.partial_exits:
            # 누적 청산 비율 계산
            total_ratio_at_level = sum([r for l, r in self.partial_exits if l <= exit_level])
            
            if pnl_pct >= exit_level and accumulated < total_ratio_at_level:
                # 이번에 청산할 비율
                exit_size = exit_ratio
                reason = f"Partial Exit {exit_level*100:.0f}% profit - {exit_ratio*100:.0f}% position"
                return exit_size, reason
        
        return 0, ""
    
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
        """캔들 종가 체크 시간인지 확인 - 1시간봉"""
        current_time = datetime.now()
        current_minute = current_time.minute
        current_second = current_time.second
        
        # 1시간 캔들 체크 (정시)
        if current_minute == 0 and current_second < 30:
            candle_time = current_time.replace(minute=0, second=0, microsecond=0)
            return True, candle_time
        
        return False, None
    
    async def fetch_and_prepare_data(self, symbol: str) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
        """데이터 수집 및 준비 - 1시간봉 사용"""
        try:
            # 1시간봉 데이터만 사용 (백테스트와 동일)
            # EMA 200 계산을 위해 충분한 데이터 수집
            df_1h = await self.binance_api.get_klines(symbol, '1h', limit=500)
            
            if df_1h.empty:
                logger.error(f"데이터 수집 실패: {symbol}")
                return None, None
            
            # 지표 계산
            df_1h = self.calculate_indicators(df_1h)
            
            # BaseStrategy 인터페이스 호환성을 위해 동일한 데이터를 두 번 반환
            return df_1h, df_1h
            
        except Exception as e:
            logger.error(f"데이터 준비 실패 ({symbol}): {e}")
            return None, None
    
    async def check_entry_signal(self, symbol: str, df_4h: pd.DataFrame, 
                                df_15m: pd.DataFrame, current_index: int) -> Tuple[bool, Optional[str]]:
        """진입 신호 체크 - BaseStrategy 인터페이스"""
        try:
            # 일일 손실 한도 체크 (백테스트와 동일)
            if not self.check_daily_loss_limit(symbol):
                return False, None
            
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
            prev1 = df_15m.iloc[current_index - 1]
            symbol = position.symbol
            
            # ATR 기반 손절/익절
            current_price = current['close']
            current_atr = current['atr'] if not pd.isna(current['atr']) else current_price * 0.02
            
            # 반대 신호 가중치 계산 (백테스트와 동일)
            signal_weight = self.calculate_signal_weight(current, df_15m, current_index)
            
            if position.side.upper() == 'LONG':
                stop_loss = position.entry_price - (current_atr * self.stop_loss_atr)
                take_profit = position.entry_price + (current_atr * self.take_profit_atr)
                
                if current_price <= stop_loss:
                    return True, f"손절 (SL: {stop_loss:.2f})"
                elif current_price >= take_profit:
                    return True, f"익절 (TP: {take_profit:.2f})"
                
                # 강한 반대 신호 (SHORT 신호)
                if signal_weight <= -self.signal_strength_threshold:
                    return True, f"반대 신호 (강도: {signal_weight:.1f})"
                
                # EMA 데드크로스
                if current['ema_fast'] < current['ema_slow'] and prev1['ema_fast'] >= prev1['ema_slow']:
                    return True, "EMA 데드크로스"
                
                # ZLHMA 아래로 돌파
                if current['close'] < current['zlhma'] and prev1['close'] >= prev1['zlhma']:
                    return True, "ZLHMA 하향 돌파"
                
            else:  # SHORT
                stop_loss = position.entry_price + (current_atr * self.stop_loss_atr)
                take_profit = position.entry_price - (current_atr * self.take_profit_atr)
                
                if current_price >= stop_loss:
                    return True, f"손절 (SL: {stop_loss:.2f})"
                elif current_price <= take_profit:
                    return True, f"익절 (TP: {take_profit:.2f})"
                
                # 강한 반대 신호 (LONG 신호)
                if signal_weight >= self.signal_strength_threshold:
                    return True, f"반대 신호 (강도: {signal_weight:.1f})"
                
                # EMA 골든크로스
                if current['ema_fast'] > current['ema_slow'] and prev1['ema_fast'] <= prev1['ema_slow']:
                    return True, "EMA 골든크로스"
                
                # ZLHMA 위로 돌파
                if current['close'] > current['zlhma'] and prev1['close'] <= prev1['zlhma']:
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
        """포지션 관리 - 부분 익절 및 트레일링 스톱 포함"""
        try:
            symbol = position.symbol
            
            # 데이터 준비
            df_4h, df_15m = await self.fetch_and_prepare_data(symbol)
            
            if df_4h is None or df_15m is None:
                return
            
            # 마지막 완성된 캔들 사용
            current_index = len(df_15m) - 2
            current = df_15m.iloc[current_index]
            current_price = current['close']
            
            # 1. 트레일링 스톱 업데이트
            self.update_trailing_stop(symbol, position, current_price)
            
            # 2. 트레일링 스톱 히트 체크
            if self.check_trailing_stop(symbol, position, current_price):
                logger.info(f"🔔 트레일링 스톱 히트: {symbol} @ {self.trailing_stop_price[symbol]:.2f}")
                success = await self.execute_exit(position, f"트레일링 스톱 ({self.trailing_stop_price[symbol]:.2f})")
                if success:
                    logger.info(f"✅ {symbol} 트레일링 스톱 청산 완료")
                    # 심볼별 상태 초기화
                    self.trailing_stop_active[symbol] = False
                    self.trailing_stop_price[symbol] = None
                    self.highest_price[symbol] = None
                    self.lowest_price[symbol] = None
                return
            
            # 3. 부분 익절 체크
            exit_size, partial_reason = self.calculate_partial_exit_size(symbol, position, current_price)
            if exit_size > 0:
                logger.info(f"💰 부분 익절 신호: {symbol} - {partial_reason}")
                
                # 부분 청산 실행
                # 바이낸스 API를 통해 일부만 청산
                try:
                    # 청산할 수량 계산
                    exit_quantity = position.size * exit_size
                    exit_quantity = await self.binance_api.round_quantity(symbol, exit_quantity)
                    
                    # 청산 주문
                    side = 'SELL' if position.side.upper() == 'LONG' else 'BUY'
                    order = await self.binance_api.place_order(
                        symbol=symbol,
                        side=side,
                        quantity=exit_quantity,
                        order_type='MARKET'
                    )
                    
                    if order:
                        # 누적 청산 비율 업데이트
                        if symbol not in self.accumulated_reduction:
                            self.accumulated_reduction[symbol] = 0
                        self.accumulated_reduction[symbol] += exit_size
                        
                        # 포지션 크기 업데이트 (position_manager에서 처리)
                        await self.position_manager.update_position_size(symbol, position.size - exit_quantity)
                        
                        logger.info(f"✅ {symbol} 부분 익절 완료: {exit_size*100:.0f}% ({exit_quantity})")
                        
                        # 손익분기점으로 스톱 이동 (첫 부분 익절 시)
                        if self.accumulated_reduction[symbol] <= exit_size:
                            # 손익분기점 + 약간의 이익
                            if position.side.upper() == 'LONG':
                                new_stop = position.entry_price * 1.002  # 0.2% 이익
                            else:
                                new_stop = position.entry_price * 0.998  # 0.2% 이익
                            
                            logger.info(f"🛡️ {symbol} 스톱로스를 손익분기점으로 이동: {new_stop:.2f}")
                
                except Exception as e:
                    logger.error(f"부분 익절 실행 실패 ({symbol}): {e}")
                
                return  # 부분 익절 후에는 전체 청산 체크하지 않음
            
            # 4. 전체 청산 신호 체크
            should_exit, reason = await self.check_exit_signal(
                position, df_15m, current_index
            )
            
            if should_exit:
                logger.info(f"🚨 청산 신호 감지: {symbol} - {reason}")
                
                # 반대 신호인 경우 판별
                is_reverse_signal = "반대 신호" in reason
                
                # 청산 실행
                success = await self.execute_exit(position, reason)
                
                if success:
                    logger.info(f"✅ {symbol} 청산 완료: {reason}")
                    # 심볼별 상태 초기화
                    self.accumulated_reduction[symbol] = 0
                    self.trailing_stop_active[symbol] = False
                    self.trailing_stop_price[symbol] = None
                    self.highest_price[symbol] = None
                    self.lowest_price[symbol] = None
                    
                    # 반대 신호로 인한 청산인 경우 즉시 반대 진입
                    if is_reverse_signal:
                        # 새로운 방향 결정
                        new_direction = 'short' if position.side.upper() == 'LONG' else 'long'
                        
                        # 손절/익절 계산
                        current_atr = current['atr'] if not pd.isna(current['atr']) else current_price * 0.02
                        if new_direction == 'long':
                            stop_loss = current_price - (current_atr * self.stop_loss_atr)
                            take_profit = current_price + (current_atr * self.take_profit_atr)
                        else:
                            stop_loss = current_price + (current_atr * self.stop_loss_atr)
                            take_profit = current_price - (current_atr * self.take_profit_atr)
                        
                        # 즉시 반대 진입
                        logger.info(f"🔄 {symbol} 반대 진입 시작: {new_direction.upper()}")
                        try:
                            reverse_success = await self.execute_entry(symbol, new_direction, stop_loss, take_profit)
                            if reverse_success:
                                logger.info(f"✅ {symbol} 반대 진입 성공: {new_direction.upper()}")
                            else:
                                logger.warning(f"⚠️ {symbol} 반대 진입 실패")
                        except Exception as e:
                            logger.error(f"반대 진입 중 오류 발생: {e}")
                
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
    
    def calculate_kelly_position_size(self) -> float:
        """Kelly Criterion에 따른 포지션 크기 계산 (백테스트와 동일)"""
        if len(self.recent_trades) < 10:  # 최소 거래 수
            return self.kelly_min
        
        # 최근 거래에서 승률과 손익비 계산
        recent = self.recent_trades[-self.kelly_window:]
        wins = [t for t in recent if t['pnl_pct'] > 0]
        losses = [t for t in recent if t['pnl_pct'] < 0]
        
        if not wins or not losses:
            return self.kelly_min
        
        win_rate = len(wins) / len(recent)
        avg_win = np.mean([t['pnl_pct'] for t in wins])
        avg_loss = abs(np.mean([t['pnl_pct'] for t in losses]))
        
        # Kelly 공식: f = (p * b - q) / b
        # p: 승률, q: 패율, b: 손익비
        b = avg_win / avg_loss if avg_loss > 0 else 1
        p = win_rate
        q = 1 - p
        
        kelly = (p * b - q) / b if b > 0 else 0
        
        # 안전 마진 적용 (Kelly의 25%)
        kelly *= 0.25
        
        # 범위 제한
        return max(self.kelly_min, min(kelly, self.kelly_max))
    
    async def calculate_position_size(self, symbol: str, use_dynamic_sizing: bool = True) -> float:
        """포지션 크기 계산 - Kelly Criterion 적용"""
        try:
            # Kelly Criterion 기반 포지션 크기 계산
            kelly_size = self.calculate_kelly_position_size()
            
            logger.info(f"📊 Kelly Criterion 포지션 크기: {kelly_size*100:.1f}% (최근 {len(self.recent_trades)}개 거래 분석)")
            
            # 계좌 잔고 조회
            account_balance = await self.binance_api.get_account_balance()
            
            # 현재 활성 포지션 확인
            active_positions = self.position_manager.get_active_positions(include_manual=False)
            active_count = len(active_positions)
            
            # 최대 포지션 수
            max_positions = self.config.get('max_positions', 3)
            
            if active_count >= max_positions:
                logger.warning(f"최대 포지션 수 도달: {active_count}/{max_positions}")
                return 0.0
            
            # MDD 제한에 따른 포지션 크기 조정
            if self.mdd_manager:
                mdd_restrictions = await self.mdd_manager.check_mdd_restrictions(account_balance)
                if mdd_restrictions['position_size_multiplier'] < 1.0:
                    logger.info(f"MDD 제한으로 포지션 크기 축소: {mdd_restrictions['position_size_multiplier']*100:.0f}%")
                    kelly_size *= mdd_restrictions['position_size_multiplier']
            
            # 포지션 가치 계산
            position_value = account_balance * kelly_size
            
            # 현재 가격 조회
            current_price = await self.binance_api.get_current_price(symbol)
            
            # 수량 계산
            quantity = position_value / current_price
            
            # 심볼별 정밀도 적용
            quantity = await self.binance_api.round_quantity(symbol, quantity)
            
            # 최소 주문 금액 체크
            min_notional = 10.0  # USDT
            if quantity * current_price < min_notional:
                logger.warning(f"주문 금액이 최소값 미만: ${quantity * current_price:.2f} < ${min_notional}")
                return 0.0
            
            return quantity
            
        except Exception as e:
            logger.error(f"포지션 크기 계산 실패: {e}")
            # 에러 시 부모 클래스의 기본 계산 사용
            return await super().calculate_position_size(symbol, use_dynamic_sizing)
    
    def check_daily_loss_limit(self, symbol: str) -> bool:
        """일일 손실 한도 확인 - 거래 가능 여부 반환"""
        # 거래 중단 시간 확인
        if symbol in self.trading_suspended_until:
            current_time = datetime.now()
            if current_time < self.trading_suspended_until[symbol]:
                logger.warning(f"⚠️ {symbol} 일일 손실 한도로 거래 중단 중 (재개: {self.trading_suspended_until[symbol]})")
                return False
            else:
                # 거래 재개 - 중단 정보 삭제
                del self.trading_suspended_until[symbol]
                self.daily_loss[symbol] = 0
                logger.info(f"✅ {symbol} 거래 재개 - 일일 손실 한도 리셋")
        
        return True
    
    def update_daily_loss(self, symbol: str, pnl_pct: float, account_balance: float):
        """일일 손실 업데이트 및 거래 중단 처리"""
        try:
            current_date = datetime.now().date()
            
            # 날짜가 바뀌면 일일 손실 리셋
            if symbol in self.last_trade_date:
                if current_date != self.last_trade_date[symbol]:
                    self.daily_loss[symbol] = 0
                    logger.info(f"📅 {symbol} 새로운 거래일 시작 - 일일 손실 리셋")
            
            self.last_trade_date[symbol] = current_date
            
            # 손실인 경우만 누적
            if pnl_pct < 0:
                # 실제 손실 금액 계산 (레버리지 적용)
                actual_loss_pct = abs(pnl_pct) * self.leverage / 100  # 자본 대비 비율
                
                if symbol not in self.daily_loss:
                    self.daily_loss[symbol] = 0
                
                self.daily_loss[symbol] += actual_loss_pct
                
                logger.info(f"📊 {symbol} 일일 손실 업데이트: {self.daily_loss[symbol]*100:.2f}% / {self.daily_loss_limit*100:.0f}%")
                
                # 일일 손실 한도 초과 확인
                if self.daily_loss[symbol] > self.daily_loss_limit:
                    suspension_time = datetime.now() + timedelta(hours=24)
                    self.trading_suspended_until[symbol] = suspension_time
                    
                    logger.warning(f"⚠️ {symbol} 일일 손실 한도 초과! 거래 중단 (~{suspension_time.strftime('%Y-%m-%d %H:%M')})")
                    
                    # 텔레그램 알림 (있다면)
                    if hasattr(self, 'notification_manager') and self.notification_manager:
                        self.notification_manager.send_notification(
                            f"⚠️ 일일 손실 한도 초과\n"
                            f"심볼: {symbol}\n"
                            f"일일 손실: {self.daily_loss[symbol]*100:.2f}%\n"
                            f"거래 재개: {suspension_time.strftime('%Y-%m-%d %H:%M')}",
                            priority='HIGH'
                        )
            
        except Exception as e:
            logger.error(f"일일 손실 업데이트 실패: {e}")
    
    async def execute_exit(self, position, reason: str):
        """포지션 청산 실행 (일일 손실 추적 포함)"""
        try:
            # 청산 전 포지션 정보 저장
            symbol = position.symbol
            entry_price = position.entry_price
            side = position.side
            
            # 현재 가격 조회
            current_price = await self.binance_api.get_current_price(symbol)
            
            # 예상 손익률 계산
            if side.upper() == 'LONG':
                pnl_pct = (current_price - entry_price) / entry_price * 100
            else:
                pnl_pct = (entry_price - current_price) / entry_price * 100
            
            # 부모 클래스의 execute_exit 호출
            result = await super().execute_exit(position, reason)
            
            if result:
                # 계좌 잔고 조회
                account_balance = await self.binance_api.get_account_balance()
                
                # 일일 손실 업데이트
                self.update_daily_loss(symbol, pnl_pct, account_balance)
                
                # 연속 손실 추적
                if pnl_pct < 0:
                    if symbol not in self.consecutive_losses:
                        self.consecutive_losses[symbol] = 0
                    self.consecutive_losses[symbol] += 1
                    logger.info(f"📉 {symbol} 연속 손실: {self.consecutive_losses[symbol]}회")
                else:
                    self.consecutive_losses[symbol] = 0
                
                # 거래 기록 저장 (Kelly Criterion용)
                trade_record = {
                    'symbol': symbol,
                    'pnl_pct': pnl_pct,
                    'timestamp': datetime.now(),
                    'reason': reason
                }
                self.recent_trades.append(trade_record)
                
                # 최근 거래 기록 제한
                if len(self.recent_trades) > self.kelly_window * 2:
                    self.recent_trades = self.recent_trades[-self.kelly_window:]
            
            return result
            
        except Exception as e:
            logger.error(f"포지션 청산 실패 (일일 손실 추적): {e}")
            # 에러가 발생해도 부모 클래스의 기본 청산은 시도
            return await super().execute_exit(position, reason)
    
    async def execute_entry(self, symbol: str, direction: str, stop_loss: float, take_profit: float):
        """포지션 진입 실행 (거래 기록 추가)"""
        try:
            # 진입 신호 로깅
            logger.info(f"🎯 {symbol} 진입 시도: {direction.upper()}")
            logger.info(f"   Kelly 포지션 크기: {self.calculate_kelly_position_size()*100:.1f}%")
            logger.info(f"   신호 강도: {self.signal_strength_threshold}")
            
            # 부모 클래스의 execute_entry 호출
            result = await super().execute_entry(symbol, direction, stop_loss, take_profit)
            
            if result:
                # 진입 성공 시 거래 정보 기록
                position = self.position_manager.get_position(symbol)
                if position:
                    # 심볼별 상태 초기화
                    self.trailing_stop_active[symbol] = False
                    self.trailing_stop_price[symbol] = None
                    self.highest_price[symbol] = position.entry_price
                    self.lowest_price[symbol] = position.entry_price
                    self.accumulated_reduction[symbol] = 0
                    
                    # 진입 정보 로깅
                    logger.info(f"✅ {symbol} 진입 완료:")
                    logger.info(f"   방향: {direction.upper()}")
                    logger.info(f"   진입가: {position.entry_price:.2f}")
                    logger.info(f"   수량: {position.size}")
                    logger.info(f"   손절: {stop_loss:.2f}")
                    logger.info(f"   익절: {take_profit:.2f}")
                    logger.info(f"   레버리지: {self.leverage}x")
            
            return result
            
        except Exception as e:
            logger.error(f"포지션 진입 실패 (거래 기록): {e}")
            # 에러가 발생해도 부모 클래스의 기본 진입은 시도
            return await super().execute_entry(symbol, direction, stop_loss, take_profit)
