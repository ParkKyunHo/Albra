# AlbraTrading 수동/자동 거래 통합 가이드

## 🎯 Phase 3-1: Hybrid Trading Framework

AlbraTrading 시스템에 수동/자동 거래 통합 기능이 추가되었습니다. 이제 BTC를 포함한 모든 심볼에서 시스템 자동거래와 수동거래를 동시에 할 수 있습니다.

## ✨ 주요 기능

### 1. 수동/자동 거래 완전 분리
- 수동 거래와 자동 거래가 서로 간섭하지 않음
- 수동 포지션은 자동 청산 로직에서 제외
- 동일 심볼에 대한 중복 진입 방지

### 2. 개별 레버리지 및 포지션 크기 설정
- 수동 거래시 심볼별로 다른 레버리지 설정 가능
- 포지션 크기를 자유롭게 조정 가능
- 기본값: 레버리지 15x, 포지션 크기 24%

### 3. 별도 알림 채널
- 수동 거래 전용 알림 (🤚 아이콘)
- 자동 거래와 구분되는 메시지 형식
- 수동 포지션은 자동 청산되지 않음을 명시

## 📱 텔레그램 명령어

### 수동 거래 진입
```
/manual BTCUSDT long [size] [leverage]
/manual BTCUSDT short [size] [leverage]

예시:
/manual BTCUSDT long              # 기본 설정으로 롱
/manual BTCUSDT short 0.01        # 0.01 BTC 숏
/manual BTCUSDT long 0.02 10      # 0.02 BTC, 10x 레버리지
```

### 수동 거래 청산
```
/close_manual BTCUSDT [percentage]

예시:
/close_manual BTCUSDT             # 전체 청산
/close_manual BTCUSDT 50          # 50% 부분 청산
/close_manual BTCUSDT 100 익절    # 전체 청산 (익절)
```

### 수동 포지션 조회
```
/manual_positions                  # 모든 수동 포지션 목록
```

### 수동 거래 수정 (피라미딩)
```
/modify_manual BTCUSDT add 0.01    # 0.01 BTC 추가
/modify_manual BTCUSDT leverage 20 # 레버리지 변경
```

## ⚙️ 설정 (config.yaml)

```yaml
# 수동/자동 거래 통합 설정
hybrid_trading:
  enabled: true
  
  # 수동 거래 기본값
  manual_defaults:
    leverage: 15          # 기본 레버리지
    position_size: 24     # 기본 포지션 크기 (%)
    
  # 충돌 방지 설정
  conflict_prevention:
    block_auto_on_manual: true  # 수동 포지션이 있을 때 자동 거래 차단
    separate_notifications: true # 수동/자동 알림 분리
    
  # 수동 거래 추적
  tracking:
    record_manual_trades: true  # 수동 거래 기록 저장
    track_pnl: true            # 손익 추적
```

## 🔒 안전 기능

### 1. 포지션 충돌 방지
- 동일 심볼에 수동/자동 포지션 동시 보유 불가
- 수동 포지션이 있으면 해당 심볼의 자동 거래 차단

### 2. 수동 포지션 보호
- TFPE 전략이 수동 포지션을 절대 건드리지 않음
- 손절/익절은 수동으로만 가능
- MDD 강제 청산에서도 제외

### 3. 명확한 구분
- 모든 수동 거래는 `is_manual=True` 태그
- 전략명은 'MANUAL'로 표시
- 알림 메시지에 수동 거래임을 명시

## 📊 모니터링

### 웹 대시보드
- 수동/자동 포지션 구분 표시
- 실시간 손익 추적
- 포지션별 상태 모니터링

### 텔레그램 상태 리포트
- 30분마다 자동 전송되는 상태 리포트
- 수동/자동 포지션 개수 구분
- 전체 계좌 상태 요약

## ⚠️ 주의사항

1. **수동 거래 책임**: 수동 포지션은 자동으로 관리되지 않으므로 직접 모니터링 필요
2. **레버리지 설정**: 높은 레버리지는 높은 위험을 수반
3. **포지션 크기**: 계좌 잔고를 고려하여 적절한 크기로 거래
4. **부분 청산**: 리스크 관리를 위해 부분 청산 기능 활용

## 🚀 시작하기

1. 시스템이 정상 실행 중인지 확인
   ```
   /status
   ```

2. 수동 거래 시작
   ```
   /manual BTCUSDT long
   ```

3. 포지션 모니터링
   ```
   /manual_positions
   ```

4. 필요시 청산
   ```
   /close_manual BTCUSDT
   ```

## 📝 변경 내역

### 신규 파일
- `src/core/hybrid_trading_manager.py` - 수동/자동 거래 통합 관리자
- `tests/test_hybrid_trading.py` - 테스트 코드

### 수정된 파일
- `src/main.py` - HybridTradingManager 초기화 추가
- `src/utils/telegram_commands.py` - 수동 거래 명령어 구현
- `src/utils/smart_notification_manager.py` - 수동 거래 이벤트 타입 추가
- `config/config.yaml` - hybrid_trading 설정 추가

### 확인된 기능
- `src/strategies/tfpe_strategy.py` - 이미 수동 포지션 제외 로직 구현됨
- `src/core/position_manager.py` - is_manual 필드 이미 존재

## 🔧 문제 해결

### 수동 거래가 등록되지 않을 때
1. 이미 해당 심볼에 포지션이 있는지 확인
2. 계좌 잔고가 충분한지 확인
3. 심볼명이 정확한지 확인 (예: BTCUSDT)

### 청산이 되지 않을 때
1. 포지션이 수동 포지션인지 확인 (/manual_positions)
2. 심볼명이 정확한지 확인
3. 거래소 연결 상태 확인

### 알림이 오지 않을 때
1. 텔레그램 봇 설정 확인
2. /status로 시스템 상태 확인
3. 알림 우선순위 설정 확인

---

**중요**: 이 시스템은 1인용으로 설계되었습니다. 수동 거래 기능은 자동 거래를 보완하는 용도로 사용하시고, 항상 리스크 관리에 유의하시기 바랍니다.
