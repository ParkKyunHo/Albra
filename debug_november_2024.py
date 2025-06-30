"""
EMA Strategy Debug - 2024년 11월 1일~15일 분석
"""

import pandas as pd
import numpy as np
from datetime import datetime
import sys
import os
import time
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backtest_modules'))

from backtest_modules.ema_volatility_strategy import EMAVolatilityStrategy
from backtest_modules.fixed.data_fetcher_fixed import DataFetcherFixed

def analyze_november_issue():
    """2024년 11월 1-15일 기간 상세 분석"""
    print("\n=== EMA Strategy Debug: Nov 1-15, 2024 ===")
    print("="*50)
    
    # 1. 데이터 로드
    print("\n1. Loading data...")
    data_fetcher = DataFetcherFixed()
    exchange = data_fetcher.exchange
    
    # 10월 15일부터 11월 30일까지 데이터 로드 (버퍼 포함)
    start_dt = pd.to_datetime('2024-10-15')
    end_dt = pd.to_datetime('2024-11-30')
    since = int(start_dt.timestamp() * 1000)
    
    all_data = []
    while since < int(end_dt.timestamp() * 1000):
        try:
            time.sleep(0.5)
            ohlcv = exchange.fetch_ohlcv('BTC/USDT', '1h', since=since, limit=1000)
            if not ohlcv:
                break
            all_data.extend(ohlcv)
            since = ohlcv[-1][0] + 1
        except Exception as e:
            print(f"  Warning: {e}")
            break
    
    if not all_data:
        print("❌ Failed to load data")
        return
    
    # DataFrame 생성
    df_1h = pd.DataFrame(all_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df_1h['timestamp'] = pd.to_datetime(df_1h['timestamp'], unit='ms')
    df_1h = df_1h.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
    df_1h.set_index('timestamp', inplace=True)
    
    print(f"✓ Loaded {len(df_1h)} candles")
    
    # 2. 전략 실행
    strategy = EMAVolatilityStrategy(initial_capital=10000)
    strategy.df_1h = df_1h
    results = strategy.run_backtest()
    
    # 3. 11월 1-15일 거래만 필터링
    trades_df = results['trades_df']
    if not trades_df.empty:
        nov_start = pd.to_datetime('2024-11-01')
        nov_end = pd.to_datetime('2024-11-15')
        
        nov_trades = trades_df[
            (trades_df['entry_time'] >= nov_start) & 
            (trades_df['entry_time'] <= nov_end)
        ]
        
        print(f"\n2. November 1-15 Analysis:")
        print(f"  Total trades in period: {len(nov_trades)}")
        
        if len(nov_trades) > 0:
            print(f"\n  Trade Details:")
            for idx, trade in nov_trades.iterrows():
                print(f"\n  Trade #{idx+1}:")
                print(f"    Direction: {trade['direction'].upper()}")
                print(f"    Entry: {trade['entry_time'].strftime('%Y-%m-%d %H:%M')} @ ${trade['entry_price']:,.0f}")
                print(f"    Exit: {trade['exit_time'].strftime('%Y-%m-%d %H:%M')} @ ${trade['exit_price']:,.0f}")
                print(f"    P&L: {trade['net_pnl_pct']:.2f}%")
                print(f"    Holding: {trade['holding_hours']:.1f} hours")
                
                # 롱/숏 손익 계산 검증
                if trade['direction'] == 'long':
                    expected_pnl = ((trade['exit_price'] - trade['entry_price']) / trade['entry_price']) * 100 * 5
                else:  # short
                    expected_pnl = ((trade['entry_price'] - trade['exit_price']) / trade['entry_price']) * 100 * 5
                
                print(f"    Expected P&L: {expected_pnl:.2f}%")
                print(f"    Calculation OK: {'✓' if abs(expected_pnl - trade['pnl_pct']) < 1 else '✗'}")
        
        # 4. 차트 생성
        plot_november_chart(df_1h, nov_trades, strategy)
    
    else:
        print("\nNo trades found in the period")

def plot_november_chart(df_1h, nov_trades, strategy):
    """11월 1-15일 차트 생성"""
    # 11월 데이터만 필터링
    nov_start = pd.to_datetime('2024-11-01')
    nov_end = pd.to_datetime('2024-11-15')
    df_nov = df_1h[(df_1h.index >= nov_start) & (df_1h.index <= nov_end)]
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10), sharex=True)
    
    # 1. 가격 차트
    ax1.plot(df_nov.index, df_nov['close'], 'b-', alpha=0.5, linewidth=1, label='Price')
    
    # EMA 계산 및 표시
    df_nov['ema20'] = df_1h['close'].ewm(span=20).mean()
    df_nov['ema50'] = df_1h['close'].ewm(span=50).mean()
    
    ax1.plot(df_nov.index, df_nov['ema20'], 'g-', alpha=0.8, label='EMA20', linewidth=2)
    ax1.plot(df_nov.index, df_nov['ema50'], 'r-', alpha=0.8, label='EMA50', linewidth=2)
    
    # 거래 표시
    for idx, trade in nov_trades.iterrows():
        color = 'green' if trade['direction'] == 'long' else 'red'
        marker_in = '^' if trade['direction'] == 'long' else 'v'
        marker_out = 'v' if trade['direction'] == 'long' else '^'
        
        ax1.scatter(trade['entry_time'], trade['entry_price'], color=color, 
                   s=100, marker=marker_in, zorder=5, edgecolors='black', linewidth=2)
        ax1.scatter(trade['exit_time'], trade['exit_price'], color=color, 
                   s=100, marker=marker_out, zorder=5, edgecolors='black', linewidth=2, alpha=0.6)
        
        # P&L 텍스트
        mid_time = trade['entry_time'] + (trade['exit_time'] - trade['entry_time']) / 2
        mid_price = (trade['entry_price'] + trade['exit_price']) / 2
        ax1.text(mid_time, mid_price, f"{trade['net_pnl_pct']:.1f}%",
                ha='center', va='center', fontsize=8, fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.3', 
                         facecolor='lightgreen' if trade['net_pnl_pct'] > 0 else 'lightcoral',
                         alpha=0.8))
    
    ax1.set_title('November 1-15, 2024 - EMA 20/50 Strategy Analysis', fontsize=14)
    ax1.set_ylabel('Price (USDT)')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # 2. EMA 차이
    ax2.plot(df_nov.index, df_nov['ema20'] - df_nov['ema50'], 'purple', linewidth=2)
    ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax2.fill_between(df_nov.index, 0, df_nov['ema20'] - df_nov['ema50'], 
                     where=df_nov['ema20'] > df_nov['ema50'], alpha=0.3, color='green')
    ax2.fill_between(df_nov.index, 0, df_nov['ema20'] - df_nov['ema50'], 
                     where=df_nov['ema20'] <= df_nov['ema50'], alpha=0.3, color='red')
    
    ax2.set_title('EMA20 - EMA50 Difference')
    ax2.set_ylabel('Price Difference')
    ax2.set_xlabel('Date')
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('november_2024_analysis.png', dpi=300, bbox_inches='tight')
    plt.show()
    
    print("\nChart saved as: november_2024_analysis.png")

def suggest_range_filters():
    """횡보장 필터 제안"""
    print("\n\n=== Suggested Range Market Filters ===")
    print("="*50)
    
    print("\n1. ADX Filter (Trend Strength):")
    print("""
    if adx < 25:  # Weak trend = potential range
        reduce_position_size *= 0.5
        # or skip trade entirely
    """)
    
    print("\n2. Bollinger Band Squeeze:")
    print("""
    bb_width = (upper_band - lower_band) / middle_band
    if bb_width < 0.02:  # 2% squeeze
        skip_trade = True
    """)
    
    print("\n3. ATR-based Range Detection:")
    print("""
    atr_ratio = atr / close
    if atr_ratio < 0.01:  # Low volatility
        use_tighter_stops = True
        stop_loss = 1.0 * atr  # Instead of 2.0
    """)
    
    print("\n4. EMA Distance Filter:")
    print("""
    ema_distance = abs(ema20 - ema50) / close
    if ema_distance < 0.005:  # EMAs too close (0.5%)
        wait_for_stronger_signal = True
    """)
    
    print("\n5. Recent Whipsaw Detection:")
    print("""
    # Count crosses in last N candles
    recent_crosses = count_ema_crosses(last_20_candles)
    if recent_crosses > 2:
        skip_trade = True  # Too many false signals
    """)
    
    print("\n6. Volume Confirmation:")
    print("""
    if volume < volume_ma20 * 0.8:  # Low volume
        require_stronger_breakout = True
    """)
    
    print("\n7. Multi-Timeframe Confirmation:")
    print("""
    # Check 4H timeframe
    if ema20_4h > ema50_4h and ema20_1h > ema50_1h:
        proceed_with_long = True  # Both timeframes agree
    """)

if __name__ == "__main__":
    try:
        # 11월 문제 분석
        analyze_november_issue()
        
        # 횡보장 필터 제안
        suggest_range_filters()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
