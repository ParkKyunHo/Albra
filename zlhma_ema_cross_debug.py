"""
ZLHMA EMA Cross 백테스트 디버깅
진입 신호가 왜 발생하지 않는지 확인
"""

import pandas as pd
import numpy as np
from datetime import datetime

# 백테스트 모듈 import
from zlhma_ema_cross_1h_backtest import ZLHMAEMACross1HBacktest, generate_realistic_data


def debug_entry_signals():
    """진입 신호 디버깅"""
    print("\n" + "="*80)
    print("ZLHMA EMA CROSS - ENTRY SIGNAL DEBUG")
    print("="*80)
    
    # 데이터 생성
    df = generate_realistic_data('2024-01-01', '2024-03-31', '1h')
    print(f"📊 Generated {len(df)} candles")
    
    # 백테스트 인스턴스 생성
    strategy = ZLHMAEMACross1HBacktest(initial_capital=10000, leverage=10)
    
    # 지표 계산
    df = strategy.calculate_indicators(df)
    
    # ADX 값 확인
    print("\n📊 ADX Values:")
    adx_values = df['adx'].dropna()
    print(f"  • ADX 평균: {adx_values.mean():.2f}")
    print(f"  • ADX 최대: {adx_values.max():.2f}")
    print(f"  • ADX 최소: {adx_values.min():.2f}")
    print(f"  • ADX > 25: {(adx_values > 25).sum()} 캔들 ({(adx_values > 25).sum() / len(adx_values) * 100:.1f}%)")
    
    # EMA 크로스 확인
    ema_cross_count = 0
    golden_cross_count = 0
    death_cross_count = 0
    
    for i in range(strategy.slow_ema_period + 1, len(df)):
        current = df.iloc[i]
        prev = df.iloc[i-1]
        
        fast_ema = current['ema_50']
        slow_ema = current['ema_200']
        fast_ema_prev = prev['ema_50']
        slow_ema_prev = prev['ema_200']
        
        # 골든크로스
        if fast_ema > slow_ema and fast_ema_prev <= slow_ema_prev:
            golden_cross_count += 1
            print(f"\n🔸 Golden Cross at {df.index[i]}")
            print(f"  • Fast EMA: {fast_ema:.2f} (prev: {fast_ema_prev:.2f})")
            print(f"  • Slow EMA: {slow_ema:.2f} (prev: {slow_ema_prev:.2f})")
            
            # 신호 강도 계산
            signal_strength = 2.0  # 크로스 기본 점수
            
            # ZLHMA 체크
            if i >= 2:
                zlhma = current['zlhma']
                zlhma_prev = prev['zlhma']
                zlhma_prev2 = df.iloc[i-2]['zlhma']
                
                if zlhma > zlhma_prev and zlhma_prev > zlhma_prev2:
                    signal_strength += 1.0
                    print(f"  ✓ ZLHMA 상승 모멘텀")
                    
            # 가격 위치
            if current['close'] > current['zlhma']:
                signal_strength += 0.5
                print(f"  ✓ 가격이 ZLHMA 위")
                
            if current['close'] > fast_ema and current['close'] > slow_ema:
                signal_strength += 0.5
                print(f"  ✓ 가격이 두 EMA 위")
                
            print(f"  • Signal Strength: {signal_strength}/2.5")
            print(f"  • ADX: {current['adx']:.2f}")
            
            # 진입 가능 여부
            if signal_strength >= 2.5 and current['adx'] >= 25:
                print(f"  ✅ ENTRY SIGNAL!")
            else:
                print(f"  ❌ No entry (strength: {signal_strength}, ADX: {current['adx']:.2f})")
        
        # 데드크로스
        elif fast_ema < slow_ema and fast_ema_prev >= slow_ema_prev:
            death_cross_count += 1
            print(f"\n🔹 Death Cross at {df.index[i]}")
    
    print(f"\n📊 Summary:")
    print(f"  • Total Golden Crosses: {golden_cross_count}")
    print(f"  • Total Death Crosses: {death_cross_count}")
    print(f"  • Total Crosses: {golden_cross_count + death_cross_count}")
    
    # 가격 움직임 확인
    print(f"\n📊 Price Movement:")
    print(f"  • Start Price: ${df.iloc[0]['close']:.2f}")
    print(f"  • End Price: ${df.iloc[-1]['close']:.2f}")
    print(f"  • Change: {(df.iloc[-1]['close'] / df.iloc[0]['close'] - 1) * 100:.2f}%")
    
    # EMA 상태 확인
    ema_bullish = (df['ema_50'] > df['ema_200']).sum()
    ema_bearish = (df['ema_50'] < df['ema_200']).sum()
    print(f"\n📊 EMA State:")
    print(f"  • Bullish (50 > 200): {ema_bullish} candles ({ema_bullish/len(df)*100:.1f}%)")
    print(f"  • Bearish (50 < 200): {ema_bearish} candles ({ema_bearish/len(df)*100:.1f}%)")


if __name__ == "__main__":
    debug_entry_signals()