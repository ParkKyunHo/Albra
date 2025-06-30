# backtest_modules/fixed/data_fetcher_fixed.py
"""개선된 데이터 수집 및 지표 계산 모듈 - NaN 처리 및 데이터 정합성 개선"""

import pandas as pd
import numpy as np
import ccxt
import pandas_ta as ta
from datetime import datetime, timedelta
import time
import os
import pickle
import hashlib


class DataFetcherFixed:
    """개선된 데이터 수집 및 지표 계산 클래스"""
    
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
        """개선된 Donchian Channel 계산 - NaN 처리 포함"""
        # 원본 데이터 보존
        df = df.copy()
        
        # Donchian Channel 계산
        df['dc_upper'] = df['high'].rolling(period).max()
        df['dc_lower'] = df['low'].rolling(period).min()
        df['dc_middle'] = (df['dc_upper'] + df['dc_lower']) / 2
        
        # NaN 처리 - forward fill 후 backward fill
        df['dc_upper'] = df['dc_upper'].ffill().bfill()
        df['dc_lower'] = df['dc_lower'].ffill().bfill()
        df['dc_middle'] = df['dc_middle'].ffill().bfill()
        
        # 추세 판단
        df['dc_trend'] = np.where(df['close'] > df['dc_middle'], 1, -1)
        
        # 가격 위치 (0~1) - 안전한 계산
        dc_range = df['dc_upper'] - df['dc_lower']
        df['price_position'] = np.where(
            dc_range > 0,
            (df['close'] - df['dc_lower']) / dc_range,
            0.5  # 채널 폭이 0인 경우 중간값
        )
        
        # 채널 폭 (변동성 지표) - 안전한 계산
        df['dc_width'] = np.where(
            df['dc_middle'] > 0,
            (df['dc_upper'] - df['dc_lower']) / df['dc_middle'],
            0.01  # 기본값
        )
        
        # 별칭 추가 (호환성)
        df['channel_width_pct'] = df['dc_width']
        
        # 최종 NaN 체크 및 처리
        dc_columns = ['dc_upper', 'dc_lower', 'dc_middle', 'dc_trend', 
                      'price_position', 'dc_width', 'channel_width_pct']
        
        for col in dc_columns:
            if col in df.columns:
                # NaN이 있는 경우 로깅
                nan_count = df[col].isna().sum()
                if nan_count > 0:
                    print(f"⚠️ Warning: {col} has {nan_count} NaN values. Filling with defaults.")
                    
                    # 적절한 기본값으로 채우기
                    if col in ['price_position']:
                        df[col] = df[col].fillna(0.5)
                    elif col in ['dc_width', 'channel_width_pct']:
                        df[col] = df[col].fillna(0.01)
                    elif col in ['dc_trend']:
                        df[col] = df[col].fillna(0)
                    else:
                        df[col] = df[col].ffill().bfill()
        
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
        """데이터 수집 - 개선된 버전"""
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
            
            # Buffer for indicators - 더 충분히 확보
            fetch_start = start_dt - timedelta(days=60)  # 30일에서 60일로 증가
            
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
                    retry_count = 0
                    
                    if len(all_4h_data) % 5000 == 0:
                        print(f"  Progress: {len(all_4h_data)} 4H candles fetched...")
                    
                except Exception as e:
                    retry_count += 1
                    if retry_count >= max_retries:
                        print(f"❌ Failed to fetch 4H data after {max_retries} retries: {e}")
                        break
                    print(f"⚠️ Retry {retry_count}/{max_retries} for 4H data: {e}")
                    time.sleep(2 ** retry_count)
            
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
                    time.sleep(0.5)
                    ohlcv = self.exchange.fetch_ohlcv(symbol, '15m', since=since_15m, limit=1000)
                    
                    if not ohlcv:
                        break
                    
                    all_15m_data.extend(ohlcv)
                    since_15m = ohlcv[-1][0] + 1
                    retry_count = 0
                    
                    if len(all_15m_data) % 10000 == 0:
                        print(f"  Progress: {len(all_15m_data)} 15m candles fetched...")
                    
                except Exception as e:
                    retry_count += 1
                    if retry_count >= max_retries:
                        print(f"❌ Failed to fetch 15m data after {max_retries} retries: {e}")
                        break
                    print(f"⚠️ Retry {retry_count}/{max_retries} for 15m data: {e}")
                    time.sleep(2 ** retry_count)
            
            if not all_15m_data:
                print("❌ No 15m data fetched")
                return None, None
            
            df_15m = pd.DataFrame(all_15m_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df_15m['timestamp'] = pd.to_datetime(df_15m['timestamp'], unit='ms')
            df_15m = df_15m.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
            df_15m.set_index('timestamp', inplace=True)
            
            # Filter to exact period - 약간의 버퍼 유지
            buffer_start = start_dt - timedelta(days=30)
            df_4h = df_4h[(df_4h.index >= buffer_start) & (df_4h.index <= end_dt)]
            df_15m = df_15m[(df_15m.index >= buffer_start) & (df_15m.index <= end_dt)]
            
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
        """개선된 지표 계산 - NaN 처리 강화"""
        print("📊 Calculating indicators with improved NaN handling...")
        
        # 복사본으로 작업
        df_4h = df_4h.copy()
        df_15m = df_15m.copy()
        
        # 4H indicators
        print("  Calculating 4H indicators...")
        df_4h = self.calculate_donchian_channel(df_4h, params['dc_period'])
        df_4h['ma50'] = ta.sma(df_4h['close'], 50)
        df_4h['ma200'] = ta.sma(df_4h['close'], 200)
        
        # 200 EMA 추가 (시장 편향 판단용)
        df_4h['ema200'] = ta.ema(df_4h['close'], 200)
        
        # MA/EMA NaN 처리
        df_4h['ma50'] = df_4h['ma50'].ffill().bfill()
        df_4h['ma200'] = df_4h['ma200'].ffill().bfill()
        df_4h['ema200'] = df_4h['ema200'].ffill().bfill()
        
        # 시장 편향 (Market Bias) 계산
        # 1: 상승 편향 (Close > EMA200), -1: 하락 편향 (Close < EMA200)
        df_4h['market_bias'] = np.where(df_4h['close'] > df_4h['ema200'], 1, -1)
        
        # EMA200과의 거리 (%) - 추가 필터링용
        df_4h['ema200_distance'] = (df_4h['close'] - df_4h['ema200']) / df_4h['ema200'] * 100
        df_4h['ema200_distance'] = df_4h['ema200_distance'].fillna(0)
        
        # 15m indicators
        print("  Calculating 15m indicators...")
        df_15m = self.calculate_donchian_channel(df_15m, params['dc_period'])
        
        # ADX/DI
        adx_data = ta.adx(df_15m['high'], df_15m['low'], df_15m['close'], length=14)
        if adx_data is not None:
            df_15m['adx'] = adx_data['ADX_14'].fillna(20)  # 기본값 20
            df_15m['plus_di'] = adx_data['DMP_14'].fillna(0)
            df_15m['minus_di'] = adx_data['DMN_14'].fillna(0)
        else:
            print("⚠️ ADX calculation failed, using defaults")
            df_15m['adx'] = 20
            df_15m['plus_di'] = 0
            df_15m['minus_di'] = 0
        
        # RSI
        df_15m['rsi'] = ta.rsi(df_15m['close'], length=14)
        df_15m['rsi'] = df_15m['rsi'].fillna(50)  # 중립값
        
        # EMA
        df_15m['ema12'] = ta.ema(df_15m['close'], 12)
        df_15m['ema12'] = df_15m['ema12'].fillna(df_15m['close'])  # close로 대체
        df_15m['ema_distance'] = abs(df_15m['close'] - df_15m['ema12']) / df_15m['close']
        df_15m['ema_distance'] = df_15m['ema_distance'].fillna(0.01)
        
        # ATR
        df_15m['atr'] = ta.atr(df_15m['high'], df_15m['low'], df_15m['close'], length=14)
        # ATR이 NaN인 경우 High-Low의 평균으로 대체
        if df_15m['atr'].isna().any():
            default_atr = (df_15m['high'] - df_15m['low']).rolling(14).mean()
            df_15m['atr'] = df_15m['atr'].fillna(default_atr)
            df_15m['atr'] = df_15m['atr'].fillna((df_15m['high'] - df_15m['low']).mean())
        
        # Volume
        df_15m['volume_ma'] = df_15m['volume'].rolling(window=20).mean()
        df_15m['volume_ma'] = df_15m['volume_ma'].fillna(df_15m['volume'].mean())
        
        # Volume ratio 안전한 계산
        df_15m['volume_ratio'] = np.where(
            df_15m['volume_ma'] > 0,
            df_15m['volume'] / df_15m['volume_ma'],
            1.0
        )
        
        # Swing High/Low
        swing_period = params.get('swing_period', 20)
        df_15m['swing_high'] = df_15m['high'].rolling(window=swing_period, center=True).max()
        df_15m['swing_low'] = df_15m['low'].rolling(window=swing_period, center=True).min()
        
        # Swing NaN 처리
        df_15m['swing_high'] = df_15m['swing_high'].ffill().bfill()
        df_15m['swing_low'] = df_15m['swing_low'].ffill().bfill()
        
        # Momentum
        lookback = params.get('momentum_lookback', 20)
        price_change = df_15m['close'] - df_15m['close'].shift(lookback)
        price_shift = df_15m['close'].shift(lookback)
        
        df_15m['momentum'] = np.where(
            price_shift > 0,
            (price_change / price_shift * 100).abs(),
            0
        )
        df_15m['momentum'] = df_15m['momentum'].fillna(0)
        
        # 가격 가속도 (모멘텀 전략용)
        df_15m['momentum_5'] = ((df_15m['close'] - df_15m['close'].shift(5)) / 
                                df_15m['close'].shift(5) * 100).fillna(0)
        df_15m['momentum_10'] = ((df_15m['close'] - df_15m['close'].shift(10)) / 
                                 df_15m['close'].shift(10) * 100).fillna(0)
        df_15m['momentum_acceleration'] = (df_15m['momentum_5'] - df_15m['momentum_10']).fillna(0)
        
        # 최종 NaN 체크
        print("\n📊 Data quality check:")
        for col in df_4h.columns:
            nan_count = df_4h[col].isna().sum()
            if nan_count > 0:
                print(f"  4H - {col}: {nan_count} NaN values")
        
        for col in df_15m.columns:
            nan_count = df_15m[col].isna().sum()
            if nan_count > 0:
                print(f"  15m - {col}: {nan_count} NaN values")
        
        # 시작 부분의 데이터 제거 (지표 계산으로 인한 NaN)
        min_required_candles = max(50, params.get('dc_period', 20), lookback, swing_period)
        df_15m = df_15m.iloc[min_required_candles:]
        
        # 4시간봉도 정렬
        df_4h = df_4h[df_4h.index >= df_15m.index[0]]
        
        print(f"\n✅ Indicator calculation complete")
        print(f"  Final 4H candles: {len(df_4h)}")
        print(f"  Final 15m candles: {len(df_15m)}")
        
        return df_4h, df_15m
    
    def validate_data_alignment(self, df_4h: pd.DataFrame, df_15m: pd.DataFrame):
        """4시간봉과 15분봉 데이터 정합성 검증"""
        print("\n🔍 Validating data alignment...")
        
        # 시간 범위 확인
        print(f"  4H range: {df_4h.index[0]} to {df_4h.index[-1]}")
        print(f"  15m range: {df_15m.index[0]} to {df_15m.index[-1]}")
        
        # 4시간봉 시간이 15분봉에 포함되는지 확인
        misaligned = 0
        for idx in df_4h.index:
            # 4시간봉 시간에 해당하는 15분봉 찾기
            aligned_time = idx.floor('15min')
            if aligned_time not in df_15m.index:
                misaligned += 1
                if misaligned < 5:  # 처음 5개만 출력
                    print(f"  ⚠️ Misaligned 4H candle: {idx}")
        
        if misaligned > 0:
            print(f"  ⚠️ Total misaligned candles: {misaligned}/{len(df_4h)}")
        else:
            print("  ✅ All candles properly aligned")
        
        return misaligned == 0
