"""
EMA Volatility Strategy - 20/50 EMA Crossover with ATR-based Stops
1시간봉 기준 골든크로스(롱), 데드크로스(숏) 전략
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import ta


class EMAVolatilityStrategy:
    """EMA 크로스오버 + TFPE 보완 전략
    
    핵심 원칙:
    1. EMA 20/50 크로스오버는 단순함이 핵심 - 필터 없이 바로 진입
    2. TFPE는 EMA가 놓치는 극단적 반전 기회를 포착
    3. EMA 추세와 같은 방향의 TFPE 신호만 수용
    4. EMA 포지션은 반대 크로스에서 청산 후 바로 반대 포지션 진입
    5. TFPE 포지션은 RSI 중립 복귀 또는 EMA 크로스에서 빠르게 청산
    """
    
    def __init__(self, initial_capital: float = 10000):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        
        # 전략 파라미터
        self.ema_fast = 20          # 빠른 EMA
        self.ema_slow = 50          # 느린 EMA
        self.atr_period = 14        # ATR 기간
        self.atr_stop_multiplier = 2.0    # 손절 ATR 배수 (2.0으로 변경)
        self.leverage = 5           # 레버리지
        self.position_size_pct = 10 # 포지션 크기 (%)
        
        # TFPE 파라미터 추가
        self.rsi_period = 14        # RSI 기간
        self.rsi_oversold = 30      # RSI 과매도
        self.rsi_overbought = 70    # RSI 과매수
        self.tfpe_position_size_pct = 5  # TFPE 포지션 크기 (작게 설정)
        
        # 거래 기록
        self.trades = []
        self.equity_curve = []
        
        # 현재 포지션
        self.current_position = None
        self.position_type = None  # 'long' or 'short'
        self.signal_type = None  # 'ema' or 'tfpe' - 신호 타입 추가
        
        # 데이터프레임
        self.df_1h = None
        
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """기술적 지표 계산"""
        # EMA 계산
        df['ema20'] = ta.trend.ema_indicator(df['close'], window=self.ema_fast)
        df['ema50'] = ta.trend.ema_indicator(df['close'], window=self.ema_slow)
        
        # ATR 계산
        df['atr'] = ta.volatility.average_true_range(
            high=df['high'], 
            low=df['low'], 
            close=df['close'], 
            window=self.atr_period
        )
        
        # EMA 크로스 신호
        df['ema_diff'] = df['ema20'] - df['ema50']
        df['ema_cross'] = np.where(
            (df['ema_diff'] > 0) & (df['ema_diff'].shift(1) <= 0), 1,  # 골든크로스
            np.where(
                (df['ema_diff'] < 0) & (df['ema_diff'].shift(1) >= 0), -1,  # 데드크로스
                0
            )
        )
        
        # 변동성 계산 (일일 변동성)
        df['returns'] = df['close'].pct_change()
        df['volatility'] = df['returns'].rolling(window=20).std() * np.sqrt(24)  # 1시간봉이므로 24시간
        
        # RSI 계산 (TFPE용)
        df['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=self.rsi_period).rsi()
        
        # Donchian Channel 계산 (20기간)
        df['dc_upper'] = df['high'].rolling(window=20).max()
        df['dc_lower'] = df['low'].rolling(window=20).min()
        df['dc_middle'] = (df['dc_upper'] + df['dc_lower']) / 2
        
        # 가격 위치 (0~1)
        df['price_position'] = (df['close'] - df['dc_lower']) / (df['dc_upper'] - df['dc_lower'])
        df['price_position'] = df['price_position'].fillna(0.5)
        
        return df
    
    def check_entry_signal(self, row: pd.Series, prev_row: pd.Series) -> Optional[Tuple[str, str]]:
        """진입 신호 확인 - EMA + TFPE 보완적 시스템"""
        if self.current_position is not None:
            return None
            
        # 1. EMA 크로스오버 신호 확인 - 단순함이 핵심, 필터 없음
        ema_signal = None
        if row['ema_cross'] == 1:
            ema_signal = 'long'
        elif row['ema_cross'] == -1:
            ema_signal = 'short'
            
        # 2. TFPE 신호 확인 (RSI + 위치)
        tfpe_signal = None
        if pd.notna(row['rsi']):
            # 과매도 + 하단 채널 근처 = 롱 신호
            if row['rsi'] < self.rsi_oversold and row['price_position'] < 0.2:
                tfpe_signal = 'long'
            # 과매수 + 상단 채널 근처 = 숏 신호
            elif row['rsi'] > self.rsi_overbought and row['price_position'] > 0.8:
                tfpe_signal = 'short'
        
        # 3. 보완적 신호 시스템
        # EMA 신호가 있으면 바로 진입 (필터 없음)
        if ema_signal:
            return (ema_signal, 'ema')
        
        # EMA 신호가 없을 때 TFPE 신호 확인
        # TFPE는 EMA가 놓치는 극단적 반전 기회를 포착
        elif tfpe_signal:
            # 현재 EMA 추세와 반대 방향의 TFPE 신호는 무시
            # (추세 추종 전략과 충돌 방지)
            ema_trend = 'up' if row['ema20'] > row['ema50'] else 'down'
            
            # EMA 상승 추세에서 TFPE 숏 신호는 무시
            if ema_trend == 'up' and tfpe_signal == 'short':
                return None
            # EMA 하락 추세에서 TFPE 롱 신호는 무시
            elif ema_trend == 'down' and tfpe_signal == 'long':
                return None
            
            # 추세와 같은 방향의 TFPE 신호만 수용
            return (tfpe_signal, 'tfpe')
            
        return None
    
    def check_exit_signal(self, row: pd.Series) -> bool:
        """청산 신호 확인"""
        if self.current_position is None:
            return False
            
        current_price = row['close']
        entry_price = self.current_position['entry_price']
        stop_loss = self.current_position['stop_loss']
        
        # 손절 확인 (ATR 2배)
        if self.position_type == 'long':
            if current_price <= stop_loss:
                return True
        else:  # short
            if current_price >= stop_loss:
                return True
                
        # 전략별 다른 청산 로직
        if self.signal_type == 'ema':
            # EMA 포지션: 반대 크로스에서 청산
            if self.position_type == 'long' and row['ema_cross'] == -1:
                return True
            elif self.position_type == 'short' and row['ema_cross'] == 1:
                return True
        else:  # tfpe
            # TFPE 포지션: 반전 신호를 포착한 후 빠른 청산
            if self.position_type == 'long':
                # 1) RSI가 중립점(50) 이상으로 회복
                # 2) 과매수 영역 진입
                # 3) EMA 데드크로스 발생
                if (row['rsi'] > 50 or 
                    row['rsi'] > self.rsi_overbought or
                    row['ema_cross'] == -1):
                    return True
            else:  # short
                # 1) RSI가 중립점(50) 이하로 회복
                # 2) 과매도 영역 진입
                # 3) EMA 골든크로스 발생
                if (row['rsi'] < 50 or 
                    row['rsi'] < self.rsi_oversold or
                    row['ema_cross'] == 1):
                    return True
            
        return False
    
    def calculate_position_size(self, capital: float, price: float, signal_type: str = 'ema') -> float:
        """포지션 크기 계산 - 신호 타입에 따라 다른 크기"""
        # 신호 타입에 따른 포지션 크기
        if signal_type == 'ema':
            position_pct = self.position_size_pct  # 10%
        else:  # tfpe
            position_pct = self.tfpe_position_size_pct  # 5%
        
        # 계정의 일정 비율만 사용
        risk_amount = capital * (position_pct / 100)
        
        # 레버리지 적용
        position_value = risk_amount * self.leverage
        position_size = position_value / price
        
        return position_size
    
    def enter_position(self, signal_info: Tuple[str, str], row: pd.Series, timestamp: pd.Timestamp):
        """포지션 진입"""
        signal, signal_type = signal_info
        entry_price = row['close']
        atr = row['atr']
        
        # 신호 타입에 따른 포지션 크기 계산
        position_size = self.calculate_position_size(self.capital, entry_price, signal_type)
        
        # 손절 가격만 설정 (익절은 반대 크로스에서 처리)
        if signal == 'long':
            stop_loss = entry_price - (atr * self.atr_stop_multiplier)
        else:  # short
            stop_loss = entry_price + (atr * self.atr_stop_multiplier)
        
        self.current_position = {
            'entry_time': timestamp,
            'entry_price': entry_price,
            'position_size': position_size,
            'stop_loss': stop_loss,
            'atr': atr,
            'signal_type': signal_type,  # 신호 타입 저장
            'rsi': row['rsi']  # 진입 시 RSI 저장
        }
        self.position_type = signal
        self.signal_type = signal_type  # 클래스 변수에도 저장
    
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
        
        # 수수료 (메이커/테이커 평균 0.05%)
        fee = position_size * (entry_price + exit_price) * 0.0005
        net_pnl = pnl - fee
        net_pnl_pct = pnl_pct - 0.1  # 수수료 약 0.1%
        
        # 거래 기록
        trade = {
            'entry_time': self.current_position['entry_time'],
            'exit_time': timestamp,
            'direction': self.position_type,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'position_size': position_size,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'fee': fee,
            'net_pnl': net_pnl,
            'net_pnl_pct': net_pnl_pct,
            'stop_loss': self.current_position['stop_loss'],
            'atr': self.current_position['atr'],
            'holding_hours': (timestamp - self.current_position['entry_time']).total_seconds() / 3600,
            'signal_type': self.current_position['signal_type'],  # 신호 타입 기록
            'entry_rsi': self.current_position['rsi'],  # 진입 시 RSI
            'exit_rsi': row['rsi']  # 청산 시 RSI
        }
        self.trades.append(trade)
        
        # 자본 업데이트
        self.capital += net_pnl
        
        # 포지션 초기화
        self.current_position = None
        self.position_type = None
        self.signal_type = None
    
    def run_backtest(self) -> Dict:
        """백테스트 실행"""
        if self.df_1h is None or self.df_1h.empty:
            return {
                'total_return': 0,
                'final_capital': self.initial_capital,
                'trades': 0,
                'trades_df': pd.DataFrame(),
                'equity_df': pd.DataFrame()
            }
        
        # 지표 계산
        self.df_1h = self.calculate_indicators(self.df_1h)
        
        # 거래 시뮬레이션
        for i in range(1, len(self.df_1h)):
            row = self.df_1h.iloc[i]
            prev_row = self.df_1h.iloc[i-1]
            timestamp = self.df_1h.index[i]
            
            # 현재 포지션이 있으면 청산 체크
            if self.current_position is not None:
                if self.check_exit_signal(row):
                    # 청산 이유 파악
                    exit_reason = None
                    if self.signal_type == 'ema' and (
                        (self.position_type == 'long' and row['ema_cross'] == -1) or
                        (self.position_type == 'short' and row['ema_cross'] == 1)):
                        exit_reason = 'ema_cross'
                    
                    self.exit_position(row, timestamp)
                    
                    # EMA 크로스로 청산했다면 바로 반대 포지션 진입 가능
                    # (데드크로스 후 숏, 골든크로스 후 롱)
                    if exit_reason == 'ema_cross':
                        # 새로운 EMA 신호 확인
                        new_ema_signal = None
                        if row['ema_cross'] == 1:
                            new_ema_signal = ('long', 'ema')
                        elif row['ema_cross'] == -1:
                            new_ema_signal = ('short', 'ema')
                        
                        if new_ema_signal:
                            self.enter_position(new_ema_signal, row, timestamp)
                            continue  # 다음 루프로
            
            # 포지션이 없을 때만 진입 신호 체크
            if self.current_position is None:
                entry_signal = self.check_entry_signal(row, prev_row)
                if entry_signal:  # entry_signal은 이제 (방향, 신호타입) 튜플
                    self.enter_position(entry_signal, row, timestamp)
            
            # 자산 기록
            self.equity_curve.append({
                'time': timestamp,
                'capital': self.capital,
                'in_position': self.current_position is not None,
                'position_type': self.position_type,
                'ema20': row['ema20'],
                'ema50': row['ema50'],
                'volatility': row.get('volatility', 0)
            })
        
        # 마지막 포지션 청산
        if self.current_position is not None:
            last_row = self.df_1h.iloc[-1]
            self.exit_position(last_row, self.df_1h.index[-1])
        
        # 결과 정리
        trades_df = pd.DataFrame(self.trades)
        equity_df = pd.DataFrame(self.equity_curve)
        
        # 성과 계산
        total_return = ((self.capital - self.initial_capital) / self.initial_capital) * 100
        
        # 전략 통계
        strategy_stats = {}
        if len(trades_df) > 0:
            winning_trades = trades_df[trades_df['net_pnl_pct'] > 0]
            losing_trades = trades_df[trades_df['net_pnl_pct'] <= 0]
            
            strategy_stats = {
                'total_trades': len(trades_df),
                'winning_trades': len(winning_trades),
                'losing_trades': len(losing_trades),
                'win_rate': (len(winning_trades) / len(trades_df)) * 100 if len(trades_df) > 0 else 0,
                'avg_win': winning_trades['net_pnl_pct'].mean() if len(winning_trades) > 0 else 0,
                'avg_loss': losing_trades['net_pnl_pct'].mean() if len(losing_trades) > 0 else 0,
                'best_trade': trades_df['net_pnl_pct'].max(),
                'worst_trade': trades_df['net_pnl_pct'].min(),
                'avg_holding_hours': trades_df['holding_hours'].mean(),
                'long_trades': len(trades_df[trades_df['direction'] == 'long']),
                'short_trades': len(trades_df[trades_df['direction'] == 'short'])
            }
            
            # 신호 타입별 통계 추가
            if 'signal_type' in trades_df.columns:
                ema_trades = trades_df[trades_df['signal_type'] == 'ema']
                tfpe_trades = trades_df[trades_df['signal_type'] == 'tfpe']
                
                if len(ema_trades) > 0:
                    ema_wins = ema_trades[ema_trades['net_pnl_pct'] > 0]
                    strategy_stats['ema_trades'] = len(ema_trades)
                    strategy_stats['ema_win_rate'] = (len(ema_wins) / len(ema_trades)) * 100
                    strategy_stats['ema_avg_pnl'] = ema_trades['net_pnl_pct'].mean()
                
                if len(tfpe_trades) > 0:
                    tfpe_wins = tfpe_trades[tfpe_trades['net_pnl_pct'] > 0]
                    strategy_stats['tfpe_trades'] = len(tfpe_trades)
                    strategy_stats['tfpe_win_rate'] = (len(tfpe_wins) / len(tfpe_trades)) * 100
                    strategy_stats['tfpe_avg_pnl'] = tfpe_trades['net_pnl_pct'].mean()
        
        return {
            'total_return': total_return,
            'final_capital': self.capital,
            'trades': len(self.trades),
            'trades_df': trades_df,
            'equity_df': equity_df,
            'strategy_stats': strategy_stats
        }
