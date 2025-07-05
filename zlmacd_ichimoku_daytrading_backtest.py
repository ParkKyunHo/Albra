"""
ZL MACD + Ichimoku Day Trading Strategy - Walk-Forward Analysis
데이트레이딩용 ZL MACD + Ichimoku 결합 전략 백테스팅
- 15분봉 사용
- 4개 조건 모두 충족 원칙 유지
- 노이즈 필터링 및 수수료 최적화
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

# ccxt 설치 확인
try:
    import ccxt
except ImportError:
    print("❌ ccxt not installed. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "ccxt"])
    import ccxt

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
cache_dir = os.path.join(script_dir, 'wf_cache_daytrading')
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


class ZLMACDIchimokuDayTradingStrategy:
    """ZL MACD + Ichimoku Day Trading Strategy"""
    
    def __init__(self, initial_capital: float = 10000, timeframe: str = '15m', symbol: str = 'BTC/USDT'):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position = None
        self.trades = []
        self.equity_curve = []
        self.last_trade_result = None
        self.consecutive_losses = 0
        self.recent_trades = []
        self.daily_trades = 0  # 일일 거래 횟수
        self.last_trade_date = None
        self.recent_signals = []  # 최근 신호 추적 (노이즈 필터)
        
        # 타임프레임 설정 (15분봉 고정)
        self.timeframe = '15m'
        self.candles_per_day = 96  # 15분봉 기준
        
        # 데이트레이딩용 파라미터
        self.position_size_pct = 0.05  # 5% 포지션
        self.daily_trade_limit = 15    # 일일 최대 거래
        self.initial_stop_loss = 0.005 # 0.5% 타이트한 손절
        self.trailing_stop_distance = 0.003  # 0.3% 트레일링
        self.time_stop_minutes = 60    # 60분 시간 손절
        
        # ZL MACD 파라미터 (더 민감하게)
        self.zlmacd_fast = 6      # 기존 12
        self.zlmacd_slow = 13     # 기존 26
        self.zlmacd_signal = 5    # 기존 9
        
        # Ichimoku 파라미터 (더 민감하게)
        self.tenkan_period = 5    # 기존 9
        self.kijun_period = 13    # 기존 26
        self.senkou_b_period = 26 # 기존 52
        self.chikou_shift = 13    # 기존 26
        self.cloud_shift = 13     # 기존 26
        
        # 거래 비용 (메이커 주문 가정)
        self.symbol = symbol
        self.commission = 0.0002  # 0.02% 메이커
        self.slippage = 0.0005    # 0.05% (limit order)
        
        # 최소 수익 목표 (수수료의 3배)
        self.min_profit_target = (self.commission + self.slippage) * 3
        
        # 부분 청산 레벨 (데이트레이딩용)
        self.partial_exit_levels = [
            {'profit_pct': 0.5, 'exit_ratio': 0.50},   # 0.5%에서 50% 청산
            {'profit_pct': 1.0, 'exit_ratio': 0.25},   # 1.0%에서 25% 청산
            {'profit_pct': 2.0, 'exit_ratio': 0.15},   # 2.0%에서 15% 청산
            # 나머지 10%는 트레일링 스톱
        ]
        self.partial_exits_done = {}
        
        # 노이즈 필터 파라미터
        self.volume_filter_ratio = 0.5   # 평균 볼륨의 50% 이상
        self.atr_filter_low = 0.5        # ATR 하한
        self.atr_filter_high = 2.0       # ATR 상한
        self.signal_cooldown = 3         # 3개 캔들 내 중복 신호 무시
        
        # 세션별 가중치
        self.session_weights = {
            'asia': 0.5,      # 아시아 세션
            'europe': 1.0,    # 유럽 세션
            'us': 1.2,        # 미국 세션
            'overlap': 1.5    # 유럽/미국 중복
        }
        
        # 캐시
        self.data_cache = {}
        self.indicators_cache = {}
        
        # 일일 손실 한도
        self.daily_loss_limit = 0.02  # 2% (데이트레이딩은 더 타이트하게)
        self.daily_loss = 0
        
        # 레버리지 설정
        self.leverage = 5  # 데이트레이딩은 낮은 레버리지
        
        print(f"\n✅ ZL MACD + Ichimoku Day Trading Strategy initialized:")
        print(f"  • Symbol: {self.symbol}")
        print(f"  • Timeframe: {self.timeframe}")
        print(f"  • Position Size: {self.position_size_pct*100}%")
        print(f"  • Stop Loss: {self.initial_stop_loss*100}%")
        print(f"  • Daily Trade Limit: {self.daily_trade_limit}")
        print(f"  • Commission: {self.commission*100}% (maker)")
    
    def calculate_zlema(self, series: pd.Series, period: int) -> pd.Series:
        """Zero Lag EMA 계산"""
        ema1 = series.ewm(span=period, adjust=False).mean()
        ema2 = ema1.ewm(span=period, adjust=False).mean()
        zlema = 2 * ema1 - ema2
        return zlema
    
    def calculate_zlmacd(self, df: pd.DataFrame) -> pd.DataFrame:
        """ZL MACD 계산"""
        zlema_fast = self.calculate_zlema(df['close'], self.zlmacd_fast)
        zlema_slow = self.calculate_zlema(df['close'], self.zlmacd_slow)
        
        df['zlmacd'] = zlema_fast - zlema_slow
        df['zlmacd_signal'] = df['zlmacd'].ewm(span=self.zlmacd_signal, adjust=False).mean()
        df['zlmacd_histogram'] = df['zlmacd'] - df['zlmacd_signal']
        
        return df
    
    def calculate_ichimoku(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ichimoku Cloud 계산"""
        # Tenkan-sen (전환선)
        high_9 = df['high'].rolling(self.tenkan_period).max()
        low_9 = df['low'].rolling(self.tenkan_period).min()
        df['tenkan_sen'] = (high_9 + low_9) / 2
        
        # Kijun-sen (기준선)
        high_26 = df['high'].rolling(self.kijun_period).max()
        low_26 = df['low'].rolling(self.kijun_period).min()
        df['kijun_sen'] = (high_26 + low_26) / 2
        
        # Senkou Span A (선행스팬 A)
        df['senkou_span_a'] = ((df['tenkan_sen'] + df['kijun_sen']) / 2).shift(self.cloud_shift)
        
        # Senkou Span B (선행스팬 B)
        high_52 = df['high'].rolling(self.senkou_b_period).max()
        low_52 = df['low'].rolling(self.senkou_b_period).min()
        df['senkou_span_b'] = ((high_52 + low_52) / 2).shift(self.cloud_shift)
        
        # Chikou Span (후행스팬)
        df['chikou_span'] = df['close'].shift(-self.chikou_shift)
        
        # Cloud top and bottom
        df['cloud_top'] = df[['senkou_span_a', 'senkou_span_b']].max(axis=1)
        df['cloud_bottom'] = df[['senkou_span_a', 'senkou_span_b']].min(axis=1)
        
        # Cloud color (bullish/bearish)
        df['cloud_color'] = (df['senkou_span_a'] > df['senkou_span_b']).astype(int)
        
        return df
    
    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """ATR 계산"""
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift(1))
        low_close = abs(df['low'] - df['close'].shift(1))
        
        df['tr'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = df['tr'].rolling(period).mean()
        
        return df
    
    def get_session_weight(self, timestamp: pd.Timestamp) -> float:
        """거래 세션별 가중치 반환"""
        hour = timestamp.hour
        
        # UTC 기준 세션 시간
        if 0 <= hour < 8:      # 아시아 세션
            return self.session_weights['asia']
        elif 8 <= hour < 14:   # 유럽 세션
            return self.session_weights['europe']
        elif 14 <= hour < 16:  # 유럽/미국 중복
            return self.session_weights['overlap']
        elif 16 <= hour < 22:  # 미국 세션
            return self.session_weights['us']
        else:
            return 0.3  # 기타 시간대
    
    def apply_noise_filters(self, df: pd.DataFrame, index: int) -> bool:
        """노이즈 필터 적용"""
        # 볼륨 필터
        avg_volume = df['volume'].rolling(20).mean().iloc[index]
        current_volume = df['volume'].iloc[index]
        if current_volume < avg_volume * self.volume_filter_ratio:
            return False
        
        # ATR 필터
        if 'atr' in df.columns:
            atr = df['atr'].iloc[index]
            atr_avg = df['atr'].rolling(20).mean().iloc[index]
            if pd.notna(atr) and pd.notna(atr_avg):
                if atr < atr_avg * self.atr_filter_low or atr > atr_avg * self.atr_filter_high:
                    return False
        
        # 최근 신호 중복 체크
        current_time = df.index[index]
        for signal_time, signal_type in self.recent_signals:
            time_diff = (current_time - signal_time).total_seconds() / 60  # 분 단위
            if time_diff < self.signal_cooldown * 15:  # 15분봉 기준
                return False
        
        return True
    
    def check_entry_conditions(self, df: pd.DataFrame, index: int, position_type: str) -> dict:
        """진입 조건 확인 - 4개 조건 모두 충족 필요"""
        result = {
            'can_enter': False,
            'signals': [],
            'strength': 0
        }
        
        # 필수 데이터 확인
        if index < max(self.tenkan_period, self.kijun_period, self.senkou_b_period):
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
                result['strength'] += 1
            
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
                result['strength'] += 1
        
        # 모든 4개 조건이 충족되어야 진입 가능
        result['can_enter'] = result['strength'] >= 4
        
        # 노이즈 필터 적용
        if result['can_enter']:
            result['can_enter'] = self.apply_noise_filters(df, index)
        
        return result
    
    def check_time_stop(self, entry_time, current_time, pnl_pct) -> Optional[str]:
        """시간 기반 손절 확인"""
        hold_time_minutes = (current_time - entry_time).total_seconds() / 60
        
        # 30분 경과 시 손실 중이면 50% 청산
        if hold_time_minutes > 30 and pnl_pct < 0:
            return 'TIME_STOP_30M'
        
        # 60분 경과 시 목표 미달성이면 전체 청산
        if hold_time_minutes > self.time_stop_minutes and pnl_pct < self.min_profit_target:
            return 'TIME_STOP_60M'
        
        return None
    
    def check_exit_conditions(self, df: pd.DataFrame, index: int, position_type: str) -> dict:
        """종료 조건 확인"""
        result = {
            'should_exit': False,
            'exit_type': None,
            'reasons': []
        }
        
        current_price = df['close'].iloc[index]
        low = df['low'].iloc[index]
        high = df['high'].iloc[index]
        
        if position_type == 'LONG':
            # 구름 하단 돌파
            if current_price < df['cloud_bottom'].iloc[index]:
                result['should_exit'] = True
                result['exit_type'] = 'CLOUD_BREAK'
                result['reasons'].append('Price broke below cloud')
            
            # 기준선 터치
            elif low <= df['kijun_sen'].iloc[index]:
                result['should_exit'] = True
                result['exit_type'] = 'KIJUN_TOUCH'
                result['reasons'].append('Price touched Kijun-sen')
            
            # MACD 데드크로스
            elif df['zlmacd'].iloc[index] < df['zlmacd_signal'].iloc[index]:
                result['should_exit'] = True
                result['exit_type'] = 'MACD_CROSS'
                result['reasons'].append('MACD dead cross')
        
        else:  # SHORT
            # 구름 상단 돌파
            if current_price > df['cloud_top'].iloc[index]:
                result['should_exit'] = True
                result['exit_type'] = 'CLOUD_BREAK'
                result['reasons'].append('Price broke above cloud')
            
            # 기준선 터치
            elif high >= df['kijun_sen'].iloc[index]:
                result['should_exit'] = True
                result['exit_type'] = 'KIJUN_TOUCH'
                result['reasons'].append('Price touched Kijun-sen')
            
            # MACD 골든크로스
            elif df['zlmacd'].iloc[index] > df['zlmacd_signal'].iloc[index]:
                result['should_exit'] = True
                result['exit_type'] = 'MACD_CROSS'
                result['reasons'].append('MACD golden cross')
        
        return result
    
    def calculate_position_size(self) -> float:
        """포지션 크기 계산"""
        # 기본 포지션 크기
        base_size = self.position_size_pct
        
        # 연속 손실에 따른 조정
        if self.consecutive_losses >= 3:
            base_size *= 0.7
        elif self.consecutive_losses >= 5:
            base_size *= 0.5
        
        # 일일 거래 횟수에 따른 조정
        if self.daily_trades > 10:
            base_size *= 0.8
        
        return min(base_size, 0.1)  # 최대 10%
    
    def run_backtest(self, df: pd.DataFrame) -> Dict:
        """백테스트 실행"""
        # 지표 계산
        df = self.calculate_zlmacd(df)
        df = self.calculate_ichimoku(df)
        df = self.calculate_atr(df)
        
        # 백테스트 루프
        for i in range(100, len(df)):
            current_time = df.index[i]
            current_price = df['close'].iloc[i]
            
            # 일일 거래 횟수 리셋
            if self.last_trade_date and current_time.date() != self.last_trade_date:
                self.daily_trades = 0
                self.daily_loss = 0
            
            # 포지션이 있을 때
            if self.position:
                # 시간 손절 체크
                time_stop = self.check_time_stop(
                    self.position['entry_time'],
                    current_time,
                    self.position['pnl_pct']
                )
                
                if time_stop:
                    self.close_position(current_price, i, current_time, time_stop)
                    continue
                
                # 일반 종료 조건 체크
                exit_conditions = self.check_exit_conditions(df, i, self.position['type'])
                if exit_conditions['should_exit']:
                    self.close_position(current_price, i, current_time, exit_conditions['exit_type'])
                    continue
                
                # 부분 청산 체크
                self.check_partial_exits(current_price, current_time)
                
                # 트레일링 스톱 업데이트
                self.update_trailing_stop(current_price)
            
            # 포지션이 없을 때
            else:
                # 일일 거래 제한 체크
                if self.daily_trades >= self.daily_trade_limit:
                    continue
                
                # 일일 손실 한도 체크
                if self.daily_loss >= self.daily_loss_limit * self.capital:
                    continue
                
                # 롱 진입 체크
                long_conditions = self.check_entry_conditions(df, i, 'LONG')
                if long_conditions['can_enter']:
                    self.open_position('LONG', current_price, i, current_time, long_conditions)
                    continue
                
                # 숏 진입 체크
                short_conditions = self.check_entry_conditions(df, i, 'SHORT')
                if short_conditions['can_enter']:
                    self.open_position('SHORT', current_price, i, current_time, short_conditions)
            
            # 자산 곡선 업데이트
            self.update_equity_curve(current_price, current_time)
        
        # 백테스트 결과 계산
        return self.calculate_results()
    
    def open_position(self, position_type: str, price: float, index: int, time: pd.Timestamp, conditions: dict):
        """포지션 오픈"""
        # 세션 가중치 적용
        session_weight = self.get_session_weight(time)
        position_size = self.calculate_position_size() * session_weight
        
        # 포지션 생성
        self.position = {
            'type': position_type,
            'entry_price': price,
            'entry_time': time,
            'entry_index': index,
            'size': position_size,
            'value': self.capital * position_size,
            'stop_loss': price * (1 - self.initial_stop_loss) if position_type == 'LONG' else price * (1 + self.initial_stop_loss),
            'signals': conditions['signals'],
            'partial_exits': 0,
            'remaining_size': 1.0,  # 100%
            'pnl': 0,
            'pnl_pct': 0
        }
        
        # 거래 비용 차감
        commission = self.position['value'] * self.commission
        self.capital -= commission
        
        # 최근 신호 기록
        self.recent_signals.append((time, position_type))
        if len(self.recent_signals) > 10:
            self.recent_signals.pop(0)
        
        # 일일 거래 횟수 증가
        self.daily_trades += 1
        self.last_trade_date = time.date()
        
        print(f"  {position_type} Entry: {conditions['signals']} at ${price:.2f}")
    
    def close_position(self, price: float, index: int, time: pd.Timestamp, exit_reason: str):
        """포지션 종료"""
        if not self.position:
            return
        
        # 손익 계산
        if self.position['type'] == 'LONG':
            pnl_pct = (price / self.position['entry_price'] - 1) * self.leverage
        else:
            pnl_pct = (self.position['entry_price'] / price - 1) * self.leverage
        
        # 남은 포지션에 대한 손익
        pnl = self.position['value'] * self.position['remaining_size'] * pnl_pct
        
        # 거래 비용
        commission = self.position['value'] * self.position['remaining_size'] * self.commission
        net_pnl = pnl - commission
        
        # 자본 업데이트
        self.capital += net_pnl
        
        # 일일 손실 업데이트
        if net_pnl < 0:
            self.daily_loss += abs(net_pnl)
        
        # 거래 기록
        trade_record = {
            'entry_time': self.position['entry_time'],
            'exit_time': time,
            'direction': self.position['type'].lower(),
            'entry_price': self.position['entry_price'],
            'exit_price': price,
            'pnl': net_pnl,
            'pnl_pct': pnl_pct,
            'holding_time': (time - self.position['entry_time']).total_seconds() / 60,  # 분 단위
            'exit_reason': exit_reason,
            'signals': self.position['signals']
        }
        self.trades.append(trade_record)
        
        # 연속 손실 업데이트
        if net_pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        
        # 포지션 초기화
        self.position = None
        self.partial_exits_done = {}
    
    def check_partial_exits(self, current_price: float, current_time: pd.Timestamp):
        """부분 청산 체크"""
        if not self.position:
            return
        
        # 현재 수익률 계산
        if self.position['type'] == 'LONG':
            pnl_pct = (current_price / self.position['entry_price'] - 1) * 100
        else:
            pnl_pct = (self.position['entry_price'] / current_price - 1) * 100
        
        # 부분 청산 레벨 체크
        for i, level in enumerate(self.partial_exit_levels):
            level_key = f"level_{i}"
            if level_key not in self.partial_exits_done and pnl_pct >= level['profit_pct']:
                # 부분 청산 실행
                exit_size = level['exit_ratio'] * self.position['remaining_size']
                exit_value = self.position['value'] * exit_size
                
                # 손익 계산
                pnl = exit_value * (pnl_pct / 100) * self.leverage
                commission = exit_value * self.commission
                net_pnl = pnl - commission
                
                # 자본 업데이트
                self.capital += net_pnl
                
                # 포지션 업데이트
                self.position['remaining_size'] -= exit_size
                self.partial_exits_done[level_key] = True
                
                print(f"    Partial exit ({level['exit_ratio']*100}%) at {pnl_pct:.1f}% profit")
    
    def update_trailing_stop(self, current_price: float):
        """트레일링 스톱 업데이트"""
        if not self.position:
            return
        
        if self.position['type'] == 'LONG':
            # 최고가 업데이트
            if 'highest_price' not in self.position:
                self.position['highest_price'] = current_price
            else:
                self.position['highest_price'] = max(self.position['highest_price'], current_price)
            
            # 트레일링 스톱 계산
            trailing_stop = self.position['highest_price'] * (1 - self.trailing_stop_distance)
            
            # 스톱로스 업데이트
            if trailing_stop > self.position['stop_loss']:
                self.position['stop_loss'] = trailing_stop
        
        else:  # SHORT
            # 최저가 업데이트
            if 'lowest_price' not in self.position:
                self.position['lowest_price'] = current_price
            else:
                self.position['lowest_price'] = min(self.position['lowest_price'], current_price)
            
            # 트레일링 스톱 계산
            trailing_stop = self.position['lowest_price'] * (1 + self.trailing_stop_distance)
            
            # 스톱로스 업데이트
            if trailing_stop < self.position['stop_loss']:
                self.position['stop_loss'] = trailing_stop
    
    def update_equity_curve(self, current_price: float, current_time: pd.Timestamp):
        """자산 곡선 업데이트"""
        equity = self.capital
        
        if self.position:
            # 미실현 손익 포함
            if self.position['type'] == 'LONG':
                unrealized_pnl = self.position['value'] * self.position['remaining_size'] * \
                               ((current_price / self.position['entry_price'] - 1) * self.leverage)
            else:
                unrealized_pnl = self.position['value'] * self.position['remaining_size'] * \
                               ((self.position['entry_price'] / current_price - 1) * self.leverage)
            
            equity += unrealized_pnl
        
        self.equity_curve.append({
            'time': current_time,
            'equity': equity,
            'capital': self.capital
        })
    
    def calculate_results(self) -> Dict:
        """백테스트 결과 계산"""
        if not self.trades:
            return {
                'total_return': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0,
                'total_trades': 0,
                'win_rate': 0,
                'avg_trade_duration': 0,
                'daily_avg_trades': 0,
                'commission_paid': 0
            }
        
        # 기본 통계
        total_trades = len(self.trades)
        winning_trades = sum(1 for t in self.trades if t['pnl'] > 0)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        # 수익률 계산
        total_return = (self.capital / self.initial_capital - 1) * 100
        
        # 평균 거래 시간
        avg_duration = sum(t['holding_time'] for t in self.trades) / len(self.trades)
        
        # 일평균 거래 횟수
        if self.equity_curve:
            total_days = (self.equity_curve[-1]['time'] - self.equity_curve[0]['time']).days
            daily_avg_trades = total_trades / max(total_days, 1)
        else:
            daily_avg_trades = 0
        
        # 총 수수료
        total_commission = sum(abs(t['pnl']) * self.commission for t in self.trades)
        
        # Sharpe Ratio 계산
        if len(self.equity_curve) > 1:
            returns = pd.Series([e['equity'] for e in self.equity_curve]).pct_change().dropna()
            sharpe_ratio = returns.mean() / returns.std() * np.sqrt(252 * self.candles_per_day / 24) if returns.std() > 0 else 0
        else:
            sharpe_ratio = 0
        
        # Max Drawdown 계산
        equity_series = pd.Series([e['equity'] for e in self.equity_curve])
        cummax = equity_series.cummax()
        drawdown = (equity_series - cummax) / cummax
        max_drawdown = abs(drawdown.min()) * 100
        
        return {
            'total_return': total_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'total_trades': total_trades,
            'win_rate': win_rate * 100,
            'avg_trade_duration': avg_duration,
            'daily_avg_trades': daily_avg_trades,
            'commission_paid': total_commission,
            'final_capital': self.capital
        }


class ZLMACDIchimokuDayTradingWalkForward:
    """ZL MACD + Ichimoku Day Trading Walk-Forward 분석"""
    
    def __init__(self, initial_capital: float = 10000):
        print("\nInitializing ZL MACD + Ichimoku Day Trading Walk-Forward...")
        self.initial_capital = initial_capital
        
        # 디렉토리 설정
        if __file__:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
        else:
            self.base_dir = os.getcwd()
            
        self.cache_dir = os.path.join(self.base_dir, "wf_cache_daytrading")
        self.results_cache_dir = os.path.join(self.base_dir, "wf_results_daytrading")
        
        # 디렉토리 생성
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.results_cache_dir, exist_ok=True)
        
        print(f"  Base directory: {self.base_dir}")
        print(f"  Cache directory: {self.cache_dir}")
        print(f"  Results directory: {self.results_cache_dir}")
        
        # Walk-Forward 분석 기간 (6개월 training + 1개월 test)
        self.periods = []
        
        # 2022년 1월부터 시작하여 1개월씩 슬라이딩
        start_year = 2022
        start_month = 1
        
        for i in range(12):  # 12개의 window
            # Training 시작일
            train_start_year = start_year + (start_month - 1 + i) // 12
            train_start_month = ((start_month - 1 + i) % 12) + 1
            
            # Training 종료일 (6개월 후)
            train_end_year = train_start_year + (train_start_month + 5) // 12
            train_end_month = ((train_start_month + 5) % 12) + 1
            if train_end_month == 0:
                train_end_month = 12
                train_end_year -= 1
                
            # Test 시작일 (Training 종료 다음날)
            test_start_year = train_end_year
            test_start_month = train_end_month + 1
            if test_start_month > 12:
                test_start_month = 1
                test_start_year += 1
                
            # Test 종료일 (1개월 후)
            test_end_year = test_start_year
            test_end_month = test_start_month
            if test_end_month > 12:
                test_end_month = test_end_month - 12
                test_end_year += 1
            
            period = {
                'name': f'WF_{i+1:02d}',
                'train_start': datetime(train_start_year, train_start_month, 1),
                'train_end': datetime(train_end_year, train_end_month, 1) - timedelta(days=1),
                'test_start': datetime(test_start_year, test_start_month, 1),
                'test_end': datetime(test_end_year, test_end_month, 1) + timedelta(days=30)
            }
            
            self.periods.append(period)
        
        print(f"\n✅ Walk-Forward periods initialized: {len(self.periods)} windows")
        print(f"  • Training period: 6 months")
        print(f"  • Test period: 1 month")
        print(f"  • Sliding interval: 1 month")
    
    def fetch_15m_data(self, symbol: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """15분봉 데이터를 직접 수집"""
        exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        
        print(f"  Fetching 15m data for {symbol} from {start_date.date()} to {end_date.date()}...")
        ohlcv_data = []
        since = int(start_date.timestamp() * 1000)
        end_ts = int(end_date.timestamp() * 1000)
        
        total_days = (end_date - start_date).days
        
        while since < end_ts:
            try:
                data = exchange.fetch_ohlcv(
                    symbol=symbol,
                    timeframe='15m',
                    since=since,
                    limit=1000  # 최대 1000개
                )
                
                if not data:
                    break
                    
                ohlcv_data.extend(data)
                since = data[-1][0] + 1  # 다음 시작점
                
                # Rate limit 준수
                time.sleep(exchange.rateLimit / 1000)
                
                # 진행상황 표시
                current_date = datetime.fromtimestamp(since / 1000)
                progress_days = (current_date - start_date).days
                progress = min(progress_days / total_days * 100, 100)
                print(f"\r  Progress: {progress:.1f}% - {current_date.strftime('%Y-%m-%d')}", end='')
                
            except Exception as e:
                print(f"\n  Error: {e}")
                time.sleep(5)  # 에러 시 5초 대기
                continue
        
        print()  # 줄바꿈
        
        if not ohlcv_data:
            print("  ❌ No data collected")
            return pd.DataFrame()
        
        # DataFrame 변환
        df = pd.DataFrame(ohlcv_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        # 중복 제거
        df = df[~df.index.duplicated(keep='first')]
        
        # 시간 범위 필터링
        df = df[(df.index >= start_date) & (df.index <= end_date)]
        
        print(f"  ✓ Collected {len(df)} 15m candles")
        return df
    
    def run_walk_forward_analysis(self, symbol: str = 'BTC/USDT'):
        """Walk-Forward 분석 실행"""
        print(f"\n{'='*80}")
        print(f"ZL MACD + Ichimoku Day Trading - Walk-Forward Analysis")
        print(f"{'='*80}")
        
        results = []
        data_fetcher = DataFetcherFixed()
        
        for period in self.periods:
            print(f"\nProcessing Window {period['name']}...")
            print(f"{'='*60}")
            print(f"  Window {period['name']}")
            print(f"  Training: {period['train_start'].date()} to {period['train_end'].date()}")
            print(f"  Test: {period['test_start'].date()} to {period['test_end'].date()}")
            print(f"{'='*60}")
            
            # 데이터 로드 (15분봉은 더 많은 데이터 필요)
            data_start = period['train_start'] - timedelta(days=60)  # 여유 데이터
            data_end = period['test_end']
            
            print(f"  Loading data from {data_start.date()} to {data_end.date()}")
            
            # 캐시 확인
            cache_key = f"{symbol.replace('/', '_')}_{data_start.date()}_{data_end.date()}_15m"
            cache_file = os.path.join(self.cache_dir, f"{cache_key}.pkl")
            
            if os.path.exists(cache_file):
                print(f"  Loading from cache...")
                with open(cache_file, 'rb') as f:
                    df = pickle.load(f)
            else:
                # 15분봉 데이터 직접 수집
                df = self.fetch_15m_data(symbol, data_start, data_end)
                
                if df is not None and not df.empty:
                    # 캐시에 저장
                    with open(cache_file, 'wb') as f:
                        pickle.dump(df, f)
                    print(f"  Saved to cache: {cache_key}")
            
            if df is None or df.empty:
                print(f"  ❌ Failed to load data for {period['name']}")
                continue
            
            # Training 데이터
            train_mask = (df.index >= period['train_start']) & (df.index <= period['train_end'])
            train_df = df[train_mask].copy()
            
            # Test 데이터
            test_mask = (df.index >= period['test_start']) & (df.index <= period['test_end'])
            test_df = df[test_mask].copy()
            
            print(f"  Training data: {len(train_df)} candles")
            print(f"  Test data: {len(test_df)} candles")
            
            # Training 백테스트
            print(f"\n  Running TRAINING period backtest...")
            train_strategy = ZLMACDIchimokuDayTradingStrategy(
                initial_capital=self.initial_capital,
                symbol=symbol
            )
            train_results = train_strategy.run_backtest(train_df)
            
            # Test 백테스트
            print(f"\n  Running TEST period backtest...")
            test_strategy = ZLMACDIchimokuDayTradingStrategy(
                initial_capital=self.initial_capital,
                symbol=symbol
            )
            test_results = test_strategy.run_backtest(test_df)
            
            # 결과 저장
            window_results = {
                'window': period['name'],
                'train_start': period['train_start'],
                'train_end': period['train_end'],
                'test_start': period['test_start'],
                'test_end': period['test_end'],
                'training_return': train_results['total_return'],
                'test_return': test_results['total_return'],
                'test_sharpe': test_results['sharpe_ratio'],
                'test_max_dd': test_results['max_drawdown'],
                'test_trades': test_results['total_trades'],
                'test_win_rate': test_results['win_rate'],
                'test_avg_duration': test_results['avg_trade_duration'],
                'test_daily_trades': test_results['daily_avg_trades'],
                'efficiency_ratio': test_results['total_return'] / train_results['total_return'] if train_results['total_return'] > 0 else 0,
                'overfitting_score': abs(train_results['total_return'] - test_results['total_return'])
            }
            
            results.append(window_results)
            
            print(f"\n  {'='*50}")
            print(f"  TRAINING Results:")
            print(f"    Return: {train_results['total_return']:.2f}%")
            print(f"    Sharpe: {train_results['sharpe_ratio']:.2f}")
            print(f"    Max DD: {train_results['max_drawdown']:.1f}%")
            print(f"    Trades: {train_results['total_trades']}")
            print(f"    Daily Avg: {train_results['daily_avg_trades']:.1f}")
            print(f"\n  TEST Results:")
            print(f"    Return: {test_results['total_return']:.2f}%")
            print(f"    Sharpe: {test_results['sharpe_ratio']:.2f}")
            print(f"    Max DD: {test_results['max_drawdown']:.1f}%")
            print(f"    Trades: {test_results['total_trades']}")
            print(f"    Daily Avg: {test_results['daily_avg_trades']:.1f}")
            print(f"    Avg Duration: {test_results['avg_trade_duration']:.1f} min")
            print(f"  {'='*50}")
        
        # 전체 결과 요약
        self.print_summary(results)
        
        # 결과 저장
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        result_file = os.path.join(
            self.results_cache_dir,
            f'daytrading_wf_results_{timestamp}.json'
        )
        
        with open(result_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n✅ Results saved to: {result_file}")
        
        return results
    
    def print_summary(self, results: List[Dict]):
        """결과 요약 출력"""
        if not results:
            return
        
        print(f"\n{'='*80}")
        print(f"WALK-FORWARD ANALYSIS SUMMARY - Day Trading")
        print(f"{'='*80}")
        
        # 통계 계산
        test_returns = [r['test_return'] for r in results]
        avg_test_return = sum(test_returns) / len(test_returns)
        positive_tests = sum(1 for r in test_returns if r > 0)
        
        test_sharpes = [r['test_sharpe'] for r in results]
        avg_sharpe = sum(test_sharpes) / len(test_sharpes)
        
        test_dds = [r['test_max_dd'] for r in results]
        avg_dd = sum(test_dds) / len(test_dds)
        
        avg_daily_trades = sum(r['test_daily_trades'] for r in results) / len(results)
        avg_duration = sum(r['test_avg_duration'] for r in results) / len(results)
        
        print(f"\n📊 Performance Metrics:")
        print(f"  • Average Test Return: {avg_test_return:.2f}%")
        print(f"  • Positive Test Periods: {positive_tests}/{len(results)} ({positive_tests/len(results)*100:.1f}%)")
        print(f"  • Average Sharpe Ratio: {avg_sharpe:.2f}")
        print(f"  • Average Max Drawdown: {avg_dd:.1f}%")
        print(f"  • Average Daily Trades: {avg_daily_trades:.1f}")
        print(f"  • Average Trade Duration: {avg_duration:.1f} minutes")
        
        # 상세 테이블
        print(f"\n📋 Detailed Results:")
        print(f"{'Window':<8} {'Train Return':<12} {'Test Return':<12} {'Test Sharpe':<12} {'Test DD':<10} {'Daily Trades':<12}")
        print(f"{'-'*70}")
        
        for r in results:
            print(f"{r['window']:<8} {r['training_return']:>11.1f}% {r['test_return']:>11.1f}% "
                  f"{r['test_sharpe']:>11.2f} {r['test_max_dd']:>9.1f}% {r['test_daily_trades']:>11.1f}")


def main():
    """메인 실행 함수"""
    print("\n" + "="*80)
    print("ZL MACD + Ichimoku Day Trading Strategy - Backtest Analysis")
    print("="*80)
    
    # Walk-Forward 분석 실행
    wf_analyzer = ZLMACDIchimokuDayTradingWalkForward(initial_capital=10000)
    results = wf_analyzer.run_walk_forward_analysis(symbol='BTC/USDT')
    
    print("\n✅ Day Trading backtest analysis complete!")


if __name__ == "__main__":
    main()