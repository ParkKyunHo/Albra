# 🎯 AlbraTrading 프로젝트 개발 지침

## 📋 개요
본 문서는 AlbraTrading 시스템 개발 시 준수해야 할 지침과 가이드라인을 제공합니다.

---

## 🔧 새로운 전략 추가 가이드

### 1. 전략 클래스 구현
새로운 전략을 추가할 때는 반드시 `BaseStrategy`를 상속받아 구현해야 합니다.

```python
from src.strategies.base_strategy import BaseStrategy

class NewStrategy(BaseStrategy):
    def __init__(self, binance_api, position_manager, config):
        super().__init__(binance_api, position_manager, config)
        self.strategy_name = "NEW_STRATEGY"  # 반드시 고유한 전략명 설정
```

### 2. Multi-Strategy Position Management 고려사항

#### 2.1 포지션 관리 메서드 호출
모든 포지션 관련 메서드 호출 시 반드시 `strategy_name` 파라미터를 전달해야 합니다:

```python
# ✅ 올바른 사용
position = self.position_manager.get_position(symbol, self.strategy_name)
exists = self.position_manager.is_position_exist(symbol, self.strategy_name)

# ❌ 잘못된 사용 (경고 발생)
position = self.position_manager.get_position(symbol)
```

#### 2.2 포지션 생성
```python
await self.position_manager.add_position(
    symbol=symbol,
    side=signal.side,
    entry_price=entry_price,
    size=position_size,
    leverage=self.leverage,
    stop_loss=stop_loss,
    take_profit=take_profit,
    strategy_name=self.strategy_name  # 필수!
)
```

#### 2.3 포지션 제거
```python
self.position_manager.remove_position(
    symbol=symbol,
    reason="목표가 도달",
    exit_price=current_price,
    strategy_name=self.strategy_name  # 필수!
)
```

### 3. 전략 등록 프로세스

#### 3.1 strategy_factory.py에 등록
```python
# src/strategies/strategy_factory.py
from src.strategies.new_strategy import NewStrategy

STRATEGY_MAP = {
    "TFPE": TFPEStrategy,
    "NEW_STRATEGY": NewStrategy,  # 새 전략 추가
    # ...
}
```

#### 3.2 config.yaml에 설정 추가
```yaml
strategies:
  new_strategy:
    enabled: false  # 초기에는 비활성화로 시작
    symbols: ["BTCUSDT"]
    leverage: 10
    position_size: 20
    # 전략별 특수 설정...
```

### 4. 테스트 시나리오

#### 4.1 단독 실행 테스트
```bash
# 새 전략만 실행
python src/main.py --strategies NEW_STRATEGY
```

#### 4.2 다중 전략 동시 실행 테스트
```bash
# 기존 전략과 함께 실행
python src/main.py --strategies TFPE,NEW_STRATEGY
```

#### 4.3 동일 심볼 포지션 테스트
- 동일한 심볼(예: BTCUSDT)에 대해 여러 전략이 독립적으로 포지션을 생성할 수 있는지 확인
- 각 전략의 포지션이 서로 간섭하지 않는지 확인

### 5. 주의사항

#### 5.1 전략명 충돌 방지
- 전략명은 시스템 전체에서 고유해야 함
- 기존 전략명과 중복되지 않도록 주의
- 대문자와 언더스코어 사용 권장 (예: NEW_STRATEGY_V2)

#### 5.2 포지션 동기화
- 거래소 포지션과의 매칭은 완벽하지 않을 수 있음
- 첫 실행 시 기존 포지션의 전략 할당을 수동으로 확인 필요

#### 5.3 리스크 관리
- 각 전략은 독립적인 리스크 관리 로직을 가져야 함
- 전체 계정 레벨의 리스크는 position_manager에서 통합 관리

---

## 📊 포지션 데이터 구조

### 1. 포지션 키 구조
```python
# 자동 거래 포지션
position_key = f"{symbol}_{strategy_name}"
# 예: "BTCUSDT_TFPE", "ETHUSDT_ZLMACD"

# 수동 거래 포지션
manual_key = f"{symbol}_MANUAL"
# 예: "BTCUSDT_MANUAL"
```

### 2. 포지션 객체 구조
```python
@dataclass
class Position:
    symbol: str              # 거래 심볼
    side: str               # LONG/SHORT
    size: float             # 포지션 크기
    entry_price: float      # 진입가
    leverage: int           # 레버리지
    position_id: str        # 고유 ID
    is_manual: bool         # 수동 거래 여부
    strategy_name: str      # 전략 이름 (필수)
    status: str             # ACTIVE/CLOSED/MODIFIED
    # ... 기타 필드
```

---

## 🔄 마이그레이션 가이드

### 기존 포지션 마이그레이션
시스템 첫 실행 시 기존 포지션이 자동으로 새 구조로 변환됩니다:

1. 기존 단순 키(symbol)는 복합 키(symbol_strategy)로 변환
2. strategy_name이 없는 포지션은 현재 활성 전략 중 첫 번째로 할당
3. 마이그레이션 로그는 `logs/migration.log`에 기록

### 수동 마이그레이션 필요 시
```python
# 텔레그램 명령
/migrate_positions  # 포지션 구조 마이그레이션 실행
```

---

## 💡 베스트 프랙티스

### 1. 전략 독립성 유지
- 각 전략은 다른 전략의 포지션에 접근하거나 수정하지 않음
- 전략 간 통신이 필요한 경우 이벤트 버스 사용

### 2. 로깅 규칙
```python
# 전략명을 항상 로그에 포함
self.logger.info(f"[{self.strategy_name}] 포지션 진입: {symbol}")
```

### 3. 에러 처리
```python
try:
    position = self.position_manager.get_position(symbol, self.strategy_name)
    if not position:
        self.logger.warning(f"[{self.strategy_name}] {symbol} 포지션 없음")
        return
except Exception as e:
    self.logger.error(f"[{self.strategy_name}] 포지션 조회 실패: {e}")
```

---

## 🚀 배포 체크리스트

### 새 전략 배포 시
- [ ] 백테스트 완료 및 결과 검증
- [ ] config.yaml에서 `enabled: false`로 설정
- [ ] 테스트넷에서 24시간 이상 테스트
- [ ] 포지션 관리 메서드에 strategy_name 전달 확인
- [ ] 기존 전략과의 심볼 충돌 확인
- [ ] 리스크 파라미터 검증
- [ ] 로깅 및 알림 설정 확인
- [ ] 롤백 계획 수립

---

## 📞 문제 해결

### 포지션 충돌 문제
```bash
# 포지션 상태 확인
python src/main.py --status

# 특정 전략의 포지션만 확인
텔레그램: /positions NEW_STRATEGY
```

### 전략 격리 실행
```bash
# 문제가 있는 전략만 격리하여 실행
python src/main.py --strategies NEW_STRATEGY --dry-run
```

---

이 문서는 AlbraTrading 시스템에 새로운 전략을 추가할 때 참고해야 할 핵심 가이드라인입니다.
Multi-Strategy Position Management 시스템을 올바르게 활용하여 안정적인 멀티 전략 운영을 보장하세요.
