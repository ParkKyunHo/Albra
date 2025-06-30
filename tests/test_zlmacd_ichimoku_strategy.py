# tests/test_zlmacd_ichimoku_strategy.py
"""
ZL MACD + Ichimoku Strategy 단위 테스트
"""

import pytest
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.strategies.zlmacd_ichimoku_strategy import ZLMACDIchimokuStrategy

class TestZLMACDIchimokuStrategy:
    """ZL MACD + Ichimoku 전략 테스트"""
    
    @pytest.fixture
    def mock_binance_api(self):
        """Mock Binance API"""
        api = Mock()
        api.get_account_balance = AsyncMock(return_value=10000.0)
        api.get_current_price = AsyncMock(return_value=50000.0)
        api.round_quantity = AsyncMock(side_effect=lambda symbol, qty: round(qty, 6))
        api.place_order = AsyncMock(return_value={
            'orderId': 12345,
            'status': 'FILLED',
            'avgPrice': 50000.0
        })
        api.get_klines = AsyncMock(return_value=pd.DataFrame())
        return api
    
    @pytest.fixture
    def mock_position_manager(self):
        """Mock Position Manager"""
        manager = Mock()
        manager.is_position_exist = Mock(return_value=False)
        manager.get_active_positions = Mock(return_value=[])
        manager.add_position = AsyncMock(return_value=Mock(symbol='BTCUSDT'))
        manager.get_position = Mock(return_value=None)
        return manager
    
    @pytest.fixture
    def strategy_config(self):
        """전략 설정"""
        return {
            'enabled': True,
            'leverage': 10,
            'position_size': 20,
            'zlmacd_fast': 12,
            'zlmacd_slow': 26,
            'zlmacd_signal': 9,
            'tenkan_period': 9,
            'kijun_period': 26,
            'senkou_b_period': 52,
            'adx_threshold': 25,
            'stop_loss_atr': 1.5,
            'take_profit_atr': 5.0,
            'symbols': ['BTCUSDT'],
            'min_signal_interval': 4
        }
    
    @pytest.fixture
    def strategy(self, mock_binance_api, mock_position_manager, strategy_config):
        """전략 인스턴스"""
        return ZLMACDIchimokuStrategy(
            mock_binance_api,
            mock_position_manager,
            strategy_config
        )
    
    def test_initialization(self, strategy):
        """초기화 테스트"""
        assert strategy.strategy_name == "ZLMACD_ICHIMOKU"
        assert strategy.timeframe == "1h"
        assert strategy.symbols == ['BTCUSDT']
        assert strategy.leverage == 10
        assert strategy.position_size == 20
        assert strategy.zlmacd_fast == 12
        assert strategy.zlmacd_slow == 26
        assert strategy.zlmacd_signal == 9
    
    def test_calculate_zlema(self, strategy):
        """Zero Lag EMA 계산 테스트"""
        # 테스트 데이터 생성
        data = pd.Series([100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110])
        
        # ZLEMA 계산
        zlema = strategy.calculate_zlema(data, 5)
        
        # ZLEMA는 일반 EMA보다 더 반응적이어야 함
        ema = data.ewm(span=5, adjust=False).mean()
        assert zlema.iloc[-1] > ema.iloc[-1]  # 상승 추세에서 ZLEMA가 더 높아야 함
    
    def test_calculate_zlmacd(self, strategy):
        """ZL MACD 계산 테스트"""
        # 테스트 데이터 생성
        np.random.seed(42)
        dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
        prices = 50000 + np.cumsum(np.random.randn(100) * 100)
        df = pd.DataFrame({
            'close': prices,
            'high': prices + np.random.rand(100) * 100,
            'low': prices - np.random.rand(100) * 100,
            'open': prices + np.random.randn(100) * 50,
            'volume': np.random.rand(100) * 1000000
        }, index=dates)
        
        # ZL MACD 계산
        result = strategy.calculate_zlmacd(df)
        
        # 필수 컬럼 확인
        assert 'zlmacd' in result.columns
        assert 'zlmacd_signal' in result.columns
        assert 'zlmacd_hist' in result.columns
        
        # NaN이 아닌 값이 있는지 확인
        assert not result['zlmacd'].iloc[-1] == np.nan
        assert not result['zlmacd_signal'].iloc[-1] == np.nan
    
    def test_calculate_ichimoku(self, strategy):
        """Ichimoku Cloud 계산 테스트"""
        # 테스트 데이터 생성
        np.random.seed(42)
        dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
        prices = 50000 + np.cumsum(np.random.randn(100) * 100)
        df = pd.DataFrame({
            'close': prices,
            'high': prices + np.abs(np.random.rand(100) * 100),
            'low': prices - np.abs(np.random.rand(100) * 100),
            'open': prices + np.random.randn(100) * 50,
            'volume': np.random.rand(100) * 1000000
        }, index=dates)
        
        # Ichimoku 계산
        result = strategy.calculate_ichimoku(df)
        
        # 필수 컬럼 확인
        required_columns = [
            'tenkan_sen', 'kijun_sen', 'senkou_span_a', 
            'senkou_span_b', 'chikou_span', 'cloud_top', 
            'cloud_bottom', 'cloud_color', 'cloud_thickness'
        ]
        for col in required_columns:
            assert col in result.columns
    
    @pytest.mark.asyncio
    async def test_check_entry_signal_long(self, strategy):
        """롱 진입 신호 테스트"""
        # 테스트 데이터 생성 - 상승 추세
        np.random.seed(42)
        dates = pd.date_range(start='2024-01-01', periods=200, freq='1h')
        base_price = 50000
        trend = np.linspace(0, 5000, 200)  # 상승 추세
        noise = np.random.randn(200) * 100
        prices = base_price + trend + noise
        
        df_1h = pd.DataFrame({
            'close': prices,
            'high': prices + np.abs(np.random.rand(200) * 100),
            'low': prices - np.abs(np.random.rand(200) * 100),
            'open': prices + np.random.randn(200) * 50,
            'volume': np.random.rand(200) * 1000000
        }, index=dates)
        
        # 지표 계산
        df_1h = strategy.calculate_zlmacd(df_1h)
        df_1h = strategy.calculate_ichimoku(df_1h)
        df_1h = strategy.calculate_adx(df_1h)
        
        # 롱 신호를 위한 조건 설정
        current_index = 199
        df_1h.loc[df_1h.index[current_index], 'zlmacd'] = 100
        df_1h.loc[df_1h.index[current_index-1], 'zlmacd'] = -100
        df_1h.loc[df_1h.index[current_index], 'zlmacd_signal'] = 0
        df_1h.loc[df_1h.index[current_index-1], 'zlmacd_signal'] = 0
        df_1h.loc[df_1h.index[current_index], 'cloud_bottom'] = 49000
        df_1h.loc[df_1h.index[current_index], 'cloud_top'] = 49500
        df_1h.loc[df_1h.index[current_index], 'tenkan_sen'] = 51000
        df_1h.loc[df_1h.index[current_index], 'kijun_sen'] = 50500
        df_1h.loc[df_1h.index[current_index], 'cloud_color'] = 1
        df_1h.loc[df_1h.index[current_index], f'ADX_{strategy.adx_period}'] = 30
        
        df_15m = pd.DataFrame()  # 더미
        
        # 진입 신호 체크
        has_signal, direction = await strategy.check_entry_signal(
            'BTCUSDT', df_1h, df_15m, current_index
        )
        
        assert has_signal == True
        assert direction == "long"
    
    @pytest.mark.asyncio
    async def test_check_exit_signal(self, strategy):
        """청산 신호 테스트"""
        # Mock 포지션
        position = Mock()
        position.symbol = 'BTCUSDT'
        position.side = 'LONG'
        position.entry_price = 50000
        
        # 테스트 데이터 생성
        np.random.seed(42)
        dates = pd.date_range(start='2024-01-01', periods=200, freq='1h')
        prices = 50000 + np.random.randn(200) * 100
        
        df_1h = pd.DataFrame({
            'close': prices,
            'high': prices + np.abs(np.random.rand(200) * 100),
            'low': prices - np.abs(np.random.rand(200) * 100),
            'open': prices + np.random.randn(200) * 50,
            'volume': np.random.rand(200) * 1000000
        }, index=dates)
        
        # 지표 계산
        df_1h = strategy.calculate_zlmacd(df_1h)
        df_1h = strategy.calculate_ichimoku(df_1h)
        
        # 청산 조건 설정 (Kijun 터치)
        current_index = 199
        df_1h.loc[df_1h.index[current_index], 'low'] = 49500
        df_1h.loc[df_1h.index[current_index], 'kijun_sen'] = 49600
        
        # 청산 신호 체크
        should_exit, exit_reason = await strategy.check_exit_signal(
            position, df_1h, current_index
        )
        
        assert should_exit == True
        assert exit_reason == "KIJUN_TOUCH"
    
    @pytest.mark.asyncio
    async def test_kelly_position_sizing(self, strategy):
        """Kelly Criterion 포지션 사이징 테스트"""
        # 테스트 거래 기록 추가
        strategy.recent_trades = [
            {'pnl': 100, 'pnl_pct': 2.0, 'direction': 'long'},
            {'pnl': -50, 'pnl_pct': -1.0, 'direction': 'short'},
            {'pnl': 75, 'pnl_pct': 1.5, 'direction': 'long'},
            {'pnl': -25, 'pnl_pct': -0.5, 'direction': 'long'},
            {'pnl': 150, 'pnl_pct': 3.0, 'direction': 'short'},
        ] * 5  # 25개 거래
        
        # Kelly 포지션 크기 계산
        quantity = await strategy.calculate_position_size_with_kelly('BTCUSDT')
        
        # 적절한 범위인지 확인
        assert quantity > 0
        assert quantity < 1.0  # 최대 1 BTC (50000 USD의 20%)
    
    @pytest.mark.asyncio
    async def test_trailing_stop(self, strategy):
        """트레일링 스톱 테스트"""
        # Mock 포지션
        position = Mock()
        position.symbol = 'BTCUSDT'
        position.side = 'LONG'
        position.entry_price = 50000
        
        # 3% 수익 상황
        current_price = 51500
        pnl_pct = 0.03
        
        # 트레일링 스톱 체크
        result = await strategy._check_trailing_stop(position, current_price, pnl_pct)
        
        # 활성화는 되지만 아직 터치하지 않음
        assert result == False
        assert 'BTCUSDT' in strategy.trailing_stops
        assert strategy.trailing_stops['BTCUSDT']['activated'] == True
        
        # 가격이 10% 하락
        current_price = 46350  # 51500 * 0.9
        result = await strategy._check_trailing_stop(position, current_price, -0.073)
        
        # 트레일링 스톱 터치
        assert result == True
    
    @pytest.mark.asyncio
    async def test_daily_loss_limit(self, strategy):
        """일일 손실 한도 테스트"""
        # 오늘 날짜
        today = datetime.now().date()
        
        # 3% 손실 설정
        strategy.daily_losses[today] = 300  # 10000의 3%
        
        # 한도 체크
        result = await strategy._check_daily_loss_limit()
        
        assert result == True
    
    def test_get_strategy_status(self, strategy):
        """전략 상태 조회 테스트"""
        # 일부 상태 설정
        strategy.consecutive_losses = 3
        strategy.recent_trades = [1, 2, 3]
        strategy.pyramiding_positions = {'BTCUSDT': [1, 2]}
        strategy.trailing_stops = {'BTCUSDT': {'activated': True}}
        
        # 상태 조회
        status = strategy.get_strategy_status()
        
        assert status['name'] == 'ZLMACD_ICHIMOKU'
        assert status['symbols'] == ['BTCUSDT']
        assert status['timeframe'] == '1h'
        assert status['consecutive_losses'] == 3
        assert status['recent_trades_count'] == 3
        assert status['active_pyramids']['BTCUSDT'] == 2
        assert 'BTCUSDT' in status['trailing_stops_active']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
