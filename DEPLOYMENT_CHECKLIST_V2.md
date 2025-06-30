# 🚀 AlbraTrading v2.0 배포 체크리스트

## 📋 배포 전 준비사항

### 1. 환경 변수 확인 (.env)
- [ ] `BINANCE_API_KEY` - 메인 계좌 API 키
- [ ] `BINANCE_SECRET_KEY` - 메인 계좌 시크릿 키
- [ ] `TELEGRAM_BOT_TOKEN` - 텔레그램 봇 토큰
- [ ] `TELEGRAM_CHAT_ID` - 텔레그램 채팅 ID
- [ ] `SUB1_API_KEY` (선택) - 서브 계좌 1 API 키
- [ ] `SUB1_API_SECRET` (선택) - 서브 계좌 1 시크릿

### 2. 설정 파일 확인 (config/config.yaml)
- [ ] 시스템 모드 설정 (`system.mode: "live"`)
- [ ] 멀티 계좌 설정 확인
  - [ ] `multi_account.enabled` 값 확인
  - [ ] `multi_account.mode` 값 확인 ("single" 또는 "multi")
- [ ] 전략 활성화 확인 (`strategies.tfpe.enabled: true`)
- [ ] 리스크 관리 설정 확인

### 3. 디렉토리 구조 확인
```bash
# 필수 디렉토리 생성
mkdir -p logs state data
chmod 755 logs state data
```

## 🔧 배포 절차

### Step 1: 코드 업데이트
```bash
cd /home/ubuntu/AlbraTrading
git pull origin main
```

### Step 2: 가상환경 및 의존성
```bash
# 가상환경 활성화
source venv/bin/activate

# 의존성 업데이트
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3: 설정 검증
```bash
# 설정 파일 검증
python src/main_multi_account.py --validate

# 시스템 상태 확인
python src/main_multi_account.py --status
```

### Step 4: 기존 서비스 정리
```bash
# 기존 서비스 중지 (있는 경우)
sudo systemctl stop albratrading 2>/dev/null || true
sudo systemctl stop albratrading-single 2>/dev/null || true
sudo systemctl stop albratrading-multi 2>/dev/null || true

# 프로세스 확인
ps aux | grep main | grep -v grep
```

### Step 5: Systemd 서비스 설치

#### 옵션 A: 단일 모드로 시작 (권장)
```bash
cd /home/ubuntu/AlbraTrading/scripts
chmod +x setup_systemd_multi.sh
./setup_systemd_multi.sh single
```

#### 옵션 B: 멀티 모드로 시작
```bash
./setup_systemd_multi.sh multi
```

### Step 6: 서비스 시작 확인
```bash
# 서비스 상태 확인
./setup_systemd_multi.sh status

# 로그 확인 (단일 모드)
sudo journalctl -u albratrading-single -f

# 로그 확인 (멀티 모드)
sudo journalctl -u albratrading-multi -f
```

### Step 7: 배포 검증
```bash
# 배포 체크 스크립트 실행
chmod +x scripts/check_deployment_multi.sh
./scripts/check_deployment_multi.sh
```

## ✅ 배포 후 확인사항

### 1. 프로세스 확인
- [ ] `main_multi_account.py` 프로세스 실행 중
- [ ] CPU/메모리 사용률 정상
- [ ] 프로세스 uptime 확인

### 2. 로그 확인
- [ ] 시스템 초기화 성공 메시지
- [ ] API 연결 성공
- [ ] 전략 초기화 성공
- [ ] 에러 메시지 없음

### 3. 기능 확인
- [ ] 웹 대시보드 접속 가능 (http://서버IP:5000)
- [ ] 텔레그램 봇 응답 (/status 명령)
- [ ] 포지션 동기화 작동

### 4. 멀티 계좌 모드 (해당 시)
- [ ] 모든 계좌 API 연결 성공
- [ ] CLI 도구 작동 확인
```bash
python scripts/multi_account_cli.py status
python scripts/multi_account_cli.py balance
```

## 🔄 모드 전환 (필요시)

### 단일 → 멀티 전환
```bash
# 1. 현재 상태 백업
cp config/config.yaml config/config_backup_$(date +%Y%m%d).yaml

# 2. 설정 수정
# config.yaml에서 multi_account.enabled: true로 변경

# 3. 서비스 전환
./scripts/setup_systemd_multi.sh switch
# → 멀티 모드 선택

# 4. 확인
python scripts/multi_account_cli.py status
```

## 🚨 문제 발생 시

### 1. 서비스가 시작되지 않는 경우
```bash
# 상세 로그 확인
sudo journalctl -u albratrading-single -n 100 --no-pager

# 환경 변수 확인
cat .env | grep API_KEY

# Python 경로 확인
which python
/home/ubuntu/AlbraTrading/venv/bin/python --version
```

### 2. API 연결 실패
```bash
# 테스트넷/실전 모드 확인
grep "mode:" config/config.yaml

# API 키 권한 확인 (Futures 거래 권한 필요)
```

### 3. 포트 충돌
```bash
# 5000번 포트 사용 프로세스 확인
sudo lsof -i :5000

# 필요시 포트 변경 (config.yaml)
```

### 4. 롤백 절차
```bash
# 1. 서비스 중지
sudo systemctl stop albratrading-single
# 또는
sudo systemctl stop albratrading-multi

# 2. 이전 버전으로 롤백
git checkout <previous_commit>

# 3. 서비스 재시작
sudo systemctl start albratrading-single
```

## 📊 성공 지표

배포가 성공적으로 완료되면:
1. ✅ `check_deployment_multi.sh` 스크립트가 모든 체크 통과
2. ✅ 시스템 로그에 에러 없음
3. ✅ 텔레그램으로 "시스템 시작" 알림 수신
4. ✅ 웹 대시보드 정상 작동
5. ✅ 포지션 동기화 정상 작동

## 📝 참고사항

- **첫 배포**: 단일 모드로 시작하여 안정성 확인 후 멀티 모드 전환 권장
- **모니터링**: 배포 후 최소 30분간 로그 모니터링
- **백업**: 설정 파일과 상태 파일 백업 필수
- **문서**: 변경사항은 deployment_log.txt에 기록

---

최종 업데이트: 2025년 1월
