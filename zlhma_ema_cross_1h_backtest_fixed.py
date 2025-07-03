"""
ZLHMA 50-200 EMA Golden/Death Cross Strategy - 1H Backtest (Fixed)
ZLHMA(Zero Lag Hull Moving Average) 50-200 EMA 크로스 전략 백테스팅 - 수정 버전
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
import ccxt

# 스크립트 디렉토리 확인
if __file__:
    script_dir = os.path.dirname(os.path.abspath(__file__))
else:
    script_dir = os.getcwd()

# 폰트 설정
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False


class SimpleDataFetcher1H:
    """간단한 1시간봉 데이터 수집 클래스"""
    
    def __init__(self):
        self.exchange = ccxt.binance()
    
    def fetch_1h_data(self, symbol: str = 'BTC/USDT', start_date: str = None, end_date: str = None):
        """1시간봉 데이터 가져오기"""
        try:
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            
            print(f"📊 Fetching 1H data from {start_date} to {end_date}...")
            
            all_data = []
            since = int(start_dt.timestamp() * 1000)
            end_timestamp = int(end_dt.timestamp() * 1000)
            
            while since < end_timestamp:
                try:
                    ohlcv = self.exchange.fetch_ohlcv(
                        symbol.replace('/', ''), 
                        timeframe='1h', 
                        since=since, 
                        limit=1000
                    )
                    
                    if not ohlcv:
                        break
                    
                    all_data.extend(ohlcv)
                    since = ohlcv[-1][0] + 1
                    
                    print(f"  Fetched {len(ohlcv)} candles, total: {len(all_data)}")
                    time.sleep(0.1)  # Rate limiting
                    
                except Exception as e:
                    print(f"❌ Error fetching data: {e}")
                    time.sleep(1)
                    continue
            
            # DataFrame 생성
            df = pd.DataFrame(all_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            # 날짜 범위로 필터링
            df = df[(df.index >= start_dt) & (df.index <= end_dt)]
            
            # 중복 제거 및 정렬
            df = df[~df.index.duplicated(keep='first')]
            df.sort_index(inplace=True)
            
            print(f"✅ Fetched {len(df)} 1H candles")
            print(f"  Date range: {df.index[0]} to {df.index[-1]}")
            print(f"  Price range: ${df['close'].min():.0f} - ${df['close'].max():.0f}")
            
            return df
            
        except Exception as e:
            print(f"❌ Critical error: {e}")
            import traceback
            traceback.print_exc()
            return None


class ZLHMAEMACrossStrategy:
    """ZLHMA 50-200 EMA Cross Strategy - Fixed Version"""
    
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
        self.ema_fast = 50  # 단기 EMA
        self.ema_slow = 200  # 장기 EMA
        
        # 켈리 기준 파라미터
        self.kelly_min = 0.05  # 최소 포지션 크기 5%
        self.kelly_max = 0.2   # 최대 포지션 크기 20%
        self.kelly_window = 30  # 켈리 계산용 거래 기록 수
        
        # ADX 필터 (심볼별로 다르게 설정)
        if 'BTC' in symbol:
            self.adx_threshold = 25  # BTC는 높은 임계값
        elif 'ETH' in symbol:
            self.adx_threshold = 20  # ETH는 중간 임계값
        else:
            self.adx_threshold = 15  # 기타 알트코인은 낮은 임계값
        
        # 부분 청산 비율
        self.partial_exits = [
            (0.05, 0.25),   # 5% 수익에서 25% 청산
            (0.10, 0.35),   # 10% 수익에서 추가 35% 청산 (누적 60%)
            (0.15, 0.40),   # 15% 수익에서 나머지 40% 청산 (총 100%)
        ]
        
        # 피라미딩 진입 레벨
        self.pyramiding_levels = [0.03, 0.06, 0.09]  # 3%, 6%, 9% 수익에서 추가 진입
        
        # 레버리지 설정
        self.leverage = 8  # 8배 레버리지
        
        # 가중치 시스템 파라미터
        self.weight_thresholds = {
            'strong': 4.0,   # 강한 신호 (진입 허용)
            'medium': 2.5,   # 중간 신호 (홀드)
            'weak': 1.0      # 약한 신호 (관망)
        }
    
    def calculate_zlhma(self, close_prices: pd.Series) -> pd.Series:
        """Zero Lag Hull Moving Average 계산"""
        period = self.zlhma_period
        
        # Hull Moving Average 계산
        wma_half = close_prices.rolling(window=period//2).mean()
        wma_full = close_prices.rolling(window=period).mean()
        
        # Weighted Moving Average of the difference
        diff = 2 * wma_half - wma_full
        
        # Square root period WMA
        sqrt_period = int(np.sqrt(period))
        hma = diff.rolling(window=sqrt_period).mean()
        
        # Zero Lag 적용 (추가 보정)
        lag = (period - 1) // 2
        zlhma = hma + (hma - hma.shift(lag))
        
        return zlhma
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """지표 계산"""
        df = df.copy()
        
        # ZLHMA 계산
        df['zlhma'] = self.calculate_zlhma(df['close'])
        
        # EMA 계산
        df['ema_fast'] = df['close'].ewm(span=self.ema_fast, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=self.ema_slow, adjust=False).mean()
        
        # EMA 크로스 신호
        df['ema_cross_up'] = (df['ema_fast'] > df['ema_slow']) & (df['ema_fast'].shift(1) <= df['ema_slow'].shift(1))
        df['ema_cross_down'] = (df['ema_fast'] < df['ema_slow']) & (df['ema_fast'].shift(1) >= df['ema_slow'].shift(1))
        
        # ADX 계산
        high = df['high']
        low = df['low']
        close = df['close']
        
        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=14).mean()
        
        # Directional Movement
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low
        
        pos_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0), index=df.index)
        neg_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0), index=df.index)
        
        pos_di = 100 * pos_dm.rolling(window=14).mean() / atr
        neg_di = 100 * neg_dm.rolling(window=14).mean() / atr
        
        dx = 100 * abs(pos_di - neg_di) / (pos_di + neg_di)
        df['adx'] = dx.rolling(window=14).mean()
        
        # ATR (포지션 사이징용)
        df['atr'] = atr
        df['atr_pct'] = (atr / close) * 100
        
        # ZLHMA 기울기 (모멘텀)
        df['zlhma_slope'] = df['zlhma'].diff() / df['zlhma'].shift(1) * 100
        
        # 가격 위치 (ZLHMA 대비)
        df['price_position_zlhma'] = (df['close'] - df['zlhma']) / df['zlhma'] * 100
        
        # RSI 계산
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        
        rs = avg_gain / avg_loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 볼륨 분석
        df['volume_ma'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']
        
        # NaN 처리
        df = df.fillna(0)
        
        return df
    
    def calculate_kelly_position_size(self) -> float:
        """켈리 기준에 따른 포지션 크기 계산"""
        if len(self.recent_trades) < 10:  # 최소 거래 수
            return self.kelly_min
        
        # 최근 거래에서 승률과 손익비 계산
        recent = self.recent_trades[-self.kelly_window:]
        wins = [t for t in recent if t['pnl'] > 0]
        losses = [t for t in recent if t['pnl'] < 0]
        
        if not wins or not losses:
            return self.kelly_min
        
        win_rate = len(wins) / len(recent)
        avg_win = np.mean([t['pnl_pct'] for t in wins])
        avg_loss = abs(np.mean([t['pnl_pct'] for t in losses]))
        
        # 켈리 공식: f = (p * b - q) / b
        # p: 승률, q: 패율, b: 손익비
        b = avg_win / avg_loss if avg_loss > 0 else 1
        p = win_rate
        q = 1 - p
        
        kelly = (p * b - q) / b if b > 0 else 0
        
        # 안전 마진 적용 (켈리의 25%)
        kelly *= 0.25
        
        # 범위 제한
        return max(self.kelly_min, min(kelly, self.kelly_max))
    
    def calculate_signal_weight(self, row: pd.Series, df: pd.DataFrame, idx: int) -> float:
        """신호 가중치 계산"""
        weight = 0
        
        # 1. EMA 크로스 (기본 가중치)
        if row['ema_cross_up']:
            weight += 2.0
        elif row['ema_cross_down']:
            weight -= 2.0
        
        # 2. ADX 필터 (추세 강도)
        if row['adx'] > self.adx_threshold:
            weight *= 1.5  # 강한 추세에서 가중치 증가
        elif row['adx'] < self.adx_threshold * 0.7:
            weight *= 0.5  # 약한 추세에서 가중치 감소
        
        # 3. ZLHMA 모멘텀
        if abs(row['zlhma_slope']) > 0.5:  # 강한 모멘텀
            if row['zlhma_slope'] > 0 and weight > 0:
                weight += 1.0
            elif row['zlhma_slope'] < 0 and weight < 0:
                weight -= 1.0
        
        # 4. RSI 필터
        if weight > 0 and row['rsi'] > 70:  # 과매수 구간에서 매수 신호 약화
            weight *= 0.7
        elif weight < 0 and row['rsi'] < 30:  # 과매도 구간에서 매도 신호 약화
            weight *= 0.7
        
        # 5. 볼륨 확인
        if row['volume_ratio'] > 1.5:  # 거래량 증가
            weight *= 1.2
        elif row['volume_ratio'] < 0.5:  # 거래량 감소
            weight *= 0.8
        
        # 6. 가격 위치 (ZLHMA 대비)
        if weight > 0 and row['price_position_zlhma'] > 2:  # 과도하게 위
            weight *= 0.8
        elif weight < 0 and row['price_position_zlhma'] < -2:  # 과도하게 아래
            weight *= 0.8
        
        return weight
    
    def should_add_pyramiding(self, current_price: float) -> bool:
        """피라미딩 추가 여부 판단"""
        if not self.position or len(self.pyramiding_positions) >= self.max_pyramiding_levels:
            return False
        
        # 현재 수익률 계산
        pnl_pct = (current_price - self.position['entry_price']) / self.position['entry_price']
        if self.position['side'] == 'SHORT':
            pnl_pct = -pnl_pct
        
        # 다음 피라미딩 레벨 확인
        next_level_idx = len(self.pyramiding_positions)
        if next_level_idx < len(self.pyramiding_levels):
            required_pnl = self.pyramiding_levels[next_level_idx]
            return pnl_pct >= required_pnl
        
        return False
    
    def calculate_partial_exit_size(self, current_price: float) -> float:
        """부분 청산 크기 계산"""
        if not self.position:
            return 0
        
        # 현재 수익률 계산
        pnl_pct = (current_price - self.position['entry_price']) / self.position['entry_price']
        if self.position['side'] == 'SHORT':
            pnl_pct = -pnl_pct
        
        # 부분 청산 확인
        total_exit_ratio = 0
        for exit_level, exit_ratio in self.partial_exits:
            if pnl_pct >= exit_level and self.accumulated_reduction < sum([r for _, r in self.partial_exits[:self.partial_exits.index((exit_level, exit_ratio))+1]]):
                total_exit_ratio = exit_ratio
                break
        
        if total_exit_ratio > 0:
            # 이미 청산된 비율 제외
            return total_exit_ratio
        
        return 0
    
    def execute_trade(self, row: pd.Series, signal: str, position_size: float = None):
        """거래 실행 - 개선된 버전"""
        if signal == 'BUY':
            # 매수 실행
            if position_size is None:
                position_size = self.calculate_kelly_position_size()
            
            # 포지션 증거금 계산 (전체 자본의 일부만 사용)
            margin_used = self.capital * position_size
            
            # 거래 비용 계산
            entry_price = row['close'] * (1 + self.slippage)
            
            # 실제 포지션 크기 (레버리지 적용)
            position_value = margin_used * self.leverage
            contracts = position_value / entry_price
            
            # 수수료 차감
            commission = position_value * self.commission
            self.capital -= commission
            
            if self.position is None:
                # 신규 포지션
                self.position = {
                    'side': 'LONG',
                    'entry_price': entry_price,
                    'contracts': contracts,
                    'entry_time': row.name,
                    'margin_used': margin_used,
                    'position_value': position_value,
                    'stop_loss': entry_price * (1 - self.initial_stop_loss),
                    'max_contracts': contracts
                }
                self.original_position_value = position_value
                self.highest_price = entry_price
                self.accumulated_reduction = 0
            else:
                # 피라미딩
                self.pyramiding_positions.append({
                    'entry_price': entry_price,
                    'contracts': contracts,
                    'entry_time': row.name,
                    'margin_used': margin_used
                })
                # 평균 진입가 재계산
                total_value = self.position['position_value'] + position_value
                total_contracts = self.position['contracts'] + contracts
                self.position['entry_price'] = total_value / total_contracts
                self.position['contracts'] = total_contracts
                self.position['position_value'] = total_value
                self.position['margin_used'] += margin_used
                self.position['max_contracts'] = max(self.position['max_contracts'], total_contracts)
            
        elif signal == 'SELL':
            # 매도 실행
            if position_size is None:
                position_size = self.calculate_kelly_position_size()
            
            # 포지션 증거금 계산
            margin_used = self.capital * position_size
            
            # 거래 비용 계산
            entry_price = row['close'] * (1 - self.slippage)
            
            # 실제 포지션 크기 (레버리지 적용)
            position_value = margin_used * self.leverage
            contracts = position_value / entry_price
            
            # 수수료 차감
            commission = position_value * self.commission
            self.capital -= commission
            
            if self.position is None:
                # 신규 포지션
                self.position = {
                    'side': 'SHORT',
                    'entry_price': entry_price,
                    'contracts': contracts,
                    'entry_time': row.name,
                    'margin_used': margin_used,
                    'position_value': position_value,
                    'stop_loss': entry_price * (1 + self.initial_stop_loss),
                    'max_contracts': contracts
                }
                self.original_position_value = position_value
                self.lowest_price = entry_price
                self.accumulated_reduction = 0
            else:
                # 피라미딩
                self.pyramiding_positions.append({
                    'entry_price': entry_price,
                    'contracts': contracts,
                    'entry_time': row.name,
                    'margin_used': margin_used
                })
                # 평균 진입가 재계산
                total_value = self.position['position_value'] + position_value
                total_contracts = self.position['contracts'] + contracts
                self.position['entry_price'] = total_value / total_contracts
                self.position['contracts'] = total_contracts
                self.position['position_value'] = total_value
                self.position['margin_used'] += margin_used
                self.position['max_contracts'] = max(self.position['max_contracts'], total_contracts)
    
    def close_position(self, row: pd.Series, reason: str = 'Signal', partial_ratio: float = 1.0):
        """포지션 청산 - 개선된 버전"""
        if not self.position:
            return
        
        exit_price = row['close']
        
        # 슬리피지 적용
        if self.position['side'] == 'LONG':
            exit_price *= (1 - self.slippage)
        else:
            exit_price *= (1 + self.slippage)
        
        # 청산할 계약 수 계산
        contracts_to_close = self.position['contracts'] * partial_ratio
        
        # PnL 계산 (레버리지 적용된 손익)
        if self.position['side'] == 'LONG':
            price_change = (exit_price - self.position['entry_price']) / self.position['entry_price']
        else:
            price_change = (self.position['entry_price'] - exit_price) / self.position['entry_price']
        
        # 실제 손익 계산 (사용한 증거금 대비)
        margin_used_for_close = self.position['margin_used'] * partial_ratio
        pnl = margin_used_for_close * price_change * self.leverage
        
        # 수수료 계산
        exit_value = exit_price * contracts_to_close
        commission = exit_value * self.commission
        pnl -= commission
        
        # 자본 업데이트 (증거금 반환 + 손익)
        self.capital += margin_used_for_close + pnl
        
        # 거래 기록
        trade_record = {
            'entry_time': self.position['entry_time'],
            'exit_time': row.name,
            'side': self.position['side'],
            'entry_price': self.position['entry_price'],
            'exit_price': exit_price,
            'contracts': contracts_to_close,
            'pnl': pnl,
            'pnl_pct': pnl / margin_used_for_close,
            'reason': reason,
            'capital_after': self.capital
        }
        
        self.trades.append(trade_record)
        self.recent_trades.append(trade_record)
        
        # 최근 거래 기록 제한
        if len(self.recent_trades) > self.kelly_window * 2:
            self.recent_trades = self.recent_trades[-self.kelly_window:]
        
        # 부분 청산인 경우
        if partial_ratio < 1.0:
            self.position['contracts'] -= contracts_to_close
            self.position['margin_used'] -= margin_used_for_close
            self.position['position_value'] *= (1 - partial_ratio)
            self.accumulated_reduction += partial_ratio
            
            # 스톱로스 조정 (수익 보호)
            if self.position['side'] == 'LONG' and exit_price > self.position['entry_price']:
                self.position['stop_loss'] = max(self.position['stop_loss'], self.position['entry_price'] * 1.005)  # 손익분기점 + 0.5%
            elif self.position['side'] == 'SHORT' and exit_price < self.position['entry_price']:
                self.position['stop_loss'] = min(self.position['stop_loss'], self.position['entry_price'] * 0.995)  # 손익분기점 - 0.5%
        else:
            # 전체 청산
            self.position = None
            self.pyramiding_positions = []
            self.trailing_stop_active = False
            self.trailing_stop_price = None
            self.highest_price = None
            self.lowest_price = None
            self.accumulated_reduction = 0
        
        # 일일 손실 업데이트
        if row.name.date() != self.last_trade_date:
            self.daily_loss = 0
            self.last_trade_date = row.name.date()
        
        if pnl < 0:
            self.daily_loss += abs(pnl / self.capital)
            
            # 일일 손실 한도 초과 시 거래 중단
            if self.daily_loss > self.daily_loss_limit:
                self.trading_suspended_until = row.name + timedelta(hours=24)
                print(f"⚠️ Daily loss limit exceeded. Trading suspended until {self.trading_suspended_until}")
    
    def update_trailing_stop(self, row: pd.Series):
        """트레일링 스톱 업데이트"""
        if not self.position:
            return
        
        current_price = row['close']
        
        if self.position['side'] == 'LONG':
            # 최고가 업데이트
            if self.highest_price is None or current_price > self.highest_price:
                self.highest_price = current_price
            
            # 수익이 5% 이상이면 트레일링 스톱 활성화
            pnl_pct = (current_price - self.position['entry_price']) / self.position['entry_price']
            if pnl_pct > 0.05 and not self.trailing_stop_active:
                self.trailing_stop_active = True
                self.trailing_stop_price = self.highest_price * 0.98  # 최고가 대비 2% 아래
            
            # 트레일링 스톱 업데이트
            if self.trailing_stop_active:
                new_stop = self.highest_price * 0.98
                if self.trailing_stop_price is None or new_stop > self.trailing_stop_price:
                    self.trailing_stop_price = new_stop
                    self.position['stop_loss'] = max(self.position['stop_loss'], self.trailing_stop_price)
        
        elif self.position['side'] == 'SHORT':
            # 최저가 업데이트
            if self.lowest_price is None or current_price < self.lowest_price:
                self.lowest_price = current_price
            
            # 수익이 5% 이상이면 트레일링 스톱 활성화
            pnl_pct = (self.position['entry_price'] - current_price) / self.position['entry_price']
            if pnl_pct > 0.05 and not self.trailing_stop_active:
                self.trailing_stop_active = True
                self.trailing_stop_price = self.lowest_price * 1.02  # 최저가 대비 2% 위
            
            # 트레일링 스톱 업데이트
            if self.trailing_stop_active:
                new_stop = self.lowest_price * 1.02
                if self.trailing_stop_price is None or new_stop < self.trailing_stop_price:
                    self.trailing_stop_price = new_stop
                    self.position['stop_loss'] = min(self.position['stop_loss'], self.trailing_stop_price)
    
    def check_stop_loss(self, row: pd.Series) -> bool:
        """스톱로스 체크"""
        if not self.position:
            return False
        
        current_price = row['close']
        
        if self.position['side'] == 'LONG':
            return current_price <= self.position['stop_loss']
        else:
            return current_price >= self.position['stop_loss']
    
    def backtest(self, df: pd.DataFrame, print_trades: bool = True, plot_chart: bool = True) -> Dict:
        """백테스팅 실행"""
        # 지표 계산
        df = self.calculate_indicators(df)
        
        # 백테스팅 루프
        for idx, row in df.iterrows():
            # 거래 중단 확인
            if self.trading_suspended_until and idx < self.trading_suspended_until:
                continue
            
            # 포지션이 있는 경우
            if self.position:
                # 트레일링 스톱 업데이트
                self.update_trailing_stop(row)
                
                # 스톱로스 체크
                if self.check_stop_loss(row):
                    self.close_position(row, reason='StopLoss')
                    continue
                
                # 부분 청산 체크
                exit_ratio = self.calculate_partial_exit_size(row['close'])
                if exit_ratio > 0:
                    self.close_position(row, reason='PartialExit', partial_ratio=exit_ratio)
                    if print_trades and self.trades:
                        trade = self.trades[-1]
                        print(f"✅ Partial Exit: {trade['exit_time'].strftime('%Y-%m-%d')} - "
                              f"Size: {exit_ratio*100:.0f}% @ ${trade['exit_price']:.0f}, "
                              f"PnL: ${trade['pnl']:.2f} ({trade['pnl_pct']*100:.2f}%)")
                
                # 피라미딩 체크
                if self.should_add_pyramiding(row['close']):
                    signal_weight = self.calculate_signal_weight(row, df, idx)
                    if abs(signal_weight) >= self.weight_thresholds['medium']:
                        pyramid_size = self.calculate_kelly_position_size() * 0.5  # 피라미딩은 절반 크기
                        if self.position['side'] == 'LONG':
                            self.execute_trade(row, 'BUY', pyramid_size)
                        else:
                            self.execute_trade(row, 'SELL', pyramid_size)
                        
                        if print_trades:
                            print(f"🔺 Pyramiding: {row.name.strftime('%Y-%m-%d')} - "
                                  f"Added {pyramid_size*100:.1f}% position @ ${row['close']:.0f}")
                
                # 반대 신호 체크
                signal_weight = self.calculate_signal_weight(row, df, idx)
                
                if self.position['side'] == 'LONG' and signal_weight <= -self.weight_thresholds['strong']:
                    self.close_position(row, reason='ReverseSignal')
                    self.execute_trade(row, 'SELL')
                elif self.position['side'] == 'SHORT' and signal_weight >= self.weight_thresholds['strong']:
                    self.close_position(row, reason='ReverseSignal')
                    self.execute_trade(row, 'BUY')
            
            # 포지션이 없는 경우
            else:
                signal_weight = self.calculate_signal_weight(row, df, idx)
                
                if signal_weight >= self.weight_thresholds['strong']:
                    self.execute_trade(row, 'BUY')
                    if print_trades:
                        position_size = self.calculate_kelly_position_size()
                        print(f"🟢 BUY: {row.name.strftime('%Y-%m-%d')} @ ${row['close']:.0f} - "
                              f"Size: {position_size*100:.1f}% (Kelly), Weight: {signal_weight:.1f}")
                
                elif signal_weight <= -self.weight_thresholds['strong']:
                    self.execute_trade(row, 'SELL')
                    if print_trades:
                        position_size = self.calculate_kelly_position_size()
                        print(f"🔴 SELL: {row.name.strftime('%Y-%m-%d')} @ ${row['close']:.0f} - "
                              f"Size: {position_size*100:.1f}% (Kelly), Weight: {signal_weight:.1f}")
            
            # Equity curve 업데이트
            current_equity = self.capital
            if self.position:
                # 미실현 손익 포함
                current_price = row['close']
                if self.position['side'] == 'LONG':
                    unrealized_pnl = (current_price - self.position['entry_price']) / self.position['entry_price'] * self.position['margin_used'] * self.leverage
                else:
                    unrealized_pnl = (self.position['entry_price'] - current_price) / self.position['entry_price'] * self.position['margin_used'] * self.leverage
                current_equity += unrealized_pnl
            
            self.equity_curve.append({
                'timestamp': idx,
                'equity': current_equity,
                'capital': self.capital
            })
        
        # 마지막 포지션 청산
        if self.position:
            self.close_position(df.iloc[-1], reason='EndOfPeriod')
        
        # 성과 지표 계산
        return self.calculate_performance_metrics()
    
    def calculate_performance_metrics(self) -> Dict:
        """성과 지표 계산"""
        if not self.trades:
            return {
                'total_return': 0,
                'win_rate': 0,
                'profit_factor': 0,
                'max_drawdown': 0,
                'sharpe_ratio': 0,
                'total_trades': 0
            }
        
        # 기본 지표
        total_trades = len(self.trades)
        winning_trades = [t for t in self.trades if t['pnl'] > 0]
        losing_trades = [t for t in self.trades if t['pnl'] < 0]
        
        win_rate = len(winning_trades) / total_trades * 100 if total_trades > 0 else 0
        
        # Profit Factor
        gross_profit = sum([t['pnl'] for t in winning_trades]) if winning_trades else 0
        gross_loss = abs(sum([t['pnl'] for t in losing_trades])) if losing_trades else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # 총 수익률
        total_return = ((self.capital - self.initial_capital) / self.initial_capital) * 100
        
        # Maximum Drawdown
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


def create_performance_charts(strategy, start_date: str, end_date: str):
    """성과 차트 생성 - 개선된 버전"""
    print("\n📊 Creating performance charts...")
    
    # Equity curve 데이터 준비
    equity_df = pd.DataFrame(strategy.equity_curve)
    equity_df.set_index('timestamp', inplace=True)
    
    # 수익률 계산
    equity_df['returns'] = equity_df['equity'].pct_change()
    equity_df['cumulative_returns'] = ((equity_df['equity'] / strategy.initial_capital) - 1) * 100
    
    # 드로다운 계산
    equity_df['running_max'] = equity_df['equity'].cummax()
    equity_df['drawdown'] = ((equity_df['equity'] - equity_df['running_max']) / equity_df['running_max']) * 100
    
    # 거래 데이터 준비
    trades_df = pd.DataFrame(strategy.trades)
    if not trades_df.empty:
        trades_df['cumulative_pnl'] = trades_df['pnl'].cumsum()
    
    # 차트 생성
    fig, axes = plt.subplots(4, 1, figsize=(14, 16), sharex=True)
    
    # 1. 누적 수익률 차트
    ax1 = axes[0]
    ax1.plot(equity_df.index, equity_df['cumulative_returns'], 'b-', linewidth=2, label='Cumulative Returns')
    ax1.fill_between(equity_df.index, 0, equity_df['cumulative_returns'], alpha=0.3)
    ax1.set_ylabel('Cumulative Returns (%)', fontsize=12)
    ax1.set_title(f'ZLHMA 50-200 EMA Cross Strategy - 1H Performance ({start_date} to {end_date})', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.legend()
    
    # 2. 자본 추이 차트
    ax2 = axes[1]
    ax2.plot(equity_df.index, equity_df['equity'], 'g-', linewidth=2, label='Portfolio Value')
    ax2.axhline(y=strategy.initial_capital, color='r', linestyle='--', alpha=0.5, label='Initial Capital')
    
    # 거래 포인트 표시
    if not trades_df.empty:
        for _, trade in trades_df.iterrows():
            # 가장 가까운 시간 찾기
            try:
                entry_idx = equity_df.index.get_indexer([trade['entry_time']], method='nearest')[0]
                exit_idx = equity_df.index.get_indexer([trade['exit_time']], method='nearest')[0]
                
                entry_time = equity_df.index[entry_idx]
                exit_time = equity_df.index[exit_idx]
                entry_equity = equity_df.iloc[entry_idx]['equity']
                exit_equity = equity_df.iloc[exit_idx]['equity']
                
                if trade['side'] == 'LONG':
                    ax2.scatter(entry_time, entry_equity, color='green', marker='^', s=100, zorder=5)
                    ax2.scatter(exit_time, exit_equity, color='red', marker='v', s=100, zorder=5)
                else:
                    ax2.scatter(entry_time, entry_equity, color='red', marker='v', s=100, zorder=5)
                    ax2.scatter(exit_time, exit_equity, color='green', marker='^', s=100, zorder=5)
            except Exception as e:
                print(f"Warning: Could not plot trade points: {e}")
                continue
    
    ax2.set_ylabel('Portfolio Value ($)', fontsize=12)
    ax2.set_title('Portfolio Value Over Time', fontsize=12)
    ax2.grid(True, alpha=0.3)
    ax2.legend()
    
    # 3. 드로다운 차트
    ax3 = axes[2]
    ax3.fill_between(equity_df.index, 0, equity_df['drawdown'], color='red', alpha=0.5)
    ax3.plot(equity_df.index, equity_df['drawdown'], 'r-', linewidth=1)
    ax3.set_ylabel('Drawdown (%)', fontsize=12)
    ax3.set_title('Drawdown Analysis', fontsize=12)
    ax3.grid(True, alpha=0.3)
    
    # 4. 월별 수익률 히트맵 준비
    ax4 = axes[3]
    if not equity_df.empty:
        # 월별 수익률 계산
        monthly_returns = equity_df['returns'].resample('M').apply(lambda x: ((1 + x).prod() - 1) * 100)
        
        # 연도와 월 분리
        years = sorted(monthly_returns.index.year.unique())
        months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        # 히트맵 데이터 준비
        heatmap_data = np.zeros((len(years), 12))
        for i, year in enumerate(years):
            for j, month in enumerate(range(1, 13)):
                try:
                    value = monthly_returns[monthly_returns.index.year == year][monthly_returns.index.month == month].values[0]
                    heatmap_data[i, j] = value
                except:
                    heatmap_data[i, j] = np.nan
        
        # 히트맵 그리기
        im = ax4.imshow(heatmap_data, cmap='RdYlGn', aspect='auto', vmin=-10, vmax=10)
        ax4.set_xticks(np.arange(12))
        ax4.set_yticks(np.arange(len(years)))
        ax4.set_xticklabels(months)
        ax4.set_yticklabels(years)
        ax4.set_title('Monthly Returns Heatmap (%)', fontsize=12)
        
        # 값 표시
        for i in range(len(years)):
            for j in range(12):
                if not np.isnan(heatmap_data[i, j]):
                    text = ax4.text(j, i, f'{heatmap_data[i, j]:.1f}', 
                                   ha="center", va="center", color="black", fontsize=8)
        
        # 컬러바 추가
        cbar = plt.colorbar(im, ax=ax4)
        cbar.set_label('Monthly Return (%)', rotation=270, labelpad=20)
    
    plt.tight_layout()
    
    # 차트 저장
    chart_file = f'zlhma_ema_cross_1h_performance_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
    plt.savefig(chart_file, dpi=300, bbox_inches='tight')
    print(f"📊 Performance charts saved to {chart_file}")
    
    # 추가 통계 차트
    fig2, axes2 = plt.subplots(2, 2, figsize=(14, 10))
    
    # 1. 거래별 손익 차트
    ax1 = axes2[0, 0]
    if not trades_df.empty:
        colors = ['green' if pnl > 0 else 'red' for pnl in trades_df['pnl']]
        ax1.bar(range(len(trades_df)), trades_df['pnl'], color=colors, alpha=0.7)
        ax1.axhline(y=0, color='black', linestyle='-', alpha=0.5)
        ax1.set_xlabel('Trade Number')
        ax1.set_ylabel('PnL ($)')
        ax1.set_title('Individual Trade PnL')
        ax1.grid(True, alpha=0.3)
    
    # 2. 누적 손익 차트
    ax2 = axes2[0, 1]
    if not trades_df.empty:
        ax2.plot(trades_df['cumulative_pnl'], 'b-', linewidth=2)
        ax2.fill_between(range(len(trades_df)), 0, trades_df['cumulative_pnl'], alpha=0.3)
        ax2.set_xlabel('Trade Number')
        ax2.set_ylabel('Cumulative PnL ($)')
        ax2.set_title('Cumulative Trade PnL')
        ax2.grid(True, alpha=0.3)
    
    # 3. 승률 분포 파이 차트
    ax3 = axes2[1, 0]
    if not trades_df.empty:
        wins = len(trades_df[trades_df['pnl'] > 0])
        losses = len(trades_df[trades_df['pnl'] <= 0])
        ax3.pie([wins, losses], labels=['Wins', 'Losses'], colors=['green', 'red'], 
                autopct='%1.1f%%', startangle=90)
        ax3.set_title('Win/Loss Distribution')
    
    # 4. 수익률 분포 히스토그램
    ax4 = axes2[1, 1]
    if not trades_df.empty:
        ax4.hist(trades_df['pnl_pct'] * 100, bins=20, color='blue', alpha=0.7, edgecolor='black')
        ax4.axvline(x=0, color='red', linestyle='--', alpha=0.5)
        ax4.set_xlabel('Return (%)')
        ax4.set_ylabel('Frequency')
        ax4.set_title('Trade Return Distribution')
        ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # 통계 차트 저장
    stats_chart_file = f'zlhma_ema_cross_1h_stats_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
    plt.savefig(stats_chart_file, dpi=300, bbox_inches='tight')
    print(f"📊 Statistics charts saved to {stats_chart_file}")
    
    plt.close('all')


def run_1h_backtest(start_date: str = '2021-01-01', end_date: str = '2025-03-31'):
    """1시간봉 백테스트 실행"""
    print("=" * 80)
    print("ZLHMA 50-200 EMA Cross Strategy - 1H Backtest (Fixed)")
    print("=" * 80)
    
    # 데이터 가져오기
    fetcher = SimpleDataFetcher1H()
    df = fetcher.fetch_1h_data('BTC/USDT', start_date, end_date)
    
    if df is None or len(df) == 0:
        print("❌ Failed to fetch 1H data")
        return
    
    # 전략 실행
    strategy = ZLHMAEMACrossStrategy(initial_capital=10000, timeframe='1h', symbol='BTC/USDT')
    report = strategy.backtest(df, print_trades=True, plot_chart=False)
    
    # 결과 출력
    print("\n" + "=" * 50)
    print("BACKTEST RESULTS")
    print("=" * 50)
    print(f"Period: {start_date} to {end_date}")
    print(f"Initial Capital: ${strategy.initial_capital:,.2f}")
    print(f"Final Capital: ${strategy.capital:,.2f}")
    print(f"Total Return: {report['total_return']:.2f}%")
    print(f"Win Rate: {report['win_rate']:.1f}%")
    print(f"Profit Factor: {report['profit_factor']:.2f}")
    print(f"Max Drawdown: {report['max_drawdown']:.2f}%")
    print(f"Sharpe Ratio: {report['sharpe_ratio']:.2f}")
    print(f"Total Trades: {report['total_trades']}")
    if report['total_trades'] > 0:
        print(f"Winning Trades: {report['winning_trades']} ({report['winning_trades']/report['total_trades']*100:.1f}%)")
        print(f"Losing Trades: {report['losing_trades']} ({report['losing_trades']/report['total_trades']*100:.1f}%)")
        print(f"Average Win: {report['avg_win']:.2f}%")
        print(f"Average Loss: {report['avg_loss']:.2f}%")
        print(f"Largest Win: ${report['largest_win']:.2f}")
        print(f"Largest Loss: ${report['largest_loss']:.2f}")
    
    # 결과 저장
    results_file = f'zlhma_ema_cross_1h_results_fixed_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(results_file, 'w') as f:
        json.dump({
            'strategy': 'ZLHMA 50-200 EMA Cross (1H) - Fixed',
            'period': f"{start_date} to {end_date}",
            'timeframe': '1h',
            'leverage': strategy.leverage,
            'initial_capital': strategy.initial_capital,
            'final_capital': strategy.capital,
            'results': report,
            'trades': strategy.trades[-10:] if strategy.trades else []  # 마지막 10개 거래만 저장
        }, f, indent=2, default=str)
    
    print(f"\n✅ Results saved to {results_file}")
    
    # 시각화
    create_performance_charts(strategy, start_date, end_date)


if __name__ == "__main__":
    # 전체 백테스트 실행
    run_1h_backtest()