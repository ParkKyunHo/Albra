"""
Trend Following HMA Cross Strategy - Standalone Walk-Forward Analysis
추세 추종 HMA 크로스 전략 - 멀티타임프레임, 피라미딩, Half Kelly 자금관리

전략 구조:
- 추세: 4시간봉 200 ZL HMA
- 진입: 15분봉 50/200 ZL HMA 크로스
- 모든 이동평균선은 Zero Lag HMA 사용
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import time
from typing import Dict, List, Tuple, Optional
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from collections import deque


class MultiTimeframeDataFetcher:
    """멀티타임프레임 데이터 생성기"""
    
    def __init__(self):
        np.random.seed(42)
        
    def generate_realistic_btc_data(self, start_date: str, end_date: str, timeframe: str = '4h') -> pd.DataFrame:
        """실제 BTC 가격 패턴을 모방한 시뮬레이션 데이터 생성"""
        print(f"📊 Generating simulated BTC {timeframe} data from {start_date} to {end_date}...")
        
        # 시간 인덱스 생성
        if timeframe == '4h':
            freq = '4H'
        elif timeframe == '15m':
            freq = '15T'
        else:
            freq = '1H'
            
        date_range = pd.date_range(start=start_date, end=end_date, freq=freq)
        
        # 기본 가격 트렌드 생성
        n_periods = len(date_range)
        t = np.linspace(0, 1, n_periods)
        
        # 다중 사인파를 이용한 복잡한 가격 움직임
        base_price = (
            30000 +  # 시작 가격
            40000 * np.sin(2 * np.pi * t) +  # 주요 사이클
            20000 * np.sin(4 * np.pi * t) +  # 중간 사이클
            10000 * np.sin(8 * np.pi * t) +  # 단기 사이클
            15000 * t  # 전체적인 상승 트렌드
        )
        
        # 타임프레임별 변동성 조정
        if timeframe == '15m':
            volatility = 0.003  # 15분봉은 작은 변동성
        else:
            volatility = 0.02   # 4시간봉은 큰 변동성
        
        returns = np.random.normal(0, volatility, n_periods)
        
        # 트렌드와 모멘텀 추가
        trend = np.zeros(n_periods)
        momentum = 0
        for i in range(1, n_periods):
            momentum = 0.7 * momentum + 0.3 * returns[i]
            trend[i] = trend[i-1] + momentum
            
        # 최종 가격 계산
        prices = base_price * (1 + trend)
        
        # OHLCV 데이터 생성
        data = []
        for i in range(n_periods):
            if i == 0:
                open_price = prices[i]
            else:
                open_price = data[i-1]['close']
                
            # 캔들 내 변동성
            intrabar_volatility = abs(np.random.normal(0, volatility/2))
            high = open_price * (1 + intrabar_volatility + abs(returns[i]))
            low = open_price * (1 - intrabar_volatility)
            close = prices[i]
            
            # 볼륨 생성
            base_volume = 1000000 if timeframe == '4h' else 100000
            volume = base_volume * (1 + abs(returns[i]) * 10) * np.random.uniform(0.8, 1.2)
            
            data.append({
                'timestamp': date_range[i],
                'open': open_price,
                'high': max(high, open_price, close),
                'low': min(low, open_price, close),
                'close': close,
                'volume': volume
            })
        
        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)
        
        print(f"✅ Generated {len(df)} {timeframe} candles")
        
        return df
    
    def fetch_multi_timeframe_data(self, symbol: str = 'BTC/USDT', start_date: str = None, end_date: str = None):
        """멀티타임프레임 데이터 생성"""
        # 4시간봉 데이터
        df_4h = self.generate_realistic_btc_data(start_date, end_date, '4h')
        
        # 15분봉 데이터
        df_15m = self.generate_realistic_btc_data(start_date, end_date, '15m')
        
        return df_4h, df_15m


class TrendFollowingHMACrossStrategy:
    """추세 추종 HMA 크로스 전략"""
    
    def __init__(self, initial_capital: float = 10000, symbol: str = 'BTC/USDT'):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position = None
        self.trades = []
        self.equity_curve = []
        
        # 거래 비용
        self.symbol = symbol
        self.slippage = 0.001  # 슬리피지 0.1%
        self.commission = 0.0006  # 수수료 0.06%
        
        # 전략 파라미터
        self.trend_hma_period = 200  # 4시간봉 추세 HMA
        self.fast_hma_period = 50    # 15분봉 빠른 HMA
        self.slow_hma_period = 200   # 15분봉 느린 HMA
        self.atr_period = 14
        
        # 피라미딩 파라미터
        self.pyramid_levels = [0.02, 0.04, 0.06]  # 2%, 4%, 6%에서 추가
        self.pyramid_size = 0.25  # 각 레벨에서 25% 추가
        self.max_pyramid_level = 3
        
        # 리스크 관리
        self.max_risk_per_trade = 0.02  # 거래당 최대 2% 리스크
        self.max_position_size = 0.5  # 계좌의 최대 50%
        self.max_loss_threshold = -0.10  # -10% 최대 손실
        self.trailing_stop_pct = 0.05  # 5% 추적 손절
        
        # Kelly 계산용
        self.recent_trades_window = 20
        self.min_kelly = 0.02
        self.max_kelly = 0.25
        
        # 거래 통계
        self.consecutive_wins = 0
        self.consecutive_losses = 0
        self.peak_equity = initial_capital
        self.current_drawdown = 0
        
        # HMA 크로스 상태 추적
        self.last_cross_signal = None
        self.cross_confirmed_bars = 0
        
    def calculate_wma(self, prices: pd.Series, period: int) -> pd.Series:
        """가중이동평균 (Weighted Moving Average) 계산"""
        weights = np.arange(1, period + 1)
        return prices.rolling(period).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
    
    def calculate_zlhma(self, prices: pd.Series, period: int) -> pd.Series:
        """Zero Lag HMA 계산"""
        # HMA = WMA(2*WMA(n/2) - WMA(n), sqrt(n))
        half_period = int(period / 2)
        sqrt_period = int(np.sqrt(period))
        
        # Step 1: Calculate WMA(n/2) and WMA(n)
        wma_half = self.calculate_wma(prices, half_period)
        wma_full = self.calculate_wma(prices, period)
        
        # Step 2: 2*WMA(n/2) - WMA(n)
        raw_hma = 2 * wma_half - wma_full
        
        # Step 3: WMA(sqrt(n)) of the result
        hma = self.calculate_wma(raw_hma, sqrt_period)
        
        # Zero Lag 보정
        lag = prices - hma
        zlhma = hma + lag * 0.3  # 30% 보정 (EMA보다 약하게)
        
        return zlhma.fillna(prices.mean())
    
    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """ATR 계산"""
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        return tr.rolling(window=period).mean().fillna(tr.mean())
    
    def calculate_indicators_4h(self, df: pd.DataFrame) -> pd.DataFrame:
        """4시간봉 지표 계산 (추세 판단용)"""
        df = df.copy()
        
        # 200 ZL HMA (추세 판단)
        df['zlhma_200'] = self.calculate_zlhma(df['close'], self.trend_hma_period)
        
        # 추세 방향
        df['trend'] = np.where(df['close'] > df['zlhma_200'], 1, -1)
        
        # ATR
        df['atr'] = self.calculate_atr(df, self.atr_period)
        
        return df.ffill().bfill()
    
    def calculate_indicators_15m(self, df: pd.DataFrame) -> pd.DataFrame:
        """15분봉 지표 계산 (진입 신호용)"""
        df = df.copy()
        
        # 50 & 200 ZL HMA
        df['zlhma_50'] = self.calculate_zlhma(df['close'], self.fast_hma_period)
        df['zlhma_200'] = self.calculate_zlhma(df['close'], self.slow_hma_period)
        
        # HMA 크로스 신호
        df['hma_cross'] = 0
        df.loc[df['zlhma_50'] > df['zlhma_200'], 'hma_cross'] = 1   # 골든크로스
        df.loc[df['zlhma_50'] < df['zlhma_200'], 'hma_cross'] = -1  # 데드크로스
        
        # 크로스 발생 감지
        df['cross_signal'] = df['hma_cross'].diff()
        
        # ATR
        df['atr'] = self.calculate_atr(df, self.atr_period)
        
        return df.ffill().bfill()
    
    def get_current_trend(self, df_4h: pd.DataFrame, current_time: pd.Timestamp) -> int:
        """현재 시점의 4시간봉 추세 확인"""
        # 현재 시간 이전의 가장 최근 4시간봉 찾기
        mask = df_4h.index <= current_time
        if not mask.any():
            return 0
        
        latest_4h = df_4h[mask].iloc[-1]
        return latest_4h['trend']
    
    def calculate_half_kelly(self) -> float:
        """Half Kelly 비율 계산"""
        if len(self.trades) < 5:
            return self.min_kelly
        
        recent_trades = self.trades[-self.recent_trades_window:]
        
        winning_trades = [t for t in recent_trades if t['pnl'] > 0]
        losing_trades = [t for t in recent_trades if t['pnl'] < 0]
        
        if not winning_trades or not losing_trades:
            return self.min_kelly
        
        win_rate = len(winning_trades) / len(recent_trades)
        avg_win = np.mean([t['pnl_pct'] for t in winning_trades])
        avg_loss = abs(np.mean([t['pnl_pct'] for t in losing_trades]))
        
        # Kelly 공식
        kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win if avg_win > 0 else 0
        
        # Half Kelly
        half_kelly = kelly / 2
        
        # 제한
        return max(min(half_kelly, self.max_kelly), self.min_kelly)
    
    def calculate_position_size(self) -> float:
        """포지션 크기 계산"""
        half_kelly = self.calculate_half_kelly()
        
        # MDD 조정
        if self.current_drawdown < -0.20:
            half_kelly *= 0.5
        
        # 연속 손실 조정
        if self.consecutive_losses >= 3:
            return 0  # 거래 중단
        elif self.consecutive_losses >= 2:
            half_kelly *= 0.5
        
        # 연속 이익 조정
        if self.consecutive_wins >= 3:
            half_kelly *= 0.5  # 과열 방지
        
        return min(half_kelly, self.max_position_size)
    
    def check_entry_conditions(self, df_15m: pd.DataFrame, i: int, trend: int) -> Tuple[bool, str]:
        """진입 조건 체크 - HMA 크로스"""
        if i < 2:
            return False, None
        
        # 포지션이 있으면 진입 안함
        if self.position is not None:
            return False, None
        
        current = df_15m.iloc[i]
        prev = df_15m.iloc[i-1]
        
        # 추세가 없으면 진입 안함
        if trend == 0:
            return False, None
        
        # 디버깅 로그 (매 100개 봉마다)
        if i % 100 == 0:
            print(f"\n  Debug [{current.name}]:")
            print(f"    4H Trend: {trend}")
            print(f"    15M HMA50: {current['zlhma_50']:.2f}")
            print(f"    15M HMA200: {current['zlhma_200']:.2f}")
            print(f"    HMA Cross: {current['hma_cross']}")
            print(f"    Cross Signal: {current.get('cross_signal', 'N/A')}")
        
        # Long 진입: 상승 추세 + 골든크로스 (단순화된 조건)
        if trend == 1 and current['hma_cross'] == 1 and prev['hma_cross'] == -1:
            print(f"  📈 골든크로스 감지: {current.name}")
            return True, 'long'
        
        # Short 진입: 하락 추세 + 데드크로스 (단순화된 조건)
        if trend == -1 and current['hma_cross'] == -1 and prev['hma_cross'] == 1:
            print(f"  📉 데드크로스 감지: {current.name}")
            return True, 'short'
        
        return False, None
    
    def check_pyramid_conditions(self, df_15m: pd.DataFrame, i: int) -> bool:
        """피라미딩 조건 체크"""
        if not self.position or self.position['pyramid_level'] >= self.max_pyramid_level:
            return False
        
        current = df_15m.iloc[i]
        entry_price = self.position['avg_entry_price']
        current_pnl = (current['close'] - entry_price) / entry_price
        
        if self.position['type'] == 'short':
            current_pnl = -current_pnl
        
        # 다음 피라미딩 레벨 확인
        next_level = self.position['pyramid_level']
        if next_level < len(self.pyramid_levels) and current_pnl >= self.pyramid_levels[next_level]:
            return True
        
        return False
    
    def check_reduce_position(self, df_15m: pd.DataFrame, i: int) -> bool:
        """포지션 축소 조건 체크"""
        if not self.position:
            return False
        
        current = df_15m.iloc[i]
        entry_price = self.position['avg_entry_price']
        current_pnl = (current['close'] - entry_price) / entry_price
        
        if self.position['type'] == 'short':
            current_pnl = -current_pnl
        
        # -2% 손실 시 포지션 50% 축소
        if current_pnl <= -0.02 and not self.position.get('reduced', False):
            return True
        
        return False
    
    def execute_trade(self, df_15m: pd.DataFrame, i: int, signal: str):
        """거래 실행"""
        current = df_15m.iloc[i]
        price = current['close']
        timestamp = df_15m.index[i]
        
        # 포지션 크기 계산
        position_size_pct = self.calculate_position_size()
        if position_size_pct == 0:
            return  # 거래 중단
        
        position_value = self.capital * position_size_pct
        
        # 거래 비용 적용
        effective_price = price * (1 + self.slippage) if signal == 'long' else price * (1 - self.slippage)
        commission_cost = position_value * self.commission
        
        # 손절 설정 (ATR 기반)
        atr_stop = current['atr'] * 3
        if signal == 'long':
            stop_loss = price - atr_stop
        else:
            stop_loss = price + atr_stop
        
        self.position = {
            'type': signal,
            'entry_time': timestamp,
            'avg_entry_price': effective_price,
            'size': position_value / effective_price,
            'total_value': position_value,
            'stop_loss': stop_loss,
            'highest_price': price if signal == 'long' else None,
            'lowest_price': price if signal == 'short' else None,
            'pyramid_level': 0,
            'commission_paid': commission_cost,
            'reduced': False
        }
        
        self.capital -= commission_cost
        
        print(f"  💰 포지션 진입: {signal.upper()} @ ${effective_price:.2f}, Size: {position_size_pct*100:.1f}%")
    
    def add_pyramid_position(self, df_15m: pd.DataFrame, i: int):
        """피라미딩 포지션 추가"""
        if not self.position:
            return
        
        current = df_15m.iloc[i]
        price = current['close']
        
        # 추가 포지션 크기
        add_value = self.position['total_value'] * self.pyramid_size
        
        # 거래 비용
        effective_price = price * (1 + self.slippage) if self.position['type'] == 'long' else price * (1 - self.slippage)
        commission_cost = add_value * self.commission
        
        # 평균 진입가 재계산
        old_value = self.position['total_value']
        new_value = old_value + add_value
        old_avg = self.position['avg_entry_price']
        
        self.position['avg_entry_price'] = (old_value * old_avg + add_value * effective_price) / new_value
        self.position['size'] += add_value / effective_price
        self.position['total_value'] = new_value
        self.position['pyramid_level'] += 1
        self.position['commission_paid'] += commission_cost
        
        self.capital -= commission_cost
        
        print(f"  🔺 피라미딩: Level {self.position['pyramid_level']} @ ${effective_price:.2f}")
    
    def reduce_position(self, df_15m: pd.DataFrame, i: int):
        """포지션 축소"""
        if not self.position:
            return
        
        current = df_15m.iloc[i]
        price = current['close']
        
        # 50% 축소
        reduce_ratio = 0.5
        reduce_size = self.position['size'] * reduce_ratio
        
        # 거래 비용
        effective_price = price * (1 - self.slippage) if self.position['type'] == 'long' else price * (1 + self.slippage)
        commission_cost = reduce_size * effective_price * self.commission
        
        # 부분 실현 손익
        if self.position['type'] == 'long':
            partial_pnl = (effective_price - self.position['avg_entry_price']) * reduce_size
        else:
            partial_pnl = (self.position['avg_entry_price'] - effective_price) * reduce_size
        
        partial_pnl -= commission_cost
        
        # 포지션 업데이트
        self.position['size'] *= (1 - reduce_ratio)
        self.position['total_value'] *= (1 - reduce_ratio)
        self.position['commission_paid'] += commission_cost
        self.position['reduced'] = True
        
        self.capital += partial_pnl
        
        print(f"  📉 포지션 축소: 50% @ ${effective_price:.2f}, PnL: ${partial_pnl:.2f}")
    
    def check_exit_conditions(self, df_15m: pd.DataFrame, i: int, trend: int) -> Tuple[bool, str]:
        """청산 조건 체크"""
        if not self.position:
            return False, ""
        
        current = df_15m.iloc[i]
        
        # 추세 전환
        if self.position['type'] == 'long' and trend == -1:
            return True, "Trend Reversal"
        elif self.position['type'] == 'short' and trend == 1:
            return True, "Trend Reversal"
        
        # 반대 크로스 (추가 안전장치)
        if self.position['type'] == 'long' and current['hma_cross'] == -1:
            return True, "Opposite Cross"
        elif self.position['type'] == 'short' and current['hma_cross'] == 1:
            return True, "Opposite Cross"
        
        # 손절
        if self.position['type'] == 'long':
            if current['close'] <= self.position['stop_loss']:
                return True, "Stop Loss"
        else:
            if current['close'] >= self.position['stop_loss']:
                return True, "Stop Loss"
        
        # 최대 손실
        current_pnl = (current['close'] - self.position['avg_entry_price']) / self.position['avg_entry_price']
        if self.position['type'] == 'short':
            current_pnl = -current_pnl
        
        if current_pnl <= self.max_loss_threshold:
            return True, "Max Loss"
        
        # 추적 손절 (수익 중일 때만)
        if current_pnl > 0:
            if self.position['type'] == 'long':
                if self.position['highest_price'] is None or current['close'] > self.position['highest_price']:
                    self.position['highest_price'] = current['close']
                
                trailing_stop = self.position['highest_price'] * (1 - self.trailing_stop_pct)
                if current['close'] <= trailing_stop:
                    return True, "Trailing Stop"
            else:
                if self.position['lowest_price'] is None or current['close'] < self.position['lowest_price']:
                    self.position['lowest_price'] = current['close']
                
                trailing_stop = self.position['lowest_price'] * (1 + self.trailing_stop_pct)
                if current['close'] >= trailing_stop:
                    return True, "Trailing Stop"
        
        # 시간 손절 (10일 = 960개 15분봉)
        if i - df_15m.index.get_loc(self.position['entry_time']) > 960:
            if current_pnl <= 0:
                return True, "Time Stop"
        
        return False, ""
    
    def close_position(self, df_15m: pd.DataFrame, i: int, reason: str):
        """포지션 청산"""
        if not self.position:
            return
        
        current = df_15m.iloc[i]
        exit_price = current['close']
        
        # 거래 비용
        if self.position['type'] == 'long':
            effective_exit_price = exit_price * (1 - self.slippage)
            pnl = (effective_exit_price - self.position['avg_entry_price']) * self.position['size']
        else:
            effective_exit_price = exit_price * (1 + self.slippage)
            pnl = (self.position['avg_entry_price'] - effective_exit_price) * self.position['size']
        
        # 수수료
        exit_commission = self.position['size'] * effective_exit_price * self.commission
        pnl -= exit_commission
        
        # 자본 업데이트
        self.capital += pnl
        
        # 거래 기록
        trade = {
            'entry_time': self.position['entry_time'],
            'exit_time': df_15m.index[i],
            'type': self.position['type'],
            'entry_price': self.position['avg_entry_price'],
            'exit_price': effective_exit_price,
            'size': self.position['size'],
            'pnl': pnl,
            'pnl_pct': pnl / self.position['total_value'],
            'reason': reason,
            'pyramid_level': self.position['pyramid_level'],
            'commission': self.position['commission_paid'] + exit_commission
        }
        
        self.trades.append(trade)
        
        # 연속 승/패 업데이트
        if pnl > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            self.consecutive_wins = 0
        
        self.position = None
        
        print(f"  💵 포지션 청산: {trade['type'].upper()} @ ${effective_exit_price:.2f}, "
              f"PnL: ${pnl:.2f} ({trade['pnl_pct']*100:.2f}%), Reason: {reason}")
    
    def update_drawdown(self):
        """드로다운 업데이트"""
        current_equity = self.capital
        
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
        
        self.current_drawdown = (current_equity - self.peak_equity) / self.peak_equity
    
    def run_backtest(self, df_4h: pd.DataFrame, df_15m: pd.DataFrame) -> Dict:
        """백테스트 실행"""
        print("📊 Starting backtest...")
        
        # 지표 계산
        df_4h = self.calculate_indicators_4h(df_4h)
        df_15m = self.calculate_indicators_15m(df_15m)
        
        # 디버깅 정보
        print(f"  4H candles: {len(df_4h)}")
        print(f"  15M candles: {len(df_15m)}")
        
        # 백테스트 실행 (15분봉 기준)
        for i in range(200, len(df_15m)):  # 충분한 이동평균 계산 후 시작
            current_time = df_15m.index[i]
            
            # 현재 시점의 4시간봉 추세 확인
            trend = self.get_current_trend(df_4h, current_time)
            
            # 자산 기록
            if self.position:
                if self.position['type'] == 'long':
                    position_value = self.position['size'] * df_15m.iloc[i]['close']
                else:
                    position_value = self.position['total_value'] * 2 - self.position['size'] * df_15m.iloc[i]['close']
            else:
                position_value = 0
            
            self.equity_curve.append({
                'timestamp': current_time,
                'equity': self.capital + position_value
            })
            
            # 드로다운 업데이트
            self.update_drawdown()
            
            # 포지션이 있는 경우
            if self.position:
                # 청산 체크
                should_exit, exit_reason = self.check_exit_conditions(df_15m, i, trend)
                if should_exit:
                    self.close_position(df_15m, i, exit_reason)
                else:
                    # 피라미딩 체크
                    if self.check_pyramid_conditions(df_15m, i):
                        self.add_pyramid_position(df_15m, i)
                    # 포지션 축소 체크
                    elif self.check_reduce_position(df_15m, i):
                        self.reduce_position(df_15m, i)
            
            # 포지션이 없는 경우
            else:
                # 진입 체크
                should_enter, direction = self.check_entry_conditions(df_15m, i, trend)
                if should_enter:
                    self.execute_trade(df_15m, i, direction)
        
        # 마지막 포지션 청산
        if self.position:
            self.close_position(df_15m, len(df_15m) - 1, "End of backtest")
        
        return self.calculate_metrics()
    
    def calculate_metrics(self) -> Dict:
        """성과 지표 계산"""
        if not self.trades:
            return {
                'total_return': 0,
                'sharpe_ratio': 0,
                'calmar_ratio': 0,
                'max_drawdown': 0,
                'win_rate': 0,
                'profit_factor': 0,
                'total_trades': 0,
                'avg_pyramid_level': 0
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
            sharpe_ratio = returns.mean() / returns.std() * np.sqrt(252 * 96) if returns.std() > 0 else 0  # 15분봉 기준
        else:
            sharpe_ratio = 0
        
        # Calmar Ratio
        years = len(equity_df) / (252 * 96)  # 15분봉 기준
        annual_return = total_return / years if years > 0 else 0
        calmar_ratio = annual_return / abs(max_drawdown) if max_drawdown != 0 else 0
        
        # 평균 피라미딩 레벨
        avg_pyramid = np.mean([t['pyramid_level'] for t in self.trades])
        
        return {
            'total_return': total_return,
            'sharpe_ratio': sharpe_ratio,
            'calmar_ratio': calmar_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'total_trades': len(self.trades),
            'avg_pyramid_level': avg_pyramid,
            'final_kelly': self.calculate_half_kelly() * 100
        }


class WalkForwardAnalysis:
    """Walk-Forward Analysis for HMA Cross Strategy"""
    
    def __init__(self, strategy_class, symbol: str = 'BTC/USDT'):
        self.strategy_class = strategy_class
        self.symbol = symbol
        
        # 분석 기간 설정
        self.start_date = '2021-01-01'
        self.end_date = '2025-06-30'
    
    def run(self):
        """Walk-Forward Analysis 실행"""
        print(f"\n{'='*80}")
        print(f"TREND FOLLOWING HMA CROSS STRATEGY - WALK-FORWARD ANALYSIS")
        print(f"Symbol: {self.symbol}")
        print(f"Period: {self.start_date} to {self.end_date}")
        print(f"추세: 4H 200 ZL HMA, 진입: 15M 50/200 ZL HMA Cross")
        print(f"{'='*80}")
        
        # 데이터 가져오기
        fetcher = MultiTimeframeDataFetcher()
        df_4h, df_15m = fetcher.fetch_multi_timeframe_data(self.symbol, self.start_date, self.end_date)
        
        # Walk-Forward 윈도우 실행
        results = []
        
        # 분기별로 실행
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
        
        for period_name, period_start, period_end in quarters:
            print(f"\n📅 Testing Period: {period_name}")
            
            # 해당 기간 데이터 추출
            period_df_4h = df_4h[(df_4h.index >= period_start) & (df_4h.index <= period_end)].copy()
            period_df_15m = df_15m[(df_15m.index >= period_start) & (df_15m.index <= period_end)].copy()
            
            if len(period_df_15m) < 500:  # 최소 데이터 요구사항
                print(f"  ⚠️ Insufficient data for {period_name}")
                continue
            
            # 전략 실행
            strategy = self.strategy_class()
            metrics = strategy.run_backtest(period_df_4h, period_df_15m)
            
            # 결과 저장
            results.append({
                'period': period_name,
                'start': period_start,
                'end': period_end,
                **metrics
            })
            
            # 결과 출력
            print(f"  📊 Results:")
            print(f"    • Total Return: {metrics['total_return']:.2f}%")
            print(f"    • Win Rate: {metrics['win_rate']:.1f}%")
            print(f"    • Max Drawdown: {metrics['max_drawdown']:.2f}%")
            print(f"    • Total Trades: {metrics['total_trades']}")
            print(f"    • Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
            print(f"    • Calmar Ratio: {metrics['calmar_ratio']:.2f}")
            print(f"    • Avg Pyramid Level: {metrics['avg_pyramid_level']:.2f}")
        
        # 전체 결과 요약
        self.print_summary(results)
        
        # 결과 시각화
        self.plot_results(results)
    
    def print_summary(self, results: List[Dict]):
        """결과 요약 출력"""
        print(f"\n{'='*80}")
        print("OVERALL SUMMARY")
        print(f"{'='*80}")
        
        # 평균 계산
        avg_return = np.mean([r['total_return'] for r in results])
        avg_win_rate = np.mean([r['win_rate'] for r in results])
        avg_drawdown = np.mean([r['max_drawdown'] for r in results])
        avg_calmar = np.mean([r['calmar_ratio'] for r in results])
        total_trades = sum([r['total_trades'] for r in results])
        
        print(f"Average Quarterly Return: {avg_return:.2f}%")
        print(f"Average Win Rate: {avg_win_rate:.1f}%")
        print(f"Average Max Drawdown: {avg_drawdown:.2f}%")
        print(f"Average Calmar Ratio: {avg_calmar:.2f}")
        print(f"Total Trades: {total_trades}")
        
        # 최고/최저 성과
        best_period = max(results, key=lambda x: x['total_return'])
        worst_period = min(results, key=lambda x: x['total_return'])
        
        print(f"\nBest Period: {best_period['period']} ({best_period['total_return']:.2f}%)")
        print(f"Worst Period: {worst_period['period']} ({worst_period['total_return']:.2f}%)")
    
    def plot_results(self, results: List[Dict]):
        """결과 시각화"""
        if not results:
            return
        
        # 설정
        plt.style.use('default')
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
        
        periods = [r['period'] for r in results]
        returns = [r['total_return'] for r in results]
        win_rates = [r['win_rate'] for r in results]
        drawdowns = [r['max_drawdown'] for r in results]
        calmar_ratios = [r['calmar_ratio'] for r in results]
        
        # 1. 분기별 수익률
        ax1.bar(periods, returns, color=['green' if r > 0 else 'red' for r in returns])
        ax1.set_title('Quarterly Returns')
        ax1.set_xlabel('Period')
        ax1.set_ylabel('Return (%)')
        ax1.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax1.tick_params(axis='x', rotation=45)
        
        # 2. 승률
        ax2.plot(periods, win_rates, marker='o', color='blue')
        ax2.set_title('Win Rate by Quarter')
        ax2.set_xlabel('Period')
        ax2.set_ylabel('Win Rate (%)')
        ax2.axhline(y=50, color='red', linestyle='--', alpha=0.5)
        ax2.tick_params(axis='x', rotation=45)
        
        # 3. 최대 낙폭
        ax3.bar(periods, drawdowns, color='red', alpha=0.7)
        ax3.set_title('Maximum Drawdown by Quarter')
        ax3.set_xlabel('Period')
        ax3.set_ylabel('Max Drawdown (%)')
        ax3.tick_params(axis='x', rotation=45)
        
        # 4. Calmar Ratio
        ax4.bar(periods, calmar_ratios, color='purple', alpha=0.7)
        ax4.set_title('Calmar Ratio by Quarter')
        ax4.set_xlabel('Period')
        ax4.set_ylabel('Calmar Ratio')
        ax4.axhline(y=1, color='green', linestyle='--', alpha=0.5)
        ax4.tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        plt.savefig('ema_cross_strategy_results.png', dpi=300, bbox_inches='tight')
        print(f"\n📊 Results saved to: ema_cross_strategy_results.png")
        plt.show()


if __name__ == "__main__":
    # Walk-Forward Analysis 실행
    wfa = WalkForwardAnalysis(TrendFollowingEMACrossStrategy)
    wfa.run()