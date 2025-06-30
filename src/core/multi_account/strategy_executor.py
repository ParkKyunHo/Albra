# src/core/multi_account/strategy_executor.py
"""
Multi-Account Strategy Executor
각 계좌별로 전략을 실행하는 실행자
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from src.strategies.base_strategy import BaseStrategy
from src.strategies.strategy_factory import get_strategy_factory
from src.core.position_manager import PositionManager
from src.core.binance_api import BinanceAPI

logger = logging.getLogger(__name__)


class MultiAccountStrategyExecutor:
    """멀티계좌 전략 실행자"""
    
    def __init__(self, multi_account_manager, notification_manager=None):
        self.multi_account_manager = multi_account_manager
        self.notification_manager = notification_manager
        self.strategy_factory = get_strategy_factory()
        
        # 계좌별 전략 인스턴스
        self.account_strategies: Dict[str, BaseStrategy] = {}
        
        # 실행 태스크
        self.execution_tasks = []
        self.running = False
        
        logger.info("MultiAccountStrategyExecutor 초기화")
    
    async def initialize_strategies(self) -> bool:
        """각 계좌별 전략 초기화"""
        try:
            if not self.multi_account_manager.is_multi_account_enabled():
                logger.info("멀티계좌가 비활성화되어 있습니다")
                return False
            
            logger.info("계좌별 전략 초기화 시작...")
            
            # 서브계좌별 전략 생성
            for account_id, account_info in self.multi_account_manager.accounts.items():
                if account_info.status.value != 'ACTIVE':
                    logger.warning(f"{account_id} 계좌가 비활성 상태입니다")
                    continue
                
                # 해당 계좌의 API와 포지션 매니저 가져오기
                api_client = self.multi_account_manager.api_clients.get(account_id)
                position_manager = self.multi_account_manager.position_managers.get(account_id)
                
                if not api_client or not position_manager:
                    logger.error(f"{account_id}: API 클라이언트 또는 포지션 매니저 없음")
                    continue
                
                # 전략 생성
                strategy_name = account_info.strategy
                strategy = self.strategy_factory.create_strategy(
                    strategy_name,
                    binance_api=api_client,
                    position_manager=position_manager
                )
                
                if strategy:
                    # 계좌 정보 주입
                    strategy.account_name = account_id
                    strategy.account_info = account_info
                    
                    # 알림 매니저 주입
                    if self.notification_manager:
                        strategy.notification_manager = self.notification_manager
                    
                    # 계좌별 설정 적용
                    self._apply_account_config(strategy, account_info)
                    
                    self.account_strategies[account_id] = strategy
                    logger.info(f"✓ {account_id}: {strategy_name} 전략 초기화 완료")
                else:
                    logger.error(f"{account_id}: {strategy_name} 전략 생성 실패")
            
            logger.info(f"총 {len(self.account_strategies)}개 계좌 전략 초기화 완료")
            return len(self.account_strategies) > 0
            
        except Exception as e:
            logger.error(f"전략 초기화 실패: {e}")
            return False
    
    def _apply_account_config(self, strategy: BaseStrategy, account_info) -> None:
        """계좌별 설정을 전략에 적용"""
        try:
            # 기본 설정 적용
            if hasattr(strategy, 'config'):
                strategy.config['leverage'] = account_info.leverage
                strategy.config['position_size'] = account_info.position_size
                strategy.config['max_positions'] = account_info.max_positions
                
                # 심볼 설정
                if hasattr(strategy, 'symbols'):
                    strategy.symbols = account_info.symbols
                elif hasattr(strategy, 'major_coins'):
                    strategy.major_coins = account_info.symbols
            
            # 리스크 설정
            if hasattr(strategy, 'risk_config'):
                strategy.risk_config['daily_loss_limit'] = account_info.daily_loss_limit
                strategy.risk_config['max_drawdown'] = account_info.max_drawdown
            
            logger.info(f"{account_info.account_id} 전략 설정 적용 완료")
            
        except Exception as e:
            logger.error(f"전략 설정 적용 실패: {e}")
    
    async def start_execution(self) -> None:
        """전략 실행 시작"""
        if not self.account_strategies:
            logger.warning("실행할 전략이 없습니다")
            return
        
        self.running = True
        logger.info(f"{len(self.account_strategies)}개 계좌 전략 실행 시작")
        
        # 각 계좌별 실행 태스크 생성
        for account_id, strategy in self.account_strategies.items():
            task = asyncio.create_task(
                self._run_strategy_for_account(account_id, strategy)
            )
            self.execution_tasks.append(task)
        
        # 모니터링 태스크
        monitor_task = asyncio.create_task(self._monitor_accounts())
        self.execution_tasks.append(monitor_task)
    
    async def _run_strategy_for_account(self, account_id: str, strategy: BaseStrategy) -> None:
        """특정 계좌의 전략 실행"""
        logger.info(f"[{account_id}] 전략 실행 시작: {strategy.name}")
        
        while self.running:
            try:
                # 계좌 상태 확인
                account_info = self.multi_account_manager.accounts.get(account_id)
                if not account_info or account_info.status.value != 'ACTIVE':
                    logger.warning(f"[{account_id}] 계좌가 비활성 상태입니다")
                    await asyncio.sleep(60)
                    continue
                
                # 전략 실행
                if hasattr(strategy, 'run_cycle'):
                    await strategy.run_cycle()
                else:
                    logger.warning(f"[{account_id}] run_cycle 메서드가 없습니다")
                
                # 대기 (전략별 주기에 맞춤)
                interval = getattr(strategy, 'check_interval', 60)
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error(f"[{account_id}] 전략 실행 오류: {e}")
                await asyncio.sleep(60)
    
    async def _monitor_accounts(self) -> None:
        """계좌 모니터링"""
        logger.info("계좌 모니터링 시작")
        
        while self.running:
            try:
                # 전체 계좌 동기화
                sync_report = await self.multi_account_manager.sync_all_accounts()
                
                # 성과 체크
                for account_id, account_info in self.multi_account_manager.accounts.items():
                    if account_info.status.value != 'ACTIVE':
                        continue
                    
                    # 일일 손실 한도 체크
                    if account_info.performance.current_drawdown > account_info.daily_loss_limit:
                        logger.warning(f"[{account_id}] 일일 손실 한도 도달: "
                                     f"{account_info.performance.current_drawdown:.2f}%")
                        
                        # 전략 일시 정지
                        if account_id in self.account_strategies:
                            strategy = self.account_strategies[account_id]
                            if hasattr(strategy, 'pause'):
                                await strategy.pause()
                            account_info.status = 'PAUSED'
                            
                            # 알림
                            if self.notification_manager:
                                await self.notification_manager.send_alert(
                                    event_type="RISK_LIMIT_REACHED",
                                    title=f"⚠️ [{account_id}] 일일 손실 한도 도달",
                                    message=(
                                        f"<b>계좌:</b> {account_id}\n"
                                        f"<b>전략:</b> {account_info.strategy}\n"
                                        f"<b>현재 손실:</b> {account_info.performance.current_drawdown:.2f}%\n"
                                        f"<b>한도:</b> {account_info.daily_loss_limit}%\n\n"
                                        f"전략이 일시 정지되었습니다."
                                    )
                                )
                
                # 5분마다 모니터링
                await asyncio.sleep(300)
                
            except Exception as e:
                logger.error(f"계좌 모니터링 오류: {e}")
                await asyncio.sleep(60)
    
    async def stop_execution(self) -> None:
        """전략 실행 중지"""
        logger.info("전략 실행 중지 중...")
        self.running = False
        
        # 모든 태스크 취소
        for task in self.execution_tasks:
            if not task.done():
                task.cancel()
        
        # 태스크 완료 대기
        if self.execution_tasks:
            await asyncio.gather(*self.execution_tasks, return_exceptions=True)
        
        logger.info("✓ 전략 실행 중지 완료")
    
    def get_execution_status(self) -> Dict[str, Any]:
        """실행 상태 조회"""
        status = {
            'running': self.running,
            'accounts': {}
        }
        
        for account_id, strategy in self.account_strategies.items():
            account_info = self.multi_account_manager.accounts.get(account_id)
            if account_info:
                status['accounts'][account_id] = {
                    'strategy': strategy.name,
                    'status': account_info.status.value,
                    'performance': {
                        'trades': account_info.performance.total_trades,
                        'win_rate': account_info.performance.win_rate,
                        'pnl': account_info.performance.total_pnl,
                        'drawdown': account_info.performance.current_drawdown
                    }
                }
        
        return status
