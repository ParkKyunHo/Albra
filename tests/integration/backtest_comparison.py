#!/usr/bin/env python3
"""
백테스팅과 실제 운영의 일치성 검증 스크립트
캔들 종가 기준 체크가 올바르게 작동하는지 확인
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
from dotenv import load_dotenv
import os

logger = setup_logger(__name__)

class BacktestComparisonTool:
    """백테스팅과 실제 운영 비교 도구"""
    
    def __init__(self):
        # 환경변수 로드
        load_dotenv()
        
        self.config_manager = ConfigManager()
        self.config = self.config_manager.config
        
        # API 키 가져오기
        api_key = os.getenv('BINANCE_API_KEY')
        secret_key = os.getenv('BINANCE_SECRET_KEY')
        
        if not api_key or not secret_key:
            raise ValueError("BINANCE_API_KEY와 BINANCE_SECRET_KEY가 .env 파일에 설정되어 있어야 합니다.")
        
        self.binance_api = BinanceAPI(api_key, secret_key, self.config)
        
        # 전략 설정
        strategy_config = self.config.get('strategies', {}).get('tfpe', {})
        self.strategy = TFPEStrategy(
            binance_api=self.binance_api,
            position_manager=None,
            config=strategy_config
        )
    
    async def check_candle_timing(self):
        """캔들 타이밍 체크"""
        print("\n=== 캔들 타이밍 검증 ===")
        
        current_time = datetime.now()
        current_minute = current_time.minute
        
        # 15분 캔들 시작 시간
        candle_start = (current_minute // 15) * 15
        candle_time = current_time.replace(minute=candle_start, second=0, microsecond=0)
        
        # 다음 캔들까지 남은 시간
        next_candle = candle_time + timedelta(minutes=15)
        time_to_next = (next_candle - current_time).total_seconds()
        
        print(f"현재 시간: {current_time.strftime('%H:%M:%S')}")
        print(f"현재 캔들: {candle_time.strftime('%H:%M')} ~ {next_candle.strftime('%H:%M')}")
        print(f"다음 캔들까지: {int(time_to_next // 60)}분 {int(time_to_next % 60)}초")
        
        # 캔들 완성 후 경과 시간
        seconds_since_candle = (current_time - candle_time).total_seconds()
        
        if 30 <= seconds_since_candle <= 90:
            print(f"✅ 신호 체크 가능 시간대 (캔들 완성 후 {int(seconds_since_candle)}초)")
        else:
            print(f"⏸️ 신호 체크 대기 중 (캔들 완성 후 {int(seconds_since_candle)}초)")
        
        return candle_time, seconds_since_candle
    
    async def simulate_signal_check(self, symbol: str = 'BTCUSDT'):
        """신호 체크 시뮬레이션"""
        print(f"\n=== {symbol} 신호 체크 시뮬레이션 ===")
        
        # 데이터 가져오기
        df_4h, df_15m = await self.strategy.fetch_and_prepare_data(symbol)
        
        if df_4h is None or df_15m is None:
            print("❌ 데이터 수집 실패")
            return
        
        # 백테스팅 방식: 마지막 완성된 캔들 사용
        backtest_index = len(df_15m) - 2  # -2는 마지막 완성된 캔들
        backtest_candle = df_15m.iloc[backtest_index]
        backtest_time = df_15m.index[backtest_index]
        
        # 실시간 방식: 현재 진행 중인 캔들 사용 (비교용)
        realtime_index = len(df_15m) - 1  # -1은 현재 진행 중인 캔들
        realtime_candle = df_15m.iloc[realtime_index]
        realtime_time = df_15m.index[realtime_index]
        
        print(f"\n[백테스팅 방식 - 완성된 캔들]")
        print(f"캔들 시간: {backtest_time}")
        print(f"종가: ${backtest_candle['close']:.2f}")
        print(f"RSI: {backtest_candle.get('rsi', 0):.1f}")
        print(f"가격 위치: {backtest_candle.get('price_position', 0):.3f}")
        print(f"모멘텀: {backtest_candle.get('momentum', 0):.2f}%")
        
        print(f"\n[실시간 방식 - 진행 중인 캔들]")
        print(f"캔들 시간: {realtime_time}")
        print(f"현재가: ${realtime_candle['close']:.2f}")
        print(f"RSI: {realtime_candle.get('rsi', 0):.1f}")
        print(f"가격 위치: {realtime_candle.get('price_position', 0):.3f}")
        print(f"모멘텀: {realtime_candle.get('momentum', 0):.2f}%")
        
        # 차이 분석
        print(f"\n[차이 분석]")
        price_diff = abs(realtime_candle['close'] - backtest_candle['close'])
        price_diff_pct = (price_diff / backtest_candle['close']) * 100
        
        print(f"가격 차이: ${price_diff:.2f} ({price_diff_pct:.2f}%)")
        
        if 'rsi' in backtest_candle and 'rsi' in realtime_candle:
            rsi_diff = abs(realtime_candle['rsi'] - backtest_candle['rsi'])
            print(f"RSI 차이: {rsi_diff:.1f}")
        
        # 신호 체크 (백테스팅 방식)
        signal, direction = await self.strategy.check_entry_signal(
            symbol, df_4h, df_15m, backtest_index
        )
        
        print(f"\n[백테스팅 방식 신호 결과]")
        if signal:
            print(f"✅ 신호 감지: {direction.upper()}")
        else:
            print(f"⏸️ 신호 없음")
    
    async def monitor_cycle_execution(self):
        """사이클 실행 모니터링"""
        print("\n=== 사이클 실행 모니터링 ===")
        
        # 15분 동안 모니터링
        start_time = datetime.now()
        check_count = 0
        
        print(f"모니터링 시작: {start_time.strftime('%H:%M:%S')}")
        print("15분 동안 실제 체크가 언제 일어나는지 관찰...")
        
        while (datetime.now() - start_time).total_seconds() < 900:  # 15분
            current_time = datetime.now()
            current_minute = current_time.minute
            seconds_since_candle = current_time.second + (current_minute % 15) * 60
            
            # 체크 조건 확인
            if 30 <= seconds_since_candle <= 90:
                check_count += 1
                candle_time = current_time.replace(
                    minute=(current_minute // 15) * 15, 
                    second=0, 
                    microsecond=0
                )
                print(f"\n[체크 #{check_count}] {current_time.strftime('%H:%M:%S')}")
                print(f"  캔들: {candle_time.strftime('%H:%M')}")
                print(f"  캔들 완성 후: {seconds_since_candle}초")
            
            await asyncio.sleep(10)  # 10초마다 확인
        
        print(f"\n모니터링 완료: 총 {check_count}회 체크 수행")

async def main():
    """메인 실행"""
    tool = BacktestComparisonTool()
    
    while True:
        print("\n" + "="*60)
        print("백테스팅 vs 실제 운영 검증 도구")
        print("="*60)
        print("1. 캔들 타이밍 체크")
        print("2. 신호 체크 시뮬레이션")
        print("3. 사이클 실행 모니터링 (15분)")
        print("4. 종료")
        
        choice = input("\n선택하세요 (1-4): ")
        
        if choice == '1':
            await tool.check_candle_timing()
        elif choice == '2':
            await tool.simulate_signal_check()
        elif choice == '3':
            await tool.monitor_cycle_execution()
        elif choice == '4':
            print("종료합니다.")
            break
        else:
            print("잘못된 선택입니다.")
        
        if choice != '4':
            input("\n계속하려면 Enter를 누르세요...")

if __name__ == "__main__":
    asyncio.run(main())
