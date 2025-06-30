# backtest_modules/signal_generator_hybrid_flexible.py
"""
유연한 Hybrid Signal Generator - TFPE Pullback + Momentum Breakout
점수제 기반 모멘텀 신호 생성
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional, Dict, Any
from datetime import datetime


class FlexibleHybridSignalGenerator:
    """유연한 하이브리드 신호 생성기 - 점수제 기반"""
    
    def __init__(self, params: dict, debug: bool = True):
        self.params = params
        self.debug = debug
        self.last_signal_time = {}
        self.signal_stats = {
            'tfpe_signals': 0,
            'momentum_signals': 0,
            'tfpe_conditions_checked': 0,
            'momentum_conditions_checked': 0,
            'regime_checks': 0,
            'strong_trends_detected': 0,
            'channel_breakouts_detected': 0,
            'momentum_score_distribution': []
        }
    
    def detect_market_regime(self, current_4h_data: pd.Series, current_15m_data: pd.Series) -> str:
        """시장 체제 감지 - 개선된 버전"""
        self.signal_stats['regime_checks'] += 1
        
        # Donchian Channel 기반 체제 감지
        dc_width = current_4h_data.get('dc_width', current_4h_data.get('channel_width_pct', np.nan))
        price_pos = current_15m_data.get('price_position', 0.5)
        adx = current_15m_data.get('adx', 20)
        
        # NaN 처리
        if pd.isna(dc_width):
            # 대체 계산: (high - low) / close
            if not pd.isna(current_4h_data.get('high')) and not pd.isna(current_4h_data.get('low')):
                dc_width = (current_4h_data['high'] - current_4h_data['low']) / current_4h_data['close']
            else:
                dc_width = 0.05  # 기본값
        
        # 강한 추세 감지 (완화된 조건)
        strong_trend_threshold = self.params.get('strong_trend_channel_width', 0.03)  # 3%로 완화
        
        if self.debug:
            print(f"\n[DEBUG] Market Regime Detection:")
            print(f"  DC Width: {dc_width:.3f} (threshold: {strong_trend_threshold})")
            print(f"  Price Position: {price_pos:.3f}")
            print(f"  ADX: {adx:.1f}")
        
        # 체제 판단
        if dc_width > strong_trend_threshold and adx > 25:
            self.signal_stats['strong_trends_detected'] += 1
            if price_pos > 0.7:
                return 'STRONG_UPTREND'
            elif price_pos < 0.3:
                return 'STRONG_DOWNTREND'
            else:
                return 'STRONG_TREND'
        elif dc_width < 0.02:  # 매우 좁은 채널
            return 'RANGE_BOUND'
        else:
            return 'NORMAL'
    
    def check_momentum_signal(self, df_15m: pd.DataFrame, df_4h: pd.DataFrame, 
                            current_index: int) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """점수제 기반 모멘텀 신호 체크"""
        self.signal_stats['momentum_conditions_checked'] += 1
        
        try:
            current_15m = df_15m.iloc[current_index]
            
            # 4시간봉 데이터 정렬
            current_time = df_15m.index[current_index]
            aligned_time = current_time.floor('4h')
            
            if aligned_time not in df_4h.index:
                return False, None, {}
            
            current_4h = df_4h.loc[aligned_time]
            
            # 시장 체제 확인
            regime = self.detect_market_regime(current_4h, current_15m)
            
            if regime not in ['STRONG_TREND', 'STRONG_UPTREND', 'STRONG_DOWNTREND']:
                return False, None, {}
            
            # 점수제 시스템 초기화
            score = 0
            max_score = 0
            conditions_met = []
            score_details = {}
            
            # 1. 채널 돌파 (필수 조건 - 40점)
            price = current_15m['close']
            dc_upper = current_15m.get('dc_upper', np.nan)
            dc_lower = current_15m.get('dc_lower', np.nan)
            
            channel_break = False
            direction = None
            
            if not pd.isna(dc_upper) and not pd.isna(dc_lower):
                # 상단 돌파 체크
                if price > dc_upper * 0.998:  # 0.2% 버퍼
                    recent_highs = df_15m['high'].iloc[current_index-10:current_index]
                    if len(recent_highs) > 0 and price > recent_highs.max() * 0.995:
                        channel_break = True
                        direction = 'long'
                        score += 40
                        conditions_met.append('channel_breakout_up')
                        self.signal_stats['channel_breakouts_detected'] += 1
                
                # 하단 돌파 체크
                elif price < dc_lower * 1.002:  # 0.2% 버퍼
                    recent_lows = df_15m['low'].iloc[current_index-10:current_index]
                    if len(recent_lows) > 0 and price < recent_lows.min() * 1.005:
                        channel_break = True
                        direction = 'short'
                        score += 40
                        conditions_met.append('channel_breakout_down')
                        self.signal_stats['channel_breakouts_detected'] += 1
            
            max_score += 40
            score_details['channel_break'] = channel_break
            
            if not channel_break:
                # 채널 돌파가 없으면 모멘텀 신호 없음
                return False, None, {'score': score, 'max_score': max_score}
            
            # 2. ADX 조건 (20점)
            adx = current_15m.get('adx', 0)
            adx_min = self.params.get('momentum_adx_min', 20)  # 완화된 조건
            
            if adx >= adx_min:
                adx_score = min(20, (adx - adx_min) / 10 * 20)  # 점진적 점수
                score += adx_score
                conditions_met.append(f'adx_{adx:.1f}')
                score_details['adx_score'] = adx_score
            max_score += 20
            
            # 3. DI 차이 (15점)
            plus_di = current_15m.get('plus_di', 0)
            minus_di = current_15m.get('minus_di', 0)
            di_diff = abs(plus_di - minus_di)
            di_diff_min = self.params.get('momentum_di_diff', 3)  # 완화된 조건
            
            if di_diff >= di_diff_min:
                di_score = min(15, (di_diff - di_diff_min) / 10 * 15)
                score += di_score
                conditions_met.append(f'di_diff_{di_diff:.1f}')
                score_details['di_score'] = di_score
                
                # 방향 확인
                if (direction == 'long' and plus_di < minus_di) or \
                   (direction == 'short' and plus_di > minus_di):
                    # 방향이 반대면 점수 감점
                    score -= 10
                    score_details['di_direction_penalty'] = -10
            max_score += 15
            
            # 4. 거래량 스파이크 (15점)
            volume_ratio = current_15m.get('volume_ratio', 1.0)
            volume_spike = self.params.get('momentum_volume_spike', 1.2)  # 완화된 조건
            
            if volume_ratio >= volume_spike:
                volume_score = min(15, (volume_ratio - volume_spike) / 0.5 * 15)
                score += volume_score
                conditions_met.append(f'volume_{volume_ratio:.2f}')
                score_details['volume_score'] = volume_score
            max_score += 15
            
            # 5. 가격 가속도 (10점)
            acceleration = current_15m.get('momentum_acceleration', 0)
            accel_min = self.params.get('momentum_acceleration', 1.1)  # 완화된 조건
            
            if abs(acceleration) >= accel_min:
                accel_score = min(10, abs(acceleration) / 2 * 10)
                score += accel_score
                conditions_met.append(f'accel_{acceleration:.2f}')
                score_details['acceleration_score'] = accel_score
            max_score += 10
            
            # 점수 기록
            score_percentage = (score / max_score * 100) if max_score > 0 else 0
            self.signal_stats['momentum_score_distribution'].append(score_percentage)
            
            # 디버그 출력
            if self.debug:
                print(f"\n[DEBUG] Momentum Signal Check:")
                print(f"  Time: {current_time}")
                print(f"  Regime: {regime}")
                print(f"  Channel Break: {channel_break} ({direction})")
                print(f"  Score: {score}/{max_score} ({score_percentage:.1f}%)")
                print(f"  Conditions: {conditions_met}")
                print(f"  Details: {score_details}")
            
            # 최소 점수 임계값 (60%)
            min_score_threshold = max_score * 0.6
            
            if score >= min_score_threshold:
                # 추가 방향 확인
                if direction == 'long' and regime == 'STRONG_DOWNTREND':
                    return False, None, {'score': score, 'max_score': max_score, 'reason': 'wrong_direction'}
                elif direction == 'short' and regime == 'STRONG_UPTREND':
                    return False, None, {'score': score, 'max_score': max_score, 'reason': 'wrong_direction'}
                
                self.signal_stats['momentum_signals'] += 1
                
                return True, direction, {
                    'score': score,
                    'max_score': max_score,
                    'score_percentage': score_percentage,
                    'conditions_met': conditions_met,
                    'regime': regime,
                    'adx': adx,
                    'di_diff': di_diff,
                    'volume_ratio': volume_ratio,
                    'acceleration': acceleration
                }
            
            return False, None, {'score': score, 'max_score': max_score}
            
        except Exception as e:
            if self.debug:
                print(f"[ERROR] Momentum signal check failed: {e}")
                import traceback
                traceback.print_exc()
            return False, None, {}
    
    def check_tfpe_signal(self, df_15m: pd.DataFrame, df_4h: pd.DataFrame, 
                         current_index: int) -> Tuple[bool, Optional[str]]:
        """TFPE Pullback 신호 체크 (기존 로직 유지)"""
        self.signal_stats['tfpe_conditions_checked'] += 1
        
        try:
            current = df_15m.iloc[current_index]
            
            # 4시간봉 추세 확인
            current_time = df_15m.index[current_index]
            aligned_time = current_time.floor('4h')
            
            if aligned_time not in df_4h.index:
                return False, None
            
            trend_4h = df_4h.loc[aligned_time, 'dc_trend']
            
            conditions_met = []
            
            # 1. 모멘텀 조건
            if current.get('momentum', 0) > self.params['min_momentum']:
                conditions_met.append("momentum")
            
            # 2. RSI 조건
            rsi = current.get('rsi', 50)
            price_pos = current.get('price_position', 0.5)
            
            if trend_4h == 1:  # 상승 추세
                if (price_pos < 0.3 and rsi <= 40) or \
                   (0.4 <= price_pos <= 0.6 and rsi <= 45):
                    conditions_met.append("rsi")
            else:  # 하락 추세
                if (price_pos > 0.7 and rsi >= 60) or \
                   (0.4 <= price_pos <= 0.6 and rsi >= 55):
                    conditions_met.append("rsi")
            
            # 3. EMA 거리
            if current.get('ema_distance', 1.0) <= self.params['ema_distance_max']:
                conditions_met.append("ema_distance")
            
            # 4. 거래량
            if current.get('volume_ratio', 0) >= self.params['volume_spike']:
                conditions_met.append("volume")
            
            # 5. 스윙 포인트 (Fibonacci)
            if 'swing_high' in current and 'swing_low' in current:
                swing_high = current['swing_high']
                swing_low = current['swing_low']
                
                if not pd.isna(swing_high) and not pd.isna(swing_low) and swing_high > swing_low:
                    price = current['close']
                    
                    if trend_4h == 1:
                        retracement = (swing_high - price) / (swing_high - swing_low)
                    else:
                        retracement = (price - swing_low) / (swing_high - swing_low)
                    
                    if 0.382 <= retracement <= 0.786:
                        conditions_met.append("fibonacci")
            
            # ADX 필터
            if current.get('adx', 0) < self.params['adx_min']:
                return False, None
            
            # 신호 판단
            if len(conditions_met) >= self.params['signal_threshold']:
                direction = 'long' if trend_4h == 1 else 'short'
                
                # 쿨다운 체크
                symbol = 'BTCUSDT'  # 또는 동적으로 결정
                if symbol in self.last_signal_time:
                    time_since_last = (current_time - self.last_signal_time[symbol]).total_seconds() / 3600
                    if time_since_last < self.params['min_signal_interval']:
                        return False, None
                
                self.last_signal_time[symbol] = current_time
                self.signal_stats['tfpe_signals'] += 1
                
                if self.debug:
                    print(f"\n[TFPE Signal] {direction.upper()} - Conditions: {conditions_met}")
                
                return True, direction
            
            return False, None
            
        except Exception as e:
            if self.debug:
                print(f"[ERROR] TFPE signal check failed: {e}")
            return False, None
    
    def check_hybrid_signals(self, df_15m: pd.DataFrame, df_4h: pd.DataFrame, 
                           current_index: int) -> Dict[str, Any]:
        """통합 신호 체크"""
        results = {
            'tfpe': {'signal': False, 'direction': None},
            'momentum': {'signal': False, 'direction': None, 'details': {}}
        }
        
        # TFPE 신호 체크
        tfpe_signal, tfpe_direction = self.check_tfpe_signal(df_15m, df_4h, current_index)
        if tfpe_signal:
            results['tfpe'] = {'signal': True, 'direction': tfpe_direction}
        
        # 모멘텀 신호 체크
        momentum_signal, momentum_direction, momentum_details = self.check_momentum_signal(
            df_15m, df_4h, current_index
        )
        if momentum_signal:
            results['momentum'] = {
                'signal': True, 
                'direction': momentum_direction,
                'details': momentum_details
            }
        
        return results
    
    def get_statistics(self) -> Dict[str, Any]:
        """신호 생성 통계"""
        stats = self.signal_stats.copy()
        
        # 점수 분포 통계
        if stats['momentum_score_distribution']:
            scores = stats['momentum_score_distribution']
            stats['momentum_avg_score'] = np.mean(scores)
            stats['momentum_max_score'] = np.max(scores)
            stats['momentum_min_score'] = np.min(scores)
            stats['momentum_scores_above_60'] = sum(1 for s in scores if s >= 60)
        
        return stats
