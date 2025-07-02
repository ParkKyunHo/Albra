"""
TFPE (Trend Following Pullback Entry) Donchian Strategy - Standalone Walk-Forward Analysis
단일 파일로 실행 가능한 TFPE 전략 전진분석 백테스팅 (2021 Q1 - 2025 Q2)

외부 의존성 최소화 버전 - pandas, numpy, matplotlib만 필요
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
import os
import time
from typing import Dict, List, Tuple, Optional
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle


class SimpleDataFetcher:
    """간단한 데이터 생성기 - 실제 바이낸스 BTC/USDT 가격을 시뮬레이션"""
    
    def __init__(self):
        # 시뮬레이션을 위한 시드 설정
        np.random.seed(42)
        
    def generate_realistic_btc_data(self, start_date: str, end_date: str, timeframe: str = '4h') -> pd.DataFrame:
        """실제 BTC 가격 패턴을 모방한 시뮬레이션 데이터 생성"""
        print(f"📊 Generating simulated BTC data from {start_date} to {end_date}...")
        
        # 시간 인덱스 생성
        if timeframe == '4h':
            freq = '4H'
        elif timeframe == '1h':
            freq = '1H'
        else:
            freq = '15T'
            
        date_range = pd.date_range(start=start_date, end=end_date, freq=freq)
        
        # 기본 가격 트렌드 생성 (2021-2025 BTC 가격 모방)
        n_periods = len(date_range)
        
        # 주요 가격 포인트 (실제 BTC 역사적 가격 참고)
        # 2021-01: ~30,000
        # 2021-04: ~60,000
        # 2021-11: ~69,000 (ATH)
        # 2022-06: ~20,000
        # 2022-11: ~16,000
        # 2023-03: ~25,000
        # 2023-11: ~38,000
        # 2024-03: ~70,000 (New ATH)
        # 2024-12: ~95,000
        # 2025-06: ~80,000
        
        # 시간에 따른 기본 가격 곡선
        t = np.linspace(0, 1, n_periods)
        
        # 다중 사인파를 이용한 복잡한 가격 움직임
        base_price = (
            30000 +  # 시작 가격
            40000 * np.sin(2 * np.pi * t) +  # 주요 사이클
            20000 * np.sin(4 * np.pi * t) +  # 중간 사이클
            10000 * np.sin(8 * np.pi * t) +  # 단기 사이클
            15000 * t  # 전체적인 상승 트렌드
        )
        
        # 변동성 추가
        volatility = 0.02  # 2% 기본 변동성
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
            intrabar_volatility = abs(np.random.normal(0, 0.005))
            high = open_price * (1 + intrabar_volatility + abs(returns[i]))
            low = open_price * (1 - intrabar_volatility)
            close = prices[i]
            
            # 볼륨 생성 (가격 변동성에 비례)
            base_volume = 1000000
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
        
        print(f"✅ Generated {len(df)} candles")
        print(f"  Price range: ${df['close'].min():.0f} - ${df['close'].max():.0f}")
        
        return df
    
    def fetch_data(self, symbol: str = 'BTC/USDT', start_date: str = None, end_date: str = None):
        """DataFetcherFixed와 호환되는 인터페이스"""
        # 4시간봉 데이터 생성
        df_4h = self.generate_realistic_btc_data(start_date, end_date, '4h')
        
        # 15분봉 데이터는 4시간봉을 기반으로 생성 (선택사항)
        # 여기서는 간단히 4시간봉 데이터만 반환
        df_15m = None
        
        return df_4h, df_15m


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
        
        # TFPE 전략 파라미터
        self.position_size = 24  # 계좌의 24%
        self.signal_threshold = 2  # 백테스트를 위해 더 완화
        
        # Donchian Channel 파라미터
        self.dc_period = 20  # Donchian 기간
        
        # RSI 파라미터
        self.rsi_period = 14
        self.rsi_pullback_long = 40
        self.rsi_pullback_short = 60
        
        # 손절/익절
        self.stop_loss_pct = 0.03  # 3% 손절
        self.take_profit_pct = 0.10  # 10% 익절
        
    def calculate_donchian_channel(self, df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        """Donchian Channel 계산"""
        df = df.copy()
        
        # Donchian Channel 계산
        df['dc_upper'] = df['high'].rolling(period).max()
        df['dc_lower'] = df['low'].rolling(period).min()
        df['dc_middle'] = (df['dc_upper'] + df['dc_lower']) / 2
        
        # NaN 처리
        df['dc_upper'] = df['dc_upper'].ffill().bfill()
        df['dc_lower'] = df['dc_lower'].ffill().bfill()
        df['dc_middle'] = df['dc_middle'].ffill().bfill()
        
        # 가격 위치 (0~1)
        dc_range = df['dc_upper'] - df['dc_lower']
        df['price_position'] = np.where(
            dc_range > 0,
            (df['close'] - df['dc_lower']) / dc_range,
            0.5
        )
        
        return df
    
    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """RSI 계산"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi.fillna(50)
    
    def calculate_adx(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """ADX (Average Directional Index) 계산"""
        high = df['high']
        low = df['low']
        close = df['close']
        
        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        # Directional Movement
        up = high - high.shift(1)
        down = low.shift(1) - low
        
        plus_dm = np.where((up > down) & (up > 0), up, 0)
        minus_dm = np.where((down > up) & (down > 0), down, 0)
        
        # Smoothed DI
        plus_di = 100 * pd.Series(plus_dm).rolling(window=period).mean() / atr
        minus_di = 100 * pd.Series(minus_dm).rolling(window=period).mean() / atr
        
        # ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()
        
        return adx.fillna(20)
    
    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """ATR (Average True Range) 계산"""
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        return tr.rolling(window=period).mean().fillna(tr.mean())
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """필요한 지표 계산"""
        df = df.copy()
        
        # Donchian Channel
        df = self.calculate_donchian_channel(df, self.dc_period)
        
        # RSI
        df['rsi'] = self.calculate_rsi(df['close'], self.rsi_period)
        
        # EMA
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
        
        # 시장 편향
        df['market_bias'] = np.where(df['close'] > df['ema_200'], 1, -1)
        
        # ADX 계산 (추세 강도)
        df['adx'] = self.calculate_adx(df)
        
        # ATR 계산 (변동성)
        df['atr'] = self.calculate_atr(df)
        
        # 볼륨 이동평균
        df['volume_ma'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']
        
        # NaN 처리
        df = df.ffill().bfill()
        
        return df
    
    def check_entry_conditions(self, df: pd.DataFrame, i: int) -> Tuple[bool, str, int]:
        """TFPE 전략: Trend Following with Pullback Entry (완화된 버전)
        
        진입 로직:
        1. 추세 확인 (ADX > 20으로 완화)
        2. Donchian 채널 방향 확인
        3. 풀백 타이밍 포착 (RSI)
        """
        if i < self.dc_period + 1:
            return False, None, 0
        
        current = df.iloc[i]
        prev = df.iloc[i-1]
        
        # 디버깅용 로그 (첫 몇 개만)
        if i < self.dc_period + 5:
            print(f"  Bar {i}: ADX={current['adx']:.1f}, RSI={current['rsi']:.1f}, "
                  f"Price Position={current['price_position']:.2f}, "
                  f"Close={current['close']:.0f}, DC_Mid={current['dc_middle']:.0f}")
        
        # 추세 강도 확인 - ADX 기준 완화 (25 -> 20)
        if current['adx'] < 20:
            return False, None, 0
        
        # Long 진입 조건 (조건 완화)
        # 1. 상승 추세: 가격이 Donchian 중간선 위
        # 2. 풀백 확인: RSI가 과매도 구간 근처 (35-55로 확대)
        # 3. 가격 위치 조건 완화 (0.7 -> 0.6)
        if (current['close'] > current['dc_middle'] and
            current['rsi'] > 35 and current['rsi'] < 55 and
            current['price_position'] > 0.6):
            return True, 'long', 1
        
        # Short 진입 조건 (조건 완화)
        # 1. 하락 추세: 가격이 Donchian 중간선 아래
        # 2. 풀백 확인: RSI가 과매수 구간 근처 (45-65로 확대)
        # 3. 가격 위치 조건 완화 (0.3 -> 0.4)
        if (current['close'] < current['dc_middle'] and
            current['rsi'] > 45 and current['rsi'] < 65 and
            current['price_position'] < 0.4):
            return True, 'short', 1
        
        # 대안: 돌파 진입 (ADX 조건 완화 40 -> 30)
        if current['adx'] > 30:
            # 상승 돌파 (조건 완화: 정확한 돌파 -> 근처)
            if current['close'] > current['dc_upper'] * 0.98:
                return True, 'long', 2
            # 하락 돌파 (조건 완화: 정확한 돌파 -> 근처)
            elif current['close'] < current['dc_lower'] * 1.02:
                return True, 'short', 2
        
        # 추가: 단순 Donchian 돌파 (ADX 무시)
        # 매우 강한 돌파 시에만
        if current['close'] > current['dc_upper'] * 1.01 and prev['close'] < current['dc_upper']:
            return True, 'long', 3
        elif current['close'] < current['dc_lower'] * 0.99 and prev['close'] > current['dc_lower']:
            return True, 'short', 3
        
        return False, None, 0
    
    def execute_trade(self, df: pd.DataFrame, i: int, signal: str, signal_strength: int):
        """거래 실행"""
        current = df.iloc[i]
        price = current['close']
        timestamp = df.index[i]
        
        # 포지션 크기 계산
        position_size_pct = self.position_size / 100
        position_value = self.capital * position_size_pct
        
        # 거래 비용 적용
        effective_price = price * (1 + self.slippage) if signal == 'long' else price * (1 - self.slippage)
        commission_cost = position_value * self.commission
        
        # 손절/익절 설정
        if signal == 'long':
            stop_loss = price * (1 - self.stop_loss_pct)
            take_profit = price * (1 + self.take_profit_pct)
        else:
            stop_loss = price * (1 + self.stop_loss_pct)
            take_profit = price * (1 - self.take_profit_pct)
        
        self.position = {
            'type': signal,
            'entry_price': effective_price,
            'entry_time': timestamp,
            'size': position_value / effective_price,
            'value': position_value,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'commission_paid': commission_cost,
            'signal_strength': signal_strength
        }
        
        self.capital -= commission_cost
    
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
        
        # 자본 업데이트
        self.capital += pnl
        
        # 거래 기록
        trade = {
            'entry_time': self.position['entry_time'],
            'exit_time': df.index[i],
            'type': self.position['type'],
            'entry_price': self.position['entry_price'],
            'exit_price': effective_exit_price,
            'size': self.position['size'],
            'pnl': pnl,
            'pnl_pct': pnl / self.position['value'],
            'reason': reason,
            'commission': self.position['commission_paid'] + exit_commission,
            'signal_strength': self.position['signal_strength']
        }
        
        self.trades.append(trade)
        self.position = None
        
        # 연속 손실 추적
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
    
    def check_exit_conditions(self, df: pd.DataFrame, i: int) -> Tuple[bool, str]:
        """청산 조건 체크"""
        if not self.position:
            return False, ""
        
        current = df.iloc[i]
        
        # 손절/익절 체크
        if self.position['type'] == 'long':
            if current['close'] <= self.position['stop_loss']:
                return True, "Stop Loss"
            elif current['close'] >= self.position['take_profit']:
                return True, "Take Profit"
        else:
            if current['close'] >= self.position['stop_loss']:
                return True, "Stop Loss"
            elif current['close'] <= self.position['take_profit']:
                return True, "Take Profit"
        
        return False, ""
    
    def run_backtest(self, df: pd.DataFrame) -> Dict:
        """백테스트 실행"""
        # 지표 계산
        df = self.calculate_indicators(df)
        
        # 백테스트 실행
        for i in range(len(df)):
            # 자산 기록
            if self.position:
                if self.position['type'] == 'long':
                    position_value = self.position['size'] * df.iloc[i]['close']
                else:
                    position_value = self.position['value'] * 2 - self.position['size'] * df.iloc[i]['close']
            else:
                position_value = 0
            
            self.equity_curve.append({
                'timestamp': df.index[i],
                'equity': self.capital + position_value
            })
            
            # 포지션이 있는 경우
            if self.position:
                # 청산 체크
                should_exit, exit_reason = self.check_exit_conditions(df, i)
                if should_exit:
                    self.close_position(df, i, exit_reason)
            
            # 포지션이 없는 경우
            else:
                # 진입 체크
                should_enter, direction, signal_strength = self.check_entry_conditions(df, i)
                if should_enter:
                    self.execute_trade(df, i, direction, signal_strength)
        
        # 마지막 포지션 청산
        if self.position:
            self.close_position(df, len(df) - 1, "End of backtest")
        
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
                'total_trades': 0,
                'avg_win': 0,
                'avg_loss': 0
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
    """Walk-Forward Analysis for TFPE Strategy"""
    
    def __init__(self, strategy_class, symbol: str = 'BTC/USDT', timeframe: str = '4h'):
        self.strategy_class = strategy_class
        self.symbol = symbol
        self.timeframe = timeframe
        
        # 분석 기간 설정
        self.start_date = '2021-01-01'
        self.end_date = '2025-06-30'
        
        # Walk-Forward 윈도우 설정
        self.optimization_window = 180  # 6개월 최적화 기간
        self.test_window = 90  # 3개월 테스트 기간
        self.step_size = 90  # 3개월씩 이동
    
    def run(self):
        """Walk-Forward Analysis 실행"""
        print(f"\n{'='*80}")
        print(f"TFPE STRATEGY - STANDALONE WALK-FORWARD ANALYSIS")
        print(f"Symbol: {self.symbol}")
        print(f"Period: {self.start_date} to {self.end_date}")
        print(f"{'='*80}")
        
        # 데이터 가져오기
        fetcher = SimpleDataFetcher()
        df, _ = fetcher.fetch_data(self.symbol, self.start_date, self.end_date)
        
        # Walk-Forward 윈도우 실행
        results = []
        periods = []
        
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
            period_df = df[(df.index >= period_start) & (df.index <= period_end)].copy()
            
            if len(period_df) < 50:
                print(f"  ⚠️ Insufficient data for {period_name}")
                continue
            
            # 전략 실행
            strategy = self.strategy_class()
            metrics = strategy.run_backtest(period_df)
            
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
        total_trades = sum([r['total_trades'] for r in results])
        
        print(f"Average Quarterly Return: {avg_return:.2f}%")
        print(f"Average Win Rate: {avg_win_rate:.1f}%")
        print(f"Average Max Drawdown: {avg_drawdown:.2f}%")
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
        trades = [r['total_trades'] for r in results]
        
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
        
        # 4. 거래 횟수
        ax4.bar(periods, trades, color='purple', alpha=0.7)
        ax4.set_title('Number of Trades by Quarter')
        ax4.set_xlabel('Period')
        ax4.set_ylabel('Number of Trades')
        ax4.tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        plt.savefig('tfpe_walk_forward_results_standalone.png', dpi=300, bbox_inches='tight')
        print(f"\n📊 Results saved to: tfpe_walk_forward_results_standalone.png")
        plt.show()


if __name__ == "__main__":
    # Walk-Forward Analysis 실행
    wfa = WalkForwardAnalysis(TFPEDonchianStrategy)
    wfa.run()