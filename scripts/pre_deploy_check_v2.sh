#!/bin/bash
# AlbraTrading 배포 전 검증 스크립트 v2.0
# 경로 호환성 및 환경 검증 강화

echo "======================================"
echo "   Pre-deployment Validation v2.0"
echo "   $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================"
echo ""

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ERRORS=0
WARNINGS=0

# 현재 환경 감지
CURRENT_USER=$(whoami)
CURRENT_PATH=$(pwd)

echo "🔍 Environment Detection:"
echo "- User: $CURRENT_USER"
echo "- Path: $CURRENT_PATH"

if [[ "$CURRENT_USER" == "ubuntu" ]]; then
    ENVIRONMENT="ec2"
    BASE_PATH="/home/ubuntu/AlbraTrading"
elif [[ "$CURRENT_USER" == "albra" ]]; then
    ENVIRONMENT="local"
    BASE_PATH="/home/albra/AlbraTrading"
else
    ENVIRONMENT="unknown"
    BASE_PATH="$CURRENT_PATH"
fi

echo -e "- Environment: ${BLUE}$ENVIRONMENT${NC}"
echo ""

# 1. Python 버전 확인
echo "🐍 Python Version Check:"
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
REQUIRED_VERSION="3.12"

if [[ "$PYTHON_VERSION" == "$REQUIRED_VERSION"* ]] || [[ "$PYTHON_VERSION" == "3.11"* ]]; then
    echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION (OK)"
else
    echo -e "${RED}✗${NC} Python $PYTHON_VERSION (Required: $REQUIRED_VERSION+)"
    ((ERRORS++))
fi
echo ""

# 2. 가상환경 확인
echo "📦 Virtual Environment:"
if [ -d "$BASE_PATH/venv" ]; then
    echo -e "${GREEN}✓${NC} venv directory exists"
    
    if [ -f "$BASE_PATH/venv/bin/python" ]; then
        VENV_PYTHON_VERSION=$($BASE_PATH/venv/bin/python --version 2>&1 | awk '{print $2}')
        echo -e "${GREEN}✓${NC} venv Python: $VENV_PYTHON_VERSION"
    else
        echo -e "${RED}✗${NC} venv Python not found"
        ((ERRORS++))
    fi
else
    echo -e "${YELLOW}⚠${NC} venv directory not found (will be created during deployment)"
    ((WARNINGS++))
fi
echo ""

# 3. 필수 파일 확인
echo "📄 Required Files:"
REQUIRED_FILES=(
    ".env"
    "config/config.yaml"
    "src/main.py"
    "requirements.txt"
    "scripts/setup_systemd_multi.sh"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$BASE_PATH/$file" ]; then
        echo -e "${GREEN}✓${NC} $file"
    else
        echo -e "${RED}✗${NC} $file (MISSING)"
        ((ERRORS++))
    fi
done

# systemd 서비스 파일 확인
echo ""
echo "🔧 Systemd Service Files:"
if [ "$ENVIRONMENT" == "ec2" ]; then
    SERVICE_SUFFIX="ec2"
else
    SERVICE_SUFFIX="local"
fi

SYSTEMD_FILES=(
    "scripts/systemd/albratrading-single.service.$SERVICE_SUFFIX"
    "scripts/systemd/albratrading-multi.service.$SERVICE_SUFFIX"
)

for file in "${SYSTEMD_FILES[@]}"; do
    if [ -f "$BASE_PATH/$file" ]; then
        echo -e "${GREEN}✓${NC} $file"
    else
        # 기본 서비스 파일 확인
        DEFAULT_FILE="${file%.$SERVICE_SUFFIX}"
        if [ -f "$BASE_PATH/$DEFAULT_FILE" ]; then
            echo -e "${YELLOW}⚠${NC} $file not found, but default exists: $DEFAULT_FILE"
            ((WARNINGS++))
        else
            echo -e "${RED}✗${NC} $file (MISSING)"
            ((ERRORS++))
        fi
    fi
done
echo ""

# 4. 환경 변수 확인
echo "🔑 Environment Variables:"
if [ -f "$BASE_PATH/.env" ]; then
    REQUIRED_VARS=(
        "BINANCE_API_KEY"
        "BINANCE_SECRET_KEY"
        "TELEGRAM_BOT_TOKEN"
        "TELEGRAM_CHAT_ID"
    )
    
    for var in "${REQUIRED_VARS[@]}"; do
        if grep -q "^${var}=" "$BASE_PATH/.env" && ! grep -q "^${var}=$" "$BASE_PATH/.env"; then
            echo -e "${GREEN}✓${NC} $var is set"
        else
            echo -e "${RED}✗${NC} $var is missing or empty"
            ((ERRORS++))
        fi
    done
    
    # Multi-account 환경변수 확인
    if grep -q "^SUB1_API_KEY=" "$BASE_PATH/.env"; then
        echo -e "${BLUE}ℹ${NC} SUB1_API_KEY is configured (multi-account ready)"
    fi
else
    echo -e "${RED}✗${NC} .env file not found"
    ((ERRORS++))
fi
echo ""

# 5. 설정 파일 검증
echo "⚙️ Configuration Validation:"
if [ -f "$BASE_PATH/config/config.yaml" ]; then
    # Multi-account 설정 확인
    MULTI_ENABLED=$(grep -A1 "multi_account:" "$BASE_PATH/config/config.yaml" | grep "enabled:" | awk '{print $2}')
    
    if [ "$MULTI_ENABLED" == "true" ]; then
        echo -e "${GREEN}✓${NC} Multi-account mode enabled"
        
        # 계좌 수 확인
        ACCOUNT_COUNT=$(grep -c "account_id:" "$BASE_PATH/config/config.yaml" || echo "0")
        echo "  - Configured accounts: $ACCOUNT_COUNT"
    else
        echo -e "${BLUE}ℹ${NC} Single account mode"
    fi
    
    # 전략 확인
    echo ""
    echo "📊 Active Strategies:"
    for strategy in tfpe momentum zlmacd zlhma; do
        if grep -q "${strategy}:" "$BASE_PATH/config/config.yaml"; then
            ENABLED=$(grep -A2 "${strategy}:" "$BASE_PATH/config/config.yaml" | grep "enabled:" | head -1 | awk '{print $2}')
            if [ "$ENABLED" == "true" ]; then
                echo -e "  ${GREEN}✓${NC} $strategy"
            else
                echo -e "  ${YELLOW}○${NC} $strategy (disabled)"
            fi
        fi
    done
else
    echo -e "${RED}✗${NC} config.yaml not found"
    ((ERRORS++))
fi
echo ""

# 6. 디렉토리 권한 확인
echo "📁 Directory Permissions:"
REQUIRED_DIRS=("logs" "state" "data")
for dir in "${REQUIRED_DIRS[@]}"; do
    DIR_PATH="$BASE_PATH/$dir"
    if [ -d "$DIR_PATH" ]; then
        if [ -w "$DIR_PATH" ]; then
            echo -e "${GREEN}✓${NC} $dir (writable)"
        else
            echo -e "${RED}✗${NC} $dir (not writable)"
            ((ERRORS++))
        fi
    else
        echo -e "${YELLOW}⚠${NC} $dir (will be created)"
        mkdir -p "$DIR_PATH"
    fi
done
echo ""

# 7. 디스크 공간 확인
echo "💾 Disk Space Check:"
DISK_USAGE=$(df -h "$BASE_PATH" | tail -1)
DISK_PERCENT=$(echo "$DISK_USAGE" | awk '{print $5}' | sed 's/%//')
DISK_AVAILABLE=$(echo "$DISK_USAGE" | awk '{print $4}')

if [ "$DISK_PERCENT" -lt 80 ]; then
    echo -e "${GREEN}✓${NC} Disk usage: ${DISK_PERCENT}% (Available: $DISK_AVAILABLE)"
elif [ "$DISK_PERCENT" -lt 90 ]; then
    echo -e "${YELLOW}⚠${NC} Disk usage: ${DISK_PERCENT}% (Available: $DISK_AVAILABLE)"
    ((WARNINGS++))
else
    echo -e "${RED}✗${NC} Critical: Disk usage ${DISK_PERCENT}% (Available: $DISK_AVAILABLE)"
    ((ERRORS++))
fi
echo ""

# 8. 포트 가용성 확인
echo "🌐 Port Availability:"
if ! sudo lsof -i :5000 >/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Port 5000 is available (Web Dashboard)"
else
    echo -e "${YELLOW}⚠${NC} Port 5000 is in use"
    sudo lsof -i :5000 | head -5
    ((WARNINGS++))
fi
echo ""

# 9. Python 종속성 테스트
if [ -f "$BASE_PATH/venv/bin/python" ]; then
    echo "📚 Python Dependencies Test:"
    
    # 핵심 모듈 임포트 테스트
    $BASE_PATH/venv/bin/python -c "
import sys
sys.path.insert(0, '$BASE_PATH')
errors = []

try:
    from src.utils.config_manager import ConfigManager
    print('✓ ConfigManager import successful')
except Exception as e:
    errors.append(f'✗ ConfigManager import failed: {e}')

try:
    from src.utils.logger import setup_logger
    print('✓ Logger import successful')
except Exception as e:
    errors.append(f'✗ Logger import failed: {e}')

try:
    import ccxt
    print('✓ ccxt library available')
except:
    errors.append('✗ ccxt library missing')

try:
    import pandas
    print('✓ pandas library available')
except:
    errors.append('✗ pandas library missing')

for error in errors:
    print(error)
    
sys.exit(len(errors))
" || ((ERRORS+=$?))
    echo ""
fi

# 최종 결과
echo "======================================"
echo "📊 Validation Summary"
echo "======================================"

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✅ Perfect! All checks passed.${NC}"
    echo ""
    echo "Ready for deployment to: $ENVIRONMENT"
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠️ Validation passed with $WARNINGS warnings.${NC}"
    echo ""
    echo "You can proceed with deployment, but review warnings."
else
    echo -e "${RED}❌ Found $ERRORS errors and $WARNINGS warnings.${NC}"
    echo ""
    echo "Please fix errors before deployment."
fi

echo ""
echo "Environment: $ENVIRONMENT"
echo "Base Path: $BASE_PATH"
echo "Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"

exit $ERRORS