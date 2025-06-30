"""
Position Sync Monitor - 포지션 동기화 상태 모니터링
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional, Tuple
import logging

from src.core.event_logger import log_event
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class PositionSyncMonitor:
    """
    포지션 동기화 상태를 모니터링하고 불일치를 감지
    """
    
    def __init__(self, position_manager, binance_api, notification_manager=None):
        self.position_manager = position_manager
        self.binance_api = binance_api
        self.notification_manager = notification_manager
        
        # 모니터링 설정
        self.check_interval = 300  # 5분마다 체크
        self.mismatch_threshold = 2  # 2번 연속 불일치시 알림
        
        # 상태 추적
        self.last_check = None
        self.mismatch_count = 0
        self.last_known_state = {
            'exchange_positions': set(),
            'system_positions': set(),
            'manual_positions': set()
        }
        
        self._running = False
        self._monitor_task = None
    
    async def start(self):
        """모니터링 시작"""
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Position Sync Monitor 시작됨")
        
        # 시작시 즉시 체크
        await self.check_sync_status()
    
    async def stop(self):
        """모니터링 중지"""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
        logger.info("Position Sync Monitor 중지됨")
    
    async def _monitor_loop(self):
        """모니터링 루프"""
        while self._running:
            try:
                await asyncio.sleep(self.check_interval)
                await self.check_sync_status()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Sync monitor 오류: {e}")
                await asyncio.sleep(60)
    
    async def check_sync_status(self) -> Dict:
        """동기화 상태 체크"""
        try:
            # 거래소 포지션 조회
            exchange_positions = await self._get_exchange_positions()
            
            # 시스템 포지션 조회
            system_positions = self._get_system_positions()
            
            # 수동 포지션 조회
            manual_positions = self._get_manual_positions()
            
            # 불일치 검사
            sync_status = self._analyze_sync_status(
                exchange_positions, 
                system_positions, 
                manual_positions
            )
            
            # 이벤트 로깅
            await log_event(
                "POSITION_SYNC_CHECK",
                {
                    "exchange_count": len(exchange_positions),
                    "system_count": len(system_positions),
                    "manual_count": len(manual_positions),
                    "is_synced": sync_status['is_synced'],
                    "issues": sync_status['issues']
                },
                "INFO" if sync_status['is_synced'] else "WARNING"
            )
            
            # 불일치 처리
            if not sync_status['is_synced']:
                await self._handle_mismatch(sync_status)
            else:
                self.mismatch_count = 0  # 리셋
            
            # 상태 업데이트
            self.last_check = datetime.now()
            self.last_known_state = {
                'exchange_positions': exchange_positions,
                'system_positions': system_positions,
                'manual_positions': manual_positions
            }
            
            return sync_status
            
        except Exception as e:
            logger.error(f"Sync status check 실패: {e}")
            await log_event(
                "POSITION_SYNC_ERROR",
                {"error": str(e)},
                "ERROR"
            )
            return {'is_synced': False, 'error': str(e)}
    
    async def _get_exchange_positions(self) -> Set[str]:
        """거래소에서 실제 포지션 조회"""
        try:
            positions = await self.binance_api.get_positions()
            return {
                pos['symbol'] 
                for pos in positions 
                if float(pos.get('positionAmt', 0)) != 0
            }
        except Exception as e:
            logger.error(f"거래소 포지션 조회 실패: {e}")
            return set()
    
    def _get_system_positions(self) -> Set[str]:
        """시스템이 관리하는 포지션"""
        # ACTIVE 상태를 Enum으로 정확히 비교
        from src.core.position_manager import PositionStatus
        return {
            pos.symbol 
            for pos in self.position_manager.positions.values()
            if pos.status == PositionStatus.ACTIVE.value and not pos.is_manual
        }
    
    def _get_manual_positions(self) -> Set[str]:
        """수동 포지션"""
        from src.core.position_manager import PositionStatus
        return {
            pos.symbol 
            for pos in self.position_manager.positions.values()
            if pos.status == PositionStatus.ACTIVE.value and pos.is_manual
        }
    
    def _analyze_sync_status(self, 
                           exchange: Set[str], 
                           system: Set[str], 
                           manual: Set[str]) -> Dict:
        """동기화 상태 분석"""
        all_known = system | manual
        
        # 불일치 검사
        missing_from_system = exchange - all_known  # 거래소에만 있는 포지션
        extra_in_system = all_known - exchange      # 시스템에만 있는 포지션
        
        issues = []
        
        if missing_from_system:
            issues.append({
                'type': 'UNTRACKED_POSITIONS',
                'symbols': list(missing_from_system),
                'description': '거래소에 있지만 시스템이 추적하지 않는 포지션'
            })
        
        if extra_in_system:
            issues.append({
                'type': 'PHANTOM_POSITIONS',
                'symbols': list(extra_in_system),
                'description': '시스템에만 있고 거래소에 없는 포지션'
            })
        
        # 시스템/수동 분류 검증
        for symbol in exchange:
            if symbol in system and symbol in manual:
                issues.append({
                    'type': 'DUPLICATE_TRACKING',
                    'symbol': symbol,
                    'description': '시스템과 수동 모두에서 추적되는 포지션'
                })
        
        return {
            'is_synced': len(issues) == 0,
            'issues': issues,
            'stats': {
                'exchange': len(exchange),
                'system': len(system),
                'manual': len(manual),
                'total_known': len(all_known)
            }
        }
    
    async def _handle_mismatch(self, sync_status: Dict):
        """불일치 처리"""
        self.mismatch_count += 1
        
        # 연속 불일치 횟수 체크
        if self.mismatch_count >= self.mismatch_threshold:
            # 심각한 불일치 - 알림 전송
            await self._send_mismatch_alert(sync_status)
            
            # 자동 수정 시도 (안전한 경우만)
            await self._attempt_auto_fix(sync_status)
    
    async def _send_mismatch_alert(self, sync_status: Dict):
        """불일치 알림 전송"""
        if not self.notification_manager:
            return
        
        message = "⚠️ 포지션 동기화 불일치 감지\n\n"
        
        for issue in sync_status['issues']:
            if issue['type'] == 'UNTRACKED_POSITIONS':
                message += f"📍 추적되지 않는 포지션:\n"
                for symbol in issue['symbols']:
                    message += f"  - {symbol}\n"
            
            elif issue['type'] == 'PHANTOM_POSITIONS':
                message += f"👻 팬텀 포지션 (거래소에 없음):\n"
                for symbol in issue['symbols']:
                    message += f"  - {symbol}\n"
            
            elif issue['type'] == 'DUPLICATE_TRACKING':
                message += f"🔀 중복 추적: {issue['symbol']}\n"
        
        message += f"\n통계: 거래소={sync_status['stats']['exchange']}, "
        message += f"시스템={sync_status['stats']['system']}, "
        message += f"수동={sync_status['stats']['manual']}"
        
        await self.notification_manager.send_alert(
            event_type="POSITION_SYNC_ERROR",
            title="포지션 동기화 불일치",
            message=message,
            priority="HIGH"
        )
    
    async def _attempt_auto_fix(self, sync_status: Dict):
        """안전한 자동 수정 시도"""
        for issue in sync_status['issues']:
            if issue['type'] == 'PHANTOM_POSITIONS':
                # 거래소에 없는 포지션은 시스템에서 제거
                for symbol in issue['symbols']:
                    logger.warning(f"팬텀 포지션 제거 시도: {symbol}")
                    # position_manager의 cleanup 메서드 호출
                    if hasattr(self.position_manager, 'remove_phantom_position'):
                        await self.position_manager.remove_phantom_position(symbol)
    
    def get_status_report(self) -> str:
        """상태 리포트 생성"""
        if not self.last_check:
            return "아직 체크되지 않음"
        
        time_since = datetime.now() - self.last_check
        
        report = f"마지막 체크: {int(time_since.total_seconds())}초 전\n"
        report += f"거래소: {len(self.last_known_state['exchange_positions'])}개\n"
        report += f"시스템: {len(self.last_known_state['system_positions'])}개\n"
        report += f"수동: {len(self.last_known_state['manual_positions'])}개\n"
        
        if self.mismatch_count > 0:
            report += f"⚠️ 불일치 감지: {self.mismatch_count}회 연속"
        
        return report
