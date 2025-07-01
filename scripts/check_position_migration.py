#!/usr/bin/env python3
"""
Position Key Migration Status Checker
포지션 키 마이그레이션 상태 확인 및 자동 마이그레이션
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.position_key_manager import PositionKeyManager
from src.core.state_manager import StateManager
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class PositionMigrationChecker:
    """포지션 마이그레이션 체커"""
    
    def __init__(self):
        self.state_manager = StateManager()
        self.legacy_positions = []
        self.migrated_positions = []
        self.migration_needed = []
        
    async def check_migration_status(self) -> Tuple[List[str], List[str], List[Tuple[str, Dict]]]:
        """마이그레이션 상태 확인
        
        Returns:
            (레거시 키 목록, 마이그레이션된 키 목록, 마이그레이션 필요 목록)
        """
        logger.info("=" * 60)
        logger.info("포지션 키 마이그레이션 상태 확인")
        logger.info("=" * 60)
        
        # 캐시된 포지션 로드
        try:
            cached_positions = await self.state_manager.load_position_cache()
        except Exception as e:
            logger.error(f"포지션 캐시 로드 실패: {e}")
            return [], [], []
        
        # 키 분류
        for key, position_data in cached_positions.items():
            if PositionKeyManager.is_legacy_key(key):
                self.legacy_positions.append(key)
                self.migration_needed.append((key, position_data))
            else:
                self.migrated_positions.append(key)
        
        # 상태 출력
        logger.info(f"📊 현재 상태:")
        logger.info(f"- 전체 포지션: {len(cached_positions)}개")
        logger.info(f"- 레거시 키 (마이그레이션 필요): {len(self.legacy_positions)}개")
        logger.info(f"- 신규 키 (마이그레이션 완료): {len(self.migrated_positions)}개")
        
        if self.legacy_positions:
            logger.info("\n🔍 레거시 포지션 상세:")
            for key in self.legacy_positions:
                position_data = cached_positions[key]
                strategy = position_data.get('strategy_name', 'N/A')
                is_manual = position_data.get('is_manual', False)
                logger.info(f"  - {key}: strategy={strategy}, is_manual={is_manual}")
        
        return self.legacy_positions, self.migrated_positions, self.migration_needed
    
    async def migrate_positions(self, dry_run: bool = True) -> bool:
        """포지션 마이그레이션 실행
        
        Args:
            dry_run: True인 경우 실제 마이그레이션 하지 않고 시뮬레이션만
            
        Returns:
            성공 여부
        """
        if not self.migration_needed:
            logger.info("✅ 마이그레이션할 포지션이 없습니다.")
            return True
        
        logger.info(f"\n{'🔍 마이그레이션 시뮬레이션' if dry_run else '🚀 마이그레이션 실행'}")
        logger.info("=" * 60)
        
        migration_plan = {}
        
        # 마이그레이션 계획 생성
        for legacy_key, position_data in self.migration_needed:
            new_key = PositionKeyManager.migrate_key(legacy_key, position_data)
            migration_plan[legacy_key] = new_key
            
            logger.info(f"  {legacy_key} → {new_key}")
            
            # 중복 키 확인
            if new_key in self.migrated_positions:
                logger.warning(f"    ⚠️ 경고: 대상 키가 이미 존재합니다!")
        
        if dry_run:
            logger.info("\n✅ 시뮬레이션 완료. 실제 마이그레이션은 수행되지 않았습니다.")
            return True
        
        # 실제 마이그레이션 실행
        logger.info("\n📝 마이그레이션 실행 중...")
        
        try:
            # 현재 캐시 로드
            cached_positions = await self.state_manager.load_position_cache()
            
            # 백업 생성
            backup_path = f"state/position_cache_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(backup_path, 'w') as f:
                json.dump(cached_positions, f, indent=2)
            logger.info(f"✅ 백업 생성: {backup_path}")
            
            # 마이그레이션 수행
            migrated_count = 0
            for legacy_key, new_key in migration_plan.items():
                if legacy_key in cached_positions:
                    # 데이터 복사
                    position_data = cached_positions[legacy_key].copy()
                    
                    # 새 키로 저장
                    cached_positions[new_key] = position_data
                    
                    # 기존 키 삭제
                    del cached_positions[legacy_key]
                    
                    migrated_count += 1
                    logger.info(f"  ✅ {legacy_key} → {new_key}")
            
            # 캐시 저장
            await self.state_manager.save_position_cache(cached_positions)
            
            logger.info(f"\n✅ 마이그레이션 완료: {migrated_count}개 포지션")
            return True
            
        except Exception as e:
            logger.error(f"❌ 마이그레이션 실패: {e}")
            return False
    
    def print_summary(self):
        """요약 정보 출력"""
        print("\n" + "=" * 60)
        print("📊 마이그레이션 요약")
        print("=" * 60)
        
        # 심볼별 그룹핑
        if self.migrated_positions:
            grouped_by_symbol = PositionKeyManager.group_by_symbol(self.migrated_positions)
            print("\n📈 심볼별 전략 분포:")
            for symbol, strategies in grouped_by_symbol.items():
                print(f"  {symbol}: {', '.join(strategies)}")
        
        # 전략별 그룹핑
        if self.migrated_positions:
            grouped_by_strategy = PositionKeyManager.group_by_strategy(self.migrated_positions)
            print("\n🎯 전략별 심볼 분포:")
            for strategy, symbols in grouped_by_strategy.items():
                print(f"  {strategy}: {', '.join(symbols)}")
        
        print("\n" + "=" * 60)


async def main():
    """메인 함수"""
    checker = PositionMigrationChecker()
    
    # 상태 확인
    legacy, migrated, needed = await checker.check_migration_status()
    
    # 요약 출력
    checker.print_summary()
    
    # 마이그레이션 필요 여부 확인
    if needed:
        print("\n⚠️ 레거시 포지션이 발견되었습니다.")
        print("마이그레이션을 수행하시겠습니까?")
        print("1. 시뮬레이션만 실행 (dry run)")
        print("2. 실제 마이그레이션 실행")
        print("3. 취소")
        
        choice = input("\n선택 [1-3]: ").strip()
        
        if choice == '1':
            await checker.migrate_positions(dry_run=True)
        elif choice == '2':
            confirm = input("\n⚠️ 실제로 마이그레이션을 수행합니다. 계속하시겠습니까? (yes/no): ")
            if confirm.lower() == 'yes':
                success = await checker.migrate_positions(dry_run=False)
                if success:
                    print("\n✅ 마이그레이션이 성공적으로 완료되었습니다!")
                else:
                    print("\n❌ 마이그레이션 중 오류가 발생했습니다.")
        else:
            print("\n취소되었습니다.")
    else:
        print("\n✅ 모든 포지션이 이미 마이그레이션되었습니다!")


if __name__ == "__main__":
    asyncio.run(main())