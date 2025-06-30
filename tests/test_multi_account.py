# tests/test_multi_account.py
"""
Multi-Account Manager Unit Tests
멀티 계좌 시스템 단위 테스트
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch
import os
import sys

# 프로젝트 루트 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.multi_account.account_manager import (
    MultiAccountManager, 
    SubAccountInfo, 
    AccountType, 
    AccountStatus,
    AccountPerformance
)
from src.utils.config_manager import ConfigManager
from src.core.state_manager import StateManager


class TestMultiAccountManager:
    """MultiAccountManager 테스트"""
    
    @pytest.fixture
    def mock_config_manager(self):
        """Mock ConfigManager"""
        config_manager = Mock(spec=ConfigManager)
        config_manager.config = {
            'multi_account': {
                'enabled': True,
                'sub_accounts': {
                    'test_account_1': {
                        'type': 'SUB_FUTURES',
                        'enabled': True,
                        'strategy': 'TFPE',
                        'leverage': 5,
                        'position_size': 10.0,
                        'max_positions': 1,
                        'daily_loss_limit': 2.0,
                        'max_drawdown': 10.0,
                        'symbols': ['BTCUSDT']
                    }
                }
            },
            'system': {'mode': 'testnet'}
        }
        return config_manager
    
    @pytest.fixture
    def mock_state_manager(self):
        """Mock StateManager"""
        state_manager = Mock(spec=StateManager)
        state_manager.save_multi_account_state = AsyncMock()
        state_manager.load_multi_account_state = AsyncMock(return_value={})
        return state_manager
    
    @pytest.fixture
    def mock_notification_manager(self):
        """Mock NotificationManager"""
        notification_manager = Mock()
        notification_manager.send_alert = AsyncMock()
        return notification_manager
    
    @pytest.fixture
    def multi_account_manager(self, mock_config_manager, mock_state_manager, mock_notification_manager):
        """MultiAccountManager 인스턴스"""
        return MultiAccountManager(
            config_manager=mock_config_manager,
            state_manager=mock_state_manager,
            notification_manager=mock_notification_manager
        )
    
    def test_initialization(self, multi_account_manager):
        """초기화 테스트"""
        assert multi_account_manager.enabled == True
        assert multi_account_manager._initialized == False
        assert len(multi_account_manager.accounts) == 0
        assert multi_account_manager.master_account is None
    
    @pytest.mark.asyncio
    async def test_initialize_master_account(self, multi_account_manager):
        """마스터 계좌 초기화 테스트"""
        # 환경변수 모킹
        with patch.dict(os.environ, {
            'BINANCE_API_KEY': 'test_master_key',
            'BINANCE_SECRET_KEY': 'test_master_secret'
        }):
            result = await multi_account_manager._initialize_master_account()
            
            assert result == True
            assert multi_account_manager.master_account is not None
            assert multi_account_manager.master_account.account_id == "MASTER"
            assert multi_account_manager.master_account.account_type == AccountType.MASTER
    
    @pytest.mark.asyncio
    async def test_load_sub_accounts(self, multi_account_manager):
        """서브 계좌 로드 테스트"""
        # 환경변수 모킹
        with patch.dict(os.environ, {
            'TEST_ACCOUNT_1_API_KEY': 'test_sub_key',
            'TEST_ACCOUNT_1_API_SECRET': 'test_sub_secret'
        }):
            await multi_account_manager._load_sub_accounts()
            
            assert len(multi_account_manager.accounts) == 1
            assert 'test_account_1' in multi_account_manager.accounts
            
            account = multi_account_manager.accounts['test_account_1']
            assert account.account_type == AccountType.SUB_FUTURES
            assert account.strategy == 'TFPE'
            assert account.leverage == 5
            assert account.position_size == 10.0


class TestSubAccountInfo:
    """SubAccountInfo 데이터클래스 테스트"""
    
    def test_sub_account_creation(self):
        """서브 계좌 정보 생성 테스트"""
        account = SubAccountInfo(
            account_id="test_1",
            email="test@example.com",
            account_type=AccountType.SUB_FUTURES,
            api_key="test_key",
            api_secret="test_secret"
        )
        
        assert account.account_id == "test_1"
        assert account.status == AccountStatus.INITIALIZING
        assert account.leverage == 10  # 기본값
        assert account.position_size == 24.0  # 기본값
        assert account.performance.account_id == "test_1"
    
    def test_sub_account_to_dict(self):
        """딕셔너리 변환 테스트"""
        account = SubAccountInfo(
            account_id="test_1",
            email="test@example.com",
            account_type=AccountType.SUB_FUTURES,
            api_key="test_key",
            api_secret="test_secret"
        )
        
        data = account.to_dict()
        
        assert isinstance(data, dict)
        assert data['account_id'] == "test_1"
        assert data['account_type'] == "SUB_FUTURES"
        assert data['status'] == "INITIALIZING"
        assert 'performance' in data
    
    def test_sub_account_from_dict(self):
        """딕셔너리에서 생성 테스트"""
        data = {
            'account_id': 'test_1',
            'email': 'test@example.com',
            'account_type': 'SUB_FUTURES',
            'api_key': 'test_key',
            'api_secret': 'test_secret',
            'status': 'ACTIVE',
            'leverage': 15,
            'performance': {
                'account_id': 'test_1',
                'total_trades': 10,
                'winning_trades': 6
            }
        }
        
        account = SubAccountInfo.from_dict(data)
        
        assert account.account_id == 'test_1'
        assert account.account_type == AccountType.SUB_FUTURES
        assert account.status == AccountStatus.ACTIVE
        assert account.leverage == 15
        assert account.performance.total_trades == 10


class TestAccountPerformance:
    """AccountPerformance 테스트"""
    
    def test_performance_initialization(self):
        """성과 추적 초기화 테스트"""
        perf = AccountPerformance(account_id="test_1")
        
        assert perf.account_id == "test_1"
        assert perf.total_trades == 0
        assert perf.winning_trades == 0
        assert perf.total_pnl == 0.0
        assert perf.win_rate == 0.0
    
    def test_update_statistics(self):
        """통계 업데이트 테스트"""
        perf = AccountPerformance(account_id="test_1")
        perf.total_trades = 10
        perf.winning_trades = 6
        
        perf.update_statistics()
        
        assert perf.win_rate == 60.0  # 6/10 * 100


class TestMultiAccountIntegration:
    """통합 테스트"""
    
    @pytest.mark.asyncio
    async def test_full_initialization_flow(self):
        """전체 초기화 플로우 테스트"""
        # 환경변수 설정
        with patch.dict(os.environ, {
            'BINANCE_API_KEY': 'master_key',
            'BINANCE_SECRET_KEY': 'master_secret',
            'TEST_ACCOUNT_1_API_KEY': 'sub_key',
            'TEST_ACCOUNT_1_API_SECRET': 'sub_secret'
        }):
            # Mock 설정
            mock_config = Mock(spec=ConfigManager)
            mock_config.config = {
                'multi_account': {
                    'enabled': True,
                    'sub_accounts': {
                        'test_account_1': {
                            'type': 'SUB_FUTURES',
                            'enabled': True,
                            'strategy': 'TFPE',
                            'symbols': ['BTCUSDT']
                        }
                    }
                },
                'system': {'mode': 'testnet'}
            }
            
            mock_state = Mock(spec=StateManager)
            mock_state.save_multi_account_state = AsyncMock()
            mock_state.load_multi_account_state = AsyncMock(return_value={})
            
            # BinanceAPI 모킹
            with patch('src.core.multi_account.account_manager.BinanceAPI') as mock_binance_class:
                mock_api_instance = AsyncMock()
                mock_api_instance.initialize = AsyncMock(return_value=True)
                mock_api_instance.get_account_balance = AsyncMock(return_value=1000.0)
                mock_binance_class.return_value = mock_api_instance
                
                # PositionManager 모킹
                with patch('src.core.multi_account.account_manager.PositionManager') as mock_pm_class:
                    mock_pm_instance = AsyncMock()
                    mock_pm_instance.initialize = AsyncMock(return_value=True)
                    mock_pm_instance.sync_positions = AsyncMock(return_value={'active': []})
                    mock_pm_class.return_value = mock_pm_instance
                    
                    # 테스트 실행
                    manager = MultiAccountManager(
                        config_manager=mock_config,
                        state_manager=mock_state
                    )
                    
                    result = await manager.initialize()
                    
                    assert result == True
                    assert manager._initialized == True
                    assert len(manager.api_clients) > 0
                    assert 'MASTER' in manager.api_clients


if __name__ == "__main__":
    # 테스트 실행
    pytest.main([__file__, "-v"])
