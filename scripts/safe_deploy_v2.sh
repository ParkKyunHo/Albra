#!/bin/bash
# AlbraTrading v2.0 안전 배포 스크립트
# 포지션이 있을 때도 안전하게 배포

echo "======================================"
echo "   AlbraTrading Safe Deploy v2.0"
echo "   $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================"
echo ""

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 현재 디렉토리 확인
cd /home/ubuntu/AlbraTrading || exit 1

# 현재 활성 모드 확인
ACTIVE_MODE="none"
if sudo systemctl is-active --quiet albratrading-single 2>/dev/null; then
    ACTIVE_MODE="single"
    SERVICE_NAME="albratrading-single"
elif sudo systemctl is-active --quiet albratrading-multi 2>/dev/null; then
    ACTIVE_MODE="multi"
    SERVICE_NAME="albratrading-multi"
else
    # 레거시 서비스 확인
    if sudo systemctl is-active --quiet albratrading 2>/dev/null; then
        ACTIVE_MODE="legacy"
        SERVICE_NAME="albratrading"
    fi
fi

echo -e "현재 모드: ${BLUE}$ACTIVE_MODE${NC}"
echo ""

# 1. 포지션 확인
echo "📊 Step 1: 포지션 확인"
echo "----------------------------------------"
source venv/bin/activate

# Python 스크립트로 포지션 확인
python3 << 'EOF'
import asyncio
import sys
import os
import json
sys.path.insert(0, '.')

try:
    from src.core.binance_api import BinanceAPI
    from src.utils.config_manager import ConfigManager
    from src.core.multi_account.account_manager import MultiAccountManager
    from dotenv import load_dotenv
    
    load_dotenv()
    
    async def check_all_positions():
        config_manager = ConfigManager()
        positions_info = {}
        total_positions = 0
        
        # 멀티 계좌 모드 확인
        multi_enabled = config_manager.config.get('multi_account', {}).get('enabled', False)
        
        if multi_enabled:
            print("🏦 멀티 계좌 모드 포지션 확인")
            # 멀티 계좌 포지션 확인
            accounts = ['main'] + [acc.get('account_id') for acc in 
                                 config_manager.config.get('multi_account', {}).get('sub_accounts', [])]
            
            for account_id in accounts:
                if account_id == 'main':
                    api_key = os.getenv('BINANCE_API_KEY')
                    secret_key = os.getenv('BINANCE_SECRET_KEY')
                else:
                    api_key = os.getenv(f'{account_id.upper()}_API_KEY')
                    secret_key = os.getenv(f'{account_id.upper()}_API_SECRET')
                
                if not api_key or not secret_key:
                    continue
                    
                api = BinanceAPI(api_key=api_key, secret_key=secret_key, testnet=False)
                await api.initialize()
                
                positions = await api.get_positions()
                active = [p for p in positions if float(p['positionAmt']) != 0]
                
                if active:
                    positions_info[account_id] = active
                    total_positions += len(active)
                    print(f"\n  [{account_id}] {len(active)}개 포지션:")
                    for pos in active:
                        print(f"    - {pos['symbol']}: {pos['positionAmt']} @ {pos['entryPrice']}")
        else:
            print("💼 단일 계좌 모드 포지션 확인")
            # 단일 계좌 포지션 확인
            api = BinanceAPI(
                api_key=os.getenv('BINANCE_API_KEY'),
                secret_key=os.getenv('BINANCE_SECRET_KEY'),
                testnet=False
            )
            await api.initialize()
            positions = await api.get_positions()
            active = [p for p in positions if float(p['positionAmt']) != 0]
            
            if active:
                positions_info['main'] = active
                total_positions = len(active)
                print(f"\n  {len(active)}개 포지션:")
                for pos in active:
                    print(f"    - {pos['symbol']}: {pos['positionAmt']} @ {pos['entryPrice']}")
        
        # 결과 저장
        with open('/tmp/deploy_positions.json', 'w') as f:
            json.dump({
                'total': total_positions,
                'accounts': list(positions_info.keys())
            }, f)
        
        return total_positions
    
    count = asyncio.run(check_all_positions())
    print(f"\n총 활성 포지션: {count}개")
    exit(0 if count == 0 else 1)
    
except Exception as e:
    print(f"❌ 포지션 확인 중 오류: {e}")
    exit(2)
EOF

POSITION_CHECK=$?

if [ $POSITION_CHECK -eq 1 ]; then
    echo ""
    echo -e "${YELLOW}⚠️  경고: 활성 포지션이 있습니다!${NC}"
    echo ""
    echo "옵션:"
    echo "1) 안전 배포 진행 (서비스 재시작 없음)"
    echo "2) 일반 배포 진행 (서비스 재시작)"
    echo "3) 배포 취소"
    echo ""
    echo -n "선택 [1-3]: "
    read -r choice
    
    case $choice in
        1) SAFE_MODE=true ;;
        2) SAFE_MODE=false ;;
        3) echo "배포 취소됨"; exit 0 ;;
        *) echo "잘못된 선택"; exit 1 ;;
    esac
elif [ $POSITION_CHECK -eq 2 ]; then
    echo -e "${RED}포지션 확인 실패${NC}"
    exit 1
else
    echo -e "${GREEN}✅ 활성 포지션 없음${NC}"
    SAFE_MODE=false
fi

# 2. 백업
echo ""
echo "💾 Step 2: 백업"
echo "----------------------------------------"
BACKUP_DIR="backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# 중요 파일 백업
cp config/config.yaml "$BACKUP_DIR/"
cp -r state/ "$BACKUP_DIR/"
echo -e "${GREEN}✓${NC} 백업 완료: $BACKUP_DIR"

# 3. 코드 업데이트
echo ""
echo "🔄 Step 3: 코드 업데이트"
echo "----------------------------------------"
echo "Git pull 수행..."
git pull origin main

if [ $? -ne 0 ]; then
    echo -e "${RED}Git pull 실패${NC}"
    exit 1
fi

# 4. 의존성 업데이트
echo ""
echo "📦 Step 4: 의존성 확인"
echo "----------------------------------------"
pip install -r requirements.txt --quiet
echo -e "${GREEN}✓${NC} 의존성 업데이트 완료"

# 5. 설정 검증
echo ""
echo "⚙️ Step 5: 설정 검증"
echo "----------------------------------------"
python src/main.py --validate

if [ $? -ne 0 ]; then
    echo -e "${RED}설정 검증 실패${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} 설정 검증 통과"

# 6. 서비스 업데이트
echo ""
echo "🔧 Step 6: 서비스 업데이트"
echo "----------------------------------------"

if [ "$ACTIVE_MODE" = "none" ]; then
    echo -e "${YELLOW}서비스가 실행 중이 아닙니다. 새로 시작하시겠습니까? (y/N)${NC}"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        ./scripts/setup_systemd_multi.sh single
    fi
else
    if [ "$SAFE_MODE" = true ]; then
        echo "안전 모드: 서비스 리로드만 수행"
        sudo systemctl reload $SERVICE_NAME
        
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✓${NC} 서비스 리로드 완료"
        else
            echo -e "${YELLOW}⚠${NC} 리로드 실패, 재시작 시도"
            sudo systemctl restart $SERVICE_NAME
        fi
    else
        echo "일반 모드: 서비스 재시작"
        sudo systemctl restart $SERVICE_NAME
        echo -e "${GREEN}✓${NC} 서비스 재시작 완료"
    fi
fi

# 7. 배포 확인
echo ""
echo "✅ Step 7: 배포 확인"
echo "----------------------------------------"
sleep 5  # 서비스 시작 대기

# 배포 체크 스크립트 실행
if [ -f "scripts/check_deployment_multi.sh" ]; then
    ./scripts/check_deployment_multi.sh
else
    # 레거시 체크
    if sudo systemctl is-active --quiet $SERVICE_NAME; then
        echo -e "${GREEN}✅ 서비스 정상 작동 중${NC}"
    else
        echo -e "${RED}❌ 서비스 시작 실패${NC}"
        sudo journalctl -u $SERVICE_NAME -n 50
    fi
fi

# 8. 최종 메시지
echo ""
echo "======================================"
echo "📋 배포 완료 요약"
echo "======================================"
echo -e "모드: ${BLUE}$ACTIVE_MODE${NC}"
echo -e "서비스: ${BLUE}$SERVICE_NAME${NC}"
if [ "$SAFE_MODE" = true ]; then
    echo -e "배포 방식: ${YELLOW}안전 모드 (리로드)${NC}"
else
    echo -e "배포 방식: ${GREEN}일반 모드 (재시작)${NC}"
fi
echo ""
echo "모니터링 명령어:"
echo "- 로그 확인: sudo journalctl -u $SERVICE_NAME -f"
echo "- 상태 확인: ./scripts/setup_systemd_multi.sh status"
if [ "$ACTIVE_MODE" = "multi" ]; then
    echo "- CLI 도구: python scripts/multi_account_cli.py status"
fi
echo ""
echo -e "${GREEN}✅ 배포가 완료되었습니다!${NC}"
