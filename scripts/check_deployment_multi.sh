#!/bin/bash
# AlbraTrading System - Deployment Verification Script v3.0
# Multi-mode systemd 기반 시스템용 체크 스크립트

echo "======================================"
echo "   AlbraTrading Deployment Check v3.0"
echo "   $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "======================================"
echo ""

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 결과 카운터
CRITICAL_ISSUES=0
WARNINGS=0

# 현재 활성 모드 확인
ACTIVE_MODE="none"
if sudo systemctl is-active --quiet albratrading-single 2>/dev/null; then
    ACTIVE_MODE="single"
elif sudo systemctl is-active --quiet albratrading-multi 2>/dev/null; then
    ACTIVE_MODE="multi"
fi

# 1. Systemd 서비스 상태 확인 (가장 중요)
echo "🔧 Systemd Service Status:"
echo "-------------------------"

if [ "$ACTIVE_MODE" = "none" ]; then
    echo -e "${RED}✗${NC} No AlbraTrading service is active!"
    echo "  Available services:"
    
    # 단일 모드 서비스 확인
    if sudo systemctl list-unit-files | grep -q albratrading-single; then
        SINGLE_STATUS=$(sudo systemctl is-enabled albratrading-single 2>/dev/null)
        echo "  - albratrading-single: $SINGLE_STATUS"
    fi
    
    # 멀티 모드 서비스 확인
    if sudo systemctl list-unit-files | grep -q albratrading-multi; then
        MULTI_STATUS=$(sudo systemctl is-enabled albratrading-multi 2>/dev/null)
        echo "  - albratrading-multi: $MULTI_STATUS"
    fi
    
    ((CRITICAL_ISSUES++))
else
    SERVICE_NAME="albratrading-$ACTIVE_MODE"
    echo -e "${GREEN}✓${NC} Active mode: ${BLUE}$ACTIVE_MODE${NC}"
    echo -e "${GREEN}✓${NC} Service $SERVICE_NAME is active"
    
    # 상세 정보
    SERVICE_INFO=$(sudo systemctl status $SERVICE_NAME --no-pager | head -15)
    echo "$SERVICE_INFO" | grep -E "Active:|Main PID:|Memory:|CPU:" | while read line; do
        echo "  $line"
    done
fi
echo ""

# 2. Python 프로세스 확인 (main_multi_account.py 확인)
echo "🐍 Python Processes:"
echo "-------------------"
# main_multi_account.py 또는 main.py 프로세스 찾기
PYTHON_PROCS=$(sudo ps aux | grep -E "python.*main(_multi_account)?\.py" | grep -v grep)
if [ -n "$PYTHON_PROCS" ]; then
    echo "$PYTHON_PROCS" | while read proc; do
        PID=$(echo $proc | awk '{print $2}')
        MEM=$(echo $proc | awk '{print $4}')
        CPU=$(echo $proc | awk '{print $3}')
        CMD=$(echo $proc | awk '{for(i=11;i<=NF;i++) printf "%s ", $i; print ""}')
        
        # main_multi_account.py인지 main.py인지 확인
        if echo "$CMD" | grep -q "main_multi_account.py"; then
            echo -e "${GREEN}✓${NC} PID $PID - ${BLUE}main_multi_account.py${NC} - CPU: $CPU%, MEM: $MEM%"
        else
            echo -e "${GREEN}✓${NC} PID $PID - main.py (legacy) - CPU: $CPU%, MEM: $MEM%"
        fi
    done
    
    # 프로세스 상세 정보
    MAIN_PID=$(echo "$PYTHON_PROCS" | head -1 | awk '{print $2}')
    if [ -n "$MAIN_PID" ]; then
        PROCESS_TIME=$(ps -o etime= -p $MAIN_PID 2>/dev/null | xargs)
        echo "  Uptime: $PROCESS_TIME"
    fi
else
    echo -e "${RED}✗${NC} No trading process found!"
    ((CRITICAL_ISSUES++))
fi
echo ""

# 3. 모드별 로그 확인
echo "📝 System Logs:"
echo "--------------"

if [ "$ACTIVE_MODE" != "none" ]; then
    SERVICE_NAME="albratrading-$ACTIVE_MODE"
    
    # 최근 에러 확인
    RECENT_ERRORS=$(sudo journalctl -u $SERVICE_NAME -p err -n 5 --no-pager 2>/dev/null)
    if [ -n "$RECENT_ERRORS" ] && [ "$RECENT_ERRORS" != "-- No entries --" ]; then
        echo -e "${YELLOW}⚠${NC} Recent errors found in $SERVICE_NAME:"
        echo "$RECENT_ERRORS" | tail -5
        ((WARNINGS++))
    else
        echo -e "${GREEN}✓${NC} No recent errors in system logs"
    fi
    
    # 로그 파일 확인
    if [ "$ACTIVE_MODE" = "single" ]; then
        LOG_FILE="/home/ubuntu/AlbraTrading/logs/systemd_single.log"
    else
        LOG_FILE="/home/ubuntu/AlbraTrading/logs/systemd_multi.log"
    fi
    
    if [ -f "$LOG_FILE" ]; then
        LOG_SIZE=$(du -h "$LOG_FILE" | cut -f1)
        LAST_LINES=$(tail -1 "$LOG_FILE" 2>/dev/null)
        echo -e "${GREEN}✓${NC} Log file: $LOG_FILE ($LOG_SIZE)"
        if [ -n "$LAST_LINES" ]; then
            echo "  Last entry: $(echo "$LAST_LINES" | cut -c1-60)..."
        fi
    fi
fi
echo ""

# 4. 포트 확인 (Flask 대시보드)
echo "🌐 Network Ports:"
echo "----------------"
PORT_CHECK=$(sudo ss -tlnp | grep :5000 2>/dev/null)
if [ -n "$PORT_CHECK" ]; then
    echo -e "${GREEN}✓${NC} Port 5000 is listening (Web Dashboard)"
    echo "  $PORT_CHECK"
else
    echo -e "${YELLOW}⚠${NC} Port 5000 is not listening"
    echo "  Note: Dashboard may be disabled or starting up"
    ((WARNINGS++))
fi
echo ""

# 5. API 헬스 체크
echo "🔍 API Health Check:"
echo "-------------------"
API_RESPONSE=""
for i in {1..3}; do
    API_RESPONSE=$(curl -s -m 5 -w "\n%{http_code}" http://localhost:5000/api/status 2>/dev/null)
    HTTP_CODE=$(echo "$API_RESPONSE" | tail -n1)
    if [ "$HTTP_CODE" = "200" ]; then
        break
    fi
    sleep 2
done

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✓${NC} API is responding"
    JSON_RESPONSE=$(echo "$API_RESPONSE" | head -n-1)
    
    # JSON 파싱
    if command -v jq &> /dev/null; then
        STATUS=$(echo "$JSON_RESPONSE" | jq -r '.status' 2>/dev/null)
        POSITIONS=$(echo "$JSON_RESPONSE" | jq -r '.positions' 2>/dev/null)
        if [ -n "$STATUS" ]; then
            echo "  Status: $STATUS"
            echo "  Active positions: $POSITIONS"
        fi
    fi
else
    echo -e "${YELLOW}⚠${NC} API not responding (dashboard may be disabled)"
fi
echo ""

# 6. 멀티 계좌 모드 확인
echo "🏦 Multi-Account Configuration:"
echo "------------------------------"
if [ -f "config/config.yaml" ]; then
    MULTI_ENABLED=$(grep -A1 "multi_account:" config/config.yaml | grep "enabled:" | awk '{print $2}')
    MULTI_MODE=$(grep -A2 "multi_account:" config/config.yaml | grep "mode:" | awk '{print $2}' | tr -d '"')
    
    if [ "$MULTI_ENABLED" = "true" ]; then
        echo -e "${GREEN}✓${NC} Multi-account enabled (mode: $MULTI_MODE)"
        
        # 서브 계좌 수 확인
        SUB_ACCOUNTS=$(grep -c "account_id:" config/config.yaml 2>/dev/null || echo "0")
        if [ "$SUB_ACCOUNTS" -gt 0 ]; then
            echo "  Sub accounts configured: $SUB_ACCOUNTS"
        fi
    else
        echo -e "${BLUE}ℹ${NC} Multi-account disabled (single mode)"
    fi
fi
echo ""

# 7. 리소스 사용량
echo "💻 System Resources:"
echo "-------------------"
# CPU 사용률
CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
echo "CPU Usage: $CPU_USAGE%"

# 메모리 사용률
MEM_INFO=$(free -m | grep "^Mem:")
MEM_TOTAL=$(echo $MEM_INFO | awk '{print $2}')
MEM_USED=$(echo $MEM_INFO | awk '{print $3}')
MEM_PERCENT=$((MEM_USED * 100 / MEM_TOTAL))
echo "Memory: ${MEM_USED}MB / ${MEM_TOTAL}MB (${MEM_PERCENT}%)"

# 디스크 사용률
DISK_INFO=$(df -h / | tail -1)
DISK_PERCENT=$(echo "$DISK_INFO" | awk '{print $5}' | sed 's/%//')
echo "Disk: $(echo "$DISK_INFO" | awk '{print $3}') / $(echo "$DISK_INFO" | awk '{print $2}') (${DISK_PERCENT}%)"

if [ "$DISK_PERCENT" -gt 90 ]; then
    echo -e "${RED}⚠${NC} Critical: Disk space low!"
    ((CRITICAL_ISSUES++))
elif [ "$DISK_PERCENT" -gt 80 ]; then
    echo -e "${YELLOW}⚠${NC} Warning: Disk usage high"
    ((WARNINGS++))
fi
echo ""

# 8. 설정 파일 확인
echo "⚙️ Configuration Files:"
echo "--------------------"
if [ -f "config/config.yaml" ]; then
    echo -e "${GREEN}✓${NC} config.yaml found"
    # 활성화된 전략 확인
    TFPE_ENABLED=$(grep -A2 "tfpe:" config/config.yaml | grep "enabled:" | awk '{print $2}')
    if [ "$TFPE_ENABLED" = "true" ]; then
        echo "  TFPE strategy: enabled"
    fi
fi

if [ -f ".env" ]; then
    echo -e "${GREEN}✓${NC} .env file found"
    # API 키 확인 (보안상 일부만 표시)
    if grep -q "BINANCE_API_KEY=" .env; then
        echo "  Main account API key: configured"
    fi
    if grep -q "SUB1_API_KEY=" .env; then
        echo "  Sub account 1 API key: configured"
    fi
else
    echo -e "${RED}✗${NC} .env file missing!"
    ((CRITICAL_ISSUES++))
fi
echo ""

# 9. 최종 요약
echo "======================================"
echo "📋 Deployment Summary"
echo "======================================"

if [ $CRITICAL_ISSUES -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✅ Perfect! All systems operational.${NC}"
    echo -e "Mode: ${BLUE}$ACTIVE_MODE${NC}"
    exit 0
elif [ $CRITICAL_ISSUES -eq 0 ]; then
    echo -e "${YELLOW}⚠️ Deployment successful with $WARNINGS warnings.${NC}"
    echo -e "Mode: ${BLUE}$ACTIVE_MODE${NC}"
    echo "The system is running but may need attention."
    exit 0
else
    echo -e "${RED}❌ Deployment failed! $CRITICAL_ISSUES critical issues found.${NC}"
    echo ""
    echo "🔧 Troubleshooting Commands:"
    echo "1. Check service status: ./scripts/setup_systemd_multi.sh status"
    echo "2. Start single mode: sudo systemctl start albratrading-single"
    echo "3. Start multi mode: sudo systemctl start albratrading-multi"
    echo "4. View logs: sudo journalctl -u albratrading-$ACTIVE_MODE -f"
    echo "5. Switch mode: ./scripts/setup_systemd_multi.sh switch"
    exit 1
fi
