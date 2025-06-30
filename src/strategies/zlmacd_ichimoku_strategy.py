# src/strategies/zlmacd_ichimoku_strategy.py
"""
ZL MACD + Ichimoku Strategy for AlbraTrading System
비트코인 1시간봉에 특화된 ZL MACD + Ichimoku Cloud 전략
"""

import asyncio
import pandas as pd
import pandas_ta as ta
import numpy as np
from typing import Dict, Optional, Tuple, List
from datetime import datetime, timedelta
import logging

from .base_strategy import BaseStrategy
from ..core.mdd_manager_improved import ImprovedMDDManager
from ..utils.smart_notification_manager import SmartNotificationManager

logger = logging.getLogger(__name__)

class ZLMACDIchimokuStrategy(BaseStrategy):
    """ZL MACD + Ichimoku Combined Strategy"""
    
    def __init__(self, binance_api, position_manager, config: Dict, config_manager=None):
        """전략 초기화"""
        super().__init__(binance_api, position_manager, config)
        
        # 전략 이름 설정
        self.strategy_name = "ZLMACD_ICHIMOKU"
        self.name = "ZL MACD + Ichimoku"
        
        # 거래 심볼 및 타임프레임 (비트코인 1시간봉 전용)
        self.symbols = config.get('symbols', ['BTCUSDT'])
        self.timeframe = '1h'  # 1시간봉 고정
        
        # ZL MACD 파라미터
        self.zlmacd_fast = config.get('zlmacd_fast', 12)
        self.zlmacd_slow = config.get('zlmacd_slow', 26)
        self.zlmacd_signal = config.get('zlmacd_signal', 9)
        
        # Ichimoku 파라미터
        self.tenkan_period = config.get('tenkan_period', 9)
        self.kijun_period = config.get('kijun_period', 26)
        self.senkou_b_period = config.get('senkou_b_period', 52)
        self.chikou_shift = config.get('chikou_shift', 26)
        self.cloud_shift = config.get('cloud_shift', 26)
        
        # 진입 조건 파라미터
        self.min_signal_strength = config.get('min_signal_strength', 3)  # 최소 3개 신호 필요
        self.cloud_distance_threshold = config.get('cloud_distance_threshold', 0.005)  # 0.5%
        
        # ADX 필터
        self.adx_period = config.get('adx_period', 14)
        self.adx_threshold = config.get('adx_threshold', 25)  # ADX > 25 필요
        
        # 손절/익절 설정 (ATR 기반)
        self.stop_loss_atr_multiplier = config.get('stop_loss_atr', 1.5)
        self.take_profit_atr_multiplier = config.get('take_profit_atr', 5.0)
        self.max_stop_loss_pct = config.get('max_stop_loss_pct', 0.02)  # 최대 2%
        
        # 트레일링 스톱 설정
        self.trailing_stop_activation = config.get('trailing_stop_activation', 0.03)  # 3% 수익
        self.trailing_stop_distance = config.get('trailing_stop_distance', 0.10)  # 10% 트레일
        self.trailing_stops = {}  # 심볼별 트레일링 스톱 추적
        
        # 부분 익절 설정
        self.partial_exit_levels = config.get('partial_exit_levels', [
            {'profit_pct': 5.0, 'exit_ratio': 0.25},   # 5%에서 25% 익절
            {'profit_pct': 10.0, 'exit_ratio': 0.35},  # 10%에서 35% 익절
            {'profit_pct': 15.0, 'exit_ratio': 0.40}   # 15%에서 40% 익절
        ])
        self.partial_exits_done = {}  # 심볼별 부분 익절 추적
        
        # 피라미딩 설정
        self.pyramiding_enabled = config.get('pyramiding_enabled', True)
        self.pyramiding_levels = config.get('pyramiding_levels', [
            {'profit_pct': 3.0, 'size_ratio': 0.75},   # 3%에서 75% 추가
            {'profit_pct': 6.0, 'size_ratio': 0.50},   # 6%에서 50% 추가
            {'profit_pct': 9.0, 'size_ratio': 0.25}    # 9%에서 25% 추가
        ])
        self.pyramiding_positions = {}  # 심볼별 피라미딩 추적
        
        # 리스크 관리 파라미터
        self.daily_loss_limit = config.get('daily_loss_limit_pct', 3.0) / 100  # 3%
        self.consecutive_loss_adjustment = config.get('consecutive_loss_adjustment', True)
        self.consecutive_losses = 0
        self.daily_losses = {}  # 날짜별 손실 추적
        
        # Kelly Criterion 파라미터 (동적 포지션 사이징)
        self.use_kelly = config.get('use_kelly', True)
        self.kelly_lookback = config.get('kelly_lookback', 100)  # 최근 100개 거래
        self.recent_trades = []  # Kelly 계산용 거래 기록
        
        # 데이터 캐시
        self.data_cache = {}
        self.last_data_update = {}
        self.indicators_cache = {}
        
        # MDD 관리자 참조
        self.mdd_manager = None
        
        # 알림 매니저 참조
        self.notification_manager = None
        
        logger.info(f"✅ ZL MACD + Ichimoku Strategy 초기화 완료")
        logger.info(f"  • 심볼: {self.symbols}")
        logger.info(f"  • 타임프레임: {self.timeframe}")
        logger.info(f"  • ZL MACD: Fast={self.zlmacd_fast}, Slow={self.zlmacd_slow}, Signal={self.zlmacd_signal}")
        logger.info(f"  • Ichimoku: Tenkan={self.tenkan_period}, Kijun={self.kijun_period}, Senkou B={self.senkou_b_period}")
        logger.info(f"  • 레버리지: {self.leverage}x")
        logger.info(f"  • 포지션 크기: {self.position_size}%")
    
    def calculate_zlema(self, series: pd.Series, period: int) -> pd.Series:
        """Zero Lag EMA 계산"""
        ema1 = series.ewm(span=period, adjust=False).mean()
        ema2 = ema1.ewm(span=period, adjust=False).mean()
        zlema = 2 * ema1 - ema2
        return zlema
    
    def calculate_zlmacd(self, df: pd.DataFrame) -> pd.DataFrame:
        """ZL MACD 계산"""
        # Zero Lag EMA 계산
        zlema_fast = self.calculate_zlema(df['close'], self.zlmacd_fast)
        zlema_slow = self.calculate_zlema(df['close'], self.zlmacd_slow)
        
        # MACD line
        df['zlmacd'] = zlema_fast - zlema_slow
        
        # Signal line (9-period EMA of MACD)
        df['zlmacd_signal'] = df['zlmacd'].ewm(span=self.zlmacd_signal, adjust=False).mean()
        
        # Histogram
        df['zlmacd_hist'] = df['zlmacd'] - df['zlmacd_signal']
        
        return df
    
    def calculate_ichimoku(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ichimoku Cloud 계산"""
        # Tenkan-sen (Conversion Line)
        high_9 = df['high'].rolling(self.tenkan_period).max()
        low_9 = df['low'].rolling(self.tenkan_period).min()
        df['tenkan_sen'] = (high_9 + low_9) / 2
        
        # Kijun-sen (Base Line)
        high_26 = df['high'].rolling(self.kijun_period).max()
        low_26 = df['low'].rolling(self.kijun_period).min()
        df['kijun_sen'] = (high_26 + low_26) / 2
        
        # Senkou Span A (Leading Span A)
        df['senkou_span_a'] = ((df['tenkan_sen'] + df['kijun_sen']) / 2).shift(self.cloud_shift)
        
        # Senkou Span B (Leading Span B)
        high_52 = df['high'].rolling(self.senkou_b_period).max()
        low_52 = df['low'].rolling(self.senkou_b_period).min()
        df['senkou_span_b'] = ((high_52 + low_52) / 2).shift(self.cloud_shift)
        
        # Chikou Span (Lagging Span)
        df['chikou_span'] = df['close'].shift(-self.chikou_shift)
        
        # Cloud top and bottom
        df['cloud_top'] = df[['senkou_span_a', 'senkou_span_b']].max(axis=1)
        df['cloud_bottom'] = df[['senkou_span_a', 'senkou_span_b']].min(axis=1)
        
        # Cloud color (bullish/bearish)
        df['cloud_color'] = (df['senkou_span_a'] > df['senkou_span_b']).astype(int)
        
        # Cloud thickness
        df['cloud_thickness'] = (df['cloud_top'] - df['cloud_bottom']) / df['close']
        
        return df
    
    def calculate_adx(self, df: pd.DataFrame) -> pd.DataFrame:
        """ADX 계산"""
        # pandas_ta를 사용하여 ADX 계산
        adx_df = ta.adx(df['high'], df['low'], df['close'], length=self.adx_period)
        
        if adx_df is not None and not adx_df.empty:
            df = pd.concat([df, adx_df], axis=1)
        else:
            # Fallback: 수동 계산
            high_low = df['high'] - df['low']
            high_close = abs(df['high'] - df['close'].shift(1))
            low_close = abs(df['low'] - df['close'].shift(1))
            
            df['tr'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            df['atr'] = df['tr'].rolling(self.adx_period).mean()
            
            # 간단한 ADX 추정 (정확도는 떨어지지만 사용 가능)
            df[f'ADX_{self.adx_period}'] = 25.0  # 기본값
        
        return df
    
    async def check_entry_signal(self, symbol: str, df_1h: pd.DataFrame, df_15m: pd.DataFrame, current_index: int) -> Tuple[bool, Optional[str]]:
        """진입 신호 체크"""
        try:
            # 최소 데이터 확인
            if current_index < self.senkou_b_period + self.cloud_shift:
                return False, None
            
            # 지표 계산
            df_1h = self.calculate_zlmacd(df_1h.copy())
            df_1h = self.calculate_ichimoku(df_1h.copy())
            df_1h = self.calculate_adx(df_1h.copy())
            
            # 현재 값 추출
            current_price = df_1h['close'].iloc[current_index]
            zlmacd = df_1h['zlmacd'].iloc[current_index]
            zlmacd_signal = df_1h['zlmacd_signal'].iloc[current_index]
            zlmacd_prev = df_1h['zlmacd'].iloc[current_index-1]
            zlmacd_signal_prev = df_1h['zlmacd_signal'].iloc[current_index-1]
            
            tenkan = df_1h['tenkan_sen'].iloc[current_index]
            kijun = df_1h['kijun_sen'].iloc[current_index]
            cloud_top = df_1h['cloud_top'].iloc[current_index]
            cloud_bottom = df_1h['cloud_bottom'].iloc[current_index]
            cloud_color = df_1h['cloud_color'].iloc[current_index]
            
            # ADX 값 확인
            adx_col = f'ADX_{self.adx_period}'
            adx_value = df_1h[adx_col].iloc[current_index] if adx_col in df_1h.columns else 0
            
            # ADX 필터
            if adx_value < self.adx_threshold:
                return False, None
            
            # 일일 손실 한도 체크
            if await self._check_daily_loss_limit():
                logger.warning(f"일일 손실 한도 도달 - 거래 중단")
                return False, None
            
            # 롱 진입 조건 확인
            long_signals = 0
            long_reasons = []
            
            # 1. ZL MACD 골든크로스
            if zlmacd > zlmacd_signal and zlmacd_prev <= zlmacd_signal_prev:
                long_signals += 1
                long_reasons.append("ZL_MACD_GOLDEN_CROSS")
            
            # 2. 가격이 구름 위
            if current_price > cloud_top:
                long_signals += 1
                long_reasons.append("PRICE_ABOVE_CLOUD")
            
            # 3. 전환선 > 기준선
            if tenkan > kijun:
                long_signals += 1
                long_reasons.append("TENKAN_ABOVE_KIJUN")
            
            # 4. 구름이 상승 전환 (녹색)
            if cloud_color == 1:
                long_signals += 0.5
                long_reasons.append("BULLISH_CLOUD")
            
            # 롱 진입 판단
            if long_signals >= self.min_signal_strength:
                direction = "long"
                signal_desc = f"LONG: {', '.join(long_reasons)} (Strength: {long_signals})"
                logger.info(f"{symbol} 롱 신호 감지: {signal_desc}")
                return True, direction
            
            # 숏 진입 조건 확인
            short_signals = 0
            short_reasons = []
            
            # 1. ZL MACD 데드크로스
            if zlmacd < zlmacd_signal and zlmacd_prev >= zlmacd_signal_prev:
                short_signals += 1
                short_reasons.append("ZL_MACD_DEAD_CROSS")
            
            # 2. 가격이 구름 아래
            if current_price < cloud_bottom:
                short_signals += 1
                short_reasons.append("PRICE_BELOW_CLOUD")
            
            # 3. 전환선 < 기준선
            if tenkan < kijun:
                short_signals += 1
                short_reasons.append("TENKAN_BELOW_KIJUN")
            
            # 4. 구름이 하락 전환 (빨간색)
            if cloud_color == 0:
                short_signals += 0.5
                short_reasons.append("BEARISH_CLOUD")
            
            # 숏 진입 판단
            if short_signals >= self.min_signal_strength:
                direction = "short"
                signal_desc = f"SHORT: {', '.join(short_reasons)} (Strength: {short_signals})"
                logger.info(f"{symbol} 숏 신호 감지: {signal_desc}")
                return True, direction
            
            return False, None
            
        except Exception as e:
            logger.error(f"진입 신호 체크 실패 ({symbol}): {e}")
            return False, None
    
    async def check_exit_signal(self, position, df_1h: pd.DataFrame, current_index: int) -> Tuple[bool, str]:
        """청산 신호 체크"""
        try:
            symbol = position.symbol
            
            # 지표 계산
            df_1h = self.calculate_zlmacd(df_1h.copy())
            df_1h = self.calculate_ichimoku(df_1h.copy())
            
            # 현재 값 추출
            current_price = df_1h['close'].iloc[current_index]
            high = df_1h['high'].iloc[current_index]
            low = df_1h['low'].iloc[current_index]
            kijun = df_1h['kijun_sen'].iloc[current_index]
            cloud_top = df_1h['cloud_top'].iloc[current_index]
            cloud_bottom = df_1h['cloud_bottom'].iloc[current_index]
            
            # 현재 손익률 계산
            if position.side.upper() == 'LONG':
                pnl_pct = (current_price - position.entry_price) / position.entry_price
            else:
                pnl_pct = (position.entry_price - current_price) / position.entry_price
            
            # 트레일링 스톱 체크
            if await self._check_trailing_stop(position, current_price, pnl_pct):
                return True, "TRAILING_STOP"
            
            # 부분 익절 체크 (청산은 아니고 부분 익절만)
            await self._check_partial_exit(position, pnl_pct)
            
            # 기준선 터치 청산
            if position.side.upper() == 'LONG':
                if low <= kijun:
                    return True, "KIJUN_TOUCH"
                
                # 구름 하단 돌파
                if current_price < cloud_bottom:
                    return True, "CLOUD_BREAK"
                
                # ZL MACD 데드크로스
                if (df_1h['zlmacd'].iloc[current_index] < df_1h['zlmacd_signal'].iloc[current_index] and
                    df_1h['zlmacd'].iloc[current_index-1] >= df_1h['zlmacd_signal'].iloc[current_index-1]):
                    return True, "ZLMACD_DEAD_CROSS"
                    
            else:  # SHORT
                if high >= kijun:
                    return True, "KIJUN_TOUCH"
                
                # 구름 상단 돌파
                if current_price > cloud_top:
                    return True, "CLOUD_BREAK"
                
                # ZL MACD 골든크로스
                if (df_1h['zlmacd'].iloc[current_index] > df_1h['zlmacd_signal'].iloc[current_index] and
                    df_1h['zlmacd'].iloc[current_index-1] <= df_1h['zlmacd_signal'].iloc[current_index-1]):
                    return True, "ZLMACD_GOLDEN_CROSS"
            
            # 최대 손실 체크
            if pnl_pct <= -self.max_stop_loss_pct:
                return True, "MAX_STOP_LOSS"
            
            return False, ""
            
        except Exception as e:
            logger.error(f"청산 신호 체크 실패 ({position.symbol}): {e}")
            return False, ""
    
    async def _check_trailing_stop(self, position, current_price: float, pnl_pct: float) -> bool:
        """트레일링 스톱 체크"""
        symbol = position.symbol
        
        # 트레일링 스톱 활성화 체크
        if pnl_pct >= self.trailing_stop_activation:
            if symbol not in self.trailing_stops:
                self.trailing_stops[symbol] = {
                    'activated': True,
                    'highest_price': current_price if position.side.upper() == 'LONG' else position.entry_price,
                    'lowest_price': position.entry_price if position.side.upper() == 'LONG' else current_price
                }
                logger.info(f"{symbol} 트레일링 스톱 활성화 (수익률: {pnl_pct*100:.1f}%)")
            
            # 최고/최저가 업데이트
            if position.side.upper() == 'LONG':
                self.trailing_stops[symbol]['highest_price'] = max(
                    self.trailing_stops[symbol]['highest_price'], 
                    current_price
                )
                # 트레일링 스톱 체크
                stop_price = self.trailing_stops[symbol]['highest_price'] * (1 - self.trailing_stop_distance)
                if current_price <= stop_price:
                    logger.info(f"{symbol} 트레일링 스톱 도달: {current_price:.2f} <= {stop_price:.2f}")
                    return True
            else:  # SHORT
                self.trailing_stops[symbol]['lowest_price'] = min(
                    self.trailing_stops[symbol]['lowest_price'], 
                    current_price
                )
                # 트레일링 스톱 체크
                stop_price = self.trailing_stops[symbol]['lowest_price'] * (1 + self.trailing_stop_distance)
                if current_price >= stop_price:
                    logger.info(f"{symbol} 트레일링 스톱 도달: {current_price:.2f} >= {stop_price:.2f}")
                    return True
        
        return False
    
    async def _check_partial_exit(self, position, pnl_pct: float):
        """부분 익절 체크"""
        symbol = position.symbol
        
        # 부분 익절 추적 초기화
        if symbol not in self.partial_exits_done:
            self.partial_exits_done[symbol] = []
        
        # 각 레벨 체크
        for i, level in enumerate(self.partial_exit_levels):
            level_id = f"level_{i}"
            if level_id not in self.partial_exits_done[symbol] and pnl_pct >= level['profit_pct'] / 100:
                # 부분 익절 실행
                exit_size = position.size * level['exit_ratio']
                logger.info(f"{symbol} 부분 익절 실행: {level['profit_pct']}%에서 {level['exit_ratio']*100}% 청산")
                
                # TODO: 실제 부분 청산 로직 구현
                # await self.binance_api.partial_close_position(symbol, exit_size)
                
                self.partial_exits_done[symbol].append(level_id)
    
    async def _check_daily_loss_limit(self) -> bool:
        """일일 손실 한도 체크"""
        today = datetime.now().date()
        
        # 날짜 변경 시 리셋
        if today not in self.daily_losses:
            self.daily_losses = {today: 0.0}
        
        # 계좌 잔고 조회
        account_balance = await self.binance_api.get_account_balance()
        
        # 일일 손실률 계산
        daily_loss_pct = abs(self.daily_losses.get(today, 0.0)) / account_balance
        
        return daily_loss_pct >= self.daily_loss_limit
    
    async def calculate_position_size_with_kelly(self, symbol: str) -> float:
        """Kelly Criterion을 사용한 동적 포지션 크기 계산"""
        try:
            # 기본 포지션 크기부터 시작
            base_size = await super().calculate_position_size(symbol, use_dynamic_sizing=True)
            
            if not self.use_kelly or len(self.recent_trades) < 20:
                return base_size
            
            # Kelly Criterion 계산
            wins = [t for t in self.recent_trades if t['pnl'] > 0]
            losses = [t for t in self.recent_trades if t['pnl'] <= 0]
            
            if len(wins) == 0 or len(losses) == 0:
                return base_size
            
            win_rate = len(wins) / len(self.recent_trades)
            avg_win = np.mean([t['pnl_pct'] for t in wins])
            avg_loss = abs(np.mean([t['pnl_pct'] for t in losses]))
            
            if avg_loss == 0:
                return base_size
            
            # Kelly 공식
            b = avg_win / avg_loss
            p = win_rate
            q = 1 - p
            
            kelly_fraction = (p * b - q) / b
            
            # Half Kelly 사용
            kelly_fraction = kelly_fraction * 0.5
            
            # 제한 적용
            kelly_fraction = max(0.05, min(0.25, kelly_fraction))
            
            # 연속 손실에 따른 조정
            if self.consecutive_losses >= 7:
                kelly_fraction *= 0.3
            elif self.consecutive_losses >= 5:
                kelly_fraction *= 0.5
            elif self.consecutive_losses >= 3:
                kelly_fraction *= 0.7
            
            # 계좌 잔고 기준으로 계산
            account_balance = await self.binance_api.get_account_balance()
            position_value = account_balance * kelly_fraction
            
            # 현재 가격으로 수량 계산
            current_price = await self.binance_api.get_current_price(symbol)
            quantity = position_value / current_price
            
            # 정밀도 적용
            quantity = await self.binance_api.round_quantity(symbol, quantity)
            
            logger.info(f"{symbol} Kelly 포지션 크기: {kelly_fraction*100:.1f}% "
                       f"(승률: {win_rate*100:.1f}%, 평균수익: {avg_win:.1f}%, 평균손실: {avg_loss:.1f}%)")
            
            return quantity
            
        except Exception as e:
            logger.error(f"Kelly 포지션 크기 계산 실패: {e}")
            return await super().calculate_position_size(symbol)
    
    async def execute_entry(self, symbol: str, direction: str, stop_loss: float, take_profit: float):
        """포지션 진입 실행 (Kelly 적용)"""
        # Kelly Criterion으로 포지션 크기 계산
        if self.use_kelly:
            quantity = await self.calculate_position_size_with_kelly(symbol)
        else:
            quantity = await self.calculate_position_size(symbol)
        
        if quantity <= 0:
            logger.error(f"유효하지 않은 포지션 크기: {quantity}")
            return False
        
        # 기본 진입 실행
        success = await super().execute_entry(symbol, direction, stop_loss, take_profit)
        
        if success:
            # 트레일링 스톱 초기화
            if symbol in self.trailing_stops:
                del self.trailing_stops[symbol]
            
            # 부분 익절 초기화
            if symbol in self.partial_exits_done:
                del self.partial_exits_done[symbol]
            
            # 피라미딩 초기화
            self.pyramiding_positions[symbol] = []
        
        return success
    
    async def execute_exit(self, position, reason: str):
        """포지션 청산 실행"""
        # 손익 계산
        current_price = await self.binance_api.get_current_price(position.symbol)
        
        if position.side.upper() == 'LONG':
            pnl_pct = (current_price - position.entry_price) / position.entry_price
        else:
            pnl_pct = (position.entry_price - current_price) / position.entry_price
        
        net_pnl_pct = pnl_pct * self.leverage
        
        # 거래 기록 저장 (Kelly 계산용)
        trade_record = {
            'symbol': position.symbol,
            'pnl': net_pnl_pct * position.size * position.entry_price,
            'pnl_pct': net_pnl_pct,
            'direction': position.side,
            'exit_reason': reason
        }
        
        self.recent_trades.append(trade_record)
        if len(self.recent_trades) > self.kelly_lookback:
            self.recent_trades.pop(0)
        
        # 연속 손실 업데이트
        if net_pnl_pct < 0:
            self.consecutive_losses += 1
            # 일일 손실 업데이트
            today = datetime.now().date()
            if today not in self.daily_losses:
                self.daily_losses[today] = 0.0
            self.daily_losses[today] += abs(trade_record['pnl'])
        else:
            self.consecutive_losses = 0
        
        # 기본 청산 실행
        success = await super().execute_exit(position, reason)
        
        if success:
            # 트레일링 스톱 정리
            if position.symbol in self.trailing_stops:
                del self.trailing_stops[position.symbol]
            
            # 부분 익절 정리
            if position.symbol in self.partial_exits_done:
                del self.partial_exits_done[position.symbol]
        
        return success
    
    async def _check_pyramiding_opportunity(self, position, current_price: float) -> bool:
        """피라미딩 기회 체크"""
        if not self.pyramiding_enabled:
            return False
        
        symbol = position.symbol
        
        # 현재 수익률 계산
        if position.side.upper() == 'LONG':
            pnl_pct = (current_price - position.entry_price) / position.entry_price * 100
        else:
            pnl_pct = (position.entry_price - current_price) / position.entry_price * 100
        
        # 피라미딩 레벨 체크
        if symbol not in self.pyramiding_positions:
            self.pyramiding_positions[symbol] = []
        
        current_pyramids = len(self.pyramiding_positions[symbol])
        
        for i, level in enumerate(self.pyramiding_levels):
            if i == current_pyramids and pnl_pct >= level['profit_pct']:
                logger.info(f"{symbol} 피라미딩 기회: 레벨 {i+1} (수익률: {pnl_pct:.1f}%)")
                # TODO: 실제 피라미딩 포지션 추가 로직
                return True
        
        return False
    
    async def run(self):
        """전략 실행 메인 루프"""
        self.is_running = True
        logger.info(f"🚀 {self.strategy_name} 전략 시작 (1시간봉 기준)")
        
        while self.is_running:
            try:
                for symbol in self.symbols:
                    # 포지션 체크 - 전략명 포함
                    position = self.position_manager.get_position(symbol, self.strategy_name)
                    
                    if position and position.status == 'ACTIVE':
                        # 기존 포지션 관리
                        await self._manage_position(position)
                    else:
                        # 신규 진입 체크
                        if await self.can_enter_position(symbol):
                            await self._check_new_entry(symbol)
                
                # 다음 1시간봉까지 대기
                await self._wait_for_next_candle()
                
            except Exception as e:
                logger.error(f"전략 실행 오류: {e}", exc_info=True)
                await asyncio.sleep(60)
    
    async def _wait_for_next_candle(self):
        """다음 1시간봉까지 대기"""
        now = datetime.now()
        # 다음 정시까지 시간 계산
        next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        wait_seconds = (next_hour - now).total_seconds()
        
        # 캔들 종가 체크를 위해 약간 늦게 실행 (30초 후)
        wait_seconds += 30
        
        logger.info(f"다음 1시간봉까지 {wait_seconds:.0f}초 대기...")
        await asyncio.sleep(wait_seconds)
    
    async def _manage_position(self, position):
        """포지션 관리"""
        try:
            # 1시간봉 데이터 조회
            df_1h = await self.binance_api.get_klines(
                position.symbol, 
                self.timeframe, 
                limit=200
            )
            
            if df_1h.empty:
                logger.error(f"데이터 조회 실패: {position.symbol}")
                return
            
            # 청산 신호 체크
            should_exit, exit_reason = await self.check_exit_signal(
                position, 
                df_1h, 
                len(df_1h) - 1
            )
            
            if should_exit:
                logger.info(f"🔚 청산 신호: {position.symbol} - {exit_reason}")
                await self.execute_exit(position, exit_reason)
            else:
                # 피라미딩 체크
                current_price = df_1h['close'].iloc[-1]
                if await self._check_pyramiding_opportunity(position, current_price):
                    logger.info(f"📈 피라미딩 추가 검토: {position.symbol}")
                    
        except Exception as e:
            logger.error(f"포지션 관리 실패 ({position.symbol}): {e}")
    
    async def _check_new_entry(self, symbol: str):
        """신규 진입 체크"""
        try:
            # 1시간봉 데이터 조회
            df_1h = await self.binance_api.get_klines(
                symbol, 
                self.timeframe, 
                limit=200
            )
            
            if df_1h.empty:
                logger.error(f"데이터 조회 실패: {symbol}")
                return
            
            # 15분봉은 사용하지 않음 (1시간봉 전용)
            df_15m = pd.DataFrame()  # 더미
            
            # 진입 신호 체크
            has_signal, direction = await self.check_entry_signal(
                symbol, 
                df_1h, 
                df_15m, 
                len(df_1h) - 1
            )
            
            if has_signal and direction:
                # ATR 계산
                atr = df_1h['atr'].iloc[-1] if 'atr' in df_1h.columns else df_1h['close'].iloc[-1] * 0.02
                current_price = df_1h['close'].iloc[-1]
                
                # 손절/익절 계산
                if direction == 'long':
                    stop_loss = current_price - (atr * self.stop_loss_atr_multiplier)
                    take_profit = current_price + (atr * self.take_profit_atr_multiplier)
                else:
                    stop_loss = current_price + (atr * self.stop_loss_atr_multiplier)
                    take_profit = current_price - (atr * self.take_profit_atr_multiplier)
                
                # 최대 손실 제한
                max_loss = current_price * self.max_stop_loss_pct
                if direction == 'long':
                    stop_loss = max(stop_loss, current_price - max_loss)
                else:
                    stop_loss = min(stop_loss, current_price + max_loss)
                
                logger.info(f"🎯 진입 신호: {symbol} {direction.upper()}")
                logger.info(f"   SL: {stop_loss:.2f}, TP: {take_profit:.2f}")
                
                # 진입 실행
                await self.execute_entry(symbol, direction, stop_loss, take_profit)
                
        except Exception as e:
            logger.error(f"신규 진입 체크 실패 ({symbol}): {e}")
    
    def get_strategy_status(self) -> Dict:
        """전략 상태 조회"""
        return {
            'name': self.strategy_name,
            'symbols': self.symbols,
            'timeframe': self.timeframe,
            'consecutive_losses': self.consecutive_losses,
            'recent_trades_count': len(self.recent_trades),
            'active_pyramids': {
                symbol: len(positions) 
                for symbol, positions in self.pyramiding_positions.items()
            },
            'trailing_stops_active': list(self.trailing_stops.keys()),
            'partial_exits_done': {
                symbol: len(exits) 
                for symbol, exits in self.partial_exits_done.items()
            }
        }
