# AlbraTrading 배포 가이드

## 📋 개요

이 문서는 AlbraTrading 시스템을 로컬 개발 환경에서 AWS EC2로 배포하는 방법을 설명합니다.

## 🔧 사전 준비사항

### 1. 로컬 환경
- Windows 10/11 with WSL2
- Python 3.12+
- Git
- SSH 클라이언트

### 2. EC2 환경
- Ubuntu 22.04 LTS
- Python 3.12+
- 충분한 디스크 공간 (최소 10GB)
- 포트 5000 오픈 (웹 대시보드용)

### 3. 필수 파일
- `.env` 파일 (API 키 포함)
- `config/config.yaml` (트레이딩 설정)
- SSH 키 파일 (`~/.ssh/trading-bot4.pem`)

## 📦 배포 프로세스

### 1. 배포 전 검증 (로컬)

```bash
# WSL 터미널에서 실행
cd /home/albra/AlbraTrading
./scripts/pre_deploy_check_v2.sh
```

### 2. 개선된 배포 스크립트 사용

Windows 명령 프롬프트에서:

```batch
cd C:\AlbraTrading
deploy_v2.bat
```

배포 스크립트는 다음 작업을 자동으로 수행합니다:
1. 로컬 코드 검증
2. SSH 연결 테스트
3. 기존 서비스 중지
4. 파일 업로드 (EC2 경로에 맞게 자동 조정)
5. Python 환경 설정
6. 서비스 시작

### 3. 배포 모드 선택

배포 시 두 가지 모드 중 선택:
- **1. Single Account Mode**: 단일 계좌 트레이딩
- **2. Multi Account Mode**: 다중 계좌 트레이딩 (권장)

## 🔍 경로 관리

### 환경별 경로 차이

| 환경 | 기본 경로 | 사용자 |
|------|----------|--------|
| 로컬 (WSL) | `/home/albra/AlbraTrading` | albra |
| EC2 | `/home/ubuntu/AlbraTrading` | ubuntu |
| Windows | `C:\AlbraTrading` | - |

### systemd 서비스 파일

시스템은 환경에 맞는 서비스 파일을 자동으로 선택합니다:
- 로컬: `*.service.local`
- EC2: `*.service.ec2`

## 🚀 배포 후 확인

### 1. 서비스 상태 확인

```bash
# SSH로 EC2 접속
ssh -i ~/.ssh/trading-bot4.pem ubuntu@43.200.179.200

# 서비스 상태 확인
sudo systemctl status albratrading-multi

# 실시간 로그 확인
sudo journalctl -u albratrading-multi -f
```

### 2. 자동 검증 스크립트

```bash
cd /home/ubuntu/AlbraTrading
./scripts/check_deployment_multi.sh
```

### 3. 웹 대시보드 접속

브라우저에서: `http://3.39.88.164:5000`

## 🔄 일반적인 작업

### 서비스 재시작

```bash
sudo systemctl restart albratrading-multi
```

### 모드 전환 (Single ↔ Multi)

```bash
cd /home/ubuntu/AlbraTrading
./scripts/setup_systemd_multi.sh switch
```

### 로그 확인

```bash
# 시스템 로그
sudo journalctl -u albratrading-multi -n 100

# 애플리케이션 로그
tail -f /home/ubuntu/AlbraTrading/logs/trading.log
```

## 🆘 문제 해결

### 1. 서비스가 시작되지 않을 때

```bash
# Python 직접 실행으로 테스트
cd /home/ubuntu/AlbraTrading
source venv/bin/activate
python src/main.py --validate
```

### 2. 경로 문제

- systemd 서비스 파일의 경로 확인
- Python PYTHONPATH 환경변수 확인

### 3. 권한 문제

```bash
# 소유권 수정
sudo chown -R ubuntu:ubuntu /home/ubuntu/AlbraTrading

# 실행 권한 부여
chmod +x scripts/*.sh
```

## 📝 배포 체크리스트

- [ ] `.env` 파일 존재 및 API 키 설정
- [ ] `config/config.yaml` 설정 확인
- [ ] SSH 키 파일 권한 (600)
- [ ] EC2 인스턴스 실행 중
- [ ] 포트 5000 보안 그룹에서 오픈
- [ ] 충분한 디스크 공간 (최소 20% 여유)

## 🔐 보안 주의사항

1. **API 키 보안**
   - `.env` 파일은 절대 Git에 커밋하지 않음
   - 정기적으로 API 키 재발급

2. **SSH 보안**
   - SSH 키 파일 권한 600 유지
   - 필요시 IP 화이트리스트 설정

3. **서비스 권한**
   - 서비스는 ubuntu 사용자로 실행
   - root 권한 최소화

## 📞 지원

문제 발생 시:
1. 로그 확인
2. 배포 검증 스크립트 실행
3. 텔레그램 봇으로 상태 확인

---

마지막 업데이트: 2025-01-30