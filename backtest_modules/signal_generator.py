# backtest_modules/signal_generator.py
"""신호 생성 모듈"""

import pandas as pd
import numpy as np
from typing import Tuple, List, Dict


class SignalGenerator:
    """신호 생성 클래스"""
    
    def __init__(self, params: dict, mdd_manager=None):
        self.params = params
        self.mdd_manager = mdd_manager
    
    def check_entry_signal_donchian(self, df_4h: pd.DataFrame, df_15m: pd.DataFrame, 
                                   current_index: int) -> Tuple[bool, str, List[str], Dict]:
        """Donchian 기반 진입 신호 체크"""
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
        if current['volume_ratio'] >= self.params['volume_spike']:
            conditions_met.append("volume")
            condition_values['volume'] = current['volume_ratio']
        
        # 6. 가격 위치 보너스
        if (direction == 'long' and price_position < self.params['price_position_low']) or \
           (direction == 'short' and price_position > self.params['price_position_high']):
            conditions_met.append("price_position")
            condition_values['price_position'] = price_position
        
        # 신호 판단 - MDD가 높을 때는 조건 완화
        required_conditions = self.params['signal_threshold']
        if self.mdd_manager and self.mdd_manager.current_mdd >= self.params['mdd_level_2'] and self.mdd_manager.active_positions_count == 0:
            # 포지션이 없고 MDD가 높으면 조건 완화
            required_conditions = max(2, required_conditions - 1)
        
        if direction and len(conditions_met) >= required_conditions:
            return True, direction, conditions_met, condition_values
        
        return False, None, [], condition_values
