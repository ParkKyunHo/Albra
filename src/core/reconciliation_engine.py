"""
Reconciliation Engine for AlbraTrading System
시스템과 거래소 간 상태 정합성 보장
"""

import asyncio
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum, auto
import json
import logging

from src.core.event_bus import publish_event, EventCategory, EventPriority
from src.core.position_state_machine import PositionState, get_position_state_machine
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class ReconciliationType(Enum):
    """정합성 확인 타입"""
    SCHEDULED = auto()      # 정기 스케줄
    ON_DEMAND = auto()      # 수동 요청
    EVENT_DRIVEN = auto()   # 이벤트 기반
    RECOVERY = auto()       # 복구 모드


class DiscrepancyType(Enum):
    """불일치 타입"""
    POSITION_NOT_IN_SYSTEM = "POSITION_NOT_IN_SYSTEM"      # 거래소에만 있음
    POSITION_NOT_IN_EXCHANGE = "POSITION_NOT_IN_EXCHANGE"  # 시스템에만 있음
    SIZE_MISMATCH = "SIZE_MISMATCH"                        # 크기 불일치
    PRICE_MISMATCH = "PRICE_MISMATCH"                      # 가격 불일치
    LEVERAGE_MISMATCH = "LEVERAGE_MISMATCH"                # 레버리지 불일치
    SIDE_MISMATCH = "SIDE_MISMATCH"                        # 방향 불일치
    STATE_MISMATCH = "STATE_MISMATCH"                      # 상태 불일치


class ResolutionAction(Enum):
    """해결 액션"""
    UPDATE_SYSTEM = "UPDATE_SYSTEM"          # 시스템 업데이트
    UPDATE_EXCHANGE = "UPDATE_EXCHANGE"      # 거래소 업데이트
    CLOSE_POSITION = "CLOSE_POSITION"        # 포지션 청산
    CREATE_POSITION = "CREATE_POSITION"      # 포지션 생성
    MANUAL_INTERVENTION = "MANUAL_INTERVENTION"  # 수동 개입 필요
    IGNORE = "IGNORE"                        # 무시
    RETRY = "RETRY"                          # 재시도


@dataclass
class Discrepancy:
    """불일치 정보"""
    discrepancy_id: str
    symbol: str
    discrepancy_type: DiscrepancyType
    system_data: Dict[str, Any]
    exchange_data: Dict[str, Any]
    detected_at: datetime = field(default_factory=datetime.now)
    severity: str = "MEDIUM"  # LOW, MEDIUM, HIGH, CRITICAL
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 변환"""
        return {
            'discrepancy_id': self.discrepancy_id,
            'symbol': self.symbol,
            'type': self.discrepancy_type.value,
            'system_data': self.system_data,
            'exchange_data': self.exchange_data,
            'detected_at': self.detected_at.isoformat(),
            'severity': self.severity,
            'details': self.details
        }


@dataclass
class ReconciliationResult:
    """정합성 확인 결과"""
    reconciliation_id: str
    reconciliation_type: ReconciliationType
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_positions_checked: int = 0
    discrepancies_found: List[Discrepancy] = field(default_factory=list)
    resolutions_attempted: int = 0
    resolutions_succeeded: int = 0
    resolutions_failed: int = 0
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 변환"""
        return {
            'reconciliation_id': self.reconciliation_id,
            'type': self.reconciliation_type.name,
            'started_at': self.started_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'total_checked': self.total_positions_checked,
            'discrepancies': len(self.discrepancies_found),
            'resolutions': {
                'attempted': self.resolutions_attempted,
                'succeeded': self.resolutions_succeeded,
                'failed': self.resolutions_failed
            },
            'errors': self.errors,
            'metadata': self.metadata
        }


class ReconciliationEngine:
    """포지션 정합성 확인 및 자동 해결 엔진"""
    
    def __init__(self, position_manager, binance_api, notification_manager=None):
        self.position_manager = position_manager
        self.binance_api = binance_api
        self.notification_manager = notification_manager
        self.state_machine = get_position_state_machine()
        
        # 설정 - config.yaml에서 로드
        from src.utils.config_manager import ConfigManager
        config_manager = ConfigManager()
        phase2_config = config_manager.config.get('phase2', {})
        reconciliation_config = phase2_config.get('reconciliation', {})
        
        self.config = {
            'check_intervals': {
                'fast': reconciliation_config.get('intervals', {}).get('triggered', 60),
                'normal': reconciliation_config.get('intervals', {}).get('periodic', 300),
                'slow': 3600  # 1시간 (하드코딩 유지)
            },
            'resolution_rules': self._default_resolution_rules(),
            'max_auto_resolution_attempts': reconciliation_config.get('max_attempts', 3),
            'critical_discrepancy_threshold': 0.1,  # 10% 차이
            'enable_auto_resolution': True
        }
        
        # 상태
        self._running = False
        self._check_tasks = {}
        self._last_check_time = {}
        self._discrepancy_history = []  # 최근 100개
        self._resolution_history = []   # 최근 100개
        
        # 통계
        self.stats = {
            'total_checks': 0,
            'total_discrepancies': 0,
            'auto_resolutions': 0,
            'manual_interventions': 0,
            'failed_resolutions': 0
        }
        
        logger.info("Reconciliation Engine 초기화")
    
    def _default_resolution_rules(self) -> Dict[DiscrepancyType, ResolutionAction]:
        """기본 해결 규칙"""
        return {
            DiscrepancyType.POSITION_NOT_IN_SYSTEM: ResolutionAction.CREATE_POSITION,
            DiscrepancyType.POSITION_NOT_IN_EXCHANGE: ResolutionAction.UPDATE_SYSTEM,
            DiscrepancyType.SIZE_MISMATCH: ResolutionAction.UPDATE_SYSTEM,
            DiscrepancyType.PRICE_MISMATCH: ResolutionAction.UPDATE_SYSTEM,
            DiscrepancyType.LEVERAGE_MISMATCH: ResolutionAction.UPDATE_EXCHANGE,
            DiscrepancyType.SIDE_MISMATCH: ResolutionAction.MANUAL_INTERVENTION,
            DiscrepancyType.STATE_MISMATCH: ResolutionAction.UPDATE_SYSTEM
        }
    
    async def start(self):
        """엔진 시작"""
        if self._running:
            logger.warning("Reconciliation Engine이 이미 실행 중입니다")
            return
        
        self._running = True
        
        # 정기 체크 태스크 시작
        self._check_tasks['fast'] = asyncio.create_task(
            self._periodic_check_loop('fast')
        )
        self._check_tasks['normal'] = asyncio.create_task(
            self._periodic_check_loop('normal')
        )
        self._check_tasks['slow'] = asyncio.create_task(
            self._periodic_check_loop('slow')
        )
        
        logger.info("Reconciliation Engine 시작")
        
        # 초기 체크
        await self.reconcile(ReconciliationType.SCHEDULED)
    
    async def stop(self):
        """엔진 정지"""
        logger.info("Reconciliation Engine 정지 중...")
        self._running = False
        
        # 태스크 취소
        for task in self._check_tasks.values():
            if task and not task.done():
                task.cancel()
        
        # 태스크 완료 대기
        if self._check_tasks:
            await asyncio.gather(*self._check_tasks.values(), return_exceptions=True)
        
        self._check_tasks.clear()
        logger.info("Reconciliation Engine 정지 완료")
    
    async def _periodic_check_loop(self, interval_type: str):
        """정기 체크 루프"""
        interval = self.config['check_intervals'][interval_type]
        
        while self._running:
            try:
                await asyncio.sleep(interval)
                
                # 체크 조건 확인
                if self._should_run_check(interval_type):
                    await self.reconcile(ReconciliationType.SCHEDULED)
                    self._last_check_time[interval_type] = datetime.now()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"정기 체크 오류 ({interval_type}): {e}")
                await asyncio.sleep(30)  # 오류 시 대기
    
    def _should_run_check(self, interval_type: str) -> bool:
        """체크 실행 여부 결정"""
        # 시장 상태에 따른 체크 빈도 조정
        if interval_type == 'fast':
            # 활성 포지션이 있을 때만 빠른 체크
            active_positions = self.position_manager.get_active_positions()
            return len(active_positions) > 0
        
        elif interval_type == 'normal':
            # 항상 실행
            return True
        
        elif interval_type == 'slow':
            # 시스템 유휴 시간 체크
            return True
        
        return False
    
    async def reconcile(self, reconciliation_type: ReconciliationType = ReconciliationType.ON_DEMAND,
                       symbols: Optional[List[str]] = None) -> ReconciliationResult:
        """정합성 확인 실행"""
        reconciliation_id = f"recon_{datetime.now().timestamp()}"
        result = ReconciliationResult(
            reconciliation_id=reconciliation_id,
            reconciliation_type=reconciliation_type,
            started_at=datetime.now()
        )
        
        try:
            logger.info(f"정합성 확인 시작: {reconciliation_type.name}")
            self.stats['total_checks'] += 1
            
            # 1. 데이터 수집
            system_positions = await self._get_system_positions(symbols)
            exchange_positions = await self._get_exchange_positions(symbols)
            
            result.total_positions_checked = len(system_positions) + len(exchange_positions)
            
            # 2. 불일치 감지
            discrepancies = await self._detect_discrepancies(
                system_positions, exchange_positions
            )
            result.discrepancies_found = discrepancies
            self.stats['total_discrepancies'] += len(discrepancies)
            
            # 3. 불일치 분류 및 우선순위 설정
            prioritized_discrepancies = self._prioritize_discrepancies(discrepancies)
            
            # 4. 자동 해결 시도
            if self.config['enable_auto_resolution'] and prioritized_discrepancies:
                resolution_results = await self._resolve_discrepancies(
                    prioritized_discrepancies
                )
                
                result.resolutions_attempted = len(resolution_results)
                result.resolutions_succeeded = sum(
                    1 for r in resolution_results.values() if r['success']
                )
                result.resolutions_failed = sum(
                    1 for r in resolution_results.values() if not r['success']
                )
            
            # 5. 결과 기록
            result.completed_at = datetime.now()
            self._record_result(result)
            
            # 6. 알림 전송
            await self._send_reconciliation_alert(result)
            
            # 7. 이벤트 발행
            await publish_event(
                "RECONCILIATION_COMPLETED",
                result.to_dict(),
                EventCategory.SYSTEM,
                EventPriority.MEDIUM
            )
            
            logger.info(
                f"정합성 확인 완료: "
                f"확인={result.total_positions_checked}, "
                f"불일치={len(result.discrepancies_found)}, "
                f"해결={result.resolutions_succeeded}/{result.resolutions_attempted}"
            )
            
            return result
        except Exception as e:
            logger.error(f"정합성 확인 중 오류: {e}")
            result.errors.append(str(e))
            result.completed_at = datetime.now()
            return result
    
    async def _get_system_positions(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """시스템 포지션 조회"""
        positions = {}
        
        all_positions = self.position_manager.get_all_positions()
        
        for symbol, position in all_positions.items():
            if symbols and symbol not in symbols:
                continue
            
            if position.status in ['ACTIVE', 'MODIFIED', 'PAUSED']:
                # 상태 머신에서 상태 정보 추가
                state_context = self.state_machine.get_context(position.position_id)
                
                positions[symbol] = {
                    'position_id': position.position_id,
                    'symbol': symbol,
                    'side': position.side,
                    'size': position.size,
                    'entry_price': position.entry_price,
                    'leverage': position.leverage,
                    'is_manual': position.is_manual,
                    'status': position.status,
                    'state': state_context.current_state.value if state_context else 'UNKNOWN',
                    'last_updated': position.last_updated
                }
        
        return positions
    
    async def _get_exchange_positions(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """거래소 포지션 조회"""
        positions = {}
        
        try:
            exchange_positions = await self.binance_api.get_positions()
            
            for pos in exchange_positions:
                symbol = pos['symbol']
                
                if symbols and symbol not in symbols:
                    continue
                
                position_amt = float(pos.get('positionAmt', 0))
                
                if position_amt != 0:
                    positions[symbol] = {
                        'symbol': symbol,
                        'side': 'LONG' if position_amt > 0 else 'SHORT',
                        'size': abs(position_amt),
                        'entry_price': float(pos.get('entryPrice', 0)),
                        'leverage': int(pos.get('leverage', 1)),
                        'unrealized_pnl': float(pos.get('unrealizedProfit', 0)),
                        'margin_type': pos.get('marginType', 'cross'),
                        'position_side': pos.get('positionSide', 'BOTH')
                    }
        
        except Exception as e:
            logger.error(f"거래소 포지션 조회 실패: {e}")
            raise
        
        return positions
    
    async def _detect_discrepancies(self, system_positions: Dict[str, Any],
                                   exchange_positions: Dict[str, Any]) -> List[Discrepancy]:
        """불일치 감지"""
        discrepancies = []
        
        # 모든 심볼 집합
        all_symbols = set(system_positions.keys()) | set(exchange_positions.keys())
        
        for symbol in all_symbols:
            sys_pos = system_positions.get(symbol)
            ex_pos = exchange_positions.get(symbol)
            
            # 케이스 1: 거래소에만 있음
            if ex_pos and not sys_pos:
                discrepancy = Discrepancy(
                    discrepancy_id=f"disc_{symbol}_{datetime.now().timestamp()}",
                    symbol=symbol,
                    discrepancy_type=DiscrepancyType.POSITION_NOT_IN_SYSTEM,
                    system_data={},
                    exchange_data=ex_pos,
                    severity="HIGH"
                )
                discrepancies.append(discrepancy)
            
            # 케이스 2: 시스템에만 있음
            elif sys_pos and not ex_pos:
                discrepancy = Discrepancy(
                    discrepancy_id=f"disc_{symbol}_{datetime.now().timestamp()}",
                    symbol=symbol,
                    discrepancy_type=DiscrepancyType.POSITION_NOT_IN_EXCHANGE,
                    system_data=sys_pos,
                    exchange_data={},
                    severity="CRITICAL"
                )
                discrepancies.append(discrepancy)
            
            # 케이스 3: 양쪽에 있지만 불일치
            elif sys_pos and ex_pos:
                # 크기 불일치
                if abs(sys_pos['size'] - ex_pos['size']) > 0.0001:
                    size_diff_pct = abs(sys_pos['size'] - ex_pos['size']) / sys_pos['size']
                    
                    discrepancy = Discrepancy(
                        discrepancy_id=f"disc_{symbol}_size_{datetime.now().timestamp()}",
                        symbol=symbol,
                        discrepancy_type=DiscrepancyType.SIZE_MISMATCH,
                        system_data=sys_pos,
                        exchange_data=ex_pos,
                        severity="HIGH" if size_diff_pct > self.config['critical_discrepancy_threshold'] else "MEDIUM",
                        details={
                            'system_size': sys_pos['size'],
                            'exchange_size': ex_pos['size'],
                            'difference': sys_pos['size'] - ex_pos['size'],
                            'difference_pct': size_diff_pct * 100
                        }
                    )
                    discrepancies.append(discrepancy)
                
                # 방향 불일치
                if sys_pos['side'] != ex_pos['side']:
                    discrepancy = Discrepancy(
                        discrepancy_id=f"disc_{symbol}_side_{datetime.now().timestamp()}",
                        symbol=symbol,
                        discrepancy_type=DiscrepancyType.SIDE_MISMATCH,
                        system_data=sys_pos,
                        exchange_data=ex_pos,
                        severity="CRITICAL"
                    )
                    discrepancies.append(discrepancy)
                
                # 레버리지 불일치
                if sys_pos['leverage'] != ex_pos['leverage']:
                    discrepancy = Discrepancy(
                        discrepancy_id=f"disc_{symbol}_leverage_{datetime.now().timestamp()}",
                        symbol=symbol,
                        discrepancy_type=DiscrepancyType.LEVERAGE_MISMATCH,
                        system_data=sys_pos,
                        exchange_data=ex_pos,
                        severity="LOW"
                    )
                    discrepancies.append(discrepancy)
        
        return discrepancies
    
    def _prioritize_discrepancies(self, discrepancies: List[Discrepancy]) -> List[Discrepancy]:
        """불일치 우선순위 설정"""
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        
        # 심각도와 타입별로 정렬
        return sorted(
            discrepancies,
            key=lambda d: (
                severity_order.get(d.severity, 99),
                d.discrepancy_type.value
            )
        )
    
    async def _resolve_discrepancies(self, discrepancies: List[Discrepancy]) -> Dict[str, Dict[str, Any]]:
        """불일치 자동 해결"""
        results = {}
        
        for discrepancy in discrepancies:
            try:
                # 해결 규칙 확인
                action = self.config['resolution_rules'].get(
                    discrepancy.discrepancy_type,
                    ResolutionAction.MANUAL_INTERVENTION
                )
                
                logger.info(
                    f"불일치 해결 시도: {discrepancy.symbol} "
                    f"({discrepancy.discrepancy_type.value}) → {action.value}"
                )
                
                # 액션 실행
                result = await self._execute_resolution_action(
                    discrepancy, action
                )
                
                results[discrepancy.discrepancy_id] = result
                
                if result['success']:
                    self.stats['auto_resolutions'] += 1
                else:
                    self.stats['failed_resolutions'] += 1
                
            except Exception as e:
                logger.error(f"불일치 해결 실패 ({discrepancy.symbol}): {e}")
                results[discrepancy.discrepancy_id] = {
                    'success': False,
                    'error': str(e),
                    'action': action.value
                }
        
        return results
    
    async def _execute_resolution_action(self, discrepancy: Discrepancy,
                                       action: ResolutionAction) -> Dict[str, Any]:
        """해결 액션 실행"""
        result = {
            'success': False,
            'action': action.value,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            if action == ResolutionAction.UPDATE_SYSTEM:
                # 시스템 데이터를 거래소 데이터로 업데이트
                await self._update_system_position(discrepancy)
                result['success'] = True
                result['details'] = "시스템 포지션 업데이트 완료"
            
            elif action == ResolutionAction.UPDATE_EXCHANGE:
                # 거래소 데이터 업데이트 (레버리지 등)
                await self._update_exchange_position(discrepancy)
                result['success'] = True
                result['details'] = "거래소 포지션 업데이트 완료"
            
            elif action == ResolutionAction.CREATE_POSITION:
                # 시스템에 포지션 생성
                await self._create_system_position(discrepancy)
                result['success'] = True
                result['details'] = "시스템 포지션 생성 완료"
            
            elif action == ResolutionAction.CLOSE_POSITION:
                # 포지션 청산
                await self._close_position(discrepancy)
                result['success'] = True
                result['details'] = "포지션 청산 완료"
            
            elif action == ResolutionAction.MANUAL_INTERVENTION:
                # 수동 개입 필요
                await self._request_manual_intervention(discrepancy)
                self.stats['manual_interventions'] += 1
                result['success'] = False
                result['details'] = "수동 개입 요청됨"
            
            elif action == ResolutionAction.IGNORE:
                # 무시
                result['success'] = True
                result['details'] = "불일치 무시됨"
            
            else:
                result['error'] = f"알 수 없는 액션: {action.value}"
            
        except Exception as e:
            result['success'] = False
            result['error'] = str(e)
            logger.error(f"액션 실행 실패 ({action.value}): {e}")
        
        return result
    
    async def _update_system_position(self, discrepancy: Discrepancy):
        """시스템 포지션 업데이트"""
        symbol = discrepancy.symbol
        ex_data = discrepancy.exchange_data
        
        position = self.position_manager.get_position(symbol)
        if position:
            # 크기 업데이트
            if discrepancy.discrepancy_type == DiscrepancyType.SIZE_MISMATCH:
                old_size = position.size
                position.update_size(ex_data['size'], "Reconciliation")
                
                # 상태 머신 업데이트
                await self.state_machine.transition(
                    position.position_id,
                    PositionState.MODIFIED,
                    f"크기 불일치 해결: {old_size} → {ex_data['size']}"
                )
            
            # 가격 업데이트
            elif discrepancy.discrepancy_type == DiscrepancyType.PRICE_MISMATCH:
                position.entry_price = ex_data['entry_price']
                position.last_updated = datetime.now().isoformat()
            
            # 캐시 저장
            await self.position_manager._save_positions_batch()
    
    async def _update_exchange_position(self, discrepancy: Discrepancy):
        """거래소 포지션 업데이트"""
        symbol = discrepancy.symbol
        sys_data = discrepancy.system_data
        
        # 레버리지 업데이트
        if discrepancy.discrepancy_type == DiscrepancyType.LEVERAGE_MISMATCH:
            await self.binance_api.set_leverage(symbol, sys_data['leverage'])
    
    async def _create_system_position(self, discrepancy: Discrepancy):
        """시스템에 포지션 생성"""
        ex_data = discrepancy.exchange_data
        
        # 포지션 ID 생성
        position_id = self.position_manager._generate_position_id(
            ex_data['symbol'],
            ex_data['side'],
            ex_data['entry_price']
        )
        
        # 포지션 생성
        from src.core.position_manager import Position
        position = Position(
            symbol=ex_data['symbol'],
            side=ex_data['side'],
            size=ex_data['size'],
            entry_price=ex_data['entry_price'],
            leverage=ex_data['leverage'],
            position_id=position_id,
            is_manual=True,  # 수동 포지션으로 표시
            strategy_name=None,
            created_at=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat(),
            initial_size=ex_data['size'],
            status='ACTIVE'
        )
        
        # 태그 추가
        position.add_tag("reconciliation_created")
        position.add_tag(f"created_{datetime.now().strftime('%Y%m%d')}")
        
        # 포지션 매니저에 추가
        self.position_manager.positions[ex_data['symbol']] = position
        
        # 상태 머신에 등록
        self.state_machine.create_position_context(
            position_id,
            ex_data['symbol'],
            PositionState.ACTIVE,
            {'source': 'reconciliation'}
        )
        
        # 캐시 저장
        await self.position_manager._save_positions_batch()
        
        logger.info(f"Reconciliation으로 포지션 생성: {ex_data['symbol']}")
    
    async def _close_position(self, discrepancy: Discrepancy):
        """포지션 청산"""
        # 구현 필요 시 추가
        raise NotImplementedError("포지션 청산 기능은 아직 구현되지 않았습니다")
    
    async def _request_manual_intervention(self, discrepancy: Discrepancy):
        """수동 개입 요청"""
        if self.notification_manager:
            message = (
                f"⚠️ <b>수동 개입 필요</b>\n\n"
                f"<b>심볼:</b> {discrepancy.symbol}\n"
                f"<b>불일치 타입:</b> {discrepancy.discrepancy_type.value}\n"
                f"<b>심각도:</b> {discrepancy.severity}\n\n"
                f"시스템과 거래소 간 불일치가 감지되어 수동 확인이 필요합니다."
            )
            
            await self.notification_manager.send_alert(
                event_type="POSITION_SYNC_ERROR",
                title="수동 개입 필요",
                message=message,
                data=discrepancy.to_dict()
            )
    
    def _record_result(self, result: ReconciliationResult):
        """결과 기록"""
        # 불일치 기록
        self._discrepancy_history.extend(result.discrepancies_found)
        
        # 최근 100개만 유지
        if len(self._discrepancy_history) > 100:
            self._discrepancy_history = self._discrepancy_history[-100:]
        
        # 해결 기록
        resolution_record = {
            'reconciliation_id': result.reconciliation_id,
            'timestamp': result.completed_at,
            'discrepancies': len(result.discrepancies_found),
            'resolutions': {
                'attempted': result.resolutions_attempted,
                'succeeded': result.resolutions_succeeded,
                'failed': result.resolutions_failed
            }
        }
        
        self._resolution_history.append(resolution_record)
        
        # 최근 100개만 유지
        if len(self._resolution_history) > 100:
            self._resolution_history = self._resolution_history[-100:]
    
    async def _send_reconciliation_alert(self, result: ReconciliationResult):
        """정합성 확인 결과 알림"""
        if not self.notification_manager:
            return
        
        # 심각한 불일치가 있는 경우만 알림
        critical_discrepancies = [
            d for d in result.discrepancies_found
            if d.severity in ['CRITICAL', 'HIGH']
        ]
        
        if critical_discrepancies:
            message = (
                f"🔍 <b>정합성 확인 결과</b>\n\n"
                f"<b>확인된 포지션:</b> {result.total_positions_checked}개\n"
                f"<b>불일치 발견:</b> {len(result.discrepancies_found)}개\n"
                f"<b>심각한 불일치:</b> {len(critical_discrepancies)}개\n\n"
            )
            
            # 주요 불일치 정보
            for disc in critical_discrepancies[:3]:  # 최대 3개
                message += (
                    f"• {disc.symbol}: {disc.discrepancy_type.value}\n"
                )
            
            if len(critical_discrepancies) > 3:
                message += f"... 외 {len(critical_discrepancies) - 3}개\n"
            
            # 해결 결과
            if result.resolutions_attempted > 0:
                message += (
                    f"\n<b>자동 해결:</b> "
                    f"{result.resolutions_succeeded}/{result.resolutions_attempted} 성공"
                )
            
            await self.notification_manager.send_alert(
                event_type="POSITION_SYNC_ERROR",
                title="정합성 불일치 감지",
                message=message,
                data=result.to_dict()
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 반환"""
        return {
            'engine_stats': self.stats.copy(),
            'recent_discrepancies': len(self._discrepancy_history),
            'discrepancy_types': self._get_discrepancy_type_distribution(),
            'resolution_success_rate': self._calculate_resolution_success_rate(),
            'last_checks': self._last_check_time.copy()
        }
    
    def _get_discrepancy_type_distribution(self) -> Dict[str, int]:
        """불일치 타입별 분포"""
        distribution = {}
        
        for disc in self._discrepancy_history:
            disc_type = disc.discrepancy_type.value
            distribution[disc_type] = distribution.get(disc_type, 0) + 1
        
        return distribution
    
    def _calculate_resolution_success_rate(self) -> float:
        """해결 성공률 계산"""
        if self.stats['auto_resolutions'] == 0:
            return 0.0
        
        total_attempts = self.stats['auto_resolutions'] + self.stats['failed_resolutions']
        return (self.stats['auto_resolutions'] / total_attempts) * 100 if total_attempts > 0 else 0.0
    
    async def force_reconcile(self, symbol: str) -> ReconciliationResult:
        """특정 심볼 강제 정합성 확인"""
        logger.info(f"강제 정합성 확인: {symbol}")
        return await self.reconcile(
            ReconciliationType.ON_DEMAND,
            symbols=[symbol]
        )
    
    def get_discrepancy_history(self, symbol: Optional[str] = None,
                               limit: int = 50) -> List[Dict[str, Any]]:
        """불일치 이력 조회"""
        history = self._discrepancy_history
        
        if symbol:
            history = [d for d in history if d.symbol == symbol]
        
        # 최신순 정렬
        history = sorted(history, key=lambda d: d.detected_at, reverse=True)
        
        # 딕셔너리 변환
        return [d.to_dict() for d in history[:limit]]


# 전역 정합성 엔진 인스턴스
_reconciliation_engine: Optional[ReconciliationEngine] = None


def get_reconciliation_engine(position_manager=None, binance_api=None,
                            notification_manager=None) -> ReconciliationEngine:
    """싱글톤 정합성 엔진 반환"""
    global _reconciliation_engine
    
    if _reconciliation_engine is None:
        if not position_manager or not binance_api:
            raise ValueError("초기 생성 시 position_manager와 binance_api가 필요합니다")
        
        _reconciliation_engine = ReconciliationEngine(
            position_manager,
            binance_api,
            notification_manager
        )
    
    return _reconciliation_engine