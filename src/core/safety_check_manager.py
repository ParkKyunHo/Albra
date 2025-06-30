# src/core/safety_check_manager.py
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class SafetyCheckManager:
    """시스템 재시작 시 포지션 안전 체크 관리"""
    
    def __init__(self, position_manager, binance_api, telegram_notifier, state_manager):
        self.position_manager = position_manager
        self.binance_api = binance_api
        self.telegram = telegram_notifier
        self.state_manager = state_manager
        
        # 안전 모드 상태
        self.safe_mode = False
        self.waiting_confirmation = False
        self.confirmation_event = asyncio.Event()
        self.user_decision = None  # 'continue', 'close_all', None
        
        # 설정
        self.confirmation_timeout = 300  # 5분
        self.emergency_close_on_timeout = True
        
        logger.info("안전 체크 관리자 초기화")
    
    async def check_startup_safety(self) -> bool:
        """시작 시 안전 체크 수행"""
        try:
            logger.info("시스템 시작 안전 체크 시작...")
            
            # 1. 비정상 종료 감지
            was_graceful = await self._check_graceful_shutdown()
            
            if not was_graceful:
                logger.warning("⚠️ 비정상 종료 감지됨!")
                # SmartNotificationManager의 send_alert 형식에 맞게 수정
                if hasattr(self, 'notification_manager') and self.notification_manager:
                    await self.notification_manager.send_alert(
                        event_type='SYSTEM_ERROR',
                        title='비정상 종료 감지',
                        message=(
                            "시스템이 예기치 않게 종료되었습니다.\n"
                            "안전 점검을 시작합니다."
                        )
                    )
                elif self.telegram:
                    # 일반 텔레그램 알림으로 폴백
                    await self.telegram.send_message(
                        "⚠️ <b>비정상 종료 감지</b>\n\n"
                        "시스템이 예기치 않게 종료되었습니다.\n"
                        "안전 점검을 시작합니다."
                    )
            
            # 2. 활성 포지션 확인
            positions = self.position_manager.get_active_positions(include_manual=False)
            system_positions = [p for p in positions if not p.is_manual]
            
            if not system_positions:
                logger.info("✅ 시스템 포지션 없음, 정상 시작")
                return True
            
            # 3. 안전 모드 활성화
            self.safe_mode = True
            logger.info(f"🛡️ 안전 모드 활성화 - {len(system_positions)}개 시스템 포지션 발견")
            
            # 4. 포지션 상태 점검
            position_report = await self._analyze_positions(system_positions)
            
            # 5. 사용자에게 보고 및 확인 요청
            await self._send_safety_report(position_report, was_graceful)
            
            # 6. 사용자 응답 대기 (5분)
            user_action = await self._wait_for_user_confirmation()
            
            # 7. 사용자 결정에 따른 처리
            if user_action == 'continue':
                logger.info("✅ 사용자가 계속 진행 선택")
                self.safe_mode = False
                return True
                
            elif user_action == 'close_all' or user_action is None:
                if user_action is None:
                    logger.warning("⏱️ 5분 타임아웃 - 시스템 포지션 청산 진행")
                    if hasattr(self, 'notification_manager') and self.notification_manager:
                        await self.notification_manager.send_alert(
                            event_type='SYSTEM_ERROR',
                            title='응답 시간 초과',
                            message=(
                                "5분 내 응답이 없어 안전을 위해\n"
                                "모든 시스템 포지션을 청산합니다."
                            )
                        )
                    elif self.telegram:
                        await self.telegram.send_message(
                            "⏱️ <b>응답 시간 초과</b>\n\n"
                            "5분 내 응답이 없어 안전을 위해\n"
                            "모든 시스템 포지션을 청산합니다."
                        )
                
                # 모든 시스템 포지션 청산
                await self._close_all_system_positions(system_positions)
                
                # 전략 일시정지
                if not was_graceful:
                    await self._pause_all_strategies()
                
                self.safe_mode = False
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"안전 체크 실패: {e}")
            # 안전을 위해 전략 일시정지
            await self._pause_all_strategies()
            return False
    
    async def _check_graceful_shutdown(self) -> bool:
        """정상 종료 여부 확인"""
        try:
            last_state = await self.state_manager.load_system_state()
            
            if not last_state:
                return True  # 첫 실행
            
            # shutdown_time이 있으면 정상 종료
            if 'shutdown_time' in last_state:
                return True
            
            # 마지막 업데이트 시간 체크
            last_update = last_state.get('last_update')
            if last_update:
                last_time = datetime.fromisoformat(last_update)
                time_diff = datetime.now() - last_time
                
                # 2분 이상 업데이트 없었으면 비정상
                if time_diff > timedelta(minutes=2):
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"종료 상태 확인 실패: {e}")
            return False  # 안전을 위해 비정상으로 간주
    
    async def _analyze_positions(self, positions: List) -> Dict:
        """포지션 분석"""
        report = {
            'total': len(positions),
            'details': [],
            'total_pnl': 0,
            'at_risk': 0
        }
        
        for position in positions:
            try:
                current_price = await self.binance_api.get_current_price(position.symbol)
                
                # PnL 계산
                if position.side == 'LONG':
                    pnl_percent = (current_price - position.entry_price) / position.entry_price * 100
                else:
                    pnl_percent = (position.entry_price - current_price) / position.entry_price * 100
                
                pnl_percent *= position.leverage
                
                # 위험 포지션 체크
                is_at_risk = pnl_percent < -5  # 5% 이상 손실
                if is_at_risk:
                    report['at_risk'] += 1
                
                report['details'].append({
                    'symbol': position.symbol,
                    'side': position.side,
                    'size': position.size,
                    'entry_price': position.entry_price,
                    'current_price': current_price,
                    'pnl_percent': pnl_percent,
                    'is_at_risk': is_at_risk,
                    'leverage': position.leverage
                })
                
                report['total_pnl'] += pnl_percent
                
            except Exception as e:
                logger.error(f"포지션 분석 실패 ({position.symbol}): {e}")
        
        return report
    
    async def _send_safety_report(self, report: Dict, was_graceful: bool):
        """안전 점검 리포트 전송"""
        message = "🛡️ <b>시스템 재시작 안전 점검</b>\n\n"
        
        if not was_graceful:
            message += "⚠️ <b>비정상 종료가 감지되었습니다</b>\n\n"
        
        message += f"<b>시스템 포지션 현황</b>\n"
        message += f"• 총 포지션: {report['total']}개\n"
        message += f"• 전체 PnL: {report['total_pnl']:.2f}%\n"
        
        if report['at_risk'] > 0:
            message += f"• ⚠️ 위험 포지션: {report['at_risk']}개\n"
        
        message += "\n<b>포지션 상세</b>\n"
        
        for pos in report['details']:
            emoji = "🔴" if pos['is_at_risk'] else "🟢" if pos['pnl_percent'] > 0 else "🟡"
            
            message += f"\n{emoji} <b>{pos['symbol']}</b> {pos['side']}\n"
            message += f"  크기: {pos['size']:.4f}\n"
            message += f"  진입가: ${pos['entry_price']:.2f}\n"
            message += f"  현재가: ${pos['current_price']:.2f}\n"
            message += f"  손익: {pos['pnl_percent']:+.2f}% ({pos['leverage']}x)\n"
        
        message += "\n<b>선택하세요:</b>\n"
        message += "/continue - 정상 거래 계속\n"
        message += "/close_all - 모든 시스템 포지션 청산\n"
        message += "\n⏱️ <b>5분 내 미응답 시 자동으로 모든 포지션이 청산됩니다</b>"
        
        # SmartNotificationManager가 있으면 사용, 없으면 일반 텔레그램
        if hasattr(self, 'notification_manager') and self.notification_manager:
            await self.notification_manager.send_alert(
                event_type='CRITICAL_ERROR',
                title='시스템 재시작 안전 점검',
                message=message,
                force=True  # 중복 체크 무시
            )
        elif self.telegram:
            await self.telegram.send_message(message)
        
        # 대기 시작
        self.waiting_confirmation = True
        self.confirmation_event.clear()
        self.user_decision = None
    
    async def _wait_for_user_confirmation(self) -> Optional[str]:
        """사용자 확인 대기"""
        try:
            # 타임아웃으로 대기
            await asyncio.wait_for(
                self.confirmation_event.wait(),
                timeout=self.confirmation_timeout
            )
            
            return self.user_decision
            
        except asyncio.TimeoutError:
            logger.warning("사용자 응답 타임아웃")
            return None
        finally:
            self.waiting_confirmation = False
    
    async def handle_user_decision(self, decision: str):
        """사용자 결정 처리 (텔레그램 명령어에서 호출)"""
        if not self.waiting_confirmation:
            return False
        
        if decision in ['continue', 'close_all']:
            self.user_decision = decision
            self.confirmation_event.set()
            return True
        
        return False
    
    async def _close_all_system_positions(self, positions: List):
        """모든 시스템 포지션 청산"""
        logger.info(f"🔴 {len(positions)}개 시스템 포지션 청산 시작")
        
        closed_count = 0
        failed_count = 0
        
        for position in positions:
            try:
                result = await self.binance_api.close_position(position.symbol)
                
                if result:
                    closed_count += 1
                    logger.info(f"✅ {position.symbol} 포지션 청산 완료")
                    
                    # 포지션 매니저에서 제거
                    current_price = await self.binance_api.get_current_price(position.symbol)
                    await self.position_manager.remove_position(position.symbol, current_price)
                else:
                    failed_count += 1
                    logger.error(f"❌ {position.symbol} 포지션 청산 실패")
                    
            except Exception as e:
                failed_count += 1
                logger.error(f"포지션 청산 오류 ({position.symbol}): {e}")
        
        # 결과 보고
        result_message = (
            f"<b>포지션 청산 완료</b>\n\n"
            f"• 성공: {closed_count}개\n"
            f"• 실패: {failed_count}개"
        )
        
        if hasattr(self, 'notification_manager') and self.notification_manager:
            await self.notification_manager.send_alert(
                event_type='POSITION_CLOSED',
                title='포지션 청산 완료',
                message=result_message
            )
        elif self.telegram:
            await self.telegram.send_message(result_message)
    
    async def _pause_all_strategies(self):
        """모든 전략 일시정지"""
        logger.info("⏸️ 모든 전략 일시정지")
        
        # 상태 저장
        await self.state_manager.save_system_state({
            'strategies_paused': True,
            'paused_at': datetime.now().isoformat(),
            'reason': 'abnormal_shutdown_safety'
        })
        
        pause_message = (
            "⏸️ <b>전략 일시정지</b>\n\n"
            "비정상 종료로 인해 모든 자동 거래가\n"
            "일시정지되었습니다.\n\n"
            "재개: /resume_all"
        )
        
        if hasattr(self, 'notification_manager') and self.notification_manager:
            await self.notification_manager.send_alert(
                event_type='SYSTEM_ERROR',
                title='전략 일시정지',
                message=pause_message
            )
        elif self.telegram:
            await self.telegram.send_message(pause_message)
    
    def is_safe_mode(self) -> bool:
        """안전 모드 상태 확인"""
        return self.safe_mode
    
    def get_status(self) -> Dict:
        """안전 체크 상태"""
        return {
            'safe_mode': self.safe_mode,
            'waiting_confirmation': self.waiting_confirmation,
            'confirmation_timeout': self.confirmation_timeout
        }