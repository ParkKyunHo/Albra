"""
Hybrid Trading Manager Tests
수동/자동 거래 통합 테스트
"""

import asyncio
import pytest
from datetime import datetime
from typing import Dict

from src.core.hybrid_trading_manager import HybridTradingManager
# Position 클래스를 import하지 않고 MockPosition 사용
# from src.core.position_manager import Position


class MockPosition:
    """테스트용 Position Mock - 실제 Position 클래스와 동일한 인터페이스"""
    def __init__(self, position_id: str, symbol: str, side: str, 
                 entry_price: float, size: float, leverage: int,
                 strategy_name: str = 'MANUAL', is_manual: bool = True,
                 created_at=None, last_updated=None, initial_size=None, 
                 status='ACTIVE', stop_loss=None, take_profit=None, **kwargs):
        self.position_id = position_id
        self.symbol = symbol
        self.side = side
        self.entry_price = entry_price
        self.size = size
        self.leverage = leverage
        self.strategy_name = strategy_name
        self.is_manual = is_manual
        self.created_at = created_at or datetime.now().isoformat()
        self.last_updated = last_updated or datetime.now().isoformat()
        self.initial_size = initial_size or size
        self.status = status
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        
        # 추가 속성들 (Position 클래스와 동일)
        self.source = kwargs.get('source', 'AUTO' if not is_manual else 'MANUAL')
        self.partial_closes = kwargs.get('partial_closes', 0)
        self.total_pnl = kwargs.get('total_pnl', 0.0)
        self.fees_paid = kwargs.get('fees_paid', 0.0)
        self.avg_entry_price = kwargs.get('avg_entry_price', entry_price)
        self.notes = kwargs.get('notes', '')
        self.tags = kwargs.get('tags', [])
        self.unrealized_pnl = 0
        self.realized_pnl = 0
    
    def to_dict(self):
        """딕셔너리 변환"""
        return {
            'position_id': self.position_id,
            'symbol': self.symbol,
            'side': self.side,
            'entry_price': self.entry_price,
            'size': self.size,
            'leverage': self.leverage,
            'strategy_name': self.strategy_name,
            'is_manual': self.is_manual,
            'created_at': self.created_at,
            'last_updated': self.last_updated,
            'initial_size': self.initial_size,
            'status': self.status,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'source': self.source,
            'partial_closes': self.partial_closes,
            'total_pnl': self.total_pnl,
            'unrealized_pnl': self.unrealized_pnl,
            'realized_pnl': self.realized_pnl
        }


class MockBinanceAPI:
    """Mock Binance API for testing"""
    
    async def get_current_price(self, symbol: str) -> float:
        """Mock current price"""
        prices = {
            'BTCUSDT': 50000.0,
            'ETHUSDT': 3000.0,
            'BNBUSDT': 400.0
        }
        return prices.get(symbol, 100.0)
    
    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Mock leverage setting"""
        return True
    
    async def get_account_balance(self) -> float:
        """Mock account balance"""
        return 10000.0


class MockPositionManager:
    """Mock Position Manager for testing"""
    
    def __init__(self):
        self.positions = {}
        self.config = {'leverage': 15, 'position_size': 24}
    
    def get_position(self, symbol: str):
        """Get position by symbol"""
        return self.positions.get(symbol)
    
    def is_position_exist(self, symbol: str) -> bool:
        """Check if position exists"""
        return symbol in self.positions
    
    async def register_position(self, **kwargs) -> MockPosition:
        """Register new position - MockPosition 사용"""
        # MockPosition 생성 (모든 필수 파라미터 포함)
        position = MockPosition(
            position_id=f"pos_{kwargs['symbol']}_{datetime.now().timestamp()}",
            symbol=kwargs['symbol'],
            side=kwargs.get('side', 'LONG'),  # 기본값 추가
            entry_price=kwargs.get('entry_price', 50000),
            size=kwargs.get('size', 0.01),
            leverage=kwargs.get('leverage', 15),
            strategy_name=kwargs.get('strategy_name', 'MANUAL'),
            is_manual=kwargs.get('is_manual', True),
            created_at=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat(),
            initial_size=kwargs.get('size', 0.01),
            status='ACTIVE'
        )
        self.positions[kwargs['symbol']] = position
        return position
    
    async def close_position(self, symbol: str, reason: str, force: bool = False) -> bool:
        """Close position"""
        if symbol in self.positions:
            del self.positions[symbol]
            return True
        return False
    
    async def partial_close_position(self, symbol: str, close_size: float, reason: str) -> bool:
        """Partial close position"""
        if symbol in self.positions:
            self.positions[symbol].size -= close_size
            return True
        return False


class MockNotificationManager:
    """Mock Notification Manager for testing"""
    
    def __init__(self):
        self.sent_alerts = []
    
    async def send_alert(self, event_type: str, title: str, message: str, 
                        priority: str = 'MEDIUM'):
        """Record sent alerts"""
        self.sent_alerts.append({
            'event_type': event_type,
            'title': title,
            'message': message,
            'priority': priority,
            'timestamp': datetime.now()
        })


@pytest.mark.asyncio
async def test_hybrid_trading_manager_initialization():
    """Test HybridTradingManager initialization"""
    position_manager = MockPositionManager()
    binance_api = MockBinanceAPI()
    notification_manager = MockNotificationManager()
    
    manager = HybridTradingManager(position_manager, binance_api, notification_manager)
    
    assert manager.position_manager == position_manager
    assert manager.binance_api == binance_api
    assert manager.notification_manager == notification_manager
    assert len(manager.manual_trades) == 0
    assert len(manager.manual_leverage_override) == 0


@pytest.mark.asyncio
async def test_register_manual_trade_success():
    """Test successful manual trade registration"""
    position_manager = MockPositionManager()
    binance_api = MockBinanceAPI()
    notification_manager = MockNotificationManager()
    
    manager = HybridTradingManager(position_manager, binance_api, notification_manager)
    
    # Register manual trade
    success, message = await manager.register_manual_trade(
        symbol='BTCUSDT',
        side='long',
        size=0.01,
        leverage=10,
        comment='Test manual trade'
    )
    
    assert success is True
    assert 'BTCUSDT' in manager.manual_trades
    assert 'BTCUSDT' in position_manager.positions
    assert position_manager.positions['BTCUSDT'].is_manual is True
    assert len(notification_manager.sent_alerts) == 1
    assert notification_manager.sent_alerts[0]['event_type'] == 'MANUAL_TRADE'


@pytest.mark.asyncio
async def test_register_manual_trade_with_existing_position():
    """Test manual trade registration with existing position"""
    position_manager = MockPositionManager()
    binance_api = MockBinanceAPI()
    notification_manager = MockNotificationManager()
    
    # Create existing position
    await position_manager.register_position(
        symbol='BTCUSDT',
        side='LONG',
        is_manual=False,
        strategy_name='TFPE'
    )
    
    manager = HybridTradingManager(position_manager, binance_api, notification_manager)
    
    # Try to register manual trade
    success, message = await manager.register_manual_trade(
        symbol='BTCUSDT',
        side='long'
    )
    
    assert success is False
    assert "자동 거래 포지션이 있습니다" in message


@pytest.mark.asyncio
async def test_close_manual_trade_full():
    """Test full manual trade closure"""
    position_manager = MockPositionManager()
    binance_api = MockBinanceAPI()
    notification_manager = MockNotificationManager()
    
    manager = HybridTradingManager(position_manager, binance_api, notification_manager)
    
    # Register manual trade first
    await manager.register_manual_trade(
        symbol='BTCUSDT',
        side='long'
    )
    
    # Close manual trade
    success, message = await manager.close_manual_trade(
        symbol='BTCUSDT',
        percentage=100,
        comment='Test close'
    )
    
    assert success is True
    assert 'BTCUSDT' not in manager.manual_trades
    assert 'BTCUSDT' not in position_manager.positions


@pytest.mark.asyncio
async def test_close_manual_trade_partial():
    """Test partial manual trade closure"""
    position_manager = MockPositionManager()
    binance_api = MockBinanceAPI()
    notification_manager = MockNotificationManager()
    
    manager = HybridTradingManager(position_manager, binance_api, notification_manager)
    
    # Register manual trade
    await manager.register_manual_trade(
        symbol='BTCUSDT',
        side='long',
        size=0.02
    )
    
    original_size = position_manager.positions['BTCUSDT'].size
    
    # Partial close
    success, message = await manager.close_manual_trade(
        symbol='BTCUSDT',
        percentage=50,
        comment='Partial close'
    )
    
    assert success is True
    assert 'BTCUSDT' in manager.manual_trades  # Still active
    assert position_manager.positions['BTCUSDT'].size < original_size


@pytest.mark.asyncio
async def test_close_auto_position_fails():
    """Test that closing auto position fails"""
    position_manager = MockPositionManager()
    binance_api = MockBinanceAPI()
    notification_manager = MockNotificationManager()
    
    # Create auto position
    await position_manager.register_position(
        symbol='BTCUSDT',
        side='LONG',
        is_manual=False,
        strategy_name='TFPE'
    )
    
    manager = HybridTradingManager(position_manager, binance_api, notification_manager)
    
    # Try to close as manual
    success, message = await manager.close_manual_trade(
        symbol='BTCUSDT',
        comment='Try close auto'
    )
    
    assert success is False
    assert "자동 거래 포지션입니다" in message


@pytest.mark.asyncio
async def test_leverage_override():
    """Test leverage override functionality"""
    position_manager = MockPositionManager()
    binance_api = MockBinanceAPI()
    notification_manager = MockNotificationManager()
    
    manager = HybridTradingManager(position_manager, binance_api, notification_manager)
    
    # Register with custom leverage
    await manager.register_manual_trade(
        symbol='BTCUSDT',
        side='long',
        leverage=20
    )
    
    assert manager.get_leverage_override('BTCUSDT') == 20
    assert position_manager.positions['BTCUSDT'].leverage == 20


@pytest.mark.asyncio
async def test_get_manual_positions():
    """Test getting manual positions list"""
    position_manager = MockPositionManager()
    binance_api = MockBinanceAPI()
    notification_manager = MockNotificationManager()
    
    manager = HybridTradingManager(position_manager, binance_api, notification_manager)
    
    # Register multiple trades
    await manager.register_manual_trade('BTCUSDT', 'long')
    await manager.register_manual_trade('ETHUSDT', 'short')
    
    manual_positions = manager.get_manual_positions()
    
    assert len(manual_positions) == 2
    assert any(p['symbol'] == 'BTCUSDT' for p in manual_positions)
    assert any(p['symbol'] == 'ETHUSDT' for p in manual_positions)


@pytest.mark.asyncio
async def test_is_manual_trade():
    """Test manual trade detection"""
    position_manager = MockPositionManager()
    binance_api = MockBinanceAPI()
    notification_manager = MockNotificationManager()
    
    manager = HybridTradingManager(position_manager, binance_api, notification_manager)
    
    # Register manual trade
    await manager.register_manual_trade('BTCUSDT', 'long')
    
    assert manager.is_manual_trade('BTCUSDT') is True
    assert manager.is_manual_trade('ETHUSDT') is False


if __name__ == '__main__':
    # Run tests
    asyncio.run(test_hybrid_trading_manager_initialization())
    asyncio.run(test_register_manual_trade_success())
    asyncio.run(test_register_manual_trade_with_existing_position())
    asyncio.run(test_close_manual_trade_full())
    asyncio.run(test_close_manual_trade_partial())
    asyncio.run(test_close_auto_position_fails())
    asyncio.run(test_leverage_override())
    asyncio.run(test_get_manual_positions())
    asyncio.run(test_is_manual_trade())
    
    print("✅ All tests passed!")
