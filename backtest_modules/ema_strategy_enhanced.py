"""
EMA Strategy with Range Market Filters
횡보장 필터가 추가된 개선된 EMA 전략
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import ta


class EMAVolatilityStrategyEnhanced:
    """횡보장 필터가 추가된 EMA 크로스오버 전략"""
    
    def __init__(self, initial_capital: float = 10000):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        
        # 기본 전략 파라미터
        self.ema_fast = 20
        self.ema_slow = 50
        self.atr_period = 14
        self.atr_stop_multiplier = 2.0
        self.leverage = 5
        self.position_size_pct = 10
        
        # 횡보장 필터 파라미터
        self.adx_threshold = 25          # ADX < 25 = 약한 추세
        self.ema_distance_min = 0.005    # EMA 최소 거리 0.5%
        self.bb_squeeze_threshold = 0.02 # 볼린저밴드 스퀴즈 2%
        self.whipsaw_lookback = 20       # 휩소 감지 기간
        self.whipsaw_max_crosses = 2     # 최대 허용 크로스 수
        self.volume_filter = 0.8         # 볼륨 필터 (평균의 80% 이상)
        
        # 거래 기록
        self.trades = []
        self.equity_curve = []
        self.skipped_signals = []  # 스킵된 신호 기록
        
        # 현재 포지션
        self.current_position = None
        self.position_type = None
        
        # 데이터
        self.df_1h = None
        
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """기술적 지표 계산 (횡보장 지표 포함)"""
        # 기본 지표
        df['ema20'] = ta.trend.ema_indicator(df['close'], window=self.ema_fast)
        df['ema50'] = ta.trend.ema_indicator(df['close'], window=self.ema_slow)
        df['atr'] = ta.volatility.average_true_range(
            high=df['high'], low=df['low'], close=df['close'], 
            window=self.atr_period
        )
        
        # EMA 크로스 신호
        df['ema_diff'] = df['ema20'] - df['ema50']
        df['ema_cross'] = np.where(
            (df['ema_diff'] > 0) & (df['ema_diff'].shift(1) <= 0), 1,
            np.where(
                (df['ema_diff'] < 0) & (df['ema_diff'].shift(1) >= 0), -1,
                0
            )
        )
        
        # 1. ADX (추세 강도)
        adx_result = ta.trend.adx(df['high'], df['low'], df['close'], window=14)
        df['adx'] = adx_result
        
        # 2. EMA 거리 (%)
        df['ema_distance'] = abs(df['ema20'] - df['ema50']) / df['close']
        
        # 3. 볼린저 밴드
        bb = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_lower'] = bb.bollinger_lband()
        df['bb_middle'] = bb.bollinger_mavg()
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
        
        # 4. 볼륨 이동평균
        df['volume_ma'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']
        
        # 5. 최근 크로스 카운트 (휩소 감지)
        df['cross_count'] = df['ema_cross'].abs().rolling(window=self.whipsaw_lookback).sum()
        
        # 6. ATR 비율 (변동성 지표)
        df['atr_ratio'] = df['atr'] / df['close']
        
        # 7. 시장 상태 판단
        df['market_regime'] = self.identify_market_regime(df)
        
        return df
    
    def identify_market_regime(self, df: pd.DataFrame) -> pd.Series:
        """시장 상태 식별 (TREND/RANGE/SQUEEZE)"""
        conditions = []
        
        # SQUEEZE: 볼린저밴드가 좁고 ATR이 낮음
        squeeze = (df['bb_width'] < self.bb_squeeze_threshold) & (df['atr_ratio'] < 0.01)
        
        # RANGE: ADX가 낮고 EMA 거리가 가까움
        range_market = (df['adx'] < self.adx_threshold) & (df['ema_distance'] < self.ema_distance_min * 2)
        
        # TREND: ADX가 높고 EMA 거리가 멀음
        trend = (df['adx'] > self.adx_threshold) & (df['ema_distance'] > self.ema_distance_min)
        
        # 우선순위: SQUEEZE > RANGE > TREND
        regime = pd.Series('NORMAL', index=df.index)
        regime[trend] = 'TREND'
        regime[range_market] = 'RANGE'
        regime[squeeze] = 'SQUEEZE'
        
        return regime
    
    def should_skip_signal(self, row: pd.Series, signal_type: str) -> Tuple[bool, str]:
        """신호를 스킵해야 하는지 판단"""
        reasons = []
        
        # 1. 시장 상태 체크
        if row['market_regime'] == 'SQUEEZE':
            reasons.append("Market in squeeze")
        elif row['market_regime'] == 'RANGE' and row['adx'] < 20:
            reasons.append(f"Very weak trend (ADX={row['adx']:.1f})")
        
        # 2. EMA 거리 체크
        if row['ema_distance'] < self.ema_distance_min:
            reasons.append(f"EMAs too close ({row['ema_distance']*100:.2f}%)")
        
        # 3. 휩소 체크
        if row['cross_count'] > self.whipsaw_max_crosses:
            reasons.append(f"Too many recent crosses ({int(row['cross_count'])})")
        
        # 4. 볼륨 체크
        if row['volume_ratio'] < self.volume_filter:
            reasons.append(f"Low volume ({row['volume_ratio']:.2f}x avg)")
        
        # 5. 극단적 변동성 체크
        if row['atr_ratio'] > 0.03:  # 3% 이상
            reasons.append(f"Extreme volatility (ATR={row['atr_ratio']*100:.1f}%)")
        
        skip = len(reasons) > 0
        reason_str = "; ".join(reasons) if skip else "Signal accepted"
        
        return skip, reason_str
    
    def calculate_dynamic_position_size(self, row: pd.Series) -> float:
        """시장 상태에 따른 동적 포지션 크기"""
        base_size = self.position_size_pct
        
        # 시장 상태별 조정
        if row['market_regime'] == 'SQUEEZE':
            return 0  # 스퀴즈에서는 거래 안함
        elif row['market_regime'] == 'RANGE':
            base_size *= 0.5  # 횡보장에서는 50% 축소
        elif row['market_regime'] == 'TREND' and row['adx'] > 30:
            base_size *= 1.2  # 강한 추세에서는 20% 증가
        
        # ADX 기반 추가 조정
        if row['adx'] < 20:
            base_size *= 0.7
        elif row['adx'] > 35:
            base_size *= 1.1
        
        # 변동성 기반 조정
        if row['atr_ratio'] > 0.02:  # 고변동성
            base_size *= 0.8
        elif row['atr_ratio'] < 0.01:  # 저변동성
            base_size *= 0.9
        
        return min(base_size, 20)  # 최대 20%
    
    def calculate_dynamic_stop_loss(self, row: pd.Series) -> float:
        """시장 상태에 따른 동적 손절 배수"""
        base_multiplier = self.atr_stop_multiplier
        
        # 횡보장에서는 타이트한 손절
        if row['market_regime'] == 'RANGE':
            base_multiplier = 1.0
        # 스퀴즈 후 브레이크아웃은 넓은 손절
        elif row['market_regime'] == 'SQUEEZE':
            base_multiplier = 2.5
        # 강한 추세에서는 표준 손절
        elif row['market_regime'] == 'TREND':
            if row['adx'] > 35:
                base_multiplier = 2.0
            else:
                base_multiplier = 1.5
        
        return base_multiplier
    
    def check_entry_signal(self, row: pd.Series, prev_row: pd.Series) -> Optional[str]:
        """진입 신호 확인 (필터 적용)"""
        if self.current_position is not None:
            return None
        
        signal = None
        
        # 기본 크로스오버 신호
        if row['ema_cross'] == 1:
            signal = 'long'
        elif row['ema_cross'] == -1:
            signal = 'short'
        
        # 신호가 있으면 필터 적용
        if signal:
            skip, reason = self.should_skip_signal(row, signal)
            
            if skip:
                self.skipped_signals.append({
                    'time': row.name,
                    'signal': signal,
                    'reason': reason,
                    'price': row['close']
                })
                return None
        
        return signal
    
    def enter_position(self, signal: str, row: pd.Series, timestamp: pd.Timestamp):
        """포지션 진입 (동적 사이징 적용)"""
        entry_price = row['close']
        atr = row['atr']
        
        # 동적 포지션 크기
        position_size_pct = self.calculate_dynamic_position_size(row)
        if position_size_pct == 0:
            return
        
        # 포지션 크기 계산
        risk_amount = self.capital * (position_size_pct / 100)
        position_value = risk_amount * self.leverage
        position_size = position_value / entry_price
        
        # 동적 손절 배수
        stop_multiplier = self.calculate_dynamic_stop_loss(row)
        
        # 손절 가격 설정
        if signal == 'long':
            stop_loss = entry_price - (atr * stop_multiplier)
        else:  # short
            stop_loss = entry_price + (atr * stop_multiplier)
        
        self.current_position = {
            'entry_time': timestamp,
            'entry_price': entry_price,
            'position_size': position_size,
            'position_size_pct': position_size_pct,
            'stop_loss': stop_loss,
            'stop_multiplier': stop_multiplier,
            'atr': atr,
            'market_regime': row['market_regime'],
            'adx': row['adx'],
            'volume_ratio': row['volume_ratio']
        }
        self.position_type = signal
    
    def run_backtest(self) -> Dict:
        """백테스트 실행"""
        if self.df_1h is None or self.df_1h.empty:
            return {
                'total_return': 0,
                'final_capital': self.initial_capital,
                'trades': 0,
                'trades_df': pd.DataFrame(),
                'equity_df': pd.DataFrame(),
                'skipped_signals_df': pd.DataFrame()
            }
        
        # 지표 계산
        self.df_1h = self.calculate_indicators(self.df_1h)
        
        # NaN 제거 (지표 계산으로 인한)
        self.df_1h = self.df_1h.dropna()
        
        # 거래 시뮬레이션
        for i in range(1, len(self.df_1h)):
            row = self.df_1h.iloc[i]
            prev_row = self.df_1h.iloc[i-1]
            timestamp = self.df_1h.index[i]
            
            # 현재 포지션이 있으면 청산 체크
            if self.current_position is not None:
                if self.check_exit_signal(row):
                    self.exit_position(row, timestamp)
            
            # 진입 신호 체크
            entry_signal = self.check_entry_signal(row, prev_row)
            if entry_signal:
                self.enter_position(entry_signal, row, timestamp)
            
            # 자산 기록
            self.equity_curve.append({
                'time': timestamp,
                'capital': self.capital,
                'in_position': self.current_position is not None,
                'position_type': self.position_type,
                'market_regime': row['market_regime'],
                'adx': row['adx'],
                'ema20': row['ema20'],
                'ema50': row['ema50']
            })
        
        # 마지막 포지션 청산
        if self.current_position is not None:
            last_row = self.df_1h.iloc[-1]
            self.exit_position(last_row, self.df_1h.index[-1])
        
        # 결과 정리
        trades_df = pd.DataFrame(self.trades)
        equity_df = pd.DataFrame(self.equity_curve)
        skipped_df = pd.DataFrame(self.skipped_signals)
        
        # 성과 계산
        total_return = ((self.capital - self.initial_capital) / self.initial_capital) * 100
        
        # 전략 통계
        strategy_stats = self._calculate_strategy_stats(trades_df, skipped_df)
        
        return {
            'total_return': total_return,
            'final_capital': self.capital,
            'trades': len(self.trades),
            'trades_df': trades_df,
            'equity_df': equity_df,
            'skipped_signals_df': skipped_df,
            'strategy_stats': strategy_stats
        }
    
    def _calculate_strategy_stats(self, trades_df: pd.DataFrame, skipped_df: pd.DataFrame) -> Dict:
        """전략 통계 계산"""
        stats = {}
        
        if len(trades_df) > 0:
            # 기본 통계
            winning_trades = trades_df[trades_df['net_pnl_pct'] > 0]
            losing_trades = trades_df[trades_df['net_pnl_pct'] <= 0]
            
            stats['total_trades'] = len(trades_df)
            stats['winning_trades'] = len(winning_trades)
            stats['losing_trades'] = len(losing_trades)
            stats['win_rate'] = (len(winning_trades) / len(trades_df)) * 100
            
            # 시장 상태별 통계
            for regime in ['TREND', 'RANGE', 'SQUEEZE', 'NORMAL']:
                regime_trades = trades_df[trades_df['market_regime'] == regime]
                if len(regime_trades) > 0:
                    regime_wins = regime_trades[regime_trades['net_pnl_pct'] > 0]
                    stats[f'{regime.lower()}_trades'] = len(regime_trades)
                    stats[f'{regime.lower()}_win_rate'] = (len(regime_wins) / len(regime_trades)) * 100
                    stats[f'{regime.lower()}_avg_pnl'] = regime_trades['net_pnl_pct'].mean()
        
        # 스킵된 신호 통계
        stats['skipped_signals'] = len(skipped_df)
        if len(skipped_df) > 0:
            skip_reasons = skipped_df['reason'].value_counts()
            stats['skip_reasons'] = skip_reasons.to_dict()
        
        return stats
    
    def check_exit_signal(self, row: pd.Series) -> bool:
        """청산 신호 확인"""
        if self.current_position is None:
            return False
            
        current_price = row['close']
        entry_price = self.current_position['entry_price']
        stop_loss = self.current_position['stop_loss']
        
        # 손절 확인
        if self.position_type == 'long':
            if current_price <= stop_loss:
                return True
        else:  # short
            if current_price >= stop_loss:
                return True
                
        # 익절: 반대 신호 발생 시
        if self.position_type == 'long' and row['ema_cross'] == -1:
            return True
        elif self.position_type == 'short' and row['ema_cross'] == 1:
            return True
            
        return False
    
    def exit_position(self, row: pd.Series, timestamp: pd.Timestamp):
        """포지션 청산"""
        if self.current_position is None:
            return
            
        exit_price = row['close']
        entry_price = self.current_position['entry_price']
        position_size = self.current_position['position_size']
        
        # 손익 계산
        if self.position_type == 'long':
            pnl = (exit_price - entry_price) * position_size
            pnl_pct = ((exit_price - entry_price) / entry_price) * 100
        else:  # short
            pnl = (entry_price - exit_price) * position_size
            pnl_pct = ((entry_price - exit_price) / entry_price) * 100
        
        # 레버리지 적용
        pnl *= self.leverage
        pnl_pct *= self.leverage
        
        # 수수료
        fee = position_size * (entry_price + exit_price) * 0.0005
        net_pnl = pnl - fee
        net_pnl_pct = pnl_pct - 0.1
        
        # 거래 기록
        trade = {
            'entry_time': self.current_position['entry_time'],
            'exit_time': timestamp,
            'direction': self.position_type,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'position_size': position_size,
            'position_size_pct': self.current_position['position_size_pct'],
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'fee': fee,
            'net_pnl': net_pnl,
            'net_pnl_pct': net_pnl_pct,
            'stop_loss': self.current_position['stop_loss'],
            'stop_multiplier': self.current_position['stop_multiplier'],
            'atr': self.current_position['atr'],
            'market_regime': self.current_position['market_regime'],
            'adx': self.current_position['adx'],
            'volume_ratio': self.current_position['volume_ratio'],
            'holding_hours': (timestamp - self.current_position['entry_time']).total_seconds() / 3600
        }
        self.trades.append(trade)
        
        # 자본 업데이트
        self.capital += net_pnl
        
        # 포지션 초기화
        self.current_position = None
        self.position_type = None
