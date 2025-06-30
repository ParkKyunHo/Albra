"""
Simple Event Bus for AlbraTrading System
이벤트 기반 아키텍처의 핵심 - Publisher-Subscriber 패턴 구현
"""

import asyncio
import logging
from typing import Dict, List, Callable, Any, Optional, Union, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from collections import defaultdict
import weakref
import inspect
from functools import wraps

from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class EventPriority(Enum):
    """이벤트 우선순위"""
    CRITICAL = 1  # 시스템 오류, 긴급 처리
    HIGH = 2      # 포지션 변경, 거래 신호
    MEDIUM = 3    # 일반 업데이트
    LOW = 4       # 로깅, 모니터링


class EventCategory(Enum):
    """이벤트 카테고리"""
    SYSTEM = auto()        # 시스템 이벤트
    POSITION = auto()      # 포지션 관련
    TRADE = auto()         # 거래 실행
    MARKET = auto()        # 시장 데이터
    STRATEGY = auto()      # 전략 신호
    NOTIFICATION = auto()  # 알림
    SAFETY = auto()        # 안전 체크


@dataclass
class Event:
    """이벤트 데이터 클래스"""
    event_type: str
    category: EventCategory
    data: Dict[str, Any]
    priority: EventPriority = EventPriority.MEDIUM
    source: str = "unknown"
    event_id: str = field(default_factory=lambda: f"evt_{datetime.now().timestamp()}")
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 변환"""
        return {
            'event_id': self.event_id,
            'event_type': self.event_type,
            'category': self.category.name,
            'priority': self.priority.name,
            'source': self.source,
            'timestamp': self.timestamp.isoformat(),
            'data': self.data,
            'metadata': self.metadata
        }


class EventHandler:
    """이벤트 핸들러 기본 클래스"""
    
    def __init__(self, handler_id: str = None):
        self.handler_id = handler_id or f"handler_{id(self)}"
        self.subscriptions: Set[str] = set()
        self._active = True
    
    async def handle_event(self, event: Event) -> None:
        """이벤트 처리 (오버라이드 필요)"""
        raise NotImplementedError
    
    def can_handle(self, event: Event) -> bool:
        """이벤트 처리 가능 여부"""
        return self._active and event.event_type in self.subscriptions
    
    def subscribe(self, event_types: Union[str, List[str]]):
        """이벤트 구독"""
        if isinstance(event_types, str):
            event_types = [event_types]
        self.subscriptions.update(event_types)
    
    def unsubscribe(self, event_types: Union[str, List[str]]):
        """구독 취소"""
        if isinstance(event_types, str):
            event_types = [event_types]
        self.subscriptions.difference_update(event_types)
    
    def deactivate(self):
        """핸들러 비활성화"""
        self._active = False


class AsyncEventBus:
    """비동기 이벤트 버스 - 중앙 이벤트 라우터"""
    
    def __init__(self, max_queue_size: int = 1000):
        # 이벤트 큐 (우선순위별)
        self.event_queues: Dict[EventPriority, asyncio.Queue] = {
            priority: asyncio.Queue(maxsize=max_queue_size // 4)
            for priority in EventPriority
        }
        
        # 핸들러 저장소 (이벤트 타입별, 약한 참조 사용)
        self._handlers: Dict[str, List[weakref.ref]] = defaultdict(list)
        
        # 통계
        self.stats = {
            'events_published': 0,
            'events_processed': 0,
            'events_failed': 0,
            'events_dropped': 0,
            'processing_time_ms': []
        }
        
        # 실행 상태
        self._running = False
        self._workers: List[asyncio.Task] = []
        
        # 이벤트 필터
        self._event_filters: List[Callable[[Event], bool]] = []
        
        # 미들웨어
        self._middlewares: List[Callable] = []
        
        # 에러 핸들러
        self._error_handlers: List[Callable] = []
        
        logger.info("Event Bus 초기화 완료")
    
    async def start(self, num_workers: int = 3):
        """이벤트 버스 시작"""
        if self._running:
            logger.warning("Event Bus가 이미 실행 중입니다")
            return
        
        self._running = True
        
        # 워커 태스크 생성
        for i in range(num_workers):
            for priority in EventPriority:
                worker = asyncio.create_task(
                    self._process_events(priority, worker_id=f"worker_{priority.name}_{i}")
                )
                self._workers.append(worker)
        
        logger.info(f"Event Bus 시작: {len(self._workers)}개 워커")
    
    async def stop(self):
        """이벤트 버스 정지"""
        logger.info("Event Bus 정지 중...")
        self._running = False
        
        # 모든 워커 정지
        for worker in self._workers:
            worker.cancel()
        
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        
        self._workers.clear()
        
        # 큐 비우기
        for queue in self.event_queues.values():
            while not queue.empty():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
        
        logger.info("Event Bus 정지 완료")
    
    async def publish(self, event: Union[Event, Dict[str, Any]], 
                     event_type: str = None, **kwargs) -> str:
        """이벤트 발행"""
        try:
            # Event 객체 생성
            if isinstance(event, dict):
                # 딕셔너리에서 Event 생성
                event_data = event
                event = Event(
                    event_type=event_type or event_data.get('event_type', 'unknown'),
                    category=EventCategory[event_data.get('category', 'SYSTEM')],
                    data=event_data.get('data', {}),
                    priority=EventPriority[event_data.get('priority', 'MEDIUM')],
                    source=event_data.get('source', 'unknown'),
                    **kwargs
                )
            
            # 필터 적용
            for filter_func in self._event_filters:
                if not filter_func(event):
                    logger.debug(f"이벤트 필터링됨: {event.event_type}")
                    return None
            
            # 미들웨어 적용
            for middleware in self._middlewares:
                event = await self._apply_middleware(middleware, event)
                if event is None:
                    return None
            
            # 큐에 추가
            queue = self.event_queues[event.priority]
            
            try:
                queue.put_nowait(event)
                self.stats['events_published'] += 1
                logger.debug(f"이벤트 발행: {event.event_type} (우선순위: {event.priority.name})")
                
            except asyncio.QueueFull:
                # 낮은 우선순위 큐로 재시도
                if event.priority != EventPriority.LOW:
                    lower_priority = EventPriority(event.priority.value + 1)
                    event.priority = lower_priority
                    self.event_queues[lower_priority].put_nowait(event)
                    logger.warning(f"큐 가득: {event.event_type} 우선순위 낮춤")
                else:
                    self.stats['events_dropped'] += 1
                    logger.error(f"이벤트 드롭: {event.event_type}")
                    raise
            
            return event.event_id
            
        except Exception as e:
            logger.error(f"이벤트 발행 실패: {e}")
            await self._handle_error(e, event)
            return None
    
    def subscribe(self, event_type: str, handler: Union[EventHandler, Callable],
                 priority: EventPriority = None) -> str:
        """이벤트 구독"""
        try:
            # 함수를 EventHandler로 래핑
            if not isinstance(handler, EventHandler):
                handler = self._wrap_function_handler(handler, event_type)
            
            # 핸들러 등록
            handler_ref = weakref.ref(handler, self._create_cleanup_callback(event_type))
            self._handlers[event_type].append(handler_ref)
            
            # 우선순위별 정렬 (선택적)
            if priority:
                # 우선순위 메타데이터 저장
                handler.priority = priority
            
            logger.info(f"이벤트 구독: {event_type} → {handler.handler_id}")
            return handler.handler_id
            
        except Exception as e:
            logger.error(f"구독 실패: {e}")
            return None
    
    def unsubscribe(self, event_type: str, handler_id: str):
        """구독 취소"""
        if event_type not in self._handlers:
            return
        
        # 핸들러 찾아서 제거
        self._handlers[event_type] = [
            ref for ref in self._handlers[event_type]
            if ref() and ref().handler_id != handler_id
        ]
    
    def add_filter(self, filter_func: Callable[[Event], bool]):
        """이벤트 필터 추가"""
        self._event_filters.append(filter_func)
    
    def add_middleware(self, middleware: Callable):
        """미들웨어 추가"""
        self._middlewares.append(middleware)
    
    def add_error_handler(self, handler: Callable):
        """에러 핸들러 추가"""
        self._error_handlers.append(handler)
    
    async def _process_events(self, priority: EventPriority, worker_id: str):
        """이벤트 처리 워커"""
        queue = self.event_queues[priority]
        
        while self._running:
            try:
                # 타임아웃으로 대기 (정지 시 빠른 종료)
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
                
                start_time = datetime.now()
                await self._dispatch_event(event)
                
                # 처리 시간 기록
                processing_time = (datetime.now() - start_time).total_seconds() * 1000
                self.stats['processing_time_ms'].append(processing_time)
                
                # 통계는 최근 1000개만 유지
                if len(self.stats['processing_time_ms']) > 1000:
                    self.stats['processing_time_ms'] = self.stats['processing_time_ms'][-1000:]
                
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"워커 {worker_id} 오류: {e}")
                await self._handle_error(e, None)
    
    async def _dispatch_event(self, event: Event):
        """이벤트를 핸들러에 전달"""
        try:
            handlers = self._handlers.get(event.event_type, [])
            
            if not handlers:
                logger.debug(f"핸들러 없음: {event.event_type}")
                return
            
            # 유효한 핸들러만 추출
            valid_handlers = []
            for handler_ref in handlers:
                handler = handler_ref()
                if handler and handler.can_handle(event):
                    valid_handlers.append(handler)
            
            # 우선순위 정렬 (있는 경우)
            valid_handlers.sort(
                key=lambda h: getattr(h, 'priority', EventPriority.MEDIUM).value
            )
            
            # 병렬 처리
            tasks = [
                self._safe_handle_event(handler, event)
                for handler in valid_handlers
            ]
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            
            self.stats['events_processed'] += 1
            
        except Exception as e:
            self.stats['events_failed'] += 1
            logger.error(f"이벤트 디스패치 실패: {e}")
            await self._handle_error(e, event)
    
    async def _safe_handle_event(self, handler: EventHandler, event: Event):
        """안전한 이벤트 처리"""
        try:
            await handler.handle_event(event)
        except Exception as e:
            logger.error(f"핸들러 {handler.handler_id} 처리 실패: {e}")
            await self._handle_error(e, event, handler)
    
    async def _apply_middleware(self, middleware: Callable, event: Event) -> Optional[Event]:
        """미들웨어 적용"""
        try:
            if asyncio.iscoroutinefunction(middleware):
                return await middleware(event)
            else:
                return middleware(event)
        except Exception as e:
            logger.error(f"미들웨어 오류: {e}")
            return event  # 오류 시 원본 이벤트 반환
    
    async def _handle_error(self, error: Exception, event: Optional[Event], 
                          handler: Optional[EventHandler] = None):
        """에러 처리"""
        error_context = {
            'error': str(error),
            'error_type': type(error).__name__,
            'event': event.to_dict() if event else None,
            'handler': handler.handler_id if handler else None,
            'timestamp': datetime.now().isoformat()
        }
        
        # 에러 핸들러 실행
        for error_handler in self._error_handlers:
            try:
                if asyncio.iscoroutinefunction(error_handler):
                    await error_handler(error_context)
                else:
                    error_handler(error_context)
            except Exception as e:
                logger.error(f"에러 핸들러 실패: {e}")
    
    def _wrap_function_handler(self, func: Callable, event_type: str) -> EventHandler:
        """일반 함수를 EventHandler로 래핑"""
        
        class FunctionHandler(EventHandler):
            def __init__(self, func, event_type):
                super().__init__(f"func_{func.__name__}_{id(func)}")
                self.func = func
                self.subscribe(event_type)
            
            async def handle_event(self, event: Event):
                if asyncio.iscoroutinefunction(self.func):
                    await self.func(event)
                else:
                    self.func(event)
        
        return FunctionHandler(func, event_type)
    
    def _create_cleanup_callback(self, event_type: str):
        """약한 참조 정리 콜백"""
        def cleanup(ref):
            if event_type in self._handlers:
                self._handlers[event_type] = [
                    r for r in self._handlers[event_type] if r is not ref
                ]
        return cleanup
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 반환"""
        avg_processing_time = 0
        if self.stats['processing_time_ms']:
            avg_processing_time = sum(self.stats['processing_time_ms']) / len(self.stats['processing_time_ms'])
        
        return {
            'events_published': self.stats['events_published'],
            'events_processed': self.stats['events_processed'],
            'events_failed': self.stats['events_failed'],
            'events_dropped': self.stats['events_dropped'],
            'avg_processing_time_ms': round(avg_processing_time, 2),
            'active_handlers': sum(len(handlers) for handlers in self._handlers.values()),
            'queue_sizes': {
                priority.name: queue.qsize()
                for priority, queue in self.event_queues.items()
            }
        }


# 전역 이벤트 버스 인스턴스
_event_bus: Optional[AsyncEventBus] = None


def get_event_bus() -> AsyncEventBus:
    """싱글톤 이벤트 버스 반환"""
    global _event_bus
    if _event_bus is None:
        _event_bus = AsyncEventBus()
    return _event_bus


# 편의 함수들
async def publish_event(event_type: str, data: Dict[str, Any], 
                       category: EventCategory = EventCategory.SYSTEM,
                       priority: EventPriority = EventPriority.MEDIUM,
                       source: str = None) -> str:
    """간편한 이벤트 발행"""
    bus = get_event_bus()
    
    # 호출자 정보 자동 추출
    if source is None:
        frame = inspect.currentframe().f_back
        source = f"{frame.f_code.co_filename}:{frame.f_lineno}"
    
    event = Event(
        event_type=event_type,
        category=category,
        data=data,
        priority=priority,
        source=source
    )
    
    return await bus.publish(event)


def subscribe_event(event_type: str, priority: EventPriority = None):
    """데코레이터를 통한 이벤트 구독"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            bus = get_event_bus()
            return bus.subscribe(event_type, func, priority)
        
        # 자동 구독 (모듈 로드 시)
        bus = get_event_bus()
        bus.subscribe(event_type, func, priority)
        
        return func
    return decorator


# 미리 정의된 이벤트 타입들
class SystemEvents:
    """시스템 이벤트 타입"""
    STARTUP = "SYSTEM_STARTUP"
    SHUTDOWN = "SYSTEM_SHUTDOWN"
    ERROR = "SYSTEM_ERROR"
    WARNING = "SYSTEM_WARNING"
    HEALTH_CHECK = "SYSTEM_HEALTH_CHECK"


class PositionEvents:
    """포지션 이벤트 타입"""
    OPENED = "POSITION_OPENED"
    CLOSED = "POSITION_CLOSED"
    MODIFIED = "POSITION_MODIFIED"
    PARTIAL_CLOSE = "POSITION_PARTIAL_CLOSE"
    SYNC_ERROR = "POSITION_SYNC_ERROR"
    STATE_CHANGED = "POSITION_STATE_CHANGED"


class TradeEvents:
    """거래 이벤트 타입"""
    SIGNAL_GENERATED = "TRADE_SIGNAL_GENERATED"
    ORDER_PLACED = "TRADE_ORDER_PLACED"
    ORDER_FILLED = "TRADE_ORDER_FILLED"
    ORDER_CANCELLED = "TRADE_ORDER_CANCELLED"
    ORDER_FAILED = "TRADE_ORDER_FAILED"


class MarketEvents:
    """시장 이벤트 타입"""
    PRICE_UPDATE = "MARKET_PRICE_UPDATE"
    CANDLE_CLOSED = "MARKET_CANDLE_CLOSED"
    VOLATILITY_SPIKE = "MARKET_VOLATILITY_SPIKE"
    LIQUIDITY_WARNING = "MARKET_LIQUIDITY_WARNING"
