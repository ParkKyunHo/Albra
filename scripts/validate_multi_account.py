#!/usr/bin/env python3
# scripts/validate_multi_account.py
"""
Multi-Account Configuration Validator
멀티 계좌 설정 검증 및 API 연결 테스트
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple
import json

# 프로젝트 루트 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.config_manager import ConfigManager
from src.core.binance_api import BinanceAPI
from src.utils.logger import setup_logger
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

logger = setup_logger(__name__)


class MultiAccountValidator:
    """멀티 계좌 설정 검증기"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.config = self.config_manager.config
        self.validation_results = {
            'timestamp': datetime.now().isoformat(),
            'errors': [],
            'warnings': [],
            'info': [],
            'accounts': {}
        }
    
    async def validate_all(self) -> Dict:
        """전체 검증 실행"""
        logger.info("=" * 60)
        logger.info("멀티 계좌 설정 검증 시작")
        logger.info("=" * 60)
        
        # 1. 설정 파일 검증
        self._validate_config()
        
        # 2. 환경변수 검증
        self._validate_env_vars()
        
        # 3. API 연결 테스트
        await self._test_api_connections()
        
        # 4. 권한 검증
        await self._validate_permissions()
        
        # 5. 결과 요약
        self._print_summary()
        
        return self.validation_results
    
    def _validate_config(self):
        """설정 파일 검증"""
        logger.info("\n📋 설정 파일 검증")
        
        # multi_account 섹션 확인
        multi_config = self.config.get('multi_account')
        if not multi_config:
            self.validation_results['errors'].append("multi_account 설정이 없습니다")
            return
        
        # 활성화 상태 확인
        if not multi_config.get('enabled', False):
            self.validation_results['warnings'].append("멀티 계좌가 비활성화되어 있습니다")
        
        # 서브 계좌 확인
        sub_accounts = multi_config.get('sub_accounts', {})
        if not sub_accounts:
            self.validation_results['warnings'].append("서브 계좌가 설정되지 않았습니다")
        else:
            for account_id, account_config in sub_accounts.items():
                self._validate_account_config(account_id, account_config)
        
        logger.info("✓ 설정 파일 검증 완료")
    
    def _validate_account_config(self, account_id: str, config: Dict):
        """개별 계좌 설정 검증"""
        required_fields = ['type', 'strategy', 'leverage', 'position_size', 'symbols']
        
        for field in required_fields:
            if field not in config:
                self.validation_results['errors'].append(
                    f"{account_id}: 필수 필드 누락 - {field}"
                )
        
        # 레버리지 범위 확인
        leverage = config.get('leverage', 0)
        if leverage < 1 or leverage > 125:
            self.validation_results['warnings'].append(
                f"{account_id}: 잘못된 레버리지 값 ({leverage})"
            )
        
        # 포지션 크기 확인
        position_size = config.get('position_size', 0)
        if position_size <= 0 or position_size > 100:
            self.validation_results['warnings'].append(
                f"{account_id}: 잘못된 포지션 크기 ({position_size}%)"
            )
    
    def _validate_env_vars(self):
        """환경변수 검증"""
        logger.info("\n🔑 환경변수 검증")
        
        # 마스터 계좌 API 키
        master_key = os.getenv('BINANCE_API_KEY')
        master_secret = os.getenv('BINANCE_SECRET_KEY')
        
        if not master_key or not master_secret:
            self.validation_results['errors'].append("마스터 계좌 API 키가 설정되지 않았습니다")
        else:
            self.validation_results['info'].append("✓ 마스터 계좌 API 키 확인")
        
        # 서브 계좌 API 키
        sub_accounts = self.config.get('multi_account', {}).get('sub_accounts', {})
        for account_id in sub_accounts:
            key_name = f"{account_id.upper()}_API_KEY"
            secret_name = f"{account_id.upper()}_API_SECRET"
            
            if not os.getenv(key_name) or not os.getenv(secret_name):
                self.validation_results['warnings'].append(
                    f"{account_id}: API 키가 설정되지 않았습니다"
                )
            else:
                self.validation_results['info'].append(f"✓ {account_id} API 키 확인")
        
        logger.info("✓ 환경변수 검증 완료")
    
    async def _test_api_connections(self):
        """API 연결 테스트"""
        logger.info("\n🔌 API 연결 테스트")
        
        testnet = self.config.get('system', {}).get('mode') == 'testnet'
        
        # 마스터 계좌 테스트
        await self._test_single_api_connection(
            'MASTER',
            os.getenv('BINANCE_API_KEY'),
            os.getenv('BINANCE_SECRET_KEY'),
            testnet
        )
        
        # 서브 계좌 테스트
        sub_accounts = self.config.get('multi_account', {}).get('sub_accounts', {})
        for account_id in sub_accounts:
            api_key = os.getenv(f"{account_id.upper()}_API_KEY")
            api_secret = os.getenv(f"{account_id.upper()}_API_SECRET")
            
            if api_key and api_secret:
                await self._test_single_api_connection(
                    account_id, api_key, api_secret, testnet
                )
    
    async def _test_single_api_connection(self, account_id: str, api_key: str, 
                                        api_secret: str, testnet: bool):
        """단일 API 연결 테스트"""
        try:
            logger.info(f"\n  {account_id} 연결 테스트 중...")
            
            api = BinanceAPI(api_key=api_key, secret_key=api_secret, testnet=testnet)
            
            # 연결 테스트
            if await api.initialize():
                # 계좌 정보 조회
                balance = await api.get_account_balance()
                
                # 포지션 모드 확인
                position_mode = await api.get_position_mode()
                
                account_info = {
                    'status': 'connected',
                    'balance': balance,
                    'position_mode': position_mode,
                    'testnet': testnet
                }
                
                self.validation_results['accounts'][account_id] = account_info
                self.validation_results['info'].append(
                    f"✓ {account_id}: 연결 성공 (잔고: ${balance:.2f}, 모드: {position_mode})"
                )
                
                # 정리
                await api.cleanup()
                
            else:
                self.validation_results['errors'].append(f"{account_id}: API 연결 실패")
                
        except Exception as e:
            self.validation_results['errors'].append(f"{account_id}: API 테스트 중 오류 - {str(e)}")
    
    async def _validate_permissions(self):
        """API 권한 검증"""
        logger.info("\n🔐 권한 검증")
        
        # TODO: 향후 구현
        # - Futures 거래 권한
        # - 서브 계좌 관리 권한 (마스터)
        # - IP 제한 설정 확인
        
        self.validation_results['info'].append("권한 검증은 Phase 2에서 구현 예정")
    
    def _print_summary(self):
        """검증 결과 요약 출력"""
        logger.info("\n" + "=" * 60)
        logger.info("📊 검증 결과 요약")
        logger.info("=" * 60)
        
        # 오류
        if self.validation_results['errors']:
            logger.error(f"\n❌ 오류 ({len(self.validation_results['errors'])}개):")
            for error in self.validation_results['errors']:
                logger.error(f"  - {error}")
        
        # 경고
        if self.validation_results['warnings']:
            logger.warning(f"\n⚠️  경고 ({len(self.validation_results['warnings'])}개):")
            for warning in self.validation_results['warnings']:
                logger.warning(f"  - {warning}")
        
        # 정보
        if self.validation_results['info']:
            logger.info(f"\n✅ 정보 ({len(self.validation_results['info'])}개):")
            for info in self.validation_results['info']:
                logger.info(f"  - {info}")
        
        # 계좌 상태
        if self.validation_results['accounts']:
            logger.info("\n📈 계좌 상태:")
            for account_id, info in self.validation_results['accounts'].items():
                logger.info(f"  - {account_id}: {info['status']}")
                if info['status'] == 'connected':
                    logger.info(f"    잔고: ${info['balance']:.2f}")
                    logger.info(f"    포지션 모드: {info['position_mode']}")
        
        # 최종 판정
        logger.info("\n" + "=" * 60)
        if not self.validation_results['errors']:
            logger.info("✅ 검증 통과 - 멀티 계좌 시스템을 사용할 수 있습니다")
        else:
            logger.error("❌ 검증 실패 - 오류를 수정한 후 다시 시도하세요")
        logger.info("=" * 60)
    
    def save_results(self, filename: str = "validation_results.json"):
        """검증 결과 저장"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.validation_results, f, indent=2, ensure_ascii=False)
            logger.info(f"\n검증 결과가 {filename}에 저장되었습니다")
        except Exception as e:
            logger.error(f"결과 저장 실패: {e}")


async def main():
    """메인 함수"""
    validator = MultiAccountValidator()
    
    try:
        results = await validator.validate_all()
        
        # 결과 저장
        validator.save_results()
        
        # 종료 코드 반환
        if results['errors']:
            sys.exit(1)
        else:
            sys.exit(0)
            
    except Exception as e:
        logger.error(f"검증 중 오류 발생: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
