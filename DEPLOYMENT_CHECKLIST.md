# 🚀 AlbraTrading 배포 전 체크리스트 (멀티 계좌 + ZLHMA 전략)

## ⚠️ 중요: 배포 전 반드시 확인해야 할 사항들

### 1. 🔑 환경 변수 설정 (.env 파일)

#### 필수 확인 사항:
```bash
# .env 파일에 다음이 모두 설정되어 있는지 확인

# 마스터 계좌
BINANCE_API_KEY=실제_마스터_API_키
BINANCE_SECRET_KEY=실제_마스터_시크릿_키

# 서브 계좌 (멀티 계좌 모드 사용 시)
TEST_ACCOUNT_1_API_KEY=실제_서브계좌1_API_키
TEST_ACCOUNT_1_API_SECRET=실제_서브계좌1_시크릿_키

# 텔레그램
TELEGRAM_BOT_TOKEN=실제_텔레그램_봇_토큰
TELEGRAM_CHAT_ID=실제_텔레그램_챗_ID
```

#### 확인 명령어:
```bash
# 로컬에서 환경변수 확인
python scripts/validate_multi_account.py
```

### 2. 📋 설정 파일 검증 (config.yaml)

#### 단일 계좌 모드 설정:
```yaml
multi_account:
  enabled: false  # 단일 계좌 모드

strategies:
  tfpe:
    enabled: true  # 마스터 계좌에서 TFPE 실행
```

#### 멀티 계좌 모드 설정:
```yaml
multi_account:
  enabled: true  # 멀티 계좌 모드 활성화
  
  sub_accounts:
    test_account_1:
      enabled: true
      strategy: "ZLHMA_EMA_CROSS"  # 서브 계좌에서 ZLHMA 실행
      leverage: 5  # 안전한 시작
      position_size: 10.0
```

### 3. 🛠️ Systemd 서비스 파일 수정

#### 현재 설정 (단일 모드):
```bash
# 서버에서 직접 수정 필요
sudo nano /etc/systemd/system/albratrading.service
```

#### 멀티 계좌 모드로 변경:
```ini
# ExecStart 라인을 다음과 같이 수정:
ExecStart=/home/ubuntu/AlbraTrading/venv/bin/python /home/ubuntu/AlbraTrading/src/main_multi_account.py --mode multi
```

### 4. 🔍 배포 전 로컬 테스트

```bash
# 1. 구문 검사
python -m py_compile src/strategies/zlhma_ema_cross_strategy.py

# 2. 드라이런 테스트 (단일 모드)
python src/main.py --dry-run

# 3. 드라이런 테스트 (멀티 모드)
python src/main_multi_account.py --mode multi --dry-run

# 4. 설정 검증
python src/main_multi_account.py --validate
```

### 5. 📦 배포 스크립트 실행

```bash
# Windows에서 실행
deploy.bat
```

### 6. 🔧 서버에서 추가 작업

배포 후 서버에 SSH로 접속하여:

```bash
# SSH 접속
ssh -i "C:\Users\사용자\.ssh\trading-bot-key" ubuntu@3.39.88.164

# 1. systemd 서비스 파일 수정 (멀티 계좌 모드 사용 시)
sudo nano /etc/systemd/system/albratrading.service
# ExecStart 라인 수정

# 2. 서비스 재시작
sudo systemctl daemon-reload
sudo systemctl restart albratrading

# 3. 로그 확인
sudo journalctl -u albratrading -f
```

### 7. 📊 배포 후 확인 사항

#### 즉시 확인:
- [ ] 서비스 상태: `sudo systemctl status albratrading`
- [ ] 오류 로그 없음: `sudo journalctl -u albratrading -n 100`
- [ ] 텔레그램 시작 알림 수신
- [ ] 웹 대시보드 접속: http://3.39.88.164:5000

#### 15분 후 확인:
- [ ] 첫 캔들 체크 로그 확인
- [ ] 메모리 사용량 정상
- [ ] API 연결 상태 정상

### 8. 🚨 비상 대응 준비

#### 긴급 중지 명령어:
```bash
# SSH 접속 후
sudo systemctl stop albratrading

# 텔레그램으로
/stop
```

#### 설정 롤백:
```bash
# 백업 파일로 복원
cp /home/ubuntu/AlbraTrading/config/config.yaml.backup /home/ubuntu/AlbraTrading/config/config.yaml
sudo systemctl restart albratrading
```

### 9. 📝 배포 모드별 체크리스트

#### 🔵 단일 계좌 모드 (권장 - 안정적)
- [x] main.py 사용
- [x] multi_account.enabled: false
- [x] 마스터 계좌 API 키만 필요
- [x] systemd 수정 불필요

#### 🟢 멀티 계좌 모드 (고급)
- [ ] main_multi_account.py 사용
- [ ] multi_account.enabled: true
- [ ] 모든 서브 계좌 API 키 설정
- [ ] systemd 서비스 파일 수정 필요

### 10. 🎯 권장 배포 순서

1. **첫 배포**: 단일 계좌 모드로 시작
   - 기존 TFPE 전략만 실행
   - 시스템 안정성 확인

2. **1주 후**: ZLHMA 전략 추가
   - 단일 계좌에서 두 전략 병렬 실행
   - 전략 간 충돌 여부 확인

3. **2주 후**: 멀티 계좌 전환 검토
   - 서브 계좌 API 키 준비
   - 멀티 모드로 전환

## ⚡ 빠른 배포 (단일 모드)

현재 설정으로 즉시 배포 가능:
```bash
# 1. 로컬에서
deploy.bat

# 2. 배포 완료 후 상태 확인
ssh -i "C:\Users\사용자\.ssh\trading-bot-key" ubuntu@3.39.88.164 "sudo systemctl status albratrading"
```

## 📞 문제 발생 시

1. 로그 확인: `sudo journalctl -u albratrading -n 200`
2. 설정 검증: `cd /home/ubuntu/AlbraTrading && python scripts/validate_multi_account.py`
3. 긴급 중지: `sudo systemctl stop albratrading`
