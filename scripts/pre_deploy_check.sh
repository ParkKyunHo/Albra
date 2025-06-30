#!/bin/bash
# AlbraTrading 배포 전 검증 스크립트
# 배포 전 모든 의존성과 설정을 검증

echo "======================================"
echo "   Pre-deployment Validation"
echo "   $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================"
echo ""

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ERRORS=0

# 1. Python 버전 확인
echo "🐍 Python Version Check:"
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
REQUIRED_VERSION="3.10"

if [[ "$PYTHON_VERSION" == "$REQUIRED_VERSION"* ]]; then
    echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION (OK)"
else
    echo -e "${RED}✗${NC} Python $PYTHON_VERSION (Required: $REQUIRED_VERSION+)"
    ((ERRORS++))
fi
echo ""

# 2. 가상환경 확인
echo "📦 Virtual Environment:"
if [ -d "venv" ]; then
    echo -e "${GREEN}✓${NC} venv directory exists"
    
    # 가상환경 내 Python 확인
    if [ -f "venv/bin/python" ]; then
        VENV_PYTHON_VERSION=$(venv/bin/python --version 2>&1 | awk '{print $2}')
        echo -e "${GREEN}✓${NC} venv Python: $VENV_PYTHON_VERSION"
    else
        echo -e "${RED}✗${NC} venv Python not found"
        ((ERRORS++))
    fi
else
    echo -e "${RED}✗${NC} venv directory not found"
    ((ERRORS++))
fi
echo ""

# 3. 필수 파일 확인
echo "📄 Required Files:"
REQUIRED_FILES=(
    ".env"
    "config/config.yaml"
    "src/main_multi_account.py"
    "requirements.txt"
    "scripts/setup_systemd_multi.sh"
    "scripts/systemd/albratrading-single.service"
    "scripts/systemd/albratrading-multi.service"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $file"
    else
        echo -e "${RED}✗${NC} $file (MISSING)"
        ((ERRORS++))
    fi
done
echo ""

# 4. 환경 변수 확인
echo "🔑 Environment Variables:"
if [ -f ".env" ]; then
    # 필수 환경 변수
    REQUIRED_VARS=(
        "BINANCE_API_KEY"
        "BINANCE_SECRET_KEY"
        "TELEGRAM_BOT_TOKEN"
        "TELEGRAM_CHAT_ID"
    )
    
    for var in "${REQUIRED_VARS[@]}"; do
        if grep -q "^${var}=" .env && ! grep -q "^${var}=$" .env; then
            echo -e "${GREEN}✓${NC} $var is set"
        else
            echo -e "${RED}✗${NC} $var is missing or empty"
            ((ERRORS++))
        fi
    done
    
    # 선택적 환경 변수 (멀티 계좌)
    if grep -q "^SUB1_API_KEY=" .env; then
        echo -e "${BLUE}ℹ${NC} SUB1_API_KEY is configured (multi-account ready)"
    fi
else
    echo -e "${RED}✗${NC} .env file not found"
    ((ERRORS++))
fi
echo ""

# 5. 설정 검증 (Python으로 실제 검증)
echo "⚙️ Configuration Validation:"
if [ -f "venv/bin/python" ]; then
    # 임포트 테스트
    echo "Testing imports..."
    venv/bin/python -c "
import sys
sys.path.insert(0, '.')
try:
    from src.utils.config_manager import ConfigManager
    from src.utils.logger import setup_logger
    print('✓ Basic imports successful')
except Exception as e:
    print(f'✗ Import error: {e}')
    sys.exit(1)
" || ((ERRORS++))

    # 설정 파일 검증 (import 테스트만 수행)
    venv/bin/python -c "
import sys
sys.path.insert(0, '.')
try:
    # 핵심 모듈 import 테스트
    from src.main_multi_account import MultiAccountTradingSystem
    from src.core.binance_api import BinanceAPI
    from src.strategies.strategy_factory import get_strategy_factory
    from src.utils.config_manager import ConfigManager
    from src.monitoring.position_sync_monitor import PositionSyncMonitor
    
    # 설정 파일 존재 여부만 확인
    import os
    if os.path.exists('config/config.yaml') and os.path.exists('.env'):
        print('✓ Configuration files found')
    else:
        print('✗ Configuration files missing')
        sys.exit(1)
    
    print('✓ All imports successful')
except ImportError as e:
    print(f'✗ Import error: {e}')
    sys.exit(1)
except Exception as e:
    print(f'✗ Unexpected error: {e}')
    sys.exit(1)
"
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} Configuration validation passed"
    else
        echo -e "${RED}✗${NC} Configuration validation failed"
        ((ERRORS++))
    fi
fi
echo ""

# 6. 디렉토리 권한 확인
echo "📁 Directory Permissions:"
REQUIRED_DIRS=("logs" "state" "data")
for dir in "${REQUIRED_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        if [ -w "$dir" ]; then
            echo -e "${GREEN}✓${NC} $dir (writable)"
        else
            echo -e "${RED}✗${NC} $dir (not writable)"
            ((ERRORS++))
        fi
    else
        echo -e "${YELLOW}⚠${NC} $dir (will be created)"
        mkdir -p "$dir"
    fi
done
echo ""

# 7. systemd 파일 검증
echo "🔧 Systemd Service Files:"
SERVICE_FILES=(
    "scripts/systemd/albratrading-single.service"
    "scripts/systemd/albratrading-multi.service"
)

for file in "${SERVICE_FILES[@]}"; do
    if [ -f "$file" ]; then
        # ExecStart 경로 확인
        EXEC_PATH=$(grep "ExecStart=" "$file" | cut -d= -f2 | awk '{print $1}')
        SCRIPT_PATH=$(grep "ExecStart=" "$file" | cut -d= -f2 | awk '{print $2}')
        
        if [[ "$SCRIPT_PATH" == *"main_multi_account.py"* ]]; then
            echo -e "${GREEN}✓${NC} $file uses main_multi_account.py"
        else
            echo -e "${YELLOW}⚠${NC} $file uses legacy main.py"
        fi
    fi
done
echo ""

# 8. 포트 가용성 확인
echo "🌐 Port Availability:"
if ! sudo lsof -i :5000 >/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Port 5000 is available"
else
    echo -e "${YELLOW}⚠${NC} Port 5000 is in use"
    sudo lsof -i :5000 | tail -n +2
fi
echo ""

# 최종 결과
echo "======================================"
echo "📊 Validation Summary"
echo "======================================"

if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✅ All checks passed! Ready for deployment.${NC}"
    echo ""
    echo "Next steps:"
    echo "1. cd /home/ubuntu/AlbraTrading"
    echo "2. ./scripts/setup_systemd_multi.sh single  # For single mode"
    echo "   OR"
    echo "   ./scripts/setup_systemd_multi.sh multi   # For multi mode"
    exit 0
else
    echo -e "${RED}❌ Found $ERRORS errors. Please fix them before deployment.${NC}"
    echo ""
    echo "Common fixes:"
    echo "- Create .env file from .env.example"
    echo "- Install Python 3.12"
    echo "- Create virtual environment: python3.12 -m venv venv"
    echo "- Install dependencies: venv/bin/pip install -r requirements.txt"
    exit 1
fi
