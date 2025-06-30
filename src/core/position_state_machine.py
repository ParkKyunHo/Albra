"""
Position State Machine for AlbraTrading System
포지션 생명주기를 명확한 상태로 관리
"""

import asyncio
from typing import Dict, List, Optional, Callable, Any, Tuple
from datetime import datetime, timedelta
from enum import Enum, auto
from dataclasses import dataclass, field
import logging

from src.core.event_bus import publish_event, EventCategory, EventPriority, PositionEvents
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class PositionState(Enum):
    """포지션 상태"""
    # 기본 상태
    PENDING = "PENDING"          # 주문 대기중
    OPENING = "OPENING"          # 주문 실행중
    ACTIVE = "ACTIVE"            # 활성 포지션
    MODIFYING = "MODIFYING"      # 수정중 (부분청산, SL/TP 변경)
    CLOSING = "CLOSING"          # 청산 진행중
    CLOSED = "CLOSED"            # 청산 완료
    
    # 오류/취소 상태
    FAILED = "FAILED"            # 실패
    CANCELLED = "CANCELLED"      # 취소됨
    
    # 특수 상태
    PAUSED = "PAUSED"            # 일시정지 (수동개입)
    MODIFIED = "MODIFIED"        # 수정됨 (수동변경)
    RECONCILING = "RECONCILING"  # 정합성 확인중


class TransitionError(Exception):
    """상태 전환 오류"""
    pass


@dataclass
class StateTransition:
    """상태 전환 정보"""
    from_state: PositionState
    to_state: PositionState
    reason: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PositionStateContext:
    """포지션 상태 컨텍스트"""
    position_id: str
    symbol: str
    current_state: PositionState
    previous_state: Optional[PositionState] = None
    state_history: List[StateTransition] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 상태별 타임스탬프
    state_timestamps: Dict[str, datetime] = field(default_factory=dict)
    
    # 재시도 정보
    retry_count: int = 0
    max_retries: int = 3
    
    # 락
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    
    def add_transition(self, transition: StateTransition):
        """전환 기록 추가"""
        self.state_history.append(transition)
        self.previous_state = transition.from_state
        self.current_state = transition.to_state
        self.updated_at = transition.timestamp
        self.state_timestamps[transition.to_state.value] = transition.timestamp
    
    def get_state_duration(self, state: PositionState) -> Optional[timedelta]:
        """특정 상태의 지속 시간"""
        if state.value not in self.state_timestamps:
            return None
        
        start_time = self.state_timestamps[state.value]
        
        # 다음 상태로의 전환 찾기
        end_time = None
        for i, transition in enumerate(self.state_history):
            if transition.from_state == state and transition.timestamp > start_time:
                end_time = transition.timestamp
                break
        
        if end_time is None and self.current_state == state:
            end_time = datetime.now()
        
        return end_time - start_time if end_time else None
    
    def is_terminal_state(self) -> bool:
        """종료 상태 여부"""
        return self.current_state in [
            PositionState.CLOSED,
            PositionState.FAILED,
            PositionState.CANCELLED
        ]


class PositionStateMachine:
    """포지션 상태 머신"""
    
    # 허용된 상태 전환
    ALLOWED_TRANSITIONS = {
        PositionState.PENDING: [
            PositionState.OPENING,
            PositionState.CANCELLED,
            PositionState.FAILED
        ],
        PositionState.OPENING: [
            PositionState.ACTIVE,
            PositionState.FAILED,
            PositionState.CANCELLED
        ],
        PositionState.ACTIVE: [
            PositionState.MODIFYING,
            PositionState.CLOSING,
            PositionState.PAUSED,
            PositionState.RECONCILING
        ],
        PositionState.MODIFYING: [
            PositionState.ACTIVE,
            PositionState.MODIFIED,
            PositionState.CLOSING,
            PositionState.FAILED
        ],
        PositionState.CLOSING: [
            PositionState.CLOSED,
            PositionState.FAILED,
            PositionState.ACTIVE  # 청산 실패 시 롤백
        ],
        PositionState.PAUSED: [
            PositionState.ACTIVE,
            PositionState.MODIFYING,
            PositionState.CLOSING
        ],
        PositionState.MODIFIED: [
            PositionState.ACTIVE,
            PositionState.PAUSED,
            PositionState.CLOSING
        ],
        PositionState.RECONCILING: [
            PositionState.ACTIVE,
            PositionState.MODIFIED,
            PositionState.CLOSED,
            PositionState.FAILED
        ],
        # 종료 상태는 전환 불가
        PositionState.CLOSED: [],
        PositionState.FAILED: [],
        PositionState.CANCELLED: []
    }
    
    def __init__(self):
        # 상태 컨텍스트 저장소
        self.contexts: Dict[str, PositionStateContext] = {}
        
        # 상태 전환 핸들러
        self.transition_handlers: Dict[
            Tuple[PositionState, PositionState], 
            List[Callable]
        ] = {}
        
        # 상태 진입/퇴출 핸들러
        self.entry_handlers: Dict[PositionState, List[Callable]] = {}
        self.exit_handlers: Dict[PositionState, List[Callable]] = {}
        
        # 통계
        self.stats = {
            'total_transitions': 0,
            'failed_transitions': 0,
            'state_counts': {state.value: 0 for state in PositionState}
        }
        
        logger.info("Position State Machine 초기화")
    
    def create_position_context(self, position_id: str, symbol: str,
                              initial_state: PositionState = PositionState.PENDING,
                              metadata: Dict[str, Any] = None) -> PositionStateContext:
        """포지션 컨텍스트 생성"""
        context = PositionStateContext(
            position_id=position_id,
            symbol=symbol,
            current_state=initial_state,
            metadata=metadata or {}
        )
        
        # 초기 상태 타임스탬프
        context.state_timestamps[initial_state.value] = context.created_at
        
        self.contexts[position_id] = context
        self.stats['state_counts'][initial_state.value] += 1
        
        logger.info(f"포지션 컨텍스트 생성: {position_id} ({symbol}) - {initial_state.value}")
        
        return context
    
    def get_context(self, position_id: str) -> Optional[PositionStateContext]:
        """포지션 컨텍스트 조회"""
        return self.contexts.get(position_id)
    
    async def transition(self, position_id: str, to_state: PositionState,
                        reason: str = "", metadata: Dict[str, Any] = None) -> bool:
        """상태 전환"""
        context = self.contexts.get(position_id)
        if not context:
            logger.error(f"포지션 컨텍스트 없음: {position_id}")
            return False
        
        async with context._lock:
            try:
                from_state = context.current_state
                
                # 동일 상태로의 전환은 무시
                if from_state == to_state:
                    logger.debug(f"동일 상태 전환 무시: {position_id} ({from_state.value})")
                    return True
                
                # 전환 가능 여부 확인
                if not self._can_transition(from_state, to_state):
                    raise TransitionError(
                        f"허용되지 않은 전환: {from_state.value} → {to_state.value}"
                    )
                
                # 종료 상태에서의 전환 방지
                if context.is_terminal_state():
                    raise TransitionError(
                        f"종료 상태에서는 전환 불가: {from_state.value}"
                    )
                
                # 전환 객체 생성
                transition = StateTransition(
                    from_state=from_state,
                    to_state=to_state,
                    reason=reason,
                    metadata=metadata or {}
                )
                
                # Exit 핸들러 실행
                await self._execute_exit_handlers(context, from_state)
                
                # 전환 핸들러 실행
                await self._execute_transition_handlers(context, from_state, to_state, transition)
                
                # 상태 업데이트
                context.add_transition(transition)
                
                # 통계 업데이트
                self.stats['total_transitions'] += 1
                self.stats['state_counts'][from_state.value] -= 1
                self.stats['state_counts'][to_state.value] += 1
                
                # Entry 핸들러 실행
                await self._execute_entry_handlers(context, to_state)
                
                # 이벤트 발행
                await self._publish_state_change_event(context, transition)
                
                logger.info(
                    f"상태 전환 성공: {position_id} "
                    f"{from_state.value} → {to_state.value} ({reason})"
                )
                
                return True
                
            except TransitionError as e:
                logger.error(f"상태 전환 오류: {e}")
                self.stats['failed_transitions'] += 1
                return False
            except Exception as e:
                logger.error(f"상태 전환 중 예외: {e}")
                self.stats['failed_transitions'] += 1
                
                # 실패 시 재시도 또는 FAILED 상태로
                if context.retry_count < context.max_retries:
                    context.retry_count += 1
                    logger.info(f"상태 전환 재시도 {context.retry_count}/{context.max_retries}")
                    return await self.transition(position_id, to_state, reason, metadata)
                else:
                    await self._force_failed_state(context, str(e))
                    return False
    
    def _can_transition(self, from_state: PositionState, to_state: PositionState) -> bool:
        """전환 가능 여부 확인"""
        allowed = self.ALLOWED_TRANSITIONS.get(from_state, [])
        return to_state in allowed
    
    async def _execute_exit_handlers(self, context: PositionStateContext, 
                                   state: PositionState):
        """Exit 핸들러 실행"""
        handlers = self.exit_handlers.get(state, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(context)
                else:
                    handler(context)
            except Exception as e:
                logger.error(f"Exit 핸들러 오류 ({state.value}): {e}")
    
    async def _execute_entry_handlers(self, context: PositionStateContext,
                                    state: PositionState):
        """Entry 핸들러 실행"""
        handlers = self.entry_handlers.get(state, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(context)
                else:
                    handler(context)
            except Exception as e:
                logger.error(f"Entry 핸들러 오류 ({state.value}): {e}")
    
    async def _execute_transition_handlers(self, context: PositionStateContext,
                                         from_state: PositionState,
                                         to_state: PositionState,
                                         transition: StateTransition):
        """전환 핸들러 실행"""
        key = (from_state, to_state)
        handlers = self.transition_handlers.get(key, [])
        
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(context, transition)
                else:
                    handler(context, transition)
            except Exception as e:
                logger.error(f"전환 핸들러 오류 ({key}): {e}")
    
    async def _publish_state_change_event(self, context: PositionStateContext,
                                        transition: StateTransition):
        """상태 변경 이벤트 발행"""
        await publish_event(
            PositionEvents.STATE_CHANGED,
            {
                'position_id': context.position_id,
                'symbol': context.symbol,
                'from_state': transition.from_state.value,
                'to_state': transition.to_state.value,
                'reason': transition.reason,
                'metadata': transition.metadata,
                'state_history_length': len(context.state_history)
            },
            EventCategory.POSITION,
            EventPriority.MEDIUM
        )
    
    async def _force_failed_state(self, context: PositionStateContext, error: str):
        """강제로 FAILED 상태로 전환"""
        try:
            # FAILED로의 전환은 항상 허용
            transition = StateTransition(
                from_state=context.current_state,
                to_state=PositionState.FAILED,
                reason=f"강제 실패: {error}",
                metadata={'error': error, 'forced': True}
            )
            
            context.add_transition(transition)
            
            # 통계 업데이트
            self.stats['state_counts'][context.previous_state.value] -= 1
            self.stats['state_counts'][PositionState.FAILED.value] += 1
            
            # 이벤트 발행
            await self._publish_state_change_event(context, transition)
            
            logger.error(f"포지션 {context.position_id} 강제 실패 처리: {error}")
            
        except Exception as e:
            logger.critical(f"강제 실패 처리 중 오류: {e}")
    
    def on_entry(self, state: PositionState):
        """Entry 핸들러 데코레이터"""
        def decorator(func):
            if state not in self.entry_handlers:
                self.entry_handlers[state] = []
            self.entry_handlers[state].append(func)
            return func
        return decorator
    
    def on_exit(self, state: PositionState):
        """Exit 핸들러 데코레이터"""
        def decorator(func):
            if state not in self.exit_handlers:
                self.exit_handlers[state] = []
            self.exit_handlers[state].append(func)
            return func
        return decorator
    
    def on_transition(self, from_state: PositionState, to_state: PositionState):
        """전환 핸들러 데코레이터"""
        def decorator(func):
            key = (from_state, to_state)
            if key not in self.transition_handlers:
                self.transition_handlers[key] = []
            self.transition_handlers[key].append(func)
            return func
        return decorator
    
    async def bulk_transition(self, transitions: List[Tuple[str, PositionState, str]]) -> Dict[str, bool]:
        """일괄 상태 전환"""
        results = {}
        
        # 병렬 처리
        tasks = []
        for position_id, to_state, reason in transitions:
            task = self.transition(position_id, to_state, reason)
            tasks.append((position_id, task))
        
        # 결과 수집
        for position_id, task in tasks:
            try:
                results[position_id] = await task
            except Exception as e:
                logger.error(f"일괄 전환 오류 ({position_id}): {e}")
                results[position_id] = False
        
        return results
    
    def get_positions_by_state(self, state: PositionState) -> List[str]:
        """특정 상태의 포지션 ID 목록"""
        return [
            position_id 
            for position_id, context in self.contexts.items()
            if context.current_state == state
        ]
    
    def get_state_summary(self) -> Dict[str, Any]:
        """상태 요약"""
        return {
            'total_positions': len(self.contexts),
            'state_distribution': {
                state.value: count 
                for state, count in self.stats['state_counts'].items()
                if count > 0
            },
            'total_transitions': self.stats['total_transitions'],
            'failed_transitions': self.stats['failed_transitions'],
            'active_positions': len([
                c for c in self.contexts.values()
                if c.current_state in [PositionState.ACTIVE, PositionState.MODIFYING]
            ]),
            'terminal_positions': len([
                c for c in self.contexts.values()
                if c.is_terminal_state()
            ])
        }
    
    def cleanup_terminal_states(self, older_than_hours: int = 24):
        """종료 상태 포지션 정리"""
        cutoff_time = datetime.now() - timedelta(hours=older_than_hours)
        removed_count = 0
        
        for position_id in list(self.contexts.keys()):
            context = self.contexts[position_id]
            
            if (context.is_terminal_state() and 
                context.updated_at < cutoff_time):
                
                # 통계에서 제거
                self.stats['state_counts'][context.current_state.value] -= 1
                
                del self.contexts[position_id]
                removed_count += 1
        
        if removed_count > 0:
            logger.info(f"종료 상태 포지션 {removed_count}개 정리")
        
        return removed_count


# 전역 상태 머신 인스턴스
_state_machine: Optional[PositionStateMachine] = None


def get_position_state_machine() -> PositionStateMachine:
    """싱글톤 상태 머신 반환"""
    global _state_machine
    if _state_machine is None:
        _state_machine = PositionStateMachine()
    return _state_machine


# 기본 핸들러 설정
def setup_default_handlers(state_machine: PositionStateMachine):
    """기본 상태 핸들러 설정"""
    
    @state_machine.on_entry(PositionState.ACTIVE)
    async def on_active_entry(context: PositionStateContext):
        """ACTIVE 상태 진입 시"""
        logger.info(f"포지션 활성화: {context.position_id}")
        context.metadata['activated_at'] = datetime.now().isoformat()
    
    @state_machine.on_exit(PositionState.ACTIVE)
    async def on_active_exit(context: PositionStateContext):
        """ACTIVE 상태 퇴출 시"""
        duration = context.get_state_duration(PositionState.ACTIVE)
        if duration:
            logger.info(f"포지션 활성 시간: {context.position_id} - {duration}")
    
    @state_machine.on_transition(PositionState.ACTIVE, PositionState.CLOSING)
    async def on_closing_transition(context: PositionStateContext, 
                                  transition: StateTransition):
        """청산 시작 시"""
        logger.info(f"포지션 청산 시작: {context.position_id} - {transition.reason}")
    
    @state_machine.on_entry(PositionState.CLOSED)
    async def on_closed_entry(context: PositionStateContext):
        """CLOSED 상태 진입 시"""
        total_duration = datetime.now() - context.created_at
        logger.info(f"포지션 종료: {context.position_id} - 총 시간: {total_duration}")
    
    @state_machine.on_entry(PositionState.FAILED)
    async def on_failed_entry(context: PositionStateContext):
        """FAILED 상태 진입 시"""
        logger.error(f"포지션 실패: {context.position_id} - {context.metadata.get('error', 'Unknown')}")
