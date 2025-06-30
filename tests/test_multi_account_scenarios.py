"""
AlbraTrading 멀티 계좌 시스템 통합 테스트
Phase 2 멀티 계좌 기능의 다양한 시나리오를 테스트
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
from decimal import Decimal
import json
import os
from typing import Dict, List, Any

from src.core.multi_account import (
    MultiAccountManager,
    UnifiedMonitor,
    MultiAccountRiskManager,
    StrategyAllocator,
    AccountType,
    RiskLevel,
    ActionType
)
from src.strategies.tfpe_strategy import TFPEStrategy
from src.utils.config_manager import ConfigManager
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class TestMultiAccountScenarios:
    """멀티 계좌 시나리오 테스트"""
    
    @pytest.fixture
    async def setup_multi_account_system(self):
        """멀티 계좌 시스템 설정"""
        # Mock 설정
        config_manager = Mock(spec=ConfigManager)
        config_manager.get.return_value = {
            'multi_account': {
                'enabled': True,
                'mode': 'multi',
                'sub_accounts': [
                    {
                        'account_id': 'sub1',
                        'api_key': 'test_key_sub1',
                        'api_secret': 'test_secret_sub1',
                        'testnet': True
                    }
                ]
            }
        }
        
        # 시스템 컴포넌트 생성
        account_manager = MultiAccountManager(config_manager)
        unified_monitor = UnifiedMonitor(account_manager)
        risk_manager = MultiAccountRiskManager(account_manager, unified_monitor)
        strategy_allocator = StrategyAllocator(config_manager)
        
        # Mock 클라이언트 설정
        master_client = AsyncMock()
        sub1_client = AsyncMock()
        
        account_manager.accounts = {
            'master': master_client,
            'sub1': sub1_client
        }
        
        yield {
            'config_manager': config_manager,
            'account_manager': account_manager,
            'unified_monitor': unified_monitor,
            'risk_manager': risk_manager,
            'strategy_allocator': strategy_allocator,
            'master_client': master_client,
            'sub1_client': sub1_client
        }
    
    @pytest.mark.asyncio
    async def test_single_to_multi_migration(self, setup_multi_account_system):
        """단일 계좌에서 멀티 계좌로 마이그레이션 테스트"""
        system = setup_multi_account_system
        
        # 단일 모드 시작
        system['config_manager'].get.return_value['multi_account']['mode'] = 'single'
        
        # 마스터 계좌 잔고 설정
        system['master_client'].get_balance.return_value = {
            'totalWalletBalance': '10000',
            'availableBalance': '8000',
            'totalUnrealizedProfit': '500'
        }
        
        # 마스터 계좌 포지션 설정
        system['master_client'].get_positions.return_value = [
            {
                'symbol': 'BTCUSDT',
                'positionAmt': '0.1',
                'entryPrice': '50000',
                'markPrice': '51000',
                'unrealizedProfit': '100'
            }
        ]
        
        # 단일 모드에서 활성 계좌 확인
        assert len(system['account_manager'].accounts) == 2  # master + sub1
        assert 'master' in system['account_manager'].accounts
        
        # 멀티 모드로 전환
        system['config_manager'].get.return_value['multi_account']['mode'] = 'multi'
        
        # 서브 계좌 잔고 설정
        system['sub1_client'].get_balance.return_value = {
            'totalWalletBalance': '5000',
            'availableBalance': '5000',
            'totalUnrealizedProfit': '0'
        }
        
        system['sub1_client'].get_positions.return_value = []
        
        # 전략 할당
        master_strategy = Mock(spec=TFPEStrategy)
        sub1_strategy = Mock(spec=TFPEStrategy)
        
        await system['strategy_allocator'].allocate_strategy(
            'master', 'TFPE', {'leverage': 10}
        )
        await system['strategy_allocator'].allocate_strategy(
            'sub1', 'TFPE', {'leverage': 5}
        )
        
        # 포트폴리오 요약 확인
        portfolio = await system['unified_monitor'].get_portfolio_summary()
        
        assert portfolio.total_balance == Decimal('15000')  # 10000 + 5000
        assert portfolio.total_unrealized_pnl == Decimal('500')
        assert portfolio.accounts_count == 2
        assert portfolio.active_accounts == 1  # master만 포지션 있음
        assert portfolio.total_positions == 1
    
    @pytest.mark.asyncio
    async def test_account_isolation(self, setup_multi_account_system):
        """계좌 간 격리 테스트"""
        system = setup_multi_account_system
        
        # 마스터 계좌 설정
        system['master_client'].get_balance.return_value = {
            'totalWalletBalance': '10000',
            'availableBalance': '8000'
        }
        
        system['master_client'].get_positions.return_value = [
            {
                'symbol': 'BTCUSDT',
                'positionAmt': '0.1',
                'entryPrice': '50000',
                'markPrice': '45000',  # 손실 상태
                'unrealizedProfit': '-500'
            }
        ]
        
        # 서브 계좌 설정
        system['sub1_client'].get_balance.return_value = {
            'totalWalletBalance': '5000',
            'availableBalance': '4500'
        }
        
        system['sub1_client'].get_positions.return_value = [
            {
                'symbol': 'ETHUSDT',
                'positionAmt': '1',
                'entryPrice': '3000',
                'markPrice': '3100',  # 이익 상태
                'unrealizedProfit': '100'
            }
        ]
        
        # 리스크 체크
        master_risk = await system['risk_manager'].check_account_risk('master')
        sub1_risk = await system['risk_manager'].check_account_risk('sub1')
        
        # 마스터 계좌만 리스크 경고
        assert master_risk.daily_pnl_pct < 0  # 손실
        assert sub1_risk.daily_pnl_pct >= 0  # 이익 또는 0
        
        # 마스터 계좌 거래 일시 중지
        await system['risk_manager'].pause_account_trading('master', 'Test pause')
        
        # 서브 계좌는 영향받지 않음
        assert 'master' in system['risk_manager'].paused_accounts
        assert 'sub1' not in system['risk_manager'].paused_accounts
        
        # 서브 계좌는 정상 거래 가능
        assert sub1_risk.is_trading_allowed
    
    @pytest.mark.asyncio
    async def test_concurrent_trading(self, setup_multi_account_system):
        """동시 거래 실행 테스트"""
        system = setup_multi_account_system
        
        # 두 계좌 모두 거래 가능 상태
        system['master_client'].get_balance.return_value = {
            'totalWalletBalance': '10000',
            'availableBalance': '10000'
        }
        
        system['sub1_client'].get_balance.return_value = {
            'totalWalletBalance': '5000',
            'availableBalance': '5000'
        }
        
        system['master_client'].get_positions.return_value = []
        system['sub1_client'].get_positions.return_value = []
        
        # 주문 실행 Mock
        system['master_client'].place_order.return_value = {
            'orderId': '123',
            'status': 'NEW',
            'symbol': 'BTCUSDT'
        }
        
        system['sub1_client'].place_order.return_value = {
            'orderId': '456',
            'status': 'NEW',
            'symbol': 'ETHUSDT'
        }
        
        # 동시 주문 실행
        master_task = asyncio.create_task(
            system['master_client'].place_order(
                symbol='BTCUSDT',
                side='BUY',
                order_type='MARKET',
                quantity=0.1
            )
        )
        
        sub1_task = asyncio.create_task(
            system['sub1_client'].place_order(
                symbol='ETHUSDT',
                side='BUY',
                order_type='MARKET',
                quantity=1.0
            )
        )
        
        # 동시 실행 확인
        results = await asyncio.gather(master_task, sub1_task)
        
        assert len(results) == 2
        assert results[0]['orderId'] == '123'
        assert results[1]['orderId'] == '456'
        
        # 각 계좌가 독립적으로 주문 실행했는지 확인
        system['master_client'].place_order.assert_called_once()
        system['sub1_client'].place_order.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_failure_recovery(self, setup_multi_account_system):
        """장애 복구 테스트"""
        system = setup_multi_account_system
        
        # 초기 상태 설정
        system['master_client'].get_balance.return_value = {
            'totalWalletBalance': '10000',
            'availableBalance': '8000'
        }
        
        system['master_client'].get_positions.return_value = [
            {
                'symbol': 'BTCUSDT',
                'positionAmt': '0.1',
                'entryPrice': '50000',
                'markPrice': '45000',
                'unrealizedProfit': '-500'
            }
        ]
        
        # 일일 손실 한도 초과 시뮬레이션
        system['risk_manager'].daily_pnl_tracking['master'] = {
            'start_balance': 11000,  # 시작 잔고
            'date': datetime.now().strftime('%Y-%m-%d')
        }
        
        # 리스크 체크 (손실 한도 초과)
        await system['risk_manager'].check_account_risk('master')
        
        # 자동으로 거래 일시 중지되었는지 확인
        assert 'master' in system['risk_manager'].paused_accounts
        
        # 자동 복구 시스템 활성화
        auto_recovery = system['risk_manager'].AutoRecoverySystem(system['risk_manager'])
        recovery_plan = await auto_recovery.create_recovery_plan(
            'master',
            'daily_loss_limit_exceeded',
            'GRADUAL_RESUME'
        )
        
        assert recovery_plan.recovery_type == 'GRADUAL_RESUME'
        assert 'risk_level_improved' in recovery_plan.conditions
        assert len(recovery_plan.actions) > 0
        
        # 복구 조건 충족 시뮬레이션
        system['risk_manager'].account_risk_status['master'] = Mock(
            risk_level=RiskLevel.MEDIUM,
            daily_pnl_pct=-0.5  # 손실 회복
        )
        
        # 복구 실행
        await system['risk_manager']._execute_recovery_plan('master', recovery_plan)
        
        # 거래 재개되었는지 확인
        assert 'master' not in system['risk_manager'].paused_accounts
        assert recovery_plan.executed_at is not None
    
    @pytest.mark.asyncio
    async def test_risk_limits(self, setup_multi_account_system):
        """리스크 한도 테스트"""
        system = setup_multi_account_system
        
        # 계좌별 다른 리스크 한도 설정
        system['risk_manager'].set_account_risk_limits('master', {
            'daily_loss_limit_pct': 5.0,
            'max_leverage': 20
        })
        
        system['risk_manager'].set_account_risk_limits('sub1', {
            'daily_loss_limit_pct': 3.0,  # 더 보수적
            'max_leverage': 10
        })
        
        # 마스터 계좌: 4% 손실 (한도 내)
        system['master_client'].get_balance.return_value = {
            'totalWalletBalance': '9600',
            'availableBalance': '9600'
        }
        
        system['risk_manager'].daily_pnl_tracking['master'] = {
            'start_balance': 10000,
            'date': datetime.now().strftime('%Y-%m-%d')
        }
        
        # 서브 계좌: 3.5% 손실 (한도 초과)
        system['sub1_client'].get_balance.return_value = {
            'totalWalletBalance': '4825',
            'availableBalance': '4825'
        }
        
        system['risk_manager'].daily_pnl_tracking['sub1'] = {
            'start_balance': 5000,
            'date': datetime.now().strftime('%Y-%m-%d')
        }
        
        # 리스크 체크
        master_ok = await system['risk_manager'].check_daily_loss_limit('master')
        sub1_ok = await system['risk_manager'].check_daily_loss_limit('sub1')
        
        # 마스터는 OK, 서브는 한도 초과
        assert master_ok is True
        assert sub1_ok is False
        assert 'sub1' in system['risk_manager'].paused_accounts
        assert 'master' not in system['risk_manager'].paused_accounts
    
    @pytest.mark.asyncio
    async def test_portfolio_risk_concentration(self, setup_multi_account_system):
        """포트폴리오 리스크 집중도 테스트"""
        system = setup_multi_account_system
        
        # 마스터 계좌: BTC에 집중
        system['master_client'].get_positions.return_value = [
            {
                'symbol': 'BTCUSDT',
                'positionAmt': '0.2',
                'markPrice': '50000'
            }
        ]
        
        # 서브 계좌: 역시 BTC에 집중
        system['sub1_client'].get_positions.return_value = [
            {
                'symbol': 'BTCUSDT',
                'positionAmt': '0.1',
                'markPrice': '50000'
            }
        ]
        
        # 리스크 집중도 체크
        concentration = await system['unified_monitor'].check_risk_concentration()
        
        # BTC 집중도 확인
        assert 'BTCUSDT' in concentration.by_symbol
        assert concentration.by_symbol['BTCUSDT'] > 0.9  # 90% 이상 집중
        
        # 경고 발생 확인
        assert len(concentration.warnings) > 0
        assert any('concentration too high' in w for w in concentration.warnings)
        
        # 포트폴리오 리스크 레벨 확인
        portfolio_risk = await system['risk_manager'].check_portfolio_risk()
        assert portfolio_risk.value >= RiskLevel.MEDIUM.value
    
    @pytest.mark.asyncio
    async def test_emergency_stop_cascade(self, setup_multi_account_system):
        """연쇄 긴급 정지 테스트"""
        system = setup_multi_account_system
        
        # 포지션 설정
        system['master_client'].get_positions.return_value = [
            {'symbol': 'BTCUSDT', 'positionAmt': '0.1', 'markPrice': '50000'},
            {'symbol': 'ETHUSDT', 'positionAmt': '1.0', 'markPrice': '3000'}
        ]
        
        system['sub1_client'].get_positions.return_value = [
            {'symbol': 'BNBUSDT', 'positionAmt': '10', 'markPrice': '300'}
        ]
        
        # 주문 취소 및 포지션 청산 Mock
        system['master_client'].get_open_orders.return_value = []
        system['sub1_client'].get_open_orders.return_value = []
        
        system['master_client'].place_order.return_value = {'orderId': '999'}
        system['sub1_client'].place_order.return_value = {'orderId': '998'}
        
        # 전체 긴급 정지
        result = await system['risk_manager'].emergency_stop_all()
        
        assert result is True
        assert system['risk_manager'].emergency_stopped is True
        
        # 모든 계좌가 정지되었는지 확인
        assert 'master' in system['risk_manager'].paused_accounts
        assert 'sub1' in system['risk_manager'].paused_accounts
        
        # 포지션 청산 주문 확인
        assert system['master_client'].place_order.call_count >= 2  # 2개 포지션
        assert system['sub1_client'].place_order.call_count >= 1  # 1개 포지션
    
    @pytest.mark.asyncio
    async def test_strategy_compatibility(self, setup_multi_account_system):
        """전략 호환성 테스트"""
        system = setup_multi_account_system
        
        # 전략 체커 생성
        checker = system['strategy_allocator'].StrategyCompatibilityChecker()
        
        # 마스터: TFPE 전략
        master_allocation = system['strategy_allocator'].StrategyAllocation(
            account_id='master',
            strategy_name='TFPE',
            parameters={'leverage': 10, 'position_size': 0.24}
        )
        
        # 서브1: TFPE 전략 (다른 파라미터)
        sub1_allocation = system['strategy_allocator'].StrategyAllocation(
            account_id='sub1',
            strategy_name='TFPE',
            parameters={'leverage': 5, 'position_size': 0.10}
        )
        
        # 호환성 체크
        is_compatible = checker.check_compatibility([master_allocation, sub1_allocation])
        
        # 같은 전략이지만 다른 파라미터는 호환 가능
        assert is_compatible is True
        
        # 충돌 체크
        conflicts = checker.find_conflicts([master_allocation, sub1_allocation])
        assert len(conflicts) == 0
    
    @pytest.mark.asyncio
    async def test_performance_tracking(self, setup_multi_account_system):
        """성과 추적 테스트"""
        system = setup_multi_account_system
        
        # 모니터링 시작
        await system['unified_monitor'].start_monitoring()
        
        # 초기 잔고 설정
        system['master_client'].get_balance.return_value = {
            'totalWalletBalance': '10000',
            'totalUnrealizedProfit': '0'
        }
        
        system['sub1_client'].get_balance.return_value = {
            'totalWalletBalance': '5000',
            'totalUnrealizedProfit': '0'
        }
        
        system['master_client'].get_positions.return_value = []
        system['sub1_client'].get_positions.return_value = []
        
        # 시간 경과 시뮬레이션
        await asyncio.sleep(0.1)
        
        # 수익 발생
        system['master_client'].get_balance.return_value = {
            'totalWalletBalance': '10500',
            'totalUnrealizedProfit': '500'
        }
        
        # 성과 비교
        performance = await system['unified_monitor'].get_performance_comparison()
        
        assert 'comparison' in performance
        assert 'chart_data' in performance
        
        # 차트 데이터 검증
        chart_data = performance['chart_data']
        assert 'pnl_comparison' in chart_data
        assert 'performance_metrics' in chart_data
        
        await system['unified_monitor'].stop_monitoring()


@pytest.mark.asyncio
async def test_multi_account_integration():
    """통합 테스트 실행"""
    test_suite = TestMultiAccountScenarios()
    
    # 픽스처 수동 설정
    async with test_suite.setup_multi_account_system() as system:
        # 각 테스트 실행
        await test_suite.test_single_to_multi_migration(system)
        await test_suite.test_account_isolation(system)
        await test_suite.test_concurrent_trading(system)
        await test_suite.test_failure_recovery(system)
        await test_suite.test_risk_limits(system)
        await test_suite.test_portfolio_risk_concentration(system)
        await test_suite.test_emergency_stop_cascade(system)
        await test_suite.test_strategy_compatibility(system)
        await test_suite.test_performance_tracking(system)
    
    logger.info("All multi-account integration tests passed!")


if __name__ == '__main__':
    # 직접 실행 시
    asyncio.run(test_multi_account_integration())
