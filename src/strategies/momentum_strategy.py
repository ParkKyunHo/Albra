# src/strategies/momentum_strategy.py
"""
Momentum Breakout Strategy
백테스트에서 검증된 모멘텀 돌파 전략
"""

import asyncio
import pandas as pd
import pandas_ta as ta
import numpy as np
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
import logging

from .base_strategy import BaseStrategy
from ..core.mdd_manager_improved import ImprovedMDDManager

logger = logging.getLogger(__name__)

class MomentumStrategy(BaseStrategy):
    """Momentum Breakout 전략 - Strong Trend를 타는 전략"""
    
    def __init__(self, binance_api, position_manager, config: Dict, config_manager=None):
        super().__init__(binance_api, position_manager, config)
        
        # 전략 이름 설정
        self.strategy_name = "MOMENTUM"
        self.name = "Momentum Breakout"
        
        # 백테스트 개선 파라미터
        self.position_size = config.get('position_size', 20)  # 계좌의 20%
        self.adx_min = config.get('adx_min', 35)  # 강한 추세만 (30 → 35)
        self.di_diff = config.get('di_diff', 15)  # 명확한 방향성 (10 → 15)
        self.volume_spike = config.get('volume_spike', 2.0)  # 거래량 2배
        self.acceleration = config.get('acceleration', 1.5)  # 가속도 1.5배
        
        # 손절/익절
        self.stop_loss_atr = config.get('stop_loss_atr', 2.0)
        self.take_profit_atr = config.get('take_profit_atr', 6.0)
        
        # 추적 손절
        self.trailing_enabled = config.get('trailing_enabled', True)
        self.trailing_start = config.get('trailing_start', 1.5)  # 1.5 ATR부터 시작
        self.trailing_step = config.get('trailing_step', 0.5)   # 0.5 ATR 단위로 이동
        
        # Donchian Channel 파라미터
        self.dc_period = config.get('dc_period', 20)
        self.strong_trend_channel_width = config.get('strong_trend_channel_width', 0.08)  # 8%
        self.strong_trend_price_extreme = config.get('strong_trend_price_extreme', 0.1)   # 10%
        
        # 신호 간격
        self.min_signal_interval = config.get('min_signal_interval', 4)  # 4시간
        
        # 데이터 캐시
        self.data_cache = {}
        self.last_data_update = {}
        
        # MDD 관리자 (나중에 초기화)
        self.mdd_manager = None
        
        # 알림 매니저 참조 (나중에 주입)
        self.notification_manager = None
        
        # 거래 코인 목록 (config에서 로드)
        self.trading_coins = config.get('trading_coins', [
            'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 
            'SOLUSDT', 'XRPUSDT', 'ADAUSDT'
        ])
        
        # 추적 손절 상태
        self.trailing_stops = {}
        
        logger.info(f"Momentum Breakout 전략 초기화 완료")
        logger.info(f"파라미터: ADX최소={self.adx_min}, DI차이={self.di_diff}, 거래량스파이크={self.volume_spike}x")
        logger.info(f"손절/익절: SL={self.stop_loss_atr}xATR, TP={self.take_profit_atr}xATR")
        logger.info(f"추적손절: {'활성화' if self.trailing_enabled else '비활성화'}")
    
    async def run_cycle(self):
        """전략 실행 사이클"""
        try:
            # 초기화 체크
            if not hasattr(self, '_initialized'):
                await self._initialize()
                self._initialized = True
            
            # 캔들 종가 기반 체크
            await self._run_candle_close_cycle()
            
            # 추적 손절 업데이트
            if self.trailing_enabled:
                await self._update_trailing_stops()
            
            # 공통 작업
            await self._periodic_maintenance()
            
        except Exception as e:
            logger.error(f"{self.name} 사이클 실행 실패: {e}")
    
    async def _initialize(self):
        """전략 초기화"""
        logger.info(f"{self.name} 전략 초기화 시작")
        
        # MDD 관리자 초기화
        mdd_config = self.config.get('mdd_protection', {
            'max_allowed_mdd': 40.0,
            'mdd_recovery_threshold': 15.0,
            'mdd_position_reduction': 0.5,
            'mdd_stop_new_trades': True,
            'mdd_force_close_threshold': 50.0
        })
        self.mdd_manager = ImprovedMDDManager(mdd_config, self.notification_manager)
        logger.info("✓ MDD 보호 기능 활성화")
    
    async def _run_candle_close_cycle(self):
        """캔들 종가 기반 사이클"""
        # TFPE와 동일한 로직 사용
        is_check_time, candle_time = await self._is_candle_close_time()
        if not is_check_time or not candle_time:
            return
        
        if not hasattr(self, '_last_checked_candle'):
            self._last_checked_candle = {}
        
        # 새로운 캔들인지 확인
        any_new_candle = False
        for symbol in self.trading_coins:
            if symbol not in self._last_checked_candle or self._last_checked_candle[symbol] < candle_time:
                any_new_candle = True
                break
        
        if not any_new_candle:
            return
        
        logger.info(f"\n{'='*60}")
        logger.info(f"🚀 Momentum 전략 - 15분 캔들 체크: {candle_time.strftime('%Y-%m-%d %H:%M')}")
        logger.info(f"{'='*60}")
        
        tasks = []
        
        for symbol in self.trading_coins:
            # 이미 체크했으면 스킵
            if symbol in self._last_checked_candle and self._last_checked_candle[symbol] >= candle_time:
                continue
            
            # 체크 완료 표시
            self._last_checked_candle[symbol] = candle_time
            
            # 현재 포지션 확인
            position = self.position_manager.get_position(symbol)
            
            # 1. 포지션이 있으면 관리
            if position and position.status == 'ACTIVE':
                # 자동 전략 포지션만 관리
                if not position.is_manual and position.strategy_name == self.strategy_name:
                    logger.info(f"  🎯 {symbol}: 모멘텀 포지션 관리")
                    tasks.append(self._manage_position(position))
            
            # 2. 포지션이 없으면 진입 체크
            else:
                if self.position_manager.is_position_exist(symbol):
                    logger.warning(f"  ⚠️ {symbol}: 다른 전략 포지션 존재")
                    continue
                
                can_enter = await self.can_enter_position(symbol)
                if can_enter:
                    logger.info(f"  🔍 {symbol}: 모멘텀 신호 체크")
                    tasks.append(self._check_new_entry(symbol))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info(f"{'='*60}\n")
    
    async def _is_candle_close_time(self) -> Tuple[bool, Optional[datetime]]:
        """캔들 종가 체크 시간인지 확인"""
        # TFPE와 동일한 로직
        current_time = datetime.now()
        current_minute = current_time.minute
        current_second = current_time.second
        
        # 15분 캔들 체크 시간인지 확인
        if current_minute % 15 == 0 and current_second < 30:
            candle_time = current_time.replace(minute=(current_minute // 15) * 15, second=0, microsecond=0)
            return True, candle_time
        
        return False, None
    
    async def fetch_and_prepare_data(self, symbol: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
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
            
            # Donchian Channel 추가
            df_4h = self.add_donchian_indicators(df_4h)
            df_15m = self.add_donchian_indicators(df_15m)
            
            # 가속도 계산
            df_15m['price_change'] = df_15m['close'].pct_change()
            df_15m['acceleration'] = df_15m['price_change'].diff()
            
            return df_4h, df_15m
            
        except Exception as e:
            logger.error(f"데이터 준비 실패 ({symbol}): {e}")
            return None, None
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """기술 지표 계산"""
        try:
            # ADX/DI
            adx_data = ta.adx(df['high'], df['low'], df['close'], length=14)
            if adx_data is not None:
                df['adx'] = adx_data['ADX_14']
                df['plus_di'] = adx_data['DMP_14']
                df['minus_di'] = adx_data['DMN_14']
                df['di_diff'] = df['plus_di'] - df['minus_di']
            
            # ATR
            df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
            
            # 볼륨
            df['volume_ma'] = df['volume'].rolling(window=20).mean()
            df['volume_ratio'] = df['volume'] / df['volume_ma']
            
            # 모멘텀
            df['momentum'] = ((df['close'] - df['close'].shift(20)) / 
                             df['close'].shift(20) * 100).abs()
            
            return df
            
        except Exception as e:
            logger.error(f"지표 계산 실패: {e}")
            return df
    
    def add_donchian_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Donchian Channel 지표 추가"""
        try:
            df['dc_upper'] = df['high'].rolling(window=self.dc_period).max()
            df['dc_lower'] = df['low'].rolling(window=self.dc_period).min()
            df['dc_middle'] = (df['dc_upper'] + df['dc_lower']) / 2
            
            # 채널폭
            df['dc_width'] = df['dc_upper'] - df['dc_lower']
            df['channel_width_pct'] = df['dc_width'] / df['close']
            
            # 가격 위치
            df['price_position'] = np.where(
                df['dc_width'] > 0,
                (df['close'] - df['dc_lower']) / df['dc_width'],
                0.5
            )
            
            return df
            
        except Exception as e:
            logger.error(f"Donchian 지표 추가 실패: {e}")
            return df
    
    async def check_entry_signal(self, symbol: str, df_4h: pd.DataFrame, 
                                df_15m: pd.DataFrame, current_index: int) -> Tuple[bool, Optional[str]]:
        """모멘텀 돌파 진입 신호 체크"""
        try:
            if current_index < 50:
                return False, None
            
            current = df_15m.iloc[current_index]
            
            # 필수 지표 체크
            if pd.isna(current['adx']) or pd.isna(current['di_diff']):
                return False, None
            
            # 1. 강한 추세 확인 (ADX)
            if current['adx'] < self.adx_min:
                logger.debug(f"{symbol} ADX 부족: {current['adx']:.1f} < {self.adx_min}")
                return False, None
            
            # 2. 명확한 방향성 (DI 차이)
            di_diff_abs = abs(current['di_diff'])
            if di_diff_abs < self.di_diff:
                logger.debug(f"{symbol} DI 차이 부족: {di_diff_abs:.1f} < {self.di_diff}")
                return False, None
            
            # 방향 결정
            direction = 'long' if current['di_diff'] > 0 else 'short'
            
            # 3. 거래량 스파이크
            if current['volume_ratio'] < self.volume_spike:
                logger.debug(f"{symbol} 거래량 부족: {current['volume_ratio']:.2f} < {self.volume_spike}")
                return False, None
            
            # 4. 가격 가속도
            if pd.notna(current['acceleration']) and current['acceleration'] > 0:
                # 가속도가 양수면 모멘텀 증가
                accel_multiplier = 1 + current['acceleration']
                if accel_multiplier < self.acceleration:
                    return False, None
            
            # 5. Donchian 돌파 확인
            if direction == 'long':
                # 상단 돌파 근처
                if current['price_position'] < 0.9:
                    return False, None
            else:
                # 하단 돌파 근처
                if current['price_position'] > 0.1:
                    return False, None
            
            # 6. 채널폭 확인 (강한 추세)
            if current['channel_width_pct'] < self.strong_trend_channel_width:
                logger.debug(f"{symbol} 채널폭 부족: {current['channel_width_pct']:.3f}")
                return False, None
            
            logger.info(f"🚀 모멘텀 신호 감지: {symbol} {direction}")
            logger.info(f"   ADX: {current['adx']:.1f}, DI차이: {di_diff_abs:.1f}")
            logger.info(f"   거래량: {current['volume_ratio']:.2f}x, 채널폭: {current['channel_width_pct']:.1%}")
            
            # 마지막 신호 시간 업데이트
            self.last_signal_time[symbol] = datetime.now()
            
            return True, direction
            
        except Exception as e:
            logger.error(f"모멘텀 신호 체크 실패: {e}")
            return False, None
    
    async def check_exit_signal(self, position, df_15m: pd.DataFrame, 
                               current_index: int) -> Tuple[bool, str]:
        """청산 신호 체크 (손절/익절 + 추적손절)"""
        try:
            current = df_15m.iloc[current_index]
            current_price = current['close']
            
            # 손익률 계산
            if position.side == 'long':
                pnl_pct = (current_price - position.entry_price) / position.entry_price * 100
            else:
                pnl_pct = (position.entry_price - current_price) / position.entry_price * 100
            
            # ATR 기반 손절/익절
            current_atr = current['atr']
            
            if position.side.upper() == 'LONG':
                stop_loss = position.entry_price - (current_atr * self.stop_loss_atr)
                take_profit = position.entry_price + (current_atr * self.take_profit_atr)
                
                # 추적 손절 체크
                if self.trailing_enabled and position.symbol in self.trailing_stops:
                    stop_loss = max(stop_loss, self.trailing_stops[position.symbol])
                
                if current_price <= stop_loss:
                    return True, f"손절 (SL: {stop_loss:.2f})"
                elif current_price >= take_profit:
                    return True, f"익절 (TP: {take_profit:.2f})"
                    
            else:  # SHORT
                stop_loss = position.entry_price + (current_atr * self.stop_loss_atr)
                take_profit = position.entry_price - (current_atr * self.take_profit_atr)
                
                # 추적 손절 체크
                if self.trailing_enabled and position.symbol in self.trailing_stops:
                    stop_loss = min(stop_loss, self.trailing_stops[position.symbol])
                
                if current_price >= stop_loss:
                    return True, f"손절 (SL: {stop_loss:.2f})"
                elif current_price <= take_profit:
                    return True, f"익절 (TP: {take_profit:.2f})"
            
            # 추세 약화 체크
            if current['adx'] < self.adx_min * 0.7:  # ADX가 크게 감소
                return True, "추세 약화"
            
            # DI 역전 체크
            if position.side == 'long' and current['di_diff'] < -5:
                return True, "DI 역전 (하락 전환)"
            elif position.side == 'short' and current['di_diff'] > 5:
                return True, "DI 역전 (상승 전환)"
            
            return False, ""
            
        except Exception as e:
            logger.error(f"청산 신호 체크 실패: {e}")
            return False, ""
    
    async def _update_trailing_stops(self):
        """추적 손절 업데이트"""
        try:
            active_positions = self.position_manager.get_active_positions(include_manual=False)
            momentum_positions = [p for p in active_positions if p.strategy_name == self.strategy_name]
            
            for position in momentum_positions:
                symbol = position.symbol
                
                # 현재가 조회
                current_price = await self.binance_api.get_current_price(symbol)
                if not current_price:
                    continue
                
                # 최근 ATR 조회
                df = await self.binance_api.get_klines(symbol, '15m', limit=20)
                if df.empty or 'atr' not in df.columns:
                    continue
                
                current_atr = df['atr'].iloc[-1]
                
                # 수익 ATR 계산
                if position.side.upper() == 'LONG':
                    profit_in_atr = (current_price - position.entry_price) / current_atr
                else:
                    profit_in_atr = (position.entry_price - current_price) / current_atr
                
                # 추적 손절 시작 조건
                if profit_in_atr >= self.trailing_start:
                    # 추적 손절 레벨 계산
                    trail_distance = current_atr * (self.stop_loss_atr - self.trailing_step * int(profit_in_atr / self.trailing_step))
                    
                    if position.side.upper() == 'LONG':
                        new_stop = current_price - trail_distance
                        # 기존 추적 손절보다 높을 때만 업데이트
                        if symbol not in self.trailing_stops or new_stop > self.trailing_stops[symbol]:
                            self.trailing_stops[symbol] = new_stop
                            logger.info(f"{symbol} 추적 손절 업데이트: {new_stop:.2f}")
                    else:
                        new_stop = current_price + trail_distance
                        # 기존 추적 손절보다 낮을 때만 업데이트
                        if symbol not in self.trailing_stops or new_stop < self.trailing_stops[symbol]:
                            self.trailing_stops[symbol] = new_stop
                            logger.info(f"{symbol} 추적 손절 업데이트: {new_stop:.2f}")
                            
        except Exception as e:
            logger.error(f"추적 손절 업데이트 실패: {e}")
    
    async def _check_new_entry(self, symbol: str):
        """신규 진입 체크"""
        try:
            # MDD 제한 체크
            if self.mdd_manager:
                current_balance = await self.binance_api.get_account_balance()
                mdd_restrictions = await self.mdd_manager.check_mdd_restrictions(current_balance)
                
                if not mdd_restrictions['allow_new_trades']:
                    self.mdd_manager.skip_trade_by_mdd()
                    logger.warning(f"MDD 제한으로 신규 거래 차단: {mdd_restrictions['reason']}")
                    return
            
            # 데이터 준비
            df_4h, df_15m = await self.fetch_and_prepare_data(symbol)
            
            if df_4h is None or df_15m is None:
                return
            
            # 마지막 완성된 캔들 사용
            current_index = len(df_15m) - 2
            
            if current_index < 50:
                return
            
            # 진입 신호 체크
            signal, direction = await self.check_entry_signal(
                symbol, df_4h, df_15m, current_index
            )
            
            if not signal:
                return
            
            logger.info(f"🎯 모멘텀 신호 확인! {symbol} {direction}")
            
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
                logger.info(f"⚡ {symbol} 모멘텀 포지션 진입 완료")
                
                # 추적 손절 초기화
                if self.trailing_enabled:
                    self.trailing_stops[symbol] = stop_loss
            
        except Exception as e:
            logger.error(f"모멘텀 진입 체크 실패 ({symbol}): {e}")
    
    async def _manage_position(self, position):
        """포지션 관리"""
        try:
            symbol = position.symbol
            
            # 데이터 준비
            df_4h, df_15m = await self.fetch_and_prepare_data(symbol)
            
            if df_4h is None or df_15m is None:
                return
            
            # 현재 인덱스
            current_index = len(df_15m) - 2
            
            if current_index < 0:
                return
            
            # 청산 신호 체크
            should_exit, reason = await self.check_exit_signal(
                position, df_15m, current_index
            )
            
            if should_exit:
                logger.info(f"🚨 모멘텀 청산 신호: {symbol} - {reason}")
                
                # 청산 실행
                success = await self.execute_exit(position, reason)
                
                if success:
                    logger.info(f"✅ {symbol} 모멘텀 포지션 청산 완료")
                    
                    # 추적 손절 제거
                    if symbol in self.trailing_stops:
                        del self.trailing_stops[symbol]
                        
        except Exception as e:
            logger.error(f"모멘텀 포지션 관리 실패 ({position.symbol}): {e}")
    
    async def _periodic_maintenance(self):
        """주기적 유지보수 작업"""
        try:
            # MDD 체크
            if self.mdd_manager:
                active_positions = self.position_manager.get_active_positions(include_manual=False)
                momentum_positions = [p for p in active_positions if p.strategy_name == self.strategy_name]
                self.mdd_manager.update_position_count(len(momentum_positions))
                
                current_balance = await self.binance_api.get_account_balance()
                mdd_restrictions = await self.mdd_manager.check_mdd_restrictions(current_balance)
                
                if mdd_restrictions['force_close_positions']:
                    logger.critical(f"MDD 강제 청산: {mdd_restrictions['reason']}")
                    await self._force_close_all_positions("MDD 강제 청산")
                    
        except Exception as e:
            logger.error(f"유지보수 작업 실패: {e}")
    
    async def _force_close_all_positions(self, reason: str):
        """모든 포지션 강제 청산"""
        try:
            active_positions = self.position_manager.get_active_positions(include_manual=False)
            momentum_positions = [p for p in active_positions if p.strategy_name == self.strategy_name]
            
            for position in momentum_positions:
                try:
                    logger.info(f"강제 청산: {position.symbol}")
                    await self.execute_exit(position, reason)
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"{position.symbol} 강제 청산 실패: {e}")
                    
        except Exception as e:
            logger.error(f"강제 청산 작업 실패: {e}")
    
    def get_strategy_info(self) -> Dict:
        """전략 정보 반환"""
        return {
            'name': 'Momentum Breakout Strategy',
            'version': '1.0',
            'parameters': {
                'leverage': self.leverage,
                'position_size': f"{self.position_size}%",
                'adx_min': self.adx_min,
                'di_diff': self.di_diff,
                'stop_loss': f"ATR × {self.stop_loss_atr}",
                'take_profit': f"ATR × {self.take_profit_atr}",
                'volume_spike': f"{self.volume_spike}x",
                'trailing_stop': '활성화' if self.trailing_enabled else '비활성화'
            },
            'description': 'Strong trend following strategy with momentum breakout'
        }
