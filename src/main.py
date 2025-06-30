#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Albra Trading System - Main Entry Point
전략 선택 및 실행 가능한 메인 모듈
"""

import asyncio
import signal
import sys
import os
import threading
import argparse
from typing import List, Optional
from datetime import datetime
from dotenv import load_dotenv

# 프로젝트 루트 디렉토리를 Python 경로에 추가
# main.py가 src/ 디렉토리 안에 있으므로, 부모의 부모 디렉토리가 프로젝트 루트
current_file = os.path.abspath(__file__)
src_directory = os.path.dirname(current_file)
project_root = os.path.dirname(src_directory)

# Python 경로에 프로젝트 루트 추가
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 디버깅용 출력 (배포 후 제거 가능)
print(f"Python Path: {sys.path[0]}")
print(f"Project Root: {project_root}")

from src.core.binance_api import BinanceAPI
from src.core.position_manager import PositionManager
from src.core.state_manager import StateManager
from src.core.realtime_price_monitor import RealtimePriceMonitor
from src.core.realtime_signal_processor import RealtimeSignalProcessor
from src.strategies.strategy_factory import get_strategy_factory
from src.strategies.base_strategy import BaseStrategy
from src.web.dashboard import create_dashboard
from src.utils.config_manager import ConfigManager
from src.utils.logger import setup_logger
from src.utils.smart_notification_manager import SmartNotificationManager
from src.utils.telegram_notifier import TelegramNotifier
from src.utils.telegram_commands import setup_telegram_commands, TelegramCommandHandler
from src.core.smart_resume_manager import SmartResumeManager
from src.core.safety_check_manager import SafetyCheckManager
from src.core.fast_position_monitor import FastPositionMonitor
from src.core.event_logger import get_event_logger, log_event
from src.monitoring.position_sync_monitor import PositionSyncMonitor
from src.core.phase2_integration import Phase2Integration, setup_phase2_components
from src.analysis.market_regime_analyzer import get_regime_analyzer
from src.analysis.performance_tracker import get_performance_tracker
from src.core.risk_parity_allocator import get_risk_parity_allocator
from src.core.multi_account.account_manager import MultiAccountManager
from src.core.multi_account.strategy_executor import MultiAccountStrategyExecutor

# 환경 변수 로드
load_dotenv()

logger = setup_logger(__name__)

class TradingSystem:
    """메인 트레이딩 시스템 클래스"""
    
    def __init__(self, strategy_names: Optional[List[str]] = None):
        """
        Args:
            strategy_names: 실행할 전략 이름 리스트 (None이면 모든 활성 전략)
        """
        self.config_manager = ConfigManager()
        self.config = self.config_manager.config
        self.running = False
        self.tasks = []
        self.strategy_names = strategy_names
        
        # 전략 팩토리
        self.strategy_factory = get_strategy_factory()
        self.strategies: List[BaseStrategy] = []
        
        # 핵심 컴포넌트
        self.exchange = None
        self.position_manager = None
        self.notification_manager = None
        self.telegram_notifier = None
        self.telegram_handler = None
        self.state_manager = None
        self.resume_manager = None
        self.safety_checker = None
        
        # 실시간 모니터링 컴포넌트
        self.realtime_monitor = None
        self.realtime_enabled = False
        self.fast_monitor = None  # 빠른 포지션 모니터
        
        # 이벤트 루프
        self.loop = None
        
        # 시작 시간 추가 (telegram_commands.py에서 참조)
        self.start_time = datetime.now()
        
        # 모니터링 컴포넌트
        self.event_logger = None
        self.sync_monitor = None
        
        # Phase 2 컴포넌트
        self.phase2_integration = None
        
        # 분석 컴포넌트
        self.market_regime_analyzer = None
        self.performance_tracker = None
        self.risk_parity_allocator = None
        
        # 멀티계좌 관리자
        self.multi_account_manager = None
        self.multi_strategy_executor = None
        
    async def initialize(self):
        """시스템 초기화"""
        try:
            logger.info("=" * 60)
            logger.info("Albra Trading System 초기화 시작")
            logger.info("=" * 60)
            
            # API 키 확인 및 로드
            api_key = os.getenv('BINANCE_API_KEY')
            secret_key = os.getenv('BINANCE_SECRET_KEY')
            
            if not api_key or not secret_key:
                logger.error("바이낸스 API 키가 설정되지 않았습니다. .env 파일을 확인하세요.")
                logger.error("필요한 환경변수: BINANCE_API_KEY, BINANCE_SECRET_KEY")
                return False
            
            # 테스트넷 여부 확인
            testnet = self.config.get('system', {}).get('mode', 'testnet') == 'testnet'
            
            # 거래소 API 초기화 - API 키 전달
            self.exchange = BinanceAPI(api_key=api_key, secret_key=secret_key, testnet=testnet)
            await self.exchange.initialize()
            
            # 상태 관리자 초기화
            self.state_manager = StateManager()
            
            # 멀티계좌 관리자 초기화 (서브계좌 지원)
            self.multi_account_manager = MultiAccountManager(
                config_manager=self.config_manager,
                state_manager=self.state_manager
            )
            
            # 멀티계좌 모드 확인 및 초기화
            multi_account_enabled = self.config.get('multi_account', {}).get('enabled', False)
            if multi_account_enabled:
                logger.info("멀티계좌 모드 활성화 - 서브계좌 초기화 중...")
                if await self.multi_account_manager.initialize():
                    logger.info("✓ 멀티계좌 시스템 초기화 완료")
                else:
                    logger.warning("멀티계좌 초기화 실패 - 단일 계좌 모드로 곀4속")
            else:
                logger.info("단일 계좌 모드로 실행")
            
            # 알림 시스템 초기화 (포지션 매니저보다 먼저)
            notification_manager_temp = None
            try:
                telegram_config = self.config.get('telegram', {})
                if telegram_config.get('enabled', True):
                    bot_token = telegram_config.get('bot_token') or os.getenv('TELEGRAM_BOT_TOKEN')
                    chat_id = telegram_config.get('chat_id') or os.getenv('TELEGRAM_CHAT_ID')
                    
                    
                    if bot_token and chat_id:
                        self.telegram_notifier = TelegramNotifier(
                            bot_token=bot_token,
                            chat_id=chat_id
                        )
                        
                        # TelegramNotifier 초기화 추가
                        telegram_initialized = await self.telegram_notifier.initialize()
                        if not telegram_initialized:
                            logger.error("텔레그램 봇 초기화 실패")
                            self.telegram_notifier = None
                        else:
                            self.notification_manager = SmartNotificationManager(
                                telegram_notifier=self.telegram_notifier,
                                config_manager=self.config_manager
                            )
                            await self.notification_manager.start()
                            notification_manager_temp = self.notification_manager
                            logger.info("✓ 알림 시스템 초기화 완료")
                    else:
                        logger.warning("텔레그램 봇 토큰 또는 채팅 ID가 없습니다. 알림 기능이 비활성화됩니다.")
                else:
                    logger.info("알림 시스템 비활성화됨")
                    
            except Exception as e:
                logger.error(f"알림 시스템 초기화 실패: {e}")
                logger.warning("알림 없이 계속 진행합니다.")
            
            # 포지션 매니저 초기화 (알림 매니저 전달)
            self.position_manager = PositionManager(
                binance_api=self.exchange,
                state_manager=self.state_manager,
                notification_manager=notification_manager_temp,  # 알림 매니저 전달
                config_manager=self.config_manager  # config 매니저 추가
            )
            await self.position_manager.initialize()
            
            # 텔레그램 명령어 핸들러 설정 (포지션 매니저 생성 후)
            if self.telegram_notifier and self.notification_manager:
                self.telegram_handler = TelegramCommandHandler(
                    self.position_manager,
                    self.notification_manager,
                    self
                )
                
                # 핸들러 초기화
                if self.telegram_handler.commands:
                    await self.telegram_handler.initialize()
                    logger.info("✓ 텔레그램 명령어 핸들러 초기화 완료")
                else:
                    logger.warning("텔레그램 명령어 핸들러 초기화 실패 - 봇 토큰 없음")
                    self.telegram_handler = None
            
            # 안전 체크 매니저 초기화
            self.safety_checker = SafetyCheckManager(
                self.position_manager,
                self.exchange,
                self.telegram_notifier,
                self.state_manager
            )
            
            # 안전 체크에 notification_manager 추가
            if self.notification_manager:
                self.safety_checker.notification_manager = self.notification_manager
            
            # 안전 체크 실행
            is_safe = await self.safety_checker.check_startup_safety()
            if not is_safe:
                logger.error("시스템 안전 체크 실패")
                return False
            
            # 전략 초기화
            await self._initialize_strategies()
            
            # 트레이딩 모드 확인
            tfpe_config = self.config.get('strategies', {}).get('tfpe', {})
            trading_mode = tfpe_config.get('trading_mode', 'candle_close')
            
            if trading_mode == 'candle_close':
                logger.info("트레이딩 모드: 캔들 종가 기준")
                if tfpe_config.get('candle_close_check', {}).get('use_server_time', True):
                    logger.info("  - 바이낸스 서버 시간 사용")
                else:
                    logger.info("  - 로컬 시간 사용")
            elif trading_mode == 'realtime':
                logger.info("트레이딩 모드: 실시간 모니터링")
                logger.warning("현재 실시간 모드는 개발 중입니다")
            
            # 기존 코드와의 호환성
            self.realtime_enabled = (trading_mode == 'realtime')
            
            # 스마트 재개 매니저 초기화 (전략 초기화 후)
            self.resume_manager = SmartResumeManager(
                self.position_manager,
                self.exchange,
                self.notification_manager
            )
            
            # Hybrid Trading Manager 초기화 (수동/자동 거래 통합)
            from src.core.hybrid_trading_manager import HybridTradingManager
            self.hybrid_manager = HybridTradingManager(
                self.position_manager,
                self.exchange,
                self.notification_manager
            )
            logger.info("✓ Hybrid Trading Manager 초기화 완료")
            
            # Performance Tracker 초기화
            self.performance_tracker = get_performance_tracker()
            await self.performance_tracker.start_auto_save()
            logger.info("✓ Performance Tracker 초기화 완료")
            
            # Market Regime Analyzer 초기화
            regime_config = self.config.get("market_regime", {})
            self.market_regime_analyzer = get_regime_analyzer(regime_config)
            logger.info("✓ Market Regime Analyzer 초기화 완료")
            
            # Risk Parity Allocator 초기화
            self.risk_parity_allocator = get_risk_parity_allocator(self.performance_tracker)
            logger.info("✓ Risk Parity Allocator 초기화 완료")
            
            # 빠른 포지션 모니터 초기화
            self.fast_monitor = FastPositionMonitor(
                self.position_manager,
                self.exchange,
                self.notification_manager
            )
            
            # 헬스 체커 초기화 (선택적)
            self.health_checker = None
            
            # 이벤트 로거 초기화
            self.event_logger = get_event_logger()
            await self.event_logger.start()
            logger.info("✓ 이벤트 로거 시작")
            
            # 포지션 동기화 모니터 초기화
            self.sync_monitor = PositionSyncMonitor(
                self.position_manager,
                self.exchange,
                self.notification_manager
            )
            
            # Phase 2 컴포넌트 초기화 (선택적)
            if self.config.get('phase2', {}).get('enabled', False):
                logger.info("Phase 2 컴포넌트 활성화")
                self.phase2_integration = await setup_phase2_components(self)
                if not self.phase2_integration:
                    logger.warning("Phase 2 컴포넌트 초기화 실패 - 기본 모드로 계속")
            else:
                logger.info("Phase 2 컴포넌트 비활성화")
            
            # 시스템 초기화 이벤트 로깅
            await log_event(
                "SYSTEM_INITIALIZED",
                {
                    "strategies": [s.name for s in self.strategies] if self.strategies else [],
                    "monitoring_symbols": len(self.position_manager.symbols) if hasattr(self.position_manager, 'symbols') else 0,
                    "realtime_mode": self.realtime_enabled
                },
                "INFO"
            )
            
            # 시스템 시작 알림
            if self.notification_manager:
                realtime_status = "활성화" if self.realtime_enabled else "비활성화"
                
                # 포지션 요약 추가
                position_summary = self.position_manager.get_position_summary()
                active_positions_info = f"\n활성 포지션: 자동={position_summary['auto_positions']}, 수동={position_summary['manual_positions']}"
                
                await self.notification_manager.send_alert(
                    event_type="SYSTEM_ERROR",  # CRITICAL 레벨로 즉시 전송
                    title="🚀 Albra Trading System 시작",
                    message=(
                        f"활성 전략: {', '.join([s.name for s in self.strategies]) if self.strategies else 'None'}\n"
                        f"실시간 모니터링: {realtime_status}\n"
                        f"모니터링 심볼: {len(self.position_manager.symbols) if hasattr(self.position_manager, 'symbols') else 0}개"
                        f"{active_positions_info}\n"
                        f"Hybrid Trading: ✅ 활성화\n\n"
                        f"수동 거래 명령어: /help 참조"
                    ),
                    force=True  # 강제 전송
                )
            
            logger.info("✓ 시스템 초기화 완료")
            return True
            
        except Exception as e:
            logger.error(f"시스템 초기화 실패: {e}")
            return False
    
    async def _initialize_strategies(self):
        """전략 초기화"""
        try:
            # 멀티계좌 모드인 경우
            if self.multi_account_manager and self.multi_account_manager.is_multi_account_enabled():
                logger.info("멀티계좌 모드 - 계좌별 전략 할당")
                
                # 멀티계좌 전략 실행자 생성
                self.multi_strategy_executor = MultiAccountStrategyExecutor(
                    multi_account_manager=self.multi_account_manager,
                    notification_manager=self.notification_manager
                )
                
                # 계좌별 전략 초기화
                if await self.multi_strategy_executor.initialize_strategies():
                    logger.info("✓ 멀티계좌 전략 초기화 완료")
                else:
                    logger.error("멀티계좌 전략 초기화 실패")
                
                # 마스터 계좌의 전략도 초기화 (선택적)
                if self.strategy_names:
                    # 특정 전략만 실행
                    for name in self.strategy_names:
                        strategy = self.strategy_factory.create_strategy(
                            name,
                            binance_api=self.exchange,
                            position_manager=self.position_manager
                        )
                        if strategy:
                            self.strategies.append(strategy)
                            logger.info(f"✓ 마스터 계좌 전략 초기화: {name}")
                
            else:
                # 단일 계좌 모드 (Existing Code)
                if self.strategy_names:
                    # 특정 전략만 실행
                    for name in self.strategy_names:
                        strategy = self.strategy_factory.create_strategy(
                            name,
                            binance_api=self.exchange,
                            position_manager=self.position_manager
                        )
                        if strategy:
                            self.strategies.append(strategy)
                            logger.info(f"✓ 전략 초기화: {name}")
                        else:
                            logger.error(f"전략 생성 실패: {name}")
                else:
                    # 모든 활성 전략 실행
                    self.strategies = self.strategy_factory.create_active_strategies(
                        binance_api=self.exchange,
                        position_manager=self.position_manager
                    )
                
                if not self.strategies:
                    logger.warning("활성화된 전략이 없습니다. 기본 모니터링 모드로 실행됩니다.")
                    # 빈 전략 리스트로도 시스템은 실행 가능 (포지션 모니터링만 수행)
                    return
                
                # 포지션 매니저에 전략 심볼 등록
                all_symbols = set()
                for strategy in self.strategies:
                    if hasattr(strategy, 'symbols'):
                        all_symbols.update(strategy.symbols)
                    elif hasattr(strategy, 'major_coins'):
                        all_symbols.update(strategy.major_coins)
                    
                    # 전략에 notification_manager 주입
                    if self.notification_manager and hasattr(strategy, 'notification_manager'):
                        strategy.notification_manager = self.notification_manager
                        logger.info(f"✓ {strategy.name if hasattr(strategy, 'name') else 'Unknown'} 전략에 알림 매니저 연결")
                    
                    # 분석 컴포넌트 주입
                    if hasattr(strategy, "performance_tracker"):
                        strategy.performance_tracker = self.performance_tracker
                    if hasattr(strategy, "market_regime_analyzer"):
                        strategy.market_regime_analyzer = self.market_regime_analyzer
                    if hasattr(strategy, "risk_parity_allocator"):
                        strategy.risk_parity_allocator = self.risk_parity_allocator
                
                if hasattr(self.position_manager, 'symbols'):
                    self.position_manager.symbols = list(all_symbols)
                    logger.info(f"총 {len(all_symbols)}개 심볼 모니터링")
            
        except Exception as e:
            logger.error(f"전략 초기화 실패: {e}")
            # 전략 초기화 실패해도 시스템은 계속 실행
            self.strategies = []
    
    async def start_dashboard(self):
        """웹 대시보드 시작"""
        try:
            dashboard_config = self.config.get('web_dashboard', {})
            if not dashboard_config.get('enabled', True):
                logger.info("웹 대시보드가 비활성화되어 있습니다.")
                return
                
            dashboard_thread = threading.Thread(
                target=create_dashboard,
                args=(self.position_manager, self.strategies, self.config),
                daemon=True
            )
            dashboard_thread.start()
            logger.info("✓ 웹 대시보드 시작 (http://localhost:5000)")
        except Exception as e:
            logger.error(f"대시보드 시작 실패: {e}")
            # 대시보드 실패해도 시스템은 계속 실행
    
    async def run_strategies(self):
        """전략 실행 루프"""
        logger.info("전략 실행 시작")
        
        while self.running:
            try:
                if not self.strategies:
                    # 전략이 없으면 대기만
                    await asyncio.sleep(60)
                    continue
                
                # 각 전략 실행
                for strategy in self.strategies:
                    try:
                        if hasattr(strategy, 'run_cycle'):
                            await strategy.run_cycle()
                        elif hasattr(strategy, 'analyze'):
                            # 구버전 호환성
                            market_data = {}  # 필요시 시장 데이터 수집
                            signals = await strategy.analyze(market_data)
                            if signals and self.position_manager:
                                await self.position_manager.process_signals(signals)
                    except Exception as e:
                        logger.error(f"{strategy.name if hasattr(strategy, 'name') else 'Unknown'} 전략 실행 실패: {e}")
                
                # 대기 시간 계산 (15분 캔들 주기에 맞춤)
                current_time = datetime.now()
                current_minute = current_time.minute
                current_second = current_time.second
                
                # 다음 15분 캔들까지 남은 시간 계산
                minutes_to_next = 15 - (current_minute % 15)
                seconds_to_next = minutes_to_next * 60 - current_second
                
                # 너무 짧으면 최소 5초 대기
                wait_time = max(5, seconds_to_next)
                
                # 다음 체크 시간 로그 (분 단위로만)
                if current_second == 0:  # 매분 정각에만 로그
                    logger.debug(f"다음 캔들 체크까지 {int(wait_time/60)}분 {int(wait_time%60)}초")
                    
                await asyncio.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"전략 실행 중 오류: {e}")
                await asyncio.sleep(10)
    
    async def monitor_positions(self):
        """포지션 모니터링"""
        if hasattr(self.position_manager, 'start_monitoring'):
            await self.position_manager.start_monitoring()
        else:
            # 기본 모니터링 루프
            logger.info("기본 포지션 모니터링 시작")
            while self.running:
                try:
                    # 포지션 동기화
                    if hasattr(self.position_manager, 'sync_positions'):
                        await self.position_manager.sync_positions()
                    # config에서 동기화 간격 읽기
                    sync_interval = self.position_manager.config.get('auto_sync_interval', 60)
                    logger.debug(f"다음 동기화까지 {sync_interval}초 대기")
                    await asyncio.sleep(sync_interval)
                except Exception as e:
                    logger.error(f"포지션 모니터링 오류: {e}")
                    await asyncio.sleep(60)
    
    async def run(self):
        """메인 실행 루프"""
        try:
            # 초기화
            if not await self.initialize():
                logger.error("초기화 실패로 시스템 종료")
                return
            
            self.running = True
            self.loop = asyncio.get_event_loop()
            
            # 대시보드 시작
            await self.start_dashboard()
            
            # 비동기 태스크 생성
            tasks = [
                asyncio.create_task(self.run_strategies()),
                asyncio.create_task(self.monitor_positions()),
            ]
            
            # 멀티계좌 전략 실행 (해당하는 경우)
            if self.multi_strategy_executor:
                await self.multi_strategy_executor.start_execution()
                logger.info("✓ 멀티계좌 전략 실행 시작")
            
            # 스마트 재개 매니저 시작
            if self.resume_manager:
                tasks.append(asyncio.create_task(self.resume_manager.start_monitoring()))
            
            # 빠른 포지션 모니터 시작
            if self.fast_monitor:
                await self.fast_monitor.start()
                logger.info("✓ 빠른 포지션 모니터링 시작 (10초 간격)")
            
            # 헬스 체커 시작 (선택적)
            if self.config.get('monitoring', {}).get('health_check', {}).get('enabled', False):
                from src.monitoring.health_checker import SystemHealthChecker
                self.health_checker = SystemHealthChecker({
                    'exchange': self.exchange,
                    'position_manager': self.position_manager
                })
                tasks.append(asyncio.create_task(self.health_checker.start_monitoring()))
                logger.info("✓ 시스템 헬스 체커 시작")
            
            # 포지션 동기화 모니터 시작
            if self.sync_monitor:
                await self.sync_monitor.start()
                logger.info("✓ 포지션 동기화 모니터 시작")
            
            # 텔레그램 명령어 핸들러 폴링 추가
            if self.telegram_handler:
                tasks.append(asyncio.create_task(self.telegram_handler.run_polling()))
                logger.info("✓ 텔레그램 명령어 폴링 시작")
            
            self.tasks = tasks
            
            # 태스크 실행
            await asyncio.gather(*tasks)
            
        except asyncio.CancelledError:
            logger.info("시스템 종료 신호 받음")
        except Exception as e:
            logger.error(f"시스템 실행 중 오류: {e}")
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """시스템 종료"""
        logger.info("시스템 종료 시작...")
        self.running = False
        
        # 실시간 모니터링 중지
        for strategy in self.strategies:
            if hasattr(strategy, 'price_monitor') and strategy.price_monitor:
                await strategy.price_monitor.stop()
        
        # 모든 태스크 취소
        for task in self.tasks:
            if not task.done():
                task.cancel()
        
        # 태스크 완료 대기
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        # 전략 종료
        await self.strategy_factory.stop_all_strategies()
        
        # 컴포넌트 종료
        if self.multi_strategy_executor:
            await self.multi_strategy_executor.stop_execution()
            
        if self.multi_account_manager:
            await self.multi_account_manager.cleanup()
            
        if self.sync_monitor:
            await self.sync_monitor.stop()
            
        if self.fast_monitor:
            await self.fast_monitor.stop()
            
        if self.resume_manager:
            await self.resume_manager.stop_monitoring()
        
        if self.position_manager:
            if hasattr(self.position_manager, 'close_all_positions'):
                await self.position_manager.close_all_positions("시스템 종료")
            if hasattr(self.position_manager, 'stop_monitoring'):
                self.position_manager.stop_monitoring()
        
        if self.notification_manager:
            await self.notification_manager.send_alert(
                event_type="SYSTEM_STOPPED",
                title="🛑 Albra Trading System 종료",
                message="모든 포지션이 정리되었습니다."
            )
            await self.notification_manager.stop()
        
        if self.performance_tracker:
            await self.performance_tracker.stop_auto_save()
            await self.performance_tracker.save_history()
            logger.info("✓ Performance Tracker 저장 완료")
        
        if self.exchange:
            await self.exchange.cleanup()
        
        # 상태 저장
        if self.state_manager:
            await self.state_manager.save_system_state({
                'shutdown_time': datetime.now().isoformat(),
                'graceful_shutdown': True
            })
        
        # Phase 2 컴포넌트 종료
        if self.phase2_integration:
            await self.phase2_integration.shutdown()
        
        # 이벤트 로거 종료
        if self.event_logger:
            await log_event(
                "SYSTEM_SHUTDOWN",
                {"graceful": True, "shutdown_time": datetime.now().isoformat()},
                "INFO"
            )
            await self.event_logger.stop()
        
        logger.info("✓ 시스템 종료 완료")
    
    def handle_signal(self, signum, frame):
        """시그널 핸들러"""
        logger.info(f"종료 시그널 받음: {signum}")
        if self.loop and self.running:
            self.loop.create_task(self.shutdown())
    
    # 추가 메서드들 (telegram_commands.py와의 호환성)
    def stop_bot(self):
        """봇 일시 정지"""
        self.running = False
        logger.info("봇이 일시 정지되었습니다")
    
    def resume_bot(self):
        """봇 재시작"""
        self.running = True
        logger.info("봇이 재시작되었습니다")
    
    @property
    def is_running(self):
        """실행 상태 확인"""
        return self.running
    
    @property
    def binance_api(self):
        """BinanceAPI 인스턴스 반환 (호환성)"""
        return self.exchange
    
    @property
    def strategy(self):
        """첫 번째 전략 반환 (호환성)"""
        return self.strategies[0] if self.strategies else None


def parse_arguments():
    """명령행 인자 파싱"""
    parser = argparse.ArgumentParser(
        description='Albra Trading System - 자동 트레이딩 시스템'
    )
    
    parser.add_argument(
        '--strategies', '-s',
        nargs='+',
        help='실행할 전략 이름 (예: TFPE GRID). 미지정시 모든 활성 전략 실행'
    )
    
    parser.add_argument(
        '--list-strategies', '-l',
        action='store_true',
        help='사용 가능한 전략 목록 표시'
    )
    
    parser.add_argument(
        '--validate', '-v',
        action='store_true',
        help='전략 검증만 수행'
    )
    
    parser.add_argument(
        '--no-realtime', '-nr',
        action='store_true',
        help='실시간 모니터링 비활성화'
    )
    
    return parser.parse_args()


async def list_strategies():
    """사용 가능한 전략 목록 표시"""
    factory = get_strategy_factory()
    
    print("\n=== 사용 가능한 전략 ===\n")
    
    available = factory.get_available_strategies()
    for name in available:
        info = factory.get_strategy_info(name)
        config = factory.config_manager.get_strategy_config(name)
        
        print(f"[{name}]")
        print(f"  상태: {'활성' if config and config.enabled else '비활성'}")
        print(f"  설명: {info.get('description', 'N/A')}")
        if config:
            print(f"  심볼: {', '.join(config.symbols[:3])}{'...' if len(config.symbols) > 3 else ''}")
            print(f"  레버리지: {config.parameters.get('leverage', 'N/A')}")
            print(f"  실시간: {'활성' if config.parameters.get('realtime_enabled', False) else '비활성'}")
        print()


async def validate_strategies(strategy_names: List[str]):
    """전략 검증"""
    factory = get_strategy_factory()
    
    print("\n=== 전략 검증 ===\n")
    
    all_valid = True
    for name in strategy_names:
        result = factory.validate_strategy(name)
        
        print(f"[{name}]")
        print(f"  유효성: {'✓' if result['valid'] else '✗'}")
        
        if result['errors']:
            print("  오류:")
            for error in result['errors']:
                print(f"    - {error}")
            all_valid = False
        
        if result['warnings']:
            print("  경고:")
            for warning in result['warnings']:
                print(f"    - {warning}")
        
        print()
    
    return all_valid


async def main():
    """메인 함수"""
    args = parse_arguments()
    
    # 전략 목록 표시
    if args.list_strategies:
        await list_strategies()
        return
    
    # 전략 검증
    if args.validate:
        strategies = args.strategies or get_strategy_factory().get_available_strategies()
        is_valid = await validate_strategies(strategies)
        sys.exit(0 if is_valid else 1)
    
    # 트레이딩 시스템 실행
    system = TradingSystem(strategy_names=args.strategies)
    
    # 실시간 모니터링 옵션 처리
    if args.no_realtime:
        system.config['strategies']['tfpe']['realtime_enabled'] = False
        logger.info("실시간 모니터링이 명령행 옵션으로 비활성화되었습니다")
    
    # 시그널 핸들러 등록
    signal.signal(signal.SIGINT, system.handle_signal)
    signal.signal(signal.SIGTERM, system.handle_signal)
    
    # shutdown 이벤트 추가 (telegram_commands.py 호환성)
    system._shutdown_event = asyncio.Event()
    
    try:
        await system.run()
    except KeyboardInterrupt:
        logger.info("키보드 인터럽트 감지")
    except Exception as e:
        logger.error(f"시스템 오류: {e}")
    finally:
        if system.running:
            await system.shutdown()


if __name__ == "__main__":
    # Windows 이벤트 루프 정책 설정
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 의존성 확인
    try:
        import websockets
    except ImportError:
        print("ERROR: websockets 라이브러리가 설치되지 않았습니다.")
        print("실행: pip install websockets")
        sys.exit(1)
    
    asyncio.run(main())