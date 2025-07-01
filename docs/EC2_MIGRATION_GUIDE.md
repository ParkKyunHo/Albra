# AlbraTrading EC2 마이그레이션 가이드

## 📋 현재 상황 (2025-07-01 KST)

### 문제 설명
- **이전 EC2 인스턴스**: 54.88.60.48 (us-east-1, 미국 동부 버지니아)
- **현재 EC2 인스턴스**: 43.201.76.89 (ap-northeast-2, 한국 서울)
- **이전 문제**: 바이낸스가 미국 지역에서의 API 접속을 차단
- **해결**: 한국 리전으로 마이그레이션 완료

### 현재 EC2 사양
- **인스턴스 타입**: (확인 필요)
- **OS**: Ubuntu 22.04 LTS
- **Python**: 3.10 (venv 설치됨)
- **스토리지**: (확인 필요)
- **보안 그룹**: SSH(22), HTTP(80), HTTPS(443) 개방 추정

## 🎯 해결 방안

### 권장 리전 선택
1. **한국 (ap-northeast-2, 서울)**
   - 장점: 낮은 레이턴시, 바이낸스 접속 가능
   - 단점: 미국보다 약간 높은 비용
   
2. **일본 (ap-northeast-1, 도쿄)**
   - 장점: 바이낸스 접속 가능, 안정적인 인프라
   - 단점: 한국보다 약간 높은 레이턴시

**추천**: 한국 리전 (ap-northeast-2)

## 📝 마이그레이션 체크리스트

### 사전 준비
- [ ] AWS 콘솔 접속 권한 확인
- [ ] 현재 EC2 인스턴스의 정확한 사양 확인
- [ ] 필요한 경우 EBS 스냅샷 생성
- [ ] 보안 그룹 규칙 백업
- [ ] .env 파일 백업 (로컬에 있는지 확인)

### 마이그레이션 단계

#### 1단계: 새 EC2 인스턴스 생성
```bash
# AWS 콘솔에서:
1. EC2 대시보드 → 인스턴스 시작
2. 리전 선택: Asia Pacific (Seoul) ap-northeast-2
3. AMI 선택: Ubuntu Server 22.04 LTS (HVM), SSD Volume Type (Python 3.10 기본 포함)
4. 인스턴스 타입: t3.micro (또는 기존과 동일)
5. 키 페어: trading-bot4 사용 또는 새로 생성
6. 네트워크 설정:
   - VPC: 기본 VPC
   - 서브넷: 기본 설정
   - 퍼블릭 IP 자동 할당: 활성화
7. 보안 그룹: 
   - SSH (22) - 내 IP
   - HTTP (80) - 0.0.0.0/0
   - HTTPS (443) - 0.0.0.0/0
   - Custom TCP (5000) - 0.0.0.0/0 (Flask 대시보드)
8. 스토리지: 20GB gp3 (또는 필요에 따라)
```

#### 2단계: 초기 설정 스크립트
```bash
# SSH 접속
ssh -i ~/.ssh/trading-bot4 ubuntu@43.201.76.89

# 시스템 업데이트
sudo apt update && sudo apt upgrade -y

# Python 3.10 설치
sudo apt update
sudo apt install python3.10 python3.10-venv python3.10-dev -y

# 필수 패키지 설치
sudo apt install git nginx certbot python3-certbot-nginx -y

# 작업 디렉토리 생성
mkdir -p /home/ubuntu/AlbraTrading
cd /home/ubuntu/AlbraTrading

# Python 가상환경 생성
python3.10 -m venv venv
source venv/bin/activate

# pip 업그레이드
pip install --upgrade pip setuptools wheel
```

#### 3단계: 프로젝트 배포
```bash
# 로컬에서 deployment.yaml 업데이트
# ec2_ip: [NEW_EC2_IP]

# WSL에서 배포 실행
cd /home/albra/AlbraTrading
./deploy_v2.bat
```

#### 4단계: 환경 설정
```bash
# EC2에서 .env 파일 생성
cd /home/ubuntu/AlbraTrading
nano .env

# 필요한 환경 변수 설정:
# BINANCE_API_KEY=your_api_key
# BINANCE_API_SECRET=your_api_secret
# TELEGRAM_BOT_TOKEN=your_bot_token
# TELEGRAM_CHAT_ID=your_chat_id
# 기타 필요한 설정...
```

#### 5단계: 바이낸스 API 테스트
```bash
# Python 테스트 스크립트 실행
cd /home/ubuntu/AlbraTrading
source venv/bin/activate
python -c "
from binance.client import Client
import os
from dotenv import load_dotenv

load_dotenv()
client = Client(os.getenv('BINANCE_API_KEY'), os.getenv('BINANCE_API_SECRET'))
try:
    status = client.get_system_status()
    print('바이낸스 API 연결 성공:', status)
    account = client.get_account()
    print('계정 정보 획득 성공')
except Exception as e:
    print('바이낸스 API 연결 실패:', str(e))
"
```

#### 6단계: Systemd 서비스 설정
```bash
# 서비스 파일 복사
sudo cp scripts/systemd/albratrading-multi.service /etc/systemd/system/

# 서비스 활성화 및 시작
sudo systemctl daemon-reload
sudo systemctl enable albratrading-multi
sudo systemctl start albratrading-multi

# 상태 확인
sudo systemctl status albratrading-multi
sudo journalctl -u albratrading-multi -f
```

#### 7단계: 모니터링 설정
```bash
# 대시보드 접속 테스트
curl http://localhost:5000/health

# 텔레그램 봇 테스트
# 텔레그램에서 /status 명령 전송
```

## 🔄 마이그레이션 후 작업

### 검증 항목
- [ ] 바이낸스 API 정상 접속
- [ ] 실시간 가격 데이터 수신
- [ ] 주문 실행 가능 (테스트 주문)
- [ ] 텔레그램 봇 응답
- [ ] 웹 대시보드 접속
- [ ] 로그 파일 생성 및 기록

### DNS 업데이트 (필요시)
```bash
# Route 53 또는 사용 중인 DNS 서비스에서
# A 레코드를 새 IP로 업데이트
```

### 이전 인스턴스 정리
```bash
# 모든 것이 정상 작동 확인 후:
1. 이전 EC2 인스턴스 중지 (즉시 종료하지 말고 며칠 관찰)
2. EBS 스냅샷 생성 (백업용)
3. 1주일 후 문제 없으면 인스턴스 종료
```

## 🚨 롤백 계획

만약 새 인스턴스에서 문제 발생 시:
1. systemd 서비스 중지: `sudo systemctl stop albratrading-multi`
2. 이전 EC2 인스턴스 재시작
3. deployment.yaml의 IP를 이전 IP로 되돌림
4. 문제 분석 후 재시도

## 📊 비용 고려사항

### 예상 월 비용 (서울 리전)
- t3.micro: 약 $10-15/월
- EBS 스토리지 (20GB): 약 $2/월
- 데이터 전송: 사용량에 따라 변동
- **총 예상**: 약 $15-25/월

## 🔐 보안 권장사항

1. **보안 그룹 강화**
   - SSH는 특정 IP만 허용
   - 불필요한 포트 차단
   
2. **정기 백업**
   - EBS 스냅샷 주기적 생성
   - 상태 파일 별도 백업

3. **모니터링**
   - CloudWatch 알람 설정
   - 비정상 트래픽 감지

## 📞 문제 발생 시 체크포인트

1. **바이낸스 API 연결 실패**
   - 리전 확인 (ap-northeast-2인지)
   - API 키/시크릿 확인
   - IP 화이트리스트 설정 확인

2. **서비스 시작 실패**
   - 로그 확인: `sudo journalctl -u albratrading-multi -n 100`
   - Python 경로 확인
   - 의존성 설치 확인

3. **성능 문제**
   - 인스턴스 타입 업그레이드 고려
   - 네트워크 레이턴시 확인
   - 리소스 사용량 모니터링

---
*작성일: 2025-07-01*
*작성자: Claude Code Assistant*