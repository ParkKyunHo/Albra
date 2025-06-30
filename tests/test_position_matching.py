#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
포지션 매칭 로직 테스트
"""

import asyncio
from datetime import datetime, timedelta
import sys
import os

# 프로젝트 루트 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.position_manager import PositionManager, Position, PositionStatus

class MockBinanceAPI:
    """테스트용 Mock Binance API"""
    async def get_positions(self):
        return []
    
    async def get_account_balance(self):
        return 1000.0

class MockStateManager:
    """테스트용 Mock State Manager"""
    async def load_position_cache(self):
        return {}
    
    async def save_position_cache(self, data):
        pass
    
    async def load_system_state(self):
        return {}

async def test_position_matching():
    """포지션 매칭 로직 테스트"""
    print("=" * 60)
    print("포지션 매칭 로직 테스트")
    print("=" * 60)
    
    # Mock 객체 생성
    binance_api = MockBinanceAPI()
    state_manager = MockStateManager()
    
    # PositionManager 생성
    pm = PositionManager(binance_api, state_manager)
    await pm.initialize()
    
    # 1. 시스템 포지션 추가 (전략이 생성)
    print("\n1. 시스템 포지션 추가 시뮬레이션")
    position = await pm.add_position(
        symbol="BTCUSDT",
        side="SHORT",
        size=0.001,
        entry_price=107658.10,
        leverage=10,
        strategy_name="TFPE"
    )
    
    if position:
        print(f"   - 포지션 ID: {position.position_id}")
        print(f"   - 생성 시간: {position.created_at}")
        print(f"   - 진입가: ${position.entry_price}")
    
    # 2. 거래소에서 조회된 포지션 (슬리피지 발생)
    print("\n2. 거래소 포지션 시뮬레이션 (슬리피지)")
    exchange_position = {
        'symbol': 'BTCUSDT',
        'positionAmt': '-0.001',  # 음수 = SHORT
        'entryPrice': '107659.90',  # 슬리피지로 인한 가격 차이
        'leverage': '10',
        'positionSide': 'BOTH'
    }
    
    # 3. 시스템 포지션 매칭 테스트
    print("\n3. 개선된 매칭 로직 테스트")
    
    # 포지션 방향 변환
    side = pm._convert_binance_side(exchange_position)
    print(f"   - 변환된 방향: {side}")
    
    # 새로운 ID 생성 (시간이 다름)
    new_id = pm._generate_position_id(
        'BTCUSDT', 
        side, 
        float(exchange_position['entryPrice'])
    )
    print(f"   - 새로 생성된 ID: {new_id}")
    print(f"   - 기존 시스템 ID에 있나?: {new_id in pm.system_position_ids}")
    
    # 개선된 매칭 로직 테스트
    is_system = await pm._is_system_position_improved(
        symbol='BTCUSDT',
        side=side,
        size=0.001,
        entry_price=float(exchange_position['entryPrice']),
        position_id=new_id
    )
    
    print(f"\n4. 매칭 결과: {'시스템 포지션' if is_system else '수동 포지션'}")
    
    if is_system:
        print("   ✅ 성공: 슬리피지와 시간 차이에도 불구하고 시스템 포지션으로 인식됨")
    else:
        print("   ❌ 실패: 수동 포지션으로 잘못 인식됨")
    
    # 5. 극단적인 케이스 테스트
    print("\n5. 극단적인 케이스 테스트")
    
    # 5-1. 큰 가격 차이 (0.5%)
    print("\n   5-1. 큰 가격 차이 테스트 (0.5%)")
    is_system_large_diff = await pm._is_system_position_improved(
        symbol='BTCUSDT',
        side='SHORT',
        size=0.001,
        entry_price=108200.00,  # 0.5% 차이
        position_id='test_id_1'
    )
    print(f"   결과: {'시스템' if is_system_large_diff else '수동'} (예상: 수동)")
    
    # 5-2. 오래된 포지션 (10분 후)
    print("\n   5-2. 오래된 포지션 테스트")
    # 포지션 생성 시간을 10분 전으로 변경
    old_position = pm.positions.get('BTCUSDT')
    if old_position:
        old_time = datetime.now() - timedelta(minutes=10)
        old_position.created_at = old_time.isoformat()
        
        is_system_old = await pm._is_system_position_improved(
            symbol='BTCUSDT',
            side='SHORT',
            size=0.001,
            entry_price=107659.00,
            position_id='test_id_2'
        )
        print(f"   결과: {'시스템' if is_system_old else '수동'} (예상: 수동)")
    
    print("\n테스트 완료!")

if __name__ == "__main__":
    asyncio.run(test_position_matching())
