# ZLHMA EMA Cross 전략 분석 세션 - 2025-01-03

## 작업 배경
사용자가 ZLHMA EMA Cross 전략의 백테스팅 결과가 원본(~450% 수익)과 현재 구현(-95% 손실)이 크게 다른 문제를 디버깅 중입니다.

## 원본 테스트 코드 발견
- 파일: `/home/albra/AlbraTrading/zlhma-ema.py` (79,555 bytes)
- 내용: ZLHMA 50-200 EMA Golden/Death Cross Strategy - Walk-Forward Analysis

## 핵심 발견 사항

### 1. 전략 구조
- **메인 신호**: EMA 50/200 크로스 (가중치 2)
- **보조 신호**: ZLHMA 모멘텀 (가중치 1)
- **최소 신호 강도**: 2.5 필요

### 2. 주요 파라미터
```python
# 원본 설정값
self.leverage = 8  # 레버리지 8배 (40배 아님!)
self.zlhma_period = 14  # ZLHMA 기간
self.fast_ema_period = 50  # 단기 EMA
self.slow_ema_period = 200  # 장기 EMA

# ADX 필터 (심볼별)
BTC: ADX > 25
ETH: ADX > 23
XRP: ADX > 20

# 포지션 사이징
Kelly Criterion: 5-20% (Half Kelly)
기본값: 10%
```

### 3. 진입 로직
```python
def check_entry_conditions():
    # LONG 진입 신호
    1. EMA 골든크로스 (fast > slow) - 가중치 2
    2. ZLHMA 상승 모멘텀 - 가중치 1
    3. 가격 > ZLHMA - 가중치 0.5
    4. 가격 > 두 EMA - 가중치 0.5
    
    # 총 가중치 >= 2.5이면 진입
```

### 4. 청산 로직
```python
def check_exit_conditions():
    # LONG 청산
    1. EMA 데드크로스 (주요 청산)
    2. 가격 < ZLHMA
    3. 가격 < 50 EMA * 0.98 (2% 아래)
```

### 5. 리스크 관리
```python
# 손절
- 초기: min(2%, 1.5 * ATR)
- 트레일링: 3% 수익 시 활성화, 최고점에서 10% 하락

# 연속 손실 포지션 조정
- 3회 연속: 70%로 축소
- 5회 연속: 50%로 축소
- 7회 연속: 30%로 축소

# 일일 손실 한도
- 3% 초과 시 24시간 거래 중단
```

### 6. 부분 익절 (3단계)
```python
1단계: 5% 수익 → 25% 익절
2단계: 10% 수익 → 35% 익절
3단계: 15% 수익 → 40% 익절
```

### 7. 피라미딩 (3단계)
```python
1단계: 3% 수익 시 → 원 포지션의 75%
2단계: 6% 수익 시 → 원 포지션의 50%
3단계: 9% 수익 시 → 원 포지션의 25%
```

### 8. 중요한 차이점
- **레버리지**: 8배 (40배 아님)
- **필터**: ADX 필수 사용
- **가중치 시스템**: 단순 AND 조건이 아닌 가중치 합산
- **Kelly Criterion**: 동적 포지션 사이징
- **should_take_trade()**: 항상 True 반환 (필터 없음)

## 현재 구현과의 주요 차이
1. 레버리지가 40배로 잘못 설정됨
2. 가중치 시스템 미구현
3. Kelly Criterion 미적용
4. 부분 익절/피라미딩 로직 차이

## 다음 작업
1. 원본 로직 그대로 백테스트 재구현
2. 8배 레버리지로 테스트
3. 가중치 시스템 적용
4. Kelly Criterion 포지션 사이징 구현

## 파일 목록
- `/home/albra/AlbraTrading/zlhma-ema.py` - 원본 테스트 코드
- `/home/albra/AlbraTrading/zlhma_ema_cross_1h_backtest.py` - 현재 구현 (trend filter 포함)
- `/home/albra/AlbraTrading/zlhma_ema_cross_15m_backtest.py` - 15분봉 버전
- `/home/albra/AlbraTrading/zlhma_ema_cross_15m_backtest_original.py` - 원본 로직 시도
- `/home/albra/AlbraTrading/src/strategies/zlhma_ema_cross_strategy.py` - 실제 전략 코드