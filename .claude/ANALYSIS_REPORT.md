# AlbraTrading 프로젝트 분석 보고서

## 🔍 시스템 개요
- **프로젝트**: AlbraTrading - AWS EC2 24/7 자동 트레이딩 시스템
- **버전**: v2.0 (Multi-Account Edition)
- **아키텍처**: Event-Driven Architecture with State Machine
- **현재 모드**: Multi-Account Mode (Master + Sub1)

## 🛠️ 수정된 이슈

### 1. Position Status Enum 오류 ✅
**문제**: `'str' object has no attribute 'value'` 오류
**원인**: Position 객체의 status가 때로는 Enum, 때로는 string으로 저장됨
**해결**: `position_manager.py`의 `to_dict()` 메서드 수정
```python
# status가 이미 문자열인 경우와 Enum인 경우 모두 처리
if hasattr(self.status, 'value'):
    data['status'] = self.status.value
elif isinstance(self.status, str):
    data['status'] = self.status
```

### 2. 텔레그램 타이포 수정 ✅
**문제**: "잘고" → "잔고"
**위치**: `telegram_commands.py` line 1840
**수정**: 타이포 수정 완료

## 🚨 주요 이슈 분석

### 1. POSITION_SYNC_ERROR (5분마다 발생)
**원인 분석**:
1. Position sync interval: 60초
2. Reconciliation periodic interval: 300초 (5분)
3. 멀티 전략 시스템의 복합 키 구조 (`symbol_strategy`) 사용
4. 포지션 매칭 로직이 복합 키를 제대로 처리하지 못함

**해결 방안**:
- Reconciliation engine의 포지션 매칭 로직 개선 필요
- 복합 키 구조를 고려한 동기화 로직 구현

### 2. 중복 BTCUSDT 포지션 표시
**원인**: 
- 멀티 전략 시스템의 설계상 특징
- 동일 심볼에 대해 여러 전략이 독립적으로 포지션 보유 가능
- 예: "BTCUSDT_TFPE", "BTCUSDT_ZLMACD_ICHIMOKU"

**해결 방안**:
- 텔레그램 명령어에서 심볼별로 그룹화하여 표시
- 전략별 포지션을 명확히 구분하여 표시

## 📊 트레이딩 전략 분석

### 1. TFPE (Trend Following with Price Extremes)
**특징**:
- Donchian Channel (20 period) 기반
- 채널 내 가격 위치로 진입 신호 판단
- ADX > 25 필요
- 신호 임계값: 4 (높은 품질)

**리스크 관리**:
- Stop Loss: 1.5 ATR
- Take Profit: 5.0 ATR
- Leverage: 10x
- Position Size: 24%

**진입 조건**:
- 롱: 가격이 채널 하단 30% 이하 + RSI < 40
- 숏: 가격이 채널 상단 70% 이상 + RSI > 60

### 2. ZLHMA EMA Cross Strategy
**특징**:
- Zero Lag Hull MA (14) + EMA 50/200 크로스
- ADX 필터 (BTC: >25)
- 신호 강도 임계값: 2.5

**리스크 관리**:
- Stop Loss: 1.5 ATR
- Take Profit: 5.0 ATR
- Trailing Stop: 3% 수익시 활성화
- 3단계 부분 익절 (5%, 10%, 15%)

**피라미딩**:
- 3단계 피라미딩 지원
- 수익 3%, 6%, 9%에서 추가 진입

### 3. ZLMACD Ichimoku Strategy
**특징**:
- Zero Lag MACD + Ichimoku Cloud
- 최소 신호 강도: 3
- Kelly Criterion 포지션 사이징 (5-20%)
- 비트코인 1시간봉 특화

**리스크 관리**:
- Stop Loss: min(2%, 1.5 * ATR)
- Take Profit: 5.0 ATR
- 일일 손실 한도: 3%
- 연속 손실시 포지션 축소

**특별 기능**:
- 3단계 부분 익절
- 3단계 피라미딩
- 연속 손실 조정 (3회: 70%, 5회: 50%, 7회: 30%)

## 🔧 시스템 구성

### 계좌 구조
```
Master Account (TFPE + Momentum)
├── BTCUSDT (TFPE)
└── [기타 심볼들]

Sub1 Account (ZLMACD_ICHIMOKU)
└── BTCUSDT
```

### 주요 설정값
- Position Sync Interval: 60초
- Reconciliation Interval: 300초 (5분)
- MDD Protection: 활성화 (다단계)
- Smart Notification: 활성화
- Event-Driven Architecture: 활성화

## 📋 권장 사항

1. **즉시 조치 필요**:
   - Reconciliation engine의 복합 키 처리 로직 개선
   - 포지션 표시 UI 개선 (전략별 그룹화)

2. **모니터링 필요**:
   - Sub1 계좌의 ZLMACD_ICHIMOKU 전략 성과
   - Position sync 오류 빈도

3. **최적화 제안**:
   - Reconciliation interval을 60초로 단축 고려
   - 복합 키 기반 포지션 관리 시스템 문서화

## 📈 현재 상태
- 시스템: 정상 작동 중
- 오류: Position sync 관련 경고 발생 중
- 성능: 전략별 독립 실행으로 안정적

---
*생성일: 2025-06-30*
*작성자: Claude Code*