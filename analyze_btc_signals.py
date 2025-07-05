#!/usr/bin/env python3
"""
비트코인 실시간 데이터 분석 및 ZLMACD_ICHIMOKU 전략 신호 확인
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import json

# 프로젝트 루트를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

# 바이낸스 API를 직접 사용하는 간단한 버전
import ccxt

async def fetch_btc_data():
    """바이낸스에서 BTCUSDT 데이터 가져오기"""
    try:
        # Binance 거래소 객체 생성
        exchange = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_SECRET_KEY'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'  # 선물 거래
            }
        })
        
        # 1시간봉 데이터 가져오기 (최근 200개)
        ohlcv = exchange.fetch_ohlcv('BTC/USDT', '1h', limit=200)
        
        # 현재 가격
        ticker = exchange.fetch_ticker('BTC/USDT')
        current_price = ticker['last']
        
        print(f"\n📊 BTCUSDT 실시간 분석")
        print(f"{'='*60}")
        print(f"현재 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} KST")
        print(f"현재 가격: ${current_price:,.2f}")
        print(f"\n최근 2개 캔들:")
        
        # 최근 2개 캔들 표시
        for i in range(-2, 0):
            candle = ohlcv[i]
            timestamp = datetime.fromtimestamp(candle[0]/1000)
            print(f"  {timestamp.strftime('%Y-%m-%d %H:%M')} - O: ${candle[1]:,.2f}, H: ${candle[2]:,.2f}, L: ${candle[3]:,.2f}, C: ${candle[4]:,.2f}, V: {candle[5]:,.0f}")
        
        # 데이터를 DataFrame 형태로 변환
        data = {
            'timestamp': [x[0] for x in ohlcv],
            'open': [x[1] for x in ohlcv],
            'high': [x[2] for x in ohlcv],
            'low': [x[3] for x in ohlcv],
            'close': [x[4] for x in ohlcv],
            'volume': [x[5] for x in ohlcv]
        }
        
        return data, current_price
        
    except Exception as e:
        print(f"❌ 데이터 가져오기 실패: {e}")
        return None, None

def calculate_zlema(prices: List[float], period: int) -> List[float]:
    """Zero Lag EMA 계산"""
    if len(prices) < period * 2:
        return [None] * len(prices)
    
    # 첫 번째 EMA
    ema1 = []
    alpha = 2 / (period + 1)
    
    # 초기값
    ema1.append(sum(prices[:period]) / period)
    
    # EMA 계산
    for i in range(period, len(prices)):
        ema1.append((prices[i] - ema1[-1]) * alpha + ema1[-1])
    
    # 두 번째 EMA (EMA의 EMA)
    ema2 = []
    ema2.append(sum(ema1[:period]) / period)
    
    for i in range(period, len(ema1)):
        ema2.append((ema1[i] - ema2[-1]) * alpha + ema2[-1])
    
    # Zero Lag EMA = 2 * EMA1 - EMA2
    zlema = []
    for i in range(len(ema2)):
        zlema.append(2 * ema1[i] - ema2[i])
    
    # 패딩
    result = [None] * (len(prices) - len(zlema)) + zlema
    return result

def calculate_indicators(data: Dict) -> Dict:
    """지표 계산"""
    closes = data['close']
    highs = data['high']
    lows = data['low']
    
    # ZL MACD 계산
    zlema_fast = calculate_zlema(closes, 12)
    zlema_slow = calculate_zlema(closes, 26)
    
    macd_line = []
    for i in range(len(closes)):
        if zlema_fast[i] is not None and zlema_slow[i] is not None:
            macd_line.append(zlema_fast[i] - zlema_slow[i])
        else:
            macd_line.append(None)
    
    # Signal line (9-period EMA of MACD)
    signal_line = []
    valid_macd = [x for x in macd_line if x is not None]
    if len(valid_macd) >= 9:
        alpha = 2 / (9 + 1)
        signal_line.append(sum(valid_macd[:9]) / 9)
        for i in range(9, len(valid_macd)):
            signal_line.append((valid_macd[i] - signal_line[-1]) * alpha + signal_line[-1])
    
    # Ichimoku Cloud 계산
    # Tenkan-sen (9-period)
    tenkan = []
    for i in range(len(closes)):
        if i >= 8:
            high_9 = max(highs[i-8:i+1])
            low_9 = min(lows[i-8:i+1])
            tenkan.append((high_9 + low_9) / 2)
        else:
            tenkan.append(None)
    
    # Kijun-sen (26-period)
    kijun = []
    for i in range(len(closes)):
        if i >= 25:
            high_26 = max(highs[i-25:i+1])
            low_26 = min(lows[i-25:i+1])
            kijun.append((high_26 + low_26) / 2)
        else:
            kijun.append(None)
    
    # Senkou Span A & B (shifted 26 periods)
    senkou_a = []
    senkou_b = []
    for i in range(len(closes)):
        if i >= 25 and tenkan[i] is not None and kijun[i] is not None:
            senkou_a.append((tenkan[i] + kijun[i]) / 2)
        else:
            senkou_a.append(None)
            
        if i >= 51:
            high_52 = max(highs[i-51:i+1])
            low_52 = min(lows[i-51:i+1])
            senkou_b.append((high_52 + low_52) / 2)
        else:
            senkou_b.append(None)
    
    return {
        'macd': macd_line,
        'signal': signal_line,
        'tenkan': tenkan,
        'kijun': kijun,
        'senkou_a': senkou_a,
        'senkou_b': senkou_b
    }

def check_signals(data: Dict, indicators: Dict, current_price: float) -> Tuple[str, List[str], float]:
    """신호 체크"""
    # 마지막 인덱스
    idx = -1
    prev_idx = -2
    
    # 현재 값들
    try:
        current_close = data['close'][idx]
        macd = indicators['macd'][idx]
        macd_prev = indicators['macd'][prev_idx]
        signal = indicators['signal'][-1] if indicators['signal'] else None
        signal_prev = indicators['signal'][-2] if len(indicators['signal']) >= 2 else None
        tenkan = indicators['tenkan'][idx]
        kijun = indicators['kijun'][idx]
        senkou_a = indicators['senkou_a'][idx]
        senkou_b = indicators['senkou_b'][idx]
        
        # 구름 계산
        if senkou_a is not None and senkou_b is not None:
            cloud_top = max(senkou_a, senkou_b)
            cloud_bottom = min(senkou_a, senkou_b)
            cloud_color = "녹색" if senkou_a > senkou_b else "빨간색"
        else:
            cloud_top = cloud_bottom = None
            cloud_color = "N/A"
        
        print(f"\n📈 지표 현황:")
        print(f"  • ZL MACD: {macd:.2f}" if macd else "  • ZL MACD: N/A")
        print(f"  • Signal: {signal:.2f}" if signal else "  • Signal: N/A")
        print(f"  • 전환선: ${tenkan:.2f}" if tenkan else "  • 전환선: N/A")
        print(f"  • 기준선: ${kijun:.2f}" if kijun else "  • 기준선: N/A")
        print(f"  • 구름 상단: ${cloud_top:.2f}" if cloud_top else "  • 구름 상단: N/A")
        print(f"  • 구름 하단: ${cloud_bottom:.2f}" if cloud_bottom else "  • 구름 하단: N/A")
        print(f"  • 구름 색상: {cloud_color}")
        print(f"  • ADX: 가정값 30 (트렌드 충분)")  # 실제로는 ADX 계산 필요
        
        # 신호 체크
        long_signals = 0
        long_reasons = []
        short_signals = 0
        short_reasons = []
        
        # 롱 신호 체크
        if macd and signal and macd_prev and signal_prev:
            if macd > signal and macd_prev <= signal_prev:
                long_signals += 1
                long_reasons.append("✅ ZL MACD 골든크로스")
            elif macd < signal and macd_prev >= signal_prev:
                short_signals += 1
                short_reasons.append("✅ ZL MACD 데드크로스")
        
        if cloud_top and current_price > cloud_top:
            long_signals += 1
            long_reasons.append("✅ 가격이 구름 위")
        elif cloud_bottom and current_price < cloud_bottom:
            short_signals += 1
            short_reasons.append("✅ 가격이 구름 아래")
        
        if tenkan and kijun:
            if tenkan > kijun:
                long_signals += 1
                long_reasons.append("✅ 전환선 > 기준선")
            else:
                short_signals += 1
                short_reasons.append("✅ 전환선 < 기준선")
        
        if cloud_color == "녹색":
            long_signals += 0.5
            long_reasons.append("✅ 구름 상승 전환 (녹색)")
        else:
            short_signals += 0.5
            short_reasons.append("✅ 구름 하락 전환 (빨간색)")
        
        # 결과 판정
        if long_signals >= 3:
            return "LONG", long_reasons, long_signals
        elif short_signals >= 3:
            return "SHORT", short_reasons, short_signals
        else:
            return "NEUTRAL", [], max(long_signals, short_signals)
            
    except Exception as e:
        print(f"신호 체크 오류: {e}")
        return "ERROR", [], 0

async def main():
    """메인 실행 함수"""
    print("🔍 BTCUSDT ZLMACD_ICHIMOKU 전략 신호 분석 시작...")
    
    # 데이터 가져오기
    data, current_price = await fetch_btc_data()
    
    if data is None:
        print("데이터를 가져올 수 없습니다.")
        return
    
    # 지표 계산
    indicators = calculate_indicators(data)
    
    # 신호 체크
    signal_type, reasons, strength = check_signals(data, indicators, current_price)
    
    # 결과 출력
    print(f"\n🎯 전략 신호 분석 결과:")
    print(f"{'='*60}")
    
    if signal_type == "LONG":
        print(f"📈 **롱 진입 신호** (강도: {strength}/4)")
        for reason in reasons:
            print(f"   {reason}")
        print(f"\n💡 권장: 롱 포지션 진입 가능")
    elif signal_type == "SHORT":
        print(f"📉 **숏 진입 신호** (강도: {strength}/4)")
        for reason in reasons:
            print(f"   {reason}")
        print(f"\n💡 권장: 숏 포지션 진입 가능")
    else:
        print(f"⏸️  **중립 상태** (최대 신호 강도: {strength}/4)")
        print(f"   진입 조건 미충족 (최소 3개 신호 필요)")
        print(f"\n💡 권장: 대기 및 관찰")
    
    # 최근 캔들의 신호 히스토리
    print(f"\n📜 최근 10개 캔들 신호 히스토리:")
    for i in range(-10, 0):
        try:
            timestamp = datetime.fromtimestamp(data['timestamp'][i]/1000)
            macd = indicators['macd'][i]
            signal = indicators['signal'][i-len(indicators['signal'])+len(data['close'])] if indicators['signal'] else None
            
            if macd and signal:
                cross = "🔴" if macd < signal else "🟢"
            else:
                cross = "⚪"
                
            print(f"   {timestamp.strftime('%m-%d %H:%M')} {cross} C: ${data['close'][i]:,.0f}")
        except:
            pass

if __name__ == "__main__":
    asyncio.run(main())