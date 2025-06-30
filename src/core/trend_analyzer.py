"""
중장기 트렌드 분석 모듈
멀티 타임프레임 분석을 통한 트렌드 강도 계산
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class TrendAnalyzer:
    """중장기 트렌드 분석기"""
    
    def __init__(self, binance_api):
        self.binance_api = binance_api
        self.lookback_days = 14  # 2주
        
        # EMA 기간
        self.ema_periods = {
            '4h': 200,
            '1h': 50,
            '15m': 20
        }
        
    async def analyze_trend(self, symbol: str) -> Dict:
        """종합적인 트렌드 분석"""
        try:
            # 각 타임프레임 데이터 수집
            df_4h = await self._get_historical_data(symbol, '4h', 60)  # 10일치
            df_1h = await self._get_historical_data(symbol, '1h', 24 * 14)  # 14일치
            df_15m = await self._get_historical_data(symbol, '15m', 96 * 7)  # 7일치
            
            # EMA 계산
            ema_200_4h = self._calculate_ema(df_4h, 200)
            ema_50_1h = self._calculate_ema(df_1h, 50)
            
            # 현재 가격
            current_price = df_15m['close'].iloc[-1]
            
            # 트렌드 점수 계산
            trend_score = self._calculate_trend_score(
                current_price, 
                ema_200_4h, 
                ema_50_1h,
                df_1h
            )
            
            # 트렌드 강도
            trend_strength = self._get_trend_strength(trend_score)
            
            # 추천 바이어스
            bias = self._get_trading_bias(trend_score)
            
            return {
                'score': trend_score,
                'strength': trend_strength,
                'bias': bias,
                'ema_200_4h': ema_200_4h,
                'ema_50_1h': ema_50_1h,
                'current_price': current_price,
                'price_vs_ema200': (current_price - ema_200_4h) / ema_200_4h * 100,
                'analysis_time': datetime.now()
            }
            
        except Exception as e:
            logger.error(f"트렌드 분석 실패 ({symbol}): {e}")
            return None
    
    async def _get_historical_data(self, symbol: str, interval: str, limit: int) -> pd.DataFrame:
        """과거 데이터 조회"""
        try:
            klines = await self.binance_api.client.get_klines(
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 
                'volume', 'close_time', 'quote_volume', 'trades',
                'taker_buy_base', 'taker_buy_quote', 'ignore'
            ])
            
            # 데이터 타입 변환
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            return df
            
        except Exception as e:
            logger.error(f"데이터 조회 실패: {e}")
            raise
    
    def _calculate_ema(self, df: pd.DataFrame, period: int) -> float:
        """EMA 계산"""
        if len(df) < period:
            return df['close'].mean()
        
        ema = df['close'].ewm(span=period, adjust=False).mean()
        return ema.iloc[-1]
    
    def _calculate_trend_score(self, price: float, ema_200_4h: float, 
                              ema_50_1h: float, df_1h: pd.DataFrame) -> float:
        """트렌드 점수 계산 (0-100)"""
        score = 50  # 기본 점수
        
        # 1. 4시간봉 200 EMA 대비 위치 (±25점)
        if price > ema_200_4h:
            distance_pct = (price - ema_200_4h) / ema_200_4h * 100
            score += min(25, distance_pct * 5)  # 최대 25점
        else:
            distance_pct = (ema_200_4h - price) / ema_200_4h * 100
            score -= min(25, distance_pct * 5)
        
        # 2. 1시간봉 50 EMA 대비 위치 (±15점)
        if price > ema_50_1h:
            score += 15
        else:
            score -= 15
        
        # 3. 14일 가격 위치 (±10점)
        high_14d = df_1h['high'].rolling(24 * 14).max().iloc[-1]
        low_14d = df_1h['low'].rolling(24 * 14).min().iloc[-1]
        
        if high_14d > low_14d:
            price_position = (price - low_14d) / (high_14d - low_14d)
            score += (price_position - 0.5) * 20
        
        # 점수 범위 제한
        return max(0, min(100, score))
    
    def _get_trend_strength(self, score: float) -> str:
        """트렌드 강도 판단"""
        if score >= 80:
            return "STRONG_UPTREND"
        elif score >= 65:
            return "UPTREND"
        elif score >= 35:
            return "NEUTRAL"
        elif score >= 20:
            return "DOWNTREND"
        else:
            return "STRONG_DOWNTREND"
    
    def _get_trading_bias(self, score: float) -> Dict[str, float]:
        """트레이딩 바이어스 계산"""
        # 기본 바이어스
        long_bias = 0.5
        short_bias = 0.5
        
        if score >= 70:  # 강한 상승
            long_bias = 0.8
            short_bias = 0.2
        elif score >= 55:  # 상승
            long_bias = 0.65
            short_bias = 0.35
        elif score <= 30:  # 강한 하락
            long_bias = 0.2
            short_bias = 0.8
        elif score <= 45:  # 하락
            long_bias = 0.35
            short_bias = 0.65
        
        return {
            'long': long_bias,
            'short': short_bias,
            'neutral': 1 - abs(long_bias - short_bias)
        }
    
    def get_parameter_adjustments(self, trend_score: float) -> Dict[str, float]:
        """트렌드에 따른 전략 파라미터 조정값"""
        adjustments = {
            'long_threshold_multiplier': 1.0,
            'short_threshold_multiplier': 1.0,
            'position_size_multiplier': 1.0,
            'stop_loss_multiplier': 1.0
        }
        
        if trend_score >= 70:  # 강한 상승 트렌드
            adjustments['long_threshold_multiplier'] = 0.85  # 롱 진입 조건 완화
            adjustments['short_threshold_multiplier'] = 1.3  # 숏 진입 조건 강화
            adjustments['position_size_multiplier'] = 1.15  # 포지션 크기 증가
            adjustments['stop_loss_multiplier'] = 1.1  # 손절 여유 증가
            
        elif trend_score <= 30:  # 강한 하락 트렌드
            adjustments['short_threshold_multiplier'] = 0.85
            adjustments['long_threshold_multiplier'] = 1.3
            adjustments['position_size_multiplier'] = 1.15
            adjustments['stop_loss_multiplier'] = 1.1
            
        elif 45 <= trend_score <= 55:  # 중립 구간
            adjustments['position_size_multiplier'] = 0.8  # 포지션 크기 축소
            adjustments['stop_loss_multiplier'] = 0.9  # 타이트한 손절
        
        return adjustments
