# MDD 계좌 이체 문제 해결 가이드

## 문제 상황
메인 계좌에서 서브 계좌로 자산을 이동할 때 시스템이 이를 손실로 인식하여 MDD(Maximum DrawDown)가 급증하는 문제

## 원인
- MDD는 최고점 자본(Peak Capital)과 현재 잔고의 차이로 계산
- 계좌 이체 시 잔고가 급감하면 시스템이 이를 손실로 인식

## 해결 방법

### 1. 즉시 조치 - MDD 재설정

```bash
# Windows
reset_mdd.bat

# 또는 Python 직접 실행
python scripts\reset_mdd_peak.py
```

이 스크립트는:
- 현재 계좌 잔고를 조회
- Peak Capital을 현재 잔고로 재설정
- MDD를 0%로 초기화

### 2. 자동 이체 감지 (이미 적용됨)

시스템은 이제 자동으로 계좌 이체를 감지합니다:
- 5분 이내에 잔고가 20% 이상 감소하면 이체로 판단
- Peak Capital을 자동으로 조정
- 텔레그램으로 알림 전송

### 3. 설정 조정 (선택사항)

`config/config.yaml`에서 이체 감지 설정 조정 가능:

```yaml
mdd_protection:
  # 계좌 이체 감지 설정
  detect_transfers: true  # 자동 감지 활성화/비활성화
  transfer_threshold_pct: 20.0  # 감지 임계값 (%)
  transfer_time_window: 300  # 감지 시간 윈도우 (초)
```

## 향후 계좌 이체 시 권장사항

1. **이체 전 시스템 일시정지** (선택사항)
   - 대량 이체 시 시스템을 잠시 중단

2. **이체 후 확인**
   - MDD 상태 확인
   - 필요시 수동으로 재설정

3. **단계적 이체**
   - 대량 이체 시 여러 번에 나누어 이체
   - 각 이체 간 충분한 시간 간격 유지

## 테스트

이체 감지 기능 테스트:
```bash
python scripts\test_transfer_detection.py
```

## 문의사항

추가 문제가 발생하면:
1. 로그 파일 확인: `logs/` 디렉토리
2. 시스템 상태 리포트 확인 (텔레그램)
3. 필요시 수동으로 MDD 재설정
