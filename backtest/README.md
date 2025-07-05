# AlbraTrading Backtesting Framework

## 개요

엔터프라이즈급 이벤트 기반 백테스팅 프레임워크입니다. 자연어로 설명한 전략을 자동으로 백테스트 가능한 코드로 변환할 수 있습니다.

## 주요 기능

### 1. 이벤트 기반 아키텍처
- 실제 거래와 동일한 이벤트 플로우 시뮬레이션
- MarketEvent → SignalEvent → OrderEvent → FillEvent
- 정확한 슬리피지 및 수수료 모델링

### 2. 자연어 전략 빌더
```python
from backtest.strategies.builder import NaturalLanguageStrategyBuilder

builder = NaturalLanguageStrategyBuilder()
description = "20일 이동평균선과 50일 이동평균선의 골든크로스에서 매수"
code, blueprint = builder.build_strategy(description)
```

### 3. 포괄적인 성과 분석
- Sharpe, Sortino, Calmar Ratio
- Maximum Drawdown 분석
- VaR, CVaR 계산
- Walk-Forward Analysis

## 빠른 시작

### 1. 자연어로 전략 생성
```bash
python backtest/examples/nl_strategy_example.py
```

### 2. 기존 전략 백테스트
```python
from backtest.core.engine import Backtest
from backtest.strategies.library.zlmacd_ichimoku import ZLMACDIchimokuStrategy

# 백테스트 실행
backtest = Backtest(
    strategy=ZLMACDIchimokuStrategy(),
    symbol='BTC/USDT',
    timeframe='1h',
    initial_capital=10000
)

results = backtest.run(
    start_date='2024-01-01',
    end_date='2024-12-31'
)

# 결과 시각화
from backtest.analysis.visualization import plot_backtest_results
plot_backtest_results(results)
```

### 3. Walk-Forward Analysis
```python
from backtest.analysis.walk_forward import WalkForwardAnalyzer

analyzer = WalkForwardAnalyzer(
    strategy_class=MyStrategy,
    symbol='BTC/USDT'
)

# 파라미터 최적화
param_grid = {
    'fast_ma': [10, 20, 30],
    'slow_ma': [50, 100, 200]
}

results = analyzer.run_analysis(
    start_date='2023-01-01',
    end_date='2024-12-31',
    param_grid=param_grid
)
```

## 전략 개발 가이드

### 1. BaseStrategy 상속
```python
from backtest.strategies.base import BaseStrategy, StrategyParameters

class MyStrategy(BaseStrategy):
    def __init__(self):
        super().__init__(StrategyParameters(
            position_size=0.1,
            stop_loss=0.02,
            take_profit=0.05
        ))
    
    @property
    def name(self) -> str:
        return "MY_STRATEGY"
    
    def generate_signal(self, market_event: MarketEvent) -> Optional[SignalEvent]:
        # 전략 로직 구현
        pass
```

### 2. 지원하는 기술적 지표
- 이동평균: SMA, EMA, WMA, HMA, ZLMA
- 모멘텀: RSI, MACD, Stochastic
- 변동성: Bollinger Bands, ATR, Keltner Channel
- 추세: ADX, Ichimoku, Parabolic SAR
- 볼륨: OBV, Volume Profile

### 3. 리스크 관리
- 고정 손절/익절
- ATR 기반 동적 손절
- 트레일링 스톱
- 부분 청산
- 켈리 기준 포지션 사이징

## 디렉토리 구조

```
backtest/
├── core/              # 핵심 엔진
├── strategies/        # 전략 프레임워크
│   ├── base.py       # BaseStrategy 클래스
│   ├── indicators.py # 기술적 지표
│   ├── builder.py    # 자연어 빌더
│   └── library/      # 구현된 전략들
├── execution/        # 주문 실행
├── risk/            # 리스크 관리
├── analysis/        # 성과 분석
└── examples/        # 예제 코드
```

## 성능 최적화 팁

1. **벡터화 연산 사용**
   ```python
   # Good
   returns = prices.pct_change()
   
   # Bad
   returns = [prices[i]/prices[i-1]-1 for i in range(1, len(prices))]
   ```

2. **캐싱 활용**
   ```python
   @lru_cache(maxsize=128)
   def calculate_indicator(data):
       # 계산 비용이 높은 지표
       pass
   ```

3. **병렬 처리**
   ```python
   # Walk-forward 분석 시 병렬 처리
   analyzer.run_analysis(n_jobs=-1)  # 모든 CPU 코어 사용
   ```

## 주의사항

- 백테스트 결과와 실거래 성과는 차이가 있을 수 있습니다
- 과최적화(Overfitting)를 피하기 위해 Walk-Forward Analysis 사용을 권장합니다
- 거래 비용(수수료, 슬리피지)을 현실적으로 설정하세요
- 시장 상황 변화를 고려하여 정기적으로 전략을 재검토하세요

## 문제 해결

### ImportError 발생 시
```bash
# 프로젝트 루트에서 실행
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### 메모리 부족 시
- 데이터 청크 크기 조정
- 불필요한 데이터 컬럼 제거
- 더 작은 기간으로 나누어 백테스트

## 라이선스

이 백테스팅 프레임워크는 AlbraTrading 프로젝트의 일부입니다.