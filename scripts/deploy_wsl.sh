#!/bin/bash
# AlbraTrading WSL Deployment Script
# 이 스크립트는 WSL 환경에서 실행되어 EC2로 배포합니다

set -e  # 에러 발생 시 중단

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 설정
EC2_IP="13.209.157.171"
SSH_KEY="$HOME/.ssh/trading-bot4"
LOCAL_DIR="/home/albra/AlbraTrading"
REMOTE_DIR="/home/ubuntu/AlbraTrading"

echo -e "${BLUE}======================================"
echo "   AlbraTrading Deployment (WSL)"
echo "   $(date '+%Y-%m-%d %H:%M:%S')"
echo -e "======================================${NC}"
echo

# 현재 디렉토리 확인
cd "$LOCAL_DIR"

echo -e "${BLUE}[Configuration]${NC}"
echo "- EC2 IP: $EC2_IP"
echo "- Local Dir: $LOCAL_DIR"
echo "- Remote Dir: $REMOTE_DIR"
echo "- SSH Key: $SSH_KEY"
echo

# SSH 키 확인
echo -e "${BLUE}[1/12] Checking SSH key...${NC}"
if [ ! -f "$SSH_KEY" ]; then
    echo -e "${RED}ERROR: SSH key not found: $SSH_KEY${NC}"
    echo "Please ensure your SSH key is in the correct location."
    exit 1
fi
chmod 600 "$SSH_KEY"
echo -e "${GREEN}✓ SSH key found and permissions set${NC}"

# 로컬 검증
echo -e "${BLUE}[2/12] Running local verification...${NC}"
if [ -f "scripts/verify_code.py" ]; then
    python3 scripts/verify_code.py || {
        echo -e "${RED}ERROR: Code verification failed!${NC}"
        exit 1
    }
else
    echo -e "${YELLOW}WARNING: verify_code.py not found, skipping verification...${NC}"
fi

# 필수 파일 확인
echo -e "${BLUE}[3/12] Checking required files...${NC}"
REQUIRED_FILES=(".env" "config/config.yaml" "src/main.py" "requirements.txt")
for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓ $file${NC}"
    else
        echo -e "${RED}✗ $file (MISSING)${NC}"
        exit 1
    fi
done

# SSH 연결 테스트
echo -e "${BLUE}[4/12] Testing SSH connection...${NC}"
ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -i "$SSH_KEY" ubuntu@$EC2_IP "echo 'SSH connection successful'" || {
    echo -e "${RED}ERROR: Cannot connect to EC2 instance!${NC}"
    echo "Please check:"
    echo "1. EC2 instance is running"
    echo "2. Security group allows SSH (port 22)"
    echo "3. EC2 IP is correct: $EC2_IP"
    exit 1
}

# 백업
echo -e "${BLUE}[5/12] Backing up current deployment on EC2...${NC}"
ssh -i "$SSH_KEY" ubuntu@$EC2_IP "if [ -d $REMOTE_DIR ]; then sudo cp -r $REMOTE_DIR/state $REMOTE_DIR/state.backup.\$(date +%Y%m%d_%H%M%S) 2>/dev/null || true; fi"

# 서비스 중지 (Graceful Shutdown)
echo -e "${BLUE}[6/12] Stopping existing services gracefully...${NC}"

# 현재 실행 중인 서비스 확인
ACTIVE_SERVICE=$(ssh -i "$SSH_KEY" ubuntu@$EC2_IP "
    if systemctl is-active --quiet albratrading-single; then
        echo 'albratrading-single'
    elif systemctl is-active --quiet albratrading-multi; then
        echo 'albratrading-multi'
    else
        echo 'none'
    fi
")

if [ "$ACTIVE_SERVICE" != "none" ]; then
    echo "  - Active service detected: $ACTIVE_SERVICE"
    echo "  - Sending SIGTERM for graceful shutdown..."
    
    # SIGTERM 전송 (graceful shutdown 트리거)
    ssh -i "$SSH_KEY" ubuntu@$EC2_IP "sudo systemctl kill --signal=SIGTERM $ACTIVE_SERVICE"
    
    # Graceful shutdown 대기 (최대 10초)
    echo "  - Waiting for graceful shutdown..."
    for i in {1..10}; do
        if ! ssh -i "$SSH_KEY" ubuntu@$EC2_IP "systemctl is-active --quiet $ACTIVE_SERVICE"; then
            echo -e "  ${GREEN}✓ Service stopped gracefully${NC}"
            break
        fi
        sleep 1
    done
    
    # 여전히 실행 중이면 강제 종료
    if ssh -i "$SSH_KEY" ubuntu@$EC2_IP "systemctl is-active --quiet $ACTIVE_SERVICE"; then
        echo -e "  ${YELLOW}⚠ Force stopping service...${NC}"
        ssh -i "$SSH_KEY" ubuntu@$EC2_IP "sudo systemctl stop $ACTIVE_SERVICE"
    fi
else
    echo "  - No active services found"
fi

# 다른 서비스도 확실히 중지
ssh -i "$SSH_KEY" ubuntu@$EC2_IP "sudo systemctl stop albratrading-single 2>/dev/null || true"
ssh -i "$SSH_KEY" ubuntu@$EC2_IP "sudo systemctl stop albratrading-multi 2>/dev/null || true"

# 잠시 대기
sleep 2

# 디렉토리 생성
echo -e "${BLUE}[7/12] Creating remote directory structure...${NC}"
ssh -i "$SSH_KEY" ubuntu@$EC2_IP "mkdir -p $REMOTE_DIR/{src/{core,strategies,utils,web/templates,monitoring,analysis,core/multi_account},config,state,data,logs,scripts/systemd}"

# 파일 업로드
echo -e "${BLUE}[8/12] Uploading project files...${NC}"

echo "  - Uploading source code..."
scp -i "$SSH_KEY" -r src/* ubuntu@$EC2_IP:$REMOTE_DIR/src/

echo "  - Uploading config files..."
scp -i "$SSH_KEY" -r config/* ubuntu@$EC2_IP:$REMOTE_DIR/config/

echo "  - Uploading scripts..."
scp -i "$SSH_KEY" -r scripts/* ubuntu@$EC2_IP:$REMOTE_DIR/scripts/

# systemd 서비스 파일 처리
echo "  - Uploading systemd service files (EC2 version)..."
if [ -f "scripts/systemd/albratrading-single.service.ec2" ]; then
    scp -i "$SSH_KEY" scripts/systemd/albratrading-single.service.ec2 ubuntu@$EC2_IP:$REMOTE_DIR/scripts/systemd/albratrading-single.service
else
    scp -i "$SSH_KEY" scripts/systemd/albratrading-single.service ubuntu@$EC2_IP:$REMOTE_DIR/scripts/systemd/
fi

if [ -f "scripts/systemd/albratrading-multi.service.ec2" ]; then
    scp -i "$SSH_KEY" scripts/systemd/albratrading-multi.service.ec2 ubuntu@$EC2_IP:$REMOTE_DIR/scripts/systemd/albratrading-multi.service
else
    scp -i "$SSH_KEY" scripts/systemd/albratrading-multi.service ubuntu@$EC2_IP:$REMOTE_DIR/scripts/systemd/
fi

echo "  - Uploading requirements.txt..."
scp -i "$SSH_KEY" requirements.txt ubuntu@$EC2_IP:$REMOTE_DIR/

echo "  - Uploading .env file..."
scp -i "$SSH_KEY" .env ubuntu@$EC2_IP:$REMOTE_DIR/

# 권한 설정
echo -e "${BLUE}[9/12] Setting permissions...${NC}"
ssh -i "$SSH_KEY" ubuntu@$EC2_IP "chmod +x $REMOTE_DIR/scripts/*.sh $REMOTE_DIR/scripts/*.py 2>/dev/null || true"
ssh -i "$SSH_KEY" ubuntu@$EC2_IP "chmod -R 755 $REMOTE_DIR/src/"
ssh -i "$SSH_KEY" ubuntu@$EC2_IP "sudo chown -R ubuntu:ubuntu $REMOTE_DIR/"
# 로그 디렉토리 권한 명시적 설정
ssh -i "$SSH_KEY" ubuntu@$EC2_IP "sudo chown -R ubuntu:ubuntu $REMOTE_DIR/logs/ 2>/dev/null || true"

# Python 버전 확인
echo -e "${BLUE}[10/12] Checking Python versions...${NC}"
LOCAL_PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
REMOTE_PYTHON_VERSION=$(ssh -i "$SSH_KEY" ubuntu@$EC2_IP "python3 --version" | cut -d' ' -f2)
echo "Local Python: $LOCAL_PYTHON_VERSION"
echo "EC2 Python: $REMOTE_PYTHON_VERSION"

# 버전 불일치 경고
LOCAL_MAJOR_MINOR=$(echo $LOCAL_PYTHON_VERSION | cut -d'.' -f1,2)
REMOTE_MAJOR_MINOR=$(echo $REMOTE_PYTHON_VERSION | cut -d'.' -f1,2)
if [ "$LOCAL_MAJOR_MINOR" != "$REMOTE_MAJOR_MINOR" ]; then
    echo -e "${YELLOW}⚠️  Warning: Python version mismatch detected!${NC}"
    echo -e "${YELLOW}   Local: Python $LOCAL_PYTHON_VERSION${NC}"
    echo -e "${YELLOW}   EC2: Python $REMOTE_PYTHON_VERSION${NC}"
    echo -e "${YELLOW}   This may cause package compatibility issues.${NC}"
    echo
    read -p "Continue anyway? (y/N): " CONTINUE
    if [ "$CONTINUE" != "y" ] && [ "$CONTINUE" != "Y" ]; then
        echo -e "${RED}Deployment cancelled.${NC}"
        exit 1
    fi
fi

# Python 환경 설정
echo -e "${BLUE}[11/12] Setting up Python environment...${NC}"
# venv가 이미 있으면 삭제하고 새로 생성 (호환성 보장)
if [ -f "$HOME/.python-version" ]; then
    REQUIRED_VERSION=$(cat "$HOME/.python-version")
    echo "Creating venv with Python $REMOTE_PYTHON_VERSION (required: $REQUIRED_VERSION)"
fi
ssh -i "$SSH_KEY" ubuntu@$EC2_IP "cd $REMOTE_DIR && rm -rf venv && python3.10 -m venv venv"
ssh -i "$SSH_KEY" ubuntu@$EC2_IP "cd $REMOTE_DIR && source venv/bin/activate && pip install --upgrade pip"
ssh -i "$SSH_KEY" ubuntu@$EC2_IP "cd $REMOTE_DIR && source venv/bin/activate && pip install -r requirements.txt --upgrade --no-cache-dir --prefer-binary"

# 사전 배포 검사
echo -e "${BLUE}[12/12] Running pre-deployment checks...${NC}"
ssh -i "$SSH_KEY" ubuntu@$EC2_IP "cd $REMOTE_DIR && if [ -f scripts/pre_deploy_check.sh ]; then chmod +x scripts/pre_deploy_check.sh && ./scripts/pre_deploy_check.sh; fi"

# 배포 모드 선택 및 서비스 시작
echo -e "${BLUE}[13/13] Setting up and starting service...${NC}"
echo
echo "Select deployment mode:"
echo "  1. Single Account Mode"
echo "  2. Multi Account Mode"
echo
read -p "Enter choice (1 or 2) [Default: 2]: " MODE_CHOICE
MODE_CHOICE=${MODE_CHOICE:-2}

if [ "$MODE_CHOICE" = "2" ]; then
    echo -e "${GREEN}Setting up multi-account mode...${NC}"
    ssh -i "$SSH_KEY" ubuntu@$EC2_IP "cd $REMOTE_DIR && bash ./scripts/setup_systemd_multi.sh multi"
    SERVICE_NAME="albratrading-multi"
else
    echo -e "${GREEN}Setting up single-account mode...${NC}"
    ssh -i "$SSH_KEY" ubuntu@$EC2_IP "cd $REMOTE_DIR && bash ./scripts/setup_systemd_multi.sh single"
    SERVICE_NAME="albratrading-single"
fi

echo
echo "Waiting for service to stabilize..."
sleep 10

# 서비스 상태 확인
echo -e "${BLUE}======================================"
echo "         DEPLOYMENT SUMMARY"
echo -e "======================================${NC}"
echo

echo -e "${BLUE}[Service Status]${NC}"
if ssh -i "$SSH_KEY" ubuntu@$EC2_IP "sudo systemctl is-active --quiet $SERVICE_NAME"; then
    echo -e "${GREEN}✓ Service: ACTIVE${NC}"
    ssh -i "$SSH_KEY" ubuntu@$EC2_IP "sudo systemctl status $SERVICE_NAME --no-pager | head -10"
else
    echo -e "${RED}✗ Service: FAILED${NC}"
    echo
    echo "[Error Logs]"
    ssh -i "$SSH_KEY" ubuntu@$EC2_IP "sudo journalctl -u $SERVICE_NAME -n 20 --no-pager"
fi

# 배포 검사
echo
echo -e "${BLUE}[Deployment Check]${NC}"
ssh -i "$SSH_KEY" ubuntu@$EC2_IP "cd $REMOTE_DIR && if [ -f scripts/check_deployment_multi.sh ]; then chmod +x scripts/check_deployment_multi.sh && ./scripts/check_deployment_multi.sh; fi"

# 알림 전송
if [ -f "scripts/deployment_notify.py" ]; then
    echo
    echo -e "${BLUE}[Sending notification]${NC}"
    if ssh -i "$SSH_KEY" ubuntu@$EC2_IP "sudo systemctl is-active --quiet $SERVICE_NAME"; then
        python3 scripts/deployment_notify.py --status success --mode ${MODE_CHOICE/1/single} --mode ${MODE_CHOICE/2/multi} --message "Deployment completed successfully"
    else
        python3 scripts/deployment_notify.py --status failed --mode ${MODE_CHOICE/1/single} --mode ${MODE_CHOICE/2/multi} --message "Deployment failed - check logs"
    fi
fi

echo
echo -e "${BLUE}======================================"
echo "Deployment completed at $(date '+%Y-%m-%d %H:%M:%S')"
echo
echo "Quick commands:"
echo "  Status:  ssh -i $SSH_KEY ubuntu@$EC2_IP \"sudo systemctl status $SERVICE_NAME\""
echo "  Logs:    ssh -i $SSH_KEY ubuntu@$EC2_IP \"sudo journalctl -u $SERVICE_NAME -f\""
echo "  Connect: ssh -i $SSH_KEY ubuntu@$EC2_IP"
echo -e "======================================${NC}"