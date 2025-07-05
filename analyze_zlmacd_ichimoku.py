#!/usr/bin/env python3
"""
BTCUSDT의 최근 데이터를 가져와서 ZLMACD_ICHIMOKU 전략의 진입 조건 분석
"""

import asyncio
import pandas as pd
import numpy as np
from datetime import datetime
import os
import sys
from dotenv import load_dotenv

# 프로젝트 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.core.binance_api import BinanceAPI
from src.strategies.zlmacd_ichimoku_strategy import ZLMACDIchimokuStrategy

# 환경 변수 로드
load_dotenv()

class ZLMACDAnalyzer:
    def __init__(self):
        # API 키 로드
        self.api_key = os.getenv('BINANCE_API_KEY')
        self.secret_key = os.getenv('BINANCE_SECRET_KEY')
        
        # BinanceAPI 초기화
        self.api = BinanceAPI(self.api_key, self.secret_key, testnet=False)
        
        # 전략 파라미터
        self.strategy_params = {
            'zlmacd_fast': 12,
            'zlmacd_slow': 26,
            'zlmacd_signal': 9,
            'tenkan_period': 9,
            'kijun_period': 26,
            'senkou_b_period': 52,
            'chikou_shift': 26,
            'cloud_shift': 26,
            'adx_period': 14,
            'adx_threshold': 25,
            'min_signal_strength': 3
        }
        
        # 더미 전략 객체 (지표 계산 메서드 사용)
        self.strategy = type('DummyStrategy', (), {
            'calculate_zlema': ZLMACDIchimokuStrategy.calculate_zlema,
            'calculate_zlmacd': ZLMACDIchimokuStrategy.calculate_zlmacd,
            'calculate_ichimoku': ZLMACDIchimokuStrategy.calculate_ichimoku,
            'calculate_adx': ZLMACDIchimokuStrategy.calculate_adx,
            'zlmacd_fast': self.strategy_params['zlmacd_fast'],
            'zlmacd_slow': self.strategy_params['zlmacd_slow'],
            'zlmacd_signal': self.strategy_params['zlmacd_signal'],
            'tenkan_period': self.strategy_params['tenkan_period'],
            'kijun_period': self.strategy_params['kijun_period'],
            'senkou_b_period': self.strategy_params['senkou_b_period'],
            'chikou_shift': self.strategy_params['chikou_shift'],
            'cloud_shift': self.strategy_params['cloud_shift'],
            'adx_period': self.strategy_params['adx_period']
        })()
    
    async def analyze(self):
        """메인 분석 함수"""
        try:
            # API 초기화
            print("🔌 바이낸스 API 연결 중...")
            if not await self.api.initialize():
                print("❌ API 초기화 실패")
                return
            
            print("✅ API 연결 성공\n")
            
            # 1시간봉 데이터 가져오기 (200개)
            print("📊 BTCUSDT 1시간봉 데이터 가져오는 중...")
            df = await self.api.get_klines("BTCUSDT", "1h", limit=200)
            
            if df.empty:
                print("❌ 데이터를 가져올 수 없습니다.")
                return
            
            print(f"✅ {len(df)}개 캔들 데이터 수신\n")
            
            # 현재 가격 정보
            current_price = await self.api.get_current_price("BTCUSDT")
            print(f"💰 현재 가격: ${current_price:,.2f}")
            
            # 최근 2개 캔들 정보
            print("\n📊 최근 2개 1시간봉:")
            for i in range(-2, 0):
                candle = df.iloc[i]
                print(f"  [{i+3}번째 캔들] {candle.name.strftime('%Y-%m-%d %H:%M')}")
                print(f"    시가: ${candle['open']:,.2f}")
                print(f"    고가: ${candle['high']:,.2f}")
                print(f"    저가: ${candle['low']:,.2f}")
                print(f"    종가: ${candle['close']:,.2f}")
                print(f"    거래량: {candle['volume']:,.2f}")
            
            # 지표 계산
            print("\n📈 지표 계산 중...")
            
            # ZL MACD 계산
            df = self.strategy.calculate_zlmacd(self.strategy, df.copy())
            
            # Ichimoku 계산
            df = self.strategy.calculate_ichimoku(self.strategy, df.copy())
            
            # ADX 계산
            df = self.strategy.calculate_adx(self.strategy, df.copy())
            
            # 현재 지표 값
            current_idx = -1
            prev_idx = -2
            
            # ZL MACD 값
            zlmacd = df['zlmacd'].iloc[current_idx]
            zlmacd_signal = df['zlmacd_signal'].iloc[current_idx]
            zlmacd_prev = df['zlmacd'].iloc[prev_idx]
            zlmacd_signal_prev = df['zlmacd_signal'].iloc[prev_idx]
            
            print("\n🔵 ZL MACD 지표:")
            print(f"  현재 MACD: {zlmacd:.4f}")
            print(f"  현재 Signal: {zlmacd_signal:.4f}")
            print(f"  이전 MACD: {zlmacd_prev:.4f}")
            print(f"  이전 Signal: {zlmacd_signal_prev:.4f}")
            
            # Ichimoku 값
            tenkan = df['tenkan_sen'].iloc[current_idx]
            kijun = df['kijun_sen'].iloc[current_idx]
            cloud_top = df['cloud_top'].iloc[current_idx]
            cloud_bottom = df['cloud_bottom'].iloc[current_idx]
            cloud_color = df['cloud_color'].iloc[current_idx]
            
            print("\n☁️ Ichimoku Cloud 지표:")
            print(f"  전환선 (Tenkan): ${tenkan:,.2f}")
            print(f"  기준선 (Kijun): ${kijun:,.2f}")
            print(f"  구름 상단: ${cloud_top:,.2f}")
            print(f"  구름 하단: ${cloud_bottom:,.2f}")
            print(f"  구름 색상: {'🟢 녹색 (상승)' if cloud_color == 1 else '🔴 빨간색 (하락)'}")
            
            # ADX 값
            adx_col = f'ADX_{self.strategy_params["adx_period"]}'
            adx_value = df[adx_col].iloc[current_idx] if adx_col in df.columns else 0
            
            print(f"\n📊 ADX 값: {adx_value:.2f} {'✅ (트렌드 충분)' if adx_value > self.strategy_params['adx_threshold'] else '❌ (트렌드 부족)'}")
            
            # 진입 조건 분석
            print("\n" + "="*50)
            print("📋 진입 조건 분석")
            print("="*50)
            
            # 롱 진입 조건 체크
            print("\n🟢 롱 진입 조건 (최소 3개 충족 필요):")
            long_signals = 0
            
            # 1. ZL MACD 골든크로스
            if zlmacd > zlmacd_signal and zlmacd_prev <= zlmacd_signal_prev:
                print("  ✅ ZL MACD 골든크로스 발생")
                long_signals += 1
            else:
                print("  ❌ ZL MACD 골든크로스 없음")
            
            # 2. 가격이 구름 위
            if current_price > cloud_top:
                print(f"  ✅ 가격이 구름 위 (${current_price:,.2f} > ${cloud_top:,.2f})")
                long_signals += 1
            else:
                print(f"  ❌ 가격이 구름 위가 아님 (${current_price:,.2f} <= ${cloud_top:,.2f})")
            
            # 3. 전환선 > 기준선
            if tenkan > kijun:
                print(f"  ✅ 전환선 > 기준선 (${tenkan:,.2f} > ${kijun:,.2f})")
                long_signals += 1
            else:
                print(f"  ❌ 전환선 <= 기준선 (${tenkan:,.2f} <= ${kijun:,.2f})")
            
            # 4. 구름 상승 전환
            if cloud_color == 1:
                print("  ✅ 구름이 상승 전환 (녹색)")
                long_signals += 0.5
            else:
                print("  ❌ 구름이 하락 전환 (빨간색)")
            
            print(f"\n  롱 신호 강도: {long_signals}/4")
            
            # 숏 진입 조건 체크
            print("\n🔴 숏 진입 조건 (최소 3개 충족 필요):")
            short_signals = 0
            
            # 1. ZL MACD 데드크로스
            if zlmacd < zlmacd_signal and zlmacd_prev >= zlmacd_signal_prev:
                print("  ✅ ZL MACD 데드크로스 발생")
                short_signals += 1
            else:
                print("  ❌ ZL MACD 데드크로스 없음")
            
            # 2. 가격이 구름 아래
            if current_price < cloud_bottom:
                print(f"  ✅ 가격이 구름 아래 (${current_price:,.2f} < ${cloud_bottom:,.2f})")
                short_signals += 1
            else:
                print(f"  ❌ 가격이 구름 아래가 아님 (${current_price:,.2f} >= ${cloud_bottom:,.2f})")
            
            # 3. 전환선 < 기준선
            if tenkan < kijun:
                print(f"  ✅ 전환선 < 기준선 (${tenkan:,.2f} < ${kijun:,.2f})")
                short_signals += 1
            else:
                print(f"  ❌ 전환선 >= 기준선 (${tenkan:,.2f} >= ${kijun:,.2f})")
            
            # 4. 구름 하락 전환
            if cloud_color == 0:
                print("  ✅ 구름이 하락 전환 (빨간색)")
                short_signals += 0.5
            else:
                print("  ❌ 구름이 상승 전환 (녹색)")
            
            print(f"\n  숏 신호 강도: {short_signals}/4")
            
            # 최종 판단
            print("\n" + "="*50)
            print("🎯 최종 분석 결과")
            print("="*50)
            
            if adx_value < self.strategy_params['adx_threshold']:
                print("❌ ADX가 임계값 미만 - 진입 불가")
            elif long_signals >= self.strategy_params['min_signal_strength']:
                print("✅ 롱 진입 조건 충족!")
                print(f"   신호 강도: {long_signals}")
                print("   추천: LONG 포지션 진입")
            elif short_signals >= self.strategy_params['min_signal_strength']:
                print("✅ 숏 진입 조건 충족!")
                print(f"   신호 강도: {short_signals}")
                print("   추천: SHORT 포지션 진입")
            else:
                print("⏸️ 진입 조건 미충족 - 대기")
                print(f"   롱 신호: {long_signals}/3")
                print(f"   숏 신호: {short_signals}/3")
            
            # 추가 정보
            print("\n📌 추가 정보:")
            print(f"  현재 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  마지막 캔들 시간: {df.index[-1].strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 히스토리컬 백테스트 (최근 10개 캔들)
            print("\n📜 최근 10개 캔들 신호 히스토리:")
            for i in range(-10, 0):
                candle_time = df.index[i].strftime('%m-%d %H:%M')
                zlmacd_i = df['zlmacd'].iloc[i]
                signal_i = df['zlmacd_signal'].iloc[i]
                price_i = df['close'].iloc[i]
                cloud_top_i = df['cloud_top'].iloc[i]
                cloud_bottom_i = df['cloud_bottom'].iloc[i]
                
                signal_type = "➖"
                if i > -10:  # 이전 캔들과 비교 가능한 경우
                    if (df['zlmacd'].iloc[i] > df['zlmacd_signal'].iloc[i] and 
                        df['zlmacd'].iloc[i-1] <= df['zlmacd_signal'].iloc[i-1]):
                        signal_type = "🟢"
                    elif (df['zlmacd'].iloc[i] < df['zlmacd_signal'].iloc[i] and 
                          df['zlmacd'].iloc[i-1] >= df['zlmacd_signal'].iloc[i-1]):
                        signal_type = "🔴"
                
                position = "구름위" if price_i > cloud_top_i else "구름아래" if price_i < cloud_bottom_i else "구름속"
                print(f"  {candle_time}: {signal_type} ${price_i:,.0f} ({position})")
            
        except Exception as e:
            print(f"❌ 분석 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # API 정리
            if hasattr(self, 'api'):
                await self.api.cleanup()

async def main():
    analyzer = ZLMACDAnalyzer()
    await analyzer.analyze()

if __name__ == "__main__":
    asyncio.run(main())