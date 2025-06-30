# ZLHMA EMA Cross 전략 배포 체크리스트

## 즉시 실행 가능 (✅ 완료)
- [x] 전략 코드 생성 완료 (`src/strategies/zlhma_ema_cross_strategy.py`)
- [x] Factory 등록 완료 (`strategy_factory.py`)
- [x] Config 설정 추가 완료 (`config.yaml`)
- [x] 백테스트 파일 백업 완료

## 테스트 단계 (현재 여기)
- [ ] 통합 테스트 실행
  ```bash
  python scripts/test_zlhma_integration.py
  ```

- [ ] 드라이런 테스트
  ```bash
  python src/main.py --strategies ZLHMA_EMA_CROSS --dry-run
  ```

## 실전 배포 단계
- [ ] config.yaml 수정
  ```yaml
  zlhma_ema_cross:
    enabled: true  # false → true
  ```

- [ ] 실전 시작
  ```bash
  python src/main.py
  ```

## 모니터링
- [ ] 로그 확인: `tail -f logs/trading_*.log | grep ZLHMA`
- [ ] 텔레그램 알림 확인
- [ ] 포지션 상태: `/status`

## 비상 대응
- 전략 중단: config.yaml에서 `enabled: false`
- 시스템 중단: `/stop` (텔레그램)
- 포지션 청산: `/close_all` (텔레그램)

---

## 현재 상황 요약

### 🟢 사용 가능
- **기존 main.py**: 현재 TFPE 전략으로 정상 운영 중
- **새 전략 추가**: ZLHMA_EMA_CROSS 전략 독립적으로 실행 가능

### 🟡 선택적
- **멀티 계좌 모드**: 준비 완료, 필요시 활성화 가능

### 권장 진행 순서
1. **드라이런 테스트** (1-2일)
2. **실전 소액 테스트** (1주)
3. **정상 운영** (검증 후)
4. **멀티 계좌** (선택적, 나중에)

---

*최종 업데이트: 2025-01-02*
