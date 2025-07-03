"""1시간봉 데이터 수집 모듈"""

import pandas as pd
import numpy as np
import ccxt
from datetime import datetime, timedelta
import time
import os
import pickle
import hashlib


class DataFetcher1H:
    """1시간봉 데이터 수집 클래스"""
    
    def __init__(self, exchange=None, use_cache=True):
        self.exchange = exchange or ccxt.binance()
        self.use_cache = use_cache
        self.cache_dir = "cache_data_1h"
        
        # 캐시 디렉토리 생성
        if self.use_cache and not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
    
    def _get_cache_key(self, symbol: str, start_date: str, end_date: str) -> str:
        """캐시 키 생성"""
        key_string = f"{symbol}_{start_date}_{end_date}_1h"
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
                print(f"⚠️ Cache load error: {e}")
        return None
    
    def _save_to_cache(self, cache_key: str, data: pd.DataFrame):
        """데이터를 캐시에 저장"""
        try:
            cache_file = os.path.join(self.cache_dir, f"{cache_key}.pkl")
            with open(cache_file, 'wb') as f:
                pickle.dump(data, f)
            print(f"💾 Saved to cache: {cache_key}")
        except Exception as e:
            print(f"⚠️ Cache save error: {e}")
    
    def fetch_data(self, symbol: str = 'BTC/USDT', start_date: str = None, end_date: str = None):
        """1시간봉 데이터 수집"""
        try:
            if start_date and end_date:
                start_dt = pd.to_datetime(start_date)
                end_dt = pd.to_datetime(end_date)
                print(f"📊 Fetching 1H data from {start_date} to {end_date}...")
            else:
                end_dt = datetime.now()
                start_dt = end_dt - timedelta(days=90)
                print(f"📊 Fetching last 3 months of 1H data for {symbol}...")
            
            # 캐시 확인
            if self.use_cache:
                cache_key = self._get_cache_key(symbol, start_date, end_date)
                df_cached = self._load_from_cache(cache_key)
                if df_cached is not None:
                    print("✅ Using cached 1H data")
                    return df_cached, None  # 두 번째 값은 호환성을 위해 None 반환
            
            # Fetch 1H data
            print("📊 Fetching 1H data from exchange...")
            since = int(start_dt.timestamp() * 1000)
            all_data = []
            
            while since < int(end_dt.timestamp() * 1000):
                try:
                    ohlcv = self.exchange.fetch_ohlcv(
                        symbol.replace('/', ''), 
                        timeframe='1h', 
                        since=since, 
                        limit=1000
                    )
                    
                    if not ohlcv:
                        break
                    
                    all_data.extend(ohlcv)
                    since = ohlcv[-1][0] + 1
                    
                    print(f"  Fetched {len(ohlcv)} candles, total: {len(all_data)}")
                    time.sleep(0.1)  # Rate limiting
                    
                except Exception as e:
                    print(f"❌ Error fetching data: {e}")
                    time.sleep(1)
                    continue
            
            # DataFrame 생성
            df = pd.DataFrame(all_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            # 날짜 범위로 필터링
            df = df[(df.index >= start_dt) & (df.index <= end_dt)]
            
            # 중복 제거
            df = df[~df.index.duplicated(keep='first')]
            
            # 정렬
            df.sort_index(inplace=True)
            
            print(f"✅ Fetched {len(df)} 1H candles")
            print(f"  Date range: {df.index[0]} to {df.index[-1]}")
            print(f"  Price range: ${df['close'].min():.0f} - ${df['close'].max():.0f}")
            
            # 캐시 저장
            if self.use_cache:
                self._save_to_cache(cache_key, df)
            
            return df, None  # 두 번째 값은 호환성을 위해 None 반환
            
        except Exception as e:
            print(f"❌ Critical error in fetch_data: {e}")
            import traceback
            traceback.print_exc()
            return None, None