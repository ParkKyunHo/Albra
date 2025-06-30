# AlbraTrading 배포 운영 가이드
## ZLHMA EMA Cross 전략 통합 및 멀티 계좌 운영 가이드

작성일: 2025-01-02
버전: 2.0 (멀티모드 지원 추가)

---

## 📋 현재 상태 요약

1. **전략 통합 완료**
   - ✅ `zlhma_ema_cross_strategy.py` BaseStrategy 통합 버전 생성
   - ✅ `strategy_factory.py` 전략 등록 완료
   - ✅ `config.yaml` 설정 추가 완료
   - ✅ 백테스트 파일 백업 완료

2. **멀티 계좌 시스템 완료**
   - ✅ `main_multi_account.py` 단일/멀티 모드 통합
   - ✅ Systemd 멀티모드 서비스 지원
   - ✅ CLI 관리 도구 구현
   - ✅ 통합 모니터링 시스템

3. **시스템 구조**
   ```
   main.py              → 레거시 (단일 계좌 전용)
   main_multi_account.py → 통합 진입점 (단일/멀티 모드)
   ```

---

## 🚀 배포 단계별 가이드

### 현재 시스템 상태 확인
```bash
# SSH 접속
ssh ubuntu@your-server-ip

# 현재 서비스 상태 확인
cd /home/ubuntu/AlbraTrading/scripts
./setup_systemd_multi.sh status

# 로그 확인
sudo journalctl -u albratrading-single -n 50  # 단일 모드
sudo journalctl -u albratrading-multi -n 50   # 멀티 모드
```

### Phase 1: 단일 계좌 모드에서 새 전략 테스트 (권장)

#### 1.1 드라이런 테스트 (Day 1)
```bash
# 현재 운영 중인 시스템 영향 없이 테스트
python src/main_multi_account.py --mode single --strategies ZLHMA_EMA_CROSS --dry-run

# 검증 사항:
# - 신호 생성 빈도 확인
# - 지표 계산 정확성 확인
# - 메모리/CPU 사용량 모니터링
```

#### 1.2 설정 활성화 (Day 2-3)
```yaml
# config.yaml 수정
strategies:
  zlhma_ema_cross:
    enabled: true  # false → true 변경
    leverage: 5    # 초기엔 낮은 레버리지
    position_size: 10  # 작은 포지션으로 시작
```

#### 1.3 실전 운영 시작 (Day 4+)
```bash
# 서비스 재시작 (단일 모드)
sudo systemctl restart albratrading-single

# 로그 모니터링
sudo journalctl -u albratrading-single -f | grep ZLHMA
```

---

### Phase 2: 멀티 계좌 전환 (선택적)

#### 2.1 환경 설정
```bash
# .env 파일에 서브 계좌 API 추가
cat >> .env << EOF
# Sub Account 1
SUB1_API_KEY=your_sub1_api_key
SUB1_API_SECRET=your_sub1_api_secret

# Sub Account 2 (optional)
SUB2_API_KEY=your_sub2_api_key
SUB2_API_SECRET=your_sub2_api_secret
EOF
```

#### 2.2 멀티 계좌 설정
```yaml
# config.yaml 수정
multi_account:
  enabled: true  # false → true
  mode: "multi"  # "single" → "multi"
  sub_accounts:
    - account_id: "sub1"
      api_key: "${SUB1_API_KEY}"
      api_secret: "${SUB1_API_SECRET}"
      enabled: true
      strategy_preferences:
        - "ZLHMA_EMA_CROSS"  # 새 전략 테스트용
      risk_limits:
        daily_loss_limit_pct: 2.0  # 더 엄격한 제한
        max_leverage: 5
        
    - account_id: "sub2"
      api_key: "${SUB2_API_KEY}"
      api_secret: "${SUB2_API_SECRET}"
      enabled: false  # 필요시 활성화
      strategy_preferences:
        - "TFPE"  # 안정적인 전략
```

#### 2.3 멀티 계좌 검증
```bash
# 설정 검증
python src/main_multi_account.py --validate

# 상태 확인
python src/main_multi_account.py --status

# CLI로 계좌 확인
python scripts/multi_account_cli.py status
```

#### 2.4 서비스 모드 전환
```bash
# 현재 서비스 중지
sudo systemctl stop albratrading-single

# 멀티 모드로 전환
cd /home/ubuntu/AlbraTrading/scripts
./setup_systemd_multi.sh multi

# 상태 확인
sudo systemctl status albratrading-multi

# 실시간 로그
sudo journalctl -u albratrading-multi -f
```

#### 2.5 멀티 계좌 모니터링
```bash
# 전체 상태
python scripts/multi_account_cli.py status

# 잔고 확인
python scripts/multi_account_cli.py balance

# 포지션 확인
python scripts/multi_account_cli.py positions

# 성과 분석
python scripts/multi_account_cli.py performance

# 리스크 체크
python scripts/multi_account_cli.py risk-check
```

---

## ⚠️ 중요 주의사항

### 1. 기존 시스템 보호
- **백업 필수**: 설정 변경 전 백업
  ```bash
  cp config/config.yaml config/config_backup_$(date +%Y%m%d).yaml
  cp -r state/ state_backup_$(date +%Y%m%d)/
  ```
- 현재 운영 중인 포지션 확인 후 전환
- 새 전략은 독립적으로 작동

### 2. 단계적 접근
```
권장 순서:
1. 단일 모드 + ZLHMA 드라이런 (3일)
2. 단일 모드 + ZLHMA 실전 소액 (1주)
3. 멀티 모드 준비 (API 키, 설정)
4. 멀티 모드 전환 및 테스트 (1주)
5. 멀티 모드 실전 운영
```

### 3. 리스크 관리
- 초기 레버리지: 5배 이하
- 초기 포지션: 10% 이하
- 일일 손실 한도: 2%
- MDD 모니터링 필수
- 계좌별 독립적 리스크 설정

---

## 📊 모니터링 체크리스트

### 일일 점검 (필수)
- [ ] 시스템 상태 확인
  ```bash
  ./setup_systemd_multi.sh status
  ```
- [ ] 포지션 상태 확인
  ```bash
  python scripts/multi_account_cli.py positions
  ```
- [ ] 리스크 레벨 확인
  ```bash
  python scripts/multi_account_cli.py risk-check
  ```
- [ ] 손익 현황 확인
- [ ] 시스템 로그 확인

### 주간 점검
- [ ] 전략 성과 분석
  ```bash
  python scripts/multi_account_cli.py report --type weekly
  ```
- [ ] 백테스트 대비 실전 성과 비교
- [ ] 파라미터 조정 필요성 검토
- [ ] 시스템 리소스 사용량

---

## 🛠️ 문제 해결 가이드

### 서비스 관련 문제

#### 서비스가 시작되지 않음
```bash
# 로그 확인
sudo journalctl -u albratrading-multi -n 100 --no-pager

# 설정 검증
python src/main_multi_account.py --validate

# 수동 실행 테스트
cd /home/ubuntu/AlbraTrading
source venv/bin/activate
python src/main_multi_account.py --mode single
```

#### 모드 전환 문제
```bash
# 현재 상태 확인
./setup_systemd_multi.sh status

# 강제 정리 후 재시작
sudo systemctl stop albratrading-single
sudo systemctl stop albratrading-multi
pkill -f main_multi_account
./setup_systemd_multi.sh [single|multi]
```

### 멀티 계좌 관련 문제

#### API 연결 실패
```bash
# API 키 확인
grep -E "(SUB|API)" .env

# 개별 계좌 테스트
python scripts/validate_multi_account.py
```

#### 계좌 동기화 문제
```bash
# 전체 동기화
python scripts/multi_account_cli.py sync-all

# 특정 계좌만
python scripts/multi_account_cli.py sync sub1
```

### 전략 관련 문제

#### 신호가 생성되지 않는 경우
1. ADX 임계값 확인 (기본: 25)
2. 데이터 수집 상태 확인
3. EMA 크로스 조건 확인

#### 과도한 신호 생성
1. `min_signal_interval` 증가 (기본: 4시간)
2. `signal_strength_threshold` 상향 조정

### 성능 이슈
1. 캐시 크기 확인
2. 심볼 수 줄이기
3. 로그 레벨 조정

---

## 📞 비상 대응

### 긴급 정지 (단일 모드)
```bash
# 시스템 중단
sudo systemctl stop albratrading-single

# 텔레그램 명령
/stop
/close_all
```

### 긴급 정지 (멀티 모드)
```bash
# 특정 계좌만
python scripts/multi_account_cli.py emergency-stop sub1

# 전체 시스템
python scripts/multi_account_cli.py emergency-stop all
sudo systemctl stop albratrading-multi
```

---

## 🔄 롤백 절차

### 단일 모드 롤백
```bash
# 1. 서비스 중지
sudo systemctl stop albratrading-single

# 2. 설정 복원
cp config/config_backup.yaml config/config.yaml

# 3. 서비스 재시작
sudo systemctl start albratrading-single
```

### 멀티 → 단일 모드 롤백
```bash
# 1. 멀티 서비스 중지
sudo systemctl stop albratrading-multi

# 2. 모든 포지션 확인
python scripts/multi_account_cli.py positions

# 3. 단일 모드로 전환
./setup_systemd_multi.sh single

# 4. 설정 수정
# config.yaml에서 multi_account.enabled: false
```

---

## 📈 성공 지표

### 단일 모드 성공 지표
- Week 1: 시스템 안정성, 신호 정확도 70%+
- Week 2: 누적 수익 양수, 승률 45%+
- Month 1: 월 수익률 5%+, 샤프 비율 1.0+

### 멀티 모드 성공 지표
- 계좌별 독립적 운영 확인
- 리스크 분산 효과 측정
- 전체 포트폴리오 성과 개선
- 계좌 간 상관관계 < 0.7

---

## 🎯 최종 권장사항

### 보수적 접근 (권장)
1. 현재 단일 모드 유지
2. 새 전략 충분히 테스트 (2-4주)
3. 안정화 후 멀티 모드 검토

### 적극적 접근
1. 즉시 멀티 모드 준비
2. 서브 계좌에서 새 전략 테스트
3. 메인 계좌는 안정적 전략 유지
4. 점진적 자금 배분 조정

### 공통 원칙
- **백업 우선**: 모든 변경 전 백업
- **소액 테스트**: 큰 자금 투입 전 검증
- **단계적 확대**: 성공 확인 후 확대
- **지속적 모니터링**: 일일 체크 필수

---

## 📚 참고 문서

- [ALBRA_TRADING_SYSTEM.md](./ALBRA_TRADING_SYSTEM.md) - 전체 시스템 아키텍처
- [README.md](./README.md) - 사용자 가이드
- [scripts/multi_account_cli.py](./scripts/multi_account_cli.py) - CLI 도구 사용법

**"천천히, 그러나 확실하게"**

---

*문서 버전: 2.0*
*최종 수정: 2025-01-02*
