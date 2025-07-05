# 백테스팅 시스템 사용 가이드

## 빠른 시작

### 1. 필요한 패키지 설치
```bash
pip install pandas numpy matplotlib seaborn scipy tqdm numba
```

### 2. 자연어 전략 빌더 실행
```bash
python backtest/examples/nl_strategy_example.py
```

대화형 모드에서 전략을 입력하면 자동으로 코드가 생성됩니다.

### 예시 입력:
```
Your strategy description: 20일 볼린저 밴드 하단 터치 후 RSI가 30 이하면 매수, 볼린저 상단 터치 후 RSI가 70 이상이면 매도. 손절 2%, 익절 5%, 트레일링 스톱 사용.
```

## 자연어 전략 빌더 사용법

### 지원하는 한국어/영어 패턴

#### 기술적 지표
- `"20일 이동평균"` 또는 `"20 day moving average"` → SMA(20)
- `"14일 RSI"` 또는 `"14 period RSI"` → RSI(14)
- `"MACD 12, 26"` → MACD(12, 26, 9)
- `"볼린저 밴드 20일 2표준편차"` 또는 `"Bollinger 20 2 std"` → BB(20, 2)
- `"이치모쿠"` 또는 `"Ichimoku"` → Ichimoku Cloud
- `"14일 ATR"` → ATR(14)

#### 진입 조건
- `"골든크로스에서 매수"` → MA Golden Cross
- `"데드크로스에서 매도"` → MA Death Cross
- `"RSI 30 이하에서 매수"` → RSI Oversold
- `"RSI 70 이상에서 매도"` → RSI Overbought
- `"가격이 볼린저 상단 돌파시"` → Bollinger Breakout
- `"상승추세에서"` → Uptrend (MA alignment)

#### 청산 조건
- `"손절 2%"` → 2% Stop Loss
- `"익절 5%"` → 5% Take Profit
- `"1.5 ATR 손절"` → ATR-based Stop Loss
- `"트레일링 스톱"` → Trailing Stop

#### 포지션 관리
- `"켈리 기준"` → Kelly Criterion
- `"포지션 10%"` → Fixed 10% Position
- `"리스크 2%"` → Risk-based Position Sizing

## 생성된 전략 테스트

### 1. 간단한 백테스트
```python
from backtest.core.engine import Backtest
from backtest.examples.generated_strategies.ma_crossover import CrossOver

# 백테스트 실행
backtest = Backtest(
    strategy=CrossOver(),
    symbol='BTC/USDT',
    timeframe='1h',
    initial_capital=10000,
    commission=0.001
)

# 실제 데이터로 백테스트 (데이터 소스 필요)
results = backtest.run(
    start_date='2024-01-01',
    end_date='2024-12-31'
)

print(f"총 수익률: {results['metrics']['total_return']:.2%}")
```

### 2. 전략 커스터마이징
생성된 전략 파일을 직접 수정할 수 있습니다:

```python
# backtest/examples/generated_strategies/my_strategy.py
class MyStrategy(BaseStrategy):
    def generate_signal(self, market_event: MarketEvent) -> Optional[SignalEvent]:
        # 여기에 추가 로직 구현
        pass
```

## 전략 예시

### 1. 단순 이동평균 크로스오버
```
20일 이동평균선과 50일 이동평균선의 골든크로스에서 매수, 데드크로스에서 매도. 손절 2%, 익절 5%.
```

### 2. RSI 반전 전략
```
RSI가 30 이하로 과매도 구간에 진입하면 매수, 70 이상으로 과매수 구간에 진입하면 매도. ATR의 1.5배로 손절, 3배로 익절. 켈리 기준으로 포지션 사이징.
```

### 3. 볼린저 밴드 + RSI 복합 전략
```
볼린저 밴드 하단 터치 후 RSI가 30 이하면 매수. 볼린저 밴드 상단 터치 후 RSI가 70 이상이면 매도. 손절 1.5%, 익절 4%. 3% 수익 시 트레일링 스톱 활성화.
```

### 4. 이치모쿠 + MACD 전략
```
이치모쿠 구름 위에서 MACD 골든크로스가 발생하면 매수. 가격이 구름 아래로 떨어지거나 MACD 데드크로스 시 청산. 손절 2%, 익절 10%. 일일 손실 한도 3%.
```

## 주의사항

1. **생성된 코드 검토**: 자연어 해석이 완벽하지 않을 수 있으므로 생성된 코드를 반드시 검토하세요.

2. **백테스트 한계**: 
   - 슬리피지와 수수료가 실제와 다를 수 있습니다
   - 과거 성과가 미래 수익을 보장하지 않습니다
   - Walk-forward analysis로 과최적화를 방지하세요

3. **데이터 필요**: 실제 백테스트를 위해서는 과거 가격 데이터가 필요합니다.

## 문제 해결

### ImportError 발생 시
```bash
# 프로젝트 루트에서 실행
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### 전략이 생성되지 않을 때
- 더 구체적인 설명을 사용하세요
- 지원하는 패턴 목록을 참고하세요
- 영어로 시도해보세요

## 다음 단계

1. **실제 데이터 연결**: Binance API나 CSV 파일에서 데이터 로드
2. **Walk-Forward Analysis**: 전략 최적화 및 검증
3. **포트폴리오 백테스트**: 여러 전략 조합 테스트
4. **실시간 연동**: 실제 거래 시스템과 연결

---

더 자세한 내용은 `backtest/README.md`를 참고하세요.