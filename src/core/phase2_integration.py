"""
Phase 2 Integration Module
Phase 2 컴포넌트들을 기존 시스템에 통합
"""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime

from src.core.event_bus import AsyncEventBus, get_event_bus
from src.core.event_bus_integration import EventBusIntegration, get_event_bus_integration
from src.core.position_state_machine import (
    PositionStateMachine, get_position_state_machine, 
    PositionState, setup_default_handlers
)
from src.core.reconciliation_engine import (
    ReconciliationEngine, get_reconciliation_engine,
    ReconciliationType
)
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class Phase2Integration:
    """Phase 2 컴포넌트 통합 관리자"""
    
    def __init__(self, trading_system):
        self.trading_system = trading_system
        
        # Phase 2 컴포넌트
        self.event_bus: Optional[AsyncEventBus] = None
        self.event_bus_integration: Optional[EventBusIntegration] = None
        self.state_machine: Optional[PositionStateMachine] = None
        self.reconciliation_engine: Optional[ReconciliationEngine] = None
        
        # 상태
        self._initialized = False
        
        logger.info("Phase 2 Integration 준비")
    
    async def initialize(self) -> bool:
        """Phase 2 컴포넌트 초기화"""
        try:
            logger.info("="*60)
            logger.info("Phase 2 컴포넌트 초기화 시작")
            logger.info("="*60)
            
            # 1. Event Bus 초기화
            await self._initialize_event_bus()
            
            # 2. Position State Machine 초기화
            await self._initialize_state_machine()
            
            # 3. Reconciliation Engine 초기화
            await self._initialize_reconciliation_engine()
            
            # 4. 컴포넌트 간 연결 설정
            await self._setup_component_connections()
            
            self._initialized = True
            
            logger.info("✅ Phase 2 컴포넌트 초기화 완료")
            logger.info("  - Event Bus: 활성화")
            logger.info("  - State Machine: 활성화")
            logger.info("  - Reconciliation Engine: 활성화")
            
            return True
            
        except Exception as e:
            logger.error(f"Phase 2 초기화 실패: {e}")
            return False
    
    async def _initialize_event_bus(self):
        """Event Bus 초기화 및 통합"""
        logger.info("Event Bus 초기화 중...")
        
        # Event Bus Integration 생성
        self.event_bus_integration = get_event_bus_integration()
        
        # 통합 초기화 (notification_manager 전달)
        notification_manager = getattr(self.trading_system, 'notification_manager', None)
        await self.event_bus_integration.initialize(notification_manager)
        
        # Event Bus 참조
        self.event_bus = get_event_bus()
        
        logger.info("✓ Event Bus 초기화 완료")
    
    async def _initialize_state_machine(self):
        """Position State Machine 초기화"""
        logger.info("Position State Machine 초기화 중...")
        
        # State Machine 생성
        self.state_machine = get_position_state_machine()
        
        # 기본 핸들러 설정
        setup_default_handlers(self.state_machine)
        
        # 커스텀 핸들러 추가
        self._setup_custom_state_handlers()
        
        # 기존 포지션들의 상태 컨텍스트 생성
        await self._migrate_existing_positions()
        
        logger.info("✓ Position State Machine 초기화 완료")
    
    async def _initialize_reconciliation_engine(self):
        """Reconciliation Engine 초기화"""
        logger.info("Reconciliation Engine 초기화 중...")
        
        # 필요한 컴포넌트 가져오기
        position_manager = getattr(self.trading_system, 'position_manager', None)
        binance_api = getattr(self.trading_system, 'exchange', None)
        notification_manager = getattr(self.trading_system, 'notification_manager', None)
        
        if not position_manager or not binance_api:
            raise ValueError("position_manager와 binance_api가 필요합니다")
        
        # Reconciliation Engine 생성
        self.reconciliation_engine = get_reconciliation_engine(
            position_manager,
            binance_api,
            notification_manager
        )
        
        # 엔진 시작
        await self.reconciliation_engine.start()
        
        logger.info("✓ Reconciliation Engine 초기화 완료")
    
    async def _setup_component_connections(self):
        """컴포넌트 간 연결 설정"""
        logger.info("컴포넌트 연결 설정 중...")
        
        # Position Manager가 Event Bus를 사용하도록 설정
        if hasattr(self.trading_system, 'position_manager'):
            # 포지션 이벤트 핸들러 추가
            self.trading_system.position_manager.add_event_handler(
                'position_created', self._on_position_created
            )
            self.trading_system.position_manager.add_event_handler(
                'position_closed', self._on_position_closed
            )
            self.trading_system.position_manager.add_event_handler(
                'position_updated', self._on_position_updated
            )
        
        # Event Bus 구독 설정
        self._setup_event_subscriptions()
        
        logger.info("✓ 컴포넌트 연결 완료")
    
    def _setup_custom_state_handlers(self):
        """커스텀 상태 전환 핸들러 설정"""
        
        @self.state_machine.on_transition(PositionState.ACTIVE, PositionState.MODIFYING)
        async def on_position_modifying(context, transition):
            """포지션 수정 시작"""
            logger.info(f"포지션 수정 시작: {context.position_id}")
            
            # Event Bus로 이벤트 발행
            from src.core.event_bus import publish_event, EventCategory, EventPriority
            await publish_event(
                "POSITION_MODIFYING",
                {
                    'position_id': context.position_id,
                    'symbol': context.symbol,
                    'reason': transition.reason
                },
                EventCategory.POSITION,
                EventPriority.MEDIUM
            )
        
        @self.state_machine.on_entry(PositionState.RECONCILING)
        async def on_reconciling_entry(context):
            """정합성 확인 상태 진입"""
            logger.info(f"정합성 확인 시작: {context.position_id}")
            
            # Reconciliation Engine 트리거
            if self.reconciliation_engine:
                await self.reconciliation_engine.force_reconcile(context.symbol)
    
    async def _migrate_existing_positions(self):
        """기존 포지션들에 대한 상태 컨텍스트 생성"""
        if not hasattr(self.trading_system, 'position_manager'):
            return
        
        migrated_count = 0
        positions = self.trading_system.position_manager.get_all_positions()
        
        for symbol, position in positions.items():
            if position.status == 'ACTIVE':
                # 상태 컨텍스트가 없으면 생성
                if not self.state_machine.get_context(position.position_id):
                    initial_state = PositionState.ACTIVE
                    
                    # 상태에 따른 초기 상태 설정
                    if position.status == 'MODIFIED':
                        initial_state = PositionState.MODIFIED
                    elif position.status == 'PAUSED':
                        initial_state = PositionState.PAUSED
                    
                    self.state_machine.create_position_context(
                        position.position_id,
                        symbol,
                        initial_state,
                        {
                            'migrated': True,
                            'original_status': position.status,
                            'is_manual': position.is_manual
                        }
                    )
                    migrated_count += 1
        
        if migrated_count > 0:
            logger.info(f"기존 포지션 {migrated_count}개에 대한 상태 컨텍스트 생성 완료")
    
    def _setup_event_subscriptions(self):
        """Event Bus 구독 설정"""
        from src.core.event_bus import subscribe_event, PositionEvents, TradeEvents
        
        # 포지션 이벤트 구독
        @subscribe_event(PositionEvents.OPENED)
        async def on_position_opened_event(event):
            """포지션 오픈 이벤트 처리"""
            position_id = event.data.get('position_id')
            if position_id and not self.state_machine.get_context(position_id):
                # 새 포지션에 대한 상태 컨텍스트 생성
                self.state_machine.create_position_context(
                    position_id,
                    event.data.get('symbol'),
                    PositionState.ACTIVE,
                    {'source': event.source}
                )
        
        @subscribe_event(PositionEvents.CLOSED)
        async def on_position_closed_event(event):
            """포지션 종료 이벤트 처리"""
            position_id = event.data.get('position_id')
            if position_id:
                # 상태를 CLOSED로 전환
                await self.state_machine.transition(
                    position_id,
                    PositionState.CLOSED,
                    event.data.get('reason', 'Unknown')
                )
        
        @subscribe_event(PositionEvents.SYNC_ERROR)
        async def on_sync_error_event(event):
            """동기화 오류 이벤트 처리"""
            # Reconciliation Engine 트리거
            if self.reconciliation_engine:
                symbol = event.data.get('symbol')
                if symbol:
                    await self.reconciliation_engine.force_reconcile(symbol)
    
    async def _on_position_created(self, event_data: Dict[str, Any]):
        """포지션 생성 이벤트 핸들러"""
        from src.core.event_bus import publish_event, PositionEvents, EventCategory, EventPriority
        
        # Event Bus로 이벤트 발행
        await publish_event(
            PositionEvents.OPENED,
            event_data,
            EventCategory.POSITION,
            EventPriority.HIGH
        )
        
        # State Machine에 컨텍스트 생성
        position = event_data.get('position')
        if position:
            self.state_machine.create_position_context(
                position['position_id'],
                position['symbol'],
                PositionState.ACTIVE,
                {'strategy': position.get('strategy_name')}
            )
    
    async def _on_position_closed(self, event_data: Dict[str, Any]):
        """포지션 종료 이벤트 핸들러"""
        from src.core.event_bus import publish_event, PositionEvents, EventCategory, EventPriority
        
        # Event Bus로 이벤트 발행
        await publish_event(
            PositionEvents.CLOSED,
            event_data,
            EventCategory.POSITION,
            EventPriority.HIGH
        )
        
        # State Machine 상태 전환
        position_id = event_data.get('position', {}).get('position_id')
        if position_id:
            await self.state_machine.transition(
                position_id,
                PositionState.CLOSED,
                event_data.get('reason', 'Unknown')
            )
    
    async def _on_position_updated(self, event_data: Dict[str, Any]):
        """포지션 업데이트 이벤트 핸들러"""
        from src.core.event_bus import publish_event, PositionEvents, EventCategory, EventPriority
        
        # Event Bus로 이벤트 발행
        await publish_event(
            PositionEvents.MODIFIED,
            event_data,
            EventCategory.POSITION,
            EventPriority.MEDIUM
        )
        
        # State Machine 상태 업데이트
        position_id = event_data.get('position', {}).get('position_id')
        change_type = event_data.get('change_type')
        
        if position_id and change_type == 'size_change':
            # 크기 변경은 MODIFYING 상태로
            context = self.state_machine.get_context(position_id)
            if context and context.current_state == PositionState.ACTIVE:
                await self.state_machine.transition(
                    position_id,
                    PositionState.MODIFYING,
                    f"Size changed: {event_data.get('change_data', {})}"
                )
                # 다시 ACTIVE로 전환
                await self.state_machine.transition(
                    position_id,
                    PositionState.ACTIVE,
                    "Modification completed"
                )
    
    async def shutdown(self):
        """Phase 2 컴포넌트 종료"""
        if not self._initialized:
            return
        
        logger.info("Phase 2 컴포넌트 종료 중...")
        
        try:
            # Reconciliation Engine 종료
            if self.reconciliation_engine:
                await self.reconciliation_engine.stop()
            
            # State Machine 정리
            if self.state_machine:
                # 종료 상태 포지션 정리
                self.state_machine.cleanup_terminal_states(older_than_hours=0)
            
            # Event Bus 종료
            if self.event_bus_integration:
                await self.event_bus_integration.shutdown()
            
            self._initialized = False
            logger.info("✓ Phase 2 컴포넌트 종료 완료")
            
        except Exception as e:
            logger.error(f"Phase 2 종료 중 오류: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Phase 2 컴포넌트 상태 조회"""
        status = {
            'initialized': self._initialized,
            'components': {
                'event_bus': None,
                'state_machine': None,
                'reconciliation_engine': None
            }
        }
        
        if self.event_bus:
            status['components']['event_bus'] = self.event_bus.get_stats()
        
        if self.state_machine:
            status['components']['state_machine'] = self.state_machine.get_state_summary()
        
        if self.reconciliation_engine:
            status['components']['reconciliation_engine'] = self.reconciliation_engine.get_stats()
        
        return status
    
    async def force_reconciliation(self, symbol: Optional[str] = None):
        """강제 정합성 확인 실행"""
        if not self.reconciliation_engine:
            logger.error("Reconciliation Engine이 초기화되지 않았습니다")
            return None
        
        if symbol:
            # 특정 심볼만
            return await self.reconciliation_engine.force_reconcile(symbol)
        else:
            # 전체
            return await self.reconciliation_engine.reconcile(
                ReconciliationType.ON_DEMAND
            )
    
    def get_position_state(self, position_id: str) -> Optional[str]:
        """포지션 상태 조회"""
        if not self.state_machine:
            return None
        
        context = self.state_machine.get_context(position_id)
        return context.current_state.value if context else None
    
    def get_discrepancy_history(self, symbol: Optional[str] = None, limit: int = 50):
        """불일치 이력 조회"""
        if not self.reconciliation_engine:
            return []
        
        return self.reconciliation_engine.get_discrepancy_history(symbol, limit)


# Phase 2 통합을 위한 헬퍼 함수
async def setup_phase2_components(trading_system) -> Optional[Phase2Integration]:
    """Phase 2 컴포넌트 설정 헬퍼"""
    try:
        # Phase 2 Integration 생성
        phase2 = Phase2Integration(trading_system)
        
        # 초기화
        success = await phase2.initialize()
        
        if success:
            logger.info("✅ Phase 2 컴포넌트 설정 완료")
            return phase2
        else:
            logger.error("Phase 2 컴포넌트 설정 실패")
            return None
            
    except Exception as e:
        logger.error(f"Phase 2 설정 중 오류: {e}")
        return None
