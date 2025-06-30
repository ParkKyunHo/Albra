# src/core/multi_account/strategy_allocator.py
"""
Multi-Account Strategy Allocator
전략-계좌 할당을 관리하는 엔터프라이즈급 시스템

Goldman Sachs 스타일의 포트폴리오 전략 관리:
- 계좌별 독립적인 전략 운영
- 심볼 충돌 방지 메커니즘
- 동적 전략 전환 지원
- 전략 성과 추적 및 최적화
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Set, Any, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
import json
from collections import defaultdict
import uuid

from src.utils.logger import setup_logger
from src.core.multi_account.account_manager import AccountStatus, SubAccountInfo

logger = setup_logger(__name__)


class AllocationStatus(Enum):
    """할당 상태"""
    ACTIVE = "ACTIVE"           # 활성
    PENDING = "PENDING"         # 대기 중
    TRANSITIONING = "TRANSITIONING"  # 전환 중
    PAUSED = "PAUSED"          # 일시 정지
    STOPPED = "STOPPED"        # 중지됨
    ERROR = "ERROR"            # 오류


class ConflictType(Enum):
    """충돌 유형"""
    SYMBOL_OVERLAP = "SYMBOL_OVERLAP"      # 심볼 중복
    STRATEGY_INCOMPATIBLE = "STRATEGY_INCOMPATIBLE"  # 전략 비호환
    RESOURCE_LIMIT = "RESOURCE_LIMIT"      # 리소스 한계
    RISK_LIMIT = "RISK_LIMIT"             # 리스크 한도


@dataclass
class StrategyAllocation:
    """전략 할당 정보"""
    allocation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    account_id: str = ""
    strategy_name: str = ""
    symbols: List[str] = field(default_factory=list)
    status: AllocationStatus = AllocationStatus.PENDING
    
    # 할당 파라미터
    position_size: float = 24.0  # %
    max_positions: int = 3
    leverage: int = 10
    
    # 리스크 파라미터
    daily_loss_limit: float = 5.0  # %
    max_drawdown: float = 20.0  # %
    
    # 성과 추적
    total_trades: int = 0
    winning_trades: int = 0
    total_pnl: float = 0.0
    sharpe_ratio: float = 0.0
    
    # 메타데이터
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    activated_at: Optional[str] = None
    last_trade_at: Optional[str] = None
    error_count: int = 0
    last_error: Optional[str] = None
    
    # 할당 제약
    constraints: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 변환"""
        data = asdict(self)
        data['status'] = self.status.value
        return data
    
    def is_active(self) -> bool:
        """활성 상태 확인"""
        return self.status == AllocationStatus.ACTIVE


@dataclass
class AllocationConflict:
    """할당 충돌 정보"""
    conflict_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    conflict_type: ConflictType = ConflictType.SYMBOL_OVERLAP
    account_id: str = ""
    symbol: str = ""
    existing_allocation: Optional[str] = None
    new_allocation: Optional[str] = None
    description: str = ""
    severity: str = "MEDIUM"  # LOW, MEDIUM, HIGH, CRITICAL
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    resolved: bool = False
    resolution: Optional[str] = None


class StrategyCompatibilityChecker:
    """전략 호환성 검사기"""
    
    # 전략 간 호환성 매트릭스
    COMPATIBILITY_MATRIX = {
        # 같은 계좌에서 동시 실행 가능한 전략 조합
        "TFPE": ["GRID", "DCA"],  # TFPE는 Grid, DCA와 호환
        "MOMENTUM": [],  # Momentum은 단독 실행 권장
        "GRID": ["TFPE", "DCA"],
        "DCA": ["TFPE", "GRID"],
        "ARBITRAGE": [],  # 차익거래는 단독 실행
    }
    
    # 전략별 리소스 요구사항
    RESOURCE_REQUIREMENTS = {
        "TFPE": {"min_balance": 1000, "api_weight": 10},
        "MOMENTUM": {"min_balance": 2000, "api_weight": 15},
        "GRID": {"min_balance": 500, "api_weight": 20},
        "DCA": {"min_balance": 500, "api_weight": 5},
        "ARBITRAGE": {"min_balance": 5000, "api_weight": 30},
    }
    
    @classmethod
    def check_compatibility(cls, strategy1: str, strategy2: str) -> bool:
        """두 전략의 호환성 검사"""
        compatible_strategies = cls.COMPATIBILITY_MATRIX.get(strategy1, [])
        return strategy2 in compatible_strategies
    
    @classmethod
    def get_resource_requirements(cls, strategy: str) -> Dict[str, Any]:
        """전략의 리소스 요구사항 반환"""
        return cls.RESOURCE_REQUIREMENTS.get(strategy, {})


class StrategyAllocator:
    """
    전략-계좌 할당 관리자
    Jane Street 스타일의 포트폴리오 전략 관리
    """
    
    def __init__(self):
        """초기화"""
        # 할당 저장소
        self.allocations: Dict[str, StrategyAllocation] = {}  # allocation_id -> allocation
        self.account_allocations: Dict[str, List[str]] = defaultdict(list)  # account_id -> [allocation_ids]
        self.symbol_allocations: Dict[str, Dict[str, str]] = defaultdict(dict)  # account_id -> {symbol -> allocation_id}
        
        # 충돌 기록
        self.conflicts: List[AllocationConflict] = []
        self.resolved_conflicts: List[AllocationConflict] = []
        
        # 통계
        self.stats = {
            'total_allocations': 0,
            'active_allocations': 0,
            'total_conflicts': 0,
            'resolved_conflicts': 0,
            'allocation_changes': 0,
            'last_update': None
        }
        
        # 할당 규칙
        self.allocation_rules = {
            'max_strategies_per_account': 3,
            'max_symbols_per_strategy': 10,
            'min_balance_per_strategy': 100,  # USD
            'conflict_resolution_mode': 'PREVENT',  # PREVENT, AUTO_RESOLVE, MANUAL
        }
        
        # 동기화 락
        self._lock = asyncio.Lock()
        
        # 호환성 검사기
        self.compatibility_checker = StrategyCompatibilityChecker()
        
        logger.info("StrategyAllocator 초기화 완료")
    
    async def allocate_strategy(self, account_id: str, strategy_name: str, 
                               symbols: List[str], **kwargs) -> Tuple[bool, Optional[StrategyAllocation], Optional[str]]:
        """
        전략을 특정 계좌에 할당
        
        Args:
            account_id: 계좌 ID
            strategy_name: 전략 이름
            symbols: 거래할 심볼 목록
            **kwargs: 추가 할당 파라미터
            
        Returns:
            (성공 여부, 할당 객체, 오류 메시지)
        """
        async with self._lock:
            try:
                logger.info(f"전략 할당 시작: {account_id} - {strategy_name} - {symbols}")
                
                # 1. 사전 검증
                validation_result = await self._validate_allocation(
                    account_id, strategy_name, symbols
                )
                
                if not validation_result[0]:
                    return False, None, validation_result[1]
                
                # 2. 충돌 검사
                conflicts = await self._check_conflicts(account_id, strategy_name, symbols)
                
                if conflicts:
                    # 충돌 처리
                    resolution = await self._handle_conflicts(conflicts)
                    if not resolution[0]:
                        return False, None, f"충돌 해결 실패: {resolution[1]}"
                
                # 3. 할당 생성
                allocation = StrategyAllocation(
                    account_id=account_id,
                    strategy_name=strategy_name,
                    symbols=symbols,
                    position_size=kwargs.get('position_size', 24.0),
                    max_positions=kwargs.get('max_positions', 3),
                    leverage=kwargs.get('leverage', 10),
                    daily_loss_limit=kwargs.get('daily_loss_limit', 5.0),
                    max_drawdown=kwargs.get('max_drawdown', 20.0),
                    constraints=kwargs.get('constraints', {})
                )
                
                # 4. 할당 등록
                await self._register_allocation(allocation)
                
                # 5. 활성화
                await self._activate_allocation(allocation)
                
                # 통계 업데이트
                self.stats['total_allocations'] += 1
                self.stats['active_allocations'] += 1
                self.stats['allocation_changes'] += 1
                self.stats['last_update'] = datetime.now().isoformat()
                
                logger.info(f"✅ 전략 할당 성공: {allocation.allocation_id}")
                
                return True, allocation, None
                
            except Exception as e:
                logger.error(f"전략 할당 실패: {e}")
                return False, None, str(e)
    
    async def _validate_allocation(self, account_id: str, strategy_name: str, 
                                  symbols: List[str]) -> Tuple[bool, Optional[str]]:
        """할당 유효성 검증"""
        # 1. 계좌당 전략 수 제한
        current_allocations = len(self.account_allocations.get(account_id, []))
        if current_allocations >= self.allocation_rules['max_strategies_per_account']:
            return False, f"계좌당 최대 전략 수 초과 ({self.allocation_rules['max_strategies_per_account']}개)"
        
        # 2. 전략당 심볼 수 제한
        if len(symbols) > self.allocation_rules['max_symbols_per_strategy']:
            return False, f"전략당 최대 심볼 수 초과 ({self.allocation_rules['max_symbols_per_strategy']}개)"
        
        # 3. 심볼 유효성
        if not symbols:
            return False, "심볼 목록이 비어있습니다"
        
        # 4. 전략 이름 유효성
        valid_strategies = ["TFPE", "MOMENTUM", "GRID", "DCA", "ARBITRAGE"]
        if strategy_name not in valid_strategies:
            return False, f"알 수 없는 전략: {strategy_name}"
        
        return True, None
    
    async def _check_conflicts(self, account_id: str, strategy_name: str, 
                              symbols: List[str]) -> List[AllocationConflict]:
        """충돌 검사"""
        conflicts = []
        
        # 1. 심볼 중복 검사
        symbol_map = self.symbol_allocations.get(account_id, {})
        for symbol in symbols:
            if symbol in symbol_map:
                existing_allocation_id = symbol_map[symbol]
                existing_allocation = self.allocations.get(existing_allocation_id)
                
                if existing_allocation and existing_allocation.status == AllocationStatus.ACTIVE:
                    conflict = AllocationConflict(
                        conflict_type=ConflictType.SYMBOL_OVERLAP,
                        account_id=account_id,
                        symbol=symbol,
                        existing_allocation=existing_allocation_id,
                        description=f"심볼 {symbol}이(가) 이미 {existing_allocation.strategy_name} 전략에서 사용 중",
                        severity="HIGH"
                    )
                    conflicts.append(conflict)
        
        # 2. 전략 호환성 검사
        for allocation_id in self.account_allocations.get(account_id, []):
            allocation = self.allocations.get(allocation_id)
            if allocation and allocation.status == AllocationStatus.ACTIVE:
                if not self.compatibility_checker.check_compatibility(
                    allocation.strategy_name, strategy_name
                ):
                    conflict = AllocationConflict(
                        conflict_type=ConflictType.STRATEGY_INCOMPATIBLE,
                        account_id=account_id,
                        existing_allocation=allocation_id,
                        description=f"{allocation.strategy_name}와(과) {strategy_name} 전략은 동시 실행 불가",
                        severity="CRITICAL"
                    )
                    conflicts.append(conflict)
        
        # 3. 리소스 제한 검사
        resource_req = self.compatibility_checker.get_resource_requirements(strategy_name)
        # TODO: 실제 계좌 잔고 및 API 사용량 확인
        
        return conflicts
    
    async def _handle_conflicts(self, conflicts: List[AllocationConflict]) -> Tuple[bool, Optional[str]]:
        """충돌 처리"""
        resolution_mode = self.allocation_rules['conflict_resolution_mode']
        
        if resolution_mode == 'PREVENT':
            # 충돌 방지 모드: 충돌 시 할당 거부
            conflict_desc = ", ".join([c.description for c in conflicts])
            return False, f"충돌 감지: {conflict_desc}"
        
        elif resolution_mode == 'AUTO_RESOLVE':
            # 자동 해결 모드
            for conflict in conflicts:
                if conflict.conflict_type == ConflictType.SYMBOL_OVERLAP:
                    # 기존 할당에서 심볼 제거
                    if conflict.existing_allocation:
                        await self._remove_symbol_from_allocation(
                            conflict.existing_allocation, 
                            conflict.symbol
                        )
                        conflict.resolved = True
                        conflict.resolution = "기존 할당에서 심볼 제거"
                
                elif conflict.conflict_type == ConflictType.STRATEGY_INCOMPATIBLE:
                    # 우선순위가 낮은 전략 일시 정지
                    # TODO: 전략 우선순위 시스템 구현
                    return False, "전략 비호환성 자동 해결 미구현"
            
            # 해결된 충돌 기록
            self.resolved_conflicts.extend([c for c in conflicts if c.resolved])
            return True, None
        
        else:  # MANUAL
            # 수동 해결 모드: 사용자 개입 필요
            return False, "수동 충돌 해결 필요"
    
    async def _register_allocation(self, allocation: StrategyAllocation) -> None:
        """할당 등록"""
        # 할당 저장
        self.allocations[allocation.allocation_id] = allocation
        
        # 계좌별 할당 목록 업데이트
        self.account_allocations[allocation.account_id].append(allocation.allocation_id)
        
        # 심볼별 할당 매핑 업데이트
        for symbol in allocation.symbols:
            self.symbol_allocations[allocation.account_id][symbol] = allocation.allocation_id
        
        logger.info(f"할당 등록: {allocation.allocation_id}")
    
    async def _activate_allocation(self, allocation: StrategyAllocation) -> None:
        """할당 활성화"""
        allocation.status = AllocationStatus.ACTIVE
        allocation.activated_at = datetime.now().isoformat()
        
        logger.info(f"할당 활성화: {allocation.allocation_id}")
    
    async def _remove_symbol_from_allocation(self, allocation_id: str, symbol: str) -> None:
        """할당에서 심볼 제거"""
        allocation = self.allocations.get(allocation_id)
        if not allocation:
            return
        
        if symbol in allocation.symbols:
            allocation.symbols.remove(symbol)
            
            # 심볼 매핑에서도 제거
            if allocation.account_id in self.symbol_allocations:
                self.symbol_allocations[allocation.account_id].pop(symbol, None)
            
            logger.info(f"심볼 제거: {allocation_id}에서 {symbol} 제거")
    
    async def check_symbol_conflict(self, account_id: str, symbol: str) -> bool:
        """
        특정 계좌에서 심볼 충돌 확인
        
        Returns:
            True if conflict exists, False otherwise
        """
        symbol_map = self.symbol_allocations.get(account_id, {})
        return symbol in symbol_map
    
    async def get_allocation_map(self) -> Dict[str, Any]:
        """전체 할당 상태 반환"""
        allocation_map = {
            'summary': {
                'total_allocations': len(self.allocations),
                'active_allocations': sum(1 for a in self.allocations.values() if a.is_active()),
                'total_accounts': len(self.account_allocations),
                'total_conflicts': len(self.conflicts),
                'last_update': self.stats['last_update']
            },
            'allocations_by_account': {},
            'allocations_by_strategy': defaultdict(list),
            'symbol_coverage': defaultdict(set)
        }
        
        # 계좌별 할당
        for account_id, allocation_ids in self.account_allocations.items():
            account_allocations = []
            for alloc_id in allocation_ids:
                allocation = self.allocations.get(alloc_id)
                if allocation:
                    account_allocations.append({
                        'allocation_id': allocation.allocation_id,
                        'strategy': allocation.strategy_name,
                        'symbols': allocation.symbols,
                        'status': allocation.status.value,
                        'pnl': allocation.total_pnl
                    })
            allocation_map['allocations_by_account'][account_id] = account_allocations
        
        # 전략별 할당
        for allocation in self.allocations.values():
            allocation_map['allocations_by_strategy'][allocation.strategy_name].append({
                'account_id': allocation.account_id,
                'symbols': allocation.symbols,
                'status': allocation.status.value
            })
        
        # 심볼 커버리지
        for account_id, symbol_map in self.symbol_allocations.items():
            allocation_map['symbol_coverage'][account_id] = set(symbol_map.keys())
        
        return allocation_map
    
    async def reallocate_strategy(self, allocation_id: str, new_symbols: Optional[List[str]] = None,
                                 new_params: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[str]]:
        """
        전략 재할당 (심볼 또는 파라미터 변경)
        
        Args:
            allocation_id: 할당 ID
            new_symbols: 새로운 심볼 목록 (None이면 변경 없음)
            new_params: 새로운 파라미터 (None이면 변경 없음)
            
        Returns:
            (성공 여부, 오류 메시지)
        """
        async with self._lock:
            try:
                allocation = self.allocations.get(allocation_id)
                if not allocation:
                    return False, "할당을 찾을 수 없습니다"
                
                # 1. 전환 상태로 변경
                allocation.status = AllocationStatus.TRANSITIONING
                
                # 2. 심볼 변경
                if new_symbols is not None:
                    # 기존 심볼 매핑 제거
                    for symbol in allocation.symbols:
                        if allocation.account_id in self.symbol_allocations:
                            self.symbol_allocations[allocation.account_id].pop(symbol, None)
                    
                    # 새 심볼 충돌 검사
                    conflicts = await self._check_conflicts(
                        allocation.account_id, 
                        allocation.strategy_name, 
                        new_symbols
                    )
                    
                    if conflicts:
                        allocation.status = AllocationStatus.ERROR
                        return False, "새 심볼에 충돌이 있습니다"
                    
                    # 심볼 업데이트
                    allocation.symbols = new_symbols
                    
                    # 새 심볼 매핑 등록
                    for symbol in new_symbols:
                        self.symbol_allocations[allocation.account_id][symbol] = allocation_id
                
                # 3. 파라미터 변경
                if new_params:
                    for key, value in new_params.items():
                        if hasattr(allocation, key):
                            setattr(allocation, key, value)
                
                # 4. 활성 상태로 복귀
                allocation.status = AllocationStatus.ACTIVE
                
                self.stats['allocation_changes'] += 1
                self.stats['last_update'] = datetime.now().isoformat()
                
                logger.info(f"전략 재할당 성공: {allocation_id}")
                return True, None
                
            except Exception as e:
                logger.error(f"전략 재할당 실패: {e}")
                if allocation:
                    allocation.status = AllocationStatus.ERROR
                    allocation.last_error = str(e)
                return False, str(e)
    
    async def pause_allocation(self, allocation_id: str, reason: str = "") -> bool:
        """할당 일시 정지"""
        allocation = self.allocations.get(allocation_id)
        if not allocation:
            return False
        
        allocation.status = AllocationStatus.PAUSED
        logger.info(f"할당 일시 정지: {allocation_id} (사유: {reason})")
        
        self.stats['active_allocations'] -= 1
        return True
    
    async def resume_allocation(self, allocation_id: str) -> bool:
        """할당 재개"""
        allocation = self.allocations.get(allocation_id)
        if not allocation or allocation.status != AllocationStatus.PAUSED:
            return False
        
        allocation.status = AllocationStatus.ACTIVE
        logger.info(f"할당 재개: {allocation_id}")
        
        self.stats['active_allocations'] += 1
        return True
    
    async def stop_allocation(self, allocation_id: str, cleanup: bool = True) -> bool:
        """
        할당 중지
        
        Args:
            allocation_id: 할당 ID
            cleanup: 심볼 매핑 정리 여부
        """
        async with self._lock:
            allocation = self.allocations.get(allocation_id)
            if not allocation:
                return False
            
            allocation.status = AllocationStatus.STOPPED
            
            if cleanup:
                # 심볼 매핑 제거
                for symbol in allocation.symbols:
                    if allocation.account_id in self.symbol_allocations:
                        self.symbol_allocations[allocation.account_id].pop(symbol, None)
                
                # 계좌 할당 목록에서 제거
                if allocation.account_id in self.account_allocations:
                    self.account_allocations[allocation.account_id].remove(allocation_id)
            
            logger.info(f"할당 중지: {allocation_id}")
            
            self.stats['active_allocations'] -= 1
            return True
    
    async def get_account_allocations(self, account_id: str) -> List[StrategyAllocation]:
        """특정 계좌의 모든 할당 조회"""
        allocations = []
        for alloc_id in self.account_allocations.get(account_id, []):
            allocation = self.allocations.get(alloc_id)
            if allocation:
                allocations.append(allocation)
        return allocations
    
    async def get_strategy_allocations(self, strategy_name: str) -> List[StrategyAllocation]:
        """특정 전략의 모든 할당 조회"""
        return [
            allocation for allocation in self.allocations.values()
            if allocation.strategy_name == strategy_name
        ]
    
    async def update_allocation_performance(self, allocation_id: str, 
                                          trade_result: Dict[str, Any]) -> None:
        """할당 성과 업데이트"""
        allocation = self.allocations.get(allocation_id)
        if not allocation:
            return
        
        # 거래 통계 업데이트
        allocation.total_trades += 1
        pnl = trade_result.get('pnl', 0)
        allocation.total_pnl += pnl
        
        if pnl > 0:
            allocation.winning_trades += 1
        
        allocation.last_trade_at = datetime.now().isoformat()
        
        # TODO: Sharpe ratio 계산
        
        logger.debug(f"할당 성과 업데이트: {allocation_id}, PnL: {pnl}")
    
    def get_conflict_history(self, resolved_only: bool = False) -> List[AllocationConflict]:
        """충돌 이력 조회"""
        if resolved_only:
            return self.resolved_conflicts
        return self.conflicts
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 반환"""
        return {
            **self.stats,
            'allocation_rules': self.allocation_rules,
            'active_strategies': list(set(
                a.strategy_name for a in self.allocations.values() 
                if a.is_active()
            ))
        }
    
    async def save_state(self, filepath: str) -> None:
        """상태 저장"""
        state = {
            'allocations': {
                aid: alloc.to_dict() 
                for aid, alloc in self.allocations.items()
            },
            'account_allocations': dict(self.account_allocations),
            'symbol_allocations': dict(self.symbol_allocations),
            'conflicts': [c.__dict__ for c in self.conflicts],
            'stats': self.stats,
            'saved_at': datetime.now().isoformat()
        }
        
        with open(filepath, 'w') as f:
            json.dump(state, f, indent=2)
        
        logger.info(f"할당 상태 저장: {filepath}")
    
    async def load_state(self, filepath: str) -> None:
        """상태 로드"""
        try:
            with open(filepath, 'r') as f:
                state = json.load(f)
            
            # 할당 복원
            self.allocations.clear()
            for aid, alloc_data in state.get('allocations', {}).items():
                # AllocationStatus enum 복원
                if 'status' in alloc_data:
                    alloc_data['status'] = AllocationStatus(alloc_data['status'])
                
                allocation = StrategyAllocation(**alloc_data)
                self.allocations[aid] = allocation
            
            # 매핑 복원
            self.account_allocations = defaultdict(list, state.get('account_allocations', {}))
            self.symbol_allocations = defaultdict(dict, state.get('symbol_allocations', {}))
            
            # 통계 복원
            self.stats.update(state.get('stats', {}))
            
            logger.info(f"할당 상태 로드: {filepath}")
            
        except Exception as e:
            logger.error(f"할당 상태 로드 실패: {e}")


class AllocationOptimizer:
    """
    할당 최적화 엔진
    Jane Street 스타일의 포트폴리오 최적화
    """
    
    def __init__(self, allocator: StrategyAllocator):
        """
        Args:
            allocator: 전략 할당자
        """
        self.allocator = allocator
        self.optimization_history = []
        
    async def optimize_allocations(self, constraints: Dict[str, Any]) -> Dict[str, Any]:
        """
        전체 할당 최적화
        
        Args:
            constraints: 최적화 제약 조건
            
        Returns:
            최적화 결과 및 권장사항
        """
        recommendations = {
            'timestamp': datetime.now().isoformat(),
            'reallocations': [],
            'new_allocations': [],
            'removals': [],
            'parameter_adjustments': []
        }
        
        # 1. 성과 기반 분석
        performance_analysis = await self._analyze_performance()
        
        # 2. 리스크 분석
        risk_analysis = await self._analyze_risk()
        
        # 3. 상관관계 분석
        correlation_analysis = await self._analyze_correlations()
        
        # 4. 최적화 권장사항 생성
        # 저성과 전략 식별
        for allocation_id, metrics in performance_analysis['underperforming'].items():
            allocation = self.allocator.allocations.get(allocation_id)
            if allocation:
                if metrics['sharpe_ratio'] < -0.5:  # 매우 낮은 샤프 비율
                    recommendations['removals'].append({
                        'allocation_id': allocation_id,
                        'reason': 'Sharpe ratio < -0.5',
                        'current_pnl': allocation.total_pnl
                    })
                elif metrics['win_rate'] < 30:  # 낮은 승률
                    recommendations['parameter_adjustments'].append({
                        'allocation_id': allocation_id,
                        'suggestion': 'Reduce position size',
                        'new_position_size': allocation.position_size * 0.5
                    })
        
        # 고성과 전략 확장
        for allocation_id, metrics in performance_analysis['outperforming'].items():
            allocation = self.allocator.allocations.get(allocation_id)
            if allocation and metrics['sharpe_ratio'] > 1.5:
                recommendations['parameter_adjustments'].append({
                    'allocation_id': allocation_id,
                    'suggestion': 'Increase position size',
                    'new_position_size': min(allocation.position_size * 1.5, 50)  # 최대 50%
                })
        
        # 상관관계 기반 다각화
        if correlation_analysis['high_correlation_pairs']:
            for pair in correlation_analysis['high_correlation_pairs']:
                recommendations['reallocations'].append({
                    'allocation_ids': pair,
                    'suggestion': 'Diversify symbols to reduce correlation',
                    'correlation': correlation_analysis['correlations'].get(tuple(pair), 0)
                })
        
        self.optimization_history.append(recommendations)
        
        return recommendations
    
    async def _analyze_performance(self) -> Dict[str, Any]:
        """성과 분석"""
        performance_metrics = {
            'underperforming': {},
            'outperforming': {},
            'average_sharpe': 0,
            'total_pnl': 0
        }
        
        sharpe_ratios = []
        
        for allocation_id, allocation in self.allocator.allocations.items():
            if allocation.total_trades > 10:  # 충분한 거래 데이터가 있는 경우만
                win_rate = (allocation.winning_trades / allocation.total_trades) * 100
                avg_pnl_per_trade = allocation.total_pnl / allocation.total_trades
                
                # 간단한 Sharpe ratio 근사치
                # TODO: 실제 수익률 표준편차 계산
                sharpe_estimate = avg_pnl_per_trade / 100  # 단순화된 계산
                
                metrics = {
                    'win_rate': win_rate,
                    'avg_pnl': avg_pnl_per_trade,
                    'sharpe_ratio': sharpe_estimate,
                    'total_trades': allocation.total_trades
                }
                
                if sharpe_estimate < 0:
                    performance_metrics['underperforming'][allocation_id] = metrics
                elif sharpe_estimate > 1:
                    performance_metrics['outperforming'][allocation_id] = metrics
                
                sharpe_ratios.append(sharpe_estimate)
                performance_metrics['total_pnl'] += allocation.total_pnl
        
        if sharpe_ratios:
            performance_metrics['average_sharpe'] = sum(sharpe_ratios) / len(sharpe_ratios)
        
        return performance_metrics
    
    async def _analyze_risk(self) -> Dict[str, Any]:
        """리스크 분석"""
        risk_metrics = {
            'high_risk_allocations': [],
            'concentration_risk': {},
            'total_exposure': 0
        }
        
        # 계좌별 노출도 계산
        account_exposures = defaultdict(float)
        
        for allocation in self.allocator.allocations.values():
            if allocation.is_active():
                exposure = allocation.position_size * allocation.leverage
                account_exposures[allocation.account_id] += exposure
                
                # 고위험 할당 식별
                if exposure > 100:  # 100% 이상 노출
                    risk_metrics['high_risk_allocations'].append({
                        'allocation_id': allocation.allocation_id,
                        'exposure': exposure,
                        'leverage': allocation.leverage
                    })
        
        # 집중 리스크 계산
        total_exposure = sum(account_exposures.values())
        for account_id, exposure in account_exposures.items():
            concentration = (exposure / total_exposure) * 100 if total_exposure > 0 else 0
            if concentration > 50:  # 50% 이상 집중
                risk_metrics['concentration_risk'][account_id] = concentration
        
        risk_metrics['total_exposure'] = total_exposure
        
        return risk_metrics
    
    async def _analyze_correlations(self) -> Dict[str, Any]:
        """상관관계 분석"""
        # TODO: 실제 수익률 상관관계 계산
        # 현재는 간단한 심볼 기반 분석
        
        correlation_metrics = {
            'high_correlation_pairs': [],
            'correlations': {},
            'diversification_score': 0
        }
        
        allocations_list = list(self.allocator.allocations.values())
        
        for i in range(len(allocations_list)):
            for j in range(i + 1, len(allocations_list)):
                alloc1 = allocations_list[i]
                alloc2 = allocations_list[j]
                
                if alloc1.is_active() and alloc2.is_active():
                    # 심볼 겹침 비율을 상관관계 프록시로 사용
                    common_symbols = set(alloc1.symbols) & set(alloc2.symbols)
                    if common_symbols:
                        overlap_ratio = len(common_symbols) / min(len(alloc1.symbols), len(alloc2.symbols))
                        
                        if overlap_ratio > 0.5:  # 50% 이상 겹침
                            correlation_metrics['high_correlation_pairs'].append([
                                alloc1.allocation_id,
                                alloc2.allocation_id
                            ])
                            correlation_metrics['correlations'][(alloc1.allocation_id, alloc2.allocation_id)] = overlap_ratio
        
        # 다각화 점수 계산 (0-100)
        total_symbols = len(set(
            symbol 
            for alloc in allocations_list 
            if alloc.is_active()
            for symbol in alloc.symbols
        ))
        
        active_allocations = sum(1 for alloc in allocations_list if alloc.is_active())
        
        if active_allocations > 0:
            correlation_metrics['diversification_score'] = min(
                (total_symbols / active_allocations) * 10, 
                100
            )
        
        return correlation_metrics


# 사용 예시 및 테스트 코드
async def example_usage():
    """사용 예시"""
    # 할당자 생성
    allocator = StrategyAllocator()
    
    # 전략 할당
    success, allocation, error = await allocator.allocate_strategy(
        account_id="SUB1",
        strategy_name="TFPE",
        symbols=["BTCUSDT", "ETHUSDT"],
        position_size=20.0,
        leverage=10
    )
    
    if success:
        logger.info(f"할당 성공: {allocation.allocation_id}")
    else:
        logger.error(f"할당 실패: {error}")
    
    # 할당 맵 조회
    allocation_map = await allocator.get_allocation_map()
    logger.info(f"전체 할당 상태: {json.dumps(allocation_map, indent=2)}")
    
    # 최적화
    optimizer = AllocationOptimizer(allocator)
    recommendations = await optimizer.optimize_allocations({})
    logger.info(f"최적화 권장사항: {json.dumps(recommendations, indent=2)}")


if __name__ == "__main__":
    # 테스트 실행
    asyncio.run(example_usage())
