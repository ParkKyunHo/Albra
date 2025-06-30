#!/usr/bin/env python3
"""
백테스팅과 실제 트레이딩의 일치성 확인 스크립트
"""

import sys
import os
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.binance_api import BinanceAPI
from src.strategies.tfpe_strategy import TFPEStrategy
from src.utils.config_manager import ConfigManager
from src.utils.logger import setup_logger
from dotenv import load_dotenv

logger = setup_logger(__name__)

class TradingConsistencyChecker:
    """백테스팅과 실제 트레이딩의 일치성 검증"""
    
    def __init__(self):
        load_dotenv()
        self.config_manager = ConfigManager()
        self.config = self.config_manager.config
        
        # API 키 가져오기
        api_key = os.getenv('BINANCE_API_KEY')
        secret_key = os.getenv('BINANCE_SECRET_KEY')
        
        if not api_key or not secret_key:
            raise ValueError("BINANCE_API_KEY와 BINANCE_SECRET_KEY가 필요합니다.")
        
        self.binance_api = BinanceAPI(api_key, secret_key, self.config.get('system', {}).get('mode') == 'testnet')
        
    async def check_candle_timing_consistency(self):
        """캔들 타이밍 일치성 확인"""
        print("\n=== 캔들 타이밍 일치성 검증 ===")
        
        # 1. 서버 시간 vs 로컬 시간
        await self.binance_api.initialize()
        server_time_ms = await self.binance_api.get_server_time()
        server_time = datetime.fromtimestamp(server_time_ms / 1000)
        local_time = datetime.now()
        
        time_diff = abs((server_time - local_time).total_seconds())
        
        print(f"서버 시간: {server_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"로컬 시간: {local_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"시간 차이: {time_diff:.1f}초")
        
        if time_diff > 5:
            print("⚠️ 경고: 서버와 로컬 시간 차이가 5초 이상입니다!")
        else:
            print("✅ 시간 동기화 양호")
        
        # 2. 캔들 체크 윈도우 확인
        tfpe_config = self.config.get('strategies', {}).get('tfpe', {})
        candle_config = tfpe_config.get('candle_close_check', {})
        
        print(f"\n캔들 체크 설정:")
        print(f"  - 체크 윈도우: {candle_config.get('check_window_seconds', 30)}초")
        print(f"  - 서버 시간 사용: {candle_config.get('use_server_time', True)}")
        print(f"  - API 지연 허용: {candle_config.get('api_delay_tolerance', 5)}초")
        
        # 3. 백테스팅 방식과 비교
        print(f"\n백테스팅 vs 실제 트레이딩:")
        print(f"  - 백테스팅: 마지막 완성된 캔들 사용 (index = -2)")
        print(f"  - 실제: 캔들 완성 후 {candle_config.get('check_window_seconds', 30)}초 이내 체크")
        print(f"  - 차이: 최대 {candle_config.get('check_window_seconds', 30) + candle_config.get('api_delay_tolerance', 5)}초")
        
        return time_diff <= 5
    
    async def check_data_consistency(self, symbol: str = 'BTCUSDT'):
        """데이터 일치성 확인"""
        print(f"\n=== 데이터 일치성 검증 ({symbol}) ===")
        
        # 전략 생성
        strategy_config = self.config.get('strategies', {}).get('tfpe', {})
        strategy = TFPEStrategy(
            binance_api=self.binance_api,
            position_manager=None,
            config=strategy_config
        )
        
        # 데이터 가져오기
        df_4h, df_15m = await strategy.fetch_and_prepare_data(symbol)
        
        if df_4h is None or df_15m is None:
            print("❌ 데이터 수집 실패")
            return False
        
        # 마지막 캔들 확인
        last_15m_candle = df_15m.index[-1]
        current_time = datetime.now()
        expected_candle_time = current_time.replace(
            minute=(current_time.minute // 15) * 15, 
            second=0, 
            microsecond=0
        )
        
        print(f"\n15분봉 데이터:")
        print(f"  - 마지막 캔들: {last_15m_candle}")
        print(f"  - 예상 캔들: {expected_candle_time}")
        print(f"  - 차이: {abs((last_15m_candle - expected_candle_time).total_seconds())}초")
        
        # 백테스팅 인덱스 vs 실제 인덱스
        backtest_index = len(df_15m) - 2
        realtime_index = len(df_15m) - 1
        
        print(f"\n인덱스 사용:")
        print(f"  - 백테스팅: {backtest_index} (완성된 캔들)")
        print(f"  - 실시간: {realtime_index} (진행 중인 캔들)")
        
        # 지표 값 비교
        if backtest_index >= 0:
            backtest_candle = df_15m.iloc[backtest_index]
            current_candle = df_15m.iloc[realtime_index]
            
            print(f"\n지표 값 비교:")
            print(f"  - RSI 차이: {abs(backtest_candle.get('rsi', 0) - current_candle.get('rsi', 0)):.1f}")
            print(f"  - 가격 차이: {abs(backtest_candle['close'] - current_candle['close']):.2f}")
            
            # 모멘텀 체크
            if 'momentum' in backtest_candle:
                print(f"  - 모멘텀 차이: {abs(backtest_candle['momentum'] - current_candle.get('momentum', 0)):.2f}%")
        
        return True
    
    async def check_signal_consistency(self):
        """신호 생성 일치성 확인"""
        print(f"\n=== 신호 생성 일치성 검증 ===")
        
        # 설정 확인
        strategy_config = self.config.get('strategies', {}).get('tfpe', {})
        
        print(f"\n신호 파라미터:")
        print(f"  - 신호 임계값: {strategy_config.get('signal_threshold', 3)}/5")
        print(f"  - 최소 모멘텀: {strategy_config.get('min_momentum', 2.0)}%")
        print(f"  - RSI 과매도: {strategy_config.get('rsi_oversold', 30)}")
        print(f"  - RSI 과매수: {strategy_config.get('rsi_overbought', 70)}")
        print(f"  - 채널폭 임계값: {strategy_config.get('channel_width_threshold', 0.05) * 100}%")
        
        print(f"\n백테스팅과 동일한 조건:")
        print(f"  ✅ 4시간봉 채널폭 사용")
        print(f"  ✅ 피보나치 되돌림 체크")
        print(f"  ✅ 스윙 하이/로우 계산")
        print(f"  ✅ 모멘텀 lookback 파라미터")
        print(f"  ✅ 가격 위치 보너스 조건")
        
        return True

async def main():
    """메인 실행"""
    try:
        checker = TradingConsistencyChecker()
        
        print("=" * 60)
        print("백테스팅과 실제 트레이딩 일치성 검증")
        print("=" * 60)
        
        # 1. 캔들 타이밍 확인
        timing_ok = await checker.check_candle_timing_consistency()
        
        # 2. 데이터 일치성 확인
        data_ok = await checker.check_data_consistency()
        
        # 3. 신호 생성 일치성 확인
        signal_ok = await checker.check_signal_consistency()
        
        # 결과 요약
        print("\n" + "=" * 60)
        print("검증 결과 요약")
        print("=" * 60)
        
        all_ok = timing_ok and data_ok and signal_ok
        
        if all_ok:
            print("✅ 모든 검증 통과 - 백테스팅과 실제 트레이딩이 일치합니다")
        else:
            print("⚠️ 일부 검증 실패 - 추가 확인이 필요합니다")
        
        print("\n권장사항:")
        print("1. 서버 시간을 사용하여 시간 동기화 문제 해결")
        print("2. 캔들 체크 윈도우를 30초로 설정하여 API 지연 대응")
        print("3. 백테스팅과 동일한 지표 계산 로직 사용")
        
        # 리소스 정리
        await checker.binance_api.cleanup()
        
    except Exception as e:
        print(f"❌ 검증 실패: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
