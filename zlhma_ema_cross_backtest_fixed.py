"""
ZLHMA 50-200 EMA Golden/Death Cross Strategy - 실제 데이터 백테스팅
원본 전략 로직 그대로 적용 (가중치 시스템, Kelly Criterion, 8배 레버리지)
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

# 프로젝트 루트 디렉토리를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backtest_modules'))

try:
    from backtest_modules.fixed.data_fetcher_fixed import DataFetcherFixed
    print("✓ DataFetcherFixed import successful")
except ImportError as e:
    print(f"❌ Import error: {e}")
    raise

# 폰트 설정
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False


class ZLHMAEMACrossStrategy:
    """ZLHMA 50-200 EMA Cross Strategy - 원본 로직"""
    
    def __init__(self, initial_capital: float = 10000, timeframe: str = '4h', symbol: str = 'BTC/USDT'):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position = None
        self.trades = []
        self.equity_curve = []
        self.last_trade_result = None
        self.consecutive_losses = 0
        self.recent_trades = []  # Kelly 계산용
        
        # 거래 비용
        self.symbol = symbol
        self.slippage = 0.001  # 슬리피지 0.1%
        self.commission = 0.0006  # 수수료 0.06%
        
        # ZLHMA 파라미터
        self.zlhma_period = 14  # ZLHMA 기간
        
        # EMA 파라미터
        self.fast_ema_period = 50  # 단기 EMA
        self.slow_ema_period = 200  # 장기 EMA
        
        self.leverage = 8  # 레버리지 8배 (원본 설정)
        self.max_position_loss_pct = 0.08  # 포지션당 최대 손실 8%
        
        # ATR 계산
        self.atr_period = 14
        self.current_atr = None
        
        # ADX 필터 파라미터
        self.adx_period = 14
        self.adx_threshold = 25  # BTC 기본값
        
        # 리스크 관리
        self.daily_loss_limit = 0.03  # 일일 최대 손실 3%
        self.initial_stop_loss = 0.02  # 초기 손절 2%
        
        print(f"✅ ZLHMA 50-200 EMA Cross Strategy initialized:")
        print(f"  • Symbol: {symbol}")
        print(f"  • Timeframe: {timeframe}")
        print(f"  • Leverage: {self.leverage}x (원본 설정)")
        print(f"  • Position Sizing: Kelly Criterion (5-20%)")
        print(f"  • Entry: 가중치 시스템 (최소 2.5 필요)")
        print(f"  • ADX Filter: > {self.adx_threshold}")
    
    def calculate_wma(self, values: pd.Series, period: int) -> pd.Series:
        """Weighted Moving Average 계산"""
        weights = np.arange(1, period + 1)
        wma = values.rolling(period).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
        return wma
    
    def calculate_hma(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Hull Moving Average 계산"""
        half_length = int(period / 2)
        sqrt_length = int(np.sqrt(period))
        
        wma_half = self.calculate_wma(df['close'], half_length)
        wma_full = self.calculate_wma(df['close'], period)
        raw_hma = 2 * wma_half - wma_full
        hma = self.calculate_wma(raw_hma, sqrt_length)
        
        return hma
    
    def calculate_zlhma(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Zero Lag Hull Moving Average 계산"""
        hma = self.calculate_hma(df, period)
        lag = int((period - 1) / 2)
        zlhma = hma + (hma - hma.shift(lag))
        return zlhma
    
    def calculate_ema(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Exponential Moving Average 계산"""
        return df['close'].ewm(span=period, adjust=False).mean()
    
    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """ATR 계산"""
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift(1))
        low_close = abs(df['low'] - df['close'].shift(1))
        
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()
    
    def calculate_adx(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """ADX 계산"""
        # True Range
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift(1))
        low_close = abs(df['low'] - df['close'].shift(1))
        df['tr'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        # Directional Movement
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
        
        # ADX
        dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus)
        df['adx'] = dx.rolling(period).mean()
        
        return df
    
    def check_entry_conditions(self, df: pd.DataFrame, index: int, position_type: str) -> dict:
        """진입 조건 확인 - 가중치 시스템"""
        result = {
            'can_enter': False,
            'signals': [],
            'strength': 0
        }
        
        if index < self.slow_ema_period:
            return result
        
        current_price = df['close'].iloc[index]
        zlhma = df['zlhma'].iloc[index]
        zlhma_prev = df['zlhma'].iloc[index-1]
        zlhma_prev2 = df['zlhma'].iloc[index-2]
        
        fast_ema = df['ema_50'].iloc[index]
        slow_ema = df['ema_200'].iloc[index]
        fast_ema_prev = df['ema_50'].iloc[index-1]
        slow_ema_prev = df['ema_200'].iloc[index-1]
        
        adx = df['adx'].iloc[index]
        
        # ADX 필터 체크
        if adx < self.adx_threshold:
            return result
        
        if position_type == 'LONG':
            # 1. EMA 골든크로스 (가중치 2)
            if fast_ema > slow_ema and fast_ema_prev <= slow_ema_prev:
                result['signals'].append('EMA_GOLDEN_CROSS')
                result['strength'] += 2
            
            # 2. ZLHMA 상승 모멘텀 (가중치 1)
            if zlhma > zlhma_prev and zlhma_prev > zlhma_prev2:
                result['signals'].append('ZLHMA_UPWARD_MOMENTUM')
                result['strength'] += 1
            
            # 3. 가격이 ZLHMA 위 (가중치 0.5)
            if current_price > zlhma:
                result['signals'].append('PRICE_ABOVE_ZLHMA')
                result['strength'] += 0.5
            
            # 4. 가격이 두 EMA 위 (가중치 0.5)
            if current_price > fast_ema and current_price > slow_ema:
                result['signals'].append('PRICE_ABOVE_EMAS')
                result['strength'] += 0.5
        
        else:  # SHORT
            # 1. EMA 데드크로스 (가중치 2)
            if fast_ema < slow_ema and fast_ema_prev >= slow_ema_prev:
                result['signals'].append('EMA_DEATH_CROSS')
                result['strength'] += 2
            
            # 2. ZLHMA 하락 모멘텀 (가중치 1)
            if zlhma < zlhma_prev and zlhma_prev < zlhma_prev2:
                result['signals'].append('ZLHMA_DOWNWARD_MOMENTUM')
                result['strength'] += 1
            
            # 3. 가격이 ZLHMA 아래 (가중치 0.5)
            if current_price < zlhma:
                result['signals'].append('PRICE_BELOW_ZLHMA')
                result['strength'] += 0.5
            
            # 4. 가격이 두 EMA 아래 (가중치 0.5)
            if current_price < fast_ema and current_price < slow_ema:
                result['signals'].append('PRICE_BELOW_EMAS')
                result['strength'] += 0.5
        
        # 최소 2.5 이상의 신호 강도 필요
        result['can_enter'] = result['strength'] >= 2.5
        
        return result
    
    def calculate_kelly_position_size(self) -> float:
        """Kelly Criterion을 사용한 포지션 사이즈 계산"""
        # 최소 20개 거래 필요
        if len(self.recent_trades) < 20:
            return 0.10  # 기본값 10%
        
        # 승률과 평균 손익 계산
        wins = [t for t in self.recent_trades if t['pnl'] > 0]
        losses = [t for t in self.recent_trades if t['pnl'] <= 0]
        
        if len(wins) == 0 or len(losses) == 0:
            return 0.10
        
        win_rate = len(wins) / len(self.recent_trades)
        avg_win = np.mean([t['pnl'] / t['position_value'] for t in wins])
        avg_loss = abs(np.mean([t['pnl'] / t['position_value'] for t in losses]))
        
        # Kelly 계산
        p = win_rate
        q = 1 - p
        b = avg_win / avg_loss if avg_loss > 0 else 0
        
        kelly_pct = (p * b - q) / b if b > 0 else 0
        
        # Half Kelly (더 보수적)
        half_kelly = kelly_pct / 2
        
        # 5% ~ 20% 제한
        return max(0.05, min(0.20, half_kelly))
    
    def calculate_position_size_with_consecutive_loss_adjustment(self, kelly_fraction: float) -> float:
        """연속 손실에 따른 포지션 크기 조정"""
        base_position_size = self.capital * kelly_fraction
        
        # 연속 손실에 따른 축소
        if self.consecutive_losses >= 7:
            adjustment_factor = 0.30  # 30%로 축소
        elif self.consecutive_losses >= 5:
            adjustment_factor = 0.50  # 50%로 축소
        elif self.consecutive_losses >= 3:
            adjustment_factor = 0.70  # 70%로 축소
        else:
            adjustment_factor = 1.0
        
        return base_position_size * adjustment_factor
    
    def execute_trade(self, signal: str, price: float, timestamp):
        """거래 실행"""
        kelly_fraction = self.calculate_kelly_position_size()
        position_size = self.calculate_position_size_with_consecutive_loss_adjustment(kelly_fraction)
        
        # 레버리지 적용
        actual_position_size = position_size * self.leverage
        shares = actual_position_size / price
        
        # 수수료
        commission_cost = position_size * self.commission
        
        # ATR 기반 손절
        stop_loss_distance = min(self.initial_stop_loss, 1.5 * self.current_atr / price)
        
        if signal == 'LONG':
            stop_loss = price * (1 - stop_loss_distance)
        else:
            stop_loss = price * (1 + stop_loss_distance)
        
        self.position = {
            'type': signal,
            'entry_price': price,
            'entry_time': timestamp,
            'shares': shares,
            'position_value': position_size,
            'stop_loss': stop_loss,
            'trailing_stop_active': False,
            'highest_price': price if signal == 'LONG' else None,
            'lowest_price': price if signal == 'SHORT' else None
        }
        
        self.capital -= commission_cost
        
        print(f"  📈 {signal} Entry @ ${price:.2f}, Size: {kelly_fraction*100:.1f}% (Adjusted: {position_size/self.capital*100:.1f}%)")
    
    def close_position(self, price: float, timestamp, reason: str):
        """포지션 청산"""
        if not self.position:
            return
        
        position_type = self.position['type']
        entry_price = self.position['entry_price']
        shares = self.position['shares']
        
        # 손익 계산
        if position_type == 'LONG':
            pnl = (price - entry_price) * shares
        else:
            pnl = (entry_price - price) * shares
        
        # 수수료
        commission_cost = abs(shares * price * self.commission)
        pnl -= commission_cost
        
        # 자본 업데이트
        self.capital += pnl
        
        # 거래 기록
        trade = {
            'entry_time': self.position['entry_time'],
            'exit_time': timestamp,
            'type': position_type,
            'entry_price': entry_price,
            'exit_price': price,
            'shares': shares,
            'position_value': self.position['position_value'],
            'pnl': pnl,
            'reason': reason
        }
        
        self.trades.append(trade)
        self.recent_trades.append(trade)
        if len(self.recent_trades) > 50:  # 최근 50개만 유지
            self.recent_trades.pop(0)
        
        # 연속 손실 업데이트
        if pnl > 0:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
        
        self.position = None
        
        print(f"  📉 {position_type} Exit @ ${price:.2f}, PnL: ${pnl:.2f} ({pnl/self.position['position_value']*100:.2f}%), Reason: {reason}")
    
    def check_exit_conditions(self, df: pd.DataFrame, index: int) -> Tuple[bool, str]:
        """청산 조건 확인"""
        if not self.position:
            return False, ""
        
        current_price = df['close'].iloc[index]
        zlhma = df['zlhma'].iloc[index]
        fast_ema = df['ema_50'].iloc[index]
        slow_ema = df['ema_200'].iloc[index]
        
        position_type = self.position['type']
        entry_price = self.position['entry_price']
        
        # 손익 계산
        if position_type == 'LONG':
            pnl_pct = (current_price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - current_price) / entry_price
        
        # 손절
        if current_price <= self.position['stop_loss'] and position_type == 'LONG':
            return True, "Stop Loss"
        elif current_price >= self.position['stop_loss'] and position_type == 'SHORT':
            return True, "Stop Loss"
        
        # 최대 손실
        if pnl_pct <= -self.max_position_loss_pct:
            return True, "Max Loss"
        
        # 트레일링 스톱
        if pnl_pct >= 0.03:  # 3% 수익 시 활성화
            if position_type == 'LONG':
                if self.position['highest_price'] is None or current_price > self.position['highest_price']:
                    self.position['highest_price'] = current_price
                
                trailing_stop = self.position['highest_price'] * 0.90  # 최고점에서 10% 하락
                if current_price <= trailing_stop:
                    return True, "Trailing Stop"
            else:
                if self.position['lowest_price'] is None or current_price < self.position['lowest_price']:
                    self.position['lowest_price'] = current_price
                
                trailing_stop = self.position['lowest_price'] * 1.10  # 최저점에서 10% 상승
                if current_price >= trailing_stop:
                    return True, "Trailing Stop"
        
        # 전략 특정 청산 조건
        if position_type == 'LONG':
            # EMA 데드크로스
            if fast_ema < slow_ema:
                return True, "EMA Death Cross"
            # ZLHMA 아래로 돌파
            elif current_price < zlhma:
                return True, "ZLHMA Break"
            # 50 EMA 아래로 강한 돌파
            elif current_price < fast_ema * 0.98:
                return True, "Fast EMA Break"
        else:  # SHORT
            # EMA 골든크로스
            if fast_ema > slow_ema:
                return True, "EMA Golden Cross"
            # ZLHMA 위로 돌파
            elif current_price > zlhma:
                return True, "ZLHMA Break"
            # 50 EMA 위로 강한 돌파
            elif current_price > fast_ema * 1.02:
                return True, "Fast EMA Break"
        
        return False, ""
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """모든 기술적 지표 계산"""
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
    
    def run_backtest(self, df: pd.DataFrame) -> Dict:
        """백테스트 실행"""
        print("\n📊 Starting ZLHMA EMA Cross Backtest...")
        
        # 지표 계산
        df = self.calculate_indicators(df)
        
        # 백테스트 루프
        for i in range(self.slow_ema_period + 1, len(df)):
            current_time = df.index[i]
            self.current_atr = df['atr'].iloc[i]
            
            # 포지션이 있는 경우 청산 체크
            if self.position:
                should_exit, exit_reason = self.check_exit_conditions(df, i)
                if should_exit:
                    self.close_position(df['close'].iloc[i], current_time, exit_reason)
            
            # 포지션이 없는 경우 진입 체크
            if not self.position:
                # Long 진입 체크
                long_conditions = self.check_entry_conditions(df, i, 'LONG')
                if long_conditions['can_enter']:
                    self.execute_trade('LONG', df['close'].iloc[i], current_time)
                else:
                    # Short 진입 체크
                    short_conditions = self.check_entry_conditions(df, i, 'SHORT')
                    if short_conditions['can_enter']:
                        self.execute_trade('SHORT', df['close'].iloc[i], current_time)
            
            # Equity 기록
            equity = self.capital
            if self.position:
                current_price = df['close'].iloc[i]
                if self.position['type'] == 'LONG':
                    unrealized_pnl = (current_price - self.position['entry_price']) * self.position['shares']
                else:
                    unrealized_pnl = (self.position['entry_price'] - current_price) * self.position['shares']
                equity += unrealized_pnl
            
            self.equity_curve.append({
                'timestamp': current_time,
                'equity': equity
            })
        
        # 마지막 포지션 청산
        if self.position:
            self.close_position(df['close'].iloc[-1], df.index[-1], "End of backtest")
        
        return self.calculate_metrics()
    
    def calculate_metrics(self) -> Dict:
        """성과 메트릭 계산"""
        if not self.trades:
            return {
                'total_return': 0,
                'win_rate': 0,
                'profit_factor': 0,
                'max_drawdown': 0,
                'total_trades': 0,
                'sharpe_ratio': 0
            }
        
        # 총 수익률
        total_return = ((self.capital - self.initial_capital) / self.initial_capital) * 100
        
        # 승률
        winning_trades = [t for t in self.trades if t['pnl'] > 0]
        win_rate = (len(winning_trades) / len(self.trades)) * 100
        
        # Profit Factor
        gross_profit = sum([t['pnl'] for t in self.trades if t['pnl'] > 0])
        gross_loss = abs(sum([t['pnl'] for t in self.trades if t['pnl'] < 0]))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # 최대 낙폭
        equity_df = pd.DataFrame(self.equity_curve)
        equity_df['cummax'] = equity_df['equity'].cummax()
        equity_df['drawdown'] = (equity_df['equity'] - equity_df['cummax']) / equity_df['cummax']
        max_drawdown = equity_df['drawdown'].min() * 100
        
        # Sharpe Ratio (간단한 계산)
        if len(equity_df) > 1:
            returns = equity_df['equity'].pct_change().dropna()
            sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(252 * 6) if returns.std() > 0 else 0
        else:
            sharpe_ratio = 0
        
        return {
            'total_return': total_return,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'max_drawdown': max_drawdown,
            'total_trades': len(self.trades),
            'sharpe_ratio': sharpe_ratio
        }


def main():
    """메인 실행 함수"""
    print("=" * 80)
    print("ZLHMA 50-200 EMA Cross Strategy - Real Data Backtest")
    print("=" * 80)
    
    # 데이터 가져오기
    fetcher = DataFetcherFixed(use_cache=True)
    
    # 기간 설정 (2024년 1월 ~ 2025년 6월)
    start_date = '2024-01-01'
    end_date = '2025-06-30'
    
    print(f"\n📊 Fetching BTC/USDT data from {start_date} to {end_date}...")
    
    try:
        # DataFetcherFixed는 두 개의 값을 반환 (4h, 15m)
        df_4h, _ = fetcher.fetch_data('BTC/USDT', start_date, end_date)
        
        if df_4h is None or len(df_4h) == 0:
            print("❌ Failed to fetch data")
            return
        
        print(f"✅ Fetched {len(df_4h)} candles")
        print(f"  Price range: ${df_4h['close'].min():.0f} - ${df_4h['close'].max():.0f}")
        
        # 전략 실행
        strategy = ZLHMAEMACrossStrategy(initial_capital=10000, timeframe='4h', symbol='BTC/USDT')
        results = strategy.run_backtest(df_4h)
        
        # 결과 출력
        print("\n" + "=" * 50)
        print("BACKTEST RESULTS")
        print("=" * 50)
        print(f"Total Return: {results['total_return']:.2f}%")
        print(f"Win Rate: {results['win_rate']:.1f}%")
        print(f"Profit Factor: {results['profit_factor']:.2f}")
        print(f"Max Drawdown: {results['max_drawdown']:.2f}%")
        print(f"Total Trades: {results['total_trades']}")
        print(f"Sharpe Ratio: {results['sharpe_ratio']:.2f}")
        
        # 결과 저장
        results_file = 'zlhma_ema_cross_real_data_results.json'
        with open(results_file, 'w') as f:
            json.dump({
                'strategy': 'ZLHMA 50-200 EMA Cross',
                'period': f"{start_date} to {end_date}",
                'leverage': strategy.leverage,
                'results': results,
                'trades': len(strategy.trades)
            }, f, indent=2)
        
        print(f"\n✅ Results saved to {results_file}")
        
        # Equity Curve 그래프
        if strategy.equity_curve:
            plt.figure(figsize=(12, 6))
            equity_df = pd.DataFrame(strategy.equity_curve)
            plt.plot(equity_df['timestamp'], equity_df['equity'])
            plt.title('ZLHMA EMA Cross Strategy - Equity Curve')
            plt.xlabel('Date')
            plt.ylabel('Equity ($)')
            plt.grid(True)
            plt.xticks(rotation=45)
            plt.tight_layout()
            
            chart_file = 'zlhma_ema_cross_equity_curve.png'
            plt.savefig(chart_file)
            print(f"📊 Equity curve saved to {chart_file}")
            plt.close()
        
    except Exception as e:
        print(f"❌ Error during backtest: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()