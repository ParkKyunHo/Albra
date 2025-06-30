# AlbraTrading 시스템 수정 사항

## 🛠️ 적용된 수정 사항 (2025-06-30)

### 1. Position Status Enum 오류 수정 ✅

**파일**: `src/core/position_manager.py`
**라인**: 66-85

**수정 전**:
```python
def to_dict(self) -> Dict:
    """딕셔너리 변환 - 개선된 버전"""
    data = asdict(self)
    # Enum 값들을 문자열로 변환
    if hasattr(self.status, 'value'):
        data['status'] = self.status.value
    if hasattr(self.source, 'value'):
        data['source'] = self.source.value
    return data
```

**수정 후**:
```python
def to_dict(self) -> Dict:
    """딕셔너리 변환 - 개선된 버전"""
    data = asdict(self)
    # Enum 값들을 문자열로 변환
    # status가 이미 문자열인 경우와 Enum인 경우 모두 처리
    if hasattr(self.status, 'value'):
        data['status'] = self.status.value
    elif isinstance(self.status, str):
        data['status'] = self.status
    else:
        data['status'] = str(self.status)
        
    # source도 동일하게 처리
    if hasattr(self.source, 'value'):
        data['source'] = self.source.value
    elif isinstance(self.source, str):
        data['source'] = self.source
    else:
        data['source'] = str(self.source)
    return data
```

**수정 이유**: Position 객체의 status 필드가 때로는 PositionStatus Enum으로, 때로는 문자열로 저장되어 있어 `'str' object has no attribute 'value'` 오류가 발생했습니다.

### 2. 텔레그램 메시지 타이포 수정 ✅

**파일**: `src/utils/telegram_commands.py`
**라인**: 1840

**수정 전**:
```python
message += f"잘고: ${master_summary.get('balance', 0):.2f}\n"
```

**수정 후**:
```python
message += f"잔고: ${master_summary.get('balance', 0):.2f}\n"
```

**수정 이유**: "잘고"는 "잔고"의 오타입니다.

## 🔍 발견된 추가 이슈

### 1. POSITION_SYNC_ERROR (5분마다 발생)

**근본 원인**:
- Position Manager는 복합 키 구조 (`symbol_strategy`) 사용
- Reconciliation Engine은 단순 심볼 기반 매칭
- 동기화 주기 불일치 (Position sync: 60초, Reconciliation: 300초)

**해결 방안**:
```python
# reconciliation_engine.py의 _get_system_positions 메서드 수정 필요
# 복합 키에서 심볼 추출하여 매칭하도록 개선
```

### 2. 중복 포지션 표시 문제

**원인**: 멀티 전략 시스템의 정상적인 동작
- 동일 심볼(BTCUSDT)에 대해 여러 전략이 독립적으로 포지션 보유
- Master 계좌: BTCUSDT_TFPE
- Sub1 계좌: BTCUSDT_ZLMACD_ICHIMOKU

**해결 방안**: UI 개선으로 전략별 포지션을 명확히 구분하여 표시

## 📝 추가 권장 수정 사항

1. **config.yaml 수정**:
   ```yaml
   # Reconciliation interval을 position sync와 동일하게 조정
   reconciliation:
     intervals:
       periodic: 60  # 300 → 60 (1분)
   ```

2. **포지션 표시 개선**:
   - 텔레그램 명령어에서 심볼별 그룹화
   - 전략 이름 명시적 표시

3. **로깅 개선**:
   - 복합 키 사용 시 더 명확한 로그 메시지
   - 동기화 오류 시 상세 정보 포함

---
*작성일: 2025-06-30*
*작성자: Claude Code*