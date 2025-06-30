"""
Event Bus Integration Adapter
기존 시스템과 새로운 Event Bus를 연결하는 어댑터
"""

import asyncio
from typing import Dict, Any, Optional
from datetime import datetime

from src.core.event_bus import (
    AsyncEventBus, Event, EventHandler, EventCategory, EventPriority,
    SystemEvents, PositionEvents, TradeEvents, MarketEvents,
    get_event_bus, publish_event
)
from src.core.event_logger import get_event_logger
from src.utils.logger import setup_logger
from src.utils.config_manager import ConfigManager

logger = setup_logger(__name__)


class EventLoggerAdapter(EventHandler):
    """기존 Event Logger를 Event Bus에 연결하는 어댑터"""
    
    def __init__(self):
        super().__init__("event_logger_adapter")
        self.event_logger = get_event_logger()
        
        # 모든 이벤트 구독
        self.subscribe([
            SystemEvents.STARTUP, SystemEvents.SHUTDOWN, SystemEvents.ERROR,
            PositionEvents.OPENED, PositionEvents.CLOSED, PositionEvents.MODIFIED,
            TradeEvents.SIGNAL_GENERATED, TradeEvents.ORDER_PLACED, TradeEvents.ORDER_FILLED,
            MarketEvents.CANDLE_CLOSED
        ])
    
    async def handle_event(self, event: Event):
        """Event Bus 이벤트를 Event Logger 형식으로 변환"""
        try:
            # 우선순위를 심각도로 매핑
            severity_map = {
                EventPriority.CRITICAL: "CRITICAL",
                EventPriority.HIGH: "ERROR",
                EventPriority.MEDIUM: "WARNING",
                EventPriority.LOW: "INFO"
            }
            
            await self.event_logger.log_event(
                event_type=event.event_type,
                event_data={
                    **event.data,
                    'source': event.source,
                    'category': event.category.name,
                    'event_id': event.event_id
                },
                severity=severity_map.get(event.priority, "INFO")
            )
        except Exception as e:
            logger.error(f"EventLogger 어댑터 오류: {e}")


class NotificationAdapter(EventHandler):
    """알림 시스템을 Event Bus에 연결하는 어댑터"""
    
    def __init__(self, notification_manager):
        super().__init__("notification_adapter")
        self.notification_manager = notification_manager
        
        # 알림이 필요한 이벤트 구독
        self.subscribe([
            SystemEvents.STARTUP, SystemEvents.SHUTDOWN, SystemEvents.ERROR,
            PositionEvents.OPENED, PositionEvents.CLOSED, PositionEvents.MODIFIED,
            PositionEvents.PARTIAL_CLOSE, PositionEvents.SYNC_ERROR,
            TradeEvents.ORDER_FAILED
        ])
    
    async def handle_event(self, event: Event):
        """Event Bus 이벤트를 알림으로 변환"""
        try:
            # 이벤트 타입별 알림 설정
            notification_config = self._get_notification_config(event)
            
            if notification_config:
                await self.notification_manager.send_alert(
                    event_type=notification_config['type'],
                    title=notification_config['title'],
                    message=notification_config['message'],
                    data=event.data,
                    event_id=event.event_id
                )
        except Exception as e:
            logger.error(f"Notification 어댑터 오류: {e}")
    
    def _get_notification_config(self, event: Event) -> Optional[Dict[str, str]]:
        """이벤트에 따른 알림 설정 반환"""
        configs = {
            SystemEvents.STARTUP: {
                'type': 'SYSTEM_ERROR',  # CRITICAL 레벨
                'title': '🚀 시스템 시작',
                'message': '트레이딩 시스템이 시작되었습니다.'
            },
            SystemEvents.SHUTDOWN: {
                'type': 'SYSTEM_STOPPED',
                'title': '🛑 시스템 종료',
                'message': '트레이딩 시스템이 종료되었습니다.'
            },
            SystemEvents.ERROR: {
                'type': 'SYSTEM_ERROR',
                'title': '❌ 시스템 오류',
                'message': f"오류 발생: {event.data.get('error', 'Unknown error')}"
            },
            PositionEvents.OPENED: {
                'type': 'POSITION_OPENED',
                'title': f"🔵 {event.data.get('symbol', 'Unknown')} 포지션 진입",
                'message': self._format_position_message(event.data)
            },
            PositionEvents.CLOSED: {
                'type': 'POSITION_CLOSED',
                'title': f"🔴 {event.data.get('symbol', 'Unknown')} 포지션 청산",
                'message': self._format_position_message(event.data)
            },
            PositionEvents.MODIFIED: {
                'type': 'POSITION_MODIFIED',
                'title': f"✏️ {event.data.get('symbol', 'Unknown')} 포지션 변경",
                'message': self._format_position_message(event.data)
            },
            PositionEvents.PARTIAL_CLOSE: {
                'type': 'PARTIAL_CLOSE',
                'title': f"✂️ {event.data.get('symbol', 'Unknown')} 부분 청산",
                'message': self._format_partial_close_message(event.data)
            },
            PositionEvents.SYNC_ERROR: {
                'type': 'POSITION_SYNC_ERROR',
                'title': '⚠️ 포지션 동기화 오류',
                'message': f"동기화 오류: {event.data.get('error', 'Unknown error')}"
            },
            TradeEvents.ORDER_FAILED: {
                'type': 'SYSTEM_ERROR',
                'title': '❌ 주문 실패',
                'message': f"주문 실패: {event.data.get('reason', 'Unknown reason')}"
            }
        }
        
        return configs.get(event.event_type)
    
    def _format_position_message(self, data: Dict[str, Any]) -> str:
        """포지션 정보 메시지 포맷팅"""
        return (
            f"<b>방향:</b> {data.get('side', 'N/A')}\n"
            f"<b>수량:</b> {data.get('size', 0):.4f}\n"
            f"<b>가격:</b> ${data.get('price', 0):.2f}\n"
            f"<b>레버리지:</b> {data.get('leverage', 1)}x"
        )
    
    def _format_partial_close_message(self, data: Dict[str, Any]) -> str:
        """부분 청산 메시지 포맷팅"""
        return (
            f"<b>청산 수량:</b> {data.get('closed_size', 0):.4f}\n"
            f"<b>남은 수량:</b> {data.get('remaining_size', 0):.4f}\n"
            f"<b>청산가:</b> ${data.get('exit_price', 0):.2f}"
        )


class EventBusIntegration:
    """Event Bus를 기존 시스템에 통합하는 메인 클래스"""
    
    def __init__(self):
        self.event_bus = get_event_bus()
        self.adapters = []
        self._initialized = False
        
        # Config Manager 로드
        self.config_manager = ConfigManager()
        self.config = self.config_manager.config
    
    async def initialize(self, notification_manager=None):
        """통합 초기화"""
        if self._initialized:
            logger.warning("Event Bus Integration이 이미 초기화되었습니다")
            return
        
        try:
            # Event Bus 설정 읽기
            event_bus_config = self.config.get('phase2', {}).get('event_bus', {})
            num_workers = event_bus_config.get('num_workers', 3)
            
            # Event Bus 시작
            await self.event_bus.start(num_workers=num_workers)
            logger.info(f"Event Bus 시작 - 워커 수: {num_workers}")
            
            # Event Logger 어댑터 추가
            logger_adapter = EventLoggerAdapter()
            self.adapters.append(logger_adapter)
            
            # Notification 어댑터 추가 (있는 경우)
            if notification_manager:
                notification_adapter = NotificationAdapter(notification_manager)
                self.adapters.append(notification_adapter)
            
            # 미들웨어 추가
            self.event_bus.add_middleware(self._event_validation_middleware)
            
            # 에러 핸들러 추가
            self.event_bus.add_error_handler(self._handle_event_error)
            
            self._initialized = True
            logger.info("Event Bus Integration 초기화 완료")
            
            # 시작 이벤트 발행
            await publish_event(
                SystemEvents.STARTUP,
                {'timestamp': datetime.now().isoformat()},
                EventCategory.SYSTEM,
                EventPriority.HIGH
            )
            
        except Exception as e:
            logger.error(f"Event Bus Integration 초기화 실패: {e}")
            raise
    
    async def shutdown(self):
        """통합 종료"""
        if not self._initialized:
            return
        
        try:
            # 종료 이벤트 발행
            await publish_event(
                SystemEvents.SHUTDOWN,
                {'timestamp': datetime.now().isoformat()},
                EventCategory.SYSTEM,
                EventPriority.HIGH
            )
            
            # Event Bus 정지
            await self.event_bus.stop()
            
            self._initialized = False
            logger.info("Event Bus Integration 종료 완료")
            
        except Exception as e:
            logger.error(f"Event Bus Integration 종료 실패: {e}")
    
    def _event_validation_middleware(self, event: Event) -> Event:
        """이벤트 검증 미들웨어"""
        # 필수 필드 검증
        if not event.event_type:
            raise ValueError("event_type은 필수입니다")
        
        # 타임스탬프 추가 (없는 경우)
        if 'timestamp' not in event.data:
            event.data['timestamp'] = datetime.now().isoformat()
        
        return event
    
    async def _handle_event_error(self, error_context: Dict[str, Any]):
        """이벤트 에러 처리"""
        logger.error(f"Event Bus 에러: {error_context}")
        
        # 심각한 에러인 경우 알림
        if error_context.get('event', {}).get('priority') == 'CRITICAL':
            await publish_event(
                SystemEvents.ERROR,
                {
                    'error': error_context['error'],
                    'error_type': error_context['error_type'],
                    'event_type': error_context.get('event', {}).get('event_type', 'Unknown')
                },
                EventCategory.SYSTEM,
                EventPriority.CRITICAL
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 반환"""
        return self.event_bus.get_stats()


# 전역 통합 인스턴스
_integration: Optional[EventBusIntegration] = None


def get_event_bus_integration() -> EventBusIntegration:
    """싱글톤 통합 인스턴스 반환"""
    global _integration
    if _integration is None:
        _integration = EventBusIntegration()
    return _integration


# 기존 시스템 호환성을 위한 헬퍼 함수들
async def emit_position_event(event_type: str, position_data: Dict[str, Any]):
    """포지션 이벤트 발행 (기존 시스템 호환)"""
    event_map = {
        'opened': PositionEvents.OPENED,
        'closed': PositionEvents.CLOSED,
        'modified': PositionEvents.MODIFIED,
        'partial_close': PositionEvents.PARTIAL_CLOSE
    }
    
    event_type_mapped = event_map.get(event_type, event_type)
    
    await publish_event(
        event_type_mapped,
        position_data,
        EventCategory.POSITION,
        EventPriority.HIGH
    )


async def emit_trade_event(event_type: str, trade_data: Dict[str, Any]):
    """거래 이벤트 발행 (기존 시스템 호환)"""
    event_map = {
        'signal': TradeEvents.SIGNAL_GENERATED,
        'order_placed': TradeEvents.ORDER_PLACED,
        'order_filled': TradeEvents.ORDER_FILLED,
        'order_cancelled': TradeEvents.ORDER_CANCELLED,
        'order_failed': TradeEvents.ORDER_FAILED
    }
    
    event_type_mapped = event_map.get(event_type, event_type)
    
    await publish_event(
        event_type_mapped,
        trade_data,
        EventCategory.TRADE,
        EventPriority.HIGH
    )


async def emit_system_event(event_type: str, data: Dict[str, Any], 
                           priority: EventPriority = EventPriority.MEDIUM):
    """시스템 이벤트 발행 (기존 시스템 호환)"""
    await publish_event(
        event_type,
        data,
        EventCategory.SYSTEM,
        priority
    )
