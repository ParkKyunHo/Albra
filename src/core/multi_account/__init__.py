# src/core/multi_account/__init__.py
"""
AlbraTrading Multi-Account Management Module
바이낸스 서브 계좌를 활용한 멀티 계좌 관리 시스템
"""

from .account_manager import (
    MultiAccountManager,
    SubAccountInfo,
    AccountType,
    AccountStatus,
    AccountPerformance
)

from .strategy_allocator import (
    StrategyAllocator,
    StrategyAllocation,
    AllocationStatus,
    AllocationConflict,
    ConflictType,
    StrategyCompatibilityChecker,
    AllocationOptimizer
)

from .unified_monitor import (
    UnifiedMonitor,
    AccountPerformance as MonitorAccountPerformance,
    PortfolioSummary,
    RiskConcentration
)

from .risk_manager import (
    MultiAccountRiskManager,
    AutoRecoverySystem,
    RiskLevel,
    ActionType,
    RiskLimit,
    RiskEvent,
    AccountRiskStatus,
    RecoveryPlan
)

__all__ = [
    # Account Manager
    'MultiAccountManager',
    'SubAccountInfo',
    'AccountType',
    'AccountStatus',
    'AccountPerformance',
    
    # Strategy Allocator
    'StrategyAllocator',
    'StrategyAllocation',
    'AllocationStatus',
    'AllocationConflict',
    'ConflictType',
    'StrategyCompatibilityChecker',
    'AllocationOptimizer',
    
    # Unified Monitor
    'UnifiedMonitor',
    'MonitorAccountPerformance',
    'PortfolioSummary',
    'RiskConcentration',
    
    # Risk Manager
    'MultiAccountRiskManager',
    'AutoRecoverySystem',
    'RiskLevel',
    'ActionType',
    'RiskLimit',
    'RiskEvent',
    'AccountRiskStatus',
    'RecoveryPlan'
]

__version__ = '1.0.0'
