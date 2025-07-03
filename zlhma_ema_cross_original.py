"""
ZLHMA 50-200 EMA Golden/Death Cross Strategy - Walk-Forward Analysis
ZLHMA(Zero Lag Hull Moving Average) 50-200 EMA 크로스 전략 백테스팅
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


class ZLHMAEMACrossStrategy:
    """ZLHMA 50-200 EMA Cross Strategy"""
    
    def __init__(self, initial_capital: float = 10000, timeframe: str = '1h', symbol: str = 'BTC/USDT'):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position = None
        self.trades = []
        self.equity_curve = []
        self.last_trade_result = None  # 직전 거래 결과 추적
        self.consecutive_losses = 0  # 연속 손실 횟수 추적
        self.recent_trades = []  # 최근 거래 기록 (켈리 계산용)
        self.pyramiding_positions = []  # 피라미딩 포지션 관리
        self.max_pyramiding_levels = 3  # 최대 피라미딩 단계
        self.original_position_value = 0  # 원래 포지션 가치 저장
        self.accumulated_reduction = 0  # 누적 축소 비율
        
        # 추가 리스크 관리 파라미터
        self.daily_loss_limit = 0.03  # 일일 최대 손실 한도 3%
        self.daily_loss = 0  # 오늘의 누적 손실
        self.last_trade_date = None  # 마지막 거래 날짜
        self.trading_suspended_until = None  # 거래 재개 시간
        self.initial_stop_loss = 0.02  # 초기 타이트한 손절 2%
        self.trailing_stop_active = False  # 트레일링 스톱 활성화 여부
        self.trailing_stop_price = None  # 트레일링 스톱 가격
        self.highest_price = None  # 포지션 보유 중 최고가
        self.lowest_price = None  # 포지션 보유 중 최저가
        
        # 거래 비용 (심볼에 따라 조정)
        self.symbol = symbol
        if 'XRP' in symbol:
            self.slippage = 0.002  # XRP는 슬리피지 0.2%
        else:
            self.slippage = 0.001  # 기본 슬리피지 0.1%
        self.commission = 0.0006  # 수수료 0.06% (메이커)
        
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
        
        # ZLHMA 파라미터
        self.zlhma_period = 14  # ZLHMA 기간
        
        # EMA 파라미터
        self.fast_ema_period = 50  # 단기 EMA
        self.slow_ema_period = 200  # 장기 EMA
        
        self.leverage = 8  # 레버리지 8배
        self.max_position_loss_pct = 0.08  # 포지션당 최대 손실 8%
        
        # ATR 계산 및 저장
        self.atr_period = 14
        self.current_atr = None
        
        # ADX 필터 파라미터 (심볼에 따라 조정)
        self.adx_period = 14
        if 'XRP' in symbol:
            self.adx_threshold = 20  # XRP는 ADX 20
        elif 'ETH' in symbol:
            self.adx_threshold = 23  # ETH는 ADX 23
        else:
            self.adx_threshold = 25  # BTC는 기본 ADX 25
        
        # 부분 익절 파라미터 - 3단계 익절
        self.partial_exit_1_pct = 5.0   # 첫 번째 부분 익절 수익률 (5%)
        self.partial_exit_2_pct = 10.0  # 두 번째 부분 익절 수익률 (10%)
        self.partial_exit_3_pct = 15.0  # 세 번째 부분 익절 수익률 (15%)
        self.partial_exit_1_ratio = 0.25  # 첫 번째 익절 비율 (25%)
        self.partial_exit_2_ratio = 0.35  # 두 번째 익절 비율 (35%)
        self.partial_exit_3_ratio = 0.40  # 세 번째 익절 비율 (40%)
        self.partial_exit_1_done = False  # 첫 번째 부분 익절 완료 여부
        self.partial_exit_2_done = False  # 두 번째 부분 익절 완료 여부
        self.partial_exit_3_done = False  # 세 번째 부분 익절 완료 여부
        
        print(f"  ZLHMA 50-200 EMA Cross Strategy initialized:")
        print(f"  • Symbol: {symbol}")
        print(f"  • Timeframe: {timeframe}")
        print(f"  • ZLHMA Period: {self.zlhma_period}")
        print(f"  • EMA Periods: Fast={self.fast_ema_period}, Slow={self.slow_ema_period}")
        print(f"  • Leverage: {self.leverage}x")
        print(f"  • Position Sizing: Half Kelly Criterion (5-20% of capital, start 10%)")
        print(f"  • Entry: ZLHMA momentum + EMA cross confirmation")
        print(f"  • Max Position Loss: {self.max_position_loss_pct*100:.0f}% (Full Exit)")
        print(f"  • Stop Loss: ATR-based dynamic stop (1.5*ATR, max 2%), then trailing stop")
        print(f"  • Trailing Stop: Activates at 3% profit, trails by 10% from peak")
        print(f"  • Daily Loss Limit: {self.daily_loss_limit*100:.0f}% (24h suspension if exceeded)")
        print(f"  • Pyramiding: 3 levels at 3%, 6%, 9% profit")
        print(f"  • Trading Costs: {self.slippage*100:.1f}% slippage, {self.commission*100:.2f}% commission")
        print(f"  • Market Filter: ADX > {self.adx_threshold} required for entry")
        print(f"  • Consecutive Loss Adjustment: 3+ losses→70%, 5+ losses→50%, 7+ losses→30%")
        print(f"  • Partial Take Profit: 25% at +5%, 35% at +10%, 40% at +15%")
    
    def calculate_wma(self, values: pd.Series, period: int) -> pd.Series:
        """Weighted Moving Average 계산"""
        weights = np.arange(1, period + 1)
        wma = values.rolling(period).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
        return wma
    
    def calculate_hma(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Hull Moving Average 계산"""
        half_length = int(period / 2)
        sqrt_length = int(np.sqrt(period))
        
        # Step 1: Calculate WMA with period/2
        wma_half = self.calculate_wma(df['close'], half_length)
        
        # Step 2: Calculate WMA with full period
        wma_full = self.calculate_wma(df['close'], period)
        
        # Step 3: 2*WMA(period/2) - WMA(period)
        raw_hma = 2 * wma_half - wma_full
        
        # Step 4: WMA(sqrt(period)) of the result
        hma = self.calculate_wma(raw_hma, sqrt_length)
        
        return hma
    
    def calculate_zlhma(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Zero Lag Hull Moving Average 계산"""
        # Step 1: Calculate standard HMA
        hma = self.calculate_hma(df, period)
        
        # Step 2: Calculate the lag
        lag = int((period - 1) / 2)
        
        # Step 3: Calculate Zero Lag HMA
        # ZLHMA = HMA + (HMA - HMA[lag])
        zlhma = hma + (hma - hma.shift(lag))
        
        return zlhma
    
    def calculate_ema(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Exponential Moving Average 계산"""
        return df['close'].ewm(span=period, adjust=False).mean()
    
    def calculate_adx(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """ADX (Average Directional Index) 계산"""
        # True Range 계산
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift(1))
        low_close = abs(df['low'] - df['close'].shift(1))
        
        df['tr'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        # Directional Movement 계산
        df['dm_plus'] = np.where(
            (df['high'] - df['high'].shift(1)) > (df['low'].shift(1) - df['low']),
            np.maximum(df['high'] - df['high'].shift(1), 0), 0
        )
        df['dm_minus'] = np.where(
            (df['low'].shift(1) - df['low']) > (df['high'] - df['high'].shift(1)),
            np.maximum(df['low'].shift(1) - df['low'], 0), 0
        )
        
        # Smoothed indicators
        atr = df['tr'].rolling(period).mean()
        di_plus = 100 * (df['dm_plus'].rolling(period).mean() / atr)
        di_minus = 100 * (df['dm_minus'].rolling(period).mean() / atr)
        
        # ADX 계산
        dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus)
        df['adx'] = dx.rolling(period).mean()
        
        return df
    
    def check_entry_conditions(self, df: pd.DataFrame, index: int, position_type: str) -> dict:
        """진입 조건 확인"""
        result = {
            'can_enter': False,
            'signals': [],
            'strength': 0
        }
        
        # 필수 데이터 확인
        if index < self.slow_ema_period:  # 최소 200개 캔들 필요
            return result
        
        current_price = df['close'].iloc[index]
        zlhma = df['zlhma'].iloc[index]
        zlhma_prev = df['zlhma'].iloc[index-1]
        zlhma_prev2 = df['zlhma'].iloc[index-2]
        
        fast_ema = df['ema_50'].iloc[index]
        slow_ema = df['ema_200'].iloc[index]
        fast_ema_prev = df['ema_50'].iloc[index-1]
        slow_ema_prev = df['ema_200'].iloc[index-1]
        
        if position_type == 'LONG':
            # 1. EMA 골든크로스
            if fast_ema > slow_ema and fast_ema_prev <= slow_ema_prev:
                result['signals'].append('EMA_GOLDEN_CROSS')
                result['strength'] += 2  # 메인 신호이므로 가중치 2
            
            # 2. ZLHMA 상승 모멘텀
            if zlhma > zlhma_prev and zlhma_prev > zlhma_prev2:
                result['signals'].append('ZLHMA_UPWARD_MOMENTUM')
                result['strength'] += 1
            
            # 3. 가격이 ZLHMA 위
            if current_price > zlhma:
                result['signals'].append('PRICE_ABOVE_ZLHMA')
                result['strength'] += 0.5
            
            # 4. 가격이 두 EMA 위
            if current_price > fast_ema and current_price > slow_ema:
                result['signals'].append('PRICE_ABOVE_EMAS')
                result['strength'] += 0.5
            
        else:  # SHORT
            # 1. EMA 데드크로스
            if fast_ema < slow_ema and fast_ema_prev >= slow_ema_prev:
                result['signals'].append('EMA_DEATH_CROSS')
                result['strength'] += 2  # 메인 신호이므로 가중치 2
            
            # 2. ZLHMA 하락 모멘텀
            if zlhma < zlhma_prev and zlhma_prev < zlhma_prev2:
                result['signals'].append('ZLHMA_DOWNWARD_MOMENTUM')
                result['strength'] += 1
            
            # 3. 가격이 ZLHMA 아래
            if current_price < zlhma:
                result['signals'].append('PRICE_BELOW_ZLHMA')
                result['strength'] += 0.5
            
            # 4. 가격이 두 EMA 아래
            if current_price < fast_ema and current_price < slow_ema:
                result['signals'].append('PRICE_BELOW_EMAS')
                result['strength'] += 0.5
        
        # 최소 2.5 이상의 신호 강도 필요 (EMA 크로스 + 추가 확인)
        result['can_enter'] = result['strength'] >= 2.5
        
        return result
    
    def check_exit_conditions(self, df: pd.DataFrame, index: int, position_type: str) -> dict:
        """종료 조건 확인"""
        result = {
            'should_exit': False,
            'exit_type': None,
            'reasons': []
        }
        
        current_price = df['close'].iloc[index]
        high = df['high'].iloc[index]
        low = df['low'].iloc[index]
        zlhma = df['zlhma'].iloc[index]
        fast_ema = df['ema_50'].iloc[index]
        slow_ema = df['ema_200'].iloc[index]
        
        if position_type == 'LONG':
            # 1. EMA 데드크로스 (주요 청산 신호)
            if fast_ema < slow_ema:
                result['should_exit'] = True
                result['exit_type'] = 'EMA_DEATH_CROSS'
                result['reasons'].append('EMA Death Cross')
            
            # 2. ZLHMA 아래로 돌파
            elif current_price < zlhma:
                result['should_exit'] = True
                result['exit_type'] = 'ZLHMA_BREAK'
                result['reasons'].append('Price broke below ZLHMA')
            
            # 3. 50 EMA 아래로 강한 돌파
            elif low < fast_ema * 0.98:  # 2% 아래
                result['should_exit'] = True
                result['exit_type'] = 'FAST_EMA_BREAK'
                result['reasons'].append('Strong break below 50 EMA')
            
        else:  # SHORT
            # 1. EMA 골든크로스 (주요 청산 신호)
            if fast_ema > slow_ema:
                result['should_exit'] = True
                result['exit_type'] = 'EMA_GOLDEN_CROSS'
                result['reasons'].append('EMA Golden Cross')
            
            # 2. ZLHMA 위로 돌파
            elif current_price > zlhma:
                result['should_exit'] = True
                result['exit_type'] = 'ZLHMA_BREAK'
                result['reasons'].append('Price broke above ZLHMA')
            
            # 3. 50 EMA 위로 강한 돌파
            elif high > fast_ema * 1.02:  # 2% 위
                result['should_exit'] = True
                result['exit_type'] = 'FAST_EMA_BREAK'
                result['reasons'].append('Strong break above 50 EMA')
        
        return result
    
    def should_take_trade(self) -> bool:
        """필터: 모든 신호에서 거래"""
        return True
    
    def calculate_consecutive_losses(self, trades_df: pd.DataFrame) -> int:
        """최대 연속 손실 횟수 계산"""
        if len(trades_df) == 0:
            return 0
        
        max_consecutive = 0
        current_consecutive = 0
        
        for _, trade in trades_df.iterrows():
            if trade['net_pnl_pct'] < 0:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0
        
        return max_consecutive
    
    def calculate_position_size_with_consecutive_loss_adjustment(self, kelly_fraction: float) -> float:
        """연속 손실에 따른 포지션 크기 조정"""
        # 기본 포지션 크기
        base_position_size = self.capital * kelly_fraction
        
        # 연속 손실에 따른 축소 비율
        if self.consecutive_losses >= 7:
            position_multiplier = 0.3  # 70% 축소
            print(f"    Consecutive losses: {self.consecutive_losses} - Position reduced to 30%")
        elif self.consecutive_losses >= 5:
            position_multiplier = 0.5  # 50% 축소
            print(f"    Consecutive losses: {self.consecutive_losses} - Position reduced to 50%")
        elif self.consecutive_losses >= 3:
            position_multiplier = 0.7  # 30% 축소
            print(f"    Consecutive losses: {self.consecutive_losses} - Position reduced to 70%")
        else:
            position_multiplier = 1.0  # 정상 크기
        
        return base_position_size * position_multiplier
    
    def check_pyramiding_opportunity(self, position_type: str, current_price: float, 
                                   df: pd.DataFrame, index: int) -> bool:
        """피라미딩 기회 확인"""
        if not self.position or len(self.pyramiding_positions) >= self.max_pyramiding_levels:
            return False
        
        if self.position['type'] != position_type:
            return False
        
        # 현재 수익률 확인
        if position_type == 'LONG':
            current_pnl_pct = (current_price / self.position['entry_price'] - 1) * 100
        else:  # SHORT
            current_pnl_pct = (self.position['entry_price'] / current_price - 1) * 100
        
        # 하이브리드 피라미딩 단계별 진입 조건 (3단계)
        pyramid_levels = len(self.pyramiding_positions)
        
        if pyramid_levels == 0:
            # 첫 번째 피라미딩: 3% 가격 상승
            return current_pnl_pct >= 3.0
        elif pyramid_levels == 1:
            # 두 번째 피라미딩: 6% 가격 상승
            return current_pnl_pct >= 6.0
        elif pyramid_levels == 2:
            # 세 번째 피라미딩: 9% 가격 상승
            return current_pnl_pct >= 9.0
        
        return False
    
    def add_pyramiding_position(self, position_type: str, price: float, time: datetime, index: int):
        """피라미딩 포지션 추가"""
        # 피라미딩 단계별 크기 조정
        pyramid_levels = len(self.pyramiding_positions)
        
        # 피라미딩 크기 설정 (3단계)
        if pyramid_levels == 0:
            # 첫 번째 피라미딩: 원 포지션의 75%
            pyramid_size = self.original_position_value * 0.75
        elif pyramid_levels == 1:
            # 두 번째 피라미딩: 원 포지션의 50%
            pyramid_size = self.original_position_value * 0.50
        else:
            # 세 번째 피라미딩: 원 포지션의 25%
            pyramid_size = self.original_position_value * 0.25
        
        actual_pyramid_size = pyramid_size * self.leverage
        shares = actual_pyramid_size / price
        
        pyramid_position = {
            'type': position_type,
            'entry_price': price,
            'entry_time': time,
            'shares': shares,
            'entry_index': index,
            'position_value': pyramid_size,
            'leveraged_value': actual_pyramid_size,
            'stop_loss_price': None
        }
        
        # 피라미딩 포지션에는 개별 손절 설정하지 않음 (메인 포지션과 함께 관리)
        
        self.pyramiding_positions.append(pyramid_position)
        print(f"    Pyramiding Level {len(self.pyramiding_positions)}: {position_type} at {price:.2f} (Size: {pyramid_size/self.original_position_value*100:.0f}%)")
    
    def calculate_kelly_position_size(self) -> float:
        """켈리 기준을 활용한 동적 포지션 사이즈 계산"""
        # 최소 20개 이상의 거래가 필요
        if len(self.recent_trades) < 20:
            return 0.10  # 기본값: 자본의 10%
        
        # 승률과 평균 손익 계산
        wins = [t for t in self.recent_trades if t['pnl'] > 0]
        losses = [t for t in self.recent_trades if t['pnl'] <= 0]
        
        if len(wins) == 0 or len(losses) == 0:
            return 0.10  # 기본값 10%
        
        win_rate = len(wins) / len(self.recent_trades)
        avg_win = np.mean([t['pnl_pct'] for t in wins])
        avg_loss = abs(np.mean([t['pnl_pct'] for t in losses]))
        
        # 켈리 공식: f = (p * b - q) / b
        # p = 승률, q = 패율, b = 평균승리 / 평균손실
        if avg_loss == 0:
            return 0.15  # 기본값을 15%로 설정
        
        b = avg_win / avg_loss
        p = win_rate
        q = 1 - p
        
        kelly_fraction = (p * b - q) / b
        
        # 하프 켈리 사용 (50% 켈리)
        kelly_fraction = kelly_fraction * 0.5
        
        # 최소 5%, 최대 20%로 제한
        kelly_fraction = max(0.05, min(0.2, kelly_fraction))
        
        return kelly_fraction
    
    def enter_position(self, position_type: str, price: float, time: datetime, index: int):
        """포지션 진입"""
        # 항상 현재 보유 자본의 켈리 비율로 시작 (매 거래마다 리셋)
        kelly_fraction = self.calculate_kelly_position_size()
        
        # 연속 손실에 따른 포지션 크기 조정
        position_size = self.calculate_position_size_with_consecutive_loss_adjustment(kelly_fraction)
        
        # 레버리지 적용
        actual_position_size = position_size * self.leverage
        shares = actual_position_size / price
        
        # 수수료 차감
        commission_cost = position_size * self.commission
        self.capital -= commission_cost
        
        self.position = {
            'type': position_type,
            'entry_price': price,
            'entry_time': time,
            'shares': shares,
            'entry_index': index,
            'position_value': position_size,
            'leveraged_value': actual_position_size,
            'stop_loss_price': None  # 손절가 초기화
        }
        
        # 피라미딩 리스트 초기화
        self.pyramiding_positions = []
        self.original_position_value = position_size  # 원래 포지션 크기 저장
        self.trailing_stop_active = False  # 트레일링 스톱 초기화
        self.trailing_stop_price = None
        self.highest_price = None
        self.lowest_price = None
        # 부분 익절 플래그 초기화
        self.partial_exit_1_done = False
        self.partial_exit_2_done = False
        self.partial_exit_3_done = False
    
    def partial_exit_position(self, exit_ratio: float, price: float, time: datetime, index: int, exit_reason: str):
        """부분 익절 실행"""
        if self.position is None:
            return
        
        # 종료할 포지션 크기 계산
        exit_shares = self.position['shares'] * exit_ratio
        exit_position_value = self.position['position_value'] * exit_ratio
        
        # 손익 계산
        if self.position['type'] == 'LONG':
            pnl = exit_shares * (price - self.position['entry_price'])
        else:  # SHORT
            pnl = exit_shares * (self.position['entry_price'] - price)
        
        # 슬리피지 적용
        if self.position['type'] == 'LONG':
            actual_exit_price = price * (1 - self.slippage)
        else:  # SHORT  
            actual_exit_price = price * (1 + self.slippage)
        
        # 실제 손익 재계산
        if self.position['type'] == 'LONG':
            pnl = exit_shares * (actual_exit_price - self.position['entry_price'])
        else:  # SHORT
            pnl = exit_shares * (self.position['entry_price'] - actual_exit_price)
        
        # 수수료 차감
        commission_cost = exit_position_value * self.commission
        pnl -= commission_cost
        
        # 자본 업데이트
        self.capital += pnl
        
        # 남은 포지션 업데이트
        self.position['shares'] -= exit_shares
        self.position['position_value'] -= exit_position_value
        
        print(f"    Partial Exit ({exit_ratio*100:.0f}%): {self.position['type']} at {actual_exit_price:.2f}, PnL: ${pnl:.2f}")
    
    def exit_position(self, price: float, time: datetime, index: int, exit_type: str):
        """포지션 종료"""
        if self.position is None:
            return
        
        position_type = self.position['type']
        total_shares = self.position['shares']
        
        # 피라미딩 포지션 포함한 총 shares 계산
        for pyramid_pos in self.pyramiding_positions:
            total_shares += pyramid_pos['shares']
        
        # 전체 손익 계산
        total_pnl = 0
        
        # 메인 포지션 손익
        if position_type == 'LONG':
            pnl = self.position['shares'] * (price - self.position['entry_price'])
        else:  # SHORT
            pnl = self.position['shares'] * (self.position['entry_price'] - price)
        total_pnl += pnl
        
        # 피라미딩 포지션 손익
        for pyramid_pos in self.pyramiding_positions:
            if position_type == 'LONG':
                pyramid_pnl = pyramid_pos['shares'] * (price - pyramid_pos['entry_price'])
            else:  # SHORT
                pyramid_pnl = pyramid_pos['shares'] * (pyramid_pos['entry_price'] - price)
            total_pnl += pyramid_pnl
        
        # 슬리피지 적용
        if position_type == 'LONG':
            actual_exit_price = price * (1 - self.slippage)
        else:  # SHORT
            actual_exit_price = price * (1 + self.slippage)
        
        # 슬리피지 반영한 실제 손익 재계산
        total_pnl = 0
        if position_type == 'LONG':
            total_pnl = self.position['shares'] * (actual_exit_price - self.position['entry_price'])
        else:  # SHORT
            total_pnl = self.position['shares'] * (self.position['entry_price'] - actual_exit_price)
        
        for pyramid_pos in self.pyramiding_positions:
            if position_type == 'LONG':
                pyramid_pnl = pyramid_pos['shares'] * (actual_exit_price - pyramid_pos['entry_price'])
            else:  # SHORT
                pyramid_pnl = pyramid_pos['shares'] * (pyramid_pos['entry_price'] - actual_exit_price)
            total_pnl += pyramid_pnl
        
        # 수수료 차감
        total_position_value = self.position['position_value']
        for pyramid_pos in self.pyramiding_positions:
            total_position_value += pyramid_pos['position_value']
        
        commission_cost = total_position_value * self.commission
        total_pnl -= commission_cost
        
        # 자본 업데이트
        self.capital += total_pnl
        
        # 거래 기록 저장
        self.trades.append({
            'entry_time': self.position['entry_time'],
            'exit_time': time,
            'type': position_type,
            'entry_price': self.position['entry_price'],
            'exit_price': actual_exit_price,
            'shares': total_shares,
            'position_value': total_position_value,
            'pnl': total_pnl,
            'pnl_pct': total_pnl / total_position_value,
            'exit_type': exit_type,
            'pyramiding_levels': len(self.pyramiding_positions),
            'partial_exits': {
                'level_1': self.partial_exit_1_done,
                'level_2': self.partial_exit_2_done,
                'level_3': self.partial_exit_3_done
            }
        })
        
        # 최근 거래 리스트 업데이트 (Kelly 계산용)
        self.recent_trades.append(self.trades[-1])
        if len(self.recent_trades) > 50:  # 최근 50개만 유지
            self.recent_trades.pop(0)
        
        # 연속 손실 업데이트
        if total_pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        
        # 포지션 초기화
        self.position = None
        self.pyramiding_positions = []
        self.original_position_value = 0
        
        print(f"  Exit {position_type} at {actual_exit_price:.2f}, PnL: ${total_pnl:.2f} ({total_pnl/total_position_value*100:.2f}%), Reason: {exit_type}")
    
    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """ATR (Average True Range) 계산"""
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift(1))
        low_close = abs(df['low'] - df['close'].shift(1))
        
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        return atr
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """모든 지표 계산"""
        # ZLHMA
        df['zlhma'] = self.calculate_zlhma(df, self.zlhma_period)
        
        # EMA
        df['ema_50'] = self.calculate_ema(df, self.fast_ema_period)
        df['ema_200'] = self.calculate_ema(df, self.slow_ema_period)
        
        # ATR
        df['atr'] = self.calculate_atr(df, self.atr_period)
        
        # ADX
        df = self.calculate_adx(df, self.adx_period)
        
        # NaN 처리
        df = df.fillna(method='ffill').fillna(method='bfill')
        
        return df
    
    def backtest(self, df: pd.DataFrame, print_trades: bool = True, plot_chart: bool = False):
        """백테스트 실행"""
        # 지표 계산
        df = self.calculate_indicators(df)
        
        # 백테스트 루프
        for i in range(self.slow_ema_period + 1, len(df)):
            current_time = df.index[i]
            current_price = df['close'].iloc[i]
            self.current_atr = df['atr'].iloc[i]
            
            # 일일 손실 리셋 (날짜 변경 시)
            if self.last_trade_date and current_time.date() != self.last_trade_date:
                self.daily_loss = 0
                self.last_trade_date = current_time.date()
            
            # 거래 정지 확인
            if self.trading_suspended_until and current_time < self.trading_suspended_until:
                continue
            
            # 포지션이 있는 경우
            if self.position:
                # 손절가 업데이트 (ATR 기반)
                if self.position['stop_loss_price'] is None:
                    # 초기 손절가 설정: ATR의 1.5배 또는 2% 중 작은 값
                    atr_stop = self.current_atr * 1.5
                    pct_stop = current_price * self.initial_stop_loss
                    stop_distance = min(atr_stop, pct_stop)
                    
                    if self.position['type'] == 'LONG':
                        self.position['stop_loss_price'] = self.position['entry_price'] - stop_distance
                    else:  # SHORT
                        self.position['stop_loss_price'] = self.position['entry_price'] + stop_distance
                
                # 현재 수익률 계산
                if self.position['type'] == 'LONG':
                    current_pnl_pct = (current_price / self.position['entry_price'] - 1) * 100
                else:  # SHORT
                    current_pnl_pct = (self.position['entry_price'] / current_price - 1) * 100
                
                # 트레일링 스톱 활성화 (3% 수익 시)
                if current_pnl_pct >= 3.0 and not self.trailing_stop_active:
                    self.trailing_stop_active = True
                    if self.position['type'] == 'LONG':
                        self.trailing_stop_price = current_price * 0.90  # 현재가의 90%
                        self.highest_price = current_price
                    else:  # SHORT
                        self.trailing_stop_price = current_price * 1.10  # 현재가의 110%
                        self.lowest_price = current_price
                    print(f"    Trailing stop activated at {self.trailing_stop_price:.2f}")
                
                # 트레일링 스톱 업데이트
                if self.trailing_stop_active:
                    if self.position['type'] == 'LONG':
                        if current_price > self.highest_price:
                            self.highest_price = current_price
                            self.trailing_stop_price = current_price * 0.90
                    else:  # SHORT
                        if current_price < self.lowest_price:
                            self.lowest_price = current_price
                            self.trailing_stop_price = current_price * 1.10
                
                # 손절 체크
                stop_hit = False
                if self.position['type'] == 'LONG':
                    if current_price <= self.position['stop_loss_price']:
                        stop_hit = True
                        exit_reason = "Stop Loss"
                    elif self.trailing_stop_active and current_price <= self.trailing_stop_price:
                        stop_hit = True
                        exit_reason = "Trailing Stop"
                else:  # SHORT
                    if current_price >= self.position['stop_loss_price']:
                        stop_hit = True
                        exit_reason = "Stop Loss"
                    elif self.trailing_stop_active and current_price >= self.trailing_stop_price:
                        stop_hit = True
                        exit_reason = "Trailing Stop"
                
                # 최대 손실 체크
                if current_pnl_pct <= -self.max_position_loss_pct * 100:
                    stop_hit = True
                    exit_reason = "Max Loss"
                
                if stop_hit:
                    self.exit_position(current_price, current_time, i, exit_reason)
                    
                    # 일일 손실 한도 체크
                    if self.trades[-1]['pnl'] < 0:
                        self.daily_loss += abs(self.trades[-1]['pnl'] / self.capital)
                        if self.daily_loss >= self.daily_loss_limit:
                            self.trading_suspended_until = current_time + timedelta(hours=24)
                            print(f"    Daily loss limit reached. Trading suspended until {self.trading_suspended_until}")
                    continue
                
                # 부분 익절 체크
                if not self.partial_exit_1_done and current_pnl_pct >= self.partial_exit_1_pct:
                    self.partial_exit_position(self.partial_exit_1_ratio, current_price, current_time, i, f"Partial TP1 ({self.partial_exit_1_pct}%)")
                    self.partial_exit_1_done = True
                elif not self.partial_exit_2_done and current_pnl_pct >= self.partial_exit_2_pct:
                    self.partial_exit_position(self.partial_exit_2_ratio, current_price, current_time, i, f"Partial TP2 ({self.partial_exit_2_pct}%)")
                    self.partial_exit_2_done = True
                elif not self.partial_exit_3_done and current_pnl_pct >= self.partial_exit_3_pct:
                    self.partial_exit_position(self.partial_exit_3_ratio, current_price, current_time, i, f"Partial TP3 ({self.partial_exit_3_pct}%)")
                    self.partial_exit_3_done = True
                
                # 피라미딩 체크
                if self.check_pyramiding_opportunity(self.position['type'], current_price, df, i):
                    self.add_pyramiding_position(self.position['type'], current_price, current_time, i)
                
                # 전략적 청산 조건 체크
                exit_conditions = self.check_exit_conditions(df, i, self.position['type'])
                if exit_conditions['should_exit']:
                    self.exit_position(current_price, current_time, i, exit_conditions['exit_type'])
                    continue
            
            # 포지션이 없는 경우 - 진입 조건 체크
            else:
                # ADX 필터
                if df['adx'].iloc[i] < self.adx_threshold:
                    continue
                
                # Long 진입 체크
                long_conditions = self.check_entry_conditions(df, i, 'LONG')
                if long_conditions['can_enter'] and self.should_take_trade():
                    print(f"\n  Entry Signal: LONG")
                    print(f"    Signals: {', '.join(long_conditions['signals'])}")
                    print(f"    Signal Strength: {long_conditions['strength']:.1f}")
                    self.enter_position('LONG', current_price, current_time, i)
                    if print_trades:
                        print(f"    Enter LONG at {current_price:.2f} on {current_time}")
                    continue
                
                # Short 진입 체크
                short_conditions = self.check_entry_conditions(df, i, 'SHORT')
                if short_conditions['can_enter'] and self.should_take_trade():
                    print(f"\n  Entry Signal: SHORT")
                    print(f"    Signals: {', '.join(short_conditions['signals'])}")
                    print(f"    Signal Strength: {short_conditions['strength']:.1f}")
                    self.enter_position('SHORT', current_price, current_time, i)
                    if print_trades:
                        print(f"    Enter SHORT at {current_price:.2f} on {current_time}")
                    continue
            
            # Equity curve 업데이트
            total_equity = self.capital
            if self.position:
                # 미실현 손익 계산
                unrealized_pnl = 0
                if self.position['type'] == 'LONG':
                    unrealized_pnl = self.position['shares'] * (current_price - self.position['entry_price'])
                else:  # SHORT
                    unrealized_pnl = self.position['shares'] * (self.position['entry_price'] - current_price)
                
                # 피라미딩 포지션 미실현 손익
                for pyramid_pos in self.pyramiding_positions:
                    if self.position['type'] == 'LONG':
                        unrealized_pnl += pyramid_pos['shares'] * (current_price - pyramid_pos['entry_price'])
                    else:  # SHORT
                        unrealized_pnl += pyramid_pos['shares'] * (pyramid_pos['entry_price'] - current_price)
                
                total_equity += unrealized_pnl
            
            self.equity_curve.append({
                'time': current_time,
                'equity': total_equity,
                'capital': self.capital
            })
        
        # 마지막 포지션 청산
        if self.position:
            self.exit_position(df['close'].iloc[-1], df.index[-1], len(df)-1, "End of backtest")
        
        return self.generate_report(df)
    
    def generate_report(self, df: pd.DataFrame) -> dict:
        """백테스트 리포트 생성"""
        if not self.trades:
            return {
                'total_return': 0,
                'win_rate': 0,
                'profit_factor': 0,
                'max_drawdown': 0,
                'sharpe_ratio': 0,
                'total_trades': 0
            }
        
        # 거래 통계
        total_trades = len(self.trades)
        winning_trades = [t for t in self.trades if t['pnl'] > 0]
        losing_trades = [t for t in self.trades if t['pnl'] <= 0]
        
        win_rate = len(winning_trades) / total_trades * 100 if total_trades > 0 else 0
        
        # 수익률
        total_return = (self.capital - self.initial_capital) / self.initial_capital * 100
        
        # Profit Factor
        gross_profit = sum([t['pnl'] for t in winning_trades]) if winning_trades else 0
        gross_loss = abs(sum([t['pnl'] for t in losing_trades])) if losing_trades else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # 최대 낙폭
        equity_df = pd.DataFrame(self.equity_curve)
        equity_df['drawdown'] = (equity_df['equity'] / equity_df['equity'].cummax() - 1) * 100
        max_drawdown = equity_df['drawdown'].min()
        
        # Sharpe Ratio (간단 계산)
        if len(equity_df) > 1:
            returns = equity_df['equity'].pct_change().dropna()
            sharpe_ratio = returns.mean() / returns.std() * np.sqrt(252 * self.candles_per_day) if returns.std() > 0 else 0
        else:
            sharpe_ratio = 0
        
        return {
            'total_return': total_return,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'avg_win': np.mean([t['pnl_pct'] * 100 for t in winning_trades]) if winning_trades else 0,
            'avg_loss': np.mean([t['pnl_pct'] * 100 for t in losing_trades]) if losing_trades else 0,
            'largest_win': max([t['pnl'] for t in winning_trades]) if winning_trades else 0,
            'largest_loss': min([t['pnl'] for t in losing_trades]) if losing_trades else 0
        }


def run_walk_forward_analysis(start_date: str = '2021-01-01', end_date: str = '2025-06-30'):
    """Walk-Forward Analysis 실행"""
    print(f"\n{'='*80}")
    print(f"ZLHMA 50-200 EMA Cross Strategy - Walk-Forward Analysis")
    print(f"Period: {start_date} to {end_date}")
    print(f"{'='*80}\n")
    
    # 데이터 가져오기
    fetcher = DataFetcherFixed(use_cache=True)
    
    # 전체 기간 데이터 가져오기
    print(f"📊 Fetching complete dataset for BTC/USDT...")
    # 1시간봉 데이터를 위해 fetch_1h 메서드 사용 (없으면 생성해야 함)
    df_1h, _ = fetcher.fetch_data('BTC/USDT', start_date, end_date)
    
    if df_1h is None or len(df_1h) == 0:
        print("❌ Failed to fetch data")
        return
    
    print(f"✅ Fetched {len(df_1h)} candles (treating as 1H)")
    print("⚠️ Note: DataFetcherFixed returns 4H data. For accurate 1H backtesting, use real 1H data.")
    
    # Walk-Forward 윈도우 설정
    quarters = [
        ('2021-Q1', '2021-01-01', '2021-03-31'),
        ('2021-Q2', '2021-04-01', '2021-06-30'),
        ('2021-Q3', '2021-07-01', '2021-09-30'),
        ('2021-Q4', '2021-10-01', '2021-12-31'),
        ('2022-Q1', '2022-01-01', '2022-03-31'),
        ('2022-Q2', '2022-04-01', '2022-06-30'),
        ('2022-Q3', '2022-07-01', '2022-09-30'),
        ('2022-Q4', '2022-10-01', '2022-12-31'),
        ('2023-Q1', '2023-01-01', '2023-03-31'),
        ('2023-Q2', '2023-04-01', '2023-06-30'),
        ('2023-Q3', '2023-07-01', '2023-09-30'),
        ('2023-Q4', '2023-10-01', '2023-12-31'),
        ('2024-Q1', '2024-01-01', '2024-03-31'),
        ('2024-Q2', '2024-04-01', '2024-06-30'),
        ('2024-Q3', '2024-07-01', '2024-09-30'),
        ('2024-Q4', '2024-10-01', '2024-12-31'),
        ('2025-Q1', '2025-01-01', '2025-03-31'),
        ('2025-Q2', '2025-04-01', '2025-06-30'),
    ]
    
    results = []
    cumulative_capital = 10000
    
    for period_name, period_start, period_end in quarters:
        print(f"\n{'='*60}")
        print(f"Testing Period: {period_name} ({period_start} to {period_end})")
        print(f"{'='*60}")
        
        # 해당 기간 데이터 추출
        period_df = df_1h[(df_1h.index >= period_start) & (df_1h.index <= period_end)].copy()
        
        if len(period_df) < 200:  # 최소 데이터 요구사항
            print(f"⚠️ Insufficient data for {period_name} (only {len(period_df)} candles)")
            continue
        
        # 전략 실행
        strategy = ZLHMAEMACrossStrategy(initial_capital=cumulative_capital, timeframe='1h', symbol='BTC/USDT')
        report = strategy.backtest(period_df, print_trades=False, plot_chart=False)
        
        # 다음 기간을 위한 자본 업데이트
        cumulative_capital = strategy.capital
        
        # 결과 저장
        result = {
            'period': period_name,
            'start': period_start,
            'end': period_end,
            'initial_capital': strategy.initial_capital,
            'final_capital': strategy.capital,
            **report
        }
        results.append(result)
        
        # 결과 출력
        print(f"\n📊 Results for {period_name}:")
        print(f"  • Total Return: {report['total_return']:.2f}%")
        print(f"  • Win Rate: {report['win_rate']:.1f}%")
        print(f"  • Profit Factor: {report['profit_factor']:.2f}")
        print(f"  • Max Drawdown: {report['max_drawdown']:.2f}%")
        print(f"  • Total Trades: {report['total_trades']}")
        print(f"  • Capital: ${strategy.initial_capital:.2f} → ${strategy.capital:.2f}")
    
    # 전체 결과 요약
    print(f"\n{'='*80}")
    print("OVERALL SUMMARY")
    print(f"{'='*80}")
    
    if results:
        total_return = ((cumulative_capital - 10000) / 10000) * 100
        avg_win_rate = np.mean([r['win_rate'] for r in results])
        avg_profit_factor = np.mean([r['profit_factor'] for r in results if r['profit_factor'] != float('inf')])
        worst_drawdown = min([r['max_drawdown'] for r in results])
        total_trades = sum([r['total_trades'] for r in results])
        
        print(f"Total Return: {total_return:.2f}% (${10000:.2f} → ${cumulative_capital:.2f})")
        print(f"Average Win Rate: {avg_win_rate:.1f}%")
        print(f"Average Profit Factor: {avg_profit_factor:.2f}")
        print(f"Worst Drawdown: {worst_drawdown:.2f}%")
        print(f"Total Trades: {total_trades}")
        
        # 최고/최저 분기
        best_quarter = max(results, key=lambda x: x['total_return'])
        worst_quarter = min(results, key=lambda x: x['total_return'])
        
        print(f"\nBest Quarter: {best_quarter['period']} ({best_quarter['total_return']:.2f}%)")
        print(f"Worst Quarter: {worst_quarter['period']} ({worst_quarter['total_return']:.2f}%)")
    
    # 결과 저장
    results_file = f'zlhma_ema_cross_wf_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(results_file, 'w') as f:
        json.dump({
            'strategy': 'ZLHMA 50-200 EMA Cross',
            'period': f"{start_date} to {end_date}",
            'leverage': 8,
            'results': results,
            'summary': {
                'total_return': total_return if results else 0,
                'final_capital': cumulative_capital,
                'total_quarters': len(results)
            }
        }, f, indent=2, default=str)
    
    print(f"\n✅ Results saved to {results_file}")
    
    # Equity Curve 플로팅
    if results:
        plt.figure(figsize=(12, 6))
        
        # 분기별 자본 추이
        periods = [r['period'] for r in results]
        capitals = [r['final_capital'] for r in results]
        
        plt.plot(periods, capitals, marker='o', linewidth=2)
        plt.axhline(y=10000, color='r', linestyle='--', alpha=0.5, label='Initial Capital')
        
        plt.title('ZLHMA 50-200 EMA Cross - Walk-Forward Equity Curve')
        plt.xlabel('Period')
        plt.ylabel('Capital ($)')
        plt.xticks(rotation=45)
        plt.grid(True, alpha=0.3)
        plt.legend()
        plt.tight_layout()
        
        chart_file = f'zlhma_ema_cross_wf_equity_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
        plt.savefig(chart_file)
        print(f"📊 Equity curve saved to {chart_file}")
        plt.close()


def main():
    """메인 실행 함수"""
    # Walk-Forward Analysis 실행
    run_walk_forward_analysis()


if __name__ == "__main__":
    main()