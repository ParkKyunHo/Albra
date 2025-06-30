# backtest_modules/data_fetcher.py
"""데이터 수집 및 지표 계산 모듈"""

import pandas as pd
import numpy as np
import ccxt
import pandas_ta as ta
from datetime import datetime, timedelta
import time
import os
import pickle
import hashlib


class DataFetcher:
    """데이터 수집 및 지표 계산 클래스"""
    
    def __init__(self, exchange=None, use_cache=True):
        self.exchange = exchange or ccxt.binance()
        self.df_4h = None
        self.df_15m = None
        self.use_cache = use_cache
        self.cache_dir = "cache_data"
        
        # 캐시 디렉토리 생성
        if self.use_cache and not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
    
    def calculate_donchian_channel(self, df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        """Donchian Channel 계산"""
        df['dc_upper'] = df['high'].rolling(period).max()
        df['dc_lower'] = df['low'].rolling(period).min()
        df['dc_middle'] = (df['dc_upper'] + df['dc_lower']) / 2
        
        # 추세 판단
        df['dc_trend'] = np.where(df['close'] > df['dc_middle'], 1, -1)
        
        # 가격 위치 (0~1)
        df['price_position'] = (df['close'] - df['dc_lower']) / (df['dc_upper'] - df['dc_lower'])
        df['price_position'] = df['price_position'].fillna(0.5)
        
        # 채널 폭 (변동성 지표)
        df['dc_width'] = (df['dc_upper'] - df['dc_lower']) / df['dc_middle']
        df['channel_width_pct'] = df['dc_width']  # 명확한 이름으로 복사
        
        return df
    
    def _get_cache_key(self, symbol: str, start_date: str, end_date: str, timeframe: str) -> str:
        """캐시 키 생성"""
        key_string = f"{symbol}_{start_date}_{end_date}_{timeframe}"
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _load_from_cache(self, cache_key: str) -> pd.DataFrame:
        """캐시에서 데이터 로드"""
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.pkl")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'rb') as f:
                    data = pickle.load(f)
                print(f"📦 Loaded from cache: {cache_key}")
                return data
            except Exception as e:
                print(f"⚠️ Cache load failed: {e}")
        return None
    
    def _save_to_cache(self, cache_key: str, data: pd.DataFrame):
        """데이터를 캐시에 저장"""
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.pkl")
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(data, f)
            print(f"💾 Saved to cache: {cache_key}")
        except Exception as e:
            print(f"⚠️ Cache save failed: {e}")
    
    def fetch_data(self, symbol: str = 'BTC/USDT', start_date: str = None, end_date: str = None):
        """데이터 수집 - 개선된 버전 (레이트 리밋 및 에러 처리 포함)"""
        try:
            if start_date and end_date:
                start_dt = pd.to_datetime(start_date)
                end_dt = pd.to_datetime(end_date)
                print(f"📊 Fetching data from {start_date} to {end_date}...")
            else:
                end_dt = datetime.now()
                start_dt = end_dt - timedelta(days=90)
                print(f"📊 Fetching last 3 months of data for {symbol}...")
            
            # 데이터 기간이 너무 긴 경우 경고
            days_diff = (end_dt - start_dt).days
            if days_diff > 365:
                print(f"⚠️ Warning: Fetching {days_diff} days of data. This may take a while...")
            
            # Buffer for indicators
            fetch_start = start_dt - timedelta(days=30)
            
            # 캐시 확인
            if self.use_cache:
                cache_key_4h = self._get_cache_key(symbol, start_date, end_date, '4h')
                cache_key_15m = self._get_cache_key(symbol, start_date, end_date, '15m')
                
                df_4h_cached = self._load_from_cache(cache_key_4h)
                df_15m_cached = self._load_from_cache(cache_key_15m)
                
                if df_4h_cached is not None and df_15m_cached is not None:
                    print("✅ Using cached data")
                    self.df_4h = df_4h_cached
                    self.df_15m = df_15m_cached
                    return df_4h_cached, df_15m_cached
            
            # Fetch 4H data
            print("📊 Fetching 4H data...")
            since_4h = int(fetch_start.timestamp() * 1000)
            all_4h_data = []
            retry_count = 0
            max_retries = 3
            
            while since_4h < int(end_dt.timestamp() * 1000):
                try:
                    time.sleep(0.5)  # Rate limit protection
                    ohlcv = self.exchange.fetch_ohlcv(symbol, '4h', since=since_4h, limit=1000)
                    
                    if not ohlcv:
                        break
                    
                    all_4h_data.extend(ohlcv)
                    since_4h = ohlcv[-1][0] + 1
                    retry_count = 0  # Reset retry count on success
                    
                    # Progress indicator
                    if len(all_4h_data) % 5000 == 0:
                        print(f"  Progress: {len(all_4h_data)} 4H candles fetched...")
                    
                except Exception as e:
                    retry_count += 1
                    if retry_count >= max_retries:
                        print(f"❌ Failed to fetch 4H data after {max_retries} retries: {e}")
                        break
                    print(f"⚠️ Retry {retry_count}/{max_retries} for 4H data: {e}")
                    time.sleep(2 ** retry_count)  # Exponential backoff
            
            if not all_4h_data:
                print("❌ No 4H data fetched")
                return None, None
            
            df_4h = pd.DataFrame(all_4h_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df_4h['timestamp'] = pd.to_datetime(df_4h['timestamp'], unit='ms')
            df_4h = df_4h.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
            df_4h.set_index('timestamp', inplace=True)
            
            # Fetch 15m data
            print("📊 Fetching 15m data...")
            since_15m = int(fetch_start.timestamp() * 1000)
            all_15m_data = []
            retry_count = 0
            
            while since_15m < int(end_dt.timestamp() * 1000):
                try:
                    time.sleep(0.5)  # Rate limit protection
                    ohlcv = self.exchange.fetch_ohlcv(symbol, '15m', since=since_15m, limit=1000)
                    
                    if not ohlcv:
                        break
                    
                    all_15m_data.extend(ohlcv)
                    since_15m = ohlcv[-1][0] + 1
                    retry_count = 0  # Reset retry count on success
                    
                    # Progress indicator
                    if len(all_15m_data) % 10000 == 0:
                        print(f"  Progress: {len(all_15m_data)} 15m candles fetched...")
                    
                except Exception as e:
                    retry_count += 1
                    if retry_count >= max_retries:
                        print(f"❌ Failed to fetch 15m data after {max_retries} retries: {e}")
                        break
                    print(f"⚠️ Retry {retry_count}/{max_retries} for 15m data: {e}")
                    time.sleep(2 ** retry_count)  # Exponential backoff
            
            if not all_15m_data:
                print("❌ No 15m data fetched")
                return None, None
            
            df_15m = pd.DataFrame(all_15m_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df_15m['timestamp'] = pd.to_datetime(df_15m['timestamp'], unit='ms')
            df_15m = df_15m.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
            df_15m.set_index('timestamp', inplace=True)
            
            # Filter to exact period
            df_4h = df_4h[(df_4h.index >= start_dt) & (df_4h.index <= end_dt)]
            df_15m = df_15m[(df_15m.index >= start_dt) & (df_15m.index <= end_dt)]
            
            print(f"✅ Data collection complete:")
            print(f"  📊 15m candles: {len(df_15m):,}")
            print(f"  📈 4H candles: {len(df_4h):,}")
            
            self.df_4h = df_4h
            self.df_15m = df_15m
            
            # 캐시에 저장
            if self.use_cache:
                self._save_to_cache(cache_key_4h, df_4h)
                self._save_to_cache(cache_key_15m, df_15m)
            
            return df_4h, df_15m
            
        except Exception as e:
            print(f"❌ Data fetch failed: {e}")
            import traceback
            traceback.print_exc()
            return None, None
    
    def calculate_indicators(self, df_4h: pd.DataFrame, df_15m: pd.DataFrame, params: dict):
        """지표 계산"""
        print("📊 Calculating indicators...")
        
        # 4H indicators
        df_4h = self.calculate_donchian_channel(df_4h, params['dc_period'])
        df_4h['ma50'] = ta.sma(df_4h['close'], 50)
        df_4h['ma200'] = ta.sma(df_4h['close'], 200)
        
        # 15m indicators
        print("  Calculating 15m indicators...")
        df_15m = self.calculate_donchian_channel(df_15m, params['dc_period'])
        
        # ADX/DI
        adx_data = ta.adx(df_15m['high'], df_15m['low'], df_15m['close'], length=14)
        if adx_data is not None:
            df_15m['adx'] = adx_data['ADX_14']
            df_15m['plus_di'] = adx_data['DMP_14']
            df_15m['minus_di'] = adx_data['DMN_14']
        
        # RSI
        df_15m['rsi'] = ta.rsi(df_15m['close'], length=14)
        
        # EMA
        df_15m['ema12'] = ta.ema(df_15m['close'], 12)
        df_15m['ema_distance'] = abs(df_15m['close'] - df_15m['ema12']) / df_15m['close']
        
        # ATR
        df_15m['atr'] = ta.atr(df_15m['high'], df_15m['low'], df_15m['close'], length=14)
        
        # Volume
        df_15m['volume_ma'] = df_15m['volume'].rolling(window=20).mean()
        df_15m['volume_ratio'] = df_15m['volume'] / df_15m['volume_ma']
        
        # Swing High/Low
        df_15m['swing_high'] = df_15m['high'].rolling(window=params['swing_period'], center=True).max()
        df_15m['swing_low'] = df_15m['low'].rolling(window=params['swing_period'], center=True).min()
        
        # Momentum
        lookback = params['momentum_lookback']
        df_15m['momentum'] = ((df_15m['close'] - df_15m['close'].shift(lookback)) / 
                              df_15m['close'].shift(lookback) * 100).abs()
        
        print("✅ Indicator calculation complete")
        return df_4h, df_15m
