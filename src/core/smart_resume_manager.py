# src/core/smart_resume_manager.py
"""
스마트 재개 관리자 - 수동 거래 감지 및 자동 재개 (개선 버전)
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, Set, Tuple, List
import logging

logger = logging.getLogger(__name__)

class SmartResumeManager:
    """수동 거래 후 자동 재개 관리"""
    
    def __init__(self, position_manager, binance_api, notification_manager=None):
        self.position_manager = position_manager
        self.binance_api = binance_api
        self.notification_manager = notification_manager  # SmartNotificationManager 사용
        
        # 일시정지된 심볼 관리
        self.paused_symbols: Dict[str, Dict] = {}  # {symbol: {time, reason, original_position}}
        
        # 재개 조건 설정
        self.resume_conditions = {
            'min_delay': timedelta(minutes=30),      # 최소 대기 시간
            'max_delay': timedelta(hours=4),         # 최대 대기 시간
            'idle_check_interval': timedelta(minutes=5),  # 유휴 체크 간격
            'position_closed': True,                 # 포지션 종료 시 재개
            'no_activity_duration': timedelta(minutes=15),  # 활동 없음 시간
            'size_stable_duration': timedelta(minutes=10),  # 크기 안정화 시간
        }
        
        # 포지션 활동 추적
        self.position_activity: Dict[str, Dict] = {}  # {symbol: {last_change, last_size}}
        
        # 포지션 상태 추적
        self.position_snapshots: Dict[str, Dict] = {}  # 마지막 확인된 포지션 상태
        
        # 모니터링 상태
        self.is_monitoring = False
        self.monitor_task = None
        
        logger.info("스마트 재개 관리자 초기화 (개선 버전)")
    
    async def start_monitoring(self):
        """모니터링 시작"""
        if self.is_monitoring:
            return
            
        self.is_monitoring = True
        self.monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("🔄 스마트 재개 모니터링 시작")
    
    async def stop_monitoring(self):
        """모니터링 중지"""
        self.is_monitoring = False
        
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("🔄 스마트 재개 모니터링 중지")
    
    async def _monitoring_loop(self):
        """메인 모니터링 루프"""
        while self.is_monitoring:
            try:
                # 1. 포지션 변경 감지
                changes = await self._detect_position_changes()
                
                for symbol, change_type, details in changes:
                    await self._handle_position_change(symbol, change_type, details)
                
                # 2. 자동 재개 체크
                await self._check_auto_resume()
                
                # 30초마다 체크
                await asyncio.sleep(30)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"스마트 재개 모니터링 오류: {e}")
                await asyncio.sleep(10)
    
    async def _detect_position_changes(self) -> List[Tuple[str, str, Dict]]:
        """포지션 변경 감지"""
        changes = []
        current_time = datetime.now()
        
        # 현재 활성 포지션
        active_positions = self.position_manager.get_active_positions(include_manual=False)
        
        for position in active_positions:
            symbol = position.symbol
            
            # 활동 추적 초기화
            if symbol not in self.position_activity:
                self.position_activity[symbol] = {
                    'last_change': current_time,
                    'last_size': position.size,
                    'change_history': []
                }
            
            # 이전 스냅샷과 비교
            if symbol in self.position_snapshots:
                old_snapshot = self.position_snapshots[symbol]
                
                # 크기 변경 감지
                if abs(position.size - old_snapshot['size']) > 0.0001:
                    change_ratio = abs(position.size - old_snapshot['size']) / old_snapshot['size']
                    
                    # 활동 기록 업데이트
                    self.position_activity[symbol]['last_change'] = current_time
                    self.position_activity[symbol]['change_history'].append({
                        'time': current_time,
                        'old_size': old_snapshot['size'],
                        'new_size': position.size,
                        'change_ratio': change_ratio
                    })
                    
                    # 최근 10개 변경만 유지
                    if len(self.position_activity[symbol]['change_history']) > 10:
                        self.position_activity[symbol]['change_history'].pop(0)
                    
                    if position.size > old_snapshot['size']:
                        changes.append((symbol, 'SIZE_INCREASED', {
                            'old_size': old_snapshot['size'],
                            'new_size': position.size,
                            'change_ratio': change_ratio
                        }))
                    else:
                        changes.append((symbol, 'SIZE_DECREASED', {
                            'old_size': old_snapshot['size'],
                            'new_size': position.size,
                            'change_ratio': change_ratio
                        }))
                    
                    self.position_activity[symbol]['last_size'] = position.size
                
                # 상태 변경 감지
                if position.status != old_snapshot['status']:
                    changes.append((symbol, 'STATUS_CHANGED', {
                        'old_status': old_snapshot['status'],
                        'new_status': position.status
                    }))
            
            # 스냅샷 업데이트
            self.position_snapshots[symbol] = {
                'size': position.size,
                'status': position.status,
                'entry_price': position.entry_price,
                'timestamp': current_time
            }
        
        # 종료된 포지션 체크
        for symbol in list(self.position_snapshots.keys()):
            if not any(p.symbol == symbol for p in active_positions):
                changes.append((symbol, 'POSITION_CLOSED', {}))
                del self.position_snapshots[symbol]
                if symbol in self.position_activity:
                    del self.position_activity[symbol]
        
        return changes
    
    async def _handle_position_change(self, symbol: str, change_type: str, details: Dict):
        """포지션 변경 처리"""
        if change_type == 'SIZE_INCREASED':
            # 포지션 증가 - 일시정지
            await self.pause_symbol(symbol, f"포지션 크기 증가 감지 ({details['change_ratio']*100:.1f}%)")
            
        elif change_type == 'SIZE_DECREASED':
            # 포지션 감소
            if details['change_ratio'] > 0.7:  # 70% 이상 감소
                await self.pause_symbol(symbol, f"대량 포지션 감소 ({details['change_ratio']*100:.1f}%)")
            else:
                # 소량 감소는 로그만
                logger.info(f"{symbol} 포지션 일부 청산: {details['old_size']} → {details['new_size']}")
        
        elif change_type == 'POSITION_CLOSED':
            # 포지션 종료 - 자동 재개 후보
            if symbol in self.paused_symbols:
                logger.info(f"{symbol} 포지션 종료 감지, 재개 조건 확인 중...")
    
    async def pause_symbol(self, symbol: str, reason: str):
        """심볼 일시정지"""
        if symbol not in self.paused_symbols:
            position = self.position_manager.get_position(symbol)
            
            self.paused_symbols[symbol] = {
                'pause_time': datetime.now(),
                'reason': reason,
                'original_position': position.to_dict() if position else None,
                'resume_attempts': 0
            }
            
            logger.info(f"⏸️ {symbol} 자동 거래 일시정지: {reason}")
            
            # 중요 알림 전송 (SmartNotificationManager 사용)
            if self.notification_manager:
                await self.notification_manager.send_alert(
                    event_type='POSITION_PAUSED',
                    title=f"⏸️ {symbol} 자동 거래 일시정지",
                    message=(
                        f"<b>사유:</b> {reason}\n\n"
                        f"<b>재개 조건:</b>\n"
                        f"• 최소 {self.resume_conditions['min_delay'].total_seconds()/60:.0f}분 경과\n"
                        f"• 포지션 종료 또는 {self.resume_conditions['no_activity_duration'].total_seconds()/60:.0f}분간 변동 없음\n"
                        f"• 수동 재개: /resume {symbol}"
                    ),
                    data={
                        'symbol': symbol,
                        'reason': reason,
                        'position': position.to_dict() if position else None
                    }
                )
    
    async def _check_auto_resume(self):
        """자동 재개 체크 (개선된 로직)"""
        current_time = datetime.now()
        symbols_to_resume = []
        
        for symbol, pause_info in self.paused_symbols.items():
            pause_time = pause_info['pause_time']
            elapsed = current_time - pause_time
            
            # 1. 최소 대기 시간 체크
            if elapsed < self.resume_conditions['min_delay']:
                continue
            
            # 2. 최대 대기 시간 초과 - 강제 재개
            if elapsed >= self.resume_conditions['max_delay']:
                symbols_to_resume.append((symbol, "최대 대기 시간 초과"))
                continue
            
            # 3. 포지션 상태 확인
            position = self.position_manager.get_position(symbol)
            
            # 3-1. 포지션이 종료됨
            if not position or position.status == 'CLOSED':
                symbols_to_resume.append((symbol, "포지션 종료"))
                continue
            
            # 3-2. 활동 없음 체크
            if symbol in self.position_activity:
                last_change = self.position_activity[symbol]['last_change']
                no_activity_duration = current_time - last_change
                
                if no_activity_duration >= self.resume_conditions['no_activity_duration']:
                    # 추가로 크기 안정성 체크
                    if self._is_position_stable(symbol):
                        symbols_to_resume.append((symbol, f"{no_activity_duration.total_seconds()/60:.0f}분간 변동 없음"))
                        continue
            
            # 4. 재개 시도 횟수에 따른 점진적 체크
            attempts = pause_info.get('resume_attempts', 0)
            if attempts > 0:
                # 재시도마다 대기 시간 감소
                adjusted_delay = self.resume_conditions['min_delay'] * (0.8 ** attempts)
                if elapsed >= adjusted_delay:
                    pause_info['resume_attempts'] += 1
                    logger.info(f"{symbol} 재개 조건 재확인 (시도 {attempts + 1})")
        
        # 재개 처리
        for symbol, reason in symbols_to_resume:
            await self.resume_symbol(symbol, auto=True, reason=reason)
    
    def _is_position_stable(self, symbol: str) -> bool:
        """포지션 안정성 체크"""
        if symbol not in self.position_activity:
            return True
        
        activity = self.position_activity[symbol]
        history = activity.get('change_history', [])
        
        if not history:
            return True
        
        # 최근 10분간 변경 이력 확인
        recent_changes = [
            ch for ch in history 
            if datetime.now() - ch['time'] < self.resume_conditions['size_stable_duration']
        ]
        
        # 변경이 없거나 미미한 변경만 있으면 안정적
        if not recent_changes:
            return True
        
        # 변경률이 모두 1% 미만이면 안정적
        return all(ch['change_ratio'] < 0.01 for ch in recent_changes)
    
    async def resume_symbol(self, symbol: str, auto: bool = False, reason: str = ""):
        """심볼 재개"""
        if symbol in self.paused_symbols:
            pause_info = self.paused_symbols[symbol]
            del self.paused_symbols[symbol]
            
            resume_type = "자동" if auto else "수동"
            pause_duration = (datetime.now() - pause_info['pause_time']).total_seconds() / 60
            
            logger.info(f"▶️ {symbol} {resume_type} 거래 재개 ({reason})")
            
            # 중요 알림 전송 (SmartNotificationManager 사용)
            if self.notification_manager:
                await self.notification_manager.send_alert(
                    event_type='POSITION_RESUMED',
                    title=f"▶️ {symbol} {resume_type} 거래 재개",
                    message=(
                        f"<b>재개 사유:</b> {reason}\n"
                        f"<b>일시정지 사유:</b> {pause_info['reason']}\n"
                        f"<b>정지 시간:</b> {pause_duration:.1f}분\n\n"
                        f"시스템이 정상적으로 거래를 재개합니다."
                    ),
                    data={
                        'symbol': symbol,
                        'resume_type': resume_type,
                        'reason': reason,
                        'pause_duration_minutes': pause_duration
                    }
                )
            
            return True
        
        return False
    
    def is_symbol_paused(self, symbol: str) -> bool:
        """심볼 일시정지 여부"""
        return symbol in self.paused_symbols
    
    def get_paused_symbols(self) -> Dict[str, Dict]:
        """일시정지된 심볼 정보"""
        return self.paused_symbols.copy()
    
    def get_status(self) -> Dict:
        """스마트 재개 상태"""
        current_time = datetime.now()
        paused_list = []
        
        for symbol, info in self.paused_symbols.items():
            elapsed = (current_time - info['pause_time']).total_seconds() / 60
            min_remaining = max(0, self.resume_conditions['min_delay'].total_seconds() / 60 - elapsed)
            
            # 재개 예상 시간 계산
            resume_estimate = "확인 중"
            position = self.position_manager.get_position(symbol)
            
            if not position:
                resume_estimate = "포지션 종료 시"
            elif symbol in self.position_activity:
                last_change = self.position_activity[symbol]['last_change']
                no_activity = (current_time - last_change).total_seconds() / 60
                remaining_idle = max(0, self.resume_conditions['no_activity_duration'].total_seconds() / 60 - no_activity)
                
                if remaining_idle > 0:
                    resume_estimate = f"약 {remaining_idle:.0f}분 후 (활동 없을 시)"
            
            paused_list.append({
                'symbol': symbol,
                'reason': info['reason'],
                'elapsed_minutes': elapsed,
                'min_remaining_minutes': min_remaining,
                'resume_estimate': resume_estimate,
                'attempts': info.get('resume_attempts', 0)
            })
        
        return {
            'is_monitoring': self.is_monitoring,
            'paused_symbols': paused_list,
            'total_paused': len(self.paused_symbols),
            'resume_conditions': {
                'min_delay_minutes': self.resume_conditions['min_delay'].total_seconds() / 60,
                'max_delay_hours': self.resume_conditions['max_delay'].total_seconds() / 3600,
                'no_activity_minutes': self.resume_conditions['no_activity_duration'].total_seconds() / 60
            }
        }
    
    async def cleanup(self):
        """정리 작업"""
        await self.stop_monitoring()
        logger.info("스마트 재개 관리자 정리 완료")