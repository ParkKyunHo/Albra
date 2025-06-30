# src/utils/telegram_commands_phase2_fix.py
"""
텔레그램 명령어 처리 보조 모듈 - 멀티계좌 상태 수정
"""

import logging
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class MultiAccountStatusHelper:
    """멀티계좌 상태 헬퍼"""
    
    def __init__(self, trading_system):
        self.trading_system = trading_system
        
    async def get_account_status(self) -> Dict:
        """계좌 상태 조회 (멀티계좌 지원)"""
        try:
            # 멀티계좌 모드 확인
            config = self.trading_system.config
            multi_account_config = config.get('multi_account', {})
            
            # 멀티계좌 활성화 상태 확인
            is_multi_enabled = (
                multi_account_config.get('enabled', False) and 
                multi_account_config.get('mode', 'single') == 'multi'
            )
            
            result = {
                'multi_enabled': is_multi_enabled,
                'accounts': {},
                'total_balance': 0,
                'total_positions': 0
            }
            
            # 마스터 계좌 정보
            master_balance = await self.trading_system.binance_api.get_account_balance()
            result['accounts']['MASTER'] = {
                'balance': master_balance,
                'positions': []
            }
            result['total_balance'] += master_balance
            
            # 서브계좌 정보 (멀티계좌 모드인 경우)
            if is_multi_enabled:
                sub_accounts = multi_account_config.get('sub_accounts', {})
                
                for account_id, account_config in sub_accounts.items():
                    if account_config.get('enabled', False):
                        # 서브계좌 API 객체가 있다면 사용
                        # 현재는 더미 데이터 (실제 구현 시 서브계좌 API 필요)
                        result['accounts'][account_id] = {
                            'balance': 0,  # TODO: 실제 서브계좌 잔고 조회
                            'positions': [],
                            'strategy': account_config.get('strategy', 'N/A'),
                            'status': 'ACTIVE'
                        }
            
            # 포지션 정보 업데이트
            positions = self.trading_system.position_manager.get_active_positions()
            for pos in positions:
                # 포지션을 적절한 계좌에 할당
                account_key = 'MASTER'  # 기본값
                
                # 전략에 따른 계좌 매핑 (실제 구현 시 수정 필요)
                if pos.strategy_name and is_multi_enabled:
                    for acc_id, acc_config in sub_accounts.items():
                        if acc_config.get('strategy') == pos.strategy_name:
                            account_key = acc_id
                            break
                
                if account_key in result['accounts']:
                    result['accounts'][account_key]['positions'].append({
                        'symbol': pos.symbol,
                        'side': pos.side,
                        'size': pos.size,
                        'entry_price': pos.entry_price,
                        'strategy': pos.strategy_name
                    })
                
                result['total_positions'] += 1
            
            return result
            
        except Exception as e:
            logger.error(f"계좌 상태 조회 실패: {e}")
            return {
                'multi_enabled': False,
                'accounts': {},
                'error': str(e)
            }
    
    async def fix_position_recognition(self) -> Dict:
        """포지션 인식 문제 수정"""
        try:
            # 시스템 포지션 ID 재로드
            self.trading_system.position_manager._load_system_positions()
            
            # 강제 동기화
            sync_report = await self.trading_system.position_manager.sync_positions()
            
            # 포지션 재분류
            fixed_count = 0
            for key, position in self.trading_system.position_manager.positions.items():
                if position.is_manual and position.position_id in self.trading_system.position_manager.system_position_ids:
                    # 잘못 분류된 시스템 포지션 수정
                    position.is_manual = False
                    position.source = 'AUTO'
                    fixed_count += 1
                    logger.info(f"포지션 재분류: {position.symbol} - 수동 → 시스템")
            
            # 캐시 저장
            await self.trading_system.position_manager._save_positions_batch()
            
            return {
                'success': True,
                'fixed_positions': fixed_count,
                'sync_report': sync_report
            }
            
        except Exception as e:
            logger.error(f"포지션 인식 수정 실패: {e}")
            return {
                'success': False,
                'error': str(e)
            }
