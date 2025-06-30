# src/core/mdd_manager_improved.py
"""
개선된 Maximum Drawdown (MDD) 관리자
다단계 포지션 크기 조정 및 회복 메커니즘 포함
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import asyncio

logger = logging.getLogger(__name__)

@dataclass
class MDDEvent:
    """MDD 이벤트 기록"""
    timestamp: datetime
    event_type: str  # 'level_change', 'recovered', 'emergency_stop'
    mdd_value: float
    capital: float
    peak_capital: float
    mdd_level: int
    action_taken: str
    details: Dict = None
    
    def to_dict(self) -> Dict:
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data

class ImprovedMDDManager:
    """개선된 MDD 관리자 - 다단계 포지션 크기 조정"""
    
    def __init__(self, config: Dict, notification_manager=None):
        """
        Args:
            config: MDD 설정
            notification_manager: 알림 매니저
        """
        self.config = config
        self.notification_manager = notification_manager
        
        # MDD 단계별 설정 (백테스트와 동일)
        self.params = {
            # 기본 설정
            'max_allowed_mdd': config.get('max_allowed_mdd', 40.0),
            'mdd_recovery_threshold': config.get('mdd_recovery_threshold', 15.0),
            
            # MDD 단계별 포지션 크기 조정
            'mdd_level_1': 30.0,  # MDD 30%: 포지션 70%로 축소
            'mdd_level_1_size': 0.7,
            'mdd_level_2': 35.0,  # MDD 35%: 포지션 50%로 축소
            'mdd_level_2_size': 0.5,
            'mdd_level_3': 40.0,  # MDD 40%: 포지션 30%로 축소
            'mdd_level_3_size': 0.3,
            'mdd_level_4': 50.0,  # MDD 50%: 포지션 10%로 축소 (긴급)
            'mdd_level_4_size': 0.1,
            
            # 회복 메커니즘
            'mdd_recovery_mode': config.get('mdd_recovery_mode', True),
            'recovery_win_threshold': config.get('recovery_win_threshold', 3),
            'recovery_size_increment': config.get('recovery_size_increment', 0.1),
            'max_recovery_size': config.get('max_recovery_size', 1.0),
            
            # 안전장치
            'mdd_emergency_stop': config.get('mdd_emergency_stop', 60.0),
            'force_trade_if_no_position': config.get('force_trade_if_no_position', True),
        }
        
        # 상태 추적
        self.peak_capital = 0.0
        self.current_mdd = 0.0
        self.current_mdd_level = 0
        self.recovery_mode_active = False
        self.current_recovery_multiplier = 1.0
        self.consecutive_wins = 0
        self.active_positions_count = 0
        self.time_without_position = 0
        self.last_mdd_update = datetime.now()
        
        # 이벤트 기록
        self.mdd_events: List[MDDEvent] = []
        self.mdd_history = []  # 시계열 MDD 기록
        
        # 통계
        self.stats = {
            'max_mdd_reached': 0.0,
            'total_mdd_events': 0,
            'emergency_stops': 0,
            'trades_skipped_by_mdd': 0,
            'trades_with_reduced_size': 0,
            'time_in_mdd_level_1': 0,
            'time_in_mdd_level_2': 0,
            'time_in_mdd_level_3': 0,
            'time_in_mdd_level_4': 0
        }
        
        logger.info(f"개선된 MDD Manager 초기화")
        logger.info(f"MDD 레벨: 30%(70%), 35%(50%), 40%(30%), 50%(10%)")
        logger.info(f"회복 모드: {'활성화' if self.params['mdd_recovery_mode'] else '비활성화'}")
    
    def calculate_current_mdd(self, current_capital: float) -> float:
        """현재 MDD 계산 및 업데이트 (이체 감지 포함)"""
        # 계좌 이체 감지 및 처리
        if self.params.get('detect_transfers', True):
            self.adjust_for_transfer(current_capital)
        
        # Peak 자본 업데이트
        if current_capital > self.peak_capital:
            self.peak_capital = current_capital
            # Peak 갱신 시 회복 모드 해제
            self.recovery_mode_active = False
            self.current_recovery_multiplier = 1.0
            logger.info(f"Peak 자본 갱신: ${self.peak_capital:,.2f}")
        
        # MDD 계산
        if self.peak_capital > 0:
            self.current_mdd = (self.peak_capital - current_capital) / self.peak_capital * 100
        else:
            self.current_mdd = 0.0
        
        # 최대 MDD 기록
        if self.current_mdd > self.stats['max_mdd_reached']:
            self.stats['max_mdd_reached'] = self.current_mdd
        
        # 시계열 기록
        self.mdd_history.append({
            'timestamp': datetime.now(),
            'mdd': self.current_mdd,
            'capital': current_capital,
            'peak_capital': self.peak_capital,
            'mdd_level': self._get_current_mdd_level(),
            'recovery_multiplier': self.current_recovery_multiplier
        })
        
        # 오래된 기록 정리 (최근 24시간만 유지)
        if len(self.mdd_history) > 1440:
            self.mdd_history = self.mdd_history[-1440:]
        
        self.last_mdd_update = datetime.now()
        
        return self.current_mdd
    
    def _get_current_mdd_level(self) -> int:
        """현재 MDD 레벨 반환"""
        if self.current_mdd >= self.params['mdd_level_4']:
            return 4
        elif self.current_mdd >= self.params['mdd_level_3']:
            return 3
        elif self.current_mdd >= self.params['mdd_level_2']:
            return 2
        elif self.current_mdd >= self.params['mdd_level_1']:
            return 1
        else:
            return 0
    
    def get_mdd_position_multiplier(self) -> float:
        """MDD 수준에 따른 포지션 크기 배수 계산"""
        if self.current_mdd >= self.params['mdd_level_4']:
            return self.params['mdd_level_4_size']
        elif self.current_mdd >= self.params['mdd_level_3']:
            return self.params['mdd_level_3_size']
        elif self.current_mdd >= self.params['mdd_level_2']:
            return self.params['mdd_level_2_size']
        elif self.current_mdd >= self.params['mdd_level_1']:
            return self.params['mdd_level_1_size']
        else:
            return 1.0
    
    async def check_mdd_restrictions(self, current_capital: float) -> Dict[str, any]:
        """개선된 MDD 기반 거래 제한 확인"""
        # MDD 업데이트
        self.calculate_current_mdd(current_capital)
        
        # 현재 MDD 레벨
        new_mdd_level = self._get_current_mdd_level()
        
        restrictions = {
            'allow_new_trades': True,
            'position_size_multiplier': 1.0,
            'force_close_positions': False,
            'reason': '',
            'current_mdd': self.current_mdd,
            'peak_capital': self.peak_capital,
            'mdd_level': new_mdd_level
        }
        
        # 긴급 정지 확인
        if self.current_mdd >= self.params['mdd_emergency_stop']:
            restrictions['allow_new_trades'] = False
            restrictions['force_close_positions'] = True
            restrictions['reason'] = f'EMERGENCY STOP: MDD {self.current_mdd:.1f}%'
            
            # 이벤트 기록
            await self._record_mdd_event('emergency_stop', current_capital, restrictions['reason'])
            
            # 긴급 알림
            if self.notification_manager:
                await self.notification_manager.send_alert(
                    event_type='SYSTEM_ERROR',
                    title='🚨 MDD 긴급 정지',
                    message=(
                        f"<b>현재 MDD:</b> {self.current_mdd:.1f}%\n"
                        f"<b>긴급 정지 임계값:</b> {self.params['mdd_emergency_stop']:.1f}%\n"
                        f"<b>현재 자본:</b> ${current_capital:,.2f}\n"
                        f"<b>Peak 자본:</b> ${self.peak_capital:,.2f}\n\n"
                        f"모든 포지션이 강제 청산됩니다!"
                    ),
                    force=True
                )
            
            self.stats['emergency_stops'] += 1
            return restrictions
        
        # MDD 레벨 변경 체크
        if new_mdd_level != self.current_mdd_level:
            # 레벨 상승 (MDD 악화)
            if new_mdd_level > self.current_mdd_level:
                await self._record_mdd_event('level_increase', current_capital, 
                                            f'MDD Level {self.current_mdd_level} → {new_mdd_level}')
                
                # 회복 모드 활성화
                if new_mdd_level >= 1:
                    self.recovery_mode_active = True
                
                # 알림 전송
                if self.notification_manager and new_mdd_level >= 1:
                    level_names = {1: "Level 1 (30%)", 2: "Level 2 (35%)", 
                                 3: "Level 3 (40%)", 4: "Level 4 (50%)"}
                    size_percentages = {1: 70, 2: 50, 3: 30, 4: 10}
                    
                    await self.notification_manager.send_alert(
                        event_type='LARGE_LOSS' if new_mdd_level >= 3 else 'POSITION_WARNING',
                        title=f'⚠️ MDD {level_names[new_mdd_level]} 도달',
                        message=(
                            f"<b>현재 MDD:</b> {self.current_mdd:.1f}%\n"
                            f"<b>MDD 레벨:</b> {new_mdd_level}\n"
                            f"<b>포지션 크기:</b> {size_percentages[new_mdd_level]}%로 축소\n"
                            f"<b>현재 자본:</b> ${current_capital:,.2f}\n\n"
                            f"리스크 관리를 위해 포지션 크기가 조정됩니다."
                        )
                    )
            
            # 레벨 하락 (MDD 개선)
            elif new_mdd_level < self.current_mdd_level:
                await self._record_mdd_event('level_decrease', current_capital, 
                                            f'MDD Level {self.current_mdd_level} → {new_mdd_level}')
            
            self.current_mdd_level = new_mdd_level
        
        # MDD 단계별 포지션 크기 조정
        base_multiplier = self.get_mdd_position_multiplier()
        
        # 회복 모드 적용
        if self.recovery_mode_active and self.params['mdd_recovery_mode']:
            final_multiplier = min(base_multiplier * self.current_recovery_multiplier, 
                                 self.params['max_recovery_size'])
        else:
            final_multiplier = base_multiplier
        
        restrictions['position_size_multiplier'] = final_multiplier
        
        # MDD 수준별 설명
        if new_mdd_level >= 3:
            restrictions['reason'] = f'MDD Level 3: {self.current_mdd:.1f}% (Size: {final_multiplier*100:.0f}%)'
        elif new_mdd_level >= 2:
            restrictions['reason'] = f'MDD Level 2: {self.current_mdd:.1f}% (Size: {final_multiplier*100:.0f}%)'
        elif new_mdd_level >= 1:
            restrictions['reason'] = f'MDD Level 1: {self.current_mdd:.1f}% (Size: {final_multiplier*100:.0f}%)'
        else:
            restrictions['reason'] = f'Normal trading (MDD: {self.current_mdd:.1f}%)'
        
        # 포지션이 없고 MDD가 높은 경우 특별 처리
        if (self.active_positions_count == 0 and 
            self.params['force_trade_if_no_position'] and 
            new_mdd_level >= 2):
            # 포지션이 없으면 최소한의 거래는 허용
            restrictions['allow_new_trades'] = True
            restrictions['position_size_multiplier'] = max(0.1, final_multiplier * 0.5)
            restrictions['reason'] += ' [No position - minimal trading allowed]'
        
        # MDD 회복 체크
        if self.current_mdd <= self.params['mdd_recovery_threshold'] and self.recovery_mode_active:
            self.recovery_mode_active = False
            self.current_recovery_multiplier = 1.0
            self.consecutive_wins = 0
            
            await self._record_mdd_event('recovered', current_capital, 
                                        f'MDD 회복: {self.current_mdd:.1f}%')
            
            # 회복 알림
            if self.notification_manager:
                await self.notification_manager.send_alert(
                    event_type='POSITION_RESUMED',
                    title='✅ MDD 회복',
                    message=(
                        f"<b>현재 MDD:</b> {self.current_mdd:.1f}%\n"
                        f"<b>회복 임계값:</b> {self.params['mdd_recovery_threshold']:.1f}%\n\n"
                        f"정상 거래가 재개됩니다."
                    )
                )
        
        # 통계 업데이트
        if final_multiplier < 1.0:
            self.stats['trades_with_reduced_size'] += 1
        
        return restrictions
    
    async def _record_mdd_event(self, event_type: str, capital: float, action: str):
        """MDD 이벤트 기록"""
        event = MDDEvent(
            timestamp=datetime.now(),
            event_type=event_type,
            mdd_value=self.current_mdd,
            capital=capital,
            peak_capital=self.peak_capital,
            mdd_level=self.current_mdd_level,
            action_taken=action,
            details={
                'recovery_mode': self.recovery_mode_active,
                'recovery_multiplier': self.current_recovery_multiplier,
                'consecutive_wins': self.consecutive_wins,
                'active_positions': self.active_positions_count
            }
        )
        
        self.mdd_events.append(event)
        self.stats['total_mdd_events'] += 1
        
        # 최근 100개 이벤트만 유지
        if len(self.mdd_events) > 100:
            self.mdd_events = self.mdd_events[-100:]
        
        logger.info(f"MDD 이벤트: {event_type} - {action}")
    
    def update_recovery_status(self, trade_won: bool):
        """거래 결과에 따른 회복 상태 업데이트"""
        if not self.recovery_mode_active:
            return
        
        if trade_won:
            self.consecutive_wins += 1
            # 연속 승리 시 포지션 크기 점진적 증가
            if self.consecutive_wins >= self.params['recovery_win_threshold']:
                old_multiplier = self.current_recovery_multiplier
                self.current_recovery_multiplier = min(
                    self.current_recovery_multiplier + self.params['recovery_size_increment'],
                    self.params['max_recovery_size']
                )
                self.consecutive_wins = 0  # 리셋
                
                if self.current_recovery_multiplier > old_multiplier:
                    logger.info(f"🔄 Recovery multiplier increased: "
                              f"{old_multiplier:.1f} → {self.current_recovery_multiplier:.1f}")
        else:
            self.consecutive_wins = 0
            # 패배 시 회복 배수 약간 감소 (너무 급격하지 않게)
            self.current_recovery_multiplier = max(
                self.current_recovery_multiplier - self.params['recovery_size_increment'] * 0.5,
                0.1
            )
    
    def skip_trade_by_mdd(self):
        """MDD로 인한 거래 스킵 기록"""
        self.stats['trades_skipped_by_mdd'] += 1
    
    def update_position_count(self, count: int):
        """활성 포지션 수 업데이트"""
        self.active_positions_count = count
        
        if count == 0:
            self.time_without_position += 1
        else:
            self.time_without_position = 0
    
    def get_mdd_status(self) -> Dict:
        """현재 MDD 상태 반환"""
        return {
            'current_mdd': self.current_mdd,
            'mdd_level': self.current_mdd_level,
            'peak_capital': self.peak_capital,
            'recovery_mode': self.recovery_mode_active,
            'recovery_multiplier': self.current_recovery_multiplier,
            'consecutive_wins': self.consecutive_wins,
            'position_multiplier': self.get_mdd_position_multiplier(),
            'last_update': self.last_mdd_update.isoformat(),
            'status': self._get_mdd_status_text()
        }
    
    def _get_mdd_status_text(self) -> str:
        """MDD 상태 텍스트"""
        if self.current_mdd >= self.params['mdd_emergency_stop']:
            return "🔴 긴급 정지"
        elif self.current_mdd_level >= 3:
            return "🔴 Level 3 (위험)"
        elif self.current_mdd_level >= 2:
            return "🟡 Level 2 (주의)"
        elif self.current_mdd_level >= 1:
            return "🟠 Level 1 (관찰)"
        else:
            return "🟢 정상"
    
    def get_mdd_history(self, hours: int = 24) -> List[Dict]:
        """MDD 히스토리 조회"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        return [
            {
                'timestamp': record['timestamp'].isoformat(),
                'mdd': record['mdd'],
                'mdd_level': record['mdd_level'],
                'capital': record['capital'],
                'peak_capital': record['peak_capital'],
                'recovery_multiplier': record.get('recovery_multiplier', 1.0)
            }
            for record in self.mdd_history
            if record['timestamp'] >= cutoff_time
        ]
    
    def get_mdd_events(self) -> List[Dict]:
        """MDD 이벤트 리스트 반환"""
        return [event.to_dict() for event in self.mdd_events]
    
    def get_statistics(self) -> Dict:
        """MDD 통계 반환"""
        # 레벨별 시간 계산
        for record in self.mdd_history:
            level = record.get('mdd_level', 0)
            if level >= 1:
                self.stats['time_in_mdd_level_1'] += 1
            if level >= 2:
                self.stats['time_in_mdd_level_2'] += 1
            if level >= 3:
                self.stats['time_in_mdd_level_3'] += 1
            if level >= 4:
                self.stats['time_in_mdd_level_4'] += 1
        
        total_time = len(self.mdd_history) if self.mdd_history else 1
        
        return {
            **self.stats,
            'current_mdd': self.current_mdd,
            'current_mdd_level': self.current_mdd_level,
            'peak_capital': self.peak_capital,
            'recovery_mode': self.recovery_mode_active,
            'time_in_level_1_pct': self.stats['time_in_mdd_level_1'] / total_time * 100,
            'time_in_level_2_pct': self.stats['time_in_mdd_level_2'] / total_time * 100,
            'time_in_level_3_pct': self.stats['time_in_mdd_level_3'] / total_time * 100,
            'time_in_level_4_pct': self.stats['time_in_mdd_level_4'] / total_time * 100,
            'total_events': len(self.mdd_events)
        }
    
    def reset_peak(self):
        """Peak 자본 리셋 (새로운 거래 기간 시작 시)"""
        self.peak_capital = 0.0
        self.current_mdd = 0.0
        self.current_mdd_level = 0
        self.recovery_mode_active = False
        self.current_recovery_multiplier = 1.0
        self.consecutive_wins = 0
        logger.info("MDD Manager: Peak 자본 리셋")
    
    def detect_capital_transfer(self, current_capital: float, threshold_pct: float = 20.0) -> bool:
        """자본 이체 감지 (급격한 잔고 감소)
        
        Args:
            current_capital: 현재 자본
            threshold_pct: 이체 감지 임계값 (기본 20%)
            
        Returns:
            bool: 이체가 감지되면 True
        """
        if self.peak_capital <= 0:
            return False
            
        # 이전 자본 대비 감소율 계산
        if hasattr(self, '_last_capital'):
            capital_change_pct = ((self._last_capital - current_capital) / self._last_capital) * 100
            
            # 급격한 감소 + 짧은 시간 내 발생
            if capital_change_pct >= threshold_pct:
                time_since_update = (datetime.now() - self.last_mdd_update).total_seconds()
                
                # 5분 이내에 20% 이상 감소하면 이체로 판단
                if time_since_update < 300:
                    logger.warning(f"자본 이체 감지: {capital_change_pct:.1f}% 감소 ({time_since_update:.0f}초 내)")
                    return True
        
        # 현재 자본 저장
        self._last_capital = current_capital
        return False
    
    def adjust_for_transfer(self, current_capital: float, auto_detect: bool = True):
        """계좌 이체에 대한 MDD 조정
        
        Args:
            current_capital: 현재 자본
            auto_detect: 자동 감지 활성화 여부
        """
        if auto_detect and self.detect_capital_transfer(current_capital):
            logger.info(f"계좌 이체 감지 - Peak Capital 자동 조정")
            logger.info(f"이전 Peak: ${self.peak_capital:,.2f}, 새 Peak: ${current_capital:,.2f}")
            
            # Peak을 현재 자본으로 조정
            self.peak_capital = current_capital
            self.current_mdd = 0.0
            self.current_mdd_level = 0
            
            # 회복 모드 해제
            self.recovery_mode_active = False
            self.current_recovery_multiplier = 1.0
            
            # 이벤트 기록
            asyncio.create_task(self._record_mdd_event(
                'transfer_detected',
                current_capital,
                f'계좌 이체 감지 - Peak 자동 조정'
            ))
            
            # 알림 전송
            if self.notification_manager:
                asyncio.create_task(self.notification_manager.send_alert(
                    event_type='SYSTEM_INFO',
                    title='💰 계좌 이체 감지',
                    message=(
                        f"<b>계좌 이체가 감지되었습니다.</b>\n\n"
                        f"<b>새로운 Peak Capital:</b> ${current_capital:,.2f}\n"
                        f"<b>MDD:</b> 0.0%로 재설정\n\n"
                        f"정상적인 거래가 계속됩니다."
                    )
                ))
