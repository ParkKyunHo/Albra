# EC2 마이그레이션 노트 (2025-07-01)

## 🚨 중요 이슈: 바이낸스 API 접속 차단

### 현재 상황
- **이전 EC2 인스턴스**: 54.88.60.48 (us-east-1 리전)
- **현재 EC2 인스턴스**: 13.209.157.171 (ap-northeast-2 서울) [Elastic IP]
- **문제**: `Service unavailable from a restricted location` 에러
- **원인**: 미국 리전에서 바이낸스 API 접속 차단

### 완료된 작업
1. ✅ EC2 인스턴스 생성 및 초기 설정
2. ✅ SSH 키 설정 (trading-bot4)
3. ✅ Python 3.10 환경 구성
4. ✅ 모든 의존성 설치 (colorlog 포함)
5. ✅ 코드 배포 및 systemd 서비스 설정
6. ✅ main_multi_account.py 사용하도록 서비스 파일 수정

### 해결 방안
1. **권장**: 한국(ap-northeast-2) 또는 일본(ap-northeast-1) 리전으로 EC2 이전
2. **대안**: VPN/프록시 설정 (권장하지 않음)

### 다음 단계
1. 새 EC2 인스턴스 생성 시 **반드시 아시아 리전 선택**
   - 서울 (ap-northeast-2)
   - 도쿄 (ap-northeast-1)
   - 싱가포르 (ap-southeast-1)

2. 현재 인스턴스의 설정은 모두 완료되었으므로:
   - AMI 이미지 생성 후 다른 리전에서 복원
   - 또는 새 인스턴스에서 동일한 설정 반복

### SSH 접속 명령
```bash
# WSL에서
ssh -i ~/.ssh/trading-bot4 ubuntu@13.209.157.171

# Windows에서 (키 복사 필요)
ssh -i C:\Users\박균호\.ssh\trading-bot4 ubuntu@13.209.157.171
```

### 서비스 관리
```bash
# 상태 확인
sudo systemctl status albratrading-multi

# 로그 확인
tail -f ~/AlbraTrading/logs/trading.log
tail -f ~/AlbraTrading/logs/systemd_multi_error.log

# 재시작
sudo systemctl restart albratrading-multi
```

### 환경 정보
- Ubuntu 24.04.2 LTS
- Python 3.10.18 (venv)
- 모든 의존성 설치 완료
- systemd 서비스 활성화됨