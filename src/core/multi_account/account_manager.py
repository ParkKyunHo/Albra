# src/core/multi_account/account_manager.py
"""
Multi-Account Manager for AlbraTrading System
Goldman Sachs 스타일의 Enterprise급 멀티 계좌 관리 시스템
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
import json
import os
from decimal import Decimal, ROUND_DOWN

# 로컬 imports
from src.core.binance_api import BinanceAPI
from src.core.position_manager import PositionManager, Position
from src.core.state_manager import StateManager
from src.utils.logger import setup_logger
from src.utils.config_manager import ConfigManager

logger = setup_logger(__name__)


class AccountType(Enum):
    """계좌 타입 정의"""
    MASTER = "MASTER"  # 마스터 계좌
    SUB_SPOT = "SUB_SPOT"  # 서브 계좌 (현물)
    SUB_FUTURES = "SUB_FUTURES"  # 서브 계좌 (선물)


class AccountStatus(Enum):
    """계좌 상태 정의"""
    ACTIVE = "ACTIVE"  # 활성
    PAUSED = "PAUSED"  # 일시 정지
    DISABLED = "DISABLED"  # 비활성
    ERROR = "ERROR"  # 오류
    INITIALIZING = "INITIALIZING"  # 초기화 중


@dataclass
class AccountPerformance:
    """계좌 성과 추적"""
    account_id: str
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def update_statistics(self) -> None:
        """통계 업데이트"""
        if self.total_trades > 0:
            self.win_rate = (self.winning_trades / self.total_trades) * 100
        
        # 추가 통계 계산 로직...
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 변환"""
        return asdict(self)


@dataclass
class SubAccountInfo:
    """서브 계좌 정보"""
    account_id: str  # 계좌 ID (설정에서 지정)
    email: str  # 서브 계좌 이메일
    account_type: AccountType
    api_key: str
    api_secret: str
    status: AccountStatus = AccountStatus.INITIALIZING
    
    # 거래 설정
    strategy: str = ""
    symbols: List[str] = field(default_factory=list)
    leverage: int = 10
    position_size: float = 24.0  # %
    max_positions: int = 3
    
    # 리스크 관리
    daily_loss_limit: float = 5.0  # %
    max_drawdown: float = 20.0  # %
    
    # 성과 추적
    performance: AccountPerformance = field(default_factory=lambda: AccountPerformance(""))
    
    # 시스템 정보
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_sync: Optional[str] = None
    error_count: int = 0
    last_error: Optional[str] = None
    
    def __post_init__(self):
        """초기화 후 처리"""
        if not self.performance.account_id:
            self.performance.account_id = self.account_id
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 변환"""
        data = asdict(self)
        # Enum 값 변환
        data['account_type'] = self.account_type.value
        data['status'] = self.status.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SubAccountInfo':
        """딕셔너리에서 생성"""
        # Enum 복원
        if 'account_type' in data:
            data['account_type'] = AccountType(data['account_type'])
        if 'status' in data:
            data['status'] = AccountStatus(data['status'])
        
        # Performance 복원
        if 'performance' in data and isinstance(data['performance'], dict):
            data['performance'] = AccountPerformance(**data['performance'])
        
        return cls(**data)


class MultiAccountManager:
    """
    멀티 계좌 관리자
    Goldman Sachs 스타일의 엔터프라이즈급 구현
    """
    
    def __init__(self, config_manager: ConfigManager, state_manager: StateManager,
                 notification_manager=None):
        """
        Args:
            config_manager: 설정 관리자
            state_manager: 상태 관리자
            notification_manager: 알림 관리자 (선택)
        """
        self.config_manager = config_manager
        self.state_manager = state_manager
        self.notification_manager = notification_manager
        
        # 계좌 저장소
        self.accounts: Dict[str, SubAccountInfo] = {}
        self.master_account: Optional[SubAccountInfo] = None
        
        # API 클라이언트 풀
        self.api_clients: Dict[str, BinanceAPI] = {}
        
        # 포지션 매니저 풀
        self.position_managers: Dict[str, PositionManager] = {}
        
        # 동기화 락
        self._lock = asyncio.Lock()
        self._initialized = False
        
        # 설정 로드
        self.config = config_manager.config.get('multi_account', {})
        self.enabled = self.config.get('enabled', False)
        
        # 통계
        self.stats = {
            'total_accounts': 0,
            'active_accounts': 0,
            'total_positions': 0,
            'total_pnl': 0.0,
            'last_sync': None,
            'errors': 0
        }
        
        logger.info(f"MultiAccountManager 초기화 (활성화: {self.enabled})")
    
    async def initialize(self) -> bool:
        """멀티 계좌 시스템 초기화"""
        try:
            if not self.enabled:
                logger.info("멀티 계좌 시스템이 비활성화되어 있습니다")
                return True
            
            logger.info("=" * 60)
            logger.info("멀티 계좌 시스템 초기화 시작")
            logger.info("=" * 60)
            
            # 1. 마스터 계좌 초기화
            if not await self._initialize_master_account():
                logger.error("마스터 계좌 초기화 실패")
                return False
            
            # 2. 서브 계좌 로드 및 초기화
            await self._load_sub_accounts()
            
            # 3. 각 계좌별 API 클라이언트 생성
            await self._initialize_api_clients()
            
            # 4. 각 계좌별 포지션 매니저 생성
            await self._initialize_position_managers()
            
            # 5. 초기 동기화
            await self.sync_all_accounts()
            
            # 6. 상태 저장
            await self._save_state()
            
            self._initialized = True
            
            logger.info(f"✅ 멀티 계좌 시스템 초기화 완료")
            logger.info(f"   - 마스터 계좌: 1개")
            logger.info(f"   - 서브 계좌: {len(self.accounts)}개")
            logger.info(f"   - 활성 계좌: {self.stats['active_accounts']}개")
            
            # 초기화 알림
            if self.notification_manager:
                await self.notification_manager.send_alert(
                    event_type="SYSTEM_INITIALIZED",
                    title="🚀 멀티 계좌 시스템 시작",
                    message=(
                        f"<b>마스터 계좌:</b> ✅\n"
                        f"<b>서브 계좌:</b> {len(self.accounts)}개\n"
                        f"<b>활성 계좌:</b> {self.stats['active_accounts']}개"
                    )
                )
            
            return True
            
        except Exception as e:
            logger.error(f"멀티 계좌 시스템 초기화 실패: {e}")
            self.stats['errors'] += 1
            return False
    
    async def _initialize_master_account(self) -> bool:
        """마스터 계좌 초기화"""
        try:
            # 환경변수에서 마스터 계좌 정보 로드
            api_key = os.getenv('BINANCE_API_KEY')
            api_secret = os.getenv('BINANCE_SECRET_KEY')
            
            if not api_key or not api_secret:
                logger.error("마스터 계좌 API 키가 설정되지 않았습니다")
                return False
            
            # 마스터 계좌 정보 생성
            self.master_account = SubAccountInfo(
                account_id="MASTER",
                email="master@albratrading.com",
                account_type=AccountType.MASTER,
                api_key=api_key,
                api_secret=api_secret,
                status=AccountStatus.ACTIVE,
                strategy="MIXED",  # 마스터는 여러 전략 실행 가능
                symbols=[],  # 모든 심볼
                leverage=10,
                position_size=24.0,
                max_positions=10  # 마스터는 더 많은 포지션 허용
            )
            
            logger.info("✓ 마스터 계좌 정보 생성")
            return True
            
        except Exception as e:
            logger.error(f"마스터 계좌 초기화 실패: {e}")
            return False
    
    async def _load_sub_accounts(self) -> None:
        """서브 계좌 로드"""
        try:
            sub_accounts_config = self.config.get('sub_accounts', {})
            
            for account_id, account_config in sub_accounts_config.items():
                if not account_config.get('enabled', True):
                    logger.info(f"서브 계좌 {account_id} 비활성화됨")
                    continue
                
                # API 키 로드 (환경변수에서)
                api_key = os.getenv(f'{account_id.upper()}_API_KEY')
                api_secret = os.getenv(f'{account_id.upper()}_API_SECRET')
                
                if not api_key or not api_secret:
                    logger.warning(f"서브 계좌 {account_id} API 키 없음 - 건너뜀")
                    continue
                
                # 서브 계좌 정보 생성
                sub_account = SubAccountInfo(
                    account_id=account_id,
                    email=f"{account_id}@albratrading.com",
                    account_type=AccountType(account_config.get('type', 'SUB_FUTURES')),
                    api_key=api_key,
                    api_secret=api_secret,
                    strategy=account_config.get('strategy', 'TFPE'),
                    symbols=account_config.get('symbols', ['BTCUSDT']),
                    leverage=account_config.get('leverage', 10),
                    position_size=account_config.get('position_size', 24.0),
                    max_positions=account_config.get('max_positions', 3),
                    daily_loss_limit=account_config.get('daily_loss_limit', 5.0),
                    max_drawdown=account_config.get('max_drawdown', 20.0)
                )
                
                self.accounts[account_id] = sub_account
                logger.info(f"✓ 서브 계좌 로드: {account_id} ({sub_account.strategy})")
            
            self.stats['total_accounts'] = len(self.accounts) + 1  # +1 for master
            
        except Exception as e:
            logger.error(f"서브 계좌 로드 실패: {e}")
    
    async def _initialize_api_clients(self) -> None:
        """API 클라이언트 초기화"""
        try:
            # 마스터 계좌 API 클라이언트
            if self.master_account:
                master_api = BinanceAPI(
                    api_key=self.master_account.api_key,
                    secret_key=self.master_account.api_secret,
                    testnet=self.config_manager.config.get('system', {}).get('mode') == 'testnet'
                )
                
                if await master_api.initialize():
                    self.api_clients['MASTER'] = master_api
                    self.stats['active_accounts'] += 1  # 마스터 계좌도 활성 계좌에 포함
                    logger.info("✓ 마스터 계좌 API 연결")
                else:
                    logger.error("마스터 계좌 API 연결 실패")
            
            # 서브 계좌 API 클라이언트
            for account_id, account in self.accounts.items():
                try:
                    api_client = BinanceAPI(
                        api_key=account.api_key,
                        secret_key=account.api_secret,
                        testnet=self.config_manager.config.get('system', {}).get('mode') == 'testnet'
                    )
                    
                    if await api_client.initialize():
                        self.api_clients[account_id] = api_client
                        account.status = AccountStatus.ACTIVE
                        self.stats['active_accounts'] += 1
                        logger.info(f"✓ {account_id} API 연결 성공")
                    else:
                        account.status = AccountStatus.ERROR
                        account.error_count += 1
                        logger.error(f"{account_id} API 연결 실패")
                        
                except Exception as e:
                    logger.error(f"{account_id} API 초기화 중 오류: {e}")
                    account.status = AccountStatus.ERROR
                    account.last_error = str(e)
                    
        except Exception as e:
            logger.error(f"API 클라이언트 초기화 실패: {e}")
    
    async def _initialize_position_managers(self) -> None:
        """포지션 매니저 초기화"""
        try:
            # 각 계좌별 독립적인 포지션 매니저 생성
            for account_id, api_client in self.api_clients.items():
                try:
                    # 계좌별 독립적인 상태 관리자
                    account_state_manager = StateManager(state_dir=f"state/{account_id}")
                    
                    # 포지션 매니저 생성
                    position_manager = PositionManager(
                        binance_api=api_client,
                        state_manager=account_state_manager,
                        notification_manager=self.notification_manager,
                        config_manager=self.config_manager
                    )
                    
                    if await position_manager.initialize():
                        self.position_managers[account_id] = position_manager
                        logger.info(f"✓ {account_id} 포지션 매니저 초기화")
                    else:
                        logger.error(f"{account_id} 포지션 매니저 초기화 실패")
                        
                except Exception as e:
                    logger.error(f"{account_id} 포지션 매니저 생성 중 오류: {e}")
                    
        except Exception as e:
            logger.error(f"포지션 매니저 초기화 실패: {e}")
    
    async def sync_all_accounts(self) -> Dict[str, Any]:
        """모든 계좌 동기화"""
        async with self._lock:
            sync_report = {
                'timestamp': datetime.now().isoformat(),
                'accounts': {},
                'total_positions': 0,
                'total_balance': 0.0,
                'errors': []
            }
            
            try:
                # 각 계좌별 동기화
                for account_id in list(self.api_clients.keys()):
                    account_sync = await self._sync_single_account(account_id)
                    sync_report['accounts'][account_id] = account_sync
                    
                    if 'error' not in account_sync:
                        sync_report['total_positions'] += account_sync.get('position_count', 0)
                        sync_report['total_balance'] += account_sync.get('balance', 0)
                
                # 통계 업데이트
                self.stats['total_positions'] = sync_report['total_positions']
                self.stats['last_sync'] = sync_report['timestamp']
                
                # 상태 저장
                await self._save_state()
                
                logger.info(f"전체 계좌 동기화 완료: "
                          f"포지션={sync_report['total_positions']}, "
                          f"잔고=${sync_report['total_balance']:.2f}")
                
                return sync_report
                
            except Exception as e:
                logger.error(f"전체 계좌 동기화 실패: {e}")
                sync_report['errors'].append(str(e))
                return sync_report
    
    async def _sync_single_account(self, account_id: str) -> Dict[str, Any]:
        """단일 계좌 동기화"""
        try:
            api_client = self.api_clients.get(account_id)
            position_manager = self.position_managers.get(account_id)
            
            if not api_client or not position_manager:
                return {'error': 'API 클라이언트 또는 포지션 매니저 없음'}
            
            # 잔고 조회
            balance = await api_client.get_account_balance()
            
            # 포지션 동기화
            sync_result = await position_manager.sync_positions()
            
            # 계좌 정보 업데이트
            if account_id != 'MASTER':
                account = self.accounts[account_id]
                account.last_sync = datetime.now().isoformat()
                
                # 성과 업데이트
                positions = position_manager.get_active_positions()
                account.performance.total_trades = position_manager.stats.get('total_positions_created', 0)
            
            return {
                'balance': balance,
                'position_count': len(sync_result.get('active', [])),
                'sync_result': sync_result,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"{account_id} 동기화 실패: {e}")
            return {'error': str(e)}
    
    async def execute_order(self, account_id: str, symbol: str, side: str, 
                          quantity: float, order_type: str = 'MARKET') -> Optional[Dict]:
        """특정 계좌에서 주문 실행"""
        try:
            api_client = self.api_clients.get(account_id)
            if not api_client:
                logger.error(f"API 클라이언트 없음: {account_id}")
                return None
            
            # 주문 실행
            result = await api_client.place_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type
            )
            
            if result:
                logger.info(f"[{account_id}] 주문 성공: {symbol} {side} {quantity}")
                
                # 포지션 매니저 업데이트
                position_manager = self.position_managers.get(account_id)
                if position_manager:
                    await position_manager.sync_positions()
            
            return result
            
        except Exception as e:
            logger.error(f"[{account_id}] 주문 실행 실패: {e}")
            return None
    
    async def get_account_summary(self, account_id: str) -> Dict[str, Any]:
        """계좌 요약 정보 조회"""
        try:
            if account_id == 'MASTER':
                account_info = self.master_account
            else:
                account_info = self.accounts.get(account_id)
            
            if not account_info:
                return {'error': '계좌 정보 없음'}
            
            api_client = self.api_clients.get(account_id)
            position_manager = self.position_managers.get(account_id)
            
            summary = {
                'account_id': account_id,
                'status': account_info.status.value,
                'strategy': account_info.strategy,
                'balance': 0.0,
                'positions': [],
                'performance': account_info.performance.to_dict() if hasattr(account_info, 'performance') else {}
            }
            
            if api_client:
                summary['balance'] = await api_client.get_account_balance()
            
            if position_manager:
                positions = position_manager.get_active_positions()
                summary['positions'] = [p.to_dict() for p in positions]
            
            return summary
            
        except Exception as e:
            logger.error(f"계좌 요약 조회 실패 ({account_id}): {e}")
            return {'error': str(e)}
    
    async def rebalance_accounts(self) -> Dict[str, Any]:
        """계좌 간 자금 재배분"""
        # TODO: 구현 예정
        logger.info("계좌 재배분 기능은 Phase 2에서 구현 예정입니다")
        return {'status': 'not_implemented'}
    
    async def _save_state(self) -> None:
        """상태 저장"""
        try:
            state_data = {
                'master_account': self.master_account.to_dict() if self.master_account else None,
                'sub_accounts': {
                    account_id: account.to_dict() 
                    for account_id, account in self.accounts.items()
                },
                'stats': self.stats,
                'last_saved': datetime.now().isoformat()
            }
            
            await self.state_manager.save_multi_account_state(state_data)
            
        except Exception as e:
            logger.error(f"멀티 계좌 상태 저장 실패: {e}")
    
    async def cleanup(self) -> None:
        """리소스 정리"""
        try:
            logger.info("멀티 계좌 시스템 종료 중...")
            
            # 모든 API 클라이언트 정리
            for account_id, api_client in self.api_clients.items():
                await api_client.cleanup()
                logger.info(f"✓ {account_id} API 연결 종료")
            
            # 상태 저장
            await self._save_state()
            
            logger.info("✓ 멀티 계좌 시스템 종료 완료")
            
        except Exception as e:
            logger.error(f"멀티 계좌 시스템 종료 중 오류: {e}")
    
    def get_system_stats(self) -> Dict[str, Any]:
        """시스템 통계 반환"""
        return {
            'enabled': self.enabled,
            'initialized': self._initialized,
            'accounts': {
                'total': self.stats['total_accounts'],
                'active': self.stats['active_accounts'],
                'master': 1 if self.master_account else 0,
                'sub': len(self.accounts)
            },
            'positions': self.stats['total_positions'],
            'last_sync': self.stats['last_sync'],
            'errors': self.stats['errors']
        }
    
    def is_multi_account_enabled(self) -> bool:
        """멀티 계좌 모드 활성화 여부"""
        return self.enabled and self._initialized
