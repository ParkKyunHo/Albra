"""
ZL MACD + Ichimoku Strategy - Walk-Forward Analysis
ZL MACD + Ichimoku 결합 전략 백테스팅
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


class ZLMACDIchimokuStrategy:
    """ZL MACD + Ichimoku Combined Strategy"""
    
    def __init__(self, initial_capital: float = 10000, timeframe: str = '4h', symbol: str = 'BTC/USDT'):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position = None
        self.trades = []
        self.equity_curve = []
        self.last_trade_result = None  # 직전 거래 결과 추적
        self.consecutive_losses = 0  # 연속 손실 횟수 추적
        self.recent_trades = []  # 최근 거래 기록 (켈리 계산용)
        self.pyramiding_positions = []  # 피라미딩 포지션 관리
        self.max_pyramiding_levels = 3  # 최대 피라미딩 단계 (3단계로 제한)
        self.original_position_value = 0  # 원래 포지션 가치 저장
        self.accumulated_reduction = 0  # 누적 축소 비율
        
        # 추가 리스크 관리 파라미터
        self.daily_loss_limit = 0.03  # 일일 최대 손실 한도 3%로 강화
        self.daily_loss = 0  # 오늘의 누적 손실
        self.last_trade_date = None  # 마지막 거래 날짜
        self.trading_suspended_until = None  # 거래 재개 시간
        self.initial_stop_loss = 0.015  # 초기 타이트한 손절 1.5%로 더욱 강화
        self.trailing_stop_active = False  # 트레일링 스톱 활성화 여부
        self.trailing_stop_price = None  # 트레일링 스톱 가격
        self.highest_price = None  # 포지션 보유 중 최고가
        self.lowest_price = None  # 포지션 보유 중 최저가
        
        # 거래 비용 (심볼에 따라 조정)
        self.symbol = symbol
        if 'XRP' in symbol:
            self.slippage = 0.002  # XRP는 슬리피지 0.2%로 상향
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
        
        # ZL MACD 파라미터
        self.zlmacd_fast = 12
        self.zlmacd_slow = 26
        self.zlmacd_signal = 9
        
        # Ichimoku 파라미터
        self.tenkan_period = 9
        self.kijun_period = 26
        self.senkou_b_period = 52
        self.chikou_shift = 26
        self.cloud_shift = 26
        
        self.leverage = 10  # 레버리지 10배로 상향 조정
        self.max_position_loss_pct = 0.08  # 포지션당 최대 손실 8%로 축소
        
        # ATR 계산 및 저장
        self.atr_period = 14
        self.current_atr = None
        # ADX 필터 파라미터 (심볼에 따라 조정)
        self.adx_period = 14
        if 'XRP' in symbol:
            self.adx_threshold = 20  # XRP는 ADX 20으로 하향 (더 많은 거래 기회)
        elif 'ETH' in symbol:
            self.adx_threshold = 23  # ETH는 ADX 23
        else:
            self.adx_threshold = 25  # BTC는 기본 ADX 25
        
        # 부분 익절 파라미터 - 강화된 3단계 익절
        self.partial_exit_1_pct = 5.0   # 첫 번째 부분 익절 수익률 (5%)
        self.partial_exit_2_pct = 10.0  # 두 번째 부분 익절 수익률 (10%)
        self.partial_exit_3_pct = 15.0  # 세 번째 부분 익절 수익률 (15%)
        self.partial_exit_1_ratio = 0.25  # 첫 번째 익절 비율 (25%)
        self.partial_exit_2_ratio = 0.35  # 두 번째 익절 비율 (35%)
        self.partial_exit_3_ratio = 0.40  # 세 번째 익절 비율 (40%)
        self.partial_exit_1_done = False  # 첫 번째 부분 익절 완료 여부
        self.partial_exit_2_done = False  # 두 번째 부분 익절 완료 여부
        self.partial_exit_3_done = False  # 세 번째 부분 익절 완료 여부
        
        print(f"  ZL MACD + Ichimoku Strategy initialized:")
        print(f"  • Symbol: {symbol}")
        print(f"  • Timeframe: {timeframe}")
        print(f"  • ZL MACD: Fast={self.zlmacd_fast}, Slow={self.zlmacd_slow}, Signal={self.zlmacd_signal}")
        print(f"  • Ichimoku: Tenkan={self.tenkan_period}, Kijun={self.kijun_period}, Senkou B={self.senkou_b_period}")
        print(f"  • Leverage: {self.leverage}x (Same as TFPE)")
        print(f"  • Position Sizing: Half Kelly Criterion (5-20% of capital, start 10%)")
        print(f"  • Entry: ZL MACD cross + Price above/below cloud + Tenkan/Kijun cross")
        print(f"  • Max Position Loss: {self.max_position_loss_pct*100:.0f}% (Full Exit)")
        print(f"  • Stop Loss: ATR-based dynamic stop (1.2*ATR, max 1.5%), then trailing stop")
        print(f"  • Trailing Stop: Activates at 3% profit, trails by 10% from peak")
        print(f"  • Daily Loss Limit: {self.daily_loss_limit*100:.0f}% (24h suspension if exceeded)")
        print(f"  • Pyramiding: 3 levels at 4%, 6%, 9% profit")
        print(f"  • Trading Costs: {self.slippage*100:.1f}% slippage, {self.commission*100:.2f}% commission")
        print(f"  • Market Filter: ADX > 25 required for entry")
        print(f"  • Consecutive Loss Adjustment: 3+ losses→70%, 5+ losses→50%, 7+ losses→30%")
        print(f"  • Partial Take Profit: 25% at +5%, 35% at +10%, 40% at +15%")
        print(f"  • Multi-layered confirmation: ZL MACD + Cloud position + TK cross")
        print(f"  • Risk Management: Cloud as dynamic support/resistance")
        print(f"  • Exit: Cloud penetration or Kijun-sen touch")
        print(f"  • Position Reduction: Progressive reduction at Tenkan-sen levels")
    
    def calculate_zlema(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Zero Lag EMA 계산"""
        ema1 = df['close'].ewm(span=period, adjust=False).mean()
        ema2 = ema1.ewm(span=period, adjust=False).mean()
        zlema = 2 * ema1 - ema2
        return zlema
    
    def calculate_zlmacd(self, df: pd.DataFrame) -> pd.DataFrame:
        """ZL MACD 계산"""
        # Zero Lag EMA 계산
        zlema_fast = self.calculate_zlema(df, self.zlmacd_fast)
        zlema_slow = self.calculate_zlema(df, self.zlmacd_slow)
        
        # MACD line
        df['zlmacd'] = zlema_fast - zlema_slow
        
        # Signal line (9-period EMA of MACD)
        df['zlmacd_signal'] = df['zlmacd'].ewm(span=self.zlmacd_signal, adjust=False).mean()
        
        # Histogram
        df['zlmacd_hist'] = df['zlmacd'] - df['zlmacd_signal']
        
        return df
    
    def calculate_ichimoku(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ichimoku Cloud 계산"""
        # Tenkan-sen (Conversion Line)
        high_9 = df['high'].rolling(self.tenkan_period).max()
        low_9 = df['low'].rolling(self.tenkan_period).min()
        df['tenkan_sen'] = (high_9 + low_9) / 2
        
        # Kijun-sen (Base Line)
        high_26 = df['high'].rolling(self.kijun_period).max()
        low_26 = df['low'].rolling(self.kijun_period).min()
        df['kijun_sen'] = (high_26 + low_26) / 2
        
        # Senkou Span A (Leading Span A)
        df['senkou_span_a'] = ((df['tenkan_sen'] + df['kijun_sen']) / 2).shift(self.cloud_shift)
        
        # Senkou Span B (Leading Span B)
        high_52 = df['high'].rolling(self.senkou_b_period).max()
        low_52 = df['low'].rolling(self.senkou_b_period).min()
        df['senkou_span_b'] = ((high_52 + low_52) / 2).shift(self.cloud_shift)
        
        # Chikou Span (Lagging Span)
        df['chikou_span'] = df['close'].shift(-self.chikou_shift)
        
        # Cloud top and bottom
        df['cloud_top'] = df[['senkou_span_a', 'senkou_span_b']].max(axis=1)
        df['cloud_bottom'] = df[['senkou_span_a', 'senkou_span_b']].min(axis=1)
        
        # Cloud color (bullish/bearish)
        df['cloud_color'] = (df['senkou_span_a'] > df['senkou_span_b']).astype(int)
        
        return df
    
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
        if index < 52:  # Minimum data needed for Ichimoku
            return result
        
        current_price = df['close'].iloc[index]
        zlmacd = df['zlmacd'].iloc[index]
        zlmacd_signal = df['zlmacd_signal'].iloc[index]
        zlmacd_prev = df['zlmacd'].iloc[index-1]
        zlmacd_signal_prev = df['zlmacd_signal'].iloc[index-1]
        
        tenkan = df['tenkan_sen'].iloc[index]
        kijun = df['kijun_sen'].iloc[index]
        cloud_top = df['cloud_top'].iloc[index]
        cloud_bottom = df['cloud_bottom'].iloc[index]
        
        if position_type == 'LONG':
            # 1. ZL MACD 골든크로스
            if zlmacd > zlmacd_signal and zlmacd_prev <= zlmacd_signal_prev:
                result['signals'].append('ZL_MACD_GOLDEN_CROSS')
                result['strength'] += 1
            
            # 2. 가격이 구름 위
            if current_price > cloud_top:
                result['signals'].append('PRICE_ABOVE_CLOUD')
                result['strength'] += 1
            
            # 3. 전환선 > 기준선
            if tenkan > kijun:
                result['signals'].append('TENKAN_ABOVE_KIJUN')
                result['strength'] += 1
            
            # 4. 구름이 상승 전환 (녹색)
            if df['cloud_color'].iloc[index] == 1:
                result['signals'].append('BULLISH_CLOUD')
                result['strength'] += 0.5
            
        else:  # SHORT
            # 1. ZL MACD 데드크로스
            if zlmacd < zlmacd_signal and zlmacd_prev >= zlmacd_signal_prev:
                result['signals'].append('ZL_MACD_DEAD_CROSS')
                result['strength'] += 1
            
            # 2. 가격이 구름 아래
            if current_price < cloud_bottom:
                result['signals'].append('PRICE_BELOW_CLOUD')
                result['strength'] += 1
            
            # 3. 전환선 < 기준선
            if tenkan < kijun:
                result['signals'].append('TENKAN_BELOW_KIJUN')
                result['strength'] += 1
            
            # 4. 구름이 하락 전환 (빨간색)
            if df['cloud_color'].iloc[index] == 0:
                result['signals'].append('BEARISH_CLOUD')
                result['strength'] += 0.5
        
        # 최소 3개 이상의 주요 신호 필요
        result['can_enter'] = result['strength'] >= 3
        
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
        tenkan = df['tenkan_sen'].iloc[index]
        kijun = df['kijun_sen'].iloc[index]
        cloud_top = df['cloud_top'].iloc[index]
        cloud_bottom = df['cloud_bottom'].iloc[index]
        
        if position_type == 'LONG':
            # 1. 기준선 터치 (부분 익절)
            if low <= kijun:
                result['should_exit'] = True
                result['exit_type'] = 'KIJUN_TOUCH'
                result['reasons'].append('Price touched Kijun-sen')
            
            # 2. 구름 하단 돌파
            elif current_price < cloud_bottom:
                result['should_exit'] = True
                result['exit_type'] = 'CLOUD_BREAK'
                result['reasons'].append('Price broke below cloud')
            
            # 3. ZL MACD 데드크로스
            elif df['zlmacd'].iloc[index] < df['zlmacd_signal'].iloc[index]:
                result['exit_type'] = 'ZLMACD_CROSS'
                result['reasons'].append('ZL MACD dead cross')
                # MACD 크로스만으로는 종료하지 않음 (다른 조건과 함께)
            
        else:  # SHORT
            # 1. 기준선 터치 (부분 익절)
            if high >= kijun:
                result['should_exit'] = True
                result['exit_type'] = 'KIJUN_TOUCH'
                result['reasons'].append('Price touched Kijun-sen')
            
            # 2. 구름 상단 돌파
            elif current_price > cloud_top:
                result['should_exit'] = True
                result['exit_type'] = 'CLOUD_BREAK'
                result['reasons'].append('Price broke above cloud')
            
            # 3. ZL MACD 골든크로스
            elif df['zlmacd'].iloc[index] > df['zlmacd_signal'].iloc[index]:
                result['exit_type'] = 'ZLMACD_CROSS'
                result['reasons'].append('ZL MACD golden cross')
        
        return result
    
    def should_take_trade(self) -> bool:
        """필터: 모든 신호에서 거래"""
        return True
    
    def calculate_dynamic_slippage(self, current_price: float) -> float:
        """ATR 기반 동적 슬리피지 계산"""
        if self.current_atr is None:
            return self.slippage
        
        # ATR이 가격의 2%보다 크면 슬리피지 증가
        volatility_factor = self.current_atr / (current_price * 0.02)
        dynamic_slippage = self.slippage * max(1.0, volatility_factor)
        
        # 최대 슬리피지는 원래의 3배로 제한
        return min(dynamic_slippage, self.slippage * 3.0)
    

    

    
    def run_backtest(self, df: pd.DataFrame) -> Dict:
        """백테스트 실행"""
        # 지표 계산
        df = self.calculate_zlmacd(df)  # ZL MACD
        df = self.calculate_ichimoku(df)  # Ichimoku Cloud
        df = self.calculate_adx(df, self.adx_period)  # ADX
        
        # ATR 계산 추가
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift(1))
        low_close = abs(df['low'] - df['close'].shift(1))
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(self.atr_period).mean()
        
        # 초기화
        self.capital = self.initial_capital
        self.position = None
        self.trades = []
        self.equity_curve = []
        self.last_trade_result = None
        self.consecutive_losses = 0
        self.recent_trades = []
        
        # 디버깅용 카운터
        entry_signals = 0
        filtered_signals = 0
        long_entries = 0
        short_entries = 0
        
        # 백테스트 루프
        for i in range(52, len(df)):  # Ichimoku needs at least 52 periods
            current_time = df.index[i]
            current_price = df['close'].iloc[i]
            high = df['high'].iloc[i]
            low = df['low'].iloc[i]
            
            # 일일 손실 한도 체크 및 거래 재개 로직
            current_date = current_time.date()
            
            # 거래 중단 상태 확인
            if self.trading_suspended_until:
                # 24시간 경과 또는 자정 체크
                if current_time >= self.trading_suspended_until or current_time.hour == 0:
                    self.trading_suspended_until = None
                    self.daily_loss = 0
                    print(f"    Trading resumed at {current_time}")
                else:
                    continue  # 아직 거래 중단 중
            
            # 날짜 변경 시 손실 리셋
            if self.last_trade_date != current_date:
                self.daily_loss = 0
                self.last_trade_date = current_date
            
            # 일일 손실 한도 초과 체크 (원금 대비)
            if self.daily_loss >= self.daily_loss_limit * self.initial_capital:
                # 24시간 후 시간 계산
                self.trading_suspended_until = current_time + pd.Timedelta(hours=24)
                print(f"    Daily loss limit reached. Trading suspended until {self.trading_suspended_until}")
                continue
            
            # ADX 값 확인
            adx_value = df['adx'].iloc[i] if 'adx' in df.columns and not pd.isna(df['adx'].iloc[i]) else 0
            self.current_atr = df['atr'].iloc[i] if 'atr' in df.columns and not pd.isna(df['atr'].iloc[i]) else current_price * 0.02
            
            # 포지션이 없을 때
            if self.position is None:
                # ADX 필터 체크
                if adx_value < self.adx_threshold:  # ADX 25 미만일 때 거래 금지
                    continue
                
                # 롱 진입 조건 확인
                long_conditions = self.check_entry_conditions(df, i, 'LONG')
                if long_conditions['can_enter'] and self.should_take_trade():
                    entry_price = df['open'].iloc[i]
                    
                    # 동적 슬리피지 계산 및 적용
                    dynamic_slippage = self.calculate_dynamic_slippage(current_price)
                    entry_price = entry_price * (1 + dynamic_slippage)
                    self.enter_position('LONG', entry_price, current_time, i)
                    entry_signals += 1
                    long_entries += 1
                    print(f"    LONG Entry: {long_conditions['signals']} (Strength: {long_conditions['strength']})")
                
                # 숏 진입 조건 확인
                short_conditions = self.check_entry_conditions(df, i, 'SHORT')
                if short_conditions['can_enter'] and self.should_take_trade():
                    entry_price = df['open'].iloc[i]
                    
                    # 동적 슬리피지 계산 및 적용 (숏의 경우 불리하게)
                    dynamic_slippage = self.calculate_dynamic_slippage(current_price)
                    entry_price = entry_price * (1 - dynamic_slippage)
                    self.enter_position('SHORT', entry_price, current_time, i)
                    entry_signals += 1
                    short_entries += 1
                    print(f"    SHORT Entry: {short_conditions['signals']} (Strength: {short_conditions['strength']})")
                
                # 필터링된 신호 카운트
                elif (long_conditions['strength'] >= 2 or short_conditions['strength'] >= 2) and not self.should_take_trade():
                    filtered_signals += 1
            
            # 롱 포지션일 때
            elif self.position['type'] == 'LONG':
                # 최고가 업데이트
                if self.highest_price is None or high > self.highest_price:
                    self.highest_price = high
                
                # 현재 수익률 계산
                current_pnl_pct = (current_price / self.position['entry_price'] - 1) * 100
                
                # 부분 익절 체크 - 3단계 강화
                if not self.partial_exit_3_done and current_pnl_pct >= self.partial_exit_3_pct:
                    # 15% 수익에서 40% 익절
                    self.partial_exit_position(self.partial_exit_3_ratio, current_price, current_time, i, 'PARTIAL_EXIT_15PCT')
                    self.partial_exit_3_done = True
                elif not self.partial_exit_2_done and current_pnl_pct >= self.partial_exit_2_pct:
                    # 10% 수익에서 35% 익절
                    self.partial_exit_position(self.partial_exit_2_ratio, current_price, current_time, i, 'PARTIAL_EXIT_10PCT')
                    self.partial_exit_2_done = True
                elif not self.partial_exit_1_done and current_pnl_pct >= self.partial_exit_1_pct:
                    # 5% 수익에서 25% 익절
                    self.partial_exit_position(self.partial_exit_1_ratio, current_price, current_time, i, 'PARTIAL_EXIT_5PCT')
                    self.partial_exit_1_done = True
                
                # ATR 기반 동적 손절 계산
                if self.current_atr and current_price > 0:
                    dynamic_stop_loss = min(0.015, 1.2 * self.current_atr / self.position['entry_price'])
                else:
                    dynamic_stop_loss = self.initial_stop_loss
                
                # 트레일링 스톱 활성화 조건 (3% 수익으로 하향)
                if current_pnl_pct >= 3.0 and not self.trailing_stop_active:
                    self.trailing_stop_active = True
                    self.trailing_stop_price = self.position['entry_price'] * 1.01  # 1% 이익 보호
                    print(f"    Trailing stop activated at {self.trailing_stop_price:.2f}")
                
                # 트레일링 스톱 업데이트 (최고가에서 10% 하락으로 타이트하게)
                if self.trailing_stop_active:
                    new_trailing_stop = self.highest_price * 0.90
                    if new_trailing_stop > self.trailing_stop_price:
                        self.trailing_stop_price = new_trailing_stop
                
                # 손절 체크
                if self.trailing_stop_active and low <= self.trailing_stop_price:
                    # 트레일링 스톱 히트
                    exit_price = min(self.trailing_stop_price, df['open'].iloc[i])
                    dynamic_slippage = self.calculate_dynamic_slippage(current_price)
                    exit_price = exit_price * (1 - dynamic_slippage)
                    self.exit_position(exit_price, current_time, i, 'TRAILING_STOP')
                elif not self.trailing_stop_active:
                    # ATR 기반 동적 초기 손절
                    price_change_pct = (low / self.position['entry_price'] - 1)
                    if price_change_pct <= -dynamic_stop_loss:
                        exit_price = min(self.position['entry_price'] * (1 - dynamic_stop_loss), df['open'].iloc[i])
                        dynamic_slippage = self.calculate_dynamic_slippage(current_price)
                        exit_price = exit_price * (1 - dynamic_slippage)
                        self.exit_position(exit_price, current_time, i, f'STOP_LOSS_{dynamic_stop_loss*100:.1f}PCT')
                
                # ZL MACD + Ichimoku 종료 조건 확인
                exit_conditions = self.check_exit_conditions(df, i, 'LONG')
                if exit_conditions['should_exit']:
                    exit_price = df['open'].iloc[i]
                    # 동적 슬리피지 적용
                    dynamic_slippage = self.calculate_dynamic_slippage(current_price)
                    exit_price = exit_price * (1 - dynamic_slippage)
                    self.exit_position(exit_price, current_time, i, exit_conditions['exit_type'])
                # 피라미딩 기회 체크
                elif self.check_pyramiding_opportunity('LONG', high, df, i):
                    pyramid_price = max(high, df['open'].iloc[i])
                    # 동적 슬리피지 적용
                    dynamic_slippage = self.calculate_dynamic_slippage(current_price)
                    pyramid_price = pyramid_price * (1 + dynamic_slippage)
                    self.add_pyramiding_position('LONG', pyramid_price, current_time, i)
            
            # 숏 포지션일 때
            elif self.position['type'] == 'SHORT':
                # 최저가 업데이트
                if self.lowest_price is None or low < self.lowest_price:
                    self.lowest_price = low
                
                # 현재 수익률 계산
                current_pnl_pct = (self.position['entry_price'] / current_price - 1) * 100
                
                # 부분 익절 체크 - 3단계 강화
                if not self.partial_exit_3_done and current_pnl_pct >= self.partial_exit_3_pct:
                    # 15% 수익에서 40% 익절
                    self.partial_exit_position(self.partial_exit_3_ratio, current_price, current_time, i, 'PARTIAL_EXIT_15PCT')
                    self.partial_exit_3_done = True
                elif not self.partial_exit_2_done and current_pnl_pct >= self.partial_exit_2_pct:
                    # 10% 수익에서 35% 익절
                    self.partial_exit_position(self.partial_exit_2_ratio, current_price, current_time, i, 'PARTIAL_EXIT_10PCT')
                    self.partial_exit_2_done = True
                elif not self.partial_exit_1_done and current_pnl_pct >= self.partial_exit_1_pct:
                    # 5% 수익에서 25% 익절
                    self.partial_exit_position(self.partial_exit_1_ratio, current_price, current_time, i, 'PARTIAL_EXIT_5PCT')
                    self.partial_exit_1_done = True
                
                # ATR 기반 동적 손절 계산
                if self.current_atr and current_price > 0:
                    dynamic_stop_loss = min(0.015, 1.2 * self.current_atr / self.position['entry_price'])
                else:
                    dynamic_stop_loss = self.initial_stop_loss
                
                # 트레일링 스톱 활성화 조건 (3% 수익으로 하향)
                if current_pnl_pct >= 3.0 and not self.trailing_stop_active:
                    self.trailing_stop_active = True
                    self.trailing_stop_price = self.position['entry_price'] * 0.99  # 1% 이익 보호
                    print(f"    Trailing stop activated at {self.trailing_stop_price:.2f}")
                
                # 트레일링 스톱 업데이트 (최저가에서 10% 상승으로 타이트하게)
                if self.trailing_stop_active:
                    new_trailing_stop = self.lowest_price * 1.10
                    if new_trailing_stop < self.trailing_stop_price:
                        self.trailing_stop_price = new_trailing_stop
                
                # 손절 체크
                if self.trailing_stop_active and high >= self.trailing_stop_price:
                    # 트레일링 스톱 히트
                    exit_price = max(self.trailing_stop_price, df['open'].iloc[i])
                    dynamic_slippage = self.calculate_dynamic_slippage(current_price)
                    exit_price = exit_price * (1 + dynamic_slippage)
                    self.exit_position(exit_price, current_time, i, 'TRAILING_STOP')
                elif not self.trailing_stop_active:
                    # ATR 기반 동적 초기 손절
                    price_change_pct = (self.position['entry_price'] / high - 1)
                    if price_change_pct <= -dynamic_stop_loss:
                        exit_price = max(self.position['entry_price'] * (1 + dynamic_stop_loss), df['open'].iloc[i])
                        dynamic_slippage = self.calculate_dynamic_slippage(current_price)
                        exit_price = exit_price * (1 + dynamic_slippage)
                        self.exit_position(exit_price, current_time, i, f'STOP_LOSS_{dynamic_stop_loss*100:.1f}PCT')
                
                # ZL MACD + Ichimoku 종료 조건 확인
                exit_conditions = self.check_exit_conditions(df, i, 'SHORT')
                if exit_conditions['should_exit']:
                    exit_price = df['open'].iloc[i]
                    # 동적 슬리피지 적용
                    dynamic_slippage = self.calculate_dynamic_slippage(current_price)
                    exit_price = exit_price * (1 + dynamic_slippage)
                    self.exit_position(exit_price, current_time, i, exit_conditions['exit_type'])
                # 피라미딩 기회 체크
                elif self.check_pyramiding_opportunity('SHORT', low, df, i):
                    pyramid_price = min(low, df['open'].iloc[i])
                    # 동적 슬리피지 적용
                    dynamic_slippage = self.calculate_dynamic_slippage(current_price)
                    pyramid_price = pyramid_price * (1 - dynamic_slippage)
                    self.add_pyramiding_position('SHORT', pyramid_price, current_time, i)
            
            # 펀딩 비용 적용 (포지션이 있을 때만)
            if self.position is not None:
                # 실제 바이낸스 펀딩은 8시간마다 적용되지만, 백테스트에서는 시간당 비율로 계산
                # 8시간당 0.01% = 시간당 0.00125%
                hourly_funding_rate = 0.0001 / 8  # 0.00125%
                
                # 타임프레임별 펀딩 비용 계산
                if self.timeframe == '4h':
                    # 4시간마다
                    funding_rate = hourly_funding_rate * 4
                elif self.timeframe == '1h':
                    # 1시간마다
                    funding_rate = hourly_funding_rate
                elif self.timeframe == '15m':
                    # 15분마다 (0.25시간)
                    funding_rate = hourly_funding_rate * 0.25
                else:
                    funding_rate = 0
                
                # 메인 포지션의 펀딩 비용
                funding_cost = self.position['leveraged_value'] * funding_rate
                
                # 피라미딩 포지션의 펀딩 비용
                for pyramid in self.pyramiding_positions:
                    funding_cost += pyramid['leveraged_value'] * funding_rate
                
                # 자본에서 펀딩 비용 차감
                self.capital -= funding_cost
            
            # 자산 기록
            current_equity = self.calculate_equity(current_price)
            self.equity_curve.append({
                'time': current_time,
                'capital': current_equity,
                'price': current_price
            })
        
        # 마지막 포지션 청산
        if self.position is not None:
            self.exit_position(df['close'].iloc[-1], df.index[-1], len(df)-1, 'END_OF_DATA')
        
        # 디버깅 정보 출력
        print(f"    Entry signals: {entry_signals} (Long: {long_entries}, Short: {short_entries})")
        print(f"    Filtered signals (skipped due to last win): {filtered_signals}")
        print(f"    Total candles analyzed: {len(df) - 52}")  # Ichimoku requires 52 periods
        
        # 결과 계산
        equity_df = pd.DataFrame(self.equity_curve)
        trades_df = pd.DataFrame(self.trades)
        
        # 성과 지표 계산
        if len(trades_df) > 0:
            total_return = (self.capital / self.initial_capital - 1) * 100
            win_trades = trades_df[trades_df['net_pnl_pct'] > 0]
            win_rate = len(win_trades) / len(trades_df) * 100
            avg_win = win_trades['net_pnl_pct'].mean() if len(win_trades) > 0 else 0
            avg_loss = trades_df[trades_df['net_pnl_pct'] < 0]['net_pnl_pct'].mean() if len(trades_df[trades_df['net_pnl_pct'] < 0]) > 0 else 0
            
            # 터틀 특유 통계
            consecutive_losses = self.calculate_consecutive_losses(trades_df)
            filtered_ratio = filtered_signals / (entry_signals + filtered_signals) * 100 if (entry_signals + filtered_signals) > 0 else 0
        else:
            total_return = 0
            win_rate = 0
            avg_win = 0
            avg_loss = 0
            consecutive_losses = 0
            filtered_ratio = 0
        
        return {
            'equity_df': equity_df,
            'trades_df': trades_df,
            'total_return': total_return,
            'win_rate': win_rate,
            'total_trades': len(trades_df),
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'final_capital': self.capital,
            'consecutive_losses': consecutive_losses,
            'filtered_ratio': filtered_ratio,
            'df': df
        }
    
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
            # 첫 번째 피라미딩: 4% 가격 상승 (상향 조정하여 더 확실한 추세에서만 추가)
            return current_pnl_pct >= 4.0
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
        
        # 수수료 차감 (레버리지 포지션 전체에 대해 적용)
        commission_cost = actual_pyramid_size * self.commission
        self.capital -= commission_cost
        
        self.pyramiding_positions.append(pyramid_position)
        print(f"    Pyramiding Level {len(self.pyramiding_positions)}: {position_type} at {price:.2f} (Size: {pyramid_size/self.original_position_value*100:.0f}%)")
    
    def calculate_kelly_position_size(self) -> float:
        """켈리 기준을 활용한 동적 포지션 사이즈 계산"""
        # 최소 20개 이상의 거래가 필요
        if len(self.recent_trades) < 20:
            return 0.10  # 기본값: 자본의 10%로 축소 (초기 리스크 감소)
        
        # 승률과 평균 손익 계산
        wins = [t for t in self.recent_trades if t['pnl'] > 0]
        losses = [t for t in self.recent_trades if t['pnl'] <= 0]
        
        if len(wins) == 0 or len(losses) == 0:
            return 0.10  # 기본값 10%로 수정
        
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
        
        # 최소 5%, 최대 20%로 제한 (기존 30% → 20%로 하향)
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
        
        # 수수료 차감 (레버리지 포지션 전체에 대해 적용)
        commission_cost = actual_position_size * self.commission
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
    
    def reduce_position_progressive(self, level_idx: int, target_reduction: float, price: float, time: datetime, index: int):
        """단계적 포지션 축소"""
        if self.position is None:
            return
            
        # 현재 남은 포지션 대비 축소할 비율 계산
        current_remaining = 1.0 - self.accumulated_reduction
        new_accumulated = target_reduction
        reduction_this_time = (new_accumulated - self.accumulated_reduction) / current_remaining
        
        # 포지션 업데이트
        self.position['position_value'] *= (1 - reduction_this_time)
        self.position['leveraged_value'] = self.position['position_value'] * self.leverage
        self.position['shares'] *= (1 - reduction_this_time)
        
        # 누적 축소 비율 업데이트
        self.accumulated_reduction = new_accumulated
        
        print(f"    Stop Loss Level {level_idx+1}: Position reduced to {(1-self.accumulated_reduction)*100:.0f}% at {price:.2f}")
    
    def partial_exit_position(self, exit_ratio: float, price: float, time: datetime, index: int, exit_reason: str):
        """부분 익절 실행"""
        if self.position is None:
            return
        
        # 종료할 포지션 크기 계산
        exit_shares = self.position['shares'] * exit_ratio
        exit_position_value = self.position['position_value'] * exit_ratio
        
        # 손익 계산
        if self.position['type'] == 'LONG':
            price_change_pct = (price / self.position['entry_price'] - 1)
            pnl_pct = price_change_pct * 100 * self.leverage
            pnl = exit_position_value * price_change_pct * self.leverage
        else:  # SHORT
            price_change_pct = (self.position['entry_price'] / price - 1)
            pnl_pct = price_change_pct * 100 * self.leverage
            pnl = exit_position_value * price_change_pct * self.leverage
        
        # 수수료 차감
        commission_cost = exit_position_value * self.commission
        net_pnl = pnl - commission_cost
        
        # 자본 업데이트
        self.capital += net_pnl
        
        # 포지션 크기 조정
        self.position['shares'] *= (1 - exit_ratio)
        self.position['position_value'] *= (1 - exit_ratio)
        self.position['leveraged_value'] *= (1 - exit_ratio)
        
        print(f"    Partial exit ({exit_ratio*100:.0f}%) at {price:.2f}, P&L: {net_pnl:.2f} ({pnl_pct:.1f}%), Reason: {exit_reason}")
        
        # 거래 기록 (부분 익절도 기록)
        trade_record = {
            'entry_time': self.position['entry_time'],
            'exit_time': time,
            'direction': self.position['type'].lower(),
            'entry_price': self.position['entry_price'],
            'exit_price': price,
            'shares': exit_shares,
            'pnl': pnl,
            'net_pnl_pct': pnl_pct,
            'pnl_pct': pnl_pct / self.leverage,
            'exit_reason': exit_reason,
            'holding_periods': (index - self.position['entry_index']),
            'result': 'WIN',  # 부분 익절은 항상 수익
            'pyramiding_levels': len(self.pyramiding_positions)
        }
        self.trades.append(trade_record)
        
        # 최근 거래 기록 업데이트 (켈리 계산용)
        self.recent_trades.append(trade_record)
        if len(self.recent_trades) > 100:  # 최근 100개만 유지
            self.recent_trades.pop(0)
    
    def exit_position(self, price: float, time: datetime, index: int, exit_reason: str):
        """포지션 청산"""
        if self.position is None:
            return
        
        # 손익 계산
        if self.position['type'] == 'LONG':
            price_change_pct = (price / self.position['entry_price'] - 1)
            pnl_pct = price_change_pct * 100 * self.leverage
            pnl = self.position['position_value'] * price_change_pct * self.leverage
        else:  # SHORT
            price_change_pct = (self.position['entry_price'] / price - 1)
            pnl_pct = price_change_pct * 100 * self.leverage
            pnl = self.position['position_value'] * price_change_pct * self.leverage
        
        # 자본 업데이트 (피라미딩 포지션 포함)
        total_pnl = pnl
        
        # 피라미딩 포지션 손익 계산
        for pyramid in self.pyramiding_positions:
            if pyramid['type'] == 'LONG':
                pyramid_change_pct = (price / pyramid['entry_price'] - 1)
            else:  # SHORT
                pyramid_change_pct = (pyramid['entry_price'] / price - 1)
            
            pyramid_pnl = pyramid['position_value'] * pyramid_change_pct * self.leverage
            total_pnl += pyramid_pnl
        
        # 수수료 차감 (레버리지 포지션 전체에 대해 적용)
        commission_cost = self.position['leveraged_value'] * self.commission
        for pyramid in self.pyramiding_positions:
            commission_cost += pyramid['leveraged_value'] * self.commission
        
        # 전체 손익으로 자본 업데이트 (수수료 차감 후)
        net_pnl = total_pnl - commission_cost
        self.capital = max(0, self.capital + net_pnl)
        
        # 일일 손실 업데이트
        if net_pnl < 0:
            self.daily_loss += abs(net_pnl)
        
        # 거래 결과 기록 (필터용)
        self.last_trade_result = 'WIN' if pnl > 0 else 'LOSS'
        
        # 연속 손실 횟수 업데이트
        if self.last_trade_result == 'LOSS':
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        
        # 거래 기록
        trade_record = {
            'entry_time': self.position['entry_time'],
            'exit_time': time,
            'direction': self.position['type'].lower(),
            'entry_price': self.position['entry_price'],
            'exit_price': price,
            'shares': self.position['shares'],
            'pnl': pnl,
            'net_pnl_pct': pnl_pct,
            'pnl_pct': pnl_pct / self.leverage,  # 켈리 계산용 (레버리지 제거)
            'exit_reason': exit_reason,
            'holding_periods': (index - self.position['entry_index']),
            'result': self.last_trade_result,
            'pyramiding_levels': len(self.pyramiding_positions)
        }
        self.trades.append(trade_record)
        
        # 최근 거래 기록 업데이트 (켈리 계산용)
        self.recent_trades.append(trade_record)
        if len(self.recent_trades) > 100:  # 최근 100개만 유지
            self.recent_trades.pop(0)
        
        # 포지션 초기화
        self.position = None
        self.pyramiding_positions = []
        # 부분 익절 플래그 초기화
        self.partial_exit_1_done = False
        self.partial_exit_2_done = False
        self.partial_exit_3_done = False
    
    def calculate_equity(self, current_price: float) -> float:
        """현재 자산 계산"""
        if self.position is None:
            return self.capital
        
        # 미실현 손익 포함 (피라미딩 포함)
        total_unrealized = 0
        
        # 메인 포지션 미실현 손익
        if self.position['type'] == 'LONG':
            price_change_pct = (current_price / self.position['entry_price'] - 1)
            unrealized_pnl = self.position['position_value'] * price_change_pct * self.leverage
        else:  # SHORT
            price_change_pct = (self.position['entry_price'] / current_price - 1)
            unrealized_pnl = self.position['position_value'] * price_change_pct * self.leverage
        
        total_unrealized += unrealized_pnl
        
        # 피라미딩 포지션 미실현 손익
        for pyramid in self.pyramiding_positions:
            if pyramid['type'] == 'LONG':
                pyramid_change_pct = (current_price / pyramid['entry_price'] - 1)
            else:  # SHORT
                pyramid_change_pct = (pyramid['entry_price'] / current_price - 1)
            
            pyramid_unrealized = pyramid['position_value'] * pyramid_change_pct * self.leverage
            total_unrealized += pyramid_unrealized
        
        return self.capital + total_unrealized


class ZLMACDIchimokuWalkForward:
    """ZL MACD + Ichimoku Strategy Walk-Forward 분석"""
    
    def __init__(self, initial_capital: float = 10000, timeframe: str = '4h', symbol: str = 'BTC/USDT'):
        print("\nInitializing ZL MACD + Ichimoku Walk-Forward...")
        self.initial_capital = initial_capital
        self.timeframe = timeframe
        self.symbol = symbol
        
        # 디렉토리 설정
        if __file__:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
        else:
            self.base_dir = os.getcwd()
            
        self.cache_dir = os.path.join(self.base_dir, "wf_cache")
        self.results_cache_dir = os.path.join(self.base_dir, "wf_cache_turtle")
        
        # 디렉토리 생성
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.results_cache_dir, exist_ok=True)
        
        print(f"  Base directory: {self.base_dir}")
        print(f"  Cache directory: {self.cache_dir}")
        print(f"  Results cache directory: {self.results_cache_dir}")
        
        # Walk-Forward 분석 기간 (12개월 training + 3개월 test)
        self.periods = []
        
        # 2020년 1월부터 시작하여 3개월씩 슬라이딩
        start_year = 2020
        start_month = 1
        
        for i in range(17):  # 약 17개의 window
            # Training 시작일
            train_start_year = start_year + (start_month - 1 + i * 3) // 12
            train_start_month = ((start_month - 1 + i * 3) % 12) + 1
            
            # Training 종료일 (12개월 후)
            train_end_year = train_start_year + 1
            train_end_month = train_start_month - 1
            if train_end_month == 0:
                train_end_month = 12
                train_end_year -= 1
                
            # Test 시작일 (Training 종료 다음날)
            test_start_year = train_end_year
            test_start_month = train_end_month + 1
            if test_start_month > 12:
                test_start_month = 1
                test_start_year += 1
                
            # Test 종료일 (3개월 후)
            test_end_year = test_start_year
            test_end_month = test_start_month + 2
            if test_end_month > 12:
                test_end_month = test_end_month - 12
                test_end_year += 1
                
            # 2025년 3월을 넘어가면 중단
            if test_end_year > 2025 or (test_end_year == 2025 and test_end_month > 3):
                break
                
            # 마지막 날 계산
            import calendar
            train_end_day = calendar.monthrange(train_end_year, train_end_month)[1]
            test_end_day = calendar.monthrange(test_end_year, test_end_month)[1]
            
            window = {
                "name": f"WF_{i+1:02d}",
                "training_start": f"{train_start_year}-{train_start_month:02d}-01",
                "training_end": f"{train_end_year}-{train_end_month:02d}-{train_end_day:02d}",
                "test_start": f"{test_start_year}-{test_start_month:02d}-01",
                "test_end": f"{test_end_year}-{test_end_month:02d}-{test_end_day:02d}"
            }
            
            self.periods.append(window)
        
        print(f"\n✅ Walk-Forward periods initialized: {len(self.periods)} windows")
        print(f"  • Training period: 12 months")
        print(f"  • Test period: 3 months")
        print(f"  • Sliding interval: 3 months")
        
        self.all_results = []
        
        print("\n✅ ZL MACD + Ichimoku parameters initialized")
        print(f"  • ZL MACD: Fast=12, Slow=26, Signal=9")
        print(f"  • Ichimoku: Tenkan=9, Kijun=26, Senkou B=52")
        print(f"  • Timeframe: {timeframe}")
        print(f"  • Entry: 3+ signals confirmation required")
        print(f"  • Exit: Cloud break or Kijun touch")
        print(f"  • Filter: ADX > 25 for trending markets")
    
    def run_walk_forward_window(self, period: Dict) -> Dict:
        """Walk-Forward 분석의 한 window 실행 (training + test)"""
        try:
            print(f"\n{'='*60}")
            print(f"  Window {period['name']}")
            print(f"  Training: {period['training_start']} to {period['training_end']}")
            print(f"  Test: {period['test_start']} to {period['test_end']}")
            print(f"{'='*60}")
            
            # 데이터 로드
            data_fetcher = DataFetcherFixed()
            exchange = data_fetcher.exchange
            
            # Training과 Test 기간을 모두 포함하는 데이터 로드
            train_start_dt = pd.to_datetime(period['training_start'])
            test_end_dt = pd.to_datetime(period['test_end'])
            
            # 지표 계산을 위해 추가 데이터 필요
            extended_start_dt = train_start_dt - timedelta(days=60)  # 2개월 전부터
            since = int(extended_start_dt.timestamp() * 1000)
            
            print(f"  Loading data from {extended_start_dt.date()} to {test_end_dt.date()}")
            
            all_data = []
            while since < int(test_end_dt.timestamp() * 1000):
                try:
                    time.sleep(0.5)  # Rate limit
                    ohlcv = exchange.fetch_ohlcv(self.symbol, self.timeframe, since=since, limit=1000)
                    if not ohlcv:
                        break
                    all_data.extend(ohlcv)
                    since = ohlcv[-1][0] + 1
                except Exception as e:
                    print(f"  Warning: {e}")
                    break
            
            if not all_data:
                print(f"  Failed to load data for {period['name']}")
                return None
            
            # DataFrame 생성
            df = pd.DataFrame(all_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
            df.set_index('timestamp', inplace=True)
            
            print(f"  Loaded {len(df)} {self.timeframe} candles")
            
            # Training 기간 데이터 필터링
            train_end_dt = pd.to_datetime(period['training_end'])
            df_train_full = df[df.index <= train_end_dt].copy()
            df_train = df[(df.index >= train_start_dt) & (df.index <= train_end_dt)].copy()
            
            # Test 기간 데이터 필터링
            test_start_dt = pd.to_datetime(period['test_start'])
            
            # Look-ahead bias 제거: Test 백테스트용 데이터는 test 시작 52일 전부터만 포함
            # Ichimoku 계산에 필요한 최소 데이터만 포함
            test_lookback_start = test_start_dt - timedelta(days=52)
            df_test_with_lookback = df[(df.index >= test_lookback_start) & (df.index <= test_end_dt)].copy()
            df_test = df[(df.index >= test_start_dt) & (df.index <= test_end_dt)].copy()
            
            if df_train.empty or df_test.empty:
                print(f"  No data in training or test period")
                return None
            
            print(f"  Training data: {len(df_train)} candles ({df_train.index[0].date()} to {df_train.index[-1].date()})")
            print(f"  Test data: {len(df_test)} candles ({df_test.index[0].date()} to {df_test.index[-1].date()})")
            
            # 1. Training 기간 백테스트
            print(f"\n  Running TRAINING period backtest...")
            strategy_train = ZLMACDIchimokuStrategy(self.initial_capital, self.timeframe, self.symbol)
            results_train = strategy_train.run_backtest(df_train_full)
            
            # Training 기간의 거래만 필터링
            trades_train = results_train.get('trades_df', pd.DataFrame())
            if not trades_train.empty:
                trades_train = trades_train[
                    (pd.to_datetime(trades_train['entry_time']) >= train_start_dt) &
                    (pd.to_datetime(trades_train['exit_time']) <= train_end_dt)
                ]
            
            # 2. Test 기간 백테스트 (동일한 파라미터 사용)
            print(f"  Running TEST period backtest...")
            strategy_test = ZLMACDIchimokuStrategy(self.initial_capital, self.timeframe, self.symbol)
            # Look-ahead bias 제거: df_test_full 대신 df_test_with_lookback 사용
            results_test = strategy_test.run_backtest(df_test_with_lookback)
            
            # Test 기간의 거래만 필터링
            trades_test = results_test.get('trades_df', pd.DataFrame())
            if not trades_test.empty:
                trades_test = trades_test[
                    (pd.to_datetime(trades_test['entry_time']) >= test_start_dt) &
                    (pd.to_datetime(trades_test['exit_time']) <= test_end_dt)
                ]
            
            # 성능 지표 계산
            def calculate_metrics(equity_df, timeframe):
                if equity_df.empty:
                    return 0, 0
                    
                returns = equity_df['capital'].pct_change().dropna()
                if timeframe == '4h':
                    annual_factor = np.sqrt(365 * 6)
                elif timeframe == '1h':
                    annual_factor = np.sqrt(365 * 24)
                else:  # 15m
                    annual_factor = np.sqrt(365 * 96)
                    
                sharpe = annual_factor * returns.mean() / returns.std() if returns.std() > 0 else 0
                
                equity_curve = equity_df['capital'].values
                peak = np.maximum.accumulate(equity_curve)
                drawdown = (equity_curve - peak) / peak * 100
                max_dd = abs(drawdown.min()) if len(drawdown) > 0 else 0
                
                return sharpe, max_dd
            
            # Training 메트릭
            train_sharpe, train_max_dd = calculate_metrics(
                results_train.get('equity_df', pd.DataFrame()), 
                self.timeframe
            )
            
            # Test 메트릭
            test_sharpe, test_max_dd = calculate_metrics(
                results_test.get('equity_df', pd.DataFrame()), 
                self.timeframe
            )
            
            # Walk-Forward 효율성 계산
            efficiency_ratio = results_test['total_return'] / results_train['total_return'] if results_train['total_return'] != 0 else 0
            
            # 과적합 점수 계산 (0-100, 낮을수록 좋음)
            overfitting_score = abs(results_train['total_return'] - results_test['total_return'])
            if train_sharpe != 0:
                overfitting_score += abs(train_sharpe - test_sharpe) * 10
            
            # 결과 요약 출력
            print(f"\n  {'='*50}")
            print(f"  TRAINING Results:")
            print(f"    Return: {results_train['total_return']:.2f}%")
            print(f"    Sharpe: {train_sharpe:.2f}")
            print(f"    Max DD: {train_max_dd:.2f}%")
            print(f"    Trades: {len(trades_train)}")
            print(f"    Win Rate: {results_train['win_rate']:.1f}%")
            
            print(f"\n  TEST Results:")
            print(f"    Return: {results_test['total_return']:.2f}%")
            print(f"    Sharpe: {test_sharpe:.2f}")
            print(f"    Max DD: {test_max_dd:.2f}%")
            print(f"    Trades: {len(trades_test)}")
            print(f"    Win Rate: {results_test['win_rate']:.1f}%")
            
            print(f"\n  Walk-Forward Metrics:")
            print(f"    Efficiency Ratio: {efficiency_ratio:.2f}")
            print(f"    Overfitting Score: {overfitting_score:.1f}")
            print(f"  {'='*50}")
            
            # 결과 포맷팅
            result = {
                'window': period['name'],
                'training_period': f"{period['training_start']} to {period['training_end']}",
                'test_period': f"{period['test_start']} to {period['test_end']}",
                
                # Training 결과
                'training_return': results_train['total_return'],
                'training_sharpe': train_sharpe,
                'training_win_rate': results_train['win_rate'],
                'training_max_dd': train_max_dd,
                'training_trades': len(trades_train),
                'training_trades_df': trades_train,
                'training_final_capital': results_train['final_capital'],
                
                # Test 결과
                'test_return': results_test['total_return'],
                'test_sharpe': test_sharpe,
                'test_win_rate': results_test['win_rate'],
                'test_max_dd': test_max_dd,
                'test_trades': len(trades_test),
                'test_trades_df': trades_test,
                'test_final_capital': results_test['final_capital'],
                
                # Walk-Forward 메트릭
                'efficiency_ratio': efficiency_ratio,
                'overfitting_score': overfitting_score,
                'consistency': 1 if results_test['total_return'] > 0 and results_train['total_return'] > 0 else 0,
                
                # 데이터
                'df_train': df_train,
                'df_test': df_test
            }
            
            return result
            
        except Exception as e:
            print(f"  ❌ Error in walk-forward window {period['name']}: {e}")
            print(f"  Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            
            return None
    
    def plot_quarter_with_trades(self, result: Dict, show: bool = True):
        """분기별 차트에 거래 표시"""
        if not result or 'trades_df' not in result:
            return None
            
        period = result['period']
        df = result['df']
        trades_df = result['trades_df']
        
        # 차트 생성
        fig = plt.figure(figsize=(20, 16))
        
        # 1. 가격 차트 + 던키안 채널 + 거래
        ax1 = plt.subplot(5, 1, 1)
        
        # 캔들스틱 차트
        dates = df.index
        prices = df['close']
        
        ax1.plot(dates, prices, 'b-', alpha=0.3, linewidth=1, label='Price')
        
        # Ichimoku Cloud 표시
        if 'cloud_top' in df.columns and 'cloud_bottom' in df.columns:
            ax1.fill_between(dates, df['cloud_top'], df['cloud_bottom'], 
                           where=df['cloud_color']==1, color='green', alpha=0.2, label='Bullish Cloud')
            ax1.fill_between(dates, df['cloud_top'], df['cloud_bottom'], 
                           where=df['cloud_color']==0, color='red', alpha=0.2, label='Bearish Cloud')
        
        # Ichimoku Lines
        if 'tenkan_sen' in df.columns:
            ax1.plot(dates, df['tenkan_sen'], 'blue', alpha=0.8, linewidth=1.5, label='Tenkan-sen')
        if 'kijun_sen' in df.columns:
            ax1.plot(dates, df['kijun_sen'], 'red', alpha=0.8, linewidth=1.5, label='Kijun-sen')
        
        # ZL MACD Histogram (하단 패널에 표시할 예정)
        # 이 부분은 다른 subplot에서 처리
        
        # 거래 표시
        for idx, trade in trades_df.iterrows():
            entry_time = pd.to_datetime(trade['entry_time'])
            exit_time = pd.to_datetime(trade['exit_time'])
            
            # 포지션 방향에 따른 색상
            if trade['direction'].upper() == 'LONG':
                color = 'green'
                marker_entry = '^'
                marker_exit = 'v'
            else:
                color = 'red'
                marker_entry = 'v'
                marker_exit = '^'
            
            # 진입/청산 마커
            ax1.scatter(entry_time, trade['entry_price'], color=color, s=150, 
                       marker=marker_entry, zorder=5, edgecolors='black', linewidth=2)
            ax1.scatter(exit_time, trade['exit_price'], color=color, s=150,
                       marker=marker_exit, zorder=5, edgecolors='black', linewidth=2, alpha=0.6)
            
            # 포지션 홀딩 구간 표시
            rect = Rectangle((mdates.date2num(entry_time), min(trade['entry_price'], trade['exit_price'])),
                           mdates.date2num(exit_time) - mdates.date2num(entry_time),
                           abs(trade['exit_price'] - trade['entry_price']),
                           facecolor=color, alpha=0.2)
            ax1.add_patch(rect)
            
            # 손익 표시
            if abs(trade.get('net_pnl_pct', 0)) > 3:
                mid_time = entry_time + (exit_time - entry_time) / 2
                mid_price = (trade['entry_price'] + trade['exit_price']) / 2
                ax1.text(mid_time, mid_price, f"{trade.get('net_pnl_pct', 0):.1f}%",
                        ha='center', va='center', fontsize=8, fontweight='bold',
                        bbox=dict(boxstyle='round,pad=0.3', 
                                facecolor='lightgreen' if trade.get('net_pnl_pct', 0) > 0 else 'lightcoral',
                                alpha=0.8))
        
        ax1.set_title(f'{period} - ZL MACD + Ichimoku Strategy ({self.symbol} - {self.timeframe})', fontsize=14)
        ax1.set_ylabel('Price (USDT)')
        ax1.grid(True, alpha=0.3)
        ax1.legend()
        
        # 2. 거래 분포 및 필터 효과
        ax2 = plt.subplot(5, 1, 2)
        
        # 롱/샷 거래 수
        if len(trades_df) > 0:
            long_trades = len(trades_df[trades_df['direction'] == 'long'])
            short_trades = len(trades_df[trades_df['direction'] == 'short'])
            
            bars = ax2.bar(['Long', 'Short'], [long_trades, short_trades], 
                           color=['green', 'red'], alpha=0.7)
            
            # 승률 표시
            if long_trades > 0:
                long_wr = (trades_df[trades_df['direction'] == 'long']['net_pnl_pct'] > 0).sum() / long_trades * 100
                ax2.text(0, long_trades + 0.5, f'{long_wr:.0f}%', ha='center', va='bottom')
            if short_trades > 0:
                short_wr = (trades_df[trades_df['direction'] == 'short']['net_pnl_pct'] > 0).sum() / short_trades * 100
                ax2.text(1, short_trades + 0.5, f'{short_wr:.0f}%', ha='center', va='bottom')
            
            # 필터 비율 표시
            if result.get('filtered_ratio', 0) > 0:
                ax2.text(0.5, max(long_trades, short_trades) * 0.5, 
                        f"Filtered: {result['filtered_ratio']:.0f}%",
                        ha='center', va='center', fontsize=10,
                        bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.5))
        
        ax2.set_title('Trade Distribution (with Filter Effect)')
        ax2.set_ylabel('Number of Trades')
        ax2.grid(True, alpha=0.3)
        
        # 3. 거래별 손익
        ax3 = plt.subplot(5, 1, 3)
        
        if 'net_pnl_pct' in trades_df.columns and len(trades_df) > 0:
            bar_colors = ['green' if pnl > 0 else 'red' for pnl in trades_df['net_pnl_pct']]
            bars = ax3.bar(range(len(trades_df)), trades_df['net_pnl_pct'].values, 
                          color=bar_colors, alpha=0.7)
            
            # 필터된 거래 표시 (WIN 후 스킵된 거래)
            for i, (idx, trade) in enumerate(trades_df.iterrows()):
                if i > 0 and trades_df.iloc[i-1]['result'] == 'WIN':
                    ax3.axvline(x=i-0.5, color='yellow', linestyle='--', alpha=0.7, linewidth=2)
        
        ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax3.set_title('Individual Trade P&L (%) - Yellow lines show where filter activated')
        ax3.set_xlabel('Trade Number')
        ax3.set_ylabel('P&L (%)')
        ax3.grid(True, alpha=0.3)
        
        # 4. 연속 손실 패턴
        ax4 = plt.subplot(5, 1, 4)
        
        if len(trades_df) > 0:
            # 각 거래의 결과를 1(승) 또는 -1(패)로 표시
            trade_results = [1 if pnl > 0 else -1 for pnl in trades_df['net_pnl_pct']]
            ax4.step(range(len(trade_results)), trade_results, where='mid', linewidth=2)
            ax4.fill_between(range(len(trade_results)), 0, trade_results, 
                           where=[r > 0 for r in trade_results], 
                           color='green', alpha=0.3, step='mid')
            ax4.fill_between(range(len(trade_results)), 0, trade_results, 
                           where=[r < 0 for r in trade_results], 
                           color='red', alpha=0.3, step='mid')
            
            # 최대 연속 손실 표시
            if result.get('consecutive_losses', 0) > 0:
                ax4.text(0.5, -0.5, f"Max Consecutive Losses: {result['consecutive_losses']}", 
                        transform=ax4.transAxes, ha='center',
                        bbox=dict(boxstyle='round', facecolor='red', alpha=0.3))
        
        ax4.set_title('Win/Loss Pattern')
        ax4.set_xlabel('Trade Number')
        ax4.set_ylabel('Win(1) / Loss(-1)')
        ax4.set_ylim(-1.5, 1.5)
        ax4.grid(True, alpha=0.3)
        
        # 5. 누적 수익률
        ax5 = plt.subplot(5, 1, 5)
        
        if 'net_pnl_pct' in trades_df.columns and len(trades_df) > 0:
            # 복리 수익률 계산
            cumulative_return = 1.0
            cumulative_returns = []
            
            for pnl_pct in trades_df['net_pnl_pct'].values:
                cumulative_return *= (1 + pnl_pct / 100)
                cumulative_returns.append((cumulative_return - 1) * 100)
            
            ax5.plot(range(len(cumulative_returns)), cumulative_returns, 'b-', linewidth=3, marker='o')
            
            # 최고/최저 표시
            if len(cumulative_returns) > 0:
                max_idx = np.argmax(cumulative_returns)
                min_idx = np.argmin(cumulative_returns)
                ax5.scatter(max_idx, cumulative_returns[max_idx], color='green', s=100, zorder=5)
                ax5.scatter(min_idx, cumulative_returns[min_idx], color='red', s=100, zorder=5)
        
        ax5.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax5.set_title('Cumulative P&L')
        ax5.set_xlabel('Trade Number')
        ax5.set_ylabel('Cumulative Return (%)')
        ax5.grid(True, alpha=0.3)
        
        # 최종 통계 표시
        final_stats = f'Return: {result["return"]:.2f}% | Win Rate: {result["win_rate"]:.1f}% | Trades: {result["trades"]} | Filtered: {result.get("filtered_ratio", 0):.0f}%'
        ax5.text(0.5, 0.02, final_stats, transform=ax5.transAxes, 
                ha='center', fontsize=10,
                bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.5))
        
        plt.tight_layout()
        
        # 저장
        symbol_clean = self.symbol.replace('/', '_')
        filename = f'zlmacd_ichimoku_{symbol_clean}_quarter_{period}_trades_{self.timeframe}.png'
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        if not show:
            print(f"  Chart saved: {filename}")
        
        if show:
            plt.show()
        else:
            plt.close(fig)
        
        return fig
    
    def run_analysis(self):
        """전체 분석 실행"""
        print("="*80)
        print("ZL MACD + Ichimoku Strategy - Walk-Forward Analysis")
        print("="*80)
        print("\n🎯 STRATEGY PARAMETERS")
        
        print(f"  • Symbol: {self.symbol}")
        print(f"  • Timeframe: {self.timeframe}")
        print(f"  • ZL MACD: Fast=12, Slow=26, Signal=9")
        print(f"  • Ichimoku: Tenkan=9, Kijun=26, Senkou B=52")
        print(f"  • Position Size: Kelly Criterion (dynamic)")
        print("\n📊 ENHANCED TRADING RULES")
        print("  • ENTRY: ZL MACD cross + Cloud position + TK cross (3+ signals)")
        print("  • EXIT: Cloud penetration or Kijun-sen touch")
        print("  • STOP LOSS: ATR-based dynamic stop (1.5*ATR, max 2%), then 10% trailing from peak")
        print("  • PROFIT PROTECTION: Trailing stop activates at 3% profit")
        print("  • RISK MANAGEMENT: Daily loss limit 3%, Half-Kelly sizing (5-20%)")
        print("  • PYRAMIDING: 3 levels at 3%, 6%, 9% profit (75%, 50%, 25% size)")
        print("  • MARKET FILTER: ADX > 25 required for entry")
        print("  • CLOUD FILTER: Long only above cloud, Short only below cloud")
        print("  • TRADING COSTS: 0.1% slippage, 0.06% commission per trade")
        print("  • CONSECUTIVE LOSS PROTECTION: Position auto-reduction on losing streaks")
        print("  • PARTIAL TAKE PROFIT: 25% at +5%, 35% at +10%, 40% at +15% for risk management")
        print("="*80)
        
        results = []
        
        # 각 분기별 백테스트
        successful_periods = 0
        failed_periods = []
        
        for period in self.periods:
            print(f"\nProcessing Window {period['name']}...")
            result = self.run_walk_forward_window(period)
            
            if result:
                results.append(result)
                self.all_results.append(result)
                successful_periods += 1
                
                # Walk-Forward 성과 출력
                print(f"  ✓ Completed: Training Return={result['training_return']:.2f}%, " +
                      f"Test Return={result['test_return']:.2f}%, " +
                      f"Efficiency={result['efficiency_ratio']:.2f}, " +
                      f"Overfitting Score={result['overfitting_score']:.1f}")
                
                # 거래 차트는 나중에 한 번에 표시하기 위해 저장만
                try:
                    self.plot_quarter_with_trades(result, show=False)
                except Exception as plot_error:
                    print(f"  ⚠️ Warning: Failed to plot chart for {period['name']}: {plot_error}")
            else:
                failed_periods.append(period['name'])
                print(f"  ❌ Failed to process {period['name']}")
        
        # 처리 결과 요약
        print(f"\n📊 Processing Summary:")
        print(f"  • Successful: {successful_periods}/{len(self.periods)} periods")
        if failed_periods:
            print(f"  • Failed: {', '.join(failed_periods)}")
        
        # 전체 요약 (결과가 있을 경우만)
        if results:
            self.generate_summary_report(results)
            
            # 모든 분기별 차트를 한 번에 표시
            show_charts = input("\n📊 Display all quarterly charts? (y/n): ")
            if show_charts.lower() == 'y':
                self.show_all_charts(results)
        else:
            print("\n❌ No results to summarize. Analysis failed.")
        
        return results
    
    def show_all_charts(self, results: List[Dict]):
        """모든 차트를 한 번에 표시"""
        print("\n📈 Displaying all charts...")
        
        # 1. 먼저 누적 수익률 차트 표시
        print("\n1. Cumulative Performance Chart")
        self.plot_cumulative_performance(results)
        
        # 2. Walk-Forward 효율성 차트
        print("\n2. Walk-Forward Efficiency Analysis")
        self.plot_walk_forward_efficiency(results)
        
        # 3. 상세 윈도우별 성과 (옵션)
        # 너무 많은 차트가 표시되므로 주석 처리
        # for i, result in enumerate(results, 1):
        #     print(f"\n   [{i}/{len(results)}] {result['window']}")
        #     try:
        #         self.plot_window_analysis(result, show=True)
        #     except Exception as e:
        #         print(f"   Failed to display chart for {result['window']}: {e}")
        
        print("\n✅ All charts displayed")
    
    def plot_walk_forward_efficiency(self, results: List[Dict], show: bool = True):
        """Walk-Forward 효율성 분석 차트"""
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        
        windows = [r['window'] for r in results]
        x = np.arange(len(windows))
        
        # 1. Efficiency Ratio 추이
        efficiency_ratios = [r['efficiency_ratio'] for r in results]
        
        colors = ['green' if 0.5 <= er <= 1.5 else 'orange' if 0.3 <= er <= 2.0 else 'red' 
                 for er in efficiency_ratios]
        
        ax1.bar(x, efficiency_ratios, color=colors, alpha=0.7)
        ax1.axhline(y=1.0, color='black', linestyle='--', alpha=0.5, label='Perfect Efficiency')
        ax1.axhline(y=0.5, color='red', linestyle='--', alpha=0.3, label='Min Acceptable')
        ax1.axhline(y=1.5, color='red', linestyle='--', alpha=0.3, label='Max Acceptable')
        
        ax1.set_xlabel('Walk-Forward Window')
        ax1.set_ylabel('Efficiency Ratio')
        ax1.set_title('Walk-Forward Efficiency Ratio (Test Return / Training Return)')
        ax1.set_xticks(x)
        ax1.set_xticklabels(windows, rotation=45)
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 2. Consistency Analysis
        consistency_scores = [r['consistency'] for r in results]
        test_returns = [r['test_return'] for r in results]
        
        ax2_twin = ax2.twinx()
        
        line1 = ax2.plot(x, consistency_scores, 'bo-', linewidth=2, markersize=8, 
                        label='Consistency Score')
        line2 = ax2_twin.plot(x, test_returns, 'go-', linewidth=2, markersize=8, 
                            label='Test Return')
        
        ax2.set_xlabel('Walk-Forward Window')
        ax2.set_ylabel('Consistency Score', color='b')
        ax2_twin.set_ylabel('Test Return (%)', color='g')
        ax2.set_title('Consistency vs Performance')
        ax2.set_xticks(x)
        ax2.set_xticklabels(windows, rotation=45)
        ax2.grid(True, alpha=0.3)
        
        lines = line1 + line2
        labels = [l.get_label() for l in lines]
        ax2.legend(lines, labels, loc='best')
        
        # 3. Robustness Score Heatmap
        # Create robustness matrix
        metrics = ['Efficiency', 'Overfitting', 'Consistency', 'Sharpe']
        scores = []
        
        for r in results:
            eff_score = 100 if 0.5 <= r['efficiency_ratio'] <= 1.5 else 50 if 0.3 <= r['efficiency_ratio'] <= 2.0 else 0
            over_score = 100 - min(r['overfitting_score'], 100)
            cons_score = r['consistency'] * 100
            sharpe_score = min(max(r['test_sharpe'] * 33.33, 0), 100)  # Scale Sharpe to 0-100
            
            scores.append([eff_score, over_score, cons_score, sharpe_score])
        
        scores_array = np.array(scores).T
        
        im = ax3.imshow(scores_array, cmap='RdYlGn', aspect='auto', vmin=0, vmax=100)
        
        ax3.set_xticks(np.arange(len(windows)))
        ax3.set_yticks(np.arange(len(metrics)))
        ax3.set_xticklabels(windows, rotation=45)
        ax3.set_yticklabels(metrics)
        ax3.set_title('Walk-Forward Robustness Heatmap')
        
        # Add colorbar
        cbar = plt.colorbar(im, ax=ax3)
        cbar.set_label('Score (0-100)')
        
        # 4. Training vs Test Scatter
        training_returns = [r['training_return'] for r in results]
        
        ax4.scatter(training_returns, test_returns, s=100, alpha=0.6, c=efficiency_ratios, 
                   cmap='RdYlGn', vmin=0, vmax=2)
        
        # Add diagonal line (perfect efficiency)
        min_val = min(min(training_returns), min(test_returns))
        max_val = max(max(training_returns), max(test_returns))
        ax4.plot([min_val, max_val], [min_val, max_val], 'k--', alpha=0.5, label='Perfect Efficiency')
        
        # Add efficiency zones
        ax4.plot([min_val, max_val], [min_val*0.5, max_val*0.5], 'r--', alpha=0.3, label='50% Efficiency')
        ax4.plot([min_val, max_val], [min_val*1.5, max_val*1.5], 'r--', alpha=0.3, label='150% Efficiency')
        
        ax4.set_xlabel('Training Return (%)')
        ax4.set_ylabel('Test Return (%)')
        ax4.set_title('Training vs Test Returns (Color = Efficiency Ratio)')
        ax4.grid(True, alpha=0.3)
        ax4.legend()
        
        # Add colorbar for efficiency
        sm = plt.cm.ScalarMappable(cmap='RdYlGn', norm=plt.Normalize(vmin=0, vmax=2))
        sm.set_array([])
        cbar2 = plt.colorbar(sm, ax=ax4)
        cbar2.set_label('Efficiency Ratio')
        
        plt.tight_layout()
        
        # 저장
        symbol_clean = self.symbol.replace('/', '_')
        filename = f'zlmacd_ichimoku_{symbol_clean}_walk_forward_efficiency_{self.timeframe}.png'
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        print(f"Walk-Forward efficiency chart saved as: {filename}")
        
        if show:
            plt.show()
        else:
            plt.close(fig)
    
    def plot_cumulative_performance(self, results: List[Dict], show: bool = True):
        """누적 성과 차트"""
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        
        # 1. 누적 수익률
        windows = [r['window'] for r in results]
        test_returns = [r['test_return'] for r in results]
        
        # 복리 수익률 계산
        cumulative = [0]
        compound_return = 1.0
        for ret in test_returns:
            compound_return *= (1 + ret / 100)
            cumulative.append((compound_return - 1) * 100)
        
        ax1.plot(range(len(cumulative)), cumulative, 'b-', linewidth=3, marker='o', markersize=8)
        ax1.fill_between(range(len(cumulative)), 0, cumulative, alpha=0.3)
        ax1.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        
        # 각 윈도우 표시
        for i, (w, r) in enumerate(zip(windows, test_returns)):
            color = 'green' if r > 0 else 'red'
            ax1.annotate(f"{r:+.1f}%", 
                        xy=(i+1, cumulative[i+1]),
                        xytext=(0, 10), textcoords='offset points',
                        ha='center', fontsize=8,
                        bbox=dict(boxstyle='round,pad=0.3', 
                                facecolor=color, alpha=0.3))
        
        ax1.set_title(f'Cumulative Test Returns - ZL MACD + Ichimoku Walk-Forward ({self.symbol} - {self.timeframe})', fontsize=14)
        ax1.set_xlabel('Walk-Forward Window')
        ax1.set_ylabel('Cumulative Return (%)')
        ax1.set_xticks(range(1, len(windows)+1))
        ax1.set_xticklabels(windows, rotation=45)
        ax1.grid(True, alpha=0.3)
        
        # 2. Training vs Test 비교
        x = np.arange(len(windows))
        width = 0.35
        
        training_returns = [r['training_return'] for r in results]
        
        bars1 = ax2.bar(x - width/2, training_returns, width, label='Training', alpha=0.7, color='blue')
        bars2 = ax2.bar(x + width/2, test_returns, width, label='Test', alpha=0.7, color='orange')
        
        ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        
        # Efficiency Ratio 표시
        for i, r in enumerate(results):
            eff = r['efficiency_ratio']
            color = 'green' if 0.5 <= eff <= 1.5 else 'red'
            ax2.text(i, max(training_returns[i], test_returns[i]) + 2, 
                    f'{eff:.1f}', ha='center', fontsize=8, color=color)
        
        ax2.set_xlabel('Walk-Forward Window')
        ax2.set_ylabel('Return (%)')
        ax2.set_title('Training vs Test Returns (Efficiency Ratio shown above)')
        ax2.set_xticks(x)
        ax2.set_xticklabels(windows, rotation=45)
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # 3. Overfitting Score 분석
        overfitting_scores = [r['overfitting_score'] for r in results]
        
        colors = ['green' if score < 20 else 'orange' if score < 40 else 'red' for score in overfitting_scores]
        bars = ax3.bar(x, overfitting_scores, color=colors, alpha=0.7)
        
        # 임계값 선 추가
        ax3.axhline(y=20, color='green', linestyle='--', alpha=0.5, label='Low Overfitting (<20)')
        ax3.axhline(y=40, color='orange', linestyle='--', alpha=0.5, label='Moderate Overfitting')
        
        ax3.set_xlabel('Walk-Forward Window')
        ax3.set_ylabel('Overfitting Score')
        ax3.set_title('Overfitting Analysis (Lower is Better)')
        ax3.set_xticks(x)
        ax3.set_xticklabels(windows, rotation=45)
        ax3.set_ylim(0, 100)
        ax3.grid(True, alpha=0.3)
        ax3.legend()
        
        # 4. Test 기간 샤프 비율 및 드로우다운
        test_sharpes = [r['test_sharpe'] for r in results]
        test_max_dds = [-r['test_max_dd'] for r in results]  # 음수로 표시
        
        ax4_twin = ax4.twinx()
        
        line1 = ax4.plot(x, test_sharpes, 'go-', linewidth=2, markersize=8, label='Test Sharpe Ratio')
        line2 = ax4_twin.plot(x, test_max_dds, 'ro-', linewidth=2, markersize=8, label='Test Max Drawdown')
        
        ax4.set_xlabel('Walk-Forward Window')
        ax4.set_ylabel('Sharpe Ratio', color='g')
        ax4_twin.set_ylabel('Max Drawdown (%)', color='r')
        ax4.set_title('Test Period Risk-Adjusted Performance')
        ax4.set_xticks(x)
        ax4.set_xticklabels(windows, rotation=45)
        ax4.grid(True, alpha=0.3)
        ax4.axhline(y=0, color='black', linestyle='--', alpha=0.5)
        
        # 범례 통합
        lines = line1 + line2
        labels = [l.get_label() for l in lines]
        ax4.legend(lines, labels, loc='best')
        
        plt.tight_layout()
        
        # 저장
        symbol_clean = self.symbol.replace('/', '_')
        filename = f'zlmacd_ichimoku_{symbol_clean}_cumulative_performance_{self.timeframe}.png'
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        print(f"Cumulative performance chart saved as: {filename}")
        
        if show:
            plt.show()
        else:
            plt.close(fig)
    
    def generate_summary_report(self, results: List[Dict]):
        """Walk-Forward 분석 전체 성과 요약"""
        print("\n" + "="*80)
        print(f"ZL MACD + ICHIMOKU - WALK-FORWARD ANALYSIS SUMMARY ({self.symbol} - {self.timeframe})")
        print("="*80)
        
        # 결과가 없는 경우 처리
        if not results:
            print("\n❌ No results to analyze.")
            return
        
        # Walk-Forward 전체 통계
        total_test_return = sum(r['test_return'] for r in results)
        avg_test_return = np.mean([r['test_return'] for r in results])
        positive_windows = sum(1 for r in results if r['test_return'] > 0)
        consistent_windows = sum(1 for r in results if r['consistency'] == 1)
        
        print("\n📊 Walk-Forward Overall Performance:")
        print(f"  • Total Test Return: {total_test_return:.2f}%")
        print(f"  • Average Test Return per Window: {avg_test_return:.2f}%")
        print(f"  • Profitable Windows: {positive_windows}/{len(results)} ({positive_windows/len(results)*100:.1f}%)")
        print(f"  • Consistent Windows: {consistent_windows}/{len(results)} ({consistent_windows/len(results)*100:.1f}%)")
        
        # Training vs Test 비교
        avg_train_return = np.mean([r['training_return'] for r in results])
        avg_efficiency = np.mean([r['efficiency_ratio'] for r in results])
        
        print("\n🔄 Training vs Test Performance:")
        print(f"  • Average Training Return: {avg_train_return:.2f}%")
        print(f"  • Average Test Return: {avg_test_return:.2f}%")
        print(f"  • Average Efficiency Ratio: {avg_efficiency:.2f}")
        print(f"  • Performance Degradation: {((avg_test_return - avg_train_return) / avg_train_return * 100):.1f}%")
        
        # 과적합 분석
        avg_overfitting = np.mean([r['overfitting_score'] for r in results])
        low_overfitting = sum(1 for r in results if r['overfitting_score'] < 20)
        
        print("\n🎯 Overfitting Analysis:")
        print(f"  • Average Overfitting Score: {avg_overfitting:.1f}")
        print(f"  • Low Overfitting Windows: {low_overfitting}/{len(results)} ({low_overfitting/len(results)*100:.1f}%)")
        
        # 리스크 지표
        test_sharpes = [r['test_sharpe'] for r in results]
        test_max_dds = [r['test_max_dd'] for r in results]
        
        print("\n📈 Risk Metrics (Test Period):")
        print(f"  • Average Sharpe Ratio: {np.mean(test_sharpes):.2f}")
        print(f"  • Best Sharpe: {max(test_sharpes):.2f}")
        print(f"  • Average Max Drawdown: {np.mean(test_max_dds):.1f}%")
        print(f"  • Worst Drawdown: {max(test_max_dds):.1f}%")
        
        # Walk-Forward Windows 상세
        print("\n📅 Walk-Forward Windows Detail:")
        print("-"*120)
        print(f"{'Window':<8} {'Training Return':<15} {'Test Return':<12} {'Efficiency':<12} {'Overfitting':<12} {'Test Sharpe':<12} {'Test DD':<10}")
        print("-"*120)
        
        for r in results:
            print(f"{r['window']:<8} {r['training_return']:>13.1f}% {r['test_return']:>10.1f}% "
                  f"{r['efficiency_ratio']:>11.2f} {r['overfitting_score']:>11.1f} "
                  f"{r['test_sharpe']:>11.2f} {r['test_max_dd']:>8.1f}%")
        
        # 최고/최악 Window
        best_window = max(results, key=lambda x: x['test_return'])
        worst_window = min(results, key=lambda x: x['test_return'])
        most_efficient = max(results, key=lambda x: x['efficiency_ratio'] if x['efficiency_ratio'] < 2 else 0)
        
        print(f"\n🏆 Best Test Performance: {best_window['window']} ({best_window['test_return']:.1f}%)")
        print(f"📉 Worst Test Performance: {worst_window['window']} ({worst_window['test_return']:.1f}%)")
        print(f"⚖️ Most Efficient Window: {most_efficient['window']} (Efficiency: {most_efficient['efficiency_ratio']:.2f})")
        
        # Walk-Forward 강건성 평가
        print("\n💎 Walk-Forward Robustness Evaluation:")
        
        # 1. 일관성 점수
        consistency_score = consistent_windows / len(results) * 100
        print(f"  • Consistency Score: {consistency_score:.1f}%")
        
        # 2. 안정성 점수 (효율성 비율의 표준편차)
        efficiency_std = np.std([r['efficiency_ratio'] for r in results])
        stability_score = 100 / (1 + efficiency_std)
        print(f"  • Stability Score: {stability_score:.1f}%")
        
        # 3. 전체 강건성 점수
        robustness_score = (consistency_score + stability_score) / 2
        print(f"  • Overall Robustness Score: {robustness_score:.1f}%")
        
        # 강건성 평가
        if robustness_score > 70:
            rating = "EXCELLENT - Highly robust strategy"
        elif robustness_score > 50:
            rating = "GOOD - Reasonably robust strategy"
        elif robustness_score > 30:
            rating = "FAIR - Some overfitting concerns"
        else:
            rating = "POOR - Significant overfitting risk"
            
        print(f"  • Rating: {rating}")
        
        print("\n💡 Key Insights:")
        print("  1. ZL MACD eliminates lag for faster signal detection")
        print("  2. Ichimoku Cloud provides multi-layered trend confirmation")
        print("  3. 3+ signals required for entry (ZL MACD cross + Cloud + TK cross)")
        print("  4. Dynamic exits: Cloud break for trend reversal, Kijun touch for profit taking")
        print("  5. Initial tight stop (1.5%) + Trailing stop (10% from peak)")
        print("  6. Pyramiding: 3 levels at 4%, 6%, 9% profit (75%, 50%, 25% size)")
        print("  7. ADX filter (>25) ensures trading only in trending markets")
        print("  8. Cloud acts as dynamic support/resistance for risk management")


def main():
    """메인 실행"""
    print("\n" + "="*80)
    print("ZL MACD + Ichimoku Strategy - Multi-Symbol & Multi-Timeframe Analysis")
    print("="*80)
    
    # 타임프레임 선택
    print("\nSelect timeframe for analysis:")
    print("1. 4H (4-hour)")
    print("2. 1H (1-hour)")
    print("3. 15M (15-minute)")
    
    timeframe_choice = input("\nEnter your choice (1-3): ")
    
    timeframe_map = {
        '1': '4h',
        '2': '1h',
        '3': '15m'
    }
    
    if timeframe_choice not in timeframe_map:
        print("Invalid choice. Using default 4H timeframe.")
        timeframe = '4h'
    else:
        timeframe = timeframe_map[timeframe_choice]
    
    # 심볼 선택
    print("\nSelect trading pair for analysis:")
    print("1. BTC/USDT (Bitcoin)")
    print("2. ETH/USDT (Ethereum)")
    print("3. XRP/USDT (Ripple)")
    
    symbol_choice = input("\nEnter your choice (1-3): ")
    
    symbol_map = {
        '1': 'BTC/USDT',
        '2': 'ETH/USDT',
        '3': 'XRP/USDT'
    }
    
    if symbol_choice not in symbol_map:
        print("Invalid choice. Using default BTC/USDT.")
        symbol = 'BTC/USDT'
    else:
        symbol = symbol_map[symbol_choice]
    
    try:
        analyzer = ZLMACDIchimokuWalkForward(timeframe=timeframe, symbol=symbol)
        print(f"\n✓ Analyzer initialized successfully with {symbol} on {timeframe} timeframe")
        
        results = analyzer.run_analysis()
    except Exception as e:
        print(f"\n❌ Critical error in main: {e}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return
    
    # 결과 저장
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # JSON으로 저장 (DataFrame 제외)
    clean_results = []
    for r in results:
        clean_r = {
            'window': r['window'],
            'training_start': r.get('training_start', ''),
            'training_end': r.get('training_end', ''),
            'test_start': r.get('test_start', ''),
            'test_end': r.get('test_end', ''),
            'training_return': r.get('training_return', 0),
            'test_return': r.get('test_return', 0),
            'efficiency_ratio': r.get('efficiency_ratio', 0),
            'overfitting_score': r.get('overfitting_score', 0),
            'consistency': r.get('consistency', 0),
            'test_sharpe': r.get('test_sharpe', 0),
            'test_max_dd': r.get('test_max_dd', 0),
            'test_trades': r.get('test_trades', 0),
            'test_win_rate': r.get('test_win_rate', 0),
            'timeframe': timeframe,
            'symbol': analyzer.symbol
        }
        clean_results.append(clean_r)
    
    symbol_clean = analyzer.symbol.replace('/', '_')
    with open(f'zlmacd_ichimoku_{symbol_clean}_wf_results_{timeframe}_{timestamp}.json', 'w') as f:
        json.dump(clean_results, f, indent=2)
    
    print(f"\n✅ ZL MACD + Ichimoku strategy analysis complete!")
    print(f"Results saved as: zlmacd_ichimoku_{symbol_clean}_wf_results_{timeframe}_{timestamp}.json")


if __name__ == "__main__":
    main()
