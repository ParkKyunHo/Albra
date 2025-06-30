#!/usr/bin/env python3
"""
실시간 신호 상태 모니터링 스크립트
백테스팅과 실제 운영의 차이를 진단하기 위한 도구
"""

import sys
import os
import asyncio
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.core.binance_api import BinanceAPI
from src.strategies.tfpe_strategy import TFPEStrategy
from src.utils.config_manager import ConfigManager
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class SignalMonitor:
    """신호 상태 모니터링"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.config = self.config_manager.config
        self.binance_api = BinanceAPI(self.config)
        
        # 전략 설정
        strategy_config = self.config.get('strategies', {}).get('tfpe', {})
        self.strategy = TFPEStrategy(
            binance_api=self.binance_api,
            position_manager=None,  # 모니터링만 할 것이므로 None
            config=strategy_config
        )
    
    async def check_current_signals(self):
        """현재 신호 상태 체크"""
        print("\n=== TFPE 전략 신호 상태 점검 ===")
        print(f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"거래 코인: {', '.join(self.strategy.major_coins)}\n")
        
        for symbol in self.strategy.major_coins:
            print(f"\n[{symbol}]")
            
            try:
                # 데이터 준비
                df_4h, df_15m = await self.strategy.fetch_and_prepare_data(symbol)
                
                if df_4h is None or df_15m is None:
                    print(f"  ❌ 데이터 수집 실패")
                    continue
                
                # 현재 인덱스
                current_index = len(df_15m) - 1
                current = df_15m.iloc[current_index]
                
                # 4시간봉 추세
                current_time = df_15m.index[current_index]
                aligned_time = current_time.floor('4H')
                
                if aligned_time in df_4h.index:
                    trend_4h = df_4h.loc[aligned_time, 'trend']
                    trend_str = "상승" if trend_4h == 1 else "하락"
                else:
                    trend_str = "불명"
                
                # 주요 지표 출력
                print(f"  📊 현재 가격: ${current['close']:.2f}")
                print(f"  📈 추세 (4H): {trend_str}")
                print(f"  📍 가격 위치: {current.get('price_position', 0):.3f}")
                print(f"  📊 RSI: {current.get('rsi', 0):.1f}")
                print(f"  🔄 모멘텀: {current.get('momentum', 0):.2f}%")
                print(f"  📢 볼륨 비율: {current.get('volume_ratio', 0):.2f}x")
                print(f"  📏 EMA 거리: {current.get('ema_distance', 0):.3f}")
                print(f"  💪 ADX: {current.get('adx', 0):.1f}")
                
                # 채널폭 (4H)
                if aligned_time in df_4h.index:
                    channel_width = df_4h.loc[aligned_time, 'channel_width_pct']
                    print(f"  📐 채널폭 (4H): {channel_width:.1%}")
                
                # 신호 체크
                signal, direction = await self.strategy.check_entry_signal(
                    symbol, df_4h, df_15m, current_index
                )
                
                if signal:
                    print(f"  ✅ 신호 감지: {direction.upper()}")
                else:
                    print(f"  ⏸️ 신호 없음")
                
                # 조건 상세 분석
                await self._analyze_conditions(symbol, current, trend_4h if 'trend_4h' in locals() else 0)
                
            except Exception as e:
                print(f"  ❌ 분석 실패: {e}")
    
    async def _analyze_conditions(self, symbol: str, current, trend: int):
        """신호 조건 상세 분석"""
        print("\n  [조건 분석]")
        conditions = []
        
        # 1. 모멘텀
        if current.get('momentum', 0) > self.strategy.min_momentum:
            conditions.append("✅ 모멘텀")
        else:
            print(f"  ❌ 모멘텀 부족: {current.get('momentum', 0):.2f}% < {self.strategy.min_momentum}%")
        
        # 2. RSI
        rsi = current.get('rsi', 0)
        price_pos = current.get('price_position', 0.5)
        
        if trend == 1:  # 상승 추세
            if (price_pos < self.strategy.price_position_low and rsi <= 40) or \
               (0.4 <= price_pos <= 0.6 and rsi <= 45):
                conditions.append("✅ RSI")
            else:
                print(f"  ❌ RSI 조건 미충족 (롱): RSI={rsi:.1f}, 위치={price_pos:.3f}")
        else:  # 하락 추세
            if (price_pos > self.strategy.price_position_high and rsi >= 60) or \
               (0.4 <= price_pos <= 0.6 and rsi >= 55):
                conditions.append("✅ RSI")
            else:
                print(f"  ❌ RSI 조건 미충족 (숏): RSI={rsi:.1f}, 위치={price_pos:.3f}")
        
        # 3. EMA 거리
        if current.get('ema_distance', 1) <= self.strategy.ema_distance_max:
            conditions.append("✅ EMA 거리")
        else:
            print(f"  ❌ EMA 거리 초과: {current.get('ema_distance', 0):.3f} > {self.strategy.ema_distance_max}")
        
        # 4. 볼륨
        if current.get('volume_ratio', 0) >= self.strategy.volume_spike:
            conditions.append("✅ 볼륨")
        else:
            print(f"  ❌ 볼륨 부족: {current.get('volume_ratio', 0):.2f}x < {self.strategy.volume_spike}x")
        
        # 5. ADX
        if current.get('adx', 0) >= self.strategy.adx_min:
            print(f"  ✅ ADX 충족: {current.get('adx', 0):.1f}")
        else:
            print(f"  ❌ ADX 부족: {current.get('adx', 0):.1f} < {self.strategy.adx_min}")
        
        print(f"\n  충족 조건: {len(conditions)}/{self.strategy.signal_threshold} 필요")
        if conditions:
            print(f"  조건: {', '.join(conditions)}")
    
    async def compare_with_backtest(self):
        """백테스팅 조건과 비교"""
        print("\n\n=== 백테스팅 vs 실제 운영 설정 비교 ===")
        
        print("\n[신호 파라미터]")
        print(f"  신호 임계값: {self.strategy.signal_threshold}/5")
        print(f"  최소 신호 간격: {self.strategy.min_signal_interval}시간")
        print(f"  최소 모멘텀: {self.strategy.min_momentum}%")
        print(f"  볼륨 스파이크: {self.strategy.volume_spike}x")
        
        print("\n[Donchian 파라미터]")
        print(f"  DC 기간: {self.strategy.dc_period}")
        print(f"  롱 진입 위치: ≤{self.strategy.price_position_low}")
        print(f"  숏 진입 위치: ≥{self.strategy.price_position_high}")
        
        print("\n[RSI 파라미터]")
        print(f"  롱 진입 RSI: ≤{self.strategy.rsi_pullback_long}")
        print(f"  숏 진입 RSI: ≥{self.strategy.rsi_pullback_short}")
        print(f"  과매도: {self.strategy.rsi_oversold}")
        print(f"  과매수: {self.strategy.rsi_overbought}")
        
        print("\n[손절/익절]")
        print(f"  손절: ATR × {self.strategy.stop_loss_atr}")
        print(f"  익절: ATR × {self.strategy.take_profit_atr}")

async def main():
    """메인 실행"""
    monitor = SignalMonitor()
    
    # 현재 신호 상태 체크
    await monitor.check_current_signals()
    
    # 백테스팅 설정과 비교
    await monitor.compare_with_backtest()
    
    print("\n\n💡 팁:")
    print("- 신호가 너무 자주 발생하면 signal_threshold를 높이세요")
    print("- 포지션을 너무 자주 잡으면 min_signal_interval을 늘리세요")
    print("- 백테스팅과 차이가 크면 데이터 캐시 시간을 줄이세요")

if __name__ == "__main__":
    asyncio.run(main())
