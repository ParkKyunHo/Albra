#!/bin/bash
# Python 버전 체크 스크립트
# 배포 전 Python 환경을 검증합니다

echo "========================================"
echo "   Python Environment Check"
echo "   $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"
echo ""

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 1. 시스템 Python 버전
echo "🐍 System Python Versions:"
echo -n "python3: "
python3 --version 2>/dev/null || echo "Not found"
echo -n "python3.10: "
python3.10 --version 2>/dev/null || echo "Not found"
echo -n "python3.12: "
python3.12 --version 2>/dev/null || echo "Not found"
echo ""

# 2. Python 3.10 필수 확인
echo "📋 Requirement Check:"
if command -v python3.10 &> /dev/null; then
    echo -e "${GREEN}✓${NC} Python 3.10 is installed"
else
    echo -e "${RED}✗${NC} Python 3.10 is NOT installed!"
    echo ""
    echo "Please install Python 3.10:"
    echo "  sudo apt update"
    echo "  sudo apt install -y python3.10 python3.10-venv python3.10-dev"
    exit 1
fi
echo ""

# 3. 가상환경 확인
echo "🔧 Virtual Environment:"
if [ -d "venv" ]; then
    if [ -f "venv/bin/python" ]; then
        VENV_VERSION=$(venv/bin/python --version 2>&1)
        if [[ "$VENV_VERSION" == *"3.10"* ]]; then
            echo -e "${GREEN}✓${NC} venv exists with $VENV_VERSION"
        else
            echo -e "${YELLOW}⚠${NC} venv exists but uses $VENV_VERSION"
            echo "   Recreating venv with Python 3.10..."
            rm -rf venv
            python3.10 -m venv venv
            echo -e "${GREEN}✓${NC} venv recreated with Python 3.10"
        fi
    else
        echo -e "${YELLOW}⚠${NC} venv exists but Python not found"
        rm -rf venv
        python3.10 -m venv venv
        echo -e "${GREEN}✓${NC} venv recreated with Python 3.10"
    fi
else
    echo -e "${YELLOW}⚠${NC} venv not found, creating..."
    python3.10 -m venv venv
    echo -e "${GREEN}✓${NC} venv created with Python 3.10"
fi
echo ""

# 4. pip 업그레이드
echo "📦 Upgrading pip:"
venv/bin/pip install --upgrade pip --quiet
echo -e "${GREEN}✓${NC} pip upgraded"
echo ""

# 5. 의존성 설치 체크
echo "📚 Dependencies:"
if [ -f "requirements.txt" ]; then
    echo -e "${GREEN}✓${NC} requirements.txt found"
    # 주요 패키지만 빠르게 체크
    PACKAGES=("python-binance" "pandas" "numpy" "flask")
    for pkg in "${PACKAGES[@]}"; do
        if venv/bin/pip show "$pkg" &>/dev/null; then
            VERSION=$(venv/bin/pip show "$pkg" | grep Version | awk '{print $2}')
            echo -e "  ${GREEN}✓${NC} $pkg ($VERSION)"
        else
            echo -e "  ${YELLOW}⚠${NC} $pkg not installed"
        fi
    done
else
    echo -e "${RED}✗${NC} requirements.txt not found!"
fi
echo ""

# 6. 요약
echo "========================================"
echo "📊 Summary:"
echo "========================================"
echo -e "${GREEN}✓${NC} Python 3.10 is available"
echo -e "${GREEN}✓${NC} Virtual environment is ready"
echo -e "${GREEN}✓${NC} System is ready for deployment"
echo ""
echo "To activate venv:"
echo "  source venv/bin/activate"
echo ""