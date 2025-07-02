#!/bin/bash

# AlbraTrading EC2 상태 확인 스크립트
# 현재 EC2 인스턴스의 상태와 설정을 확인합니다.

echo "=============================================="
echo "   AlbraTrading EC2 상태 확인"
echo "   시간: $(date '+%Y-%m-%d %H:%M:%S KST')"
echo "=============================================="

# 설정
EC2_IP="43.200.179.200"
SSH_KEY="$HOME/.ssh/trading-bot4"
SSH_USER="ubuntu"

# SSH 키 확인
if [ ! -f "$SSH_KEY" ]; then
    echo "❌ SSH 키를 찾을 수 없습니다: $SSH_KEY"
    echo "Windows에서 복사해주세요:"
    echo "cp /mnt/c/Users/박균호/.ssh/trading-bot4 ~/.ssh/"
    echo "chmod 600 ~/.ssh/trading-bot4"
    exit 1
fi

echo "📡 EC2 인스턴스에 연결 중: $EC2_IP"
echo ""

# EC2 상태 확인 명령 생성
STATUS_COMMANDS='
echo "=== 시스템 정보 ==="
echo "호스트명: $(hostname)"
echo "IP 주소: $(curl -s http://checkip.amazonaws.com 2>/dev/null || echo "확인 실패")"
echo "리전 확인: $(curl -s http://169.254.169.254/latest/meta-data/placement/region 2>/dev/null || echo "확인 실패")"
echo "인스턴스 타입: $(curl -s http://169.254.169.254/latest/meta-data/instance-type 2>/dev/null || echo "확인 실패")"
echo ""

echo "=== OS 정보 ==="
lsb_release -a 2>/dev/null || cat /etc/os-release
echo ""

echo "=== Python 버전 ==="
python3 --version 2>/dev/null || echo "Python3 not found"
if [ -d "/home/ubuntu/AlbraTrading/venv" ]; then
    source /home/ubuntu/AlbraTrading/venv/bin/activate 2>/dev/null
    python --version
fi
echo ""

echo "=== 디스크 사용량 ==="
df -h | grep -E "^/dev|Filesystem"
echo ""

echo "=== 메모리 사용량 ==="
free -h
echo ""

echo "=== AlbraTrading 서비스 상태 ==="
sudo systemctl status albratrading-multi --no-pager 2>/dev/null || echo "서비스를 찾을 수 없습니다"
echo ""

echo "=== 최근 로그 (마지막 20줄) ==="
if [ -f "/home/ubuntu/AlbraTrading/logs/trading.log" ]; then
    tail -20 /home/ubuntu/AlbraTrading/logs/trading.log
else
    echo "로그 파일을 찾을 수 없습니다"
fi
echo ""

echo "=== 바이낸스 API 테스트 ==="
if [ -f "/home/ubuntu/AlbraTrading/.env" ]; then
    cd /home/ubuntu/AlbraTrading
    if [ -d "venv" ]; then
        source venv/bin/activate
        python3 -c "
import sys
try:
    from binance.client import Client
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    api_key = os.getenv(\"BINANCE_API_KEY\")
    api_secret = os.getenv(\"BINANCE_API_SECRET\")
    
    if not api_key or not api_secret:
        print(\"❌ API 키가 설정되지 않았습니다\")
        sys.exit(1)
    
    print(\"🔄 바이낸스 API 연결 테스트 중...\")
    client = Client(api_key, api_secret)
    
    # 시스템 상태 확인
    status = client.get_system_status()
    print(f\"✅ 시스템 상태: {status}\")
    
    # 계정 정보 시도
    try:
        account = client.get_account()
        print(\"✅ 계정 정보 접근 성공\")
    except Exception as e:
        print(f\"❌ 계정 정보 접근 실패: {str(e)}\")
        
except ImportError:
    print(\"❌ Binance 라이브러리가 설치되지 않았습니다\")
except Exception as e:
    print(f\"❌ API 연결 실패: {str(e)}\")
" 2>&1
    else
        echo "❌ Python 가상환경을 찾을 수 없습니다"
    fi
else
    echo "❌ .env 파일을 찾을 수 없습니다"
fi
echo ""

echo "=== 네트워크 연결 테스트 ==="
echo -n "바이낸스 API (api.binance.com): "
nc -zv -w 5 api.binance.com 443 2>&1 | grep -o "succeeded\|failed" || echo "실패"
echo ""

echo "=== 프로세스 확인 ==="
ps aux | grep -E "python.*main_multi_account|albratrading" | grep -v grep || echo "실행 중인 AlbraTrading 프로세스가 없습니다"
'

# SSH로 명령 실행
ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -i "$SSH_KEY" "$SSH_USER@$EC2_IP" "$STATUS_COMMANDS" 2>&1

# 연결 실패 시
if [ $? -ne 0 ]; then
    echo ""
    echo "❌ EC2 인스턴스에 연결할 수 없습니다."
    echo ""
    echo "체크리스트:"
    echo "1. EC2 인스턴스가 실행 중인지 확인"
    echo "2. 보안 그룹에서 SSH(22) 포트가 열려있는지 확인"
    echo "3. SSH 키 권한이 올바른지 확인 (chmod 600)"
    echo "4. IP 주소가 올바른지 확인: $EC2_IP"
fi

echo ""
echo "=============================================="
echo "   상태 확인 완료"
echo "=============================================="