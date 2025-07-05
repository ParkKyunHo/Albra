"""
Data Manager
여러 데이터 소스를 통합 관리하는 모듈
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple
import yfinance as yf
import streamlit as st
from abc import ABC, abstractmethod


class DataSource(ABC):
    """Base class for data sources."""
    
    @abstractmethod
    def fetch_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        interval: str = '1d'
    ) -> pd.DataFrame:
        """Fetch historical data for a symbol."""
        pass
    
    @abstractmethod
    def get_available_symbols(self) -> List[str]:
        """Get list of available symbols."""
        pass


class DemoDataSource(DataSource):
    """Demo data source for testing."""
    
    def __init__(self):
        self.symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT']
    
    def fetch_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        interval: str = '1d'
    ) -> pd.DataFrame:
        """Generate demo OHLCV data."""
        
        # Generate date range
        dates = pd.date_range(start=start_date, end=end_date, freq='D')
        n = len(dates)
        
        # Generate realistic price movements
        np.random.seed(42)  # For reproducibility
        returns = np.random.normal(0.001, 0.02, n)  # Daily returns
        
        # Base price based on symbol
        base_prices = {
            'BTC/USDT': 45000,
            'ETH/USDT': 2500,
            'BNB/USDT': 320,
            'SOL/USDT': 100
        }
        base_price = base_prices.get(symbol, 100)
        
        # Generate price series
        prices = base_price * (1 + returns).cumprod()
        
        # Generate OHLCV data
        data = pd.DataFrame(index=dates)
        data['open'] = prices * (1 + np.random.uniform(-0.005, 0.005, n))
        data['high'] = prices * (1 + np.random.uniform(0, 0.01, n))
        data['low'] = prices * (1 + np.random.uniform(-0.01, 0, n))
        data['close'] = prices
        data['volume'] = np.random.uniform(1000000, 5000000, n)
        
        # Ensure OHLC consistency
        data['high'] = data[['open', 'high', 'close']].max(axis=1)
        data['low'] = data[['open', 'low', 'close']].min(axis=1)
        
        return data
    
    def get_available_symbols(self) -> List[str]:
        """Get list of available demo symbols."""
        return self.symbols


class YahooFinanceSource(DataSource):
    """Yahoo Finance data source."""
    
    def __init__(self):
        self.popular_symbols = [
            'BTC-USD', 'ETH-USD', 'AAPL', 'GOOGL', 'MSFT',
            'TSLA', 'AMZN', 'META', 'NVDA', 'JPM'
        ]
    
    def fetch_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        interval: str = '1d'
    ) -> pd.DataFrame:
        """Fetch data from Yahoo Finance."""
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(
                start=start_date,
                end=end_date,
                interval=interval
            )
            
            # Rename columns to lowercase
            data.columns = data.columns.str.lower()
            
            # Remove timezone info for simplicity
            data.index = data.index.tz_localize(None)
            
            return data
        except Exception as e:
            st.error(f"Failed to fetch data for {symbol}: {str(e)}")
            return pd.DataFrame()
    
    def get_available_symbols(self) -> List[str]:
        """Get list of popular symbols."""
        return self.popular_symbols


class CSVDataSource(DataSource):
    """CSV file data source."""
    
    def __init__(self, file_path: Optional[str] = None):
        self.file_path = file_path
        self.data = None
        
    def load_file(self, uploaded_file) -> bool:
        """Load data from uploaded file."""
        try:
            self.data = pd.read_csv(uploaded_file, index_col=0, parse_dates=True)
            return True
        except Exception as e:
            st.error(f"Failed to load CSV: {str(e)}")
            return False
    
    def fetch_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        interval: str = '1d'
    ) -> pd.DataFrame:
        """Fetch data from loaded CSV."""
        if self.data is None:
            return pd.DataFrame()
        
        # Filter by date range
        mask = (self.data.index >= start_date) & (self.data.index <= end_date)
        return self.data.loc[mask]
    
    def get_available_symbols(self) -> List[str]:
        """Get symbols from CSV."""
        if self.data is not None and 'symbol' in self.data.columns:
            return self.data['symbol'].unique().tolist()
        return []


class DataManager:
    """Manages multiple data sources and provides unified interface."""
    
    def __init__(self):
        self.sources = {
            'Demo Data': DemoDataSource(),
            'Yahoo Finance': YahooFinanceSource(),
            'CSV Upload': CSVDataSource()
        }
        self.cache = {}
    
    @st.cache_data(ttl=3600)  # Cache for 1 hour
    def fetch_data(
        self,
        source_name: str,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        interval: str = '1d'
    ) -> pd.DataFrame:
        """Fetch data from specified source with caching."""
        
        cache_key = f"{source_name}_{symbol}_{start_date}_{end_date}_{interval}"
        
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        source = self.sources.get(source_name)
        if source is None:
            st.error(f"Unknown data source: {source_name}")
            return pd.DataFrame()
        
        data = source.fetch_data(symbol, start_date, end_date, interval)
        
        # Cache the result
        if not data.empty:
            self.cache[cache_key] = data
        
        return data
    
    def get_available_symbols(self, source_name: str) -> List[str]:
        """Get available symbols for a data source."""
        source = self.sources.get(source_name)
        if source:
            return source.get_available_symbols()
        return []
    
    def add_csv_source(self, uploaded_file) -> bool:
        """Add CSV data source from uploaded file."""
        csv_source = self.sources.get('CSV Upload')
        if csv_source and isinstance(csv_source, CSVDataSource):
            return csv_source.load_file(uploaded_file)
        return False
    
    def calculate_indicators(self, data: pd.DataFrame, indicators: List[str]) -> pd.DataFrame:
        """Calculate technical indicators for the data."""
        df = data.copy()
        
        for indicator in indicators:
            if indicator == 'SMA_20':
                df['sma_20'] = df['close'].rolling(window=20).mean()
            elif indicator == 'SMA_50':
                df['sma_50'] = df['close'].rolling(window=50).mean()
            elif indicator == 'EMA_20':
                df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
            elif indicator == 'RSI':
                df['rsi'] = self._calculate_rsi(df['close'])
            elif indicator == 'MACD':
                df['macd'], df['macd_signal'], df['macd_hist'] = self._calculate_macd(df['close'])
            elif indicator == 'BB':
                df['bb_upper'], df['bb_middle'], df['bb_lower'] = self._calculate_bollinger_bands(df['close'])
            elif indicator == 'ATR':
                df['atr'] = self._calculate_atr(df)
        
        return df
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _calculate_macd(
        self,
        prices: pd.Series,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate MACD indicator."""
        ema_fast = prices.ewm(span=fast, adjust=False).mean()
        ema_slow = prices.ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal, adjust=False).mean()
        macd_hist = macd - macd_signal
        return macd, macd_signal, macd_hist
    
    def _calculate_bollinger_bands(
        self,
        prices: pd.Series,
        period: int = 20,
        std_dev: float = 2
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands."""
        middle = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        return upper, middle, lower
    
    def _calculate_atr(self, data: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range."""
        high_low = data['high'] - data['low']
        high_close = abs(data['high'] - data['close'].shift())
        low_close = abs(data['low'] - data['close'].shift())
        
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean()
        return atr


# Create global instance
data_manager = DataManager()