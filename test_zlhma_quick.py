"""
ZLHMA EMA Cross 백테스트 빠른 테스트
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from zlhma_ema_cross_1h_backtest import ZLHMAEMACross1HBacktest, fetch_binance_data
import pandas as pd

# 2021 Q1 일부만 테스트
print("데이터 로드 중...")
df = fetch_binance_data('BTC/USDT', '2021-01-01', '2021-01-31', '1h')
print(f"로드 완료: {len(df)} 캔들")

# 백테스트
strategy = ZLHMAEMACross1HBacktest(initial_capital=10000, leverage=40)
print(f"\n초기 설정:")
print(f"- 레버리지: {strategy.leverage}x")
print(f"- ADX 임계값: {strategy.adx_threshold}")
print(f"- 초기 Kelly: 10%")

metrics = strategy.run_backtest(df)

print(f"\n결과:")
print(f"- 초기: $10,000")
print(f"- 최종: ${metrics['final_capital']:,.2f}")
print(f"- 수익률: {metrics['return']:+.2f}%")
print(f"- 거래 수: {metrics['trades']}")
print(f"- 승률: {metrics['win_rate']:.1f}%")
print(f"- MDD: {metrics['max_dd']:.1f}%")