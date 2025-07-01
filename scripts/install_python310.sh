#!/bin/bash

# Python 3.10 설치 스크립트
# Ubuntu 24.04에서 Python 3.12를 제거하고 3.10 설치

set -e

echo "======================================"
echo "   Python 3.10 설치 스크립트"
echo "   $(date '+%Y-%m-%d %H:%M:%S KST')"
echo "======================================"
echo

# deadsnakes PPA 추가
echo "📦 deadsnakes PPA 추가 중..."
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update

# Python 3.10 설치
echo "🐍 Python 3.10 설치 중..."
sudo apt install -y python3.10 python3.10-venv python3.10-dev python3.10-distutils

# pip 설치
echo "📦 pip 설치 중..."
curl -sS https://bootstrap.pypa.io/get-pip.py | sudo python3.10

# Python 3.10을 기본 python3로 설정
echo "🔧 Python 3.10을 기본값으로 설정 중..."
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 2
sudo update-alternatives --set python3 /usr/bin/python3.10

# 버전 확인
echo
echo "✅ 설치 완료!"
echo "현재 Python 버전:"
python3 --version
python3.10 --version

echo
echo "======================================"
echo "다음 단계: AlbraTrading 프로젝트 배포"
echo "======================================"