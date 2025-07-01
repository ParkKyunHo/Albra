#!/bin/bash

# Python 3.12 정리 스크립트 (선택사항)
# 주의: 시스템 기본 Python을 변경하므로 신중히 실행하세요

echo "======================================"
echo "   Python 3.12 정리 및 3.10 설정"
echo "======================================"

# Python 3.10을 기본값으로 설정
echo "Python 3.10을 기본값으로 설정 중..."
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 2
sudo update-alternatives --set python3 /usr/bin/python3.10

# 또는 직접 심볼릭 링크 변경
# sudo rm /usr/bin/python3
# sudo ln -s /usr/bin/python3.10 /usr/bin/python3

echo "현재 Python 버전:"
python3 --version

echo
echo "완료! 가상환경 확인:"
cd /home/ubuntu/AlbraTrading
source venv/bin/activate
python --version

echo
echo "======================================"
echo "주의사항:"
echo "- 가상환경은 이미 Python 3.10으로 생성되어 영향 없음"
echo "- 시스템 python3 명령만 3.10을 가리키도록 변경"
echo "- Python 3.12는 여전히 설치되어 있음 (python3.12로 실행 가능)"
echo "======================================"