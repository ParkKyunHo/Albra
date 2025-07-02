"""
TFPE (Trend Following Pullback Entry) Donchian Strategy - Walk-Forward Analysis
TFPE 전략 전진분석 백테스팅 (2021 Q1 - 2025 Q2)
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
import os
import sys
import time
from typing import Dict, List, Tuple, Optional
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import pickle

# 스크립트 디렉토리 확인
if __file__:
    script_dir = os.path.dirname(os.path.abspath(__file__))
else:
    script_dir = os.getcwd()

# Backtest 모듈 임포트
sys.path.append(os.path.join(script_dir, 'backtest_modules'))
sys.path.append(script_dir)

# 디버깅 정보 추가
print(f"Current directory: {os.getcwd()}")
print(f"Script directory: {script_dir}")

# 캐시 디렉토리 확인
cache_dir = os.path.join(script_dir, 'wf_cache')
if not os.path.exists(cache_dir):
    os.makedirs(cache_dir, exist_ok=True)

try:
    from backtest_modules.fixed.data_fetcher_fixed import DataFetcherFixed
    print("✓ Import successful")
except ImportError as e:
    print(f"❌ Import error: {e}")
    raise

# 폰트 설정
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False


class TFPEDonchianStrategy:
    """TFPE (Trend Following Pullback Entry) Donchian Channel Strategy"""
    
    def __init__(self, initial_capital: float = 10000, timeframe: str = '4h', symbol: str = 'BTC/USDT'):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position = None
        self.trades = []
        self.equity_curve = []
        self.last_trade_result = None
        self.consecutive_losses = 0
        self.recent_trades = []
        
        # 거래 비용
        self.symbol = symbol
        self.slippage = 0.001  # 슬리피지 0.1%
        self.commission = 0.0006  # 수수료 0.06%
        
        # 타임프레임별 캔들 수 계산
        self.timeframe = timeframe
        if timeframe == '4h':
            self.candles_per_day = 6
        elif timeframe == '1h':
            self.candles_per_day = 24
        elif timeframe == '15m':
            self.candles_per_day = 96
        else:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        
        # TFPE 전략 파라미터 (실제 전략과 동일하게 설정)
        self.position_size = 24  # 계좌의 24%
        self.signal_threshold = 4  # 백테스트 개선: 3 → 4
        self.min_momentum = 2.0  # 최소 2% 모멘텀
        self.volume_spike = 1.5
        self.ema_distance_max = 0.015  # 1.5%
        
        # Donchian Channel 파라미터
        self.dc_period = 20  # Donchian 기간
        self.price_position_high = 0.7
        self.price_position_low = 0.3
        self.price_position_neutral_min = 0.4
        self.price_position_neutral_max = 0.6
        
        # RSI 파라미터
        self.rsi_period = 14
        self.rsi_pullback_long = 40
        self.rsi_pullback_short = 60
        self.rsi_neutral_long = 20
        self.rsi_neutral_short = 80
        
        # 횡보장 RSI 극단값
        self.rsi_oversold = 30
        self.rsi_overbought = 70
        
        # 채널폭 파라미터
        self.channel_width_threshold = 0.05  # 5%
        
        # 피보나치 되돌림 레벨
        self.fib_min = 0.382
        self.fib_max = 0.786
        
        # 손절/익절
        self.stop_loss_atr = 1.5
        self.take_profit_atr = 5.0  # 백테스트 개선: 3.0 → 5.0
        
        # ADX 파라미터
        self.adx_period = 14
        self.adx_min = 25  # 백테스트 개선: 20 → 25
        
        # 스윙/모멘텀 파라미터
        self.swing_period = 20
        self.momentum_lookback = 20
        
        self.leverage = 10  # 레버리지 10배
        self.max_position_loss_pct = 0.10  # 포지션당 최대 손실 10%
        
        # ATR 계산 및 저장
        self.atr_period = 14
        self.current_atr = None
        
        # 리스크 관리
        self.daily_loss_limit = 0.05  # 일일 최대 손실 한도 5%
        self.daily_loss = 0
        self.last_trade_date = None
        self.trading_suspended_until = None
        self.initial_stop_loss = 0.03  # 초기 손절 3%
        self.trailing_stop_active = False
        self.trailing_stop_price = None
        self.highest_price = None
        self.lowest_price = None
        
        # 부분 익절 파라미터
        self.partial_exit_1_pct = 5.0
        self.partial_exit_2_pct = 10.0
        self.partial_exit_3_pct = 15.0
        self.partial_exit_1_ratio = 0.30
        self.partial_exit_2_ratio = 0.40
        self.partial_exit_3_ratio = 0.30
        self.partial_exit_1_done = False
        self.partial_exit_2_done = False
        self.partial_exit_3_done = False
        
        print(f"  TFPE Donchian Strategy initialized:")
        print(f"  • Symbol: {symbol}")
        print(f"  • Timeframe: {timeframe}")
        print(f"  • Donchian Period: {self.dc_period}")
        print(f"  • Leverage: {self.leverage}x")
        print(f"  • Position Size: {self.position_size}% of capital")
        print(f"  • Signal Threshold: {self.signal_threshold}")
        print(f"  • Min Momentum: {self.min_momentum}%")
        print(f"  • ADX Threshold: {self.adx_min}")
        print(f"  • Stop Loss: {self.stop_loss_atr} x ATR")
        print(f"  • Take Profit: {self.take_profit_atr} x ATR")
        print(f"  • Volume Spike: {self.volume_spike}x")
        print(f"  • Channel Width Threshold: {self.channel_width_threshold*100}%")
        print(f"  • Daily Loss Limit: {self.daily_loss_limit*100}%")
        print(f"  • Partial TP: 30% at +5%, 40% at +10%, 30% at +15%")
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """모든 기술 지표 계산"""
        # Donchian Channel
        df['dc_upper'] = df['high'].rolling(self.dc_period).max()
        df['dc_lower'] = df['low'].rolling(self.dc_period).min()
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
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # ATR
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift(1))
        low_close = np.abs(df['low'] - df['close'].shift(1))
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        df['atr'] = true_range.rolling(self.atr_period).mean()
        
        # ADX
        plus_dm = df['high'].diff()
        minus_dm = -df['low'].diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        
        tr = true_range
        atr14 = tr.rolling(14).mean()
        
        plus_di = 100 * (plus_dm.rolling(14).mean() / atr14)
        minus_di = 100 * (minus_dm.rolling(14).mean() / atr14)
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        df['adx'] = dx.rolling(14).mean()
        df['plus_di'] = plus_di
        df['minus_di'] = minus_di
        
        # EMA
        df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
        
        # 볼륨 관련
        df['volume_ma'] = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']
        
        # 모멘텀
        df['momentum'] = ((df['close'] - df['close'].shift(self.momentum_lookback)) / 
                         df['close'].shift(self.momentum_lookback) * 100)
        
        # 스윙 하이/로우
        df['swing_high'] = df['high'].rolling(self.swing_period).max()
        df['swing_low'] = df['low'].rolling(self.swing_period).min()
        
        # NaN 값 처리
        df = df.ffill().bfill()
        
        # 볼륨 비율 NaN 처리 (0으로 나누어지는 경우)
        df['volume_ratio'] = df['volume_ratio'].fillna(1.0)
        
        # 디버그 정보 출력
        print(f"\n  지표 계산 완료:")
        print(f"    - 데이터 개수: {len(df)}")
        print(f"    - NaN 개수: {df.isna().sum().sum()}")
        print(f"    - ADX 평균: {df['adx'].mean():.2f}")
        print(f"    - Volume Ratio 평균: {df['volume_ratio'].mean():.2f}")
        
        return df
    
    def check_entry_conditions(self, df: pd.DataFrame, i: int) -> Tuple[bool, str]:
        """진입 조건 체크"""
        if i < max(self.dc_period, self.momentum_lookback, 200):  # 충분한 데이터 필요
            return False, None
        
        current = df.iloc[i]
        
        # ADX 필터
        if pd.isna(current['adx']) or current['adx'] < self.adx_min:
            return False, None
        
        # 채널폭 체크
        if current['channel_width_pct'] < self.channel_width_threshold:
            return False, None
        
        # 볼륨 스파이크 체크
        if current['volume_ratio'] < self.volume_spike:
            return False, None
        
        # 모멘텀 체크
        if abs(current['momentum']) < self.min_momentum:
            return False, None
        
        signal_strength = 0
        direction = None
        
        # 트렌드 상태 확인
        trend_up = current['close'] > current['ema_50'] > current['ema_200']
        trend_down = current['close'] < current['ema_50'] < current['ema_200']
        
        # 상승 추세에서의 풀백 진입
        if trend_up:
            # 가격이 채널 상단 근처에서 풀백
            if 0.4 <= current['price_position'] <= 0.7:
                if current['rsi'] <= self.rsi_pullback_long:
                    signal_strength += 2
                
                # 피보나치 되돌림 체크
                recent_high = df['high'].iloc[i-20:i].max()
                recent_low = df['low'].iloc[i-20:i].min()
                fib_range = recent_high - recent_low
                fib_level = (current['close'] - recent_low) / fib_range if fib_range > 0 else 0
                
                if self.fib_min <= fib_level <= self.fib_max:
                    signal_strength += 1
                
                # EMA 거리 체크
                ema_distance = abs(current['close'] - current['ema_50']) / current['close']
                if ema_distance <= self.ema_distance_max:
                    signal_strength += 1
                
                if signal_strength >= self.signal_threshold:
                    direction = 'long'
        
        # 하락 추세에서의 풀백 진입
        elif trend_down:
            # 가격이 채널 하단 근처에서 풀백
            if 0.3 <= current['price_position'] <= 0.6:
                if current['rsi'] >= self.rsi_pullback_short:
                    signal_strength += 2
                
                # 피보나치 되돌림 체크
                recent_high = df['high'].iloc[i-20:i].max()
                recent_low = df['low'].iloc[i-20:i].min()
                fib_range = recent_high - recent_low
                fib_level = (recent_high - current['close']) / fib_range if fib_range > 0 else 0
                
                if self.fib_min <= fib_level <= self.fib_max:
                    signal_strength += 1
                
                # EMA 거리 체크
                ema_distance = abs(current['close'] - current['ema_50']) / current['close']
                if ema_distance <= self.ema_distance_max:
                    signal_strength += 1
                
                if signal_strength >= self.signal_threshold:
                    direction = 'short'
        
        # 횡보장에서의 극단값 진입
        else:
            if self.price_position_neutral_min <= current['price_position'] <= self.price_position_neutral_max:
                if current['rsi'] <= self.rsi_oversold and current['momentum'] > 0:
                    signal_strength = self.signal_threshold
                    direction = 'long'
                elif current['rsi'] >= self.rsi_overbought and current['momentum'] < 0:
                    signal_strength = self.signal_threshold
                    direction = 'short'
        
        if signal_strength >= self.signal_threshold and direction:
            print(f"\n  ✅ 진입 신호 확정: 시간={df.iloc[i]['timestamp']}, 가격=${current['close']:.2f}, 방향={direction}")
            return True, direction
        
        return False, None
    
    def check_exit_conditions(self, df: pd.DataFrame, i: int) -> Tuple[bool, str]:
        """청산 조건 체크"""
        if not self.position:
            return False, ""
        
        current = df.iloc[i]
        entry_price = self.position['entry_price']
        position_type = self.position['type']
        
        # 현재 손익 계산
        if position_type == 'long':
            pnl_pct = (current['close'] - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - current['close']) / entry_price
        
        # 손절 체크
        stop_loss = self.position.get('stop_loss', entry_price * (1 - self.initial_stop_loss))
        if position_type == 'long' and current['close'] <= stop_loss:
            return True, "Stop Loss"
        elif position_type == 'short' and current['close'] >= stop_loss:
            return True, "Stop Loss"
        
        # 익절 체크
        take_profit = self.position.get('take_profit', None)
        if take_profit:
            if position_type == 'long' and current['close'] >= take_profit:
                return True, "Take Profit"
            elif position_type == 'short' and current['close'] <= take_profit:
                return True, "Take Profit"
        
        # Donchian 채널 이탈
        if position_type == 'long' and current['close'] < current['dc_lower']:
            return True, "Donchian Exit"
        elif position_type == 'short' and current['close'] > current['dc_upper']:
            return True, "Donchian Exit"
        
        # ADX 약화
        if current['adx'] < self.adx_min * 0.7:
            return True, "ADX Weakening"
        
        # 추세 반전
        if position_type == 'long' and current['plus_di'] < current['minus_di']:
            return True, "Trend Reversal"
        elif position_type == 'short' and current['plus_di'] > current['minus_di']:
            return True, "Trend Reversal"
        
        return False, ""
    
    def execute_trade(self, df: pd.DataFrame, i: int, signal: str):
        """거래 실행"""
        current = df.iloc[i]
        price = current['close']
        timestamp = current['timestamp']
        
        # 일일 손실 한도 체크
        if self.trading_suspended_until and timestamp < self.trading_suspended_until:
            return
        
        # 새로운 날짜 시작 시 일일 손실 초기화
        current_date = timestamp.date()
        if self.last_trade_date and current_date > self.last_trade_date:
            self.daily_loss = 0
            self.last_trade_date = current_date
        
        # 일일 손실 한도 도달 시 거래 중단
        if self.daily_loss >= self.daily_loss_limit:
            self.trading_suspended_until = timestamp + timedelta(days=1)
            return
        
        # 포지션 크기 계산 (Kelly Criterion 미적용, 고정 비율 사용)
        position_size_pct = self.position_size / 100
        
        # 연속 손실에 따른 포지션 축소
        if self.consecutive_losses >= 7:
            position_size_pct *= 0.3
        elif self.consecutive_losses >= 5:
            position_size_pct *= 0.5
        elif self.consecutive_losses >= 3:
            position_size_pct *= 0.7
        
        # ATR 기반 손절/익절 설정
        atr = current['atr']
        if signal == 'long':
            stop_loss = price - (atr * self.stop_loss_atr)
            take_profit = price + (atr * self.take_profit_atr)
        else:
            stop_loss = price + (atr * self.stop_loss_atr)
            take_profit = price - (atr * self.take_profit_atr)
        
        # 거래 비용 적용
        effective_price = price * (1 + self.slippage) if signal == 'long' else price * (1 - self.slippage)
        position_value = self.capital * position_size_pct * self.leverage
        commission_cost = position_value * self.commission
        
        self.position = {
            'type': signal,
            'entry_price': effective_price,
            'entry_time': timestamp,
            'size': position_value / effective_price,
            'value': position_value,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'atr': atr,
            'commission_paid': commission_cost
        }
        
        self.capital -= commission_cost
        self.highest_price = effective_price if signal == 'long' else None
        self.lowest_price = effective_price if signal == 'short' else None
        
        # 부분 익절 플래그 초기화
        self.partial_exit_1_done = False
        self.partial_exit_2_done = False
        self.partial_exit_3_done = False
        self.trailing_stop_active = False
        self.trailing_stop_price = None
        
        print(f"  💰 포지션 진입: {signal.upper()} @ ${effective_price:.2f}, 크기: {self.position['size']:.4f}, SL: ${stop_loss:.2f}, TP: ${take_profit:.2f}")
    
    def close_position(self, df: pd.DataFrame, i: int, reason: str):
        """포지션 청산"""
        if not self.position:
            return
        
        current = df.iloc[i]
        exit_price = current['close']
        
        # 거래 비용 적용
        if self.position['type'] == 'long':
            effective_exit_price = exit_price * (1 - self.slippage)
            pnl = (effective_exit_price - self.position['entry_price']) * self.position['size']
        else:
            effective_exit_price = exit_price * (1 + self.slippage)
            pnl = (self.position['entry_price'] - effective_exit_price) * self.position['size']
        
        # 수수료 차감
        exit_commission = self.position['size'] * effective_exit_price * self.commission
        pnl -= exit_commission
        
        # 일일 손실 업데이트
        if pnl < 0:
            self.daily_loss += abs(pnl) / self.capital
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        
        # 자본 업데이트
        self.capital += pnl
        
        # 거래 기록
        trade = {
            'entry_time': self.position['entry_time'],
            'exit_time': current['timestamp'],
            'type': self.position['type'],
            'entry_price': self.position['entry_price'],
            'exit_price': effective_exit_price,
            'size': self.position['size'],
            'pnl': pnl,
            'pnl_pct': pnl / (self.position['value']),
            'reason': reason,
            'commission': self.position['commission_paid'] + exit_commission
        }
        
        self.trades.append(trade)
        self.recent_trades.append(trade)
        if len(self.recent_trades) > 20:
            self.recent_trades.pop(0)
        
        self.position = None
        self.last_trade_result = 'win' if pnl > 0 else 'loss'
        
        print(f"  💵 포지션 청산: {self.position['type'].upper()} @ ${effective_exit_price:.2f}, PnL: ${pnl:.2f} ({pnl/self.position['value']*100:.2f}%), 이유: {reason}")
    
    def update_position(self, df: pd.DataFrame, i: int):
        """포지션 업데이트 (부분 익절, 트레일링 스톱 등)"""
        if not self.position:
            return
        
        current = df.iloc[i]
        price = current['close']
        entry_price = self.position['entry_price']
        position_type = self.position['type']
        
        # 손익률 계산
        if position_type == 'long':
            pnl_pct = (price - entry_price) / entry_price * 100
            # 최고가 업데이트
            if self.highest_price is None or price > self.highest_price:
                self.highest_price = price
        else:
            pnl_pct = (entry_price - price) / entry_price * 100
            # 최저가 업데이트
            if self.lowest_price is None or price < self.lowest_price:
                self.lowest_price = price
        
        # 부분 익절 실행
        if not self.partial_exit_1_done and pnl_pct >= self.partial_exit_1_pct:
            self.execute_partial_exit(df, i, self.partial_exit_1_ratio, "Partial TP 1")
            self.partial_exit_1_done = True
        elif not self.partial_exit_2_done and pnl_pct >= self.partial_exit_2_pct:
            self.execute_partial_exit(df, i, self.partial_exit_2_ratio, "Partial TP 2")
            self.partial_exit_2_done = True
        elif not self.partial_exit_3_done and pnl_pct >= self.partial_exit_3_pct:
            self.execute_partial_exit(df, i, self.partial_exit_3_ratio, "Partial TP 3")
            self.partial_exit_3_done = True
        
        # 트레일링 스톱 활성화 및 업데이트
        if pnl_pct >= 3.0 and not self.trailing_stop_active:
            self.trailing_stop_active = True
            if position_type == 'long':
                self.trailing_stop_price = self.highest_price * 0.97  # 3% 트레일링
            else:
                self.trailing_stop_price = self.lowest_price * 1.03
        
        # 트레일링 스톱 업데이트
        if self.trailing_stop_active:
            if position_type == 'long':
                new_stop = self.highest_price * 0.9  # 최고가 대비 10% 트레일링
                if new_stop > self.trailing_stop_price:
                    self.trailing_stop_price = new_stop
                    self.position['stop_loss'] = max(self.position['stop_loss'], self.trailing_stop_price)
            else:
                new_stop = self.lowest_price * 1.1  # 최저가 대비 10% 트레일링
                if new_stop < self.trailing_stop_price:
                    self.trailing_stop_price = new_stop
                    self.position['stop_loss'] = min(self.position['stop_loss'], self.trailing_stop_price)
    
    def execute_partial_exit(self, df: pd.DataFrame, i: int, exit_ratio: float, reason: str):
        """부분 청산 실행"""
        if not self.position:
            return
        
        current = df.iloc[i]
        exit_price = current['close']
        
        # 청산할 수량 계산
        exit_size = self.position['size'] * exit_ratio
        
        # 거래 비용 적용
        if self.position['type'] == 'long':
            effective_exit_price = exit_price * (1 - self.slippage)
            pnl = (effective_exit_price - self.position['entry_price']) * exit_size
        else:
            effective_exit_price = exit_price * (1 + self.slippage)
            pnl = (self.position['entry_price'] - effective_exit_price) * exit_size
        
        # 수수료 차감
        exit_commission = exit_size * effective_exit_price * self.commission
        pnl -= exit_commission
        
        # 자본 업데이트
        self.capital += pnl
        
        # 포지션 크기 감소
        self.position['size'] -= exit_size
        
        # 부분 청산 기록
        trade = {
            'entry_time': self.position['entry_time'],
            'exit_time': current['timestamp'],
            'type': self.position['type'],
            'entry_price': self.position['entry_price'],
            'exit_price': effective_exit_price,
            'size': exit_size,
            'pnl': pnl,
            'pnl_pct': pnl / (exit_size * self.position['entry_price']),
            'reason': reason,
            'commission': exit_commission
        }
        
        self.trades.append(trade)
    
    def run_backtest(self, df: pd.DataFrame) -> Dict:
        """백테스트 실행"""
        print(f"\n  📊 백테스트 시작: {self.symbol}")
        print(f"    - 초기 자본: ${self.initial_capital}")
        print(f"    - 데이터 범위: {df.iloc[0]['timestamp']} ~ {df.iloc[-1]['timestamp']}")
        
        # 지표 계산
        df = self.calculate_indicators(df)
        
        # 백테스트 실행
        entry_signals = 0
        trades_executed = 0
        for i in range(len(df)):
            # 자산 기록
            self.equity_curve.append({
                'timestamp': df.iloc[i]['timestamp'],
                'equity': self.capital + (self.position['size'] * df.iloc[i]['close'] if self.position else 0)
            })
            
            # 포지션이 있는 경우
            if self.position:
                # 포지션 업데이트
                self.update_position(df, i)
                
                # 청산 체크
                should_exit, exit_reason = self.check_exit_conditions(df, i)
                if should_exit:
                    self.close_position(df, i, exit_reason)
            
            # 포지션이 없는 경우
            else:
                # 진입 체크
                should_enter, direction = self.check_entry_conditions(df, i)
                if should_enter:
                    entry_signals += 1
                    self.execute_trade(df, i, direction)
                    trades_executed += 1
        
        # 마지막 포지션 청산
        if self.position:
            self.close_position(df, len(df) - 1, "End of backtest")
        
        print(f"\n  📦 백테스트 결과:")
        print(f"    - 진입 신호: {entry_signals}개")
        print(f"    - 실행된 거래: {trades_executed}개")
        print(f"    - 최종 자본: ${self.capital:.2f}")
        print(f"    - 거래 횟수: {len(self.trades)}개")
        
        return self.calculate_metrics()
    
    def calculate_metrics(self) -> Dict:
        """성과 지표 계산"""
        if not self.trades:
            return {
                'total_return': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0,
                'win_rate': 0,
                'profit_factor': 0,
                'total_trades': 0
            }
        
        # 기본 메트릭
        total_return = (self.capital - self.initial_capital) / self.initial_capital * 100
        
        # 승률
        winning_trades = [t for t in self.trades if t['pnl'] > 0]
        win_rate = len(winning_trades) / len(self.trades) * 100
        
        # Profit Factor
        gross_profit = sum(t['pnl'] for t in self.trades if t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in self.trades if t['pnl'] < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # 최대 낙폭
        equity_df = pd.DataFrame(self.equity_curve)
        equity_df['cummax'] = equity_df['equity'].cummax()
        equity_df['drawdown'] = (equity_df['equity'] - equity_df['cummax']) / equity_df['cummax']
        max_drawdown = equity_df['drawdown'].min() * 100
        
        # Sharpe Ratio
        if len(equity_df) > 1:
            returns = equity_df['equity'].pct_change().dropna()
            sharpe_ratio = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
        else:
            sharpe_ratio = 0
        
        return {
            'total_return': total_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'total_trades': len(self.trades),
            'avg_win': np.mean([t['pnl_pct'] for t in winning_trades]) * 100 if winning_trades else 0,
            'avg_loss': np.mean([t['pnl_pct'] for t in self.trades if t['pnl'] < 0]) * 100 if len([t for t in self.trades if t['pnl'] < 0]) > 0 else 0
        }


class WalkForwardAnalysis:
    """Walk-Forward Analysis 실행 클래스"""
    
    def __init__(self, strategy_class, symbols: List[str], timeframe: str = '4h'):
        self.strategy_class = strategy_class
        self.symbols = symbols
        self.timeframe = timeframe
        self.results = []
        
        # 분석 기간 설정 (2021 Q1 ~ 2025 Q2)
        self.start_date = '2021-01-01'
        self.end_date = '2025-06-30'
        
        # Walk-Forward 윈도우 설정
        self.optimization_window = 180  # 6개월 최적화 기간
        self.test_window = 90  # 3개월 테스트 기간
        self.step_size = 90  # 3개월씩 이동
    
    def fetch_data(self, symbol: str) -> pd.DataFrame:
        """데이터 가져오기"""
        print(f"\n📊 Fetching data for {symbol}...")
        
        # 캐시 파일 확인
        cache_file = os.path.join(cache_dir, f"{symbol.replace('/', '_')}_{self.timeframe}_{self.start_date}_{self.end_date}.pkl")
        
        if os.path.exists(cache_file):
            print(f"  Loading from cache...")
            with open(cache_file, 'rb') as f:
                return pickle.load(f)
        
        # 데이터 가져오기
        fetcher = DataFetcherFixed()
        # fetch_data는 4h와 15m 데이터를 모두 반환하므로, timeframe에 맞는 것을 선택
        df_4h, df_15m = fetcher.fetch_data(symbol, self.start_date, self.end_date)
        
        # timeframe에 맞는 데이터 선택
        if self.timeframe == '4h':
            df = df_4h
        elif self.timeframe == '15m':
            df = df_15m
        else:
            # 1h인 경우 4h 데이터를 사용하거나 별도 처리 필요
            df = df_4h
            
        if df is None:
            raise ValueError(f"Failed to fetch data for {symbol}")
        
        # timestamp 컬럼 추가 (인덱스가 timestamp인 경우)
        if 'timestamp' not in df.columns:
            df = df.reset_index()
            if 'timestamp' not in df.columns:
                df.rename(columns={'index': 'timestamp'}, inplace=True)
        
        # 캐시 저장
        with open(cache_file, 'wb') as f:
            pickle.dump(df, f)
        
        print(f"  Data loaded: {len(df)} candles")
        return df
    
    def run_walk_forward(self, symbol: str) -> List[Dict]:
        """Walk-Forward Analysis 실행"""
        print(f"\n🚀 Running Walk-Forward Analysis for {symbol}")
        
        # 데이터 가져오기
        df = self.fetch_data(symbol)
        
        # Walk-Forward 윈도우 생성
        results = []
        start_idx = 0
        
        while start_idx + self.optimization_window + self.test_window <= len(df):
            # 최적화 기간
            opt_start = start_idx
            opt_end = start_idx + self.optimization_window
            
            # 테스트 기간
            test_start = opt_end
            test_end = test_start + self.test_window
            
            # 날짜 정보
            opt_start_date = df.iloc[opt_start]['timestamp']
            opt_end_date = df.iloc[opt_end-1]['timestamp']
            test_start_date = df.iloc[test_start]['timestamp']
            test_end_date = df.iloc[min(test_end-1, len(df)-1)]['timestamp']
            
            print(f"\n  Window {len(results)+1}:")
            print(f"    Optimization: {opt_start_date.strftime('%Y-%m-%d')} to {opt_end_date.strftime('%Y-%m-%d')}")
            print(f"    Test: {test_start_date.strftime('%Y-%m-%d')} to {test_end_date.strftime('%Y-%m-%d')}")
            
            # 최적화 기간 백테스트 (파라미터 검증용)
            opt_strategy = self.strategy_class(timeframe=self.timeframe, symbol=symbol)
            opt_df = df.iloc[opt_start:opt_end].copy()
            print(f"    Optimization data: {len(opt_df)} candles")
            opt_metrics = opt_strategy.run_backtest(opt_df)
            
            # 테스트 기간 백테스트
            test_strategy = self.strategy_class(timeframe=self.timeframe, symbol=symbol)
            test_df = df.iloc[test_start:test_end].copy()
            print(f"    Test data: {len(test_df)} candles")
            test_metrics = test_strategy.run_backtest(test_df)
            
            # 결과 저장
            result = {
                'window': len(results) + 1,
                'opt_start': opt_start_date,
                'opt_end': opt_end_date,
                'test_start': test_start_date,
                'test_end': test_end_date,
                'opt_metrics': opt_metrics,
                'test_metrics': test_metrics,
                'test_trades': test_strategy.trades,
                'test_equity_curve': test_strategy.equity_curve
            }
            
            results.append(result)
            
            print(f"    Test Return: {test_metrics['total_return']:.2f}%")
            print(f"    Test Sharpe: {test_metrics['sharpe_ratio']:.2f}")
            print(f"    Test MDD: {test_metrics['max_drawdown']:.2f}%")
            
            # 다음 윈도우로 이동
            start_idx += self.step_size
            
            # 종료 조건
            if test_end >= len(df):
                break
        
        return results
    
    def analyze_results(self, all_results: Dict[str, List[Dict]]) -> Dict:
        """전체 결과 분석"""
        print("\n" + "="*80)
        print("📈 WALK-FORWARD ANALYSIS SUMMARY")
        print("="*80)
        
        summary = {}
        
        for symbol, results in all_results.items():
            print(f"\n{symbol}:")
            print("-" * 40)
            
            # 테스트 기간 성과 집계
            test_returns = [r['test_metrics']['total_return'] for r in results]
            test_sharpes = [r['test_metrics']['sharpe_ratio'] for r in results]
            test_mdds = [r['test_metrics']['max_drawdown'] for r in results]
            test_win_rates = [r['test_metrics']['win_rate'] for r in results]
            
            # 전체 거래 통합
            all_trades = []
            for r in results:
                all_trades.extend(r['test_trades'])
            
            # 통계 계산
            avg_return = np.mean(test_returns)
            std_return = np.std(test_returns)
            avg_sharpe = np.mean(test_sharpes)
            avg_mdd = np.mean(test_mdds)
            avg_win_rate = np.mean(test_win_rates)
            
            # 승률 및 손익비
            winning_trades = [t for t in all_trades if t['pnl'] > 0]
            losing_trades = [t for t in all_trades if t['pnl'] < 0]
            
            if winning_trades and losing_trades:
                avg_win = np.mean([t['pnl_pct'] for t in winning_trades]) * 100
                avg_loss = np.mean([t['pnl_pct'] for t in losing_trades]) * 100
                profit_factor = sum(t['pnl'] for t in winning_trades) / abs(sum(t['pnl'] for t in losing_trades))
            else:
                avg_win = 0
                avg_loss = 0
                profit_factor = 0
            
            # 일관성 지표
            positive_windows = sum(1 for r in test_returns if r > 0)
            consistency = positive_windows / len(results) * 100
            
            print(f"  평균 수익률: {avg_return:.2f}% (±{std_return:.2f}%)")
            print(f"  평균 샤프 비율: {avg_sharpe:.2f}")
            print(f"  평균 최대 낙폭: {avg_mdd:.2f}%")
            print(f"  평균 승률: {avg_win_rate:.2f}%")
            print(f"  평균 승리: {avg_win:.2f}%")
            print(f"  평균 손실: {avg_loss:.2f}%")
            print(f"  Profit Factor: {profit_factor:.2f}")
            print(f"  일관성 (수익 윈도우): {consistency:.1f}%")
            print(f"  총 거래 수: {len(all_trades)}")
            
            summary[symbol] = {
                'avg_return': avg_return,
                'std_return': std_return,
                'avg_sharpe': avg_sharpe,
                'avg_mdd': avg_mdd,
                'avg_win_rate': avg_win_rate,
                'profit_factor': profit_factor,
                'consistency': consistency,
                'total_trades': len(all_trades),
                'results': results
            }
        
        return summary
    
    def plot_results(self, all_results: Dict[str, List[Dict]]):
        """결과 시각화"""
        for symbol, results in all_results.items():
            fig, axes = plt.subplots(3, 1, figsize=(15, 12))
            fig.suptitle(f'TFPE Strategy Walk-Forward Analysis - {symbol}', fontsize=16)
            
            # 1. 각 윈도우별 수익률
            ax1 = axes[0]
            windows = [f"W{r['window']}" for r in results]
            test_returns = [r['test_metrics']['total_return'] for r in results]
            opt_returns = [r['opt_metrics']['total_return'] for r in results]
            
            x = np.arange(len(windows))
            width = 0.35
            
            ax1.bar(x - width/2, opt_returns, width, label='Optimization', alpha=0.7)
            ax1.bar(x + width/2, test_returns, width, label='Test', alpha=0.7)
            ax1.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
            ax1.set_xlabel('Window')
            ax1.set_ylabel('Return (%)')
            ax1.set_title('Returns by Window')
            ax1.set_xticks(x)
            ax1.set_xticklabels(windows)
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            
            # 2. 누적 수익률
            ax2 = axes[1]
            cumulative_equity = []
            current_capital = 10000
            
            for r in results:
                for eq in r['test_equity_curve']:
                    cumulative_equity.append({
                        'timestamp': eq['timestamp'],
                        'equity': eq['equity']
                    })
            
            if cumulative_equity:
                eq_df = pd.DataFrame(cumulative_equity)
                ax2.plot(eq_df['timestamp'], eq_df['equity'], label='Equity Curve')
                ax2.axhline(y=10000, color='red', linestyle='--', alpha=0.5, label='Initial Capital')
                ax2.set_xlabel('Date')
                ax2.set_ylabel('Equity ($)')
                ax2.set_title('Cumulative Equity Curve')
                ax2.legend()
                ax2.grid(True, alpha=0.3)
                ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
                plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)
            
            # 3. 성과 지표 추이
            ax3 = axes[2]
            test_sharpes = [r['test_metrics']['sharpe_ratio'] for r in results]
            test_mdds = [abs(r['test_metrics']['max_drawdown']) for r in results]
            
            ax3_twin = ax3.twinx()
            line1 = ax3.plot(windows, test_sharpes, 'b-o', label='Sharpe Ratio')
            line2 = ax3_twin.plot(windows, test_mdds, 'r-s', label='Max Drawdown')
            
            ax3.set_xlabel('Window')
            ax3.set_ylabel('Sharpe Ratio', color='b')
            ax3_twin.set_ylabel('Max Drawdown (%)', color='r')
            ax3.set_title('Risk-Adjusted Performance')
            ax3.tick_params(axis='y', labelcolor='b')
            ax3_twin.tick_params(axis='y', labelcolor='r')
            
            # 범례 통합
            lines = line1 + line2
            labels = [l.get_label() for l in lines]
            ax3.legend(lines, labels, loc='best')
            ax3.grid(True, alpha=0.3)
            
            plt.tight_layout()
            
            # 파일 저장
            output_file = f'tfpe_walk_forward_{symbol.replace("/", "_")}.png'
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            print(f"\n📊 Chart saved: {output_file}")
            
            plt.show()
    
    def run(self):
        """전체 Walk-Forward Analysis 실행"""
        print(f"\n{'='*80}")
        print(f"TFPE DONCHIAN STRATEGY - WALK-FORWARD ANALYSIS")
        print(f"Period: {self.start_date} to {self.end_date}")
        print(f"Optimization Window: {self.optimization_window} days")
        print(f"Test Window: {self.test_window} days")
        print(f"Step Size: {self.step_size} days")
        print(f"{'='*80}")
        
        all_results = {}
        
        for symbol in self.symbols:
            results = self.run_walk_forward(symbol)
            all_results[symbol] = results
        
        # 결과 분석
        summary = self.analyze_results(all_results)
        
        # 차트 생성 제거 (사용자 요청)
        # self.plot_results(all_results)
        
        # 결과 저장
        output_file = 'tfpe_walk_forward_results.json'
        with open(output_file, 'w') as f:
            json_results = {}
            for symbol, results in all_results.items():
                json_results[symbol] = []
                for r in results:
                    json_results[symbol].append({
                        'window': r['window'],
                        'opt_start': r['opt_start'].strftime('%Y-%m-%d'),
                        'opt_end': r['opt_end'].strftime('%Y-%m-%d'),
                        'test_start': r['test_start'].strftime('%Y-%m-%d'),
                        'test_end': r['test_end'].strftime('%Y-%m-%d'),
                        'opt_metrics': r['opt_metrics'],
                        'test_metrics': r['test_metrics']
                    })
            json.dump(json_results, f, indent=2)
        
        print(f"\n📁 Results saved to: {output_file}")
        
        return summary


def main():
    """메인 실행 함수"""
    # 분석할 심볼 목록 - 비트코인만 분석
    symbols = ['BTC/USDT']
    
    # Walk-Forward Analysis 실행
    wf = WalkForwardAnalysis(TFPEDonchianStrategy, symbols, timeframe='4h')
    summary = wf.run()
    
    # 최종 추천
    print("\n" + "="*80)
    print("💡 STRATEGY RECOMMENDATIONS")
    print("="*80)
    
    best_symbol = max(summary.keys(), key=lambda x: summary[x]['avg_sharpe'])
    most_consistent = max(summary.keys(), key=lambda x: summary[x]['consistency'])
    
    print(f"\n최고 샤프 비율: {best_symbol} (Sharpe: {summary[best_symbol]['avg_sharpe']:.2f})")
    print(f"가장 일관성 있는: {most_consistent} (일관성: {summary[most_consistent]['consistency']:.1f}%)")
    
    print("\n전략 권장사항:")
    print("1. TFPE 전략은 트렌드 추종 + 풀백 진입의 균형잡힌 접근")
    print("2. ADX > 25 필터로 강한 트렌드에서만 진입")
    print("3. ATR 기반 동적 손절/익절로 시장 변동성 대응")
    print("4. 부분 익절로 수익 보호 및 추가 상승 여력 확보")
    print("5. 일일 손실 한도 5%로 리스크 관리 강화")


if __name__ == "__main__":
    main()