# AlbraTrading Phase 2 실행 가이드

## 🚀 빠른 시작

### 1. Phase 2 활성화
`config/config.yaml` 파일에서 Phase 2를 활성화합니다:
```yaml
phase2:
  enabled: true  # false → true로 변경
```

### 2. 테스트 실행
모든 테스트를 실행하여 Phase 2가 올바르게 작동하는지 확인:
```bash
# Windows
test_phase2_all.bat

# 또는 개별 테스트
python test_phase2_integration.py
python verify_phase2_system.py
python monitor_phase2_performance.py
```

### 3. 시스템 시작
```bash
python src/main.py
```

## 📊 모니터링

### 텔레그램 명령어
Phase 2 상태를 실시간으로 모니터링할 수 있는 명령어:

- `/phase2_status` - Phase 2 컴포넌트 상태 확인
- `/reconcile [심볼]` - 정합성 확인 실행
- `/position_states` - 포지션 상태 머신 조회
- `/discrepancies [심볼] [개수]` - 불일치 이력 조회

### 상태 확인 예시
```
/phase2_status

🚀 Phase 2 컴포넌트 상태
🕒 업데이트: 14:23:45

📡 초기화 상태: ✅ 완료

📨 Event Bus:
├ 발행된 이벤트: 1,234개
├ 처리된 이벤트: 1,230개
├ 활성 핸들러: 12개
└ 평균 처리시간: 23.5ms

🎯 State Machine:
├ 총 포지션: 3개
├ 활성 포지션: 2개
└ 총 상태 전환: 45회

🔄 Reconciliation Engine:
├ 총 검사: 120회
├ 발견된 불일치: 5개
├ 자동 해결: 4개
└ 해결 성공률: 80.0%
```

## 🔧 설정 옵션

### Event Bus 설정
```yaml
event_bus:
  max_queue_size: 1000    # 이벤트 큐 최대 크기
  worker_count: 3         # 워커 스레드 수
  processing_timeout: 100 # 처리 타임아웃 (ms)
```

### State Machine 설정
```yaml
state_machine:
  enable_state_validation: true  # 상태 전환 검증
  max_retries: 3                # 최대 재시도 횟수
  transition_timeout: 5         # 전환 타임아웃 (초)
```

### Reconciliation Engine 설정
```yaml
reconciliation:
  check_intervals:
    fast: 60      # 1분 (활성 포지션 있을 때)
    normal: 300   # 5분
    slow: 3600    # 1시간
  enable_auto_resolution: true       # 자동 해결 활성화
  critical_discrepancy_threshold: 0.1 # 10% 차이를 심각으로 판단
```

## 🚨 문제 해결

### Phase 2가 초기화되지 않음
1. config.yaml에서 `phase2.enabled: true` 확인
2. 로그에서 초기화 오류 확인
3. 필요한 의존성 설치 확인

### 이벤트가 처리되지 않음
1. Event Bus가 시작되었는지 확인
2. 핸들러가 올바르게 등록되었는지 확인
3. 이벤트 우선순위 확인

### 정합성 확인 실패
1. 거래소 API 연결 상태 확인
2. 포지션 매니저 초기화 확인
3. 수동으로 `/reconcile` 명령 실행

## 📈 성능 고려사항

### 예상 리소스 사용량
- **메모리**: 추가 50-100MB
- **CPU**: 평균 5-10% 증가
- **스레드**: 3-5개 추가

### 최적화 팁
1. 불필요한 이벤트 발행 최소화
2. 정합성 확인 간격 조정
3. 종료된 포지션 정기적 정리

## 🔒 안전 고려사항

1. **점진적 활성화**: 먼저 테스트 환경에서 충분히 테스트
2. **모니터링**: 활성화 후 24시간 집중 모니터링
3. **백업**: 활성화 전 상태 백업
4. **롤백 계획**: 문제 발생 시 즉시 비활성화 가능

## 📞 지원

문제가 발생하면:
1. 로그 파일 확인: `logs/trading.log`
2. 텔레그램 명령어로 상태 확인
3. GitHub 이슈 생성

---

**최종 업데이트**: 2024년 12월
**버전**: Phase 2 v1.0
