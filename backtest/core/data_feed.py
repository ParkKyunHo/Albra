"""
Data Feed Module

This module provides data feeding capabilities for the backtesting system,
supporting multiple data sources (Binance API, CSV files, etc.).
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterator, Optional, Dict, Any
import pandas as pd
import numpy as np
import os
import pickle
from pathlib import Path

logger = logging.getLogger(__name__)


class DataFeed(ABC):
    """
    Abstract base class for data feeds.
    
    All data sources must implement this interface to work with
    the backtesting engine.
    """
    
    def __init__(self, symbol: str, timeframe: str):
        """
        Initialize the data feed.
        
        Args:
            symbol: Trading symbol (e.g., 'BTC/USDT')
            timeframe: Data timeframe (e.g., '1h', '4h', '1d')
        """
        self.symbol = symbol
        self.timeframe = timeframe
        self._data_cache: Optional[pd.DataFrame] = None
        
    @abstractmethod
    def fetch_data(self, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """
        Fetch data for the specified date range.
        
        Args:
            start_date: Start date for data
            end_date: End date for data
            
        Returns:
            DataFrame with OHLCV data indexed by timestamp
        """
        pass
    
    def get_data_iterator(self, start_date: datetime, end_date: datetime) -> Iterator[pd.Series]:
        """
        Get an iterator that yields one bar at a time.
        
        Args:
            start_date: Start date for data
            end_date: End date for data
            
        Yields:
            Series containing OHLCV data for each timestamp
        """
        # Fetch data if not cached
        if self._data_cache is None:
            self._data_cache = self.fetch_data(start_date, end_date)
        
        # Filter by date range
        mask = (self._data_cache.index >= start_date) & (self._data_cache.index <= end_date)
        data = self._data_cache[mask]
        
        # Validate data
        if not self.validate_data(data):
            raise ValueError("Data validation failed")
        
        # Yield one row at a time
        for idx, row in data.iterrows():
            yield row
    
    def get_total_bars(self, start_date: datetime, end_date: datetime) -> int:
        """Get the total number of bars in the date range."""
        if self._data_cache is None:
            self._data_cache = self.fetch_data(start_date, end_date)
        
        mask = (self._data_cache.index >= start_date) & (self._data_cache.index <= end_date)
        return mask.sum()
    
    def validate_data(self, data: pd.DataFrame) -> bool:
        """
        Validate the integrity of the data.
        
        Args:
            data: DataFrame to validate
            
        Returns:
            True if data is valid, False otherwise
        """
        # Check required columns
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        if not all(col in data.columns for col in required_columns):
            logger.error(f"Missing required columns. Found: {data.columns.tolist()}")
            return False
        
        # Check for NaN values
        if data[required_columns].isnull().any().any():
            logger.error("Data contains NaN values")
            return False
        
        # Check for negative prices
        price_columns = ['open', 'high', 'low', 'close']
        if (data[price_columns] < 0).any().any():
            logger.error("Data contains negative prices")
            return False
        
        # Check OHLC relationships
        invalid_candles = (
            (data['high'] < data['low']) |
            (data['high'] < data['open']) |
            (data['high'] < data['close']) |
            (data['low'] > data['open']) |
            (data['low'] > data['close'])
        )
        
        if invalid_candles.any():
            logger.error(f"Found {invalid_candles.sum()} invalid candles")
            return False
        
        # Check for chronological order
        if not data.index.is_monotonic_increasing:
            logger.error("Data is not in chronological order")
            return False
        
        return True
    
    def resample_data(self, data: pd.DataFrame, target_timeframe: str) -> pd.DataFrame:
        """
        Resample data to a different timeframe.
        
        Args:
            data: Original OHLCV data
            target_timeframe: Target timeframe (e.g., '4h', '1d')
            
        Returns:
            Resampled DataFrame
        """
        ohlc_dict = {
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }
        
        return data.resample(target_timeframe).agg(ohlc_dict).dropna()


class BinanceDataFeed(DataFeed):
    """
    Data feed for Binance exchange data.
    
    This implementation fetches historical data from Binance API
    and caches it locally for performance.
    """
    
    def __init__(self, symbol: str, timeframe: str, cache_dir: str = 'cache_data'):
        """
        Initialize Binance data feed.
        
        Args:
            symbol: Trading symbol (e.g., 'BTC/USDT')
            timeframe: Data timeframe
            cache_dir: Directory for caching data
        """
        super().__init__(symbol, timeframe)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # Convert symbol format
        self.binance_symbol = symbol.replace('/', '')
        
    def fetch_data(self, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """
        Fetch data from Binance API or cache.
        
        Args:
            start_date: Start date for data
            end_date: End date for data
            
        Returns:
            DataFrame with OHLCV data
        """
        # Check cache first
        cache_file = self._get_cache_filename(start_date, end_date)
        if cache_file.exists():
            logger.info(f"Loading data from cache: {cache_file}")
            return pd.read_pickle(cache_file)
        
        # Import data fetcher (assuming it exists in the project)
        try:
            from backtest_modules.fixed.data_fetcher_fixed import DataFetcherFixed
            
            fetcher = DataFetcherFixed()
            data = fetcher.fetch_data(
                symbol=self.binance_symbol,
                timeframe=self.timeframe,
                start_date=start_date.strftime('%Y-%m-%d'),
                end_date=end_date.strftime('%Y-%m-%d')
            )
            
            # Ensure proper column names
            data.columns = data.columns.str.lower()
            
            # Save to cache
            data.to_pickle(cache_file)
            logger.info(f"Data cached to: {cache_file}")
            
            return data
            
        except ImportError:
            logger.warning("DataFetcherFixed not found, using simulated data")
            return self._generate_simulated_data(start_date, end_date)
    
    def _get_cache_filename(self, start_date: datetime, end_date: datetime) -> Path:
        """Generate cache filename based on parameters."""
        filename = (
            f"{self.binance_symbol}_{self.timeframe}_"
            f"{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.pkl"
        )
        return self.cache_dir / filename
    
    def _generate_simulated_data(self, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """Generate simulated OHLCV data for testing."""
        # Create date range
        freq_map = {
            '1m': 'T',
            '5m': '5T',
            '15m': '15T',
            '1h': 'H',
            '4h': '4H',
            '1d': 'D'
        }
        
        freq = freq_map.get(self.timeframe, 'H')
        date_range = pd.date_range(start=start_date, end=end_date, freq=freq)
        
        # Generate random walk price data
        n = len(date_range)
        returns = np.random.normal(0.0002, 0.02, n)  # 0.02% mean return, 2% volatility
        close_prices = 50000 * np.exp(np.cumsum(returns))  # Starting at 50000
        
        # Generate OHLC from close
        high_prices = close_prices * (1 + np.abs(np.random.normal(0, 0.002, n)))
        low_prices = close_prices * (1 - np.abs(np.random.normal(0, 0.002, n)))
        open_prices = np.roll(close_prices, 1)
        open_prices[0] = close_prices[0]
        
        # Generate volume
        volume = np.random.lognormal(10, 1, n)
        
        # Create DataFrame
        data = pd.DataFrame({
            'open': open_prices,
            'high': high_prices,
            'low': low_prices,
            'close': close_prices,
            'volume': volume
        }, index=date_range)
        
        return data


class CSVDataFeed(DataFeed):
    """
    Data feed for CSV file data.
    
    This implementation reads historical data from CSV files.
    """
    
    def __init__(self, symbol: str, timeframe: str, csv_path: str):
        """
        Initialize CSV data feed.
        
        Args:
            symbol: Trading symbol
            timeframe: Data timeframe
            csv_path: Path to CSV file
        """
        super().__init__(symbol, timeframe)
        self.csv_path = Path(csv_path)
        
        if not self.csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    def fetch_data(self, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """
        Load data from CSV file.
        
        Args:
            start_date: Start date for data
            end_date: End date for data
            
        Returns:
            DataFrame with OHLCV data
        """
        # Read CSV
        data = pd.read_csv(self.csv_path)
        
        # Convert timestamp column to datetime index
        timestamp_columns = ['timestamp', 'date', 'time', 'datetime']
        timestamp_col = None
        
        for col in timestamp_columns:
            if col in data.columns:
                timestamp_col = col
                break
        
        if timestamp_col is None:
            raise ValueError("No timestamp column found in CSV")
        
        data[timestamp_col] = pd.to_datetime(data[timestamp_col])
        data.set_index(timestamp_col, inplace=True)
        
        # Ensure column names are lowercase
        data.columns = data.columns.str.lower()
        
        # Filter by date range
        mask = (data.index >= start_date) & (data.index <= end_date)
        return data[mask]


class MultiDataFeed(DataFeed):
    """
    Data feed that combines multiple symbols.
    
    This is useful for strategies that trade multiple assets.
    """
    
    def __init__(self, data_feeds: Dict[str, DataFeed]):
        """
        Initialize multi-symbol data feed.
        
        Args:
            data_feeds: Dictionary of symbol -> DataFeed
        """
        # Use first symbol/timeframe for base class
        first_symbol = list(data_feeds.keys())[0]
        first_feed = data_feeds[first_symbol]
        super().__init__(first_symbol, first_feed.timeframe)
        
        self.data_feeds = data_feeds
        self.symbols = list(data_feeds.keys())
    
    def fetch_data(self, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """
        Fetch data for all symbols.
        
        Returns:
            Multi-index DataFrame with all symbols' data
        """
        all_data = {}
        
        for symbol, feed in self.data_feeds.items():
            data = feed.fetch_data(start_date, end_date)
            
            # Add symbol level to column names
            data.columns = pd.MultiIndex.from_product([[symbol], data.columns])
            all_data[symbol] = data
        
        # Combine all data
        combined = pd.concat(all_data.values(), axis=1)
        
        # Forward fill missing data
        combined.fillna(method='ffill', inplace=True)
        
        return combined