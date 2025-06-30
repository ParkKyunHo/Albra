#!/bin/bash
# AlbraTrading System - Deployment Verification Script v2.0
# systemd 기반 시스템용 현대적인 체크 스크립트

echo "======================================"
echo "   AlbraTrading Deployment Check"
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

# 1. Systemd 서비스 상태 확인 (가장 중요)
echo "🔧 Systemd Service Status:"
echo "-------------------------"
SERVICE_STATUS=$(sudo systemctl is-active albratrading 2>/dev/null)
if [ "$SERVICE_STATUS" = "active" ]; then
    echo -e "${GREEN}✓${NC} AlbraTrading service is active"
    
    # 상세 정보
    SERVICE_INFO=$(sudo systemctl status albratrading --no-pager | head -15)
    echo "$SERVICE_INFO" | grep -E "Active:|Main PID:|Memory:|CPU:" | while read line; do
        echo "  $line"
    done
else
    echo -e "${RED}✗${NC} AlbraTrading service is not active (status: $SERVICE_STATUS)"
    ((CRITICAL_ISSUES++))
fi
echo ""

# 2. Python 프로세스 확인 (systemd와 연동)
echo "🐍 Python Processes:"
echo "-------------------"
# main.py 프로세스 찾기
MAIN_PY_PROCS=$(sudo ps aux | grep -E "python.*main\.py" | grep -v grep)
if [ -n "$MAIN_PY_PROCS" ]; then
    echo "$MAIN_PY_PROCS" | while read proc; do
        PID=$(echo $proc | awk '{print $2}')
        MEM=$(echo $proc | awk '{print $4}')
        CPU=$(echo $proc | awk '{print $3}')
        echo -e "${GREEN}✓${NC} PID $PID - CPU: $CPU%, MEM: $MEM%"
    done
    
    # 프로세스 상세 정보
    MAIN_PID=$(echo "$MAIN_PY_PROCS" | head -1 | awk '{print $2}')
    if [ -n "$MAIN_PID" ]; then
        PROCESS_TIME=$(ps -o etime= -p $MAIN_PID 2>/dev/null | xargs)
        echo "  Uptime: $PROCESS_TIME"
    fi
else
    echo -e "${RED}✗${NC} No main.py process found!"
    ((CRITICAL_ISSUES++))
fi
echo ""

# 3. 포트 확인 (Flask 대시보드)
echo "🌐 Network Ports:"
echo "----------------"
# sudo로 실행하여 프로세스 정보도 표시
PORT_CHECK=$(sudo ss -tlnp | grep :5000 2>/dev/null)
if [ -n "$PORT_CHECK" ]; then
    echo -e "${GREEN}✓${NC} Port 5000 is listening (Web Dashboard)"
    echo "  $PORT_CHECK"
else
    echo -e "${YELLOW}⚠${NC} Port 5000 is not listening"
    echo "  Note: Dashboard may still be starting up"
    ((WARNINGS++))
fi
echo ""

# 4. 로그 파일 체크 (systemd journal)
echo "📝 System Logs:"
echo "--------------"
# 최근 에러 확인
RECENT_ERRORS=$(sudo journalctl -u albratrading -p err -n 5 --no-pager 2>/dev/null)
if [ -n "$RECENT_ERRORS" ] && [ "$RECENT_ERRORS" != "-- No entries --" ]; then
    echo -e "${YELLOW}⚠${NC} Recent errors found:"
    echo "$RECENT_ERRORS" | tail -5
    ((WARNINGS++))
else
    echo -e "${GREEN}✓${NC} No recent errors in system logs"
fi

# 일반 로그 파일 확인
if [ -d "logs" ]; then
    LATEST_LOG=$(ls -t logs/trading*.log 2>/dev/null | head -1)
    if [ -n "$LATEST_LOG" ]; then
        LOG_SIZE=$(du -h "$LATEST_LOG" | cut -f1)
        echo -e "${GREEN}✓${NC} Latest log: $LATEST_LOG ($LOG_SIZE)"
    fi
fi
echo ""

# 5. API 헬스 체크
echo "🔍 API Health Check:"
echo "-------------------"
# 타임아웃 설정과 재시도
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
    echo -e "${YELLOW}⚠${NC} API not responding yet (may be starting up)"
    ((WARNINGS++))
fi
echo ""

# 6. 리소스 사용량
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

# 7. 설정 파일 확인
echo "⚙️ Configuration:"
echo "----------------"
if [ -f "config/config.yaml" ]; then
    echo -e "${GREEN}✓${NC} config.yaml found"
    # 활성화된 전략 확인
    ENABLED_STRATEGIES=$(grep -A2 "enabled: true" config/config.yaml | grep -B2 "strategies:" | head -3)
    if [ -n "$ENABLED_STRATEGIES" ]; then
        echo "  Active strategies detected"
    fi
fi

if [ -f ".env" ]; then
    echo -e "${GREEN}✓${NC} .env file found"
else
    echo -e "${RED}✗${NC} .env file missing!"
    ((CRITICAL_ISSUES++))
fi
echo ""

# 8. 포지션 정보 (옵션)
echo "📊 Trading Status:"
echo "-----------------"
if [ -f "state/system_state.json" ]; then
    LAST_MODIFIED=$(stat -c "%y" state/system_state.json | cut -d'.' -f1)
    echo -e "${GREEN}✓${NC} State file updated: $LAST_MODIFIED"
fi

# positions.json 확인
if [ -f "state/positions.json" ]; then
    POSITION_COUNT=$(grep -o '"symbol"' state/positions.json | wc -l)
    echo "  Active positions: $POSITION_COUNT"
fi
echo ""

# 9. 최종 요약
echo "======================================"
echo "📋 Deployment Summary"
echo "======================================"

if [ $CRITICAL_ISSUES -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✅ Perfect! All systems operational.${NC}"
    exit 0
elif [ $CRITICAL_ISSUES -eq 0 ]; then
    echo -e "${YELLOW}⚠️ Deployment successful with $WARNINGS warnings.${NC}"
    echo "The system is running but may need attention."
    exit 0
else
    echo -e "${RED}❌ Deployment failed! $CRITICAL_ISSUES critical issues found.${NC}"
    echo ""
    echo "🔧 Troubleshooting Commands:"
    echo "1. Check service: sudo systemctl status albratrading"
    echo "2. View logs: sudo journalctl -u albratrading -f"
    echo "3. Restart service: sudo systemctl restart albratrading"
    echo "4. Check errors: sudo journalctl -u albratrading -p err -n 50"
    exit 1
fi