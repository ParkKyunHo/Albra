# tfpe_donchian_hybrid_main_fixed.py
"""
TFPE + Momentum Hybrid 전략 - 개선된 버전
유연한 모멘텀 신호 + 개선된 데이터 처리
"""

import pandas as pd
import numpy as np
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
import warnings
import sys
import os

# 모듈 경로 추가
sys.path.append(os.path.join(os.path.dirname(__file__), 'backtest_modules'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'backtest_modules', 'fixed'))

# 개선된 모듈 임포트
from backtest_modules.mdd_manager import MDDManager
from backtest_modules.fixed.data_fetcher_fixed import DataFetcherFixed
from backtest_modules.signal_generator_hybrid_flexible import FlexibleHybridSignalGenerator
from backtest_modules.visualizer import Visualizer

warnings.filterwarnings('ignore')


class TFPEMomentumHybridStrategyFixed:
    """개선된 TFPE + Momentum Hybrid 전략"""
    
    def __init__(self, initial_capital: float = 10000):
        self.initial_capital = initial_capital
        
        # Trading fees
        self.fees = {
            'taker': 0.0004,
            'funding_rate': 0.0001
        }
        
        # 전략 파라미터 (유연한 모멘텀 조건)
        self.params = {
            # 기본 설정
            'leverage': 15,
            'position_size': 24,  # TFPE 포지션 크기
            
            # Donchian Channel
            'dc_period': 20,
            
            # TFPE 손절/익절
            'stop_loss_atr': 1.5,
            'take_profit_atr': 4.0,
            
            # 개선된 MDD 관리 파라미터
            'max_allowed_mdd': 40.0,
            'mdd_recovery_threshold': 15.0,
            
            # MDD 단계별 포지션 크기 조정
            'mdd_level_1': 30.0,
            'mdd_level_1_size': 0.7,
            'mdd_level_2': 35.0,
            'mdd_level_2_size': 0.5,
            'mdd_level_3': 40.0,
            'mdd_level_3_size': 0.3,
            'mdd_level_4': 50.0,
            'mdd_level_4_size': 0.1,
            
            # 회복 메커니즘
            'mdd_recovery_mode': True,
            'recovery_win_threshold': 3,
            'recovery_size_increment': 0.1,
            'max_recovery_size': 1.0,
            
            # 안전장치
            'mdd_emergency_stop': 60.0,
            'force_trade_if_no_position': True,
            
            # TFPE 진입 조건
            'adx_min': 25,
            'signal_threshold': 3,
            'min_momentum': 2.0,
            'rsi_oversold': 25,
            'rsi_overbought': 75,
            'volume_spike': 1.5,
            'ema_distance_max': 0.015,
            
            # 피보나치
            'fib_min': 0.382,
            'fib_max': 0.786,
            
            # 기타
            'swing_period': 20,
            'momentum_lookback': 20,
            'min_signal_interval': 4,
            
            # 가격 위치 임계값
            'price_position_high': 0.7,
            'price_position_low': 0.3,
            'price_position_neutral_min': 0.4,
            'price_position_neutral_max': 0.6,
            
            # === 모멘텀 전략 파라미터 (유연하게 조정) ===
            'momentum_position_size': 15,  # 모멘텀 포지션 크기
            'momentum_stop_loss_atr': 2.0,
            'momentum_take_profit_atr': 6.0,
            
            # 트레일링 스톱
            'momentum_trailing_enabled': True,
            'momentum_trailing_start': 1.5,  # 1.5 ATR 수익시 시작
            'momentum_trailing_step': 0.5,   # 0.5 ATR씩 추적
            
            # 모멘텀 진입 조건 (유연하게)
            'momentum_adx_min': 20,          # 30 → 20
            'momentum_di_diff': 3,           # 10 → 3
            'momentum_volume_spike': 1.2,    # 2.0 → 1.2
            'momentum_acceleration': 1.0,    # 1.5 → 1.0
            
            # 강한 추세 감지 (완화)
            'strong_trend_channel_width': 0.03,  # 0.08 → 0.03
            'strong_trend_price_extreme': 0.25,  # 0.1 → 0.25
            
            # 최대 통합 포지션
            'max_combined_position': 30,    # TFPE + Momentum 합계 최대 30%
            
            # === 200 EMA 필터 파라미터 ===
            'use_ema200_filter': True,       # 200 EMA 필터 활성화
            'ema200_bias_multiplier': 2.0,   # 편향에 따른 포지션 크기 배수
            'ema200_strong_distance': 5.0,   # 강한 추세 판단 거리 (%)
            'ema200_neutral_zone': 1.0,      # 중립 구간 (EMA ±1%)
        }
        
        # 모듈 초기화 (개선된 버전 사용)
        self.mdd_manager = MDDManager(self.params)
        self.mdd_manager.peak_capital = initial_capital
        self.data_fetcher = DataFetcherFixed(use_cache=True)  # 개선된 버전
        self.signal_generator = FlexibleHybridSignalGenerator(self.params, debug=False)  # 유연한 버전
        self.visualizer = Visualizer(self.params)
        
        # Data storage
        self.df_4h = None
        self.df_15m = None
        self.trades = []
        self.condition_stats = defaultdict(lambda: {'triggered': 0, 'wins': 0})
        self.mdd_history = []
        
        # 전략별 통계
        self.strategy_stats = {
            'TFPE': {'trades': 0, 'wins': 0, 'total_pnl': 0},
            'MOMENTUM': {'trades': 0, 'wins': 0, 'total_pnl': 0}
        }
        
        # 시장 체제별 통계
        self.regime_stats = {
            'STRONG_TREND': {'trades': 0, 'wins': 0},
            'STRONG_UPTREND': {'trades': 0, 'wins': 0},
            'STRONG_DOWNTREND': {'trades': 0, 'wins': 0},
            'NORMAL': {'trades': 0, 'wins': 0},
            'RANGE_BOUND': {'trades': 0, 'wins': 0}
        }
        
        # 200 EMA 필터 통계
        self.ema200_stats = {
            'bullish_trades': 0,
            'bullish_wins': 0,
            'bearish_trades': 0,
            'bearish_wins': 0,
            'size_adjustments': 0,
            'strong_trend_trades': 0
        }
        
        # Choppy Market Filter 초기화
        self.choppy_filter_enabled = True
        self.choppy_market_stats = {
            'filtered_signals': 0,
            'choppy_periods': 0,
            'total_periods': 0
        }
        
    def get_market_bias_adjusted_position_size(self, base_size: float, direction: str, 
                                               df_4h: pd.DataFrame, current_time) -> float:
        """200 EMA 기반 시장 편향에 따른 포지션 크기 조정
        
        Args:
            base_size: 기본 포지션 크기 (%)
            direction: 'long' or 'short'
            df_4h: 4시간봉 데이터프레임
            current_time: 현재 시간
            
        Returns:
            조정된 포지션 크기 (%)
        """
        if not self.params['use_ema200_filter']:
            return base_size
        
        # 현재 시간에 가장 가까운 4H 캔들 찾기
        try:
            # 4시간봉으로 정렬
            aligned_time = current_time.floor('4h')
            
            # 해당 시간이 없으면 이전 캔들 사용
            if aligned_time in df_4h.index:
                candle_4h = df_4h.loc[aligned_time]
            else:
                # 이전 캔들들 중 가장 가까운 것 찾기
                mask = df_4h.index <= current_time
                if mask.any():
                    candle_4h = df_4h[mask].iloc[-1]
                else:
                    # 데이터가 없으면 기본 크기 반환
                    return base_size
            
            market_bias = candle_4h.get('market_bias', 0)
            ema200_distance = candle_4h.get('ema200_distance', 0)
            
            # 중립 구간 체크 (EMA200 ±1%)
            if abs(ema200_distance) < self.params['ema200_neutral_zone']:
                # 중립 구간에서는 기본 크기 사용
                return base_size
            
            # 시장 편향에 따른 조정
            if market_bias > 0:  # 상승 편향 (Close > EMA200)
                if direction == 'long':
                    # 상승 편향에서 롱 포지션은 크기 증가
                    if abs(ema200_distance) > self.params['ema200_strong_distance']:
                        # 강한 상승 추세
                        adjusted_size = base_size * self.params['ema200_bias_multiplier']
                    else:
                        # 일반 상승 추세
                        adjusted_size = base_size * 1.5
                else:  # short
                    # 상승 편향에서 숏 포지션은 크기 감소
                    if abs(ema200_distance) > self.params['ema200_strong_distance']:
                        # 강한 상승 추세에서는 숏 크기 대폭 감소
                        adjusted_size = base_size * 0.5
                    else:
                        # 일반 상승 추세
                        adjusted_size = base_size * 0.75
            else:  # 하락 편향 (Close < EMA200)
                if direction == 'short':
                    # 하락 편향에서 숏 포지션은 크기 증가
                    if abs(ema200_distance) > self.params['ema200_strong_distance']:
                        # 강한 하락 추세
                        adjusted_size = base_size * self.params['ema200_bias_multiplier']
                    else:
                        # 일반 하락 추세
                        adjusted_size = base_size * 1.5
                else:  # long
                    # 하락 편향에서 롱 포지션은 크기 감소
                    if abs(ema200_distance) > self.params['ema200_strong_distance']:
                        # 강한 하락 추세에서는 롱 크기 대폭 감소
                        adjusted_size = base_size * 0.5
                    else:
                        # 일반 하락 추세
                        adjusted_size = base_size * 0.75
            
            # 최대/최소 제한
            max_size = base_size * self.params['ema200_bias_multiplier']
            min_size = base_size * 0.5
            adjusted_size = max(min_size, min(adjusted_size, max_size))
            
            # 디버그 출력 (선택적)
            if abs(ema200_distance) > self.params['ema200_neutral_zone']:
                bias_str = "상승" if market_bias > 0 else "하락"
                print(f"  📊 200 EMA Filter: {bias_str} 편향 (거리: {ema200_distance:.1f}%), "
                      f"{direction.upper()} {base_size:.0f}% → {adjusted_size:.0f}%")
            
            return adjusted_size
            
        except Exception as e:
            print(f"⚠️ Error in market bias adjustment: {e}")
            return base_size
    
    def check_choppy_market(self, df: pd.DataFrame, index: int) -> bool:
        """횡보장(Choppy Market) 감지
        
        Returns:
            True if market is choppy (거래 차단), False otherwise
        """
        if not self.choppy_filter_enabled or index < 40:
            return False
            
        # 최근 20개 캔들 데이터
        recent_data = df.iloc[index-20:index]
        
        # 1. Efficiency Ratio 계산 (가격 움직임의 효율성)
        period = 20
        net_change = abs(recent_data['close'].iloc[-1] - recent_data['close'].iloc[0])
        total_change = recent_data['close'].diff().abs().sum()
        
        if total_change == 0:
            efficiency_ratio = 0
        else:
            efficiency_ratio = net_change / total_change
        
        # 2. ADX 값 확인
        current_adx = recent_data['adx'].iloc[-1] if 'adx' in recent_data.columns else 25
        
        # 3. Bollinger Band Width
        if 'bb_upper' in recent_data.columns and 'bb_lower' in recent_data.columns:
            bb_upper = recent_data['bb_upper'].iloc[-1]
            bb_lower = recent_data['bb_lower'].iloc[-1]
            bb_middle = recent_data['bb_middle'].iloc[-1]
            bb_width = (bb_upper - bb_lower) / bb_middle if bb_middle > 0 else 0
        else:
            bb_width = 0.05  # 기본값
        
        # 4. 가격 진폭 (High-Low Range)
        recent_range = (recent_data['high'].max() - recent_data['low'].min()) / recent_data['close'].mean()
        
        # 5. 거래량 변화율
        volume_avg = recent_data['volume'].mean()
        volume_std = recent_data['volume'].std()
        volume_cv = volume_std / volume_avg if volume_avg > 0 else 0
        
        # 횡보장 판단 기준
        is_choppy = False
        choppy_reasons = []
        
        # 극심한 횡보: 모든 조건 충족
        if efficiency_ratio < 0.2 and current_adx < 15 and bb_width < 0.02:
            is_choppy = True
            choppy_reasons.append(f"EXTREME: ER={efficiency_ratio:.2f}, ADX={current_adx:.1f}, BB={bb_width:.3f}")
        
        # 일반 횡보: 2개 이상 조건 충족
        choppy_conditions = 0
        if efficiency_ratio < 0.3:
            choppy_conditions += 1
            choppy_reasons.append(f"LowER={efficiency_ratio:.2f}")
        if current_adx < 20:
            choppy_conditions += 1
            choppy_reasons.append(f"LowADX={current_adx:.1f}")
        if bb_width < 0.03:
            choppy_conditions += 1
            choppy_reasons.append(f"NarrowBB={bb_width:.3f}")
        if recent_range < 0.03:
            choppy_conditions += 1
            choppy_reasons.append(f"LowRange={recent_range:.3f}")
        if volume_cv < 0.3:  # 거래량 변화가 적음
            choppy_conditions += 1
            choppy_reasons.append(f"LowVolVar={volume_cv:.2f}")
        
        if choppy_conditions >= 3:
            is_choppy = True
        
        # 통계 업데이트
        self.choppy_market_stats['total_periods'] += 1
        if is_choppy:
            self.choppy_market_stats['choppy_periods'] += 1
            if len(choppy_reasons) > 0:
                # 디버그 출력 (선택적)
                # print(f"  🚫 Choppy market detected: {', '.join(choppy_reasons)}")
                pass
        
        return is_choppy
    
    def calculate_dynamic_stop_loss(self, entry_price: float, direction: str, 
                                   current_atr: float, df: pd.DataFrame, 
                                   index: int, strategy_type: str = 'TFPE') -> float:
        """시장 구조 기반 동적 손절 계산
        
        Args:
            entry_price: 진입 가격
            direction: 'long' or 'short'
            current_atr: 현재 ATR
            df: 가격 데이터프레임
            index: 현재 인덱스
            strategy_type: 'TFPE' or 'MOMENTUM'
            
        Returns:
            동적으로 계산된 손절 가격
        """
        # 전략별 기본 ATR 배수
        if strategy_type == 'TFPE':
            base_atr_multiplier = self.params['stop_loss_atr']
        else:  # MOMENTUM
            base_atr_multiplier = self.params['momentum_stop_loss_atr']
        
        # 기본 ATR 손절
        base_stop_distance = current_atr * base_atr_multiplier
        
        # 최근 20개 캔들로 지지/저항 레벨 찾기
        lookback = min(20, index)
        recent_data = df.iloc[index-lookback:index]
        
        if direction == 'long':
            # Long 포지션: 최근 저점들 중에서 지지선 찾기
            recent_lows = recent_data['low'].values
            
            # 1. 최근 스윙 로우 찾기 (local minima)
            swing_lows = []
            for i in range(1, len(recent_lows)-1):
                if recent_lows[i] < recent_lows[i-1] and recent_lows[i] < recent_lows[i+1]:
                    swing_lows.append(recent_lows[i])
            
            # 2. 주요 지지선 계산
            if swing_lows:
                # 가장 가까운 지지선
                support_levels = [s for s in swing_lows if s < entry_price]
                if support_levels:
                    nearest_support = max(support_levels)
                    # 지지선 아래 여유 마진 (0.2%)
                    structure_stop = nearest_support * 0.998
                else:
                    # 지지선이 없으면 최근 최저가 사용
                    structure_stop = recent_data['low'].min() * 0.995
            else:
                structure_stop = recent_data['low'].min() * 0.995
            
            # 기본 ATR 손절과 구조적 손절 중 더 가까운 것 선택 (더 보수적)
            atr_stop = entry_price - base_stop_distance
            dynamic_stop = max(atr_stop, structure_stop)
            
            # 최소 손절 거리 보장 (0.5%)
            min_stop = entry_price * 0.995
            dynamic_stop = min(dynamic_stop, min_stop)
            
        else:  # short
            # Short 포지션: 최근 고점들 중에서 저항선 찾기
            recent_highs = recent_data['high'].values
            
            # 1. 최근 스윙 하이 찾기 (local maxima)
            swing_highs = []
            for i in range(1, len(recent_highs)-1):
                if recent_highs[i] > recent_highs[i-1] and recent_highs[i] > recent_highs[i+1]:
                    swing_highs.append(recent_highs[i])
            
            # 2. 주요 저항선 계산
            if swing_highs:
                # 가장 가까운 저항선
                resistance_levels = [r for r in swing_highs if r > entry_price]
                if resistance_levels:
                    nearest_resistance = min(resistance_levels)
                    # 저항선 위 여유 마진 (0.2%)
                    structure_stop = nearest_resistance * 1.002
                else:
                    # 저항선이 없으면 최근 최고가 사용
                    structure_stop = recent_data['high'].max() * 1.005
            else:
                structure_stop = recent_data['high'].max() * 1.005
            
            # 기본 ATR 손절과 구조적 손절 중 더 가까운 것 선택 (더 보수적)
            atr_stop = entry_price + base_stop_distance
            dynamic_stop = min(atr_stop, structure_stop)
            
            # 최소 손절 거리 보장 (0.5%)
            min_stop = entry_price * 1.005
            dynamic_stop = max(dynamic_stop, min_stop)
        
        return dynamic_stop
    
    def update_trailing_stop(self, position: Dict, current_price: float, current_atr: float) -> float:
        """트레일링 스톱 업데이트 (Momentum 전략용)"""
        if not position.get('trailing_enabled', False):
            return position['stop_loss']
        
        entry_price = position['entry_price']
        current_stop = position['stop_loss']
        direction = position['direction']
        
        # 수익 계산
        if direction == 'long':
            profit_atr = (current_price - entry_price) / current_atr
            
            # 1.5 ATR 수익 이상일 때 트레일링 시작
            if profit_atr >= self.params['momentum_trailing_start']:
                # 새로운 스톱 레벨 계산
                new_stop = current_price - (current_atr * self.params['momentum_trailing_step'])
                # 기존 스톱보다 높을 때만 업데이트
                if new_stop > current_stop:
                    return new_stop
        else:  # short
            profit_atr = (entry_price - current_price) / current_atr
            
            if profit_atr >= self.params['momentum_trailing_start']:
                new_stop = current_price + (current_atr * self.params['momentum_trailing_step'])
                if new_stop < current_stop:
                    return new_stop
        
        return current_stop
    
    def run_backtest(self, start_date: str = None, end_date: str = None) -> Dict:
        """백테스트 실행 with 개선된 Hybrid 전략"""
        print("\n🚀 Running Enhanced TFPE + Momentum Hybrid backtest...")
        print("   • TFPE: Pullback strategy (24% position)")
        print("   • Momentum: Breakout strategy (15% position)")
        print("   • Max combined position: 30%")
        print("   • Enhanced data handling with NaN protection")
        print("   • Flexible momentum scoring system (60% threshold)")
        print()
        
        capital = self.initial_capital
        equity_curve = []
        self.trades = []
        self.mdd_history = []
        self.condition_stats = defaultdict(lambda: {'triggered': 0, 'wins': 0})
        
        # 전략별 통계 초기화
        self.strategy_stats = {
            'TFPE': {'trades': 0, 'wins': 0, 'total_pnl': 0, 'positions': []},
            'MOMENTUM': {'trades': 0, 'wins': 0, 'total_pnl': 0, 'positions': []}
        }
        
        # 현재 포지션들
        current_positions = []
        last_signal_times = {'TFPE': None, 'MOMENTUM': None}
        trades_skipped_by_mdd = 0
        trades_with_reduced_size = 0
        
        total_candles = len(self.df_15m)
        
        for i in range(100, total_candles):
            if i % 1000 == 0:
                progress = (i - 100) / (total_candles - 100) * 100
                print(f"  Progress: {progress:.1f}%", end='\r')
            
            current_time = self.df_15m.index[i]
            current_price = self.df_15m.iloc[i]['close']
            current_atr = self.df_15m.iloc[i]['atr']
            
            # 현재 총 포지션 크기 계산
            total_position_size = sum(pos['actual_position_size'] for pos in current_positions)
            
            # MDD 관리
            self.mdd_manager.active_positions_count = len(current_positions)
            if self.mdd_manager.active_positions_count == 0:
                self.mdd_manager.time_without_position += 1
            else:
                self.mdd_manager.time_without_position = 0
            
            # Calculate current MDD
            current_mdd = self.mdd_manager.calculate_current_mdd(capital)
            self.mdd_history.append({
                'time': current_time,
                'mdd': current_mdd,
                'capital': capital,
                'peak': self.mdd_manager.peak_capital,
                'positions': len(current_positions),
                'total_position_size': total_position_size,
                'recovery_multiplier': self.mdd_manager.current_recovery_multiplier
            })
            
            # Check MDD restrictions
            mdd_restrictions = self.mdd_manager.check_mdd_restrictions()
            
            # 포지션 청산 체크
            positions_to_remove = []
            for idx, pos in enumerate(current_positions):
                candles_held = i - pos['entry_index']
                hours_held = candles_held * 0.25
                
                # 트레일링 스톱 업데이트 (Momentum 전략만)
                if pos.get('trailing_enabled', False):
                    pos['stop_loss'] = self.update_trailing_stop(pos, current_price, current_atr)
                
                # Exit conditions
                exit_triggered = False
                exit_type = None
                
                # Force close only in emergency
                if mdd_restrictions['force_close_positions']:
                    exit_triggered, exit_type = True, 'MDD_EMERGENCY'
                else:
                    if pos['direction'] == 'long':
                        if current_price <= pos['stop_loss']:
                            exit_triggered, exit_type = True, 'SL'
                        elif current_price >= pos['take_profit']:
                            exit_triggered, exit_type = True, 'TP'
                    else:
                        if current_price >= pos['stop_loss']:
                            exit_triggered, exit_type = True, 'SL'
                        elif current_price <= pos['take_profit']:
                            exit_triggered, exit_type = True, 'TP'
                
                if exit_triggered:
                    # Calculate PnL
                    if pos['direction'] == 'long':
                        pnl_pct = (current_price - pos['entry_price']) / pos['entry_price'] * 100
                    else:
                        pnl_pct = (pos['entry_price'] - current_price) / pos['entry_price'] * 100
                    
                    # Apply position size and leverage
                    actual_position_size = pos['actual_position_size']
                    leverage = self.params['leverage']
                    gross_pnl_pct = pnl_pct * leverage * (actual_position_size / 100)
                    
                    # Fees
                    days_held = hours_held / 24
                    trading_fees_pct = (actual_position_size / 100) * leverage * self.fees['taker'] * 2
                    funding_periods = max(1, int(days_held * 3))
                    funding_fees_pct = (actual_position_size / 100) * leverage * self.fees['funding_rate'] * funding_periods
                    total_fees_pct = trading_fees_pct + funding_fees_pct
                    
                    net_pnl_pct = gross_pnl_pct - total_fees_pct
                    capital *= (1 + net_pnl_pct / 100)
                    
                    # Update recovery status
                    trade_won = net_pnl_pct > 0
                    self.mdd_manager.update_recovery_status(trade_won)
                    
                    # 전략별 통계 업데이트
                    strategy_type = pos.get('strategy_type', 'TFPE')
                    self.strategy_stats[strategy_type]['trades'] += 1
                    if trade_won:
                        self.strategy_stats[strategy_type]['wins'] += 1
                    self.strategy_stats[strategy_type]['total_pnl'] += net_pnl_pct
                    
                    # 200 EMA 통계 업데이트
                    market_bias = pos.get('market_bias', 0)
                    ema200_distance = pos.get('ema200_distance', 0)
                    if market_bias > 0:
                        self.ema200_stats['bullish_trades'] += 1
                        if trade_won:
                            self.ema200_stats['bullish_wins'] += 1
                    else:
                        self.ema200_stats['bearish_trades'] += 1
                        if trade_won:
                            self.ema200_stats['bearish_wins'] += 1
                    
                    if abs(ema200_distance) > self.params['ema200_strong_distance']:
                        self.ema200_stats['strong_trend_trades'] += 1
                    
                    # 시장 체제별 통계
                    market_regime = pos.get('market_regime', 'NORMAL')
                    if market_regime in self.regime_stats:
                        self.regime_stats[market_regime]['trades'] += 1
                        if trade_won:
                            self.regime_stats[market_regime]['wins'] += 1
                    
                    # Record trade
                    trade_data = {
                        'entry_time': pos['entry_time'],
                        'exit_time': current_time,
                        'strategy_type': strategy_type,
                        'direction': pos['direction'],
                        'entry_price': pos['entry_price'],
                        'exit_price': current_price,
                        'stop_loss': pos['stop_loss'],
                        'take_profit': pos['take_profit'],
                        'gross_pnl_pct': gross_pnl_pct,
                        'net_pnl_pct': net_pnl_pct,
                        'exit_type': exit_type,
                        'hours_held': hours_held,
                        'conditions': pos.get('conditions', []),
                        'condition_values': pos.get('condition_values', {}),
                        'mdd_at_entry': pos['mdd_at_entry'],
                        'mdd_at_exit': current_mdd,
                        'position_size': actual_position_size,
                        'mdd_level': pos.get('mdd_level', 0),
                        'size_multiplier': pos.get('size_multiplier', 1.0),
                        'market_regime': market_regime,
                        'trailing_enabled': pos.get('trailing_enabled', False),
                        'momentum_score': pos.get('momentum_score', 0)
                    }
                    self.trades.append(trade_data)
                    
                    # Update condition stats
                    for condition in pos.get('conditions', []):
                        self.condition_stats[condition]['triggered'] += 1
                        if net_pnl_pct > 0:
                            self.condition_stats[condition]['wins'] += 1
                    
                    positions_to_remove.append(idx)
            
            # 포지션 제거
            for idx in reversed(positions_to_remove):
                current_positions.pop(idx)
            
            # 신규 진입 체크 (개선된 Hybrid)
            if mdd_restrictions['allow_new_trades'] and total_position_size < self.params['max_combined_position']:
                # 횡보장 체크 - 횡보장이면 거래 차단
                is_choppy = self.check_choppy_market(self.df_15m, i)
                
                if not is_choppy:
                    # Hybrid 신호 체크
                    hybrid_results = self.signal_generator.check_hybrid_signals(
                        self.df_15m, self.df_4h, i
                    )
                    
                    # TFPE 신호 처리
                    if hybrid_results['tfpe']['signal']:
                        if last_signal_times['TFPE'] is None or (i - last_signal_times['TFPE']) >= self.params['min_signal_interval'] * 4:
                            direction = hybrid_results['tfpe']['direction']
                            position_size = self.params['position_size']
                            
                            # 200 EMA 필터 적용
                            position_size = self.get_market_bias_adjusted_position_size(
                                position_size, direction, self.df_4h, current_time
                            )
                            
                            # MDD 조정 적용
                            position_size *= mdd_restrictions['position_size_multiplier']
                            if mdd_restrictions['position_size_multiplier'] < 1.0:
                                trades_with_reduced_size += 1
                            
                            # 동적 손절 계산
                            stop_loss = self.calculate_dynamic_stop_loss(
                                current_price, direction, current_atr, 
                                self.df_15m, i, 'TFPE'
                            )
                            
                            # TP 계산 (기존 방식)
                            tp_distance = current_atr * self.params['take_profit_atr']
                            if direction == 'long':
                                take_profit = current_price + tp_distance
                            else:
                                take_profit = current_price - tp_distance
                            
                            # 200 EMA 정보 추가
                            aligned_time = current_time.floor('4h')
                            market_bias = 0
                            ema200_distance = 0
                            if aligned_time in self.df_4h.index:
                                candle_4h = self.df_4h.loc[aligned_time]
                                market_bias = candle_4h.get('market_bias', 0)
                                ema200_distance = candle_4h.get('ema200_distance', 0)
                            
                            new_position = {
                                'entry_time': current_time,
                                'entry_price': current_price,
                                'entry_index': i,
                                'direction': direction,
                                'stop_loss': stop_loss,
                                'take_profit': take_profit,
                                'conditions': ['tfpe_pullback'],
                                'condition_values': {},
                                'mdd_at_entry': current_mdd,
                                'position_size': position_size,
                                'actual_position_size': position_size,
                                'size_multiplier': mdd_restrictions['position_size_multiplier'],
                                'mdd_level': mdd_restrictions['mdd_level'],
                                'strategy_type': 'TFPE',
                                'market_regime': 'NORMAL',
                                'trailing_enabled': False,
                                'market_bias': market_bias,
                                'ema200_distance': ema200_distance
                            }
                            
                            current_positions.append(new_position)
                            last_signal_times['TFPE'] = i
                    
                    # Momentum 신호 처리
                    if hybrid_results['momentum']['signal']:
                        if last_signal_times['MOMENTUM'] is None or (i - last_signal_times['MOMENTUM']) >= self.params['min_signal_interval'] * 4:
                            direction = hybrid_results['momentum']['direction']
                            details = hybrid_results['momentum']['details']
                            position_size = self.params['momentum_position_size']
                            
                            # 200 EMA 필터 적용 (Momentum에도 적용)
                            position_size = self.get_market_bias_adjusted_position_size(
                                position_size, direction, self.df_4h, current_time
                            )
                            
                            # 동적 손절 계산 (Momentum용)
                            stop_loss = self.calculate_dynamic_stop_loss(
                                current_price, direction, current_atr, 
                                self.df_15m, i, 'MOMENTUM'
                            )
                            
                            # TP 계산 (기존 방식)
                            tp_distance = current_atr * self.params['momentum_take_profit_atr']
                            if direction == 'long':
                                take_profit = current_price + tp_distance
                            else:
                                take_profit = current_price - tp_distance
                            
                            # 200 EMA 정보 추가
                            aligned_time = current_time.floor('4h')
                            market_bias = 0
                            ema200_distance = 0
                            if aligned_time in self.df_4h.index:
                                candle_4h = self.df_4h.loc[aligned_time]
                                market_bias = candle_4h.get('market_bias', 0)
                                ema200_distance = candle_4h.get('ema200_distance', 0)
                            
                            new_position = {
                                'entry_time': current_time,
                                'entry_price': current_price,
                                'entry_index': i,
                                'direction': direction,
                                'stop_loss': stop_loss,
                                'take_profit': take_profit,
                                'conditions': details.get('conditions_met', ['momentum_breakout']),
                                'condition_values': details,
                                'mdd_at_entry': current_mdd,
                                'position_size': position_size,
                                'actual_position_size': position_size,
                                'size_multiplier': 1.0,  # Momentum은 MDD 조정 없음
                                'mdd_level': mdd_restrictions['mdd_level'],
                                'strategy_type': 'MOMENTUM',
                                'market_regime': details.get('regime', 'STRONG_TREND'),
                                'trailing_enabled': self.params['momentum_trailing_enabled'],
                                'momentum_score': details.get('score_percentage', 0),
                                'market_bias': market_bias,
                                'ema200_distance': ema200_distance
                            }
                            
                            current_positions.append(new_position)
                            last_signal_times['MOMENTUM'] = i
                else:
                    # 횡보장에서 신호 차단됨
                    self.choppy_market_stats['filtered_signals'] += 1
            
            equity_curve.append({
                'time': current_time,
                'capital': capital,
                'price': current_price,
                'mdd': current_mdd,
                'mdd_level': mdd_restrictions['mdd_level'],
                'positions_active': len(current_positions),
                'total_position_size': total_position_size,
                'position_size_multiplier': mdd_restrictions['position_size_multiplier']
            })
        
        print(f"\n✅ Enhanced Hybrid backtest complete")
        
        # 신호 생성 통계 출력
        signal_stats = self.signal_generator.get_statistics()
        print("\n📊 Signal Generation Statistics:")
        print(f"  TFPE signals: {signal_stats.get('tfpe_signals', 0)}")
        print(f"  Momentum signals: {signal_stats.get('momentum_signals', 0)}")
        print(f"  Strong trends detected: {signal_stats.get('strong_trends_detected', 0)}")
        print(f"  Channel breakouts: {signal_stats.get('channel_breakouts_detected', 0)}")
        
        if 'momentum_avg_score' in signal_stats:
            print(f"  Momentum avg score: {signal_stats['momentum_avg_score']:.1f}%")
            print(f"  Momentum scores >= 60%: {signal_stats.get('momentum_scores_above_60', 0)}")
        
        # 전략별 성과 출력
        print("\n📊 Strategy Performance:")
        for strategy, stats in self.strategy_stats.items():
            if stats['trades'] > 0:
                win_rate = stats['wins'] / stats['trades'] * 100
                avg_pnl = stats['total_pnl'] / stats['trades']
                print(f"\n  {strategy}:")
                print(f"    • Trades: {stats['trades']}")
                print(f"    • Win Rate: {win_rate:.1f}%")
                print(f"    • Total PnL: {stats['total_pnl']:.2f}%")
                print(f"    • Avg PnL: {avg_pnl:.2f}%")
        
        # 시장 체제별 성과
        print("\n📈 Market Regime Performance:")
        for regime, stats in self.regime_stats.items():
            if stats['trades'] > 0:
                win_rate = stats['wins'] / stats['trades'] * 100
                print(f"  {regime}: {stats['trades']} trades, {win_rate:.1f}% win rate")
        
        print(f"\n  Trades with reduced size: {trades_with_reduced_size}")
        print(f"  Trades skipped by MDD: {trades_skipped_by_mdd}")
        
        # Choppy Market 통계 출력
        if self.choppy_market_stats['total_periods'] > 0:
            choppy_ratio = self.choppy_market_stats['choppy_periods'] / self.choppy_market_stats['total_periods'] * 100
            print(f"\n📊 Choppy Market Statistics:")
            print(f"  Choppy periods: {choppy_ratio:.1f}% of total time")
            print(f"  Signals filtered by choppy market: {self.choppy_market_stats['filtered_signals']}")
            print(f"  Total choppy periods: {self.choppy_market_stats['choppy_periods']:,} / {self.choppy_market_stats['total_periods']:,}")
        
        # 200 EMA 필터 통계 출력
        if self.params['use_ema200_filter']:
            print(f"\n📊 200 EMA Filter Statistics:")
            if self.ema200_stats['bullish_trades'] > 0:
                bullish_wr = self.ema200_stats['bullish_wins'] / self.ema200_stats['bullish_trades'] * 100
                print(f"  Bullish market trades: {self.ema200_stats['bullish_trades']} (Win Rate: {bullish_wr:.1f}%)")
            if self.ema200_stats['bearish_trades'] > 0:
                bearish_wr = self.ema200_stats['bearish_wins'] / self.ema200_stats['bearish_trades'] * 100
                print(f"  Bearish market trades: {self.ema200_stats['bearish_trades']} (Win Rate: {bearish_wr:.1f}%)")
            print(f"  Strong trend trades: {self.ema200_stats['strong_trend_trades']}")
            
            # 포지션 크기 조정 횟수
            size_adjustments = sum(1 for t in self.trades if t.get('market_bias', 0) != 0)
            if size_adjustments > 0:
                print(f"  Position size adjustments: {size_adjustments} trades")
        
        # 동적 손절 통계 (추적을 위해 trades_df에서 분석)
        if len(self.trades) > 0:
            dynamic_stop_usage = sum(1 for t in self.trades if 'dynamic_stop' in str(t.get('conditions', [])))
            print(f"\n🎯 Dynamic Stop Loss:")
            print(f"  Applied to all {len(self.trades)} trades (100%)")
            print(f"  Note: Dynamic stops consider market structure + ATR")
        
        # Calculate results
        equity_df = pd.DataFrame(equity_curve)
        trades_df = pd.DataFrame(self.trades) if self.trades else pd.DataFrame()
        mdd_df = pd.DataFrame(self.mdd_history)
        
        return {
            'equity_df': equity_df,
            'trades_df': trades_df,
            'mdd_df': mdd_df,
            'final_capital': capital,
            'total_return': (capital - self.initial_capital) / self.initial_capital * 100,
            'trades_with_reduced_size': trades_with_reduced_size,
            'mdd_events': self.mdd_manager.mdd_events,
            'strategy_stats': self.strategy_stats,
            'regime_stats': self.regime_stats,
            'signal_stats': signal_stats,
            'choppy_market_stats': self.choppy_market_stats,
            'ema200_stats': self.ema200_stats
        }


if __name__ == "__main__":
    # 백테스트 실행
    print("="*80)
    print("TFPE + Momentum Hybrid Backtest")
    print("="*80)
    
    # 전략 인스턴스 생성
    strategy = TFPEMomentumHybridStrategyFixed(initial_capital=10000)
    
    # 데이터 로드
    print("\n📊 Loading data...")
    data_fetcher = DataFetcherFixed()
    
    # 2년간 데이터 로드
    df_4h, df_15m = data_fetcher.fetch_data(
        symbol='BTC/USDT',
        start_date='2022-07-01',
        end_date='2024-06-30'
    )
    
    # 지표 계산
    print("📈 Calculating indicators...")
    params = {
        'dc_period': 20,
        'adx_period': 14,
        'rsi_period': 14,
        'ema_period': 12,
        'volume_ma_period': 20,
        'swing_period': 20,
        'momentum_lookback': 20
    }
    
    df_4h, df_15m = data_fetcher.calculate_indicators(df_4h, df_15m, params)
    
    # 전략에 데이터 설정
    strategy.df_4h = df_4h
    strategy.df_15m = df_15m
    
    # 백테스트 실행
    results = strategy.run_backtest()
    
    # 결과 출력
    print("\n" + "="*80)
    print("📊 BACKTEST RESULTS")
    print("="*80)
    
    print(f"\n💰 Final Capital: ${results['final_capital']:,.2f}")
    print(f"📈 Total Return: {results['total_return']:.2f}%")
    print(f"📉 Trades with reduced size: {results['trades_with_reduced_size']}")
    
    if 'trades_df' in results and not results['trades_df'].empty:
        trades_df = results['trades_df']
        print(f"\n📊 Total Trades: {len(trades_df)}")
        print(f"✅ Win Rate: {(trades_df['net_pnl_pct'] > 0).mean() * 100:.1f}%")
        print(f"💹 Average PnL: {trades_df['net_pnl_pct'].mean():.2f}%")
        print(f"📈 Best Trade: {trades_df['net_pnl_pct'].max():.2f}%")
        print(f"📉 Worst Trade: {trades_df['net_pnl_pct'].min():.2f}%")
        
        # 최대 드로우다운 계산
        equity_df = results['equity_df']
        peak = equity_df['capital'].expanding().max()
        dd = (equity_df['capital'] - peak) / peak * 100
        max_dd = abs(dd.min())
        print(f"\n📉 Maximum Drawdown: {max_dd:.2f}%")
        
        # Sharpe Ratio 계산
        daily_returns = equity_df['capital'].pct_change().dropna()
        if len(daily_returns) > 0 and daily_returns.std() > 0:
            sharpe = np.sqrt(252) * daily_returns.mean() / daily_returns.std()
            print(f"📊 Sharpe Ratio: {sharpe:.2f}")
    
    print("\n✅ Backtest complete!")
