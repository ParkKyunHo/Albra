# src/utils/telegram_notifier.py
import asyncio
import aiohttp
import logging
from typing import Dict, Optional, List, Any
from datetime import datetime
import json
from enum import Enum

logger = logging.getLogger(__name__)


class AlertPriority(Enum):
    """알림 우선순위 열거형"""
    CRITICAL = "critical"
    HIGH = "high_priority"
    MEDIUM = "position_alert"
    LOW = "general"


class AlertType(Enum):
    """알림 타입 열거형"""
    SYSTEM_ERROR = "SYSTEM_ERROR"
    SYSTEM_STOPPED = "SYSTEM_STOPPED"
    LARGE_LOSS = "LARGE_LOSS"
    USER_INTERVENTION = "USER_INTERVENTION"
    POSITION_PAUSED = "POSITION_PAUSED"
    POSITION_RESUMED = "POSITION_RESUMED"
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_CLOSED = "POSITION_CLOSED"
    POSITION_SIZE_CHANGED = "POSITION_SIZE_CHANGED"
    HEARTBEAT = "HEARTBEAT"
    SYNC_COMPLETED = "SYNC_COMPLETED"


class TelegramNotifier:
    """텔레그램 알림 봇 - 연결 풀 관리 개선"""
    
    # 클래스 레벨 상수
    DEFAULT_TIMEOUT = 30
    DEFAULT_CONNECT_TIMEOUT = 10
    DEFAULT_READ_TIMEOUT = 20
    MAX_RETRIES = 3
    RETRY_DELAY = 1
    SUMMARY_INTERVAL = 3600  # 1시간
    
    # 우선순위 매핑
    PRIORITY_MAP = {
        AlertType.SYSTEM_ERROR: AlertPriority.CRITICAL,
        AlertType.SYSTEM_STOPPED: AlertPriority.CRITICAL,
        AlertType.LARGE_LOSS: AlertPriority.CRITICAL,
        AlertType.USER_INTERVENTION: AlertPriority.HIGH,
        AlertType.POSITION_PAUSED: AlertPriority.HIGH,
        AlertType.POSITION_RESUMED: AlertPriority.HIGH,
        AlertType.POSITION_OPENED: AlertPriority.MEDIUM,
        AlertType.POSITION_CLOSED: AlertPriority.MEDIUM,
        AlertType.POSITION_SIZE_CHANGED: AlertPriority.MEDIUM,
        AlertType.HEARTBEAT: AlertPriority.LOW,
        AlertType.SYNC_COMPLETED: AlertPriority.LOW,
    }
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.session: Optional[aiohttp.ClientSession] = None
        self.is_connected = False
        self.bot = None  # 호환성을 위한 bot 속성
        
        # 요약 버퍼
        self.summary_buffer = []
        self.summary_task = None
        
        # 메시지 큐 (연결 풀 문제 해결)
        self.message_queue = asyncio.Queue(maxsize=100)
        self.sender_task = None
        
        # 통계
        self.stats = {
            'messages_sent': 0,
            'messages_failed': 0,
            'last_error': None
        }
        
        logger.info("텔레그램 알림 봇 초기화")
    
    async def initialize(self) -> bool:
        """봇 초기화 및 연결 확인"""
        try:
            # 커넥터 설정으로 연결 풀 크기 증가
            connector = aiohttp.TCPConnector(
                limit=100,  # 전체 연결 제한
                limit_per_host=30,  # 호스트당 연결 제한
                ttl_dns_cache=300
            )
            
            # 타임아웃 설정
            timeout = aiohttp.ClientTimeout(
                total=self.DEFAULT_TIMEOUT,
                connect=self.DEFAULT_CONNECT_TIMEOUT,
                sock_read=self.DEFAULT_READ_TIMEOUT
            )
            
            # 세션 생성
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            )
            
            # 봇 정보 확인
            bot_info = await self._get_bot_info()
            if bot_info:
                logger.info(f"텔레그램 알림 봇 연결 성공: @{bot_info['username']}")
                self.is_connected = True
                
                # 메시지 전송 태스크 시작
                self.sender_task = asyncio.create_task(self._message_sender())
                
                # 요약 스케줄러 시작
                self.summary_task = asyncio.create_task(self._summary_scheduler())
                
                # 초기화 메시지 (main.py에서 통합 처리하므로 제거)
                # await self.send_message("🤖 트레이딩 봇 알림 시스템 시작", immediate=True)
                
                return True
            
            logger.error("텔레그램 봇 연결 실패")
            return False
            
        except Exception as e:
            logger.error(f"텔레그램 봇 초기화 실패: {e}")
            await self._cleanup_session()
            return False
    
    async def _get_bot_info(self) -> Optional[Dict]:
        """봇 정보 조회"""
        try:
            async with self.session.get(f"{self.base_url}/getMe") as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('ok'):
                        return data['result']
        except Exception as e:
            logger.error(f"봇 정보 조회 실패: {e}")
        return None
    
    async def _message_sender(self):
        """메시지 전송 워커 (큐에서 메시지를 가져와 전송)"""
        while True:
            try:
                # 큐에서 메시지 가져오기
                message_data = await self.message_queue.get()
                
                if message_data is None:  # 종료 신호
                    break
                
                # 메시지 전송 시도
                success = await self._send_message_with_retry(
                    message_data['text'],
                    message_data.get('parse_mode', 'HTML')
                )
                
                if success:
                    self.stats['messages_sent'] += 1
                else:
                    self.stats['messages_failed'] += 1
                
                # 짧은 대기 (Rate limit 방지)
                await asyncio.sleep(0.1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"메시지 전송 워커 오류: {e}")
                await asyncio.sleep(1)
    
    async def _send_message_with_retry(self, text: str, parse_mode: str = 'HTML') -> bool:
        """재시도 로직이 포함된 메시지 전송"""
        for attempt in range(self.MAX_RETRIES):
            try:
                if not self.session or self.session.closed:
                    return False
                
                data = {
                    'chat_id': self.chat_id,
                    'text': text,
                    'parse_mode': parse_mode,
                    'disable_web_page_preview': True
                }
                
                async with self.session.post(
                    f"{self.base_url}/sendMessage",
                    json=data
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get('ok'):
                            return True
                        else:
                            error_msg = result.get('description', 'Unknown error')
                            logger.error(f"메시지 전송 실패: {error_msg}")
                            self.stats['last_error'] = error_msg
                    else:
                        logger.error(f"메시지 전송 실패: HTTP {response.status}")
                        
                    # 429 (Too Many Requests)인 경우 더 긴 대기
                    if response.status == 429:
                        await asyncio.sleep(5)
                        
            except asyncio.TimeoutError:
                logger.error(f"메시지 전송 타임아웃 (시도 {attempt + 1}/{self.MAX_RETRIES})")
            except Exception as e:
                logger.error(f"메시지 전송 오류 (시도 {attempt + 1}/{self.MAX_RETRIES}): {e}")
            
            # 재시도 전 대기
            if attempt < self.MAX_RETRIES - 1:
                await asyncio.sleep(self.RETRY_DELAY * (attempt + 1))
        
        return False
    
    async def send_message(self, text: str, parse_mode: str = 'HTML', immediate: bool = False) -> bool:
        """메시지 전송 (큐 사용)"""
        try:
            message_data = {
                'text': text,
                'parse_mode': parse_mode
            }
            
            if immediate or not self.sender_task:
                # 즉시 전송 또는 워커가 없는 경우
                return await self._send_message_with_retry(text, parse_mode)
            else:
                # 큐에 추가
                await self.message_queue.put(message_data)
                return True
                
        except asyncio.QueueFull:
            logger.error("메시지 큐가 가득 참")
            return False
        except Exception as e:
            logger.error(f"메시지 전송 중 오류: {e}")
            return False
    
    async def send_alert(self, message: str, alert_type: str = 'general'):
        """알림 전송 (우선순위 기반)"""
        try:
            # alert_type이 문자열인 경우 AlertType으로 변환
            if isinstance(alert_type, str):
                try:
                    alert_enum = AlertType[alert_type]
                except KeyError:
                    # 기존 호환성을 위한 매핑
                    legacy_map = {
                        'critical': AlertPriority.CRITICAL,
                        'high_priority': AlertPriority.HIGH,
                        'high': AlertPriority.HIGH,
                        'position_alert': AlertPriority.MEDIUM,
                        'general': AlertPriority.LOW
                    }
                    priority = legacy_map.get(alert_type, AlertPriority.LOW)
                else:
                    priority = self.PRIORITY_MAP.get(alert_enum, AlertPriority.LOW)
            else:
                priority = AlertPriority.LOW
            
            # 우선순위에 따른 처리
            if priority in [AlertPriority.CRITICAL, AlertPriority.HIGH]:
                # 즉시 전송
                await self.send_message(message, immediate=True)
                logger.info(f"알림 전송 완료: {priority.value}")
            elif priority == AlertPriority.MEDIUM:
                # 요약 버퍼에 추가
                self.summary_buffer.append({
                    'time': datetime.now(),
                    'message': message,
                    'type': alert_type
                })
                logger.debug(f"알림 버퍼에 추가: {priority.value}")
            else:
                # 낮은 우선순위는 로그만
                logger.debug(f"낮은 우선순위 알림: {priority.value}")
            
        except Exception as e:
            logger.error(f"알림 전송 실패: {e}")
    
    async def send_position_alert(self, position_data: Dict):
        """포지션 알림 - 템플릿 사용"""
        try:
            action = position_data.get('action', 'UNKNOWN')
            symbol = position_data.get('symbol', 'N/A')
            side = position_data.get('side', 'N/A')
            size = position_data.get('size', 0)
            price = position_data.get('price', 0)
            
            # 액션별 템플릿
            templates = {
                'OPEN': {
                    'emoji': '📈',
                    'title': '포지션 진입',
                    'alert_type': AlertType.POSITION_OPENED
                },
                'CLOSE': {
                    'emoji': '📉',
                    'title': '포지션 청산',
                    'alert_type': AlertType.POSITION_CLOSED
                }
            }
            
            template = templates.get(action, {
                'emoji': '📊',
                'title': '포지션 변경',
                'alert_type': AlertType.POSITION_SIZE_CHANGED
            })
            
            message = f"""
{template['emoji']} <b>{template['title']}</b>

<b>심볼:</b> {symbol}
<b>방향:</b> {side}
<b>크기:</b> {size}
"""
            
            if action == 'OPEN':
                message += f"<b>진입가:</b> {price:.2f}\n"
            
            await self.send_alert(message, template['alert_type'].name)
            
        except Exception as e:
            logger.error(f"포지션 알림 실패: {e}")
    
    async def send_pnl_alert(self, pnl_data: Dict):
        """손익 알림"""
        try:
            symbol = pnl_data.get('symbol')
            pnl_percent = pnl_data.get('pnl_percent', 0)
            pnl_usdt = pnl_data.get('pnl_usdt', 0)
            
            # 손익률에 따른 이모지 자동 선택
            if pnl_percent >= 10:
                emoji = '🎯'
            elif pnl_percent >= 5:
                emoji = '💰'
            elif pnl_percent <= -10:
                emoji = '🚨'
            elif pnl_percent <= -5:
                emoji = '⚠️'
            else:
                emoji = '📊'
            
            # 큰 손실인 경우 LARGE_LOSS
            alert_type = AlertType.LARGE_LOSS if pnl_percent <= -10 else AlertType.POSITION_CLOSED
            
            message = f"""
{emoji} <b>손익 알림</b>

<b>심볼:</b> {symbol}
<b>손익률:</b> {pnl_percent:+.2f}%
<b>손익액:</b> ${pnl_usdt:+.2f}
"""
            
            await self.send_alert(message, alert_type.name)
            
        except Exception as e:
            logger.error(f"손익 알림 실패: {e}")
    
    async def send_startup_message(self):
        """시작 메시지"""
        message = """
🚀 <b>트레이딩 시스템 시작</b>

✅ 모든 컴포넌트가 정상적으로 초기화되었습니다.
📊 TFPE 전략으로 자동 거래를 시작합니다.

/help - 사용 가능한 명령어
"""
        await self.send_message(message, immediate=True)
    
    async def send_shutdown_message(self):
        """종료 메시지"""
        message = """
🛑 <b>트레이딩 시스템 종료</b>

시스템이 안전하게 종료되었습니다.
모든 포지션이 유지됩니다.
"""
        await self.send_message(message, immediate=True)
    
    async def send_daily_report(self, report_data: Dict):
        """일일 보고서"""
        try:
            # 보고서 데이터 추출
            total_trades = report_data.get('total_trades', 0)
            win_rate = report_data.get('win_rate', 0)
            daily_pnl = report_data.get('daily_pnl', 0)
            active_positions = report_data.get('active_positions', 0)
            balance = report_data.get('balance', 0)
            
            # 이모지 선택
            pnl_emoji = '📈' if daily_pnl >= 0 else '📉'
            performance_emoji = '🎯' if win_rate >= 60 else '📊'
            
            message = f"""
📊 <b>일일 보고서</b>
{datetime.now().strftime('%Y-%m-%d')}

<b>{performance_emoji} 거래 실적</b>
총 거래: {total_trades}건
승률: {win_rate:.1f}%
일일 손익: {pnl_emoji} ${daily_pnl:+.2f}

<b>💰 계좌 현황</b>
잔고: ${balance:.2f}
활성 포지션: {active_positions}개

<b>📈 통계</b>
메시지 전송: {self.stats['messages_sent']}건
전송 실패: {self.stats['messages_failed']}건

좋은 하루 되세요! 🎯
"""
            
            await self.send_message(message, immediate=True)
            
        except Exception as e:
            logger.error(f"일일 보고서 전송 실패: {e}")
    
    async def send_hourly_summary(self):
        """시간별 요약 전송"""
        if not self.summary_buffer:
            return
        
        try:
            current_time = datetime.now()
            
            # 이벤트 타입별로 그룹화
            events_by_type = {}
            for event in self.summary_buffer:
                event_type = event.get('type', 'unknown')
                if event_type not in events_by_type:
                    events_by_type[event_type] = []
                events_by_type[event_type].append(event)
            
            # 요약 메시지 생성
            summary = f"""
📊 <b>시간별 요약</b>
{current_time.strftime('%H:%M')} 기준

"""
            
            # 포지션 이벤트
            position_events = []
            for event_type in [AlertType.POSITION_OPENED.name, 
                             AlertType.POSITION_CLOSED.name,
                             AlertType.POSITION_SIZE_CHANGED.name]:
                if event_type in events_by_type:
                    position_events.extend(events_by_type[event_type])
            
            if position_events:
                summary += f"<b>📈 포지션 활동 ({len(position_events)}건)</b>\n"
                
                # 최근 5개만 표시
                for event in position_events[-5:]:
                    # 첫 줄만 추출
                    first_line = event['message'].split('\n')[0]
                    clean_line = first_line.replace('<b>', '').replace('</b>', '')
                    summary += f"• {clean_line}\n"
                summary += "\n"
            
            # 기타 이벤트 수
            other_count = len(self.summary_buffer) - len(position_events)
            if other_count > 0:
                summary += f"<b>ℹ️ 기타 이벤트</b>\n"
                summary += f"• 총 {other_count}건 발생\n"
            
            # 전송
            await self.send_message(summary)
            
            # 버퍼 초기화
            self.summary_buffer.clear()
            logger.info("시간별 요약 전송 완료")
            
        except Exception as e:
            logger.error(f"시간별 요약 전송 실패: {e}")
    
    async def _summary_scheduler(self):
        """요약 스케줄러"""
        while True:
            try:
                # 대기
                await asyncio.sleep(self.SUMMARY_INTERVAL)
                
                # 요약 전송
                await self.send_hourly_summary()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"요약 스케줄러 오류: {e}")
                await asyncio.sleep(60)
    
    async def send_error_alert(self, error_type: str, error_message: str, details: Optional[str] = None):
        """오류 알림"""
        try:
            message = f"""
🚨 <b>시스템 오류</b>

<b>타입:</b> {error_type}
<b>메시지:</b> {error_message}
"""
            if details:
                # 상세 내용이 너무 길면 잘라내기
                if len(details) > 200:
                    details = details[:200] + "..."
                message += f"<b>상세:</b> {details}\n"
            
            message += f"\n<i>발생시간: {datetime.now().strftime('%H:%M:%S')}</i>"
            
            await self.send_alert(message, AlertType.SYSTEM_ERROR.name)
            
        except Exception as e:
            logger.error(f"오류 알림 전송 실패: {e}")
    
    async def _cleanup_session(self):
        """세션 정리"""
        if self.session and not self.session.closed:
            await self.session.close()
            await asyncio.sleep(0.25)
    
    async def cleanup(self):
        """정리 작업"""
        try:
            logger.info("텔레그램 알림 봇 정리 시작")
            
            # 메시지 큐에 종료 신호
            if self.sender_task:
                await self.message_queue.put(None)
                self.sender_task.cancel()
                try:
                    await self.sender_task
                except asyncio.CancelledError:
                    pass
            
            # 요약 태스크 취소
            if self.summary_task:
                self.summary_task.cancel()
                try:
                    await self.summary_task
                except asyncio.CancelledError:
                    pass
            
            # 세션 정리
            await self._cleanup_session()
            
            self.is_connected = False
            logger.info("텔레그램 알림 봇 정리 완료")
            
        except Exception as e:
            logger.error(f"텔레그램 봇 정리 중 오류: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 정보 반환"""
        return {
            'messages_sent': self.stats['messages_sent'],
            'messages_failed': self.stats['messages_failed'],
            'last_error': self.stats['last_error'],
            'queue_size': self.message_queue.qsize() if self.message_queue else 0,
            'is_connected': self.is_connected
        }