# src/core/multi_account/compatibility.py
"""
Multi-Account Compatibility Layer
기존 단일 계좌 시스템과의 호환성을 위한 어댑터 패턴 구현
"""

import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
import asyncio

from src.core.binance_api import BinanceAPI
from src.core.position_manager import PositionManager, Position
from src.core.multi_account.account_manager import MultiAccountManager
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class UnifiedPositionManager:
    """
    통합 포지션 매니저
    단일/멀티 계좌 모드를 투명하게 처리하는 래퍼
    """
    
    def __init__(self, multi_account_manager: Optional[MultiAccountManager] = None,
                 single_position_manager: Optional[PositionManager] = None):
        """
        Args:
            multi_account_manager: 멀티 계좌 매니저 (멀티 모드)
            single_position_manager: 단일 포지션 매니저 (단일 모드)
        """
        self.multi_manager = multi_account_manager
        self.single_manager = single_position_manager
        
        # 현재 모드
        self.is_multi_mode = bool(multi_account_manager and multi_account_manager.is_multi_account_enabled())
        
        logger.info(f"UnifiedPositionManager 초기화 (모드: {'멀티' if self.is_multi_mode else '단일'})")
    
    async def sync_positions(self) -> Dict[str, Any]:
        """포지션 동기화 - 모드에 따라 적절히 처리"""
        if self.is_multi_mode:
            # 멀티 모드: 모든 계좌 동기화
            return await self.multi_manager.sync_all_accounts()
        else:
            # 단일 모드: 기존 방식
            return await self.single_manager.sync_positions()
    
    def get_all_positions(self) -> Dict[str, Position]:
        """모든 포지션 조회"""
        if self.is_multi_mode:
            # 멀티 모드: 모든 계좌의 포지션 병합
            all_positions = {}
            
            for account_id, position_manager in self.multi_manager.position_managers.items():
                account_positions = position_manager.get_all_positions()
                
                # 계좌 ID를 포함한 키로 저장
                for symbol, position in account_positions.items():
                    key = f"{account_id}:{symbol}"
                    all_positions[key] = position
            
            return all_positions
        else:
            # 단일 모드
            return self.single_manager.get_all_positions()
    
    def get_active_positions(self, account_id: Optional[str] = None, include_manual: bool = True) -> List[Position]:
        """활성 포지션 조회"""
        if self.is_multi_mode:
            if account_id:
                # 특정 계좌의 포지션
                position_manager = self.multi_manager.position_managers.get(account_id)
                return position_manager.get_active_positions(include_manual=include_manual) if position_manager else []
            else:
                # 모든 계좌의 포지션
                all_positions = []
                for pm in self.multi_manager.position_managers.values():
                    all_positions.extend(pm.get_active_positions(include_manual=include_manual))
                return all_positions
        else:
            # 단일 모드
            return self.single_manager.get_active_positions(include_manual=include_manual)
    
    async def add_position(self, symbol: str, side: str, size: float, 
                          entry_price: float, leverage: int, strategy_name: str,
                          account_id: Optional[str] = None, **kwargs) -> Position:
        """포지션 추가"""
        if self.is_multi_mode:
            # 멀티 모드: 계좌 ID가 필요
            if not account_id:
                # 전략에 따라 적절한 계좌 선택
                account_id = self._select_account_for_strategy(strategy_name)
            
            position_manager = self.multi_manager.position_managers.get(account_id)
            if not position_manager:
                raise ValueError(f"포지션 매니저를 찾을 수 없습니다: {account_id}")
            
            return await position_manager.add_position(
                symbol, side, size, entry_price, leverage, strategy_name, **kwargs
            )
        else:
            # 단일 모드
            return await self.single_manager.add_position(
                symbol, side, size, entry_price, leverage, strategy_name, **kwargs
            )
    
    async def remove_position(self, symbol: str, reason: str = "unknown", 
                            exit_price: float = None, account_id: Optional[str] = None) -> bool:
        """포지션 제거"""
        if self.is_multi_mode:
            if not account_id:
                # 모든 계좌에서 해당 심볼 검색
                for acc_id, pm in self.multi_manager.position_managers.items():
                    if pm.is_position_exist(symbol):
                        account_id = acc_id
                        break
            
            if not account_id:
                logger.warning(f"포지션을 찾을 수 없습니다: {symbol}")
                return False
            
            position_manager = self.multi_manager.position_managers.get(account_id)
            return await position_manager.remove_position(symbol, reason, exit_price)
        else:
            # 단일 모드
            return await self.single_manager.remove_position(symbol, reason, exit_price)
    
    def _select_account_for_strategy(self, strategy_name: str) -> str:
        """전략에 적합한 계좌 선택"""
        # 전략별 계좌 매핑 확인
        for account_id, account in self.multi_manager.accounts.items():
            if account.strategy == strategy_name:
                return account_id
        
        # 기본값: 마스터 계좌
        return 'MASTER'
    
    @property
    def positions(self) -> Dict[str, Position]:
        """positions 속성 - 하위 호환성을 위해"""
        if self.is_multi_mode:
            # 멀티 모드에서는 모든 포지션을 병합하여 반환
            all_positions = {}
            for account_id, pm in self.multi_manager.position_managers.items():
                for symbol, position in pm.positions.items():
                    # 복합 키 사용
                    key = f"{account_id}:{symbol}"
                    all_positions[key] = position
            return all_positions
        else:
            # 단일 모드
            return self.single_manager.positions
    
    def get_position_summary(self) -> Dict[str, Any]:
        """포지션 요약 정보"""
        if self.is_multi_mode:
            summary = {
                'total_positions': 0,
                'by_account': {},
                'by_strategy': {},
                'total_value': 0.0
            }
            
            for account_id, pm in self.multi_manager.position_managers.items():
                account_summary = pm.get_position_summary()
                summary['by_account'][account_id] = account_summary
                summary['total_positions'] += account_summary['total_positions']
                
                # 전략별 집계
                for strategy in account_summary.get('strategies', []):
                    if strategy not in summary['by_strategy']:
                        summary['by_strategy'][strategy] = 0
                    summary['by_strategy'][strategy] += 1
            
            return summary
        else:
            # 단일 모드
            return self.single_manager.get_position_summary()
    
    def get_position(self, symbol: str, strategy_name: str = None, account_id: Optional[str] = None) -> Optional[Position]:
        """특정 포지션 조회"""
        if self.is_multi_mode:
            if account_id:
                # 특정 계좌에서 조회
                position_manager = self.multi_manager.position_managers.get(account_id)
                if position_manager and hasattr(position_manager, 'get_position'):
                    return position_manager.get_position(symbol, strategy_name)
            else:
                # 모든 계좌에서 검색
                for pm in self.multi_manager.position_managers.values():
                    if hasattr(pm, 'get_position'):
                        position = pm.get_position(symbol, strategy_name)
                        if position:
                            return position
            return None
        else:
            # 단일 모드
            if hasattr(self.single_manager, 'get_position'):
                return self.single_manager.get_position(symbol, strategy_name)
            # 구버전 호환성을 위한 폴백
            return self.single_manager.positions.get(symbol)


class UnifiedBinanceAPI:
    """
    통합 바이낸스 API
    멀티 계좌 모드에서 적절한 계좌의 API를 라우팅
    """
    
    def __init__(self, multi_account_manager: Optional[MultiAccountManager] = None,
                 single_api: Optional[BinanceAPI] = None):
        """
        Args:
            multi_account_manager: 멀티 계좌 매니저
            single_api: 단일 API 클라이언트
        """
        self.multi_manager = multi_account_manager
        self.single_api = single_api
        
        self.is_multi_mode = bool(multi_account_manager and multi_account_manager.is_multi_account_enabled())
    
    async def place_order(self, symbol: str, side: str, quantity: float, 
                         order_type: str = 'MARKET', price: float = None,
                         reduce_only: bool = False, account_id: Optional[str] = None) -> Optional[Dict]:
        """주문 실행"""
        if self.is_multi_mode:
            if not account_id:
                # 심볼을 기반으로 적절한 계좌 선택
                account_id = self._select_account_for_symbol(symbol)
            
            return await self.multi_manager.execute_order(
                account_id, symbol, side, quantity, order_type
            )
        else:
            # 단일 모드
            return await self.single_api.place_order(
                symbol, side, quantity, order_type, price, reduce_only
            )
    
    async def get_current_price(self, symbol: str) -> Optional[float]:
        """현재 가격 조회"""
        if self.is_multi_mode:
            # 마스터 계좌 API 사용 (가격 조회는 어느 계좌든 동일)
            api_client = self.multi_manager.api_clients.get('MASTER')
            return await api_client.get_current_price(symbol) if api_client else None
        else:
            return await self.single_api.get_current_price(symbol)
    
    async def get_account_balance(self, account_id: Optional[str] = None) -> float:
        """계좌 잔고 조회"""
        if self.is_multi_mode:
            if account_id:
                # 특정 계좌 잔고
                api_client = self.multi_manager.api_clients.get(account_id)
                return await api_client.get_account_balance() if api_client else 0.0
            else:
                # 전체 계좌 잔고 합계
                total_balance = 0.0
                for api_client in self.multi_manager.api_clients.values():
                    balance = await api_client.get_account_balance()
                    total_balance += balance
                return total_balance
        else:
            return await self.single_api.get_account_balance()
    
    def _select_account_for_symbol(self, symbol: str) -> str:
        """심볼에 적합한 계좌 선택"""
        # 각 계좌의 심볼 목록 확인
        for account_id, account in self.multi_manager.accounts.items():
            if symbol in account.symbols:
                return account_id
        
        # 기본값: 마스터 계좌
        return 'MASTER'
    
    @property
    def is_multi_account(self) -> bool:
        """멀티 계좌 모드 여부 - 대시보드 호환성을 위해"""
        return self.is_multi_mode
    
    @property
    def account_apis(self) -> Dict[str, BinanceAPI]:
        """계좌별 API 클라이언트 - 대시보드 호환성을 위해"""
        if self.is_multi_mode and self.multi_manager:
            return self.multi_manager.api_clients
        else:
            # 단일 모드에서는 빈 딕셔너리 반환
            return {}
    
    async def get_server_time(self) -> Optional[int]:
        """서버 시간 조회"""
        if self.is_multi_mode:
            # 마스터 계좌 API 사용
            api_client = self.multi_manager.api_clients.get('MASTER')
            return await api_client.get_server_time() if api_client else None
        else:
            return await self.single_api.get_server_time()
    
    async def get_klines(self, symbol: str, interval: str, limit: int = 500) -> Optional[List]:
        """캔들 데이터 조회"""
        if self.is_multi_mode:
            # 마스터 계좌 API 사용 (시장 데이터는 모든 계좌 동일)
            api_client = self.multi_manager.api_clients.get('MASTER')
            return await api_client.get_klines(symbol, interval, limit) if api_client else None
        else:
            return await self.single_api.get_klines(symbol, interval, limit)
    
    async def get_positions(self) -> Optional[List[Dict]]:
        """거래소 포지션 조회"""
        if self.is_multi_mode:
            # 모든 계좌의 포지션 병합
            all_positions = []
            for api_client in self.multi_manager.api_clients.values():
                positions = await api_client.get_positions()
                if positions:
                    all_positions.extend(positions)
            return all_positions
        else:
            return await self.single_api.get_positions()
    
    async def get_account_info(self) -> Optional[Dict]:
        """계정 정보 조회 - telegram_commands 호환성"""
        if self.is_multi_mode:
            # 멀티 모드에서는 마스터 계좌 정보를 기본으로 반환
            # 필요시 모든 계좌 정보를 병합할 수 있음
            api_client = self.multi_manager.api_clients.get('MASTER')
            if api_client:
                master_info = await api_client.get_account_info()
                
                # 서브 계좌들의 잔고를 합산 (옵션)
                if master_info:
                    total_balance = float(master_info.get('totalWalletBalance', 0))
                    total_unrealized = float(master_info.get('totalUnrealizedProfit', 0))
                    
                    # 서브 계좌 정보 추가
                    for account_id, sub_api in self.multi_manager.api_clients.items():
                        if account_id != 'MASTER':
                            sub_info = await sub_api.get_account_info()
                            if sub_info:
                                total_balance += float(sub_info.get('totalWalletBalance', 0))
                                total_unrealized += float(sub_info.get('totalUnrealizedProfit', 0))
                    
                    # 병합된 정보 반환
                    master_info['totalWalletBalance'] = str(total_balance)
                    master_info['totalUnrealizedProfit'] = str(total_unrealized)
                    master_info['totalMarginBalance'] = str(total_balance + total_unrealized)
                    
                return master_info
            return None
        else:
            # 단일 모드
            return await self.single_api.get_account_info()


class ModeSelector:
    """
    모드 선택기
    런타임에 단일/멀티 모드를 전환
    """
    
    def __init__(self):
        self.current_mode = 'single'  # 기본값
        self._callbacks = []
    
    def set_mode(self, mode: str) -> None:
        """모드 설정"""
        if mode not in ['single', 'multi']:
            raise ValueError(f"잘못된 모드: {mode}")
        
        old_mode = self.current_mode
        self.current_mode = mode
        
        # 모드 변경 콜백 실행
        for callback in self._callbacks:
            callback(old_mode, mode)
        
        logger.info(f"거래 모드 변경: {old_mode} → {mode}")
    
    def register_callback(self, callback) -> None:
        """모드 변경 콜백 등록"""
        self._callbacks.append(callback)
    
    def is_multi_mode(self) -> bool:
        """멀티 모드 여부"""
        return self.current_mode == 'multi'


# 글로벌 모드 선택기
mode_selector = ModeSelector()


def create_unified_managers(config_manager, state_manager, notification_manager=None) -> Dict[str, Any]:
    """
    통합 매니저 생성 헬퍼 함수
    
    Returns:
        통합 매니저 딕셔너리
    """
    managers = {}
    
    # 멀티 계좌 매니저 생성 (설정에 따라)
    multi_config = config_manager.config.get('multi_account', {})
    if multi_config.get('enabled', False):
        multi_manager = MultiAccountManager(
            config_manager=config_manager,
            state_manager=state_manager,
            notification_manager=notification_manager
        )
        managers['multi_account_manager'] = multi_manager
    
    return managers
