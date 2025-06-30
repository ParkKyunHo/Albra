#!/bin/bash
# 안전한 deploy 스크립트 - 포지션이 있을 때 사용

echo "=== AlbraTrading 안전 배포 ==="
echo ""

# 1. 현재 포지션 확인
echo "1. 현재 포지션 확인..."
echo "----------------------------------------"
cd /home/ubuntu/AlbraTrading
source venv/bin/activate
python3 << EOF
import asyncio
import sys
sys.path.insert(0, '.')
from src.core.binance_api import BinanceAPI
from src.utils.config_manager import ConfigManager
import os
from dotenv import load_dotenv

load_dotenv()

async def check_positions():
    api = BinanceAPI(
        api_key=os.getenv('BINANCE_API_KEY'),
        secret_key=os.getenv('BINANCE_SECRET_KEY'),
        testnet=False
    )
    await api.initialize()
    positions = await api.get_positions()
    active = [p for p in positions if float(p['positionAmt']) != 0]
    
    if active:
        print("⚠️  활성 포지션 발견:")
        for pos in active:
            print(f"   - {pos['symbol']}: {pos['positionAmt']} @ {pos['entryPrice']}")
        print(f"\n총 {len(active)}개의 활성 포지션")
        return len(active)
    else:
        print("✅ 활성 포지션 없음")
        return 0

count = asyncio.run(check_positions())
exit(0 if count == 0 else 1)
EOF

POSITION_COUNT=$?

if [ $POSITION_COUNT -ne 0 ]; then
    echo ""
    echo "⚠️  경고: 활성 포지션이 있습니다!"
    echo ""
    echo "계속하시겠습니까? (y/N)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        echo "배포 취소됨"
        exit 1
    fi
fi

# 2. 코드만 업데이트 (서비스 중지 없이)
echo ""
echo "2. 코드 업데이트 중..."
# 여기에 scp 명령어들 추가

# 3. 서비스 리로드 (중지 없이)
echo ""
echo "3. 서비스 리로드..."
sudo systemctl reload albratrading

echo ""
echo "✅ 안전 배포 완료!"
echo ""
echo "포지션 모니터링이 계속됩니다."
