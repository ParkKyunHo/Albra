#!/usr/bin/env python3
"""
ZLHMA EMA Cross 전략 빠른 테스트 스크립트
실전 배포 전 검증용
"""

import asyncio
import sys
import os
from datetime import datetime

# 프로젝트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.logger import setup_logger
from src.strategies.strategy_factory import get_strategy_factory

logger = setup_logger(__name__)


async def test_strategy_registration():
    """전략 등록 테스트"""
    print("\n1. 전략 등록 테스트")
    print("-" * 50)
    
    factory = get_strategy_factory()
    available = factory.get_available_strategies()
    
    print(f"사용 가능한 전략: {available}")
    
    if 'ZLHMA_EMA_CROSS' in available:
        print("✅ ZLHMA_EMA_CROSS 전략이 성공적으로 등록되었습니다!")
    else:
        print("❌ ZLHMA_EMA_CROSS 전략 등록 실패!")
        return False
    
    # 전략 정보 확인
    info = factory.get_strategy_info('ZLHMA_EMA_CROSS')
    print(f"\n전략 정보:")
    print(f"  - 설명: {info.get('description', 'N/A')}")
    print(f"  - 지표: ZLHMA({info.get('indicators', {}).get('zlhma_period', 14)}), "
          f"EMA({info.get('indicators', {}).get('fast_ema', 50)}/{info.get('indicators', {}).get('slow_ema', 200)})")
    print(f"  - ADX 임계값: {info.get('indicators', {}).get('adx_threshold', 25)}")
    
    return True


async def test_strategy_validation():
    """전략 검증 테스트"""
    print("\n2. 전략 설정 검증")
    print("-" * 50)
    
    factory = get_strategy_factory()
    result = factory.validate_strategy('ZLHMA_EMA_CROSS')
    
    print(f"검증 결과: {'✅ 통과' if result['valid'] else '❌ 실패'}")
    
    if result['errors']:
        print("\n오류:")
        for error in result['errors']:
            print(f"  - {error}")
    
    if result['warnings']:
        print("\n경고:")
        for warning in result['warnings']:
            print(f"  - {warning}")
    
    return result['valid']


async def test_strategy_creation():
    """전략 생성 테스트"""
    print("\n3. 전략 인스턴스 생성 테스트")
    print("-" * 50)
    
    # Mock 객체 생성 (실제 API 연결 없이)
    class MockAPI:
        async def get_klines(self, symbol, interval, limit):
            return []
    
    class MockPositionManager:
        def get_position(self, symbol):
            return None
    
    try:
        factory = get_strategy_factory()
        
        # 테스트 설정으로 전략 생성
        test_config = {
            'enabled': True,
            'leverage': 5,
            'position_size': 10,
            'zlhma_period': 14,
            'fast_ema_period': 50,
            'slow_ema_period': 200,
            'adx_threshold': 25,
            'symbols': ['BTCUSDT']
        }
        
        strategy = factory.create_strategy(
            name='ZLHMA_EMA_CROSS',
            binance_api=MockAPI(),
            position_manager=MockPositionManager(),
            custom_config=test_config
        )
        
        if strategy:
            print("✅ 전략 인스턴스 생성 성공!")
            
            # 전략 정보 확인
            info = strategy.get_strategy_info()
            print(f"\n전략 상태:")
            print(f"  - 이름: {info['name']}")
            print(f"  - 활성 심볼: {info.get('active_symbols', [])}")
            print(f"  - 파라미터: {info.get('parameters', {})}")
            
            return True
        else:
            print("❌ 전략 인스턴스 생성 실패!")
            return False
            
    except Exception as e:
        print(f"❌ 전략 생성 중 오류: {e}")
        import traceback
        traceback.print_exc()
        return False


async def check_config_status():
    """설정 파일 상태 확인"""
    print("\n4. 설정 파일 상태")
    print("-" * 50)
    
    from src.utils.config_manager import ConfigManager
    
    config_manager = ConfigManager()
    config = config_manager.config
    
    # ZLHMA 전략 설정 확인
    zlhma_config = config.get('strategies', {}).get('zlhma_ema_cross', {})
    
    if zlhma_config:
        print("✅ ZLHMA EMA Cross 전략 설정 발견!")
        print(f"  - 활성화: {zlhma_config.get('enabled', False)}")
        print(f"  - 레버리지: {zlhma_config.get('leverage', 'N/A')}")
        print(f"  - 포지션 크기: {zlhma_config.get('position_size', 'N/A')}%")
        print(f"  - 심볼: {zlhma_config.get('symbols', [])}")
    else:
        print("❌ ZLHMA EMA Cross 전략 설정을 찾을 수 없습니다!")
        return False
    
    # 멀티 계좌 설정 확인
    multi_config = config.get('multi_account', {})
    print(f"\n멀티 계좌 설정:")
    print(f"  - 활성화: {multi_config.get('enabled', False)}")
    
    if multi_config.get('sub_accounts', {}).get('test_account_1', {}).get('strategy') == 'ZLHMA_EMA_CROSS':
        print("  - 서브 계좌가 ZLHMA 전략 사용 예정")
    
    return True


async def main():
    """메인 테스트 실행"""
    print("=" * 60)
    print("ZLHMA EMA Cross 전략 통합 테스트")
    print(f"실행 시간: {datetime.now()}")
    print("=" * 60)
    
    all_passed = True
    
    # 1. 전략 등록 테스트
    if not await test_strategy_registration():
        all_passed = False
    
    # 2. 전략 검증 테스트
    if not await test_strategy_validation():
        all_passed = False
    
    # 3. 전략 생성 테스트
    if not await test_strategy_creation():
        all_passed = False
    
    # 4. 설정 파일 확인
    if not await check_config_status():
        all_passed = False
    
    # 최종 결과
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ 모든 테스트 통과! 배포 준비 완료")
        print("\n다음 단계:")
        print("1. 드라이런 테스트: python src/main.py --strategies ZLHMA_EMA_CROSS --dry-run")
        print("2. config.yaml에서 enabled: true로 변경")
        print("3. 실전 운영 시작")
    else:
        print("❌ 일부 테스트 실패. 문제를 해결하고 다시 실행하세요.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
