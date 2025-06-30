# 🚀 Multi-Strategy Quick Reference Card

## ✅ 전략 추가 체크리스트

### 1️⃣ 전략 클래스 생성
```python
from src.strategies.base_strategy import BaseStrategy

class YourStrategy(BaseStrategy):
    def __init__(self, binance_api, position_manager, config):
        super().__init__(binance_api, position_manager, config)
        self.strategy_name = "YOUR_STRATEGY"  # ⚠️ 고유한 이름!
```

### 2️⃣ 포지션 관리 메서드 (strategy_name 필수!)

#### ✅ 올바른 사용
```python
# 포지션 조회
position = self.position_manager.get_position(symbol, self.strategy_name)

# 포지션 존재 확인
exists = self.position_manager.is_position_exist(symbol, self.strategy_name)

# 포지션 추가
await self.position_manager.add_position(
    symbol=symbol,
    strategy_name=self.strategy_name  # 필수!
)

# 포지션 제거
self.position_manager.remove_position(
    symbol=symbol,
    reason="신호",
    exit_price=price,
    strategy_name=self.strategy_name  # 필수!
)

# 활성 포지션 조회
positions = self.position_manager.get_active_positions(
    strategy_name=self.strategy_name
)
```

#### ❌ 잘못된 사용
```python
# strategy_name 누락 - 경고 발생!
position = self.position_manager.get_position(symbol)  # ❌
exists = self.position_manager.is_position_exist(symbol)  # ❌
```

### 3️⃣ 전략 등록

#### strategy_factory.py
```python
from src.strategies.your_strategy import YourStrategy

STRATEGY_MAP = {
    "TFPE": TFPEStrategy,
    "YOUR_STRATEGY": YourStrategy,  # 추가!
}
```

#### config.yaml
```yaml
strategies:
  your_strategy:
    enabled: false  # 초기에는 false로!
    symbols: ["BTCUSDT"]
    leverage: 10
    position_size: 20
```

### 4️⃣ 테스트 명령어

```bash
# 단독 실행
python src/main.py --strategies YOUR_STRATEGY

# 드라이런
python src/main.py --strategies YOUR_STRATEGY --dry-run

# 검증
python src/main.py --validate
```

### 5️⃣ 로깅 패턴

```python
# 항상 전략명 포함
self.logger.info(f"[{self.strategy_name}] 진입 신호: {symbol}")
self.logger.error(f"[{self.strategy_name}] 오류: {e}")
```

## 🔍 디버깅 팁

### 포지션 키 구조
```
자동 거래: {symbol}_{strategy_name}
예: "BTCUSDT_TFPE", "ETHUSDT_ZLMACD"

수동 거래: {symbol}_MANUAL
예: "BTCUSDT_MANUAL"
```

### 일반적인 실수

1. **strategy_name 누락**
   - 증상: 포지션이 다른 전략과 충돌
   - 해결: 모든 메서드에 strategy_name 전달

2. **전략명 중복**
   - 증상: 포지션이 덮어써짐
   - 해결: 고유한 전략명 사용

3. **config 미등록**
   - 증상: 전략이 로드되지 않음
   - 해결: config.yaml에 추가

## 📋 포지션 데이터 구조

```python
@dataclass
class Position:
    symbol: str              # "BTCUSDT"
    side: str               # "LONG" or "SHORT"
    size: float             # 포지션 크기
    entry_price: float      # 진입가
    leverage: int           # 레버리지
    position_id: str        # UUID
    is_manual: bool         # False (자동)
    strategy_name: str      # "YOUR_STRATEGY" ⚠️ 필수!
    status: str             # "ACTIVE"
```

## 🚨 긴급 명령어

```bash
# 전략별 포지션 확인
텔레그램: /positions YOUR_STRATEGY

# 특정 전략만 중지
python src/main.py --strategies TFPE  # YOUR_STRATEGY 제외

# 시스템 상태
python src/main.py --status
```

---

**Remember**: strategy_name을 빼먹지 마세요! 🎯
