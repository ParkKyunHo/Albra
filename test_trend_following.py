"""
추세 추종 ZLHMA 크로스 백테스트 테스트
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from zlhma_ema_cross_1h_backtest import ZLHMAEMACross1HBacktest, fetch_binance_data
import pandas as pd

# 2021 Q1 테스트
print("📊 추세 추종 ZLHMA 크로스 백테스트 시작...")
print("데이터 로드 중...")
df = fetch_binance_data('BTC/USDT', '2021-01-01', '2021-03-31', '1h')
print(f"✅ 로드 완료: {len(df)} 캔들")

# 백테스트
strategy = ZLHMAEMACross1HBacktest(initial_capital=10000, leverage=40)
print(f"\n초기 설정:")
print(f"- 전략: 추세 추종 ZLHMA 50/200 크로스")
print(f"- 레버리지: {strategy.leverage}x")
print(f"- ADX 임계값: {strategy.adx_threshold}")
print(f"- 초기 Kelly: 10%")
print(f"- 추세 필터: 200 ZLHMA 기준")

metrics = strategy.run_backtest(df)

print(f"\n📈 2021 Q1 결과:")
print(f"- 초기 자본: $10,000")
print(f"- 최종 자본: ${metrics['final_capital']:,.2f}")
print(f"- 수익률: {metrics['return']:+.2f}%")
print(f"- 거래 수: {metrics['trades']}")
print(f"- 승률: {metrics['win_rate']:.1f}%")
print(f"- MDD: {metrics['max_dd']:.1f}%")
print(f"- Sharpe: {metrics['sharpe']:.2f}")

# 거래 타입별 분석
if strategy.trades:
    long_trades = [t for t in strategy.trades if t['type'] == 'long']
    short_trades = [t for t in strategy.trades if t['type'] == 'short']
    
    print(f"\n거래 타입별 분석:")
    print(f"- 롱 거래: {len(long_trades)}개")
    print(f"- 숏 거래: {len(short_trades)}개")
    
    if long_trades:
        long_wins = [t for t in long_trades if t['pnl'] > 0]
        print(f"- 롱 승률: {len(long_wins)/len(long_trades)*100:.1f}%")
    
    if short_trades:
        short_wins = [t for t in short_trades if t['pnl'] > 0]
        print(f"- 숏 승률: {len(short_wins)/len(short_trades)*100:.1f}%")

# 원본 결과와 비교
print(f"\n📊 원본 결과와 비교:")
print(f"원본 - 수익률: +36.82%, 거래: 18개, 승률: 50.0%, MDD: 10.3%")
print(f"현재 - 수익률: {metrics['return']:+.2f}%, 거래: {metrics['trades']}개, 승률: {metrics['win_rate']:.1f}%, MDD: {metrics['max_dd']:.1f}%")