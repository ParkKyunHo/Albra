"""
Enhanced Walk-Forward Analysis with Donchian Channel Strategy
4-Week Donchian Channel Strategy Backtesting
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
sys.path.append(script_dir)  # 현재 디렉토리도 추가

# 디버깅 정보 추가
print(f"Current directory: {os.getcwd()}")
print(f"Script directory: {script_dir}")
print(f"Python path: {sys.path[:3]}...")  # 처음 3개만 표시

# 캐시 디렉토리 확인
cache_dir = os.path.join(script_dir, 'wf_cache')
print(f"Cache directory exists: {os.path.exists(cache_dir)}")
if not os.path.exists(cache_dir):
    print(f"Creating cache directory: {cache_dir}")
    os.makedirs(cache_dir, exist_ok=True)

try:
    # 필요한 모듈 임포트
    from backtest_modules.fixed.data_fetcher_fixed import DataFetcherFixed
    print("✓ Import successful")
except ImportError as e:
    print(f"❌ Import error: {e}")
    raise

# 한글 폰트 설정
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False


class DonchianChannelStrategy:
    """4-Week Donchian Channel Strategy"""
    
    def __init__(self, initial_capital: float = 10000):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position = None  # 현재 포지션
        self.trades = []  # 거래 기록
        self.equity_curve = []  # 자산 곡선
        
        # 전략 파라미터
        self.channel_period = 28 * 6  # 4주 = 28일 * 6 (4시간봉 하루 6개)
        self.exit_channel_period = 21 * 6  # 3주 = 21일 * 6 (매도 포지션 청산용)
        self.leverage = 1  # 레버리지 (필요시 조정 가능)
        
    def calculate_donchian_channel(self, df: pd.DataFrame, period: int) -> pd.DataFrame:
        """던키안 채널 계산"""
        df[f'dc_upper_{period}'] = df['high'].rolling(period).max()
        df[f'dc_lower_{period}'] = df['low'].rolling(period).min()
        df[f'dc_middle_{period}'] = (df[f'dc_upper_{period}'] + df[f'dc_lower_{period}']) / 2
        return df
    
    def run_backtest(self, df: pd.DataFrame) -> Dict:
        """백테스트 실행"""
        # 던키안 채널 계산
        df = self.calculate_donchian_channel(df, self.channel_period)
        df = self.calculate_donchian_channel(df, self.exit_channel_period)
        
        # 초기화
        self.capital = self.initial_capital
        self.position = None
        self.trades = []
        self.equity_curve = []
        
        # 백테스트 루프
        for i in range(self.channel_period, len(df)):
            current_time = df.index[i]
            current_price = df['close'].iloc[i]
            high = df['high'].iloc[i]
            low = df['low'].iloc[i]
            
            # 4주 채널
            upper_4w = df[f'dc_upper_{self.channel_period}'].iloc[i-1]  # 이전 캔들의 채널값 사용
            lower_4w = df[f'dc_lower_{self.channel_period}'].iloc[i-1]
            
            # 3주 채널 (매도 포지션 청산용)
            upper_3w = df[f'dc_upper_{self.exit_channel_period}'].iloc[i-1]
            
            # 포지션이 없을 때
            if self.position is None:
                # 매수 신호: 4주 고가 채널 상향 돌파
                if high > upper_4w and upper_4w > 0:
                    self.enter_position('LONG', current_price, current_time, i)
                
                # 매도 신호: 4주 저가 채널 하향 돌파
                elif low < lower_4w and lower_4w > 0:
                    self.enter_position('SHORT', current_price, current_time, i)
            
            # 롱 포지션일 때
            elif self.position['type'] == 'LONG':
                # 청산 신호: 4주 저가 채널 하향 돌파
                if low < lower_4w and lower_4w > 0:
                    self.exit_position(current_price, current_time, i, 'STOP_LOSS')
            
            # 숏 포지션일 때
            elif self.position['type'] == 'SHORT':
                # 청산 신호: 3주 고가 채널 상향 돌파
                if high > upper_3w and upper_3w > 0:
                    self.exit_position(current_price, current_time, i, 'STOP_LOSS')
            
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
        else:
            total_return = 0
            win_rate = 0
            avg_win = 0
            avg_loss = 0
        
        return {
            'equity_df': equity_df,
            'trades_df': trades_df,
            'total_return': total_return,
            'win_rate': win_rate,
            'total_trades': len(trades_df),
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'final_capital': self.capital,
            'df': df  # 데이터프레임 반환
        }
    
    def enter_position(self, position_type: str, price: float, time: datetime, index: int):
        """포지션 진입"""
        position_size = self.capital * 0.95  # 자본의 95% 사용
        
        # 레버리지 적용
        actual_position_size = position_size * self.leverage
        shares = actual_position_size / price
        
        self.position = {
            'type': position_type,
            'entry_price': price,
            'entry_time': time,
            'shares': shares,
            'entry_index': index,
            'position_value': position_size,  # 실제 투입 자본
            'leveraged_value': actual_position_size  # 레버리지 적용된 포지션 가치
        }
    
    def exit_position(self, price: float, time: datetime, index: int, exit_reason: str):
        """포지션 청산"""
        if self.position is None:
            return
        
        # 손익 계산 (레버리지 고려)
        if self.position['type'] == 'LONG':
            price_change_pct = (price / self.position['entry_price'] - 1)
            pnl_pct = price_change_pct * 100 * self.leverage  # 레버리지 적용된 수익률
            pnl = self.position['position_value'] * price_change_pct * self.leverage
        else:  # SHORT
            price_change_pct = (self.position['entry_price'] / price - 1)
            pnl_pct = price_change_pct * 100 * self.leverage  # 레버리지 적용된 수익률
            pnl = self.position['position_value'] * price_change_pct * self.leverage
        
        # 자본 업데이트
        self.capital += pnl
        
        # 거래 기록
        self.trades.append({
            'entry_time': self.position['entry_time'],
            'exit_time': time,
            'direction': self.position['type'].lower(),
            'entry_price': self.position['entry_price'],
            'exit_price': price,
            'shares': self.position['shares'],
            'pnl': pnl,
            'net_pnl_pct': pnl_pct,
            'exit_reason': exit_reason,
            'holding_hours': (index - self.position['entry_index']) * 4  # 4시간봉 기준
        })
        
        # 포지션 초기화
        self.position = None
    
    def calculate_equity(self, current_price: float) -> float:
        """현재 자산 계산"""
        if self.position is None:
            return self.capital
        
        # 미실현 손익 포함 (레버리지 고려)
        if self.position['type'] == 'LONG':
            price_change_pct = (current_price / self.position['entry_price'] - 1)
            unrealized_pnl = self.position['position_value'] * price_change_pct * self.leverage
        else:  # SHORT
            price_change_pct = (self.position['entry_price'] / current_price - 1)
            unrealized_pnl = self.position['position_value'] * price_change_pct * self.leverage
        
        return self.capital + unrealized_pnl


class DonchianWalkForward:
    """Donchian Channel Strategy Walk-Forward 분석"""
    
    def __init__(self, initial_capital: float = 10000):
        print("\nInitializing DonchianWalkForward...")
        self.initial_capital = initial_capital
        
        # 디렉토리 설정
        if __file__:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
        else:
            self.base_dir = os.getcwd()
            
        self.cache_dir = os.path.join(self.base_dir, "wf_cache")
        self.results_cache_dir = os.path.join(self.base_dir, "wf_cache_donchian")
        
        # 디렉토리 생성
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.results_cache_dir, exist_ok=True)
        
        print(f"  Base directory: {self.base_dir}")
        print(f"  Cache directory: {self.cache_dir}")
        print(f"  Results cache directory: {self.results_cache_dir}")
        
        # 분석 기간 - 2021년부터 2025년 Q1까지
        self.periods = [
            # 2021년
            {"name": "2021_Q1", "test_start": "2021-01-01", "test_end": "2021-03-31"},
            {"name": "2021_Q2", "test_start": "2021-04-01", "test_end": "2021-06-30"},
            {"name": "2021_Q3", "test_start": "2021-07-01", "test_end": "2021-09-30"},
            {"name": "2021_Q4", "test_start": "2021-10-01", "test_end": "2021-12-31"},
            # 2022년
            {"name": "2022_Q1", "test_start": "2022-01-01", "test_end": "2022-03-31"},
            {"name": "2022_Q2", "test_start": "2022-04-01", "test_end": "2022-06-30"},
            {"name": "2022_Q3", "test_start": "2022-07-01", "test_end": "2022-09-30"},
            {"name": "2022_Q4", "test_start": "2022-10-01", "test_end": "2022-12-31"},
            # 2023년
            {"name": "2023_Q1", "test_start": "2023-01-01", "test_end": "2023-03-31"},
            {"name": "2023_Q2", "test_start": "2023-04-01", "test_end": "2023-06-30"},
            {"name": "2023_Q3", "test_start": "2023-07-01", "test_end": "2023-09-30"},
            {"name": "2023_Q4", "test_start": "2023-10-01", "test_end": "2023-12-31"},
            # 2024년
            {"name": "2024_Q1", "test_start": "2024-01-01", "test_end": "2024-03-31"},
            {"name": "2024_Q2", "test_start": "2024-04-01", "test_end": "2024-06-30"},
            {"name": "2024_Q3", "test_start": "2024-07-01", "test_end": "2024-09-30"},
            {"name": "2024_Q4", "test_start": "2024-10-01", "test_end": "2024-12-31"},
            # 2025년 Q1
            {"name": "2025_Q1", "test_start": "2025-01-01", "test_end": "2025-03-31"},
        ]
        
        self.all_results = []
        
        print("\n✅ Donchian Channel parameters initialized")
        print(f"  • Channel Period: 4 weeks (28 days)")
        print(f"  • Exit Channel Period: 3 weeks (21 days)")
        print(f"  • Timeframe: 4H")
    
    def run_donchian_backtest(self, period: Dict) -> Dict:
        """Donchian Channel 전략으로 백테스트 실행 (4시간봉 사용)"""
        try:
            # 데이터 로드
            print(f"  Loading data for {period['name']}...")
            data_fetcher = DataFetcherFixed()
            
            # ccxt 직접 사용하여 4시간봉 데이터 로드
            print(f"  Fetching 4H data...")
            exchange = data_fetcher.exchange
            
            start_dt = pd.to_datetime(period['test_start'])
            end_dt = pd.to_datetime(period['test_end'])
            
            # 채널 계산을 위해 추가 데이터 필요 (4주 전부터)
            extended_start_dt = start_dt - timedelta(days=35)  # 5주 전부터
            since = int(extended_start_dt.timestamp() * 1000)
            
            all_data = []
            while since < int(end_dt.timestamp() * 1000):
                try:
                    time.sleep(0.5)  # Rate limit
                    ohlcv = exchange.fetch_ohlcv('BTC/USDT', '4h', since=since, limit=1000)
                    if not ohlcv:
                        break
                    all_data.extend(ohlcv)
                    since = ohlcv[-1][0] + 1
                except Exception as e:
                    print(f"  Warning: {e}")
                    break
            
            if not all_data:
                print(f"  Failed to load 4h data for {period['name']}")
                return None
            
            # DataFrame 생성
            df_4h = pd.DataFrame(all_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df_4h['timestamp'] = pd.to_datetime(df_4h['timestamp'], unit='ms')
            df_4h = df_4h.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
            df_4h.set_index('timestamp', inplace=True)
            
            print(f"  Loaded {len(df_4h)} 4H candles")
            
            if df_4h.empty:
                print(f"  No data in specified period")
                return None
            
            # Donchian Channel 전략 초기화
            strategy = DonchianChannelStrategy(self.initial_capital)
            
            # 백테스트 실행
            print(f"  Running Donchian Channel backtest...")
            print(f"  Channel period: {strategy.channel_period} candles (4 weeks)")
            print(f"  Exit channel period: {strategy.exit_channel_period} candles (3 weeks)")
            results = strategy.run_backtest(df_4h)
            
            # 실제 거래 기간의 데이터만 필터링
            df_period = df_4h[(df_4h.index >= start_dt) & (df_4h.index <= end_dt)]
            
            # 성능 지표 계산
            trades_df = results.get('trades_df', pd.DataFrame())
            equity_df = results.get('equity_df', pd.DataFrame())
            
            # 샤프 비율 계산
            if not equity_df.empty:
                returns = equity_df['capital'].pct_change().dropna()
                sharpe_ratio = np.sqrt(365 * 6) * returns.mean() / returns.std() if returns.std() > 0 else 0  # 4시간봉 기준
            else:
                sharpe_ratio = 0
            
            # 최대 손실 계산
            if not equity_df.empty:
                equity_curve = equity_df['capital'].values
                peak = np.maximum.accumulate(equity_curve)
                drawdown = (equity_curve - peak) / peak * 100
                max_drawdown = abs(drawdown.min())
            else:
                max_drawdown = 0
            
            # 결과 포맷팅
            result = {
                'period': period['name'],
                'return': results['total_return'],
                'sharpe': sharpe_ratio,
                'win_rate': results['win_rate'],
                'max_dd': max_drawdown,
                'trades': results['total_trades'],
                'trades_df': trades_df,
                'equity_df': equity_df,
                'df_4h': df_period,  # 거래 기간의 데이터만
                'final_capital': results['final_capital'],
                'avg_win': results['avg_win'],
                'avg_loss': results['avg_loss']
            }
            
            return result
            
        except Exception as e:
            print(f"  ❌ Error in backtest for {period['name']}: {e}")
            print(f"  Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            
            return None
    
    def plot_quarter_with_trades(self, result: Dict, show: bool = True):
        """분기별 차트에 거래 표시"""
        if not result or 'trades_df' not in result:
            return None
            
        period = result['period']
        df_4h = result['df_4h']
        trades_df = result['trades_df']
        
        # 차트 생성
        fig = plt.figure(figsize=(20, 14))
        
        # 1. 가격 차트 + 던키안 채널 + 거래
        ax1 = plt.subplot(4, 1, 1)
        
        # 캔들스틱 차트
        dates = df_4h.index
        prices = df_4h['close']
        
        ax1.plot(dates, prices, 'b-', alpha=0.3, linewidth=1, label='Price')
        
        # 던키안 채널 표시
        channel_period = 28 * 6  # 4주 * 6 (4시간봉 기준)
        exit_channel_period = 21 * 6  # 3주 * 6
        
        if f'dc_upper_{channel_period}' in df_4h.columns:
            ax1.plot(dates, df_4h[f'dc_upper_{channel_period}'], 'r-', 
                    alpha=0.7, label='4W Upper', linewidth=2)
            ax1.plot(dates, df_4h[f'dc_lower_{channel_period}'], 'g-', 
                    alpha=0.7, label='4W Lower', linewidth=2)
            ax1.fill_between(dates, df_4h[f'dc_upper_{channel_period}'], 
                           df_4h[f'dc_lower_{channel_period}'], alpha=0.1)
        
        if f'dc_upper_{exit_channel_period}' in df_4h.columns:
            ax1.plot(dates, df_4h[f'dc_upper_{exit_channel_period}'], 'r--', 
                    alpha=0.5, label='3W Upper (Exit)', linewidth=1)
        
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
        
        ax1.set_title(f'{period} - Donchian Channel Strategy (4H)', fontsize=14)
        ax1.set_ylabel('Price (USDT)')
        ax1.grid(True, alpha=0.3)
        ax1.legend()
        
        # 2. 거래 분포
        ax2 = plt.subplot(4, 1, 2)
        
        # 롱/샷 거래 수
        if len(trades_df) > 0:
            long_trades = len(trades_df[trades_df['direction'] == 'long'])
            short_trades = len(trades_df[trades_df['direction'] == 'short'])
            
            ax2.bar(['Long', 'Short'], [long_trades, short_trades], 
                    color=['green', 'red'], alpha=0.7)
            
            # 승률 표시
            if long_trades > 0:
                long_wr = (trades_df[trades_df['direction'] == 'long']['net_pnl_pct'] > 0).sum() / long_trades * 100
                ax2.text(0, long_trades + 0.5, f'{long_wr:.0f}%', ha='center', va='bottom')
            if short_trades > 0:
                short_wr = (trades_df[trades_df['direction'] == 'short']['net_pnl_pct'] > 0).sum() / short_trades * 100
                ax2.text(1, short_trades + 0.5, f'{short_wr:.0f}%', ha='center', va='bottom')
        
        ax2.set_title('Trade Distribution')
        ax2.set_ylabel('Number of Trades')
        ax2.grid(True, alpha=0.3)
        
        # 3. 거래별 손익
        ax3 = plt.subplot(4, 1, 3)
        
        if 'net_pnl_pct' in trades_df.columns and len(trades_df) > 0:
            bar_colors = ['green' if pnl > 0 else 'red' for pnl in trades_df['net_pnl_pct']]
            bars = ax3.bar(range(len(trades_df)), trades_df['net_pnl_pct'].values, 
                          color=bar_colors, alpha=0.7)
        
        ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax3.set_title('Individual Trade P&L (%)')
        ax3.set_xlabel('Trade Number')
        ax3.set_ylabel('P&L (%)')
        ax3.grid(True, alpha=0.3)
        
        # 4. 누적 수익률
        ax4 = plt.subplot(4, 1, 4)
        
        if 'net_pnl_pct' in trades_df.columns and len(trades_df) > 0:
            # 복리 수익률 계산
            cumulative_return = 1.0
            cumulative_returns = []
            
            for pnl_pct in trades_df['net_pnl_pct'].values:
                cumulative_return *= (1 + pnl_pct / 100)
                cumulative_returns.append((cumulative_return - 1) * 100)
            
            ax4.plot(range(len(cumulative_returns)), cumulative_returns, 'b-', linewidth=3, marker='o')
            
            # 최고/최저 표시
            if len(cumulative_returns) > 0:
                max_idx = np.argmax(cumulative_returns)
                min_idx = np.argmin(cumulative_returns)
                ax4.scatter(max_idx, cumulative_returns[max_idx], color='green', s=100, zorder=5)
                ax4.scatter(min_idx, cumulative_returns[min_idx], color='red', s=100, zorder=5)
        
        ax4.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax4.set_title('Cumulative P&L')
        ax4.set_xlabel('Trade Number')
        ax4.set_ylabel('Cumulative Return (%)')
        ax4.grid(True, alpha=0.3)
        
        # 최종 통계 표시
        final_stats = f'Return: {result["return"]:.2f}% | Win Rate: {result["win_rate"]:.1f}% | Trades: {result["trades"]}'
        ax4.text(0.5, 0.02, final_stats, transform=ax4.transAxes, 
                ha='center', fontsize=10,
                bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.5))
        
        plt.tight_layout()
        
        # 저장
        filename = f'donchian_quarter_{period}_trades.png'
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
        print("Donchian Channel Strategy - Walk-Forward Analysis")
        print("="*80)
        print("\n🎯 STRATEGY PARAMETERS")
        print(f"  • Entry Channel: 4 weeks (28 days)")
        print(f"  • Exit Channel (Short): 3 weeks (21 days)")
        print(f"  • Timeframe: 4H")
        print(f"  • Position Size: 95% of capital")
        print("\n📊 TRADING RULES")
        print("  • LONG: Enter when price breaks above 4-week high")
        print("  • LONG Exit: Exit when price breaks below 4-week low")
        print("  • SHORT: Enter when price breaks below 4-week low")
        print("  • SHORT Exit: Exit when price breaks above 3-week high")
        print("="*80)
        
        results = []
        
        # 각 분기별 백테스트
        successful_periods = 0
        failed_periods = []
        
        for period in self.periods:
            print(f"\nProcessing {period['name']}...")
            result = self.run_donchian_backtest(period)
            
            if result:
                results.append(result)
                self.all_results.append(result)
                successful_periods += 1
                
                # 성과 출력
                print(f"  ✓ Completed: Return={result['return']:.2f}%, " +
                      f"Sharpe={result['sharpe']:.2f}, " +
                      f"Win Rate={result['win_rate']:.1f}%, " +
                      f"Trades={result['trades']}")
                
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
        
        # 2. 각 분기별 차트 표시
        print("\n2. Quarterly Trading Charts")
        for i, result in enumerate(results, 1):
            print(f"\n   [{i}/{len(results)}] {result['period']}")
            try:
                self.plot_quarter_with_trades(result, show=True)
            except Exception as e:
                print(f"   Failed to display chart for {result['period']}: {e}")
        
        print("\n✅ All charts displayed")
    
    def plot_cumulative_performance(self, results: List[Dict], show: bool = True):
        """누적 성과 차트"""
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        
        # 1. 누적 수익률
        quarters = [r['period'] for r in results]
        returns = [r['return'] for r in results]
        
        # 복리 수익률 계산
        cumulative = [0]
        compound_return = 1.0
        for ret in returns:
            compound_return *= (1 + ret / 100)
            cumulative.append((compound_return - 1) * 100)
        
        ax1.plot(range(len(cumulative)), cumulative, 'b-', linewidth=3, marker='o', markersize=8)
        ax1.fill_between(range(len(cumulative)), 0, cumulative, alpha=0.3)
        ax1.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        
        # 각 분기 표시
        for i, (q, r) in enumerate(zip(quarters, returns)):
            color = 'green' if r > 0 else 'red'
            ax1.annotate(f"{r:+.1f}%", 
                        xy=(i+1, cumulative[i+1]),
                        xytext=(0, 10), textcoords='offset points',
                        ha='center', fontsize=8,
                        bbox=dict(boxstyle='round,pad=0.3', 
                                facecolor=color, alpha=0.3))
        
        ax1.set_title('Cumulative Returns - Donchian Channel Strategy', fontsize=14)
        ax1.set_xlabel('Quarter')
        ax1.set_ylabel('Cumulative Return (%)')
        ax1.set_xticks(range(1, len(quarters)+1))
        ax1.set_xticklabels(quarters, rotation=45)
        ax1.grid(True, alpha=0.3)
        
        # 2. 분기별 수익률
        x = np.arange(len(quarters))
        colors = ['green' if r > 0 else 'red' for r in returns]
        
        ax2.bar(x, returns, color=colors, alpha=0.7)
        ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        
        ax2.set_xlabel('Quarter')
        ax2.set_ylabel('Return (%)')
        ax2.set_title('Quarterly Returns')
        ax2.set_xticks(x)
        ax2.set_xticklabels(quarters, rotation=45)
        ax2.grid(True, alpha=0.3)
        
        # 3. 승률 분포
        win_rates = [r['win_rate'] for r in results]
        
        ax3.plot(x, win_rates, 'go-', linewidth=2, markersize=8)
        ax3.axhline(y=50, color='red', linestyle='--', alpha=0.5, label='50% Line')
        ax3.fill_between(x, 50, win_rates, where=np.array(win_rates) > 50, 
                        alpha=0.3, color='green', label='Above 50%')
        ax3.fill_between(x, 50, win_rates, where=np.array(win_rates) <= 50, 
                        alpha=0.3, color='red', label='Below 50%')
        
        ax3.set_xlabel('Quarter')
        ax3.set_ylabel('Win Rate (%)')
        ax3.set_title('Win Rate by Quarter')
        ax3.set_xticks(x)
        ax3.set_xticklabels(quarters, rotation=45)
        ax3.set_ylim(0, 100)
        ax3.grid(True, alpha=0.3)
        ax3.legend()
        
        # 4. 샤프 비율 및 드로우다운
        sharpes = [r['sharpe'] for r in results]
        max_dds = [-r['max_dd'] for r in results]  # 음수로 표시
        
        ax4_twin = ax4.twinx()
        
        line1 = ax4.plot(x, sharpes, 'go-', linewidth=2, markersize=8, label='Sharpe Ratio')
        line2 = ax4_twin.plot(x, max_dds, 'ro-', linewidth=2, markersize=8, label='Max Drawdown')
        
        ax4.set_xlabel('Quarter')
        ax4.set_ylabel('Sharpe Ratio', color='g')
        ax4_twin.set_ylabel('Max Drawdown (%)', color='r')
        ax4.set_title('Risk-Adjusted Performance')
        ax4.set_xticks(x)
        ax4.set_xticklabels(quarters, rotation=45)
        ax4.grid(True, alpha=0.3)
        ax4.axhline(y=0, color='black', linestyle='--', alpha=0.5)
        
        # 범례 통합
        lines = line1 + line2
        labels = [l.get_label() for l in lines]
        ax4.legend(lines, labels, loc='best')
        
        plt.tight_layout()
        
        # 저장
        filename = 'donchian_cumulative_performance.png'
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        print(f"Cumulative performance chart saved as: {filename}")
        
        if show:
            plt.show()
        else:
            plt.close(fig)
    
    def generate_summary_report(self, results: List[Dict]):
        """전체 성과 요약"""
        print("\n" + "="*80)
        print("DONCHIAN CHANNEL STRATEGY - COMPLETE ANALYSIS SUMMARY")
        print("="*80)
        
        # 결과가 없는 경우 처리
        if not results:
            print("\n❌ No results to analyze.")
            return
        
        # 전체 통계
        total_return = sum(r['return'] for r in results)
        avg_return = np.mean([r['return'] for r in results])
        positive_quarters = sum(1 for r in results if r['return'] > 0)
        
        print("\n📊 Overall Performance:")
        print(f"  • Total Return: {total_return:.2f}%")
        print(f"  • Average Quarterly Return: {avg_return:.2f}%")
        print(f"  • Positive Quarters: {positive_quarters}/{len(results)}")
        print(f"  • Quarterly Win Rate: {positive_quarters/len(results)*100:.1f}%")
        
        # 전체 거래 통계
        total_trades = sum(r['trades'] for r in results)
        all_win_rates = [r['win_rate'] for r in results]
        
        print("\n🎯 Trading Statistics:")
        print(f"  • Total Trades: {total_trades}")
        print(f"  • Average Win Rate: {np.mean(all_win_rates):.1f}%")
        print(f"  • Average Trades per Quarter: {total_trades/len(results):.1f}")
        
        # 리스크 지표
        sharpes = [r['sharpe'] for r in results]
        max_dds = [r['max_dd'] for r in results]
        
        print("\n📈 Risk Metrics:")
        print(f"  • Average Sharpe Ratio: {np.mean(sharpes):.2f}")
        print(f"  • Best Sharpe: {max(sharpes):.2f} ({results[sharpes.index(max(sharpes))]['period']})")
        print(f"  • Average Max Drawdown: {np.mean(max_dds):.1f}%")
        print(f"  • Worst Drawdown: {max(max_dds):.1f}% ({results[max_dds.index(max(max_dds))]['period']})")
        
        # 분기별 상세
        print("\n📅 Quarterly Breakdown:")
        print("-"*80)
        print(f"{'Quarter':<10} {'Return':<10} {'Sharpe':<10} {'Win Rate':<10} {'Max DD':<10} {'Trades':<10}")
        print("-"*80)
        
        for r in results:
            print(f"{r['period']:<10} {r['return']:>8.1f}% {r['sharpe']:>9.2f} "
                  f"{r['win_rate']:>9.1f}% {r['max_dd']:>9.1f}% {r['trades']:>9}")
        
        # 최고/최악 분기
        best_quarter = max(results, key=lambda x: x['return'])
        worst_quarter = min(results, key=lambda x: x['return'])
        
        print(f"\n🏆 Best Quarter: {best_quarter['period']} ({best_quarter['return']:.1f}%)")
        print(f"📉 Worst Quarter: {worst_quarter['period']} ({worst_quarter['return']:.1f}%)")
        
        print("\n💡 Key Insights:")
        print("  1. 4-week Donchian Channel breakout strategy")
        print("  2. Long entry on 4-week high breakout, exit on 4-week low breakout")
        print("  3. Short entry on 4-week low breakout, exit on 3-week high breakout")
        print("  4. Asymmetric exit rules for shorts (3-week vs 4-week)")
        print("  5. Pure trend following without additional filters")


def main():
    """메인 실행"""
    try:
        print("\n" + "="*80)
        print("Starting Donchian Channel Strategy Walk-Forward Analysis")
        print("="*80)
        
        analyzer = DonchianWalkForward()
        print("\n✓ Analyzer initialized successfully")
        
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
            'period': r['period'],
            'return': r['return'],
            'sharpe': r['sharpe'],
            'win_rate': r['win_rate'],
            'max_dd': r['max_dd'],
            'trades': r['trades'],
            'final_capital': r.get('final_capital', 0),
            'avg_win': r.get('avg_win', 0),
            'avg_loss': r.get('avg_loss', 0)
        }
        clean_results.append(clean_r)
    
    with open(f'donchian_wf_results_{timestamp}.json', 'w') as f:
        json.dump(clean_results, f, indent=2)
    
    print(f"\n✅ Donchian Channel strategy analysis complete!")
    print(f"Results saved as: donchian_wf_results_{timestamp}.json")


if __name__ == "__main__":
    main()
