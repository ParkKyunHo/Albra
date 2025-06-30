#!/usr/bin/env python3
"""
MDD Peak Capital 재설정 스크립트
계좌 이체 후 MDD를 재설정하기 위한 유틸리티
"""

import asyncio
import sys
import os
from datetime import datetime
from dotenv import load_dotenv

# 프로젝트 루트 경로 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

# .env 파일 로드 (프로젝트 루트에서)
env_path = os.path.join(project_root, '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
    print(f"Loaded .env from: {env_path}")
else:
    print(f"Warning: .env file not found at {env_path}")

from src.core.binance_api import BinanceAPI
from src.core.mdd_manager_improved import ImprovedMDDManager
from src.utils.logger import setup_logger

logger = setup_logger("reset_mdd")

async def reset_mdd_peak():
    """MDD Peak Capital을 현재 잔고로 재설정"""
    try:
        # 1. 바이낸스 API 초기화
        # 환경 변수 이름 확인 (BINANCE_API_SECRET 또는 BINANCE_SECRET_KEY)
        api_key = os.getenv('BINANCE_API_KEY')
        api_secret = os.getenv('BINANCE_API_SECRET') or os.getenv('BINANCE_SECRET_KEY')
        testnet = os.getenv('TESTNET', 'False').lower() == 'true'
        
        if not api_key:
            logger.error("BINANCE_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
            return
            
        if not api_secret:
            logger.error("BINANCE_API_SECRET 또는 BINANCE_SECRET_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
            return
        
        binance_api = BinanceAPI(api_key, api_secret, testnet)
        await binance_api.initialize()
        
        # 2. 현재 잔고 조회
        current_balance = await binance_api.get_account_balance()
        logger.info(f"현재 계좌 잔고: ${current_balance:,.2f}")
        
        # 3. MDD Manager 초기화
        mdd_config = {
            'max_allowed_mdd': 40.0,
            'mdd_recovery_threshold': 15.0,
            'mdd_recovery_mode': True,
            'mdd_emergency_stop': 60.0,
        }
        
        mdd_manager = ImprovedMDDManager(mdd_config)
        
        # 4. 현재 MDD 상태 확인
        old_peak = mdd_manager.peak_capital
        old_mdd = mdd_manager.calculate_current_mdd(current_balance)
        
        logger.info(f"현재 Peak Capital: ${old_peak:,.2f}")
        logger.info(f"현재 MDD: {old_mdd:.1f}%")
        
        # 5. 사용자 확인
        print("\n" + "="*50)
        print("MDD Peak Capital 재설정")
        print("="*50)
        print(f"현재 Peak Capital: ${old_peak:,.2f}")
        print(f"현재 잔고: ${current_balance:,.2f}")
        print(f"현재 MDD: {old_mdd:.1f}%")
        print("="*50)
        
        response = input("\nPeak Capital을 현재 잔고로 재설정하시겠습니까? (y/n): ")
        
        if response.lower() != 'y':
            logger.info("사용자가 재설정을 취소했습니다.")
            return
        
        # 6. Peak Capital 재설정
        mdd_manager.reset_peak()
        new_mdd = mdd_manager.calculate_current_mdd(current_balance)
        
        logger.info(f"✅ Peak Capital이 ${current_balance:,.2f}로 재설정되었습니다.")
        logger.info(f"새로운 MDD: {new_mdd:.1f}%")
        
        # 7. 이벤트 기록
        await mdd_manager._record_mdd_event(
            'manual_reset',
            current_balance,
            f'사용자 요청에 의한 Peak Capital 재설정'
        )
        
        print(f"\n✅ Peak Capital이 성공적으로 재설정되었습니다!")
        print(f"   새로운 Peak: ${current_balance:,.2f}")
        print(f"   새로운 MDD: {new_mdd:.1f}%")
        
        # 8. 정리
        await binance_api.cleanup()
        
    except Exception as e:
        logger.error(f"MDD 재설정 실패: {e}")
        print(f"\n❌ 오류 발생: {e}")

if __name__ == "__main__":
    # 스크립트 실행
    asyncio.run(reset_mdd_peak())
