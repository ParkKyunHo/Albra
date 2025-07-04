# src/utils/smart_notification_manager.py
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
from collections import OrderedDict
import logging

logger = logging.getLogger(__name__)

class AlertLevel(Enum):
    """알림 우선순위"""
    CRITICAL = 1  # 항상 알림
    HIGH = 2      # 중요 이벤트
    MEDIUM = 3    # 일반 정보 (요약)
    LOW = 4       # 로그만

class SmartNotificationManager:
    """스마트 알림 관리자"""
    
    def __init__(self, telegram_notifier=None, database_manager=None, config_manager=None):
        self.telegram = telegram_notifier
        self.db = database_manager
        
        # Config Manager에서 설정 로드
        if config_manager:
            notification_config = config_manager.config.get('smart_notification', {})
        else:
            # config_manager가 없으면 기본값 사용
            notification_config = {}
        
        # 알림 설정
        self.notification_rules = {
            AlertLevel.CRITICAL: {
                'telegram': True,
                'sound': True,
                'email': True,
                'immediate': True
            },
            AlertLevel.HIGH: {
                'telegram': True,
                'sound': False,
                'email': False,
                'immediate': True
            },
            AlertLevel.MEDIUM: {
                'telegram': True,  # 요약으로만
                'sound': False,
                'email': False,
                'immediate': False
            },
            AlertLevel.LOW: {
                'telegram': False,
                'sound': False,
                'email': False,
                'immediate': False
            }
        }
        
        # 이벤트별 알림 레벨
        self.event_levels = {
            # CRITICAL - 항상 알림
            'SYSTEM_ERROR': AlertLevel.CRITICAL,
            'SYSTEM_STOPPED': AlertLevel.CRITICAL,
            'SYSTEM_SHUTDOWN': AlertLevel.CRITICAL,  # 시스템 종료
            'SYSTEM_INITIALIZED': AlertLevel.HIGH,     # 시스템 초기화
            'SYSTEM_STARTED': AlertLevel.HIGH,         # 시스템 시작
            'LARGE_LOSS': AlertLevel.CRITICAL,
            'CRITICAL_ERROR': AlertLevel.CRITICAL,
            
            # HIGH - 중요 이벤트
            'USER_INTERVENTION': AlertLevel.HIGH,  # 수동 포지션 감지
            'POSITION_PAUSED': AlertLevel.HIGH,
            'POSITION_RESUMED': AlertLevel.HIGH,
            'MANUAL_POSITION_CLOSED': AlertLevel.HIGH,
            'PARTIAL_CLOSE': AlertLevel.HIGH,
            'LARGE_PROFIT': AlertLevel.HIGH,
            'POSITION_OPENED': AlertLevel.HIGH,  # 시스템 포지션 진입 (HIGH로 변경)
            'POSITION_CLOSED': AlertLevel.HIGH,  # 시스템 포지션 청산 (HIGH로 변경)
            'POSITION_SIZE_CHANGED': AlertLevel.HIGH,  # 포지션 크기 변경 (HIGH로 변경)
            'MANUAL_TRADE': AlertLevel.HIGH,  # 수동 거래 등록
            'MANUAL_CLOSE': AlertLevel.HIGH,  # 수동 거래 청산
            'MANUAL_MODIFIED': AlertLevel.HIGH,  # 수동 거래 수정
            'STATUS_REPORT': AlertLevel.HIGH,  # 시스템 상태 리포트 - 즉시 전송
            
            # MEDIUM - 일반 정보
            'POSITION_MODIFIED': AlertLevel.MEDIUM,
            
            # LOW - 로그만 (단, HEARTBEAT는 예외적으로 HIGH로 처리)
            'HEARTBEAT': AlertLevel.HIGH,  # 시스템 상태 리포트는 즉시 전송
            'SYNC_COMPLETED': AlertLevel.LOW,
            'TECHNICAL_SIGNAL': AlertLevel.LOW,
            'CACHE_UPDATED': AlertLevel.LOW
        }
        
        # 요약 버퍼
        self.summary_buffer = []
        self.summary_interval = notification_config.get('summary_interval', 3600)  # 기본값: 1시간
        self.last_summary_time = datetime.now()
        
        # 중복 방지
        self.recent_alerts = {}  # {alert_key: timestamp}
        self.alert_cooldown = notification_config.get('alert_cooldown', 300)  # 기본값: 5분
        
        # 이벤트 ID 기반 중복 방지 - OrderedDict로 개선
        self.event_ids = OrderedDict()  # {event_id: timestamp} - 처리된 이벤트 ID와 시간
        self.event_id_ttl = notification_config.get('event_id_ttl', 600)  # 기본값: 10분
        self.event_id_cleanup_task = None
        self.max_event_ids = notification_config.get('max_event_ids', 1000)  # 기본값: 1000개
        
        # 요약 작업
        self.summary_task = None
        
        # 재시도 설정
        self.max_retry_attempts = notification_config.get('max_retry_attempts', 3)  # 기본값: 3회
        self.retry_base_delay = notification_config.get('retry_base_delay', 1.0)  # 기본값: 1초
        self.retry_max_delay = notification_config.get('retry_max_delay', 30.0)  # 기본값: 30초
        
        logger.info("스마트 알림 관리자 초기화")
    
    async def start(self):
        """알림 관리자 시작"""
        self.summary_task = asyncio.create_task(self._summary_loop())
        self.event_id_cleanup_task = asyncio.create_task(self._event_id_cleanup_loop())
        logger.info("스마트 알림 관리자 시작")
    
    async def stop(self):
        """알림 관리자 중지"""
        # 태스크 중지
        tasks = [self.summary_task, self.event_id_cleanup_task]
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # 남은 요약 전송
        if self.summary_buffer:
            await self._send_summary()
        
        logger.info("스마트 알림 관리자 중지")
    
    async def send_alert(self, event_type: str, title: str, message: str, 
                        data: Dict = None, force: bool = False, event_id: str = None) -> bool:
        """레벨에 따른 알림 전송
        
        Args:
            event_id: 이벤트 고유 ID (중복 방지용)
        """
        try:
            # 1. 이벤트 ID 중복 체크 - 시간 기반 체크 개선
            if event_id:
                if event_id in self.event_ids:
                    # TTL 체크
                    event_time = self.event_ids[event_id]
                    if (datetime.now() - event_time).total_seconds() < self.event_id_ttl:
                        logger.debug(f"이벤트 ID 중복: {event_id}")
                        return False
                    else:
                        # TTL 만료된 경우 삭제
                        del self.event_ids[event_id]
            
            # 1-1. 시스템 종료 메시지는 특별히 처리 (중복 방지)
            if event_type == 'SYSTEM_STOPPED':
                # 최근 5초 이내에 동일한 종료 메시지를 보냈는지 확인
                system_stop_key = 'SYSTEM_STOPPED_RECENT'
                if system_stop_key in self.recent_alerts:
                    elapsed = (datetime.now() - self.recent_alerts[system_stop_key]).total_seconds()
                    if elapsed < 5:  # 5초 이내
                        logger.debug("시스템 종료 메시지 중복 방지")
                        return False
                self.recent_alerts[system_stop_key] = datetime.now()
            
            # 2. 이벤트 레벨 확인
            level = self.event_levels.get(event_type, AlertLevel.MEDIUM)
            
            # 3. 중복 체크 (force가 아닌 경우)
            if not force:
                alert_key = f"{event_type}:{title}"
                if not self._can_send_alert(alert_key, level):
                    logger.debug(f"알림 쿨다운 중: {alert_key}")
                    return False
            
            # 3. DB에 이벤트 저장
            if self.db:
                await self.db.save_system_event(
                    event_type=event_type,
                    level=level.name,
                    title=title,
                    message=message,
                    data=data
                )
            
            # 4. 알림 규칙 확인
            rules = self.notification_rules[level]
            
            # 5. 레벨별 처리
            if rules['immediate']:
                # 즉시 전송
                await self._send_immediate_alert(level, title, message, data)
            else:
                # 요약 버퍼에 추가
                self.summary_buffer.append({
                    'time': datetime.now(),
                    'event_type': event_type,
                    'level': level,
                    'title': title,
                    'message': message,
                    'data': data
                })
            
            # 6. 중복 방지 기록
            if not force:
                self.recent_alerts[alert_key] = datetime.now()
            
            # 7. 이벤트 ID 기록 - 시간과 함께 저장
            if event_id:
                self.event_ids[event_id] = datetime.now()
                # OrderedDict 크기 제한
                if len(self.event_ids) > self.max_event_ids:
                    # 가장 오래된 항목 제거
                    self.event_ids.popitem(last=False)
            
            return True
            
        except Exception as e:
            logger.error(f"알림 전송 실패: {e}")
            return False
    
    async def _send_immediate_alert(self, level: AlertLevel, title: str, 
                                  message: str, data: Dict = None):
        """즉시 알림 전송 - Exponential Backoff 재시도 포함"""
        if not self.telegram:
            return
        
        # 포맷팅
        formatted_message = self._format_alert(level, title, message, data)
        
        # 텔레그램 전송 - 재시도 로직 포함
        for attempt in range(self.max_retry_attempts):
            try:
                # send_alert 대신 send_message 직접 호출 (중복 처리 방지)
                success = await self.telegram.send_message(
                    formatted_message, 
                    immediate=True  # 즉시 전송
                )
                if success:
                    # 성공하면 리턴
                    if attempt > 0:
                        logger.info(f"알림 전송 성공 (retry {attempt})")
                    return
                else:
                    raise Exception("메시지 전송 실패")
                
            except Exception as e:
                # 마지막 시도인 경우 에러 로그만
                if attempt == self.max_retry_attempts - 1:
                    logger.error(f"텔레그램 알림 전송 실패 (모든 재시도 실패): {e}")
                    return
                
                # Exponential Backoff 계산
                delay = min(
                    self.retry_base_delay * (2 ** attempt), 
                    self.retry_max_delay
                )
                
                logger.warning(f"알림 전송 실패 (attempt {attempt + 1}/{self.max_retry_attempts}), "
                              f"{delay:.1f}초 후 재시도: {e}")
                
                await asyncio.sleep(delay)
    
    def _format_alert(self, level: AlertLevel, title: str, 
                     message: str, data: Dict = None) -> str:
        """알림 포맷팅"""
        emoji_map = {
            AlertLevel.CRITICAL: "🚨",
            AlertLevel.HIGH: "⚠️",
            AlertLevel.MEDIUM: "📊",
            AlertLevel.LOW: "ℹ️"
        }
        
        formatted = f"{emoji_map[level]} <b>{title}</b>\n\n{message}"
        
        # 추가 데이터가 있으면 포함
        if data:
            formatted += "\n\n<b>상세 정보:</b>"
            for key, value in data.items():
                formatted += f"\n• {key}: {value}"
        
        return formatted
    
    def _can_send_alert(self, alert_key: str, level: AlertLevel) -> bool:
        """알림 전송 가능 여부 (중복 방지)"""
        # CRITICAL과 HIGH는 항상 전송 (쿨다운 없음)
        if level in [AlertLevel.CRITICAL, AlertLevel.HIGH]:
            return True
        
        # MEDIUM, LOW만 쿨다운 체크
        if alert_key in self.recent_alerts:
            elapsed = (datetime.now() - self.recent_alerts[alert_key]).total_seconds()
            if elapsed < self.alert_cooldown:
                return False
        
        return True
    
    async def _summary_loop(self):
        """요약 전송 루프"""
        while True:
            try:
                await asyncio.sleep(60)  # 1분마다 체크
                
                # 요약 전송 시간 체크
                elapsed = (datetime.now() - self.last_summary_time).total_seconds()
                if elapsed >= self.summary_interval and self.summary_buffer:
                    await self._send_summary()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"요약 루프 오류: {e}")
    
    async def _event_id_cleanup_loop(self):
        """이벤트 ID 정리 루프 - TTL 기반 정리"""
        while True:
            try:
                await asyncio.sleep(300)  # 5분마다
                
                # TTL 만료된 항목 정리
                current_time = datetime.now()
                expired_ids = []
                
                for event_id, timestamp in self.event_ids.items():
                    if (current_time - timestamp).total_seconds() > self.event_id_ttl:
                        expired_ids.append(event_id)
                
                # 만료된 ID들 제거
                for event_id in expired_ids:
                    del self.event_ids[event_id]
                
                if expired_ids:
                    logger.debug(f"이벤트 ID 정리: {len(expired_ids)}개 만료, {len(self.event_ids)}개 유지")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"이벤트 ID 정리 오류: {e}")
    
    async def _send_summary(self):
        """버퍼에 쌓인 알림 요약 전송"""
        if not self.telegram:
            return
        
        try:
            # 버퍼가 비어있어도 최소한의 요약은 전송
            # DB에서 시간별 요약 가져오기
            hourly_data = None
            if self.db:
                hourly_data = await self.db.get_hourly_summary(hours=1)
            
            # 포지션 요약 추가
            position_summary = None
            if hasattr(self, 'position_manager'):
                # position_manager가 전달되지 않을 수 있으므로 체크
                # 사용하려면 SmartNotificationManager에 position_manager 참조 추가 필요
                pass
            
            # 요약 생성
            summary = self._create_summary(self.summary_buffer, hourly_data)
            
            # 전송 - send_message 사용 (immediate=True)
            await self.telegram.send_message(summary, immediate=True)
            
            # 버퍼 초기화
            self.summary_buffer.clear()
            self.last_summary_time = datetime.now()
            
            logger.info("시간별 요약 전송 완료")
            
        except Exception as e:
            logger.error(f"요약 전송 실패: {e}")
    
    def _create_summary(self, buffer: List[Dict], hourly_data: Dict = None) -> str:
        """요약 메시지 생성"""
        # 이벤트 그룹화
        event_counts = {}
        for item in buffer:
            event_type = item['event_type']
            if event_type not in event_counts:
                event_counts[event_type] = []
            event_counts[event_type].append(item)
        
        # 요약 메시지 작성
        summary = "📊 <b>시간별 요약</b>\n"
        summary += f"⏰ {self.last_summary_time.strftime('%Y-%m-%d %H:%M')} - {datetime.now().strftime('%H:%M')}\n\n"
        
        # 버퍼가 비어있어도 기본 정보는 표시
        if not buffer:
            summary += "🔔 특별한 이벤트가 없었습니다.\n\n"
        
        # DB 요약 데이터가 있으면 추가
        if hourly_data and hourly_data.get('trades'):
            trades = hourly_data['trades']
            if trades['total_trades'] > 0:
                summary += "<b>📈 거래 현황</b>\n"
                summary += f"• 총 거래: {trades['total_trades']}건\n"
                summary += f"• 승/패: {trades['win_trades']}/{trades['loss_trades']}\n"
                summary += f"• 손익: ${trades['total_pnl']:.2f}\n\n"
        
        # 이벤트별 요약
        summary += "<b>📋 이벤트 요약</b>\n"
        
        # 중요도 순으로 정렬
        sorted_events = sorted(
            event_counts.items(), 
            key=lambda x: self.event_levels.get(x[0], AlertLevel.LOW).value
        )
        
        for event_type, items in sorted_events:
            count = len(items)
            level = self.event_levels.get(event_type, AlertLevel.MEDIUM)
            
            if level == AlertLevel.MEDIUM:
                # MEDIUM 레벨 이벤트 상세 표시
                summary += f"\n{self._get_event_emoji(event_type)} {self._get_event_name(event_type)} ({count}건)\n"
                
                # 최근 3개만 표시
                for item in items[-3:]:
                    time_str = item['time'].strftime('%H:%M')
                    summary += f"  • {time_str} - {item['title']}\n"
            else:
                # LOW 레벨은 개수만
                summary += f"• {self._get_event_name(event_type)}: {count}건\n"
        
        return summary
    
    def _get_event_emoji(self, event_type: str) -> str:
        """이벤트 타입별 이모지"""
        emoji_map = {
            'POSITION_OPENED': '🔵',
            'POSITION_CLOSED': '🔴',
            'POSITION_SIZE_CHANGED': '📏',
            'POSITION_MODIFIED': '✏️',
            'PARTIAL_CLOSE': '✂️',
            'SYNC_COMPLETED': '🔄',
            'TECHNICAL_SIGNAL': '📡',
            'MANUAL_TRADE': '🤚',
            'MANUAL_CLOSE': '🛑',
            'MANUAL_MODIFIED': '🔧'
        }
        return emoji_map.get(event_type, '📌')
    
    def _get_event_name(self, event_type: str) -> str:
        """이벤트 타입 한글명"""
        name_map = {
            'POSITION_OPENED': '포지션 진입',
            'POSITION_CLOSED': '포지션 청산',
            'POSITION_SIZE_CHANGED': '포지션 크기 변경',
            'POSITION_MODIFIED': '포지션 수정',
            'PARTIAL_CLOSE': '부분 청산',
            'SYNC_COMPLETED': '동기화 완료',
            'TECHNICAL_SIGNAL': '기술적 신호',
            'HEARTBEAT': '상태 체크',
            'MANUAL_TRADE': '수동 거래 등록',
            'MANUAL_CLOSE': '수동 거래 청산',
            'MANUAL_MODIFIED': '수동 거래 수정'
        }
        return name_map.get(event_type, event_type)
    
    async def send_position_alert(self, position_data: Dict):
        """포지션 관련 알림 (호환성)"""
        action = position_data.get('action', 'UNKNOWN')
        
        # 액션을 이벤트 타입으로 매핑
        event_map = {
            'OPEN': 'POSITION_OPENED',
            'CLOSE': 'POSITION_CLOSED',
            'MODIFY': 'POSITION_MODIFIED',
            'PARTIAL_CLOSE': 'PARTIAL_CLOSE'
        }
        
        event_type = event_map.get(action, 'POSITION_MODIFIED')
        
        # 메시지 생성
        symbol = position_data['symbol']
        side = position_data.get('side', '')
        size = position_data.get('size', 0)
        price = position_data.get('price', 0)
        
        title = f"{symbol} {action}"
        message = f"방향: {side}\n수량: {size:.4f}\n가격: ${price:.2f}"
        
        if 'reason' in position_data:
            message += f"\n사유: {position_data['reason']}"
        
        await self.send_alert(event_type, title, message, position_data)
    
    async def send_pnl_alert(self, pnl_data: Dict):
        """손익 알림 (호환성)"""
        pnl_percent = pnl_data.get('pnl_percent', 0)
        
        # 손익에 따른 이벤트 타입
        if pnl_percent <= -10:
            event_type = 'LARGE_LOSS'
        elif pnl_percent >= 10:
            event_type = 'LARGE_PROFIT'
        else:
            event_type = 'POSITION_MODIFIED'
        
        symbol = pnl_data['symbol']
        title = f"{symbol} 손익 알림"
        
        message = (
            f"포지션: {pnl_data['side']}\n"
            f"손익률: {pnl_percent:+.2f}%\n"
            f"손익금액: ${pnl_data.get('pnl_usdt', 0):+.2f}\n"
            f"현재가: ${pnl_data.get('current_price', 0):.2f}"
        )
        
        await self.send_alert(event_type, title, message, pnl_data)