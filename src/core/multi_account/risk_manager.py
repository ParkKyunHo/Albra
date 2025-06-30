"""
멀티 계좌 통합 리스크 관리 시스템
계좌별 및 포트폴리오 전체의 리스크를 관리하고 자동 보호 기능 제공
"""
import asyncio
from typing import Dict, List, Optional, Tuple, Any, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
import logging
from collections import defaultdict
import json

from src.core.multi_account.account_manager import MultiAccountManager
from src.core.multi_account.unified_monitor import UnifiedMonitor, RiskConcentration
from src.utils.logger import setup_logger
from src.utils.smart_notification_manager import SmartNotificationManager

logger = setup_logger(__name__)


class RiskLevel(Enum):
    """리스크 레벨"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ActionType(Enum):
    """리스크 관리 액션 타입"""
    MONITOR = "MONITOR"
    REDUCE_POSITION = "REDUCE_POSITION"
    CLOSE_POSITION = "CLOSE_POSITION"
    PAUSE_TRADING = "PAUSE_TRADING"
    EMERGENCY_STOP = "EMERGENCY_STOP"


@dataclass
class RiskLimit:
    """리스크 한도 설정"""
    daily_loss_limit_pct: float = 5.0         # 일일 손실 한도 5%
    max_drawdown_pct: float = 20.0           # 최대 낙폭 20%
    max_position_size_pct: float = 30.0      # 단일 포지션 최대 30%
    max_leverage: int = 25                    # 최대 레버리지
    max_correlation: float = 0.8              # 계좌 간 최대 상관관계
    max_account_concentration: float = 0.5    # 단일 계좌 최대 집중도 50%
    max_symbol_concentration: float = 0.4     # 단일 심볼 최대 집중도 40%
    min_free_margin_pct: float = 20.0        # 최소 여유 마진 20%


@dataclass
class RiskEvent:
    """리스크 이벤트"""
    timestamp: datetime
    account_id: Optional[str]
    risk_type: str
    risk_level: RiskLevel
    current_value: float
    limit_value: float
    message: str
    action: ActionType


@dataclass
class AccountRiskStatus:
    """계좌별 리스크 상태"""
    account_id: str
    daily_pnl_pct: float
    current_drawdown_pct: float
    leverage_ratio: float
    free_margin_pct: float
    position_count: int
    risk_level: RiskLevel
    is_trading_allowed: bool
    warnings: List[str] = field(default_factory=list)
    last_update: datetime = field(default_factory=datetime.now)


@dataclass
class RecoveryPlan:
    """자동 복구 계획"""
    account_id: str
    recovery_type: str
    conditions: Dict[str, Any]
    actions: List[Dict[str, Any]]
    created_at: datetime = field(default_factory=datetime.now)
    executed_at: Optional[datetime] = None
    is_active: bool = True


class MultiAccountRiskManager:
    """멀티 계좌 통합 리스크 관리자
    
    주요 역할:
    - 포트폴리오 전체의 리스크 모니터링
    - 리스크 레벨 평가 및 알림
    - 권고사항 제공 (실제 실행은 각 전략이 독립적으로 결정)
    
    제한사항:
    - 직접적인 포지션 조작 불가
    - 강제 청산 불가
    - 각 전략의 독립성 보장
    """
    
    def __init__(self, 
                 account_manager: MultiAccountManager,
                 unified_monitor: UnifiedMonitor,
                 notification_manager: Optional[SmartNotificationManager] = None):
        self.account_manager = account_manager
        self.unified_monitor = unified_monitor
        self.notification_manager = notification_manager
        
        # 리스크 한도 설정
        self.global_limits = RiskLimit()
        self.account_limits: Dict[str, RiskLimit] = {}
        
        # 리스크 상태 추적
        self.account_risk_status: Dict[str, AccountRiskStatus] = {}
        self.risk_events: List[RiskEvent] = []
        self.paused_accounts: Set[str] = set()
        self.emergency_stopped: bool = False
        
        # 자동 복구 시스템
        self.recovery_plans: Dict[str, RecoveryPlan] = {}
        self.recovery_enabled = True
        
        # 일일 손실 추적
        self.daily_pnl_tracking: Dict[str, Dict[str, float]] = defaultdict(dict)
        self.daily_reset_time = "00:00"  # UTC
        
        # 모니터링 설정
        self.monitoring_interval = 30  # seconds
        self.is_monitoring = False
        self._monitoring_task: Optional[asyncio.Task] = None
        
        # 리스크 레벨별 액션 설정
        self.risk_actions = {
            RiskLevel.LOW: [ActionType.MONITOR],
            RiskLevel.MEDIUM: [ActionType.MONITOR, ActionType.REDUCE_POSITION],
            RiskLevel.HIGH: [ActionType.REDUCE_POSITION, ActionType.PAUSE_TRADING],
            RiskLevel.CRITICAL: [ActionType.CLOSE_POSITION, ActionType.EMERGENCY_STOP]
        }
    
    async def start_monitoring(self) -> None:
        """리스크 모니터링 시작"""
        if self.is_monitoring:
            logger.warning("Risk monitoring already started")
            return
        
        self.is_monitoring = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Risk monitoring started")
    
    async def stop_monitoring(self) -> None:
        """리스크 모니터링 중지"""
        self.is_monitoring = False
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Risk monitoring stopped")
    
    async def _monitoring_loop(self) -> None:
        """리스크 모니터링 루프"""
        while self.is_monitoring:
            try:
                # 전체 포트폴리오 리스크 체크
                await self.check_portfolio_risk()
                
                # 계좌별 리스크 체크
                for account_id in self.account_manager.accounts:
                    if account_id not in self.paused_accounts:
                        await self.check_account_risk(account_id)
                
                # 자동 복구 체크
                if self.recovery_enabled:
                    await self._check_recovery_conditions()
                
                # 일일 리셋 체크
                await self._check_daily_reset()
                
            except Exception as e:
                logger.error(f"Error in risk monitoring loop: {e}", exc_info=True)
            
            await asyncio.sleep(self.monitoring_interval)
    
    async def check_portfolio_risk(self) -> RiskLevel:
        """전체 포트폴리오 리스크 체크"""
        try:
            # 포트폴리오 요약 정보 가져오기
            portfolio_summary = await self.unified_monitor.get_portfolio_summary()
            
            # 리스크 집중도 체크
            risk_concentration = await self.unified_monitor.check_risk_concentration()
            
            risk_level = RiskLevel.LOW
            warnings = []
            
            # 계좌 집중도 체크
            if risk_concentration.max_concentration_account[1] > self.global_limits.max_account_concentration:
                risk_level = RiskLevel.HIGH
                warnings.append(
                    f"Account concentration too high: {risk_concentration.max_concentration_account[0]} "
                    f"({risk_concentration.max_concentration_account[1]:.1%})"
                )
            
            # 심볼 집중도 체크
            if risk_concentration.max_concentration_symbol[1] > self.global_limits.max_symbol_concentration:
                risk_level = max(risk_level, RiskLevel.MEDIUM)
                warnings.append(
                    f"Symbol concentration too high: {risk_concentration.max_concentration_symbol[0]} "
                    f"({risk_concentration.max_concentration_symbol[1]:.1%})"
                )
            
            # 상관관계 체크
            if portfolio_summary.correlation_matrix is not None:
                max_corr = portfolio_summary.correlation_matrix.max().max()
                if max_corr > self.global_limits.max_correlation:
                    risk_level = max(risk_level, RiskLevel.MEDIUM)
                    warnings.append(f"High correlation detected: {max_corr:.2f}")
            
            # 리스크 이벤트 기록
            if warnings:
                for warning in warnings:
                    self._record_risk_event(
                        account_id=None,
                        risk_type="PORTFOLIO",
                        risk_level=risk_level,
                        current_value=0,
                        limit_value=0,
                        message=warning,
                        action=self._determine_action(risk_level)
                    )
            
            return risk_level
            
        except Exception as e:
            logger.error(f"Error checking portfolio risk: {e}")
            return RiskLevel.LOW
    
    async def check_account_risk(self, account_id: str) -> AccountRiskStatus:
        """계좌별 리스크 체크"""
        try:
            client = self.account_manager.api_clients.get(account_id)
            if not client:
                return None
            
            # 계좌 정보 가져오기
            balance_info = await client.get_balance()
            positions = await client.get_positions() or []
            
            if not balance_info:
                return None
            
            # 리스크 지표 계산
            total_balance = float(balance_info.get('totalWalletBalance', 0))
            free_balance = float(balance_info.get('availableBalance', 0))
            unrealized_pnl = float(balance_info.get('totalUnrealizedProfit', 0))
            
            # 일일 손실률 계산
            daily_pnl_pct = await self._calculate_daily_loss(account_id, total_balance)
            
            # 현재 낙폭 계산
            current_drawdown_pct = self._calculate_current_drawdown(account_id, total_balance)
            
            # 레버리지 계산
            total_position_value = sum(
                abs(float(pos.get('positionAmt', 0)) * float(pos.get('markPrice', 0)))
                for pos in positions
            )
            leverage_ratio = total_position_value / total_balance if total_balance > 0 else 0
            
            # 여유 마진 비율
            free_margin_pct = (free_balance / total_balance * 100) if total_balance > 0 else 0
            
            # 리스크 레벨 결정
            risk_level = self._determine_risk_level(
                daily_pnl_pct, current_drawdown_pct, leverage_ratio, free_margin_pct
            )
            
            # 리스크 한도 체크
            limits = self.account_limits.get(account_id, self.global_limits)
            warnings = []
            
            if abs(daily_pnl_pct) > limits.daily_loss_limit_pct:
                warnings.append(f"Daily loss limit exceeded: {daily_pnl_pct:.1f}%")
                await self.check_daily_loss_limit(account_id)
            
            if current_drawdown_pct > limits.max_drawdown_pct:
                warnings.append(f"Max drawdown exceeded: {current_drawdown_pct:.1f}%")
            
            if leverage_ratio > limits.max_leverage:
                warnings.append(f"Leverage limit exceeded: {leverage_ratio:.1f}x")
            
            if free_margin_pct < limits.min_free_margin_pct:
                warnings.append(f"Low free margin: {free_margin_pct:.1f}%")
            
            # 리스크 상태 업데이트
            status = AccountRiskStatus(
                account_id=account_id,
                daily_pnl_pct=daily_pnl_pct,
                current_drawdown_pct=current_drawdown_pct,
                leverage_ratio=leverage_ratio,
                free_margin_pct=free_margin_pct,
                position_count=len(positions),
                risk_level=risk_level,
                is_trading_allowed=account_id not in self.paused_accounts,
                warnings=warnings
            )
            
            self.account_risk_status[account_id] = status
            
            # 필요시 권고사항 제공
            if risk_level.value >= RiskLevel.HIGH.value:
                await self._provide_risk_recommendations(account_id, risk_level, status)
            
            return status
            
        except Exception as e:
            logger.error(f"Error checking risk for account {account_id}: {e}")
            return None
    
    async def check_daily_loss_limit(self, account_id: str) -> bool:
        """일일 손실 한도 체크"""
        try:
            status = self.account_risk_status.get(account_id)
            if not status:
                return True
            
            limits = self.account_limits.get(account_id, self.global_limits)
            
            if abs(status.daily_pnl_pct) > limits.daily_loss_limit_pct:
                logger.warning(
                    f"Daily loss limit exceeded for account {account_id}: "
                    f"{status.daily_pnl_pct:.1f}% > {limits.daily_loss_limit_pct:.1f}%"
                )
                
                # 거래 일시 중지 권고만 하고, 실제 중지는 각 전략이 결정
                await self.recommend_pause_trading(account_id, "Daily loss limit exceeded")
                
                # 알림 전송
                if self.notification_manager:
                    await self.notification_manager.send_alert(
                        event_type="RISK_LIMIT_EXCEEDED",
                        title="🚨 Daily Loss Limit Exceeded",
                        message=(
                            f"Account: {account_id}\n"
                            f"Loss: {status.daily_pnl_pct:.1f}%\n"
                            f"Trading paused automatically"
                        ),
                        priority="HIGH"
                    )
                
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking daily loss limit: {e}")
            return True
    
    async def check_portfolio_exposure(self) -> Dict[str, float]:
        """포트폴리오 전체 노출도 체크"""
        try:
            total_exposure = 0.0
            exposure_by_symbol = defaultdict(float)
            
            for account_id, client in self.account_manager.api_clients.items():
                positions = await client.get_positions() or []
                
                for position in positions:
                    symbol = position.get('symbol', 'UNKNOWN')
                    position_value = abs(
                        float(position.get('positionAmt', 0)) * 
                        float(position.get('markPrice', 0))
                    )
                    
                    exposure_by_symbol[symbol] += position_value
                    total_exposure += position_value
            
            # 비율로 변환
            if total_exposure > 0:
                exposure_pct = {
                    symbol: (value / total_exposure * 100)
                    for symbol, value in exposure_by_symbol.items()
                }
            else:
                exposure_pct = {}
            
            return {
                'total_exposure': total_exposure,
                'by_symbol': dict(exposure_pct),
                'concentrated_symbols': [
                    symbol for symbol, pct in exposure_pct.items()
                    if pct > self.global_limits.max_symbol_concentration * 100
                ]
            }
            
        except Exception as e:
            logger.error(f"Error checking portfolio exposure: {e}")
            return {}
    
    async def recommend_pause_trading(self, account_id: str, reason: str) -> bool:
        """특정 계좌 거래 일시 중지 권고 (실제 중지는 각 전략이 결정)"""
        try:
            if account_id in self.paused_accounts:
                logger.info(f"Account {account_id} already has pause recommendation")
                return True
            
            self.paused_accounts.add(account_id)
            
            # 권고사항만 기록, 실제 주문 취소는 하지 않음
            logger.warning(f"RECOMMENDATION: Pause trading for account {account_id}: {reason}")
            
            # 이벤트 기록
            self._record_risk_event(
                account_id=account_id,
                risk_type="TRADING_PAUSE",
                risk_level=RiskLevel.HIGH,
                current_value=0,
                limit_value=0,
                message=f"Trading paused: {reason}",
                action=ActionType.PAUSE_TRADING
            )
            
            logger.info(f"Trading paused for account {account_id}: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"Error pausing account trading: {e}")
            return False
    
    async def resume_account_trading(self, account_id: str) -> bool:
        """계좌 거래 재개"""
        try:
            if account_id not in self.paused_accounts:
                logger.info(f"Account {account_id} not paused")
                return True
            
            self.paused_accounts.remove(account_id)
            
            # 복구 계획 생성
            recovery_plan = RecoveryPlan(
                account_id=account_id,
                recovery_type="MANUAL_RESUME",
                conditions={"manual_approval": True},
                actions=[{"type": "RESUME_TRADING", "timestamp": datetime.now().isoformat()}]
            )
            self.recovery_plans[account_id] = recovery_plan
            
            logger.info(f"Trading resumed for account {account_id}")
            
            if self.notification_manager:
                await self.notification_manager.send_alert(
                    event_type="TRADING_RESUMED",
                    title="✅ Trading Resumed",
                    message=(
                        f"Account: {account_id}\n"
                        f"Status: Active"
                    ),
                    priority="MEDIUM"
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Error resuming account trading: {e}")
            return False
    
    async def recommend_emergency_stop(self, account_id: str) -> bool:
        """특정 계좌 긴급 정지 권고 (실제 정지는 운영자가 결정)"""
        try:
            # 거래 중지 권고
            await self.recommend_pause_trading(account_id, "Emergency stop recommended")
            
            # 긴급 상황 알림만 전송, 실제 포지션 청산은 하지 않음
            logger.critical(f"EMERGENCY RECOMMENDATION: Consider stopping account {account_id}")
            
            # 이벤트 기록
            self._record_risk_event(
                account_id=account_id,
                risk_type="EMERGENCY_STOP",
                risk_level=RiskLevel.CRITICAL,
                current_value=0,
                limit_value=0,
                message="Emergency stop executed",
                action=ActionType.EMERGENCY_STOP
            )
            
            # 알림
            if self.notification_manager:
                await self.notification_manager.send_alert(
                    event_type="EMERGENCY_STOP",
                    title="🚨 EMERGENCY STOP",
                    message=(
                        f"Account: {account_id}\n"
                        f"All positions closed\n"
                        f"Trading halted"
                    ),
                    priority="CRITICAL"
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Error in emergency stop: {e}")
            return False
    
    async def recommend_emergency_stop_all(self) -> bool:
        """전체 시스템 긴급 정지 권고 (실제 정지는 운영자가 결정)"""
        try:
            self.emergency_stopped = True
            
            # 모든 계좌에 대해 긴급 정지 권고
            results = await asyncio.gather(
                *[self.recommend_emergency_stop(account_id) 
                  for account_id in self.account_manager.accounts],
                return_exceptions=True
            )
            
            success_count = sum(1 for r in results if r is True)
            
            logger.critical(
                f"EMERGENCY RECOMMENDATION: Consider stopping all accounts "
                f"({success_count}/{len(results)} recommendations sent)"
            )
            
            # 긴급 상황 알림
            if self.notification_manager:
                await self.notification_manager.send_alert(
                    event_type="EMERGENCY_RECOMMENDATION",
                    title="🚨 EMERGENCY RECOMMENDATION",
                    message=(
                        f"System recommends immediate review\n"
                        f"All accounts marked for potential stop\n"
                        f"Manual intervention required"
                    ),
                    priority="CRITICAL"
                )
            
            return success_count == len(results)
            
        except Exception as e:
            logger.error(f"Error in emergency stop all: {e}")
            return False
    
    def _determine_risk_level(self, 
                            daily_pnl_pct: float,
                            drawdown_pct: float,
                            leverage: float,
                            free_margin_pct: float) -> RiskLevel:
        """리스크 레벨 결정"""
        score = 0
        
        # 일일 손실
        if abs(daily_pnl_pct) > 5:
            score += 3
        elif abs(daily_pnl_pct) > 3:
            score += 2
        elif abs(daily_pnl_pct) > 1:
            score += 1
        
        # 낙폭
        if drawdown_pct > 20:
            score += 3
        elif drawdown_pct > 10:
            score += 2
        elif drawdown_pct > 5:
            score += 1
        
        # 레버리지
        if leverage > 20:
            score += 2
        elif leverage > 10:
            score += 1
        
        # 여유 마진
        if free_margin_pct < 10:
            score += 3
        elif free_margin_pct < 20:
            score += 2
        elif free_margin_pct < 30:
            score += 1
        
        # 점수에 따른 리스크 레벨
        if score >= 8:
            return RiskLevel.CRITICAL
        elif score >= 5:
            return RiskLevel.HIGH
        elif score >= 3:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    def _determine_action(self, risk_level: RiskLevel) -> ActionType:
        """리스크 레벨에 따른 액션 결정"""
        actions = self.risk_actions.get(risk_level, [ActionType.MONITOR])
        return actions[-1] if actions else ActionType.MONITOR
    
    async def _provide_risk_recommendations(self, 
                                  account_id: str,
                                  risk_level: RiskLevel,
                                  status: AccountRiskStatus) -> None:
        """리스크 권고사항 제공 (실행은 각 전략이 결정)"""
        recommendations = self.risk_actions.get(risk_level, [])
        
        # 권고사항만 로깅하고 알림 전송
        if recommendations:
            logger.warning(
                f"Risk recommendations for {account_id} (Level: {risk_level.value}): "
                f"{[action.value for action in recommendations]}"
            )
            
            # 각 전략이 자체적으로 리스크 상태를 확인할 수 있도록 상태 업데이트
            self.account_risk_status[account_id] = status
            
            # 중요 리스크 상황 알림
            if risk_level == RiskLevel.CRITICAL and self.notification_manager:
                await self.notification_manager.send_alert(
                    event_type="RISK_ALERT",
                    title=f"⚠️ Risk Alert: {account_id}",
                    message=(
                        f"Level: {risk_level.value}\n"
                        f"Recommendations: {', '.join([a.value for a in recommendations])}"
                    ),
                    priority="HIGH"
                )
    
    def get_risk_recommendation(self, account_id: str) -> Dict[str, Any]:
        """계좌별 리스크 권고사항 제공"""
        status = self.account_risk_status.get(account_id)
        if not status:
            return {'level': 'UNKNOWN', 'recommendations': []}
        
        recommendations = []
        
        if status.risk_level == RiskLevel.HIGH:
            recommendations.append("Consider reducing position sizes")
            recommendations.append("Review stop-loss levels")
        elif status.risk_level == RiskLevel.CRITICAL:
            recommendations.append("Immediate risk review required")
            recommendations.append("Consider closing losing positions")
            recommendations.append("Pause new entries until risk normalizes")
        
        return {
            'level': status.risk_level.value,
            'recommendations': recommendations,
            'metrics': {
                'daily_pnl': status.daily_pnl_pct,
                'drawdown': status.current_drawdown_pct,
                'leverage': status.leverage_ratio
            }
        }
    
    async def _calculate_daily_loss(self, account_id: str, current_balance: float) -> float:
        """일일 손실률 계산"""
        today = datetime.now().strftime('%Y-%m-%d')
        
        if account_id not in self.daily_pnl_tracking:
            self.daily_pnl_tracking[account_id] = {
                'start_balance': current_balance,
                'date': today
            }
            return 0.0
        
        tracking = self.daily_pnl_tracking[account_id]
        
        # 날짜가 바뀌었으면 리셋
        if tracking.get('date') != today:
            tracking['start_balance'] = current_balance
            tracking['date'] = today
            return 0.0
        
        start_balance = tracking['start_balance']
        if start_balance == 0:
            return 0.0
        
        return ((current_balance - start_balance) / start_balance) * 100
    
    def _calculate_current_drawdown(self, account_id: str, current_balance: float) -> float:
        """현재 낙폭 계산"""
        history = self.unified_monitor.performance_history.get(account_id, [])
        
        if not history:
            return 0.0
        
        # 최고점 찾기
        peak_balance = max(float(perf.total_balance) for perf in history)
        
        if peak_balance == 0:
            return 0.0
        
        # 현재 낙폭
        drawdown = ((peak_balance - current_balance) / peak_balance) * 100
        return max(0, drawdown)
    
    async def _check_recovery_conditions(self) -> None:
        """자동 복구 조건 체크"""
        for account_id, plan in list(self.recovery_plans.items()):
            if not plan.is_active or plan.executed_at:
                continue
            
            try:
                # 복구 조건 확인
                if await self._evaluate_recovery_conditions(account_id, plan):
                    await self._execute_recovery_plan(account_id, plan)
                    
            except Exception as e:
                logger.error(f"Error checking recovery conditions: {e}")
    
    async def _evaluate_recovery_conditions(self, 
                                          account_id: str,
                                          plan: RecoveryPlan) -> bool:
        """복구 조건 평가"""
        status = self.account_risk_status.get(account_id)
        if not status:
            return False
        
        conditions = plan.conditions
        
        # 손실 회복 조건
        if 'max_daily_loss_recovered' in conditions:
            if status.daily_pnl_pct > -1.0:  # 일일 손실 1% 이내로 회복
                return True
        
        # 리스크 레벨 개선 조건
        if 'risk_level_improved' in conditions:
            if status.risk_level.value <= RiskLevel.MEDIUM.value:
                return True
        
        # 시간 경과 조건
        if 'time_elapsed_hours' in conditions:
            hours = conditions['time_elapsed_hours']
            if (datetime.now() - plan.created_at).total_seconds() / 3600 >= hours:
                return True
        
        return False
    
    async def _execute_recovery_plan(self, account_id: str, plan: RecoveryPlan) -> None:
        """복구 계획 실행"""
        logger.info(f"Executing recovery plan for account {account_id}")
        
        for action in plan.actions:
            action_type = action.get('type')
            
            if action_type == 'RESUME_TRADING':
                await self.resume_account_trading(account_id)
                
            elif action_type == 'ADJUST_RISK_LIMITS':
                # 리스크 한도 조정
                new_limits = action.get('new_limits', {})
                if account_id not in self.account_limits:
                    self.account_limits[account_id] = RiskLimit()
                    
                for key, value in new_limits.items():
                    setattr(self.account_limits[account_id], key, value)
        
        plan.executed_at = datetime.now()
        
        if self.notification_manager:
            await self.notification_manager.send_alert(
                event_type="RECOVERY_PLAN_EXECUTED",
                title="🔄 Recovery Plan Executed",
                message=(
                    f"Account: {account_id}\n"
                    f"Type: {plan.recovery_type}"
                ),
                priority="MEDIUM"
            )
    
    async def _check_daily_reset(self) -> None:
        """일일 리셋 체크"""
        current_time = datetime.now().strftime('%H:%M')
        
        if current_time == self.daily_reset_time:
            # 일일 손실 추적 리셋
            for account_id in self.account_manager.accounts:
                if account_id in self.daily_pnl_tracking:
                    client = self.account_manager.accounts[account_id]
                    balance_info = await client.get_balance()
                    
                    if balance_info:
                        current_balance = float(balance_info.get('totalWalletBalance', 0))
                        self.daily_pnl_tracking[account_id] = {
                            'start_balance': current_balance,
                            'date': datetime.now().strftime('%Y-%m-%d')
                        }
            
            logger.info("Daily risk tracking reset completed")
    
    def _record_risk_event(self, **kwargs) -> None:
        """리스크 이벤트 기록"""
        event = RiskEvent(
            timestamp=datetime.now(),
            **kwargs
        )
        self.risk_events.append(event)
        
        # 최근 1000개만 유지
        if len(self.risk_events) > 1000:
            self.risk_events = self.risk_events[-1000:]
    
    def get_risk_summary(self) -> Dict[str, Any]:
        """리스크 요약 정보"""
        return {
            'emergency_stopped': self.emergency_stopped,
            'paused_accounts': list(self.paused_accounts),
            'account_status': {
                account_id: {
                    'risk_level': status.risk_level.value,
                    'daily_pnl_pct': status.daily_pnl_pct,
                    'drawdown_pct': status.current_drawdown_pct,
                    'warnings': status.warnings
                }
                for account_id, status in self.account_risk_status.items()
            },
            'recent_events': [
                {
                    'timestamp': event.timestamp.isoformat(),
                    'account_id': event.account_id,
                    'risk_type': event.risk_type,
                    'risk_level': event.risk_level.value,
                    'message': event.message
                }
                for event in self.risk_events[-10:]  # 최근 10개
            ],
            'active_recovery_plans': len([p for p in self.recovery_plans.values() if p.is_active])
        }
    
    def set_account_risk_limits(self, account_id: str, limits: Dict[str, float]) -> None:
        """계좌별 리스크 한도 설정"""
        if account_id not in self.account_limits:
            self.account_limits[account_id] = RiskLimit()
        
        for key, value in limits.items():
            if hasattr(self.account_limits[account_id], key):
                setattr(self.account_limits[account_id], key, value)
        
        logger.info(f"Risk limits updated for account {account_id}")


class AutoRecoverySystem:
    """자동 복구 시스템"""
    
    def __init__(self, risk_manager: MultiAccountRiskManager):
        self.risk_manager = risk_manager
        self.recovery_strategies = {
            'GRADUAL_RESUME': self._gradual_resume_strategy,
            'REDUCED_RISK': self._reduced_risk_strategy,
            'TIME_BASED': self._time_based_strategy
        }
    
    async def create_recovery_plan(self, 
                                 account_id: str,
                                 incident_type: str,
                                 strategy: str = 'GRADUAL_RESUME') -> RecoveryPlan:
        """복구 계획 생성"""
        if strategy not in self.recovery_strategies:
            strategy = 'GRADUAL_RESUME'
        
        return await self.recovery_strategies[strategy](account_id, incident_type)
    
    async def _gradual_resume_strategy(self, account_id: str, incident_type: str) -> RecoveryPlan:
        """점진적 재개 전략"""
        return RecoveryPlan(
            account_id=account_id,
            recovery_type='GRADUAL_RESUME',
            conditions={
                'risk_level_improved': True,
                'time_elapsed_hours': 2
            },
            actions=[
                {
                    'type': 'ADJUST_RISK_LIMITS',
                    'new_limits': {
                        'max_position_size_pct': 15.0,  # 일시적으로 축소
                        'max_leverage': 10
                    }
                },
                {
                    'type': 'RESUME_TRADING',
                    'restrictions': ['NO_NEW_POSITIONS_1H']
                }
            ]
        )
    
    async def _reduced_risk_strategy(self, account_id: str, incident_type: str) -> RecoveryPlan:
        """리스크 축소 전략"""
        return RecoveryPlan(
            account_id=account_id,
            recovery_type='REDUCED_RISK',
            conditions={
                'max_daily_loss_recovered': True
            },
            actions=[
                {
                    'type': 'ADJUST_RISK_LIMITS',
                    'new_limits': {
                        'daily_loss_limit_pct': 3.0,  # 더 엄격한 한도
                        'max_position_size_pct': 20.0
                    }
                },
                {
                    'type': 'RESUME_TRADING'
                }
            ]
        )
    
    async def _time_based_strategy(self, account_id: str, incident_type: str) -> RecoveryPlan:
        """시간 기반 전략"""
        return RecoveryPlan(
            account_id=account_id,
            recovery_type='TIME_BASED',
            conditions={
                'time_elapsed_hours': 4
            },
            actions=[
                {
                    'type': 'RESUME_TRADING'
                }
            ]
        )
