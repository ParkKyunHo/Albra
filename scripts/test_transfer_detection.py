#!/usr/bin/env python3
"""
MDD Manager 이체 감지 기능 테스트
"""

import asyncio
from datetime import datetime
from src.core.mdd_manager_improved import ImprovedMDDManager
from src.utils.logger import setup_logger

logger = setup_logger("test_transfer_detection")

async def test_transfer_detection():
    """이체 감지 기능 테스트"""
    
    # MDD Manager 초기화
    config = {
        'max_allowed_mdd': 40.0,
        'mdd_recovery_threshold': 15.0,
        'detect_transfers': True,
        'transfer_threshold_pct': 20.0,
    }
    
    mdd_manager = ImprovedMDDManager(config)
    
    print("=== MDD 이체 감지 테스트 ===\n")
    
    # 시나리오 1: 정상적인 자본 증가
    print("1. 정상적인 자본 증가 테스트")
    balance = 100.0
    for i in range(3):
        balance += 10
        mdd = mdd_manager.calculate_current_mdd(balance)
        print(f"   잔고: ${balance:.2f}, MDD: {mdd:.1f}%, Peak: ${mdd_manager.peak_capital:.2f}")
        await asyncio.sleep(0.1)
    
    print("\n2. 정상적인 손실 테스트")
    # 시나리오 2: 정상적인 손실 (천천히)
    for i in range(3):
        balance -= 5
        mdd = mdd_manager.calculate_current_mdd(balance)
        print(f"   잔고: ${balance:.2f}, MDD: {mdd:.1f}%, Peak: ${mdd_manager.peak_capital:.2f}")
        await asyncio.sleep(0.1)
    
    print("\n3. 급격한 자본 감소 (이체 시뮬레이션)")
    # 시나리오 3: 급격한 자본 감소 (이체)
    original_balance = balance
    balance *= 0.5  # 50% 감소
    print(f"   이체 전: ${original_balance:.2f}")
    print(f"   이체 후: ${balance:.2f}")
    
    # 이체 감지 확인
    mdd = mdd_manager.calculate_current_mdd(balance)
    print(f"   MDD: {mdd:.1f}%, Peak: ${mdd_manager.peak_capital:.2f}")
    
    if mdd < 10:  # 이체가 감지되어 MDD가 재설정됨
        print("   ✅ 이체 감지 성공! MDD가 재설정되었습니다.")
    else:
        print("   ❌ 이체 감지 실패. MDD가 높게 유지됩니다.")
    
    print("\n4. 이체 후 정상 거래")
    # 시나리오 4: 이체 후 정상 거래
    for i in range(3):
        balance += 2
        mdd = mdd_manager.calculate_current_mdd(balance)
        print(f"   잔고: ${balance:.2f}, MDD: {mdd:.1f}%, Peak: ${mdd_manager.peak_capital:.2f}")
        await asyncio.sleep(0.1)
    
    print("\n=== 테스트 완료 ===")

if __name__ == "__main__":
    asyncio.run(test_transfer_detection())
