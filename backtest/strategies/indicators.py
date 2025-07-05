"""
Technical Indicators Library

This module provides a comprehensive collection of technical indicators
optimized for performance using NumPy vectorization.
"""

import numpy as np
import pandas as pd
from typing import Tuple, Optional, Union
from numba import jit
import warnings

warnings.filterwarnings('ignore', category=RuntimeWarning)


class Indicators:
    """
    Collection of technical indicators with vectorized implementations.
    
    All indicators are implemented as static methods for easy access
    and optimal performance.
    """
    
    # Moving Averages
    
    @staticmethod
    def sma(data: Union[np.ndarray, pd.Series], period: int) -> np.ndarray:
        """
        Simple Moving Average.
        
        Args:
            data: Price data
            period: Lookback period
            
        Returns:
            Array of SMA values
        """
        if isinstance(data, pd.Series):
            return data.rolling(window=period).mean().values
        
        sma = np.full_like(data, np.nan, dtype=float)
        for i in range(period - 1, len(data)):
            sma[i] = np.mean(data[i - period + 1:i + 1])
        return sma
    
    @staticmethod
    def ema(data: Union[np.ndarray, pd.Series], period: int) -> np.ndarray:
        """
        Exponential Moving Average.
        
        Args:
            data: Price data
            period: Lookback period
            
        Returns:
            Array of EMA values
        """
        if isinstance(data, pd.Series):
            return data.ewm(span=period, adjust=False).mean().values
        
        alpha = 2 / (period + 1)
        ema = np.full_like(data, np.nan, dtype=float)
        ema[0] = data[0]
        
        for i in range(1, len(data)):
            ema[i] = alpha * data[i] + (1 - alpha) * ema[i-1]
        
        return ema
    
    @staticmethod
    def wma(data: Union[np.ndarray, pd.Series], period: int) -> np.ndarray:
        """
        Weighted Moving Average.
        
        Args:
            data: Price data
            period: Lookback period
            
        Returns:
            Array of WMA values
        """
        weights = np.arange(1, period + 1)
        wma = np.full_like(data, np.nan, dtype=float)
        
        for i in range(period - 1, len(data)):
            wma[i] = np.dot(data[i - period + 1:i + 1], weights) / weights.sum()
        
        return wma
    
    @staticmethod
    def zlema(data: Union[np.ndarray, pd.Series], period: int) -> np.ndarray:
        """
        Zero Lag Exponential Moving Average.
        
        Args:
            data: Price data
            period: Lookback period
            
        Returns:
            Array of ZLEMA values
        """
        ema1 = Indicators.ema(data, period)
        ema2 = Indicators.ema(ema1, period)
        zlema = 2 * ema1 - ema2
        return zlema
    
    @staticmethod
    def hma(data: Union[np.ndarray, pd.Series], period: int) -> np.ndarray:
        """
        Hull Moving Average.
        
        Args:
            data: Price data
            period: Lookback period
            
        Returns:
            Array of HMA values
        """
        half_period = period // 2
        sqrt_period = int(np.sqrt(period))
        
        wma_half = Indicators.wma(data, half_period)
        wma_full = Indicators.wma(data, period)
        
        raw_hma = 2 * wma_half - wma_full
        hma = Indicators.wma(raw_hma, sqrt_period)
        
        return hma
    
    # Momentum Indicators
    
    @staticmethod
    def rsi(data: Union[np.ndarray, pd.Series], period: int = 14) -> np.ndarray:
        """
        Relative Strength Index.
        
        Args:
            data: Price data
            period: RSI period
            
        Returns:
            Array of RSI values
        """
        if isinstance(data, pd.Series):
            delta = data.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            return rsi.values
        
        deltas = np.diff(data)
        rsi = np.full_like(data, np.nan, dtype=float)
        
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])
        
        for i in range(period, len(data)):
            if i > period:
                avg_gain = (avg_gain * (period - 1) + gains[i-1]) / period
                avg_loss = (avg_loss * (period - 1) + losses[i-1]) / period
            
            if avg_loss != 0:
                rs = avg_gain / avg_loss
                rsi[i] = 100 - (100 / (1 + rs))
            else:
                rsi[i] = 100
        
        return rsi
    
    @staticmethod
    def macd(data: Union[np.ndarray, pd.Series], 
             fast_period: int = 12, 
             slow_period: int = 26, 
             signal_period: int = 9) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        MACD (Moving Average Convergence Divergence).
        
        Args:
            data: Price data
            fast_period: Fast EMA period
            slow_period: Slow EMA period
            signal_period: Signal line EMA period
            
        Returns:
            Tuple of (MACD line, Signal line, Histogram)
        """
        ema_fast = Indicators.ema(data, fast_period)
        ema_slow = Indicators.ema(data, slow_period)
        
        macd_line = ema_fast - ema_slow
        signal_line = Indicators.ema(macd_line, signal_period)
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    @staticmethod
    def zlmacd(data: Union[np.ndarray, pd.Series],
               fast_period: int = 12,
               slow_period: int = 26,
               signal_period: int = 9) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Zero Lag MACD.
        
        Args:
            data: Price data
            fast_period: Fast ZLEMA period
            slow_period: Slow ZLEMA period
            signal_period: Signal line EMA period
            
        Returns:
            Tuple of (ZL MACD line, Signal line, Histogram)
        """
        zlema_fast = Indicators.zlema(data, fast_period)
        zlema_slow = Indicators.zlema(data, slow_period)
        
        zlmacd_line = zlema_fast - zlema_slow
        signal_line = Indicators.ema(zlmacd_line, signal_period)
        histogram = zlmacd_line - signal_line
        
        return zlmacd_line, signal_line, histogram
    
    @staticmethod
    def stochastic(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                   k_period: int = 14, d_period: int = 3) -> Tuple[np.ndarray, np.ndarray]:
        """
        Stochastic Oscillator.
        
        Args:
            high: High prices
            low: Low prices
            close: Close prices
            k_period: %K period
            d_period: %D period
            
        Returns:
            Tuple of (%K, %D)
        """
        k = np.full_like(close, np.nan, dtype=float)
        
        for i in range(k_period - 1, len(close)):
            period_high = np.max(high[i - k_period + 1:i + 1])
            period_low = np.min(low[i - k_period + 1:i + 1])
            
            if period_high != period_low:
                k[i] = 100 * (close[i] - period_low) / (period_high - period_low)
            else:
                k[i] = 50
        
        d = Indicators.sma(k, d_period)
        
        return k, d
    
    # Volatility Indicators
    
    @staticmethod
    def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
        """
        Average True Range.
        
        Args:
            high: High prices
            low: Low prices
            close: Close prices
            period: ATR period
            
        Returns:
            Array of ATR values
        """
        tr = np.zeros_like(close)
        tr[0] = high[0] - low[0]
        
        for i in range(1, len(close)):
            hl = high[i] - low[i]
            hc = abs(high[i] - close[i-1])
            lc = abs(low[i] - close[i-1])
            tr[i] = max(hl, hc, lc)
        
        atr = Indicators.sma(tr, period)
        return atr
    
    @staticmethod
    def bollinger_bands(data: Union[np.ndarray, pd.Series], 
                       period: int = 20, 
                       std_dev: float = 2) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Bollinger Bands.
        
        Args:
            data: Price data
            period: SMA period
            std_dev: Number of standard deviations
            
        Returns:
            Tuple of (Upper band, Middle band, Lower band)
        """
        middle = Indicators.sma(data, period)
        
        if isinstance(data, pd.Series):
            std = data.rolling(window=period).std().values
        else:
            std = np.full_like(data, np.nan, dtype=float)
            for i in range(period - 1, len(data)):
                std[i] = np.std(data[i - period + 1:i + 1])
        
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        
        return upper, middle, lower
    
    # Trend Indicators
    
    @staticmethod
    def adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
        """
        Average Directional Index.
        
        Args:
            high: High prices
            low: Low prices  
            close: Close prices
            period: ADX period
            
        Returns:
            Array of ADX values
        """
        # Calculate directional movement
        up_move = high[1:] - high[:-1]
        down_move = low[:-1] - low[1:]
        
        pos_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        neg_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        # Add zero at beginning to match array length
        pos_dm = np.concatenate([[0], pos_dm])
        neg_dm = np.concatenate([[0], neg_dm])
        
        # Calculate ATR
        atr = Indicators.atr(high, low, close, period)
        
        # Calculate directional indicators
        pos_di = 100 * Indicators.sma(pos_dm, period) / atr
        neg_di = 100 * Indicators.sma(neg_dm, period) / atr
        
        # Calculate ADX
        dx = np.abs(pos_di - neg_di) / (pos_di + neg_di) * 100
        adx = Indicators.sma(dx, period)
        
        return adx
    
    @staticmethod
    def ichimoku(high: np.ndarray, low: np.ndarray,
                 tenkan_period: int = 9,
                 kijun_period: int = 26,
                 senkou_b_period: int = 52,
                 chikou_shift: int = 26,
                 cloud_shift: int = 26) -> dict:
        """
        Ichimoku Cloud indicator.
        
        Args:
            high: High prices
            low: Low prices
            tenkan_period: Tenkan-sen period
            kijun_period: Kijun-sen period
            senkou_b_period: Senkou Span B period
            chikou_shift: Chikou Span shift
            cloud_shift: Cloud forward shift
            
        Returns:
            Dictionary with Ichimoku components
        """
        def donchian_middle(high_data, low_data, period):
            middle = np.full(len(high_data), np.nan)
            for i in range(period - 1, len(high_data)):
                period_high = np.max(high_data[i - period + 1:i + 1])
                period_low = np.min(low_data[i - period + 1:i + 1])
                middle[i] = (period_high + period_low) / 2
            return middle
        
        # Calculate components
        tenkan_sen = donchian_middle(high, low, tenkan_period)
        kijun_sen = donchian_middle(high, low, kijun_period)
        
        # Senkou Span A (shifted forward)
        senkou_span_a = (tenkan_sen + kijun_sen) / 2
        senkou_span_a = np.roll(senkou_span_a, cloud_shift)
        senkou_span_a[:cloud_shift] = np.nan
        
        # Senkou Span B (shifted forward)
        senkou_span_b = donchian_middle(high, low, senkou_b_period)
        senkou_span_b = np.roll(senkou_span_b, cloud_shift)
        senkou_span_b[:cloud_shift] = np.nan
        
        # Chikou Span (shifted backward)
        chikou_span = np.roll(high, -chikou_shift)
        chikou_span[-chikou_shift:] = np.nan
        
        return {
            'tenkan_sen': tenkan_sen,
            'kijun_sen': kijun_sen,
            'senkou_span_a': senkou_span_a,
            'senkou_span_b': senkou_span_b,
            'chikou_span': chikou_span,
            'cloud_top': np.maximum(senkou_span_a, senkou_span_b),
            'cloud_bottom': np.minimum(senkou_span_a, senkou_span_b)
        }
    
    # Volume Indicators
    
    @staticmethod
    def obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
        """
        On Balance Volume.
        
        Args:
            close: Close prices
            volume: Volume data
            
        Returns:
            Array of OBV values
        """
        obv = np.zeros_like(close)
        obv[0] = volume[0]
        
        for i in range(1, len(close)):
            if close[i] > close[i-1]:
                obv[i] = obv[i-1] + volume[i]
            elif close[i] < close[i-1]:
                obv[i] = obv[i-1] - volume[i]
            else:
                obv[i] = obv[i-1]
        
        return obv
    
    @staticmethod
    def vwap(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray) -> np.ndarray:
        """
        Volume Weighted Average Price.
        
        Args:
            high: High prices
            low: Low prices
            close: Close prices
            volume: Volume data
            
        Returns:
            Array of VWAP values
        """
        typical_price = (high + low + close) / 3
        cumulative_pv = np.cumsum(typical_price * volume)
        cumulative_volume = np.cumsum(volume)
        
        vwap = cumulative_pv / cumulative_volume
        return vwap