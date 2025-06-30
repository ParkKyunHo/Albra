# tfpe_donchian_mdd_improved_main.py
"""
TFPE 전략 - Donchian Channel 추세 감지 + 개선된 MDD 관리
메인 실행 파일
"""

import pandas as pd
import numpy as np
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
import warnings

# 모듈 임포트
try:
    from .mdd_manager import MDDManager
    from .data_fetcher import DataFetcher
    from .signal_generator import SignalGenerator
    from .visualizer import Visualizer
except:
    from mdd_manager import MDDManager
    from data_fetcher import DataFetcher
    from signal_generator import SignalGenerator
    from visualizer import Visualizer

warnings.filterwarnings('ignore')


class StrategyTester:
    """전략 테스터 클래스 추가"""
    
    @staticmethod
    def calculate_performance_metrics(trades_df: pd.DataFrame, equity_df: pd.DataFrame) -> Dict:
        """성과 지표 계산"""
        if trades_df.empty:
            return {
                'total_return': 0,
                'sharpe_ratio': 0,
                'win_rate': 0,
                'max_drawdown': 0,
                'total_trades': 0
            }
        
        # 총 수익률
        total_return = equity_df['capital'].iloc[-1] / equity_df['capital'].iloc[0] - 1
        total_return_pct = total_return * 100
        
        # 샤프 비율
        returns = equity_df['capital'].pct_change().dropna()
        sharpe = returns.mean() / returns.std() * np.sqrt(365 * 24 * 4) if returns.std() > 0 else 0
        
        # 승률
        win_rate = len(trades_df[trades_df['net_pnl_pct'] > 0]) / len(trades_df) * 100
        
        # 최대 손실
        rolling_max = equity_df['capital'].expanding().max()
        drawdown = (equity_df['capital'] - rolling_max) / rolling_max * 100
        max_drawdown = drawdown.min()
        
        return {
            'total_return': total_return_pct,
            'sharpe_ratio': sharpe,
            'win_rate': win_rate,
            'max_drawdown': abs(max_drawdown),
            'total_trades': len(trades_df)
        }


class TFPEDonchianStrategyWithMDD:
    """TFPE + Donchian Channel 전략 with 개선된 MDD 관리"""
    
    def __init__(self, initial_capital: float = 10000):
        self.initial_capital = initial_capital
        
        # Trading fees
        self.fees = {
            'taker': 0.0004,
            'funding_rate': 0.0001
        }
        
        # 전략 파라미터 (개선된 MDD 관리)
        self.params = {
            # 기본 설정
            'leverage': 15,
            'position_size': 24,  # 계좌의 24%
            
            # Donchian Channel
            'dc_period': 20,      # 20개 봉 (유일한 추세 파라미터)
            
            # 손절/익절
            'stop_loss_atr': 1.5,
            'take_profit_atr': 3.0,
            
            # 개선된 MDD 관리 파라미터
            'max_allowed_mdd': 40.0,  # 최대 허용 MDD 40%
            'mdd_recovery_threshold': 15.0,  # MDD 15% 이하로 회복시 정상 거래
            
            # MDD 단계별 포지션 크기 조정 (새로운 방식)
            'mdd_level_1': 30.0,  # MDD 30%: 포지션 70%로 축소
            'mdd_level_1_size': 0.7,
            'mdd_level_2': 35.0,  # MDD 35%: 포지션 50%로 축소
            'mdd_level_2_size': 0.5,
            'mdd_level_3': 40.0,  # MDD 40%: 포지션 30%로 축소
            'mdd_level_3_size': 0.3,
            'mdd_level_4': 50.0,  # MDD 50%: 포지션 10%로 축소 (긴급)
            'mdd_level_4_size': 0.1,
            
            # 회복 메커니즘
            'mdd_recovery_mode': True,  # 회복 모드 활성화
            'recovery_win_threshold': 3,  # 연속 3승 시 포지션 크기 증가
            'recovery_size_increment': 0.1,  # 회복 시 10%씩 증가
            'max_recovery_size': 1.0,  # 최대 100%까지 회복
            
            # 안전장치
            'mdd_emergency_stop': 60.0,  # MDD 60% 도달시 완전 중단
            'min_position_count': 0,  # 최소 포지션 수 (0 = 제한 없음)
            'force_trade_if_no_position': True,  # 포지션이 없으면 강제로 소액 거래 허용
            
            # 진입 조건 (기존 유지)
            'adx_min': 20,
            'signal_threshold': 3,
            'min_momentum': 2.0,
            'rsi_oversold': 30,
            'rsi_overbought': 70,
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
        }
        
        # 모듈 초기화
        self.mdd_manager = MDDManager(self.params)
        self.mdd_manager.peak_capital = initial_capital
        self.data_fetcher = DataFetcher()
        self.signal_generator = SignalGenerator(self.params, self.mdd_manager)
        self.visualizer = Visualizer(self.params)
        
        # Data storage
        self.df_4h = None
        self.df_15m = None
        self.trades = []
        self.condition_stats = defaultdict(lambda: {'triggered': 0, 'wins': 0})
        self.mdd_history = []
    
    def run_backtest(self, start_date: str = None, end_date: str = None) -> Dict:
        """백테스트 실행 with 개선된 MDD 관리"""
        print("\n🚀 Running TFPE + Donchian Channel backtest with improved MDD management...")
        
        capital = self.initial_capital
        equity_curve = []
        self.trades = []
        self.mdd_history = []
        self.condition_stats = defaultdict(lambda: {'triggered': 0, 'wins': 0})
        
        current_position = None
        last_signal_time = None
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
            
            # Update position tracking
            self.mdd_manager.active_positions_count = 1 if current_position else 0
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
                'position': 'YES' if current_position else 'NO',
                'recovery_multiplier': self.mdd_manager.current_recovery_multiplier
            })
            
            # Check MDD restrictions
            mdd_restrictions = self.mdd_manager.check_mdd_restrictions()
            
            # Check position exit
            if current_position:
                pos = current_position
                candles_held = i - pos['entry_index']
                hours_held = candles_held * 0.25
                
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
                    
                    # Apply position size adjustment from MDD
                    actual_position_size = pos['position_size'] * pos['size_multiplier']
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
                    
                    # Record trade
                    trade_data = {
                        'entry_time': pos['entry_time'],
                        'exit_time': current_time,
                        'direction': pos['direction'],
                        'side': pos['direction'].upper(),  # 호환성
                        'entry_price': pos['entry_price'],
                        'exit_price': current_price,
                        'stop_loss': pos['stop_loss'],
                        'take_profit': pos['take_profit'],
                        'gross_pnl_pct': gross_pnl_pct,
                        'net_pnl_pct': net_pnl_pct,
                        'pnl': net_pnl_pct,  # 호환성
                        'exit_type': exit_type,
                        'hours_held': hours_held,
                        'conditions': pos['conditions'],
                        'condition_values': pos['condition_values'],
                        'mdd_at_entry': pos['mdd_at_entry'],
                        'mdd_at_exit': current_mdd,
                        'position_size': actual_position_size,
                        'size': actual_position_size / 100,  # 호환성
                        'mdd_level': pos['mdd_level'],
                        'size_multiplier': pos['size_multiplier']
                    }
                    self.trades.append(trade_data)
                    
                    # Update condition stats
                    for condition in pos['conditions']:
                        self.condition_stats[condition]['triggered'] += 1
                        if net_pnl_pct > 0:
                            self.condition_stats[condition]['wins'] += 1
                    
                    current_position = None
            
            # Check new entry
            if not current_position and mdd_restrictions['allow_new_trades']:
                # Signal interval check
                if last_signal_time:
                    candles_since_last = i - last_signal_time
                    if candles_since_last < self.params['min_signal_interval'] * 4:
                        continue
                
                signal, direction, conditions, condition_values = self.signal_generator.check_entry_signal_donchian(
                    self.df_4h, self.df_15m, i
                )
                
                if signal:
                    # Calculate SL/TP
                    stop_distance = current_atr * self.params['stop_loss_atr']
                    tp_distance = current_atr * self.params['take_profit_atr']
                    
                    if direction == 'long':
                        stop_loss = current_price - stop_distance
                        take_profit = current_price + tp_distance
                    else:
                        stop_loss = current_price + stop_distance
                        take_profit = current_price - tp_distance
                    
                    # Track reduced size trades
                    if mdd_restrictions['position_size_multiplier'] < 1.0:
                        trades_with_reduced_size += 1
                    
                    current_position = {
                        'entry_time': current_time,
                        'entry_price': current_price,
                        'entry_index': i,
                        'direction': direction,
                        'stop_loss': stop_loss,
                        'take_profit': take_profit,
                        'conditions': conditions,
                        'condition_values': condition_values,
                        'mdd_at_entry': current_mdd,
                        'position_size': self.params['position_size'],
                        'size_multiplier': mdd_restrictions['position_size_multiplier'],
                        'mdd_level': mdd_restrictions['mdd_level']
                    }
                    
                    last_signal_time = i
            
            equity_curve.append({
                'time': current_time,
                'capital': capital,
                'price': current_price,
                'mdd': current_mdd,
                'mdd_level': mdd_restrictions['mdd_level'],
                'position_active': current_position is not None,
                'position_size_multiplier': mdd_restrictions['position_size_multiplier']
            })
        
        print(f"\n✅ Backtest complete")
        print(f"   Trades with reduced size: {trades_with_reduced_size}")
        print(f"   Trades skipped by MDD: {trades_skipped_by_mdd}")
        
        # Calculate results
        equity_df = pd.DataFrame(equity_curve)
        trades_df = pd.DataFrame(self.trades) if self.trades else pd.DataFrame()
        mdd_df = pd.DataFrame(self.mdd_history)
        
        # 성과 지표 계산
        metrics = StrategyTester.calculate_performance_metrics(trades_df, equity_df)
        
        results = {
            'equity_df': equity_df,
            'trades_df': trades_df,
            'mdd_df': mdd_df,
            'final_capital': capital,
            'trades_with_reduced_size': trades_with_reduced_size,
            'mdd_events': self.mdd_manager.mdd_events,
            **metrics  # 성과 지표 추가
        }
        
        return results
