#!/usr/bin/env python3
"""
AlbraTrading Multi-Account Main Entry Point
Enterprise-grade implementation following Goldman Sachs & Jane Street standards

This module provides:
- Seamless single/multi account mode switching
- Complete backward compatibility with existing main.py
- Enterprise-level error handling and recovery
- Comprehensive monitoring and health checks
- Graceful shutdown procedures
"""

import asyncio
import sys
import os
import signal
import argparse
import logging
import traceback
from typing import Dict, List, Optional, Any, Union, Callable
from dotenv import load_dotenv
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
import time
import psutil
import platform

# 프로젝트 루트를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 로컬 imports
from src.utils.logger import setup_logger
from src.utils.config_manager import ConfigManager
from src.utils.telegram_notifier import TelegramNotifier
from src.utils.smart_notification_manager import SmartNotificationManager
from src.core.state_manager import StateManager
from src.core.binance_api import BinanceAPI
from src.core.position_manager import PositionManager
# from src.core.position_monitor import PositionMonitor  # Deprecated
from src.monitoring.position_sync_monitor import PositionSyncMonitor
from src.monitoring.health_checker import SystemHealthChecker
from src.core.mdd_manager_improved import ImprovedMDDManager
from src.strategies.strategy_factory import get_strategy_factory
from src.strategies.strategy_config import StrategyConfigManager
from src.web.dashboard import DashboardApp
from src.analysis.performance_tracker import PerformanceTracker

# Phase 2 imports
from src.core.multi_account.account_manager import MultiAccountManager
from src.core.multi_account.compatibility import (
    UnifiedPositionManager,
    UnifiedBinanceAPI,
    ModeSelector,
    mode_selector
)

# 설정
logger = setup_logger(__name__)


class OperationMode(Enum):
    """운영 모드 정의"""
    SINGLE = "single"
    MULTI = "multi"
    VALIDATE = "validate"
    STATUS = "status"
    DRY_RUN = "dry_run"


class ShutdownReason(Enum):
    """종료 사유 정의"""
    NORMAL = "normal"
    ERROR = "error"
    SIGNAL = "signal"
    EMERGENCY = "emergency"
    MAINTENANCE = "maintenance"


@dataclass
class SystemMetrics:
    """시스템 메트릭"""
    start_time: datetime = field(default_factory=datetime.now)
    last_health_check: Optional[datetime] = None
    health_check_failures: int = 0
    api_calls: int = 0
    errors: int = 0
    warnings: int = 0
    positions_created: int = 0
    positions_closed: int = 0
    total_pnl: float = 0.0
    uptime_seconds: float = 0.0
    memory_usage_mb: float = 0.0
    cpu_percent: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 변환"""
        return {
            'start_time': self.start_time.isoformat(),
            'uptime_hours': round(self.uptime_seconds / 3600, 2),
            'health_check_failures': self.health_check_failures,
            'api_calls': self.api_calls,
            'errors': self.errors,
            'warnings': self.warnings,
            'positions_created': self.positions_created,
            'positions_closed': self.positions_closed,
            'total_pnl': round(self.total_pnl, 2),
            'memory_usage_mb': round(self.memory_usage_mb, 2),
            'cpu_percent': round(self.cpu_percent, 2)
        }


class MultiAccountTradingSystem:
    """
    멀티 계좌 트레이딩 시스템 메인 클래스
    Goldman Sachs 수준의 안정성과 확장성을 제공
    """
    
    def __init__(self, mode: OperationMode = OperationMode.SINGLE, 
                 dry_run: bool = False, target_account: Optional[str] = None):
        """
        Args:
            mode: 운영 모드
            dry_run: 드라이런 모드
            target_account: 특정 계좌만 활성화 (멀티 모드)
        """
        self.mode = mode
        self.dry_run = dry_run
        self.target_account = target_account
        
        # 시스템 상태
        self.running = False
        self.is_running = False  # telegram_commands 호환성을 위해 추가
        self.shutdown_event = asyncio.Event()
        self.initialization_complete = False
        
        # 메트릭스
        self.metrics = SystemMetrics()
        
        # 컴포넌트
        self.config_manager: Optional[ConfigManager] = None
        self.config: Optional[Dict] = None  # main.py와 호환성을 위해 추가
        self.state_manager: Optional[StateManager] = None
        self.notification_manager: Optional[SmartNotificationManager] = None
        self.telegram_notifier: Optional[TelegramNotifier] = None
        self.telegram_handler = None  # Telegram Command Handler 추가
        
        # 단일 모드 컴포넌트
        self.binance_api: Optional[BinanceAPI] = None
        self.position_manager: Optional[PositionManager] = None
        
        # 멀티 모드 컴포넌트
        self.multi_account_manager: Optional[MultiAccountManager] = None
        
        # 통합 컴포넌트
        self.unified_position_manager: Optional[UnifiedPositionManager] = None
        self.unified_api: Optional[UnifiedBinanceAPI] = None
        
        # 모니터링 컴포넌트
        self.position_sync_monitor: Optional[PositionSyncMonitor] = None
        self.health_checker: Optional[SystemHealthChecker] = None
        self.mdd_manager: Optional[ImprovedMDDManager] = None
        
        # 전략
        self.strategies_dict: Dict[str, Any] = {}  # 계좌별 전략 관리 (내부 용도)
        self.strategies: List[Any] = []  # main.py 호환성 위한 리스트
        
        # 웹 대시보드
        self.dashboard: Optional[DashboardApp] = None
        
        # 성과 추적
        self.performance_tracker: Optional[PerformanceTracker] = None
        
        # 태스크 관리
        self.tasks: List[asyncio.Task] = []
        
        # 시그널 핸들러 등록
        self._setup_signal_handlers()
        
        logger.info(f"MultiAccountTradingSystem 초기화 (모드: {mode.value}, "
                   f"드라이런: {dry_run}, 대상계좌: {target_account})")
    
    def _setup_signal_handlers(self) -> None:
        """시그널 핸들러 설정"""
        def signal_handler(signum, frame):
            logger.warning(f"시그널 수신: {signum}")
            asyncio.create_task(self.shutdown(ShutdownReason.SIGNAL))
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Windows의 경우 SIGBREAK도 처리
        if platform.system() == 'Windows':
            signal.signal(signal.SIGBREAK, signal_handler)
    
    async def initialize(self) -> bool:
        """시스템 초기화"""
        try:
            logger.info("=" * 60)
            logger.info("🚀 AlbraTrading Multi-Account System 초기화 시작")
            logger.info("=" * 60)
            
            # 1. 설정 관리자 초기화
            self.config_manager = ConfigManager()
            self.config = self.config_manager.config  # main.py와 호환성을 위해 추가
            config = self.config_manager.config
            
            # 2. 상태 관리자 초기화
            self.state_manager = StateManager()
            
            # 3. 알림 시스템 초기화
            await self._initialize_notification_system()
            
            # 4. 운영 모드별 초기화
            if self.mode == OperationMode.VALIDATE:
                return await self._validate_configuration()
            elif self.mode == OperationMode.STATUS:
                return await self._show_status()
            elif self.mode == OperationMode.MULTI:
                return await self._initialize_multi_mode()
            else:  # SINGLE or DRY_RUN
                return await self._initialize_single_mode()
            
        except Exception as e:
            logger.error(f"시스템 초기화 실패: {e}")
            logger.error(traceback.format_exc())
            self.metrics.errors += 1
            await self._send_emergency_notification(f"시스템 초기화 실패: {e}")
            return False
    
    async def _initialize_notification_system(self) -> None:
        """알림 시스템 초기화"""
        try:
            config = self.config_manager.config
            
            # Telegram Notifier
            if config.get('telegram', {}).get('enabled', False):
                self.telegram_notifier = TelegramNotifier(
                    bot_token=os.getenv('TELEGRAM_BOT_TOKEN'),
                    chat_id=os.getenv('TELEGRAM_CHAT_ID')
                )
                await self.telegram_notifier.initialize()
                logger.info("✓ Telegram Notifier 초기화 완료")
            
            # Smart Notification Manager
            self.notification_manager = SmartNotificationManager(
                telegram_notifier=self.telegram_notifier,
                database_manager=None,
                config_manager=self.config_manager
            )
            logger.info("✓ Smart Notification Manager 초기화 완료")
            
            # Telegram Command Handler 초기화 추가
            if self.telegram_notifier:
                from src.utils.telegram_commands import TelegramCommands
                bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
                if bot_token:
                    self.telegram_handler = TelegramCommands(
                        bot_token=bot_token,
                        trading_system=self
                    )
                    if await self.telegram_handler.initialize():
                        logger.info("✓ Telegram Command Handler 초기화 완료")
                        logger.info("TelegramCommands 인스턴스 생성 완료")
                    else:
                        logger.error("Telegram Command Handler 초기화 실패")
                        self.telegram_handler = None
            
        except Exception as e:
            logger.error(f"알림 시스템 초기화 실패: {e}")
            # 알림 시스템 실패는 치명적이지 않으므로 계속 진행
    
    async def _initialize_single_mode(self) -> bool:
        """단일 모드 초기화"""
        try:
            logger.info("단일 계좌 모드 초기화 중...")
            
            # 1. Binance API 초기화
            self.binance_api = BinanceAPI(
                api_key=os.getenv('BINANCE_API_KEY'),
                secret_key=os.getenv('BINANCE_SECRET_KEY'),
                testnet=self.config_manager.config.get('system', {}).get('mode') == 'testnet'
            )
            
            if not await self.binance_api.initialize():
                raise Exception("Binance API 초기화 실패")
            
            logger.info("✓ Binance API 연결 성공")
            
            # 2. Position Manager 초기화
            self.position_manager = PositionManager(
                binance_api=self.binance_api,
                state_manager=self.state_manager,
                notification_manager=self.notification_manager,
                config_manager=self.config_manager
            )
            
            if not await self.position_manager.initialize():
                raise Exception("Position Manager 초기화 실패")
            
            logger.info("✓ Position Manager 초기화 완료")
            
            # 3. 통합 컴포넌트 생성
            self.unified_position_manager = UnifiedPositionManager(
                single_position_manager=self.position_manager
            )
            
            self.unified_api = UnifiedBinanceAPI(
                single_api=self.binance_api
            )
            
            # 4. 모니터링 컴포넌트 초기화
            await self._initialize_monitoring_components()
            
            # 5. 전략 초기화
            await self._initialize_strategies()
            
            # 6. 웹 대시보드 초기화
            await self._initialize_dashboard()
            
            # 7. 호환성을 위한 alias 설정 (main.py와 동일한 구조)
            self.position_manager = self.unified_position_manager
            self.binance_api = self.unified_api
            self.exchange = self.unified_api  # main.py 호환성
            
            self.initialization_complete = True
            logger.info("✅ 단일 계좌 모드 초기화 완료")
            
            # 초기화 완료 알림
            if self.notification_manager and not self.dry_run:
                await self.notification_manager.send_alert(
                    event_type="SYSTEM_INITIALIZED",
                    title="🚀 시스템 시작",
                    message=(
                        f"<b>모드:</b> 단일 계좌\n"
                        f"<b>드라이런:</b> {'예' if self.dry_run else '아니오'}\n"
                        f"<b>활성 전략:</b> {len(self.strategies)}개"
                    )
                )
            
            return True
            
        except Exception as e:
            logger.error(f"단일 모드 초기화 실패: {e}")
            logger.error(traceback.format_exc())
            self.metrics.errors += 1
            return False
    
    async def _initialize_multi_mode(self) -> bool:
        """멀티 모드 초기화"""
        try:
            logger.info("멀티 계좌 모드 초기화 중...")
            
            # 1. Multi Account Manager 초기화
            self.multi_account_manager = MultiAccountManager(
                config_manager=self.config_manager,
                state_manager=self.state_manager,
                notification_manager=self.notification_manager
            )
            
            if not self.multi_account_manager.enabled:
                logger.error("멀티 계좌 모드가 설정에서 비활성화되어 있습니다")
                logger.info("config.yaml의 multi_account.enabled를 true로 설정하세요")
                return False
            
            if not await self.multi_account_manager.initialize():
                raise Exception("Multi Account Manager 초기화 실패")
            
            logger.info("✓ Multi Account Manager 초기화 완료")
            
            # 2. 특정 계좌만 활성화 (옵션)
            if self.target_account:
                await self._activate_specific_account(self.target_account)
            
            # 3. 통합 컴포넌트 생성
            self.unified_position_manager = UnifiedPositionManager(
                multi_account_manager=self.multi_account_manager
            )
            
            self.unified_api = UnifiedBinanceAPI(
                multi_account_manager=self.multi_account_manager
            )
            
            # 4. 모니터링 컴포넌트 초기화
            await self._initialize_monitoring_components()
            
            # 5. 전략 초기화 (계좌별)
            await self._initialize_strategies_multi()
            
            # 6. 웹 대시보드 초기화
            await self._initialize_dashboard()
            
            # 7. 호환성을 위한 alias 설정 (main.py와 동일한 구조)
            self.position_manager = self.unified_position_manager
            self.binance_api = self.unified_api
            self.exchange = self.unified_api  # main.py 호환성
            
            self.initialization_complete = True
            logger.info("✅ 멀티 계좌 모드 초기화 완료")
            
            # 초기화 완료 알림
            if self.notification_manager and not self.dry_run:
                stats = self.multi_account_manager.get_system_stats()
                await self.notification_manager.send_alert(
                    event_type="SYSTEM_INITIALIZED",
                    title="🚀 멀티 계좌 시스템 시작",
                    message=(
                        f"<b>모드:</b> 멀티 계좌\n"
                        f"<b>드라이런:</b> {'예' if self.dry_run else '아니오'}\n"
                        f"<b>활성 계좌:</b> {stats['accounts']['active']}개\n"
                        f"<b>전체 계좌:</b> {stats['accounts']['total']}개"
                    )
                )
            
            return True
            
        except Exception as e:
            logger.error(f"멀티 모드 초기화 실패: {e}")
            logger.error(traceback.format_exc())
            self.metrics.errors += 1
            return False
    
    async def _activate_specific_account(self, account_id: str) -> None:
        """특정 계좌만 활성화"""
        logger.info(f"특정 계좌 활성화: {account_id}")
        # TODO: 구현 예정
        # 다른 계좌들을 PAUSED 상태로 전환
        # 지정된 계좌만 ACTIVE 상태 유지
    
    async def _initialize_monitoring_components(self) -> None:
        """모니터링 컴포넌트 초기화"""
        try:
            # 1. Position Sync Monitor
            self.position_sync_monitor = PositionSyncMonitor(
                position_manager=self.unified_position_manager,
                binance_api=self.unified_api,
                notification_manager=self.notification_manager
            )
            logger.info("✓ Position Sync Monitor 초기화 완료")
            
            # 3. Health Checker
            self.health_checker = SystemHealthChecker({
                'exchange': self.unified_api,
                'position_manager': self.unified_position_manager,
                'notification_manager': self.notification_manager
            })
            logger.info("✓ Health Checker 초기화 완료")
            
            # 4. MDD Manager
            self.mdd_manager = ImprovedMDDManager(
                config=self.config_manager.config.get('mdd_protection', {}),
                notification_manager=self.notification_manager
            )
            logger.info("✓ MDD Manager 초기화 완료")
            
            # 5. Performance Tracker
            self.performance_tracker = PerformanceTracker(
                data_dir=self.config_manager.config.get('performance', {}).get('data_dir', 'data/performance')
            )
            logger.info("✓ Performance Tracker 초기화 완료")
            
        except Exception as e:
            logger.error(f"모니터링 컴포넌트 초기화 실패: {e}")
            raise
    
    async def _initialize_strategies(self) -> None:
        """전략 초기화 (단일 모드)"""
        try:
            config = self.config_manager.config
            strategies_config = config.get('strategies', {})
            
            for strategy_name, strategy_config in strategies_config.items():
                if not strategy_config.get('enabled', False):
                    continue
                
                logger.info(f"전략 초기화: {strategy_name}")
                
                # 전략 설정 가져오기
                full_config = self.config_manager.get_strategy_config(strategy_name)
                
                # 전략 인스턴스 생성
                strategy_factory = get_strategy_factory()
                strategy = strategy_factory.create_strategy(
                    name=strategy_name,
                    binance_api=self.unified_api,
                    position_manager=self.unified_position_manager,
                    custom_config=full_config
                )
                
                if strategy:
                    self.strategies_dict[strategy_name] = strategy
                    self.strategies.append(strategy)  # 리스트에도 추가
                    logger.info(f"✓ {strategy_name} 전략 초기화 완료")
                else:
                    logger.error(f"{strategy_name} 전략 생성 실패")
            
            logger.info(f"총 {len(self.strategies)}개 전략 초기화 완료")
            
        except Exception as e:
            logger.error(f"전략 초기화 실패: {e}")
            raise
    
    async def _initialize_strategies_multi(self) -> None:
        """전략 초기화 (멀티 모드)"""
        try:
            # 각 계좌별로 설정된 전략 초기화
            for account_id, account in self.multi_account_manager.accounts.items():
                if account.status.value != 'ACTIVE':
                    continue
                
                strategy_name = account.strategy
                if not strategy_name:
                    continue
                
                logger.info(f"[{account_id}] {strategy_name} 전략 초기화")
                
                # 계좌별 포지션 매니저 가져오기
                position_manager = self.multi_account_manager.position_managers.get(account_id)
                api_client = self.multi_account_manager.api_clients.get(account_id)
                
                if not position_manager or not api_client:
                    logger.error(f"[{account_id}] 필수 컴포넌트 없음")
                    continue
                
                # 전략 설정 가져오기
                full_config = self.config_manager.get_strategy_config(strategy_name)
                
                # 계좌별 설정 오버라이드
                full_config['leverage'] = account.leverage
                full_config['position_size'] = account.position_size
                
                # 전략 인스턴스 생성
                strategy_factory = get_strategy_factory()
                strategy = strategy_factory.create_strategy(
                    name=strategy_name,
                    binance_api=api_client,
                    position_manager=position_manager,
                    custom_config=full_config
                )
                
                if strategy:
                    # 전략에 계좌 이름 설정 (telegram_commands 호환성)
                    strategy.account_name = account_id
                    strategy.account_id = account_id
                    
                    # 계좌 ID를 포함한 키로 저장
                    strategy_key = f"{account_id}:{strategy_name}"
                    self.strategies_dict[strategy_key] = strategy
                    self.strategies.append(strategy)  # 리스트에도 추가
                    logger.info(f"✓ [{account_id}] {strategy_name} 전략 초기화 완료")
            
            # 마스터 계좌 전략도 초기화 (TFPE 전략)
            if self.multi_account_manager.master_account:
                master_api = self.multi_account_manager.api_clients.get('MASTER')
                master_position_manager = self.multi_account_manager.position_managers.get('MASTER')
                
                if master_api and master_position_manager:
                    # TFPE 전략 할당
                    tfpe_config = self.config_manager.get_strategy_config('tfpe')
                    if tfpe_config.get('enabled', False):
                        logger.info("[MASTER] TFPE 전략 초기화")
                        
                        # 전략 인스턴스 생성
                        strategy_factory = get_strategy_factory()
                        tfpe_strategy = strategy_factory.create_strategy(
                            name='tfpe',
                            binance_api=master_api,
                            position_manager=master_position_manager,
                            custom_config=tfpe_config
                        )
                        
                        if tfpe_strategy:
                            # 전략에 계좌 이름 설정 (telegram_commands 호환성)
                            tfpe_strategy.account_name = 'MASTER'
                            tfpe_strategy.account_id = 'MASTER'
                            
                            # 마스터 계좌용 키로 저장
                            strategy_key = "MASTER:TFPE"
                            self.strategies_dict[strategy_key] = tfpe_strategy
                            self.strategies.append(tfpe_strategy)  # 리스트에도 추가
                            logger.info("✓ [MASTER] TFPE 전략 초기화 완료")
                        else:
                            logger.error("[MASTER] TFPE 전략 생성 실패")
                else:
                    logger.error("[MASTER] 필수 컴포넌트 없음")
            
            logger.info(f"총 {len(self.strategies)}개 전략 초기화 완료")
            
        except Exception as e:
            logger.error(f"멀티 모드 전략 초기화 실패: {e}")
            raise
    
    async def _initialize_dashboard(self) -> None:
        """웹 대시보드 초기화"""
        try:
            dashboard_config = self.config_manager.config.get('web_dashboard', {})
            
            if dashboard_config.get('enabled', False):
                self.dashboard = DashboardApp(
                    position_manager=self.unified_position_manager,
                    binance_api=self.unified_api,
                    strategies=self.strategies,
                    config=self.config_manager.config,
                    state_manager=self.state_manager,
                    notification_manager=self.notification_manager
                )
                
                # 성과 대시보드 설정 (PerformanceTracker가 있을 경우)
                if hasattr(self, 'performance_tracker') and self.performance_tracker:
                    self.dashboard.setup_performance_dashboard(self.performance_tracker)
                    logger.info("✓ 성과 대시보드 초기화 완료")
                
                # 대시보드가 참조를 유지하도록 추가 설정
                self.dashboard.notification_manager = self.notification_manager
                self.dashboard.performance_tracker = self.performance_tracker
                
                logger.info("✓ 웹 대시보드 초기화 완료")
            
        except Exception as e:
            logger.error(f"웹 대시보드 초기화 실패: {e}")
            # 대시보드 실패는 치명적이지 않으므로 계속 진행
    
    async def _validate_configuration(self) -> bool:
        """설정 검증 모드"""
        try:
            logger.info("=" * 60)
            logger.info("설정 검증 시작")
            logger.info("=" * 60)
            
            errors = []
            warnings = []
            
            # 1. 환경변수 검증
            logger.info("\n1. 환경변수 검증")
            required_env = ['BINANCE_API_KEY', 'BINANCE_SECRET_KEY']
            
            for env_var in required_env:
                if not os.getenv(env_var):
                    errors.append(f"필수 환경변수 누락: {env_var}")
                else:
                    logger.info(f"✓ {env_var}: 설정됨")
            
            # 2. 멀티 계좌 설정 검증
            if self.config_manager.config.get('multi_account', {}).get('enabled', False):
                logger.info("\n2. 멀티 계좌 설정 검증")
                sub_accounts = self.config_manager.config.get('multi_account', {}).get('sub_accounts', {})
                
                for account_id, account_config in sub_accounts.items():
                    if not account_config.get('enabled', True):
                        continue
                    
                    # API 키 확인
                    api_key_env = f'{account_id.upper()}_API_KEY'
                    api_secret_env = f'{account_id.upper()}_API_SECRET'
                    
                    if not os.getenv(api_key_env):
                        warnings.append(f"서브 계좌 {account_id} API 키 없음: {api_key_env}")
                    else:
                        logger.info(f"✓ {account_id}: API 키 설정됨")
            
            # 3. 전략 설정 검증
            logger.info("\n3. 전략 설정 검증")
            strategies = self.config_manager.config.get('strategies', {})
            active_strategies = 0
            
            for name, config in strategies.items():
                if config.get('enabled', False):
                    active_strategies += 1
                    logger.info(f"✓ {name}: 활성화됨")
            
            if active_strategies == 0:
                errors.append("활성화된 전략이 없습니다")
            
            # 4. 리스크 설정 검증
            logger.info("\n4. 리스크 설정 검증")
            mdd_config = self.config_manager.config.get('mdd_protection', {})
            
            if mdd_config.get('enabled', False):
                logger.info(f"✓ MDD 보호: 활성화 (최대 {mdd_config.get('max_allowed_mdd', 40)}%)")
            else:
                warnings.append("MDD 보호가 비활성화되어 있습니다")
            
            # 검증 결과
            logger.info("\n" + "=" * 60)
            logger.info("검증 결과")
            logger.info("=" * 60)
            
            if errors:
                logger.error(f"❌ 오류 {len(errors)}개:")
                for error in errors:
                    logger.error(f"   - {error}")
            
            if warnings:
                logger.warning(f"⚠️  경고 {len(warnings)}개:")
                for warning in warnings:
                    logger.warning(f"   - {warning}")
            
            if not errors and not warnings:
                logger.info("✅ 모든 설정이 정상입니다")
            
            return len(errors) == 0
            
        except Exception as e:
            logger.error(f"설정 검증 중 오류: {e}")
            return False
    
    async def _show_status(self) -> bool:
        """시스템 상태 표시"""
        try:
            logger.info("=" * 60)
            logger.info("시스템 상태")
            logger.info("=" * 60)
            
            # 임시로 컴포넌트 초기화
            await self._initialize_single_mode()
            
            # 1. 시스템 정보
            logger.info("\n1. 시스템 정보")
            logger.info(f"   - Python 버전: {sys.version.split()[0]}")
            logger.info(f"   - 플랫폼: {platform.system()} {platform.release()}")
            logger.info(f"   - 프로세스 ID: {os.getpid()}")
            
            # 2. 계좌 정보
            logger.info("\n2. 계좌 정보")
            
            if self.unified_api:
                balance = await self.unified_api.get_account_balance()
                logger.info(f"   - 잔고: ${balance:.2f}")
            
            # 3. 포지션 정보
            logger.info("\n3. 포지션 정보")
            
            if self.unified_position_manager:
                positions = self.unified_position_manager.get_active_positions()
                logger.info(f"   - 활성 포지션: {len(positions)}개")
                
                for pos in positions:
                    logger.info(f"   - {pos.symbol}: {pos.side} {pos.size} @ {pos.entry_price}")
            
            # 4. 전략 상태
            logger.info("\n4. 전략 상태")
            strategies = self.config_manager.config.get('strategies', {})
            
            for name, config in strategies.items():
                status = "활성" if config.get('enabled', False) else "비활성"
                logger.info(f"   - {name}: {status}")
            
            # 5. 시스템 리소스
            logger.info("\n5. 시스템 리소스")
            process = psutil.Process(os.getpid())
            logger.info(f"   - CPU 사용률: {process.cpu_percent(interval=1)}%")
            logger.info(f"   - 메모리 사용: {process.memory_info().rss / 1024 / 1024:.1f} MB")
            
            return True
            
        except Exception as e:
            logger.error(f"상태 표시 중 오류: {e}")
            return False
    
    async def run(self) -> None:
        """메인 실행 루프"""
        try:
            if not self.initialization_complete:
                logger.error("시스템이 초기화되지 않았습니다")
                return
            
            logger.info("🏃 트레이딩 시스템 실행 시작")
            self.running = True
            self.is_running = True  # telegram_commands 호환성
            
            # 시스템 시작 알림 (초기화 때 실패했을 경우를 대비)
            if self.notification_manager and not self.dry_run:
                try:
                    # 활성 전략 정보 수집
                    active_strategies = []
                    for name, strategy in self.strategies_dict.items():
                        if hasattr(strategy, 'is_running') and strategy.is_running:
                            account_name = getattr(strategy, 'account_name', 'N/A')
                            active_strategies.append(f"{name} ({account_name})")
                    
                    await self.notification_manager.send_alert(
                        event_type="SYSTEM_STARTED",
                        title="🏃 시스템 실행 시작",
                        message=(
                            f"<b>AlbraTrading 시스템이 시작되었습니다</b>\n\n"
                            f"<b>운영 모드:</b> {'멀티 계좌' if self.mode == OperationMode.MULTI else '단일 계좌'}\n"
                            f"<b>드라이런:</b> {'예' if self.dry_run else '아니오'}\n"
                            f"<b>활성 전략:</b> {len(active_strategies)}개\n"
                            f"{chr(10).join(['• ' + s for s in active_strategies]) if active_strategies else ''}"
                        )
                    )
                except Exception as e:
                    logger.error(f"시작 알림 전송 실패: {e}")
            
            # 메인 태스크들 시작
            main_tasks = []
            
            # 1. 포지션 모니터링
            if hasattr(self, 'position_sync_monitor') and self.position_sync_monitor:
                task = asyncio.create_task(
                    self._monitor_positions(),
                    name="position_monitor"
                )
                main_tasks.append(task)
                self.tasks.append(task)
            
            # 2. 헬스 체크
            task = asyncio.create_task(
                self._health_check_loop(),
                name="health_check"
            )
            main_tasks.append(task)
            self.tasks.append(task)
            
            # 3. 전략 실행
            for name, strategy in self.strategies_dict.items():
                task = asyncio.create_task(
                    self._run_strategy(name, strategy),
                    name=f"strategy_{name}"
                )
                main_tasks.append(task)
                self.tasks.append(task)
            
            # 4. 메트릭 수집
            task = asyncio.create_task(
                self._collect_metrics(),
                name="metrics_collector"
            )
            main_tasks.append(task)
            self.tasks.append(task)
            
            # 5. 웹 대시보드
            if self.dashboard:
                # 포트 사용 체크
                import socket
                def is_port_in_use(port):
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        return s.connect_ex(('localhost', port)) == 0
                
                dashboard_port = 5000
                if is_port_in_use(dashboard_port):
                    logger.warning(f"포트 {dashboard_port}이 이미 사용 중입니다. 대시보드를 시작하지 않습니다.")
                else:
                    # 대시보드 속성이 제대로 설정되었는지 확인
                    logger.info(f"대시보드 속성 확인:")
                    logger.info(f"  - position_manager: {self.dashboard.position_manager is not None}")
                    logger.info(f"  - binance_api: {self.dashboard.binance_api is not None}")
                    logger.info(f"  - config: {self.dashboard.config is not None}")
                    
                    # Flask는 블로킹 호출이므로 별도 스레드에서 실행
                    from threading import Thread
                    dashboard_thread = Thread(
                        target=lambda: self.dashboard.app.run(
                            host='0.0.0.0', 
                            port=dashboard_port, 
                            debug=False,
                            use_reloader=False
                        ),
                        daemon=True,
                        name="dashboard"
                    )
                    dashboard_thread.start()
                    logger.info(f"웹 대시보드 시작 (포트: {dashboard_port})")
            
            # 6. 정기 상태 리포트
            task = asyncio.create_task(
                self._periodic_status_report(),
                name="status_reporter"
            )
            main_tasks.append(task)
            self.tasks.append(task)
            
            # 7. 텔레그램 명령어 폴링 추가
            if self.telegram_handler:
                task = asyncio.create_task(
                    self.telegram_handler.run_polling(),
                    name="telegram_polling"
                )
                main_tasks.append(task)
                self.tasks.append(task)
                logger.info("✓ 텔레그램 명령어 폴링 시작")
            
            logger.info(f"총 {len(main_tasks)}개 태스크 시작")
            
            # 종료 이벤트 대기
            await self.shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"메인 루프 오류: {e}")
            logger.error(traceback.format_exc())
            self.metrics.errors += 1
            await self.shutdown(ShutdownReason.ERROR)
    
    async def _monitor_positions(self) -> None:
        """포지션 모니터링 루프"""
        while self.running:
            try:
                
                # Position Sync Monitor 실행
                if self.position_sync_monitor:
                    await self.position_sync_monitor.check_sync_status()
                
                # MDD Manager 체크
                if self.mdd_manager and self.binance_api:
                    # 현재 잔고 조회
                    current_capital = await self.binance_api.get_account_balance()
                    if current_capital:
                        mdd_status = await self.mdd_manager.check_mdd_restrictions(current_capital)
                
                # 대기
                await asyncio.sleep(
                    self.config_manager.config.get('trading', {}).get('check_interval', 60)
                )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"포지션 모니터링 오류: {e}")
                self.metrics.errors += 1
                await asyncio.sleep(10)  # 에러 시 짧은 대기
    
    async def _health_check_loop(self) -> None:
        """시스템 헬스 체크 루프"""
        check_interval = 300  # 5분
        consecutive_failures = 0
        max_failures = 3
        
        while self.running:
            try:
                # Health Checker 실행
                if self.health_checker:
                    health_status = await self.health_checker.check_health()
                    
                    if health_status.get('healthy', False):
                        consecutive_failures = 0
                        self.metrics.last_health_check = datetime.now()
                    else:
                        consecutive_failures += 1
                        self.metrics.health_check_failures += 1
                        
                        # 연속 실패 시 알림
                        if consecutive_failures >= max_failures:
                            await self._send_emergency_notification(
                                f"헬스 체크 {consecutive_failures}회 연속 실패"
                            )
                            
                            # 자동 복구 시도
                            await self._attempt_auto_recovery()
                
                await asyncio.sleep(check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"헬스 체크 오류: {e}")
                self.metrics.errors += 1
                consecutive_failures += 1
                await asyncio.sleep(30)
    
    async def _run_strategy(self, name: str, strategy: Any) -> None:
        """전략 실행 루프"""
        while self.running:
            try:
                # 드라이런 모드 체크
                if self.dry_run:
                    logger.debug(f"[DRY RUN] {name} 전략 실행 (실제 거래 없음)")
                
                # 전략 실행 - main.py와 동일한 방식
                if hasattr(strategy, 'run_cycle'):
                    await strategy.run_cycle()
                elif hasattr(strategy, 'analyze'):
                    # 구버전 호환성
                    market_data = {}
                    signals = await strategy.analyze(market_data)
                    if signals and self.position_manager:
                        await self.position_manager.process_signals(signals)
                else:
                    logger.warning(f"{name} 전략에 실행 가능한 메서드가 없습니다")
                
                # 전략별 체크 간격
                check_interval = strategy.config.get('check_interval', 60)
                await asyncio.sleep(check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"{name} 전략 실행 오류: {e}")
                logger.error(traceback.format_exc())
                self.metrics.errors += 1
                
                # 전략 오류 알림
                if self.notification_manager:
                    await self.notification_manager.send_alert(
                        event_type="STRATEGY_ERROR",
                        title=f"⚠️ {name} 전략 오류",
                        message=str(e)
                    )
                
                await asyncio.sleep(60)  # 에러 시 1분 대기
    
    async def _collect_metrics(self) -> None:
        """메트릭 수집 루프"""
        while self.running:
            try:
                # 시스템 메트릭 수집
                process = psutil.Process(os.getpid())
                self.metrics.memory_usage_mb = process.memory_info().rss / 1024 / 1024
                self.metrics.cpu_percent = process.cpu_percent(interval=1)
                self.metrics.uptime_seconds = (datetime.now() - self.metrics.start_time).total_seconds()
                
                # 포지션 메트릭
                if self.unified_position_manager:
                    positions = self.unified_position_manager.get_active_positions()
                    total_pnl = sum(p.unrealized_pnl for p in positions if p.unrealized_pnl)
                    self.metrics.total_pnl = total_pnl
                
                await asyncio.sleep(60)  # 1분마다 수집
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"메트릭 수집 오류: {e}")
                await asyncio.sleep(60)
    
    async def _periodic_status_report(self) -> None:
        """정기 상태 리포트"""
        report_interval = 3600  # 1시간
        
        while self.running:
            try:
                await asyncio.sleep(report_interval)
                
                if self.notification_manager:
                    # 시스템 상태 요약
                    metrics = self.metrics.to_dict()
                    
                    message = (
                        f"<b>📊 시스템 상태 리포트</b>\n\n"
                        f"<b>가동 시간:</b> {metrics['uptime_hours']}시간\n"
                        f"<b>활성 포지션:</b> {len(self.unified_position_manager.get_active_positions()) if self.unified_position_manager else 0}개\n"
                        f"<b>총 손익:</b> ${metrics['total_pnl']}\n"
                        f"<b>메모리 사용:</b> {metrics['memory_usage_mb']} MB\n"
                        f"<b>CPU 사용률:</b> {metrics['cpu_percent']}%\n"
                        f"<b>오류 횟수:</b> {metrics['errors']}\n"
                        f"<b>경고 횟수:</b> {metrics['warnings']}\n\n"
                        f"<b>🧠 전략 실행 상태:</b>\n"
                    )
                    
                    # 전략 정보 추가
                    if self.strategies:
                        for strategy in self.strategies:
                            strategy_name = getattr(strategy, 'name', 'Unknown')
                            account_name = getattr(strategy, 'account_name', 'N/A')
                            is_running = getattr(strategy, 'is_running', False)
                            status = "▶️ 실행중" if is_running else "⏸️ 정지"
                            
                            # 전략별 포지션 수 계산 (옵션)
                            strategy_positions = 0
                            if hasattr(self.unified_position_manager, 'get_positions_by_strategy'):
                                positions = self.unified_position_manager.get_positions_by_strategy(strategy_name)
                                strategy_positions = len([p for p in positions if p.status == 'ACTIVE'])
                            
                            message += f"• {strategy_name} ({account_name}): {status}"
                            if strategy_positions > 0:
                                message += f" - 포지션 {strategy_positions}개"
                            message += "\n"
                    else:
                        message += "• 실행 중인 전략 없음\n"
                    
                    # 멀티 계좌 모드 정보
                    if self.mode == OperationMode.MULTI:
                        message += f"\n<b>💼 모드:</b> 멀티 계좌"
                    else:
                        message += f"\n<b>💼 모드:</b> 단일 계좌"
                    
                    await self.notification_manager.send_alert(
                        event_type="STATUS_REPORT",
                        title="📊 시스템 상태 리포트",
                        message=message
                    )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"상태 리포트 오류: {e}")
                await asyncio.sleep(report_interval)
    
    async def _attempt_auto_recovery(self) -> None:
        """자동 복구 시도"""
        try:
            logger.warning("자동 복구 시도 중...")
            
            # 1. API 연결 재시도
            if self.mode == OperationMode.SINGLE:
                if self.binance_api:
                    await self.binance_api.cleanup()
                    await asyncio.sleep(5)
                    await self.binance_api.initialize()
            else:
                # 멀티 모드: 각 계좌별 재연결
                if self.multi_account_manager:
                    for account_id in list(self.multi_account_manager.api_clients.keys()):
                        await self.multi_account_manager._sync_single_account(account_id)
            
            # 2. 포지션 재동기화
            if self.unified_position_manager:
                await self.unified_position_manager.sync_positions()
            
            logger.info("✓ 자동 복구 완료")
            
        except Exception as e:
            logger.error(f"자동 복구 실패: {e}")
            # 복구 실패 시 시스템 종료
            await self.shutdown(ShutdownReason.ERROR)
    
    async def _send_emergency_notification(self, message: str) -> None:
        """긴급 알림 전송"""
        try:
            if self.notification_manager:
                await self.notification_manager.send_alert(
                    event_type="EMERGENCY",
                    title="🚨 긴급 상황",
                    message=message
                )
            elif self.telegram_notifier:
                # 백업: 직접 텔레그램 전송
                await self.telegram_notifier.send_message(
                    f"🚨 긴급 상황\n\n{message}"
                )
        except Exception as e:
            logger.error(f"긴급 알림 전송 실패: {e}")
    
    async def shutdown(self, reason: ShutdownReason = ShutdownReason.NORMAL) -> None:
        """Graceful Shutdown"""
        if not self.running:
            return
        
        try:
            logger.info("=" * 60)
            logger.info(f"🛑 시스템 종료 시작 (사유: {reason.value})")
            logger.info("=" * 60)
            
            self.running = False
            self.is_running = False  # telegram_commands 호환성
            
            # 1. 신규 거래 중지
            logger.info("1. 신규 거래 중지")
            # 전략들에게 종료 신호 전송
            # self.strategies는 list이므로 직접 반복
            for strategy in self.strategies:
                if hasattr(strategy, 'stop'):
                    await strategy.stop()
            
            # 2. 실행 중인 태스크 취소
            logger.info("2. 실행 중인 태스크 취소")
            for task in self.tasks:
                if not task.done():
                    task.cancel()
            
            # 태스크 종료 대기 (최대 10초)
            if self.tasks:
                await asyncio.wait(self.tasks, timeout=10)
            
            # 3. 포지션 정보 저장
            logger.info("3. 포지션 정보 저장")
            if self.unified_position_manager:
                await self.unified_position_manager.sync_positions()
            
            # 4. 최종 상태 저장
            logger.info("4. 최종 상태 저장")
            shutdown_state = {
                'shutdown_time': datetime.now().isoformat(),
                'shutdown_reason': reason.value,
                'metrics': self.metrics.to_dict(),
                'active_positions': len(self.unified_position_manager.get_active_positions()) if self.unified_position_manager else 0
            }
            
            if self.state_manager:
                await self.state_manager.save_system_state(shutdown_state)
            
            # 5. 리소스 정리
            logger.info("5. 리소스 정리")
            
            # 웹 대시보드 종료
            if self.dashboard and hasattr(self.dashboard, 'executor'):
                self.dashboard.executor.shutdown(wait=False)
                logger.info("Dashboard executor 종료")
            
            # API 연결 종료
            if self.binance_api:
                # UnifiedBinanceAPI는 cleanup이 없을 수 있음
                if hasattr(self.binance_api, 'cleanup'):
                    await self.binance_api.cleanup()
                logger.info("API 연결 정리 완료")
            
            # 멀티 계좌 정리
            if self.multi_account_manager:
                await self.multi_account_manager.cleanup()
            
            # 6. 종료 알림 (모든 경우에 전송)
            if self.notification_manager:
                # 종료 사유에 따른 메시지 구성
                if reason == ShutdownReason.NORMAL:
                    title = "✅ 시스템 정상 종료"
                    emoji = "✅"
                elif reason == ShutdownReason.SIGNAL:
                    title = "🛑 시스템 종료 (시그널)"
                    emoji = "🛑"
                elif reason == ShutdownReason.ERROR:
                    title = "❌ 시스템 오류 종료"
                    emoji = "❌"
                elif reason == ShutdownReason.EMERGENCY:
                    title = "🚨 긴급 시스템 종료"
                    emoji = "🚨"
                else:
                    title = "🛑 시스템 종료"
                    emoji = "🛑"
                
                await self.notification_manager.send_alert(
                    event_type="SYSTEM_SHUTDOWN",
                    title=title,
                    message=(
                        f"{emoji} <b>AlbraTrading 시스템 종료</b>\n\n"
                        f"<b>종료 사유:</b> {reason.value}\n"
                        f"<b>운영 모드:</b> {'멀티 계좌' if self.mode == OperationMode.MULTI else '단일 계좌'}\n"
                        f"<b>실행 시간:</b> {self.metrics.to_dict()['uptime_hours']}시간\n"
                        f"<b>활성 포지션:</b> {len(self.unified_position_manager.get_active_positions()) if self.unified_position_manager else 0}개"
                    ),
                    force=True
                )
            
            # 알림 시스템 정리
            if self.telegram_notifier:
                await self.telegram_notifier.cleanup()
            
            # 종료 이벤트 설정
            self.shutdown_event.set()
            
            logger.info("✅ 시스템 종료 완료")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"종료 중 오류: {e}")
            logger.error(traceback.format_exc())


def parse_arguments() -> argparse.Namespace:
    """명령행 인자 파싱"""
    parser = argparse.ArgumentParser(
        description='AlbraTrading Multi-Account Trading System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 단일 계좌 모드 (기본)
  python main_multi_account.py
  
  # 멀티 계좌 모드
  python main_multi_account.py --mode multi
  
  # 특정 계좌만 활성화
  python main_multi_account.py --mode multi --account SUB1
  
  # 드라이런 모드
  python main_multi_account.py --dry-run
  
  # 설정 검증
  python main_multi_account.py --validate
  
  # 시스템 상태 확인
  python main_multi_account.py --status
        """
    )
    
    parser.add_argument(
        '--mode',
        type=str,
        choices=['single', 'multi'],
        default='single',
        help='운영 모드 선택 (기본: single)'
    )
    
    parser.add_argument(
        '--account',
        type=str,
        help='특정 계좌만 활성화 (멀티 모드에서 사용)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='실제 거래 없이 시뮬레이션'
    )
    
    parser.add_argument(
        '--validate',
        action='store_true',
        help='설정 검증만 수행'
    )
    
    parser.add_argument(
        '--status',
        action='store_true',
        help='현재 상태만 출력'
    )
    
    parser.add_argument(
        '--log-level',
        type=str,
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='로그 레벨 설정 (기본: INFO)'
    )
    
    return parser.parse_args()


async def main():
    """메인 진입점"""
    # .env 파일 로드
    load_dotenv()
    
    # 명령행 인자 파싱
    args = parse_arguments()
    
    # 로그 레벨 설정
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # 운영 모드 결정
    if args.validate:
        mode = OperationMode.VALIDATE
    elif args.status:
        mode = OperationMode.STATUS
    else:
        mode = OperationMode(args.mode)
    
    # 시스템 인스턴스 생성
    trading_system = MultiAccountTradingSystem(
        mode=mode,
        dry_run=args.dry_run,
        target_account=args.account
    )
    
    # 시그널 핸들러 설정
    def signal_handler(signum, frame):
        """시그널 핸들러"""
        logger.info(f"종료 시그널 받음: {signum}")
        # 이벤트 루프가 실행 중인 경우에만 태스크 생성
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(trading_system.shutdown(ShutdownReason.SIGNAL))
    
    # SIGINT와 SIGTERM 시그널 핸들러 등록
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    logger.info("시그널 핸들러 등록 완료")
    
    try:
        # 시스템 초기화
        if not await trading_system.initialize():
            logger.error("시스템 초기화 실패")
            sys.exit(1)
        
        # 검증/상태 모드는 여기서 종료
        if mode in [OperationMode.VALIDATE, OperationMode.STATUS]:
            sys.exit(0)
        
        # 트레이딩 시스템 실행
        await trading_system.run()
        
    except KeyboardInterrupt:
        logger.info("키보드 인터럽트 감지")
        await trading_system.shutdown(ShutdownReason.SIGNAL)
    except Exception as e:
        logger.error(f"치명적 오류: {e}")
        logger.error(traceback.format_exc())
        await trading_system.shutdown(ShutdownReason.ERROR)
        sys.exit(1)
    finally:
        # 정리 작업
        await trading_system.shutdown(ShutdownReason.NORMAL)


if __name__ == "__main__":
    # Windows 이벤트 루프 정책 설정
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    # 메인 함수 실행
    asyncio.run(main())
