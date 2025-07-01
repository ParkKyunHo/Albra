#!/bin/bash

# 새 EC2 인스턴스 초기 설정 스크립트
# Ubuntu 22.04 + Python 3.10 환경 구성

set -e

echo "======================================"
echo "   AlbraTrading EC2 초기 설정"
echo "   $(date '+%Y-%m-%d %H:%M:%S KST')"
echo "======================================"
echo

# 시스템 정보 확인
echo "📍 시스템 정보:"
lsb_release -a
echo

# 시스템 업데이트
echo "📦 시스템 패키지 업데이트 중..."
sudo apt update && sudo apt upgrade -y

# Python 3.10 설치
echo "🐍 Python 3.10 설치 중..."
sudo apt install -y python3.10 python3.10-venv python3.10-dev python3-pip

# 필수 패키지 설치
echo "📦 필수 패키지 설치 중..."
sudo apt install -y git build-essential libssl-dev libffi-dev nginx certbot python3-certbot-nginx

# 작업 디렉토리 생성
echo "📁 작업 디렉토리 생성 중..."
mkdir -p /home/ubuntu/AlbraTrading
cd /home/ubuntu/AlbraTrading

# Python 가상환경 생성
echo "🔧 Python 가상환경 생성 중..."
python3.10 -m venv venv
source venv/bin/activate

# pip 업그레이드
echo "📦 pip 업그레이드 중..."
pip install --upgrade pip setuptools wheel

# 바이낸스 테스트를 위한 기본 패키지 설치
echo "📦 기본 패키지 설치 중..."
pip install python-binance python-dotenv requests

# 리전 및 바이낸스 연결 확인
echo
echo "🌏 리전 확인:"
curl -s http://169.254.169.254/latest/meta-data/placement/region 2>/dev/null || echo "메타데이터 접근 불가"

echo
echo "🔍 바이낸스 연결 테스트:"
python3 -c "
import requests
try:
    r = requests.get('https://api.binance.com/api/v3/ping', timeout=5)
    if r.status_code == 200:
        print('✅ 바이낸스 API 연결 성공!')
    else:
        print(f'❌ 바이낸스 API 응답: {r.status_code}')
        print(r.text[:200])
except Exception as e:
    print(f'❌ 연결 실패: {e}')
"

echo
echo "======================================"
echo "✅ 초기 설정 완료!"
echo "======================================"
echo
echo "다음 단계:"
echo "1. deploy_wsl.sh 실행하여 프로젝트 배포"
echo "2. systemd 서비스 설정"
echo "3. 바이낸스 API 키 테스트"