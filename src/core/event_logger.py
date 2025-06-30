"""
Simple Event Logger for AlbraTrading System
이벤트 기반 아키텍처의 첫 단계 - 모든 중요 이벤트를 로깅
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from collections import deque
import aiofiles
import os

from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class EventLogger:
    """
    심플한 이벤트 로거
    - 파일 기반 저장 (나중에 DB로 마이그레이션 가능)
    - 메모리 버퍼링으로 성능 최적화
    - 중요 이벤트 즉시 알림
    """
    
    def __init__(self, event_dir: str = "data/events"):
        self.event_dir = event_dir
        self.buffer = deque(maxlen=1000)  # 메모리 버퍼
        self.critical_events = []  # 즉시 처리할 이벤트 타입
        self._running = False
        self._flush_task = None
        
        # 이벤트 디렉토리 생성
        os.makedirs(event_dir, exist_ok=True)
        
        # 중요 이벤트 타입 정의
        self.critical_event_types = {
            'POSITION_REGISTRATION_FAILED',
            'POSITION_SYNC_ERROR',
            'API_ERROR',
            'STRATEGY_ERROR',
            'SYSTEM_ERROR'
        }
    
    async def start(self):
        """이벤트 로거 시작"""
        self._running = True
        self._flush_task = asyncio.create_task(self._auto_flush())
        logger.info("Event Logger 시작됨")
    
    async def stop(self):
        """이벤트 로거 중지"""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
        await self.flush()  # 남은 이벤트 저장
        logger.info("Event Logger 중지됨")
    
    async def log_event(self, 
                       event_type: str, 
                       event_data: Dict[str, Any],
                       severity: str = "INFO") -> str:
        """
        이벤트 로깅
        
        Args:
            event_type: 이벤트 타입 (예: POSITION_OPENED, ORDER_PLACED)
            event_data: 이벤트 상세 데이터
            severity: INFO, WARNING, ERROR, CRITICAL
            
        Returns:
            event_id: 생성된 이벤트 ID
        """
        event = {
            'event_id': self._generate_event_id(),
            'timestamp': datetime.now().isoformat(),
            'type': event_type,
            'severity': severity,
            'data': event_data
        }
        
        # 버퍼에 추가
        self.buffer.append(event)
        
        # 중요 이벤트는 즉시 저장
        if event_type in self.critical_event_types or severity in ['ERROR', 'CRITICAL']:
            await self._save_event(event)
            logger.warning(f"중요 이벤트 기록: {event_type} - {event_data}")
        
        return event['event_id']
    
    async def get_recent_events(self, 
                               event_type: Optional[str] = None,
                               limit: int = 100) -> List[Dict]:
        """최근 이벤트 조회"""
        events = list(self.buffer)
        
        if event_type:
            events = [e for e in events if e['type'] == event_type]
        
        return events[-limit:]
    
    async def get_event_summary(self) -> Dict[str, Any]:
        """이벤트 요약 통계"""
        events = list(self.buffer)
        
        summary = {
            'total_events': len(events),
            'by_type': {},
            'by_severity': {},
            'recent_errors': []
        }
        
        for event in events:
            # 타입별 카운트
            event_type = event['type']
            summary['by_type'][event_type] = summary['by_type'].get(event_type, 0) + 1
            
            # 심각도별 카운트
            severity = event['severity']
            summary['by_severity'][severity] = summary['by_severity'].get(severity, 0) + 1
            
            # 최근 에러
            if severity in ['ERROR', 'CRITICAL']:
                summary['recent_errors'].append({
                    'type': event_type,
                    'timestamp': event['timestamp'],
                    'message': event['data'].get('message', 'No message')
                })
        
        # 최근 5개 에러만
        summary['recent_errors'] = summary['recent_errors'][-5:]
        
        return summary
    
    async def _auto_flush(self):
        """주기적으로 버퍼를 파일로 저장"""
        while self._running:
            try:
                await asyncio.sleep(60)  # 1분마다
                await self.flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Auto flush 실패: {e}")
    
    async def flush(self):
        """버퍼의 이벤트를 파일로 저장"""
        if not self.buffer:
            return
        
        # 현재 날짜로 파일명 생성
        filename = f"events_{datetime.now().strftime('%Y%m%d')}.jsonl"
        filepath = os.path.join(self.event_dir, filename)
        
        # 버퍼 내용 복사 후 클리어
        events_to_save = list(self.buffer)
        self.buffer.clear()
        
        # 파일에 추가
        try:
            async with aiofiles.open(filepath, 'a') as f:
                for event in events_to_save:
                    await f.write(json.dumps(event, ensure_ascii=False) + '\n')
            
            logger.debug(f"{len(events_to_save)}개 이벤트 저장됨")
        except Exception as e:
            logger.error(f"이벤트 저장 실패: {e}")
            # 실패시 버퍼에 다시 추가
            self.buffer.extend(events_to_save)
    
    async def _save_event(self, event: Dict):
        """단일 이벤트 즉시 저장"""
        filename = f"events_{datetime.now().strftime('%Y%m%d')}.jsonl"
        filepath = os.path.join(self.event_dir, filename)
        
        try:
            async with aiofiles.open(filepath, 'a') as f:
                await f.write(json.dumps(event, ensure_ascii=False) + '\n')
        except Exception as e:
            logger.error(f"이벤트 즉시 저장 실패: {e}")
    
    def _generate_event_id(self) -> str:
        """유니크한 이벤트 ID 생성"""
        from uuid import uuid4
        return f"evt_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid4())[:8]}"


# 전역 이벤트 로거 인스턴스
_event_logger = None


def get_event_logger() -> EventLogger:
    """싱글톤 이벤트 로거 반환"""
    global _event_logger
    if _event_logger is None:
        _event_logger = EventLogger()
    return _event_logger


async def log_event(event_type: str, event_data: Dict[str, Any], severity: str = "INFO"):
    """간편한 이벤트 로깅 함수"""
    logger = get_event_logger()
    return await logger.log_event(event_type, event_data, severity)
