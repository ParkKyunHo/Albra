# backtest_modules/signal_generator_hybrid_debug.py
"""
신호 생성 모듈 - TFPE Pullback + Momentum Breakout Hybrid Strategy (Debug Version)
기존 TFPE 전략을 유지하면서 Momentum 전략 추가 - 디버깅 버전
"""

import pandas as pd
import numpy as np
from typing import Tuple, List, Dict, Optional


class HybridSignalGenerator:
    """TFPE + Momentum Hybrid 신호 생성 클래스"""
    
    def __init__(self, params: dict, mdd_manager=None):
        self.params = params
        self.mdd_manager = mdd_manager
        
        # Momentum 전략 전용 파라미터
        self.momentum_params = {
            # 포지션 크기
            'momentum_position_size': 15,  # 계좌의 15% (TFPE 24%보다 작게)
            
            # 손절/익절
            'momentum_stop_loss_atr': 2.0,   # 2 ATR (TFPE 1.5보다 넓게)
            'momentum_take_profit_atr': 6.0,  # 6 ATR (TFPE 4.0보다 크게)
            
            # 트레일링 스톱
            'momentum_trailing_enabled': True,
            'momentum_trailing_start': 1.5,   # 1.5 ATR 수익 후 시작
            'momentum_trailing_step': 0.5,    # 0.5 ATR씩 따라감
            
            # 모멘텀 진입 조건 (완화된 버전)
            'momentum_adx_min': 25,  # 30 → 25로 완화
            'momentum_di_diff': 5,   # 10 → 5로 완화
            'momentum_volume_spike': 1.5,  # 2.0 → 1.5로 완화
            'momentum_acceleration': 1.2,  # 1.5 → 1.2로 완화
            
            # 시장 체제
            'strong_trend_channel_width': 0.05,  # 0.08 → 0.05로 완화
            'strong_trend_price_extreme': 0.2,   # 0.1 → 0.2로 완화
            
            # 최대 포지션 제한
            'max_combined_position': 30,  # TFPE + Momentum 합계 최대 30%
        }
        
        # 통합 파라미터
        self.params.update(self.momentum_params)
        
        # 디버깅 카운터
        self.debug_counters = {
            'market_regime_checks': 0,
            'strong_trend_count': 0,
            'momentum_checks': 0,
            'channel_breakouts': 0,
            'momentum_signals': 0
        }
    
    def detect_market_regime(self, df_4h: pd.DataFrame, df_15m: pd.DataFrame, 
                           current_index: int) -> str:
        """시장 체제 감지 (Market Regime Detection)"""
        self.debug_counters['market_regime_checks'] += 1
        
        current = df_15m.iloc[current_index]
        
        # 4H 데이터에서 정보 가져오기
        current_time = df_15m.index[current_index]
        aligned_time = current_time.floor('4H')
        
        if aligned_time not in df_4h.index:
            return 'NORMAL'
        
        # dc_width가 비율로 저장되어 있는지 확인
        dc_width_4h = df_4h.loc[aligned_time].get('dc_width', 0)
        if 'channel_width_pct' in df_4h.columns:
            dc_width_4h = df_4h.loc[aligned_time, 'channel_width_pct']
        
        price_position = current.get('price_position', 0.5)
        adx = current.get('adx', 0)
        
        # 디버깅 출력 (처음 몇 번만)
        if self.debug_counters['market_regime_checks'] <= 10:
            print(f"[DEBUG] Market Regime Check #{self.debug_counters['market_regime_checks']}")
            print(f"  - DC Width: {dc_width_4h:.4f} (threshold: {self.params['strong_trend_channel_width']})")
            print(f"  - Price Position: {price_position:.3f}")
            print(f"  - ADX: {adx:.1f} (threshold: {self.params['momentum_adx_min']})")
        
        # STRONG_TREND 조건
        if (dc_width_4h > self.params['strong_trend_channel_width'] and  # 채널 폭 5% 이상
            (price_position > (1 - self.params['strong_trend_price_extreme']) or 
             price_position < self.params['strong_trend_price_extreme']) and  # 가격이 채널 극단
            adx > self.params['momentum_adx_min']):  # 강한 추세
            self.debug_counters['strong_trend_count'] += 1
            if self.debug_counters['strong_trend_count'] <= 5:
                print(f"[DEBUG] STRONG_TREND detected! (count: {self.debug_counters['strong_trend_count']})")
            return 'STRONG_TREND'
        else:
            return 'NORMAL'
    
    def check_momentum_signal(self, df_4h: pd.DataFrame, df_15m: pd.DataFrame, 
                            current_index: int) -> Tuple[bool, Optional[str], List[str], Dict]:
        """
        Momentum Breakout 신호 체크
        강한 추세 돌파 시 진입
        """
        self.debug_counters['momentum_checks'] += 1
        
        if current_index < 50:
            return False, None, [], {}
        
        current = df_15m.iloc[current_index]
        prev = df_15m.iloc[current_index - 1]  # 이전 캔들
        
        # 필수 지표 체크 (volume_ma 제거)
        required_fields = ['close', 'adx', 'plus_di', 'minus_di', 'volume', 
                          'dc_upper', 'dc_lower']
        
        # 누락된 필드 확인
        missing_fields = [field for field in required_fields if pd.isna(current.get(field, np.nan))]
        if missing_fields:
            if self.debug_counters['momentum_checks'] <= 10:
                print(f"[DEBUG] Momentum check #{self.debug_counters['momentum_checks']} - Missing fields: {missing_fields}")
            return False, None, [], {}
        
        conditions_met = []
        condition_values = {}
        direction = None
        
        # 1. Donchian Channel 돌파 체크 (2개 캔들 확인)
        channel_breakout = False
        
        if prev['close'] <= prev['dc_upper'] and current['close'] > current['dc_upper']:
            # 상단 돌파
            channel_breakout = True
            direction = 'long'
            conditions_met.append("channel_breakout_up")
            condition_values['breakout_level'] = current['dc_upper']
            self.debug_counters['channel_breakouts'] += 1
            if self.debug_counters['channel_breakouts'] <= 5:
                print(f"[DEBUG] Channel BREAKOUT UP detected! Price: {current['close']:.2f} > Upper: {current['dc_upper']:.2f}")
            
        elif prev['close'] >= prev['dc_lower'] and current['close'] < current['dc_lower']:
            # 하단 돌파
            channel_breakout = True
            direction = 'short'
            conditions_met.append("channel_breakout_down")
            condition_values['breakout_level'] = current['dc_lower']
            self.debug_counters['channel_breakouts'] += 1
            if self.debug_counters['channel_breakouts'] <= 5:
                print(f"[DEBUG] Channel BREAKOUT DOWN detected! Price: {current['close']:.2f} < Lower: {current['dc_lower']:.2f}")
        
        if not channel_breakout:
            return False, None, [], {}
        
        # 2. ADX 조건 (강한 추세)
        if current['adx'] > self.params['momentum_adx_min']:
            conditions_met.append("strong_adx")
            condition_values['adx'] = current['adx']
        else:
            return False, None, [], {}
        
        # 3. DI 방향성 확인
        di_diff = current['plus_di'] - current['minus_di']
        
        if direction == 'long' and di_diff > self.params['momentum_di_diff']:
            conditions_met.append("di_bullish")
            condition_values['di_diff'] = di_diff
        elif direction == 'short' and -di_diff > self.params['momentum_di_diff']:
            conditions_met.append("di_bearish")
            condition_values['di_diff'] = di_diff
        else:
            return False, None, [], {}
        
        # 4. 거래량 급증 (volume_ma 대신 20기간 평균 직접 계산)
        volume_ma = df_15m['volume'].iloc[current_index-20:current_index].mean()
        volume_ratio = current['volume'] / volume_ma if volume_ma > 0 else 0
        
        if volume_ratio > self.params['momentum_volume_spike']:
            conditions_met.append("volume_spike")
            condition_values['volume_ratio'] = volume_ratio
        else:
            return False, None, [], {}
        
        # 5. 모멘텀 가속 체크 (수정된 계산)
        # 단기 모멘텀 (5일 = 480개 15분봉)
        short_lookback = min(480, current_index - 50)  # 최소 50개는 남기고
        if current_index >= short_lookback + 50:
            short_momentum = (current['close'] - df_15m.iloc[current_index - short_lookback]['close']) / df_15m.iloc[current_index - short_lookback]['close'] * 100
        else:
            short_momentum = 0
        
        # 장기 모멘텀 (20일 = 1920개 15분봉, 또는 가능한 만큼)
        long_lookback = min(1920, current_index - 50)
        if current_index >= long_lookback + 50:
            long_momentum = (current['close'] - df_15m.iloc[current_index - long_lookback]['close']) / df_15m.iloc[current_index - long_lookback]['close'] * 100
        else:
            long_momentum = short_momentum
        
        # 가속 확인
        if direction == 'long':
            if short_momentum > 0 and long_momentum > 0 and short_momentum > long_momentum * self.params['momentum_acceleration']:
                conditions_met.append("momentum_acceleration")
                condition_values['short_momentum'] = short_momentum
                condition_values['long_momentum'] = long_momentum
            else:
                return False, None, [], {}
        else:  # short
            if short_momentum < 0 and long_momentum < 0 and abs(short_momentum) > abs(long_momentum) * self.params['momentum_acceleration']:
                conditions_met.append("momentum_acceleration")
                condition_values['short_momentum'] = short_momentum
                condition_values['long_momentum'] = long_momentum
            else:
                return False, None, [], {}
        
        # 모든 조건 충족 시 신호 발생
        if len(conditions_met) >= 5:  # 모든 조건 충족 필요
            self.debug_counters['momentum_signals'] += 1
            print(f"\n[DEBUG] 🚀 MOMENTUM SIGNAL #{self.debug_counters['momentum_signals']}!")
            print(f"  Direction: {direction}")
            print(f"  Conditions: {conditions_met}")
            print(f"  Values: {condition_values}")
            return True, direction, conditions_met, condition_values
        
        return False, None, [], {}
    
    def check_entry_signal_donchian(self, df_4h: pd.DataFrame, df_15m: pd.DataFrame, 
                                   current_index: int) -> Tuple[bool, str, List[str], Dict]:
        """기존 TFPE Donchian 기반 진입 신호 체크 (변경 없음)"""
        if current_index < 50:
            return False, None, [], {}
        
        current = df_15m.iloc[current_index]
        
        # ADX 필터
        if pd.isna(current.get('adx', np.nan)) or current['adx'] < self.params['adx_min']:
            return False, None, [], {}
        
        # 필수 값 체크
        required_values = ['momentum', 'rsi', 'ema_distance', 'swing_high', 'swing_low', 
                          'dc_trend', 'price_position']
        if any(pd.isna(current.get(val, np.nan)) for val in required_values):
            return False, None, [], {}
        
        # 4H Donchian 추세
        current_time = df_15m.index[current_index]
        aligned_time = current_time.floor('4H')
        
        if aligned_time not in df_4h.index:
            return False, None, [], {}
        
        dc_trend_4h = df_4h.loc[aligned_time, 'dc_trend']
        dc_width_4h = df_4h.loc[aligned_time, 'dc_width']
        
        # 15m 가격 위치
        price_position = current['price_position']
        
        # 풀백 5개 조건 체크
        conditions_met = []
        condition_values = {}
        direction = None
        
        # 1. 모멘텀 조건
        momentum_ok = current['momentum'] > self.params['min_momentum']
        condition_values['momentum'] = current['momentum']
        if momentum_ok:
            conditions_met.append("momentum")
        
        # 2. 피보나치 되돌림
        swing_high = current['swing_high']
        swing_low = current['swing_low']
        
        if swing_high > swing_low:
            price = current['close']
            
            if dc_trend_4h == 1:
                retracement = (swing_high - price) / (swing_high - swing_low)
                retracement_ok = self.params['fib_min'] <= retracement <= self.params['fib_max']
            else:
                retracement = (price - swing_low) / (swing_high - swing_low)
                retracement_ok = self.params['fib_min'] <= retracement <= self.params['fib_max']
            
            condition_values['fibonacci'] = retracement
            if retracement_ok:
                conditions_met.append("fibonacci")
        
        # 3. RSI 조건
        rsi = current['rsi']
        condition_values['rsi'] = rsi
        
        # Donchian 기반 유연한 진입
        if dc_trend_4h == 1:  # 상승 추세
            if price_position < self.params['price_position_low'] and rsi <= 40:
                conditions_met.append("rsi")
                direction = 'long'
            elif self.params['price_position_neutral_min'] <= price_position <= self.params['price_position_neutral_max'] and rsi <= 45:
                conditions_met.append("rsi")
                direction = 'long'
        else:  # 하락 추세
            if price_position > self.params['price_position_high'] and rsi >= 60:
                conditions_met.append("rsi")
                direction = 'short'
            elif self.params['price_position_neutral_min'] <= price_position <= self.params['price_position_neutral_max'] and rsi >= 55:
                conditions_met.append("rsi")
                direction = 'short'
        
        # 추세 약할 때 양방향 진입
        if dc_width_4h < 0.05:  # 채널 폭이 좁음 = 횡보
            if rsi < self.params['rsi_oversold']:
                direction = 'long'
                conditions_met.append("rsi_extreme")
            elif rsi > self.params['rsi_overbought']:
                direction = 'short'
                conditions_met.append("rsi_extreme")
        
        # 4. EMA 거리
        if current['ema_distance'] <= self.params['ema_distance_max']:
            conditions_met.append("ema_distance")
            condition_values['ema_distance'] = current['ema_distance']
        
        # 5. 거래량 스파이크
        if 'volume_ratio' in current and current['volume_ratio'] >= self.params['volume_spike']:
            conditions_met.append("volume")
            condition_values['volume'] = current['volume_ratio']
        elif 'volume' in current:
            # volume_ratio가 없으면 직접 계산
            volume_ma = df_15m['volume'].iloc[current_index-20:current_index].mean()
            volume_ratio = current['volume'] / volume_ma if volume_ma > 0 else 0
            if volume_ratio >= self.params['volume_spike']:
                conditions_met.append("volume")
                condition_values['volume'] = volume_ratio
        
        # 6. 가격 위치 보너스
        if (direction == 'long' and price_position < self.params['price_position_low']) or \
           (direction == 'short' and price_position > self.params['price_position_high']):
            conditions_met.append("price_position")
            condition_values['price_position'] = price_position
        
        # 신호 판단 - MDD가 높을 때는 조건 완화
        required_conditions = self.params['signal_threshold']
        if self.mdd_manager and self.mdd_manager.current_mdd >= self.params.get('mdd_level_2', 35) and self.mdd_manager.active_positions_count == 0:
            # 포지션이 없고 MDD가 높으면 조건 완화
            required_conditions = max(2, required_conditions - 1)
        
        if direction and len(conditions_met) >= required_conditions:
            return True, direction, conditions_met, condition_values
        
        return False, None, [], condition_values
    
    def check_hybrid_signals(self, df_4h: pd.DataFrame, df_15m: pd.DataFrame, 
                           current_index: int, current_position_size: float = 0) -> Dict:
        """
        Hybrid 신호 체크 - TFPE와 Momentum 모두 확인
        
        Returns:
            dict: {
                'signal': bool,
                'strategy_type': 'TFPE' or 'MOMENTUM',
                'direction': 'long' or 'short',
                'conditions': List[str],
                'condition_values': Dict,
                'position_size': float,
                'stop_loss_atr': float,
                'take_profit_atr': float,
                'market_regime': str
            }
        """
        # 시장 체제 확인
        market_regime = self.detect_market_regime(df_4h, df_15m, current_index)
        
        # 현재 총 포지션 크기 확인
        max_position = self.params['max_combined_position']
        if current_position_size >= max_position:
            return {'signal': False, 'reason': 'Max position size reached'}
        
        # 1. 강한 추세일 때는 Momentum 전략 우선
        if market_regime == 'STRONG_TREND':
            momentum_signal, momentum_dir, momentum_conditions, momentum_values = \
                self.check_momentum_signal(df_4h, df_15m, current_index)
            
            if momentum_signal:
                # Momentum 포지션 크기 계산 (남은 여유분 고려)
                available_size = max_position - current_position_size
                position_size = min(self.params['momentum_position_size'], available_size)
                
                return {
                    'signal': True,
                    'strategy_type': 'MOMENTUM',
                    'direction': momentum_dir,
                    'conditions': momentum_conditions,
                    'condition_values': momentum_values,
                    'position_size': position_size,
                    'stop_loss_atr': self.params['momentum_stop_loss_atr'],
                    'take_profit_atr': self.params['momentum_take_profit_atr'],
                    'trailing_enabled': self.params['momentum_trailing_enabled'],
                    'market_regime': market_regime
                }
        
        # 2. TFPE 신호 체크 (일반 시장)
        tfpe_signal, tfpe_dir, tfpe_conditions, tfpe_values = \
            self.check_entry_signal_donchian(df_4h, df_15m, current_index)
        
        if tfpe_signal:
            # TFPE 포지션 크기 계산
            available_size = max_position - current_position_size
            position_size = min(self.params['position_size'], available_size)
            
            # MDD 조정 적용
            if self.mdd_manager:
                mdd_restrictions = self.mdd_manager.check_mdd_restrictions()
                position_size *= mdd_restrictions['position_size_multiplier']
            
            return {
                'signal': True,
                'strategy_type': 'TFPE',
                'direction': tfpe_dir,
                'conditions': tfpe_conditions,
                'condition_values': tfpe_values,
                'position_size': position_size,
                'stop_loss_atr': self.params['stop_loss_atr'],
                'take_profit_atr': self.params['take_profit_atr'],
                'trailing_enabled': False,
                'market_regime': market_regime
            }
        
        # 3. Momentum 신호도 체크 (NORMAL 시장에서도)
        momentum_signal, momentum_dir, momentum_conditions, momentum_values = \
            self.check_momentum_signal(df_4h, df_15m, current_index)
        
        if momentum_signal:
            available_size = max_position - current_position_size
            position_size = min(self.params['momentum_position_size'], available_size)
            
            return {
                'signal': True,
                'strategy_type': 'MOMENTUM',
                'direction': momentum_dir,
                'conditions': momentum_conditions,
                'condition_values': momentum_values,
                'position_size': position_size,
                'stop_loss_atr': self.params['momentum_stop_loss_atr'],
                'take_profit_atr': self.params['momentum_take_profit_atr'],
                'trailing_enabled': self.params['momentum_trailing_enabled'],
                'market_regime': market_regime
            }
        
        return {
            'signal': False,
            'market_regime': market_regime
        }
    
    def print_debug_summary(self):
        """디버그 카운터 요약 출력"""
        print("\n" + "="*60)
        print("DEBUG SUMMARY")
        print("="*60)
        print(f"Market Regime Checks: {self.debug_counters['market_regime_checks']}")
        print(f"Strong Trend Count: {self.debug_counters['strong_trend_count']}")
        print(f"Momentum Strategy Checks: {self.debug_counters['momentum_checks']}")
        print(f"Channel Breakouts Detected: {self.debug_counters['channel_breakouts']}")
        print(f"Momentum Signals Generated: {self.debug_counters['momentum_signals']}")
        print("="*60)
