#!/usr/bin/env python3
"""
BTCUSDT ZLMACD_ICHIMOKU 전략 상세 분석
"""

import asyncio
import os
import sys
from datetime import datetime
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

import ccxt
import pandas as pd
import numpy as np

def calculate_zlema(series: pd.Series, period: int) -> pd.Series:
    """Zero Lag EMA 계산"""
    ema1 = series.ewm(span=period, adjust=False).mean()
    ema2 = ema1.ewm(span=period, adjust=False).mean()
    zlema = 2 * ema1 - ema2
    return zlema

async def analyze_in_detail():
    """상세 분석"""
    # Binance 연결
    exchange = ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_SECRET_KEY'),
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })
    
    # 1시간봉 데이터 가져오기
    ohlcv = exchange.fetch_ohlcv('BTC/USDT', '1h', limit=200)
    
    # DataFrame 변환
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    # ZL MACD 계산
    zlema_12 = calculate_zlema(df['close'], 12)
    zlema_26 = calculate_zlema(df['close'], 26)
    df['macd'] = zlema_12 - zlema_26
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    
    # Ichimoku 계산
    high_9 = df['high'].rolling(9).max()
    low_9 = df['low'].rolling(9).min()
    df['tenkan'] = (high_9 + low_9) / 2
    
    high_26 = df['high'].rolling(26).max()
    low_26 = df['low'].rolling(26).min()
    df['kijun'] = (high_26 + low_26) / 2
    
    df['senkou_a'] = ((df['tenkan'] + df['kijun']) / 2).shift(26)
    
    high_52 = df['high'].rolling(52).max()
    low_52 = df['low'].rolling(52).min()
    df['senkou_b'] = ((high_52 + low_52) / 2).shift(26)
    
    df['cloud_top'] = df[['senkou_a', 'senkou_b']].max(axis=1)
    df['cloud_bottom'] = df[['senkou_a', 'senkou_b']].min(axis=1)
    
    # 최근 데이터
    print("\n📊 BTCUSDT ZLMACD_ICHIMOKU 전략 상세 분석")
    print("="*70)
    print(f"분석 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} KST\n")
    
    # 마지막 3개 캔들 표시
    print("📈 최근 3개 캔들:")
    for i in range(-3, 0):
        row = df.iloc[i]
        print(f"  {row['timestamp'].strftime('%m-%d %H:%M')} - "
              f"O: ${row['open']:,.2f}, H: ${row['high']:,.2f}, "
              f"L: ${row['low']:,.2f}, C: ${row['close']:,.2f}")
    
    # 현재 지표값 (마지막 완성된 캔들 기준)
    current = df.iloc[-1]
    prev = df.iloc[-2]
    
    print(f"\n📊 현재 지표값 (마지막 완성 캔들):")
    print(f"  • 종가: ${current['close']:,.2f}")
    print(f"  • MACD: {current['macd']:.2f}")
    print(f"  • Signal: {current['signal']:.2f}")
    print(f"  • 전환선: ${current['tenkan']:,.2f}")
    print(f"  • 기준선: ${current['kijun']:,.2f}")
    print(f"  • 구름 상단: ${current['cloud_top']:,.2f}")
    print(f"  • 구름 하단: ${current['cloud_bottom']:,.2f}")
    print(f"  • 구름 색상: {'🟢 녹색' if current['senkou_a'] > current['senkou_b'] else '🔴 빨간색'}")
    
    # 신호 분석
    print(f"\n🎯 신호 분석:")
    print("="*70)
    
    # 숏 신호 체크
    short_signals = 0
    short_conditions = []
    
    # 1. MACD 데드크로스
    if current['macd'] < current['signal'] and prev['macd'] >= prev['signal']:
        short_signals += 1
        short_conditions.append("✅ ZL MACD 데드크로스 (방금 발생)")
    elif current['macd'] < current['signal']:
        short_conditions.append("⭕ MACD < Signal (이미 데드크로스 상태)")
    else:
        short_conditions.append("❌ MACD > Signal")
    
    # 2. 가격이 구름 아래
    if current['close'] < current['cloud_bottom']:
        short_signals += 1
        short_conditions.append(f"✅ 가격이 구름 아래 (${current['close']:,.2f} < ${current['cloud_bottom']:,.2f})")
    else:
        short_conditions.append(f"❌ 가격이 구름 내부/위 (${current['close']:,.2f} vs 구름하단 ${current['cloud_bottom']:,.2f})")
    
    # 3. 전환선 < 기준선
    if current['tenkan'] < current['kijun']:
        short_signals += 1
        short_conditions.append(f"✅ 전환선 < 기준선 (${current['tenkan']:,.2f} < ${current['kijun']:,.2f})")
    else:
        short_conditions.append("❌ 전환선 > 기준선")
    
    # 4. 구름 색상
    if current['senkou_a'] < current['senkou_b']:
        short_signals += 0.5
        short_conditions.append("✅ 구름 하락 전환 (빨간색)")
    else:
        short_conditions.append("❌ 구름 상승 (녹색)")
    
    # 롱 신호 체크
    long_signals = 0
    long_conditions = []
    
    # 1. MACD 골든크로스
    if current['macd'] > current['signal'] and prev['macd'] <= prev['signal']:
        long_signals += 1
        long_conditions.append("✅ ZL MACD 골든크로스 (방금 발생)")
    elif current['macd'] > current['signal']:
        long_conditions.append("⭕ MACD > Signal (이미 골든크로스 상태)")
    else:
        long_conditions.append("❌ MACD < Signal")
    
    # 2. 가격이 구름 위
    if current['close'] > current['cloud_top']:
        long_signals += 1
        long_conditions.append(f"✅ 가격이 구름 위 (${current['close']:,.2f} > ${current['cloud_top']:,.2f})")
    else:
        long_conditions.append(f"❌ 가격이 구름 내부/아래")
    
    # 3. 전환선 > 기준선
    if current['tenkan'] > current['kijun']:
        long_signals += 1
        long_conditions.append("✅ 전환선 > 기준선")
    else:
        long_conditions.append("❌ 전환선 < 기준선")
    
    # 4. 구름 색상
    if current['senkou_a'] > current['senkou_b']:
        long_signals += 0.5
        long_conditions.append("✅ 구름 상승 전환 (녹색)")
    else:
        long_conditions.append("❌ 구름 하락 (빨간색)")
    
    # 결과 출력
    print(f"\n📉 숏 신호 (강도: {short_signals}/4):")
    for condition in short_conditions:
        print(f"  {condition}")
    
    print(f"\n📈 롱 신호 (강도: {long_signals}/4):")
    for condition in long_conditions:
        print(f"  {condition}")
    
    # 최종 판단
    print(f"\n💡 최종 판단:")
    print("="*70)
    
    if short_signals >= 3:
        print(f"🔴 **숏 진입 신호** - 강도: {short_signals}/4")
        print(f"   ZLMACD_ICHIMOKU 전략이 숏 포지션을 열 수 있습니다.")
    elif long_signals >= 3:
        print(f"🟢 **롱 진입 신호** - 강도: {long_signals}/4")
        print(f"   ZLMACD_ICHIMOKU 전략이 롱 포지션을 열 수 있습니다.")
    else:
        print(f"⏸️  **대기 상태**")
        print(f"   롱 신호: {long_signals}/3 필요")
        print(f"   숏 신호: {short_signals}/3 필요")
        print(f"   진입 조건을 충족하지 못했습니다.")
    
    # MACD 히스토리
    print(f"\n📊 MACD 크로스 히스토리 (최근 10개):")
    for i in range(-10, 0):
        row = df.iloc[i]
        if pd.notna(row['macd']) and pd.notna(row['signal']):
            cross = "🟢" if row['macd'] > row['signal'] else "🔴"
            print(f"  {row['timestamp'].strftime('%m-%d %H:%M')} {cross} "
                  f"MACD: {row['macd']:.2f}, Signal: {row['signal']:.2f}")

if __name__ == "__main__":
    asyncio.run(analyze_in_detail())