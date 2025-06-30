"""
통합 모니터링 시스템
멀티 계좌의 전체 상태를 통합하여 모니터링하고 분석
"""
import asyncio
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from decimal import Decimal
import logging
from collections import defaultdict

from src.core.multi_account.account_manager import MultiAccountManager
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class AccountPerformance:
    """계좌별 성과 데이터"""
    account_id: str
    total_balance: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    total_pnl: Decimal
    pnl_percentage: float
    win_rate: float
    sharpe_ratio: float
    max_drawdown: float
    active_positions: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    last_update: datetime = field(default_factory=datetime.now)


@dataclass
class PortfolioSummary:
    """전체 포트폴리오 요약"""
    total_balance: Decimal
    total_unrealized_pnl: Decimal
    total_realized_pnl: Decimal
    total_pnl: Decimal
    total_pnl_percentage: float
    accounts_count: int
    active_accounts: int
    total_positions: int
    risk_concentration: Dict[str, float]
    correlation_matrix: Optional[pd.DataFrame]
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class RiskConcentration:
    """리스크 집중도 분석"""
    by_account: Dict[str, float]
    by_symbol: Dict[str, float]
    by_strategy: Dict[str, float]
    max_concentration_account: Tuple[str, float]
    max_concentration_symbol: Tuple[str, float]
    warnings: List[str]


class UnifiedMonitor:
    """멀티 계좌 통합 모니터링 시스템"""
    
    def __init__(self, account_manager: MultiAccountManager):
        self.account_manager = account_manager
        self.performance_history: Dict[str, List[AccountPerformance]] = defaultdict(list)
        self.portfolio_history: List[PortfolioSummary] = []
        self.monitoring_interval = 60  # seconds
        self.is_monitoring = False
        self._monitoring_task: Optional[asyncio.Task] = None
        
        # 성과 분석을 위한 데이터 저장
        self.daily_returns: Dict[str, List[float]] = defaultdict(list)
        self.trade_history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        
        # 리스크 임계값
        self.risk_thresholds = {
            'max_account_concentration': 0.5,  # 50%
            'max_symbol_concentration': 0.4,   # 40%
            'max_correlation': 0.8,            # 80%
            'min_sharpe_ratio': -1.0,
            'max_drawdown': 0.4               # 40%
        }
    
    async def start_monitoring(self) -> None:
        """모니터링 시작"""
        if self.is_monitoring:
            logger.warning("Monitoring already started")
            return
        
        self.is_monitoring = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Unified monitoring started")
    
    async def stop_monitoring(self) -> None:
        """모니터링 중지"""
        self.is_monitoring = False
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Unified monitoring stopped")
    
    async def _monitoring_loop(self) -> None:
        """모니터링 루프"""
        while self.is_monitoring:
            try:
                # 포트폴리오 데이터 수집
                portfolio_summary = await self.get_portfolio_summary()
                self.portfolio_history.append(portfolio_summary)
                
                # 계좌별 성과 수집
                for account_id in self.account_manager.accounts:
                    performance = await self._get_account_performance(account_id)
                    if performance:
                        self.performance_history[account_id].append(performance)
                
                # 리스크 체크
                risk_concentration = await self.check_risk_concentration()
                if risk_concentration.warnings:
                    for warning in risk_concentration.warnings:
                        logger.warning(f"Risk warning: {warning}")
                
                # 이상 징후 감지
                await self._detect_anomalies()
                
                # 히스토리 크기 관리 (최근 24시간만 유지)
                self._cleanup_old_history()
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}", exc_info=True)
            
            await asyncio.sleep(self.monitoring_interval)
    
    async def get_portfolio_summary(self) -> PortfolioSummary:
        """전체 포트폴리오 요약 정보 생성"""
        total_balance = Decimal('0')
        total_unrealized_pnl = Decimal('0')
        total_realized_pnl = Decimal('0')
        total_positions = 0
        active_accounts = 0
        
        # 계좌별 잔고 정보 수집
        account_balances = {}
        for account_id in self.account_manager.accounts:
            try:
                client = self.account_manager.api_clients.get(account_id)
                if not client:
                    continue
                    
                balance_info = await client.get_account_info()
                positions = await client.get_positions()
                
                if balance_info:
                    account_balance = Decimal(str(balance_info.get('totalWalletBalance', 0)))
                    account_unrealized_pnl = Decimal(str(balance_info.get('totalUnrealizedProfit', 0)))
                    
                    total_balance += account_balance
                    total_unrealized_pnl += account_unrealized_pnl
                    
                    account_balances[account_id] = {
                        'balance': account_balance,
                        'unrealized_pnl': account_unrealized_pnl,
                        'positions': len(positions) if positions else 0
                    }
                    
                    if positions:
                        total_positions += len(positions)
                        active_accounts += 1
                        
            except Exception as e:
                logger.error(f"Error getting balance for account {account_id}: {e}")
        
        # 리스크 집중도 계산
        risk_concentration = self._calculate_risk_concentration(account_balances)
        
        # 상관관계 매트릭스 생성 (충분한 데이터가 있을 때만)
        correlation_matrix = None
        if len(self.daily_returns) >= 2 and all(len(returns) >= 20 for returns in self.daily_returns.values()):
            correlation_matrix = self._calculate_correlation_matrix()
        
        # 전체 PnL 계산
        total_pnl = total_unrealized_pnl + total_realized_pnl
        total_pnl_percentage = float(total_pnl / total_balance * 100) if total_balance > 0 else 0.0
        
        return PortfolioSummary(
            total_balance=total_balance,
            total_unrealized_pnl=total_unrealized_pnl,
            total_realized_pnl=total_realized_pnl,
            total_pnl=total_pnl,
            total_pnl_percentage=total_pnl_percentage,
            accounts_count=len(self.account_manager.accounts),
            active_accounts=active_accounts,
            total_positions=total_positions,
            risk_concentration=risk_concentration,
            correlation_matrix=correlation_matrix
        )
    
    async def check_risk_concentration(self) -> RiskConcentration:
        """리스크 집중도 체크"""
        by_account = {}
        by_symbol = defaultdict(float)
        by_strategy = defaultdict(float)
        warnings = []
        
        total_exposure = 0.0
        
        # 계좌별 노출도 계산
        for account_id in self.account_manager.accounts:
            try:
                client = self.account_manager.api_clients.get(account_id)
                if not client:
                    continue
                    
                positions = await client.get_positions()
                account_exposure = 0.0
                
                if positions:
                    for position in positions:
                        position_value = float(position.get('positionAmt', 0)) * float(position.get('markPrice', 0))
                        position_exposure = abs(position_value)
                        
                        account_exposure += position_exposure
                        by_symbol[position.get('symbol', 'UNKNOWN')] += position_exposure
                        total_exposure += position_exposure
                
                by_account[account_id] = account_exposure
                
                # 전략별 집계 (strategy_allocator에서 정보 가져오기)
                if hasattr(self.account_manager, 'strategy_allocator'):
                    strategy = self.account_manager.strategy_allocator.get_strategy_for_account(account_id)
                    if strategy:
                        by_strategy[strategy.__class__.__name__] += account_exposure
                        
            except Exception as e:
                logger.error(f"Error checking risk for account {account_id}: {e}")
        
        # 집중도 비율 계산
        if total_exposure > 0:
            for account_id, exposure in by_account.items():
                concentration = exposure / total_exposure
                by_account[account_id] = concentration
                
                if concentration > self.risk_thresholds['max_account_concentration']:
                    warnings.append(
                        f"Account {account_id} concentration too high: {concentration:.1%}"
                    )
            
            for symbol, exposure in by_symbol.items():
                concentration = exposure / total_exposure
                by_symbol[symbol] = concentration
                
                if concentration > self.risk_thresholds['max_symbol_concentration']:
                    warnings.append(
                        f"Symbol {symbol} concentration too high: {concentration:.1%}"
                    )
            
            for strategy, exposure in by_strategy.items():
                by_strategy[strategy] = exposure / total_exposure
        
        # 최대 집중도 찾기
        max_account = max(by_account.items(), key=lambda x: x[1]) if by_account else ('', 0.0)
        max_symbol = max(by_symbol.items(), key=lambda x: x[1]) if by_symbol else ('', 0.0)
        
        return RiskConcentration(
            by_account=dict(by_account),
            by_symbol=dict(by_symbol),
            by_strategy=dict(by_strategy),
            max_concentration_account=max_account,
            max_concentration_symbol=max_symbol,
            warnings=warnings
        )
    
    async def get_performance_comparison(self) -> Dict[str, Dict[str, Any]]:
        """계좌별 성과 비교 데이터 생성"""
        comparison = {}
        
        for account_id in self.account_manager.accounts:
            performance = await self._get_account_performance(account_id)
            if performance:
                comparison[account_id] = {
                    'total_pnl': float(performance.total_pnl),
                    'pnl_percentage': performance.pnl_percentage,
                    'win_rate': performance.win_rate,
                    'sharpe_ratio': performance.sharpe_ratio,
                    'max_drawdown': performance.max_drawdown,
                    'active_positions': performance.active_positions,
                    'total_trades': performance.total_trades
                }
        
        # 차트 데이터 생성
        chart_data = self._generate_chart_data(comparison)
        
        return {
            'comparison': comparison,
            'chart_data': chart_data
        }
    
    async def _get_account_performance(self, account_id: str) -> Optional[AccountPerformance]:
        """계좌별 성과 데이터 수집"""
        try:
            client = self.account_manager.api_clients.get(account_id)
            if not client:
                return None
            
            # 잔고 정보
            balance_info = await client.get_account_info()
            if not balance_info:
                return None
            
            # 포지션 정보
            positions = await client.get_positions() or []
            
            # 거래 이력 (실제 구현에서는 데이터베이스나 API에서 가져와야 함)
            # 여기서는 임시로 계산
            total_trades = len(self.trade_history.get(account_id, []))
            winning_trades = sum(1 for trade in self.trade_history.get(account_id, []) 
                               if trade.get('pnl', 0) > 0)
            losing_trades = total_trades - winning_trades
            
            # 성과 지표 계산
            total_balance = Decimal(str(balance_info.get('totalWalletBalance', 0)))
            unrealized_pnl = Decimal(str(balance_info.get('totalUnrealizedProfit', 0)))
            realized_pnl = Decimal('0')  # API에서 가져오거나 계산 필요
            total_pnl = unrealized_pnl + realized_pnl
            
            pnl_percentage = float(total_pnl / total_balance * 100) if total_balance > 0 else 0.0
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
            
            # Sharpe Ratio 계산 (일일 수익률 기반)
            returns = self.daily_returns.get(account_id, [])
            sharpe_ratio = self._calculate_sharpe_ratio(returns) if len(returns) >= 20 else 0.0
            
            # 최대 낙폭 계산
            max_drawdown = self._calculate_max_drawdown(account_id)
            
            return AccountPerformance(
                account_id=account_id,
                total_balance=total_balance,
                unrealized_pnl=unrealized_pnl,
                realized_pnl=realized_pnl,
                total_pnl=total_pnl,
                pnl_percentage=pnl_percentage,
                win_rate=win_rate,
                sharpe_ratio=sharpe_ratio,
                max_drawdown=max_drawdown,
                active_positions=len(positions),
                total_trades=total_trades,
                winning_trades=winning_trades,
                losing_trades=losing_trades
            )
            
        except Exception as e:
            logger.error(f"Error getting performance for account {account_id}: {e}")
            return None
    
    def _calculate_risk_concentration(self, account_balances: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
        """리스크 집중도 계산"""
        total_balance = sum(data['balance'] for data in account_balances.values())
        
        if total_balance == 0:
            return {}
        
        return {
            account_id: float(data['balance'] / total_balance)
            for account_id, data in account_balances.items()
        }
    
    def _calculate_correlation_matrix(self) -> pd.DataFrame:
        """계좌 간 상관관계 매트릭스 계산"""
        returns_df = pd.DataFrame(self.daily_returns)
        return returns_df.corr()
    
    def _calculate_sharpe_ratio(self, returns: List[float], risk_free_rate: float = 0.02) -> float:
        """샤프 비율 계산"""
        if not returns or len(returns) < 2:
            return 0.0
        
        returns_array = np.array(returns)
        excess_returns = returns_array - risk_free_rate / 252  # 일일 무위험 수익률
        
        if np.std(excess_returns) == 0:
            return 0.0
        
        return np.sqrt(252) * np.mean(excess_returns) / np.std(excess_returns)
    
    def _calculate_max_drawdown(self, account_id: str) -> float:
        """최대 낙폭 계산"""
        history = self.performance_history.get(account_id, [])
        if len(history) < 2:
            return 0.0
        
        balances = [float(perf.total_balance) for perf in history]
        peak = balances[0]
        max_dd = 0.0
        
        for balance in balances[1:]:
            if balance > peak:
                peak = balance
            else:
                drawdown = (peak - balance) / peak
                max_dd = max(max_dd, drawdown)
        
        return max_dd
    
    def _generate_chart_data(self, comparison: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """차트 데이터 생성"""
        return {
            'pnl_comparison': {
                'labels': list(comparison.keys()),
                'datasets': [{
                    'label': 'Total PnL (%)',
                    'data': [data['pnl_percentage'] for data in comparison.values()],
                    'backgroundColor': ['#4CAF50' if data['pnl_percentage'] >= 0 else '#F44336' 
                                       for data in comparison.values()]
                }]
            },
            'performance_metrics': {
                'labels': list(comparison.keys()),
                'datasets': [
                    {
                        'label': 'Win Rate (%)',
                        'data': [data['win_rate'] for data in comparison.values()],
                        'borderColor': '#2196F3',
                        'fill': False
                    },
                    {
                        'label': 'Sharpe Ratio',
                        'data': [data['sharpe_ratio'] for data in comparison.values()],
                        'borderColor': '#FF9800',
                        'fill': False
                    }
                ]
            },
            'position_distribution': {
                'labels': list(comparison.keys()),
                'datasets': [{
                    'label': 'Active Positions',
                    'data': [data['active_positions'] for data in comparison.values()],
                    'backgroundColor': '#9C27B0'
                }]
            }
        }
    
    async def _detect_anomalies(self) -> None:
        """이상 징후 감지"""
        for account_id in self.account_manager.accounts:
            history = self.performance_history.get(account_id, [])
            if len(history) < 10:
                continue
            
            recent_performance = history[-1]
            
            # Sharpe Ratio 이상
            if recent_performance.sharpe_ratio < self.risk_thresholds['min_sharpe_ratio']:
                logger.warning(
                    f"Low Sharpe ratio detected for account {account_id}: "
                    f"{recent_performance.sharpe_ratio:.2f}"
                )
            
            # 최대 낙폭 이상
            if recent_performance.max_drawdown > self.risk_thresholds['max_drawdown']:
                logger.warning(
                    f"High drawdown detected for account {account_id}: "
                    f"{recent_performance.max_drawdown:.1%}"
                )
            
            # 급격한 잔고 변화 감지
            if len(history) >= 2:
                prev_balance = float(history[-2].total_balance)
                curr_balance = float(history[-1].total_balance)
                
                if prev_balance > 0:
                    change_rate = abs(curr_balance - prev_balance) / prev_balance
                    if change_rate > 0.1:  # 10% 이상 변화
                        logger.warning(
                            f"Rapid balance change detected for account {account_id}: "
                            f"{change_rate:.1%}"
                        )
    
    def _cleanup_old_history(self) -> None:
        """오래된 히스토리 데이터 정리"""
        cutoff_time = datetime.now() - timedelta(hours=24)
        
        # 계좌별 성과 히스토리 정리
        for account_id in list(self.performance_history.keys()):
            self.performance_history[account_id] = [
                perf for perf in self.performance_history[account_id]
                if perf.last_update > cutoff_time
            ]
        
        # 포트폴리오 히스토리 정리
        self.portfolio_history = [
            summary for summary in self.portfolio_history
            if summary.timestamp > cutoff_time
        ]
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """모니터링 상태 반환"""
        return {
            'is_monitoring': self.is_monitoring,
            'monitoring_interval': self.monitoring_interval,
            'accounts_monitored': len(self.account_manager.accounts),
            'history_size': {
                'portfolio': len(self.portfolio_history),
                'accounts': {
                    account_id: len(history)
                    for account_id, history in self.performance_history.items()
                }
            },
            'risk_thresholds': self.risk_thresholds
        }
