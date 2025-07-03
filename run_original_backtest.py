"""
원본 백테스트 모듈 실행
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backtest_modules'))

from backtest_modules.zlhma_ema_cross_strategy_backtest import ZLHMAEMACrossStrategy

# 데이터 가져오기 (실제 구현에 맞게 수정 필요)
def run_original_backtest():
    print("\n" + "="*80)
    print("ORIGINAL ZLHMA EMA CROSS BACKTEST")
    print("="*80)
    
    # 전략 인스턴스 생성
    strategy = ZLHMAEMACrossStrategy(
        initial_capital=10000,
        leverage=10,  # 원본과 동일
        symbol='BTC/USDT'
    )
    
    # 백테스트 실행 (실제 데이터 필요)
    # 여기서는 예시만 보여줍니다
    print(f"Initial Capital: ${strategy.capital:,.2f}")
    print(f"Leverage: {strategy.leverage}x")
    print(f"Position Size: {strategy.position_size}%")
    print(f"ADX Threshold: {strategy.adx_threshold}")
    print(f"Symbol: {strategy.symbol}")
    
    print("\n원본 백테스트를 실행하려면 실제 데이터가 필요합니다.")
    print("backtest_modules/fixed/data_fetcher_fixed.py 모듈을 사용하여")
    print("실제 바이낸스 데이터를 가져와야 합니다.")


if __name__ == "__main__":
    run_original_backtest()