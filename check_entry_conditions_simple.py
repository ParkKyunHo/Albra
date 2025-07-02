"""
간단한 진입 조건 함수 - 원본 코드에 복사해서 사용
"""

def check_entry_conditions_simple(self, df: pd.DataFrame, i: int) -> Tuple[bool, str]:
    """단순화된 진입 조건 체크"""
    if i < max(self.dc_period, self.momentum_lookback, 200):  # 충분한 데이터 필요
        return False, None
    
    current = df.iloc[i]
    prev = df.iloc[i-1] if i > 0 else current
    
    # 기본 필터만 적용
    
    # 1. 채널폭이 너무 좁으면 제외 (2%)
    if current['channel_width_pct'] < 0.02:
        return False, None
    
    # 2. Donchian 채널 돌파 전략
    # 상단 돌파
    if current['close'] > current['dc_upper'] * 0.99:  # 1% 여유
        return True, 'long'
    
    # 하단 돌파
    if current['close'] < current['dc_lower'] * 1.01:  # 1% 여유
        return True, 'short'
    
    # 3. 풀백 전략 (더 단순하게)
    # 상승 트렌드 + RSI 과매도
    if current['close'] > current['ema_50'] and current['rsi'] < 35:
        return True, 'long'
    
    # 하락 트렌드 + RSI 과매수
    if current['close'] < current['ema_50'] and current['rsi'] > 65:
        return True, 'short'
    
    # 4. 중간선 돌파 (추가)
    if prev['close'] < prev['dc_middle'] and current['close'] > current['dc_middle']:
        return True, 'long'
    
    if prev['close'] > prev['dc_middle'] and current['close'] < current['dc_middle']:
        return True, 'short'
    
    return False, None