"""
TFPE (Trend Following Pullback Entry) Donchian Strategy - Simplified Walk-Forward Analysis
단순화된 TFPE 전략 전진분석 백테스팅 (2021 Q1 - 2025 Q2)
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


class SimplifiedTFPEStrategy:
    """단순화된 TFPE Donchian Channel Strategy"""
    
    def __init__(self, initial_capital: float = 10000, timeframe: str = '4h', symbol: str = 'BTC/USDT'):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position = None
        self.trades = []
        self.equity_curve = []
        
        # 거래 비용
        self.symbol = symbol
        self.slippage = 0.001  # 슬리피지 0.1%
        self.commission = 0.0006  # 수수료 0.06%
        
        # TFPE 전략 파라미터 (단순화)
        self.position_size = 24  # 계좌의 24%
        self.leverage = 10  # 레버리지 10배
        
        # Donchian Channel 파라미터
        self.dc_period = 20  # Donchian 기간
        
        # 손절/익절
        self.stop_loss_pct = 0.03  # 3% 손절
        self.take_profit_pct = 0.10  # 10% 익절
        
        print(f"  Simplified TFPE Strategy initialized:")
        print(f"  • Symbol: {symbol}")
        print(f"  • Donchian Period: {self.dc_period}")
        print(f"  • Position Size: {self.position_size}%")
        print(f"  • Leverage: {self.leverage}x")
        print(f"  • Stop Loss: {self.stop_loss_pct*100}%")
        print(f"  • Take Profit: {self.take_profit_pct*100}%")
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """필수 지표만 계산"""
        # Donchian Channel
        df['dc_upper'] = df['high'].rolling(self.dc_period).max()
        df['dc_lower'] = df['low'].rolling(self.dc_period).min()
        df['dc_middle'] = (df['dc_upper'] + df['dc_lower']) / 2
        
        # 가격 위치
        df['price_position'] = np.where(
            df['dc_upper'] - df['dc_lower'] > 0,
            (df['close'] - df['dc_lower']) / (df['dc_upper'] - df['dc_lower']),
            0.5
        )
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # EMA
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        
        # NaN 값 제거
        df = df.ffill().bfill()
        
        return df
    
    def check_entry_conditions(self, df: pd.DataFrame, i: int) -> Tuple[bool, str]:
        """단순화된 진입 조건"""
        if i < self.dc_period + 1:
            return False, None
        
        current = df.iloc[i]
        prev = df.iloc[i-1]
        
        # 전략 1: Donchian 돌파
        if current['close'] > current['dc_upper'] * 0.995 and prev['close'] <= prev['dc_upper']:
            return True, 'long'
        elif current['close'] < current['dc_lower'] * 1.005 and prev['close'] >= prev['dc_lower']:
            return True, 'short'
        
        # 전략 2: 풀백 진입 (트렌드 + RSI)
        if current['close'] > current['ema_50'] and current['rsi'] < 40:
            return True, 'long'
        elif current['close'] < current['ema_50'] and current['rsi'] > 60:
            return True, 'short'
        
        # 전략 3: 중간선 돌파
        if current['close'] > current['dc_middle'] and prev['close'] <= prev['dc_middle'] and current['rsi'] > 50:
            return True, 'long'
        elif current['close'] < current['dc_middle'] and prev['close'] >= prev['dc_middle'] and current['rsi'] < 50:
            return True, 'short'
        
        return False, None
    
    def execute_trade(self, df: pd.DataFrame, i: int, signal: str):
        """거래 실행"""
        current = df.iloc[i]
        price = current['close']
        timestamp = current['timestamp']
        
        # 포지션 크기 계산
        position_size_pct = self.position_size / 100
        position_value = self.capital * position_size_pct * self.leverage
        
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
            'commission_paid': commission_cost
        }
        
        self.capital -= commission_cost
        
        print(f"  💰 포지션 진입: {signal.upper()} @ ${effective_price:.2f}")
    
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
            'exit_time': current['timestamp'],
            'type': self.position['type'],
            'entry_price': self.position['entry_price'],
            'exit_price': effective_exit_price,
            'size': self.position['size'],
            'pnl': pnl,
            'pnl_pct': pnl / self.position['value'],
            'reason': reason,
            'commission': self.position['commission_paid'] + exit_commission
        }
        
        self.trades.append(trade)
        self.position = None
        
        print(f"  💵 포지션 청산: {trade['type'].upper()} @ ${effective_exit_price:.2f}, PnL: ${pnl:.2f} ({trade['pnl_pct']*100:.2f}%)")
    
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
        print(f"\n  📊 백테스트 시작: {self.symbol}")
        
        # 지표 계산
        df = self.calculate_indicators(df)
        
        # 백테스트 실행
        for i in range(len(df)):
            # 자산 기록
            if self.position:
                position_value = self.position['size'] * df.iloc[i]['close']
            else:
                position_value = 0
            
            self.equity_curve.append({
                'timestamp': df.iloc[i]['timestamp'],
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
                should_enter, direction = self.check_entry_conditions(df, i)
                if should_enter:
                    self.execute_trade(df, i, direction)
        
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


class SimpleWalkForwardAnalysis:
    """단순화된 Walk-Forward Analysis"""
    
    def __init__(self, strategy_class, symbol: str = 'BTC/USDT', timeframe: str = '4h'):
        self.strategy_class = strategy_class
        self.symbol = symbol
        self.timeframe = timeframe
        
        # 분석 기간 설정 (2021 Q1 ~ 2025 Q2)
        self.start_date = '2021-01-01'
        self.end_date = '2025-06-30'
        
        # Walk-Forward 윈도우 설정
        self.optimization_window = 180  # 6개월 최적화 기간
        self.test_window = 90  # 3개월 테스트 기간
        self.step_size = 90  # 3개월씩 이동
    
    def fetch_data(self) -> pd.DataFrame:
        """데이터 가져오기"""
        print(f"\n📊 Fetching data for {self.symbol}...")
        
        # 캐시 파일 확인
        cache_file = os.path.join(cache_dir, f"{self.symbol.replace('/', '_')}_{self.timeframe}_{self.start_date}_{self.end_date}_simple.pkl")
        
        if os.path.exists(cache_file):
            print(f"  Loading from cache...")
            with open(cache_file, 'rb') as f:
                return pickle.load(f)
        
        # 데이터 가져오기
        fetcher = DataFetcherFixed()
        df_4h, df_15m = fetcher.fetch_data(self.symbol, self.start_date, self.end_date)
        
        # 4h 데이터 사용
        df = df_4h
        
        if df is None:
            raise ValueError(f"Failed to fetch data for {self.symbol}")
        
        # timestamp 컬럼 추가
        if 'timestamp' not in df.columns:
            df = df.reset_index()
            if 'timestamp' not in df.columns:
                df.rename(columns={'index': 'timestamp'}, inplace=True)
        
        # 캐시 저장
        with open(cache_file, 'wb') as f:
            pickle.dump(df, f)
        
        print(f"  Data loaded: {len(df)} candles")
        return df
    
    def run(self):
        """Walk-Forward Analysis 실행"""
        print(f"\n{'='*80}")
        print(f"SIMPLIFIED TFPE STRATEGY - WALK-FORWARD ANALYSIS")
        print(f"Symbol: {self.symbol}")
        print(f"Period: {self.start_date} to {self.end_date}")
        print(f"{'='*80}")
        
        # 데이터 가져오기
        df = self.fetch_data()
        
        # Walk-Forward 윈도우 실행
        results = []
        start_idx = 0
        
        while start_idx + self.optimization_window + self.test_window <= len(df):
            # 윈도우 설정
            opt_start = start_idx
            opt_end = start_idx + self.optimization_window
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
            
            # 테스트 기간 백테스트
            test_strategy = self.strategy_class(timeframe=self.timeframe, symbol=self.symbol)
            test_df = df.iloc[test_start:test_end].copy()
            test_metrics = test_strategy.run_backtest(test_df)
            
            # 결과 저장
            result = {
                'window': len(results) + 1,
                'test_start': test_start_date,
                'test_end': test_end_date,
                'test_metrics': test_metrics,
                'test_trades': test_strategy.trades
            }
            
            results.append(result)
            
            print(f"    Test Return: {test_metrics['total_return']:.2f}%")
            print(f"    Test Trades: {test_metrics['total_trades']}")
            
            # 다음 윈도우로 이동
            start_idx += self.step_size
        
        # 결과 요약
        self.print_summary(results)
        
        return results
    
    def print_summary(self, results: List[Dict]):
        """결과 요약 출력"""
        print("\n" + "="*80)
        print("📈 WALK-FORWARD ANALYSIS SUMMARY")
        print("="*80)
        
        # 평균 계산
        returns = [r['test_metrics']['total_return'] for r in results]
        trades = [r['test_metrics']['total_trades'] for r in results]
        win_rates = [r['test_metrics']['win_rate'] for r in results]
        
        print(f"\n평균 수익률: {np.mean(returns):.2f}% (±{np.std(returns):.2f}%)")
        print(f"평균 거래 수: {np.mean(trades):.1f}")
        print(f"평균 승률: {np.mean(win_rates):.1f}%")
        print(f"수익 윈도우: {sum(1 for r in returns if r > 0)}/{len(results)} ({sum(1 for r in returns if r > 0)/len(results)*100:.1f}%)")


def main():
    """메인 실행 함수"""
    # Walk-Forward Analysis 실행
    wf = SimpleWalkForwardAnalysis(SimplifiedTFPEStrategy, symbol='BTC/USDT', timeframe='4h')
    results = wf.run()
    
    # 결과 저장
    output_file = 'tfpe_simple_results.json'
    with open(output_file, 'w') as f:
        json_results = []
        for r in results:
            json_results.append({
                'window': r['window'],
                'test_start': r['test_start'].strftime('%Y-%m-%d'),
                'test_end': r['test_end'].strftime('%Y-%m-%d'),
                'test_metrics': r['test_metrics']
            })
        json.dump(json_results, f, indent=2)
    
    print(f"\n📁 Results saved to: {output_file}")


if __name__ == "__main__":
    main()