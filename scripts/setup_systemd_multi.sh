#!/bin/bash
# AlbraTrading Multi-Mode Systemd Service Setup Script
# 단일 계좌 모드와 멀티 계좌 모드를 모두 지원

set -e  # 에러 발생 시 스크립트 중단

echo "=== AlbraTrading Multi-Mode Systemd 서비스 설정 ==="
echo ""

# 색상 코드
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 사용법 표시
usage() {
    echo "사용법: $0 [모드]"
    echo ""
    echo "모드:"
    echo "  single    - 단일 계좌 모드 설정"
    echo "  multi     - 멀티 계좌 모드 설정"
    echo "  status    - 현재 서비스 상태 확인"
    echo "  switch    - 모드 전환"
    echo ""
    echo "예시:"
    echo "  $0 single    # 단일 계좌 모드로 설정"
    echo "  $0 multi     # 멀티 계좌 모드로 설정"
    echo "  $0 status    # 현재 상태 확인"
    exit 1
}

# 인자 확인
if [ $# -eq 0 ]; then
    usage
fi

MODE=$1

# 현재 활성 서비스 확인
check_current_service() {
    if systemctl is-active --quiet albratrading-single; then
        echo "single"
    elif systemctl is-active --quiet albratrading-multi; then
        echo "multi"
    else
        echo "none"
    fi
}

# 서비스 상태 표시
show_status() {
    echo -e "${BLUE}=== 현재 AlbraTrading 서비스 상태 ===${NC}"
    echo ""
    
    current=$(check_current_service)
    
    if [ "$current" = "none" ]; then
        echo -e "${YELLOW}활성화된 서비스가 없습니다.${NC}"
    else
        echo -e "${GREEN}현재 활성 모드: $current${NC}"
        echo ""
        
        if [ "$current" = "single" ]; then
            sudo systemctl status albratrading-single --no-pager
        else
            sudo systemctl status albratrading-multi --no-pager
        fi
    fi
    
    echo ""
    echo -e "${BLUE}=== 서비스 상태 요약 ===${NC}"
    echo -n "단일 계좌 모드: "
    if systemctl is-enabled --quiet albratrading-single 2>/dev/null; then
        if systemctl is-active --quiet albratrading-single; then
            echo -e "${GREEN}활성${NC}"
        else
            echo -e "${YELLOW}비활성${NC}"
        fi
    else
        echo -e "${RED}미설치${NC}"
    fi
    
    echo -n "멀티 계좌 모드: "
    if systemctl is-enabled --quiet albratrading-multi 2>/dev/null; then
        if systemctl is-active --quiet albratrading-multi; then
            echo -e "${GREEN}활성${NC}"
        else
            echo -e "${YELLOW}비활성${NC}"
        fi
    else
        echo -e "${RED}미설치${NC}"
    fi
}

# 서비스 정리
cleanup_services() {
    echo "기존 서비스 정리 중..."
    
    # 기존 프로세스 정리
    sudo systemctl stop albratrading 2>/dev/null || true
    sudo systemctl stop albratrading-single 2>/dev/null || true
    sudo systemctl stop albratrading-multi 2>/dev/null || true
    
    # tmux 세션 정리
    tmux kill-session -t trading 2>/dev/null || true
    
    # 레거시 프로세스 정리
    pkill -f main.py 2>/dev/null || true
    pkill -f main_multi_account.py 2>/dev/null || true
    
    sleep 2
}

# 필수 디렉토리 생성
setup_directories() {
    echo "디렉토리 구조 확인 중..."
    mkdir -p /home/ubuntu/AlbraTrading/logs
    mkdir -p /home/ubuntu/AlbraTrading/data
    mkdir -p /home/ubuntu/AlbraTrading/state
    mkdir -p /home/ubuntu/AlbraTrading/scripts
    
    # 로그 파일 권한 설정
    touch /home/ubuntu/AlbraTrading/logs/systemd_single.log
    touch /home/ubuntu/AlbraTrading/logs/systemd_single_error.log
    touch /home/ubuntu/AlbraTrading/logs/systemd_multi.log
    touch /home/ubuntu/AlbraTrading/logs/systemd_multi_error.log
    
    sudo chown -R ubuntu:ubuntu /home/ubuntu/AlbraTrading/logs
}

# 단일 모드 설정
setup_single_mode() {
    echo -e "${BLUE}=== 단일 계좌 모드 설정 ===${NC}"
    
    # 1. 서비스 파일 복사
    echo "1. 서비스 파일 설치 중..."
    sudo cp /home/ubuntu/AlbraTrading/scripts/systemd/albratrading-single.service /etc/systemd/system/
    
    # 2. 서비스 활성화
    echo "2. 서비스 활성화 중..."
    sudo systemctl daemon-reload
    sudo systemctl enable albratrading-single.service
    
    # 3. 멀티 모드 비활성화
    sudo systemctl disable albratrading-multi.service 2>/dev/null || true
    
    # 4. 서비스 시작
    echo "3. 서비스 시작 중..."
    sudo systemctl start albratrading-single.service
    
    sleep 3
    
    # 5. 상태 확인
    if sudo systemctl is-active --quiet albratrading-single; then
        echo -e "${GREEN}✓ 단일 계좌 모드 서비스가 정상적으로 시작되었습니다!${NC}"
    else
        echo -e "${RED}✗ 서비스 시작에 실패했습니다.${NC}"
        echo "로그 확인: sudo journalctl -u albratrading-single -n 50"
        exit 1
    fi
}

# 멀티 모드 설정
setup_multi_mode() {
    echo -e "${BLUE}=== 멀티 계좌 모드 설정 ===${NC}"
    
    # 0. 설정 확인
    echo "0. 멀티 계좌 설정 확인 중..."
    if ! grep -q "multi_account:" /home/ubuntu/AlbraTrading/config/config.yaml; then
        echo -e "${RED}✗ config.yaml에 multi_account 설정이 없습니다.${NC}"
        echo "먼저 config.yaml에 멀티 계좌 설정을 추가해주세요."
        exit 1
    fi
    
    # 1. 서비스 파일 복사
    echo "1. 서비스 파일 설치 중..."
    sudo cp /home/ubuntu/AlbraTrading/scripts/systemd/albratrading-multi.service /etc/systemd/system/
    
    # 2. 서비스 활성화
    echo "2. 서비스 활성화 중..."
    sudo systemctl daemon-reload
    sudo systemctl enable albratrading-multi.service
    
    # 3. 단일 모드 비활성화
    sudo systemctl disable albratrading-single.service 2>/dev/null || true
    
    # 4. 서비스 시작
    echo "3. 서비스 시작 중..."
    sudo systemctl start albratrading-multi.service
    
    sleep 3
    
    # 5. 상태 확인
    if sudo systemctl is-active --quiet albratrading-multi; then
        echo -e "${GREEN}✓ 멀티 계좌 모드 서비스가 정상적으로 시작되었습니다!${NC}"
    else
        echo -e "${RED}✗ 서비스 시작에 실패했습니다.${NC}"
        echo "로그 확인: sudo journalctl -u albratrading-multi -n 50"
        exit 1
    fi
}

# 모드 전환
switch_mode() {
    current=$(check_current_service)
    
    echo -e "${BLUE}=== 모드 전환 ===${NC}"
    echo -e "현재 모드: ${YELLOW}$current${NC}"
    
    if [ "$current" = "none" ]; then
        echo -e "${RED}활성화된 서비스가 없습니다. 먼저 서비스를 설정하세요.${NC}"
        exit 1
    fi
    
    echo ""
    echo "전환할 모드를 선택하세요:"
    echo "1) 단일 계좌 모드"
    echo "2) 멀티 계좌 모드"
    echo "3) 취소"
    
    read -p "선택 [1-3]: " choice
    
    case $choice in
        1)
            if [ "$current" = "single" ]; then
                echo -e "${YELLOW}이미 단일 계좌 모드입니다.${NC}"
                exit 0
            fi
            cleanup_services
            setup_directories
            setup_single_mode
            ;;
        2)
            if [ "$current" = "multi" ]; then
                echo -e "${YELLOW}이미 멀티 계좌 모드입니다.${NC}"
                exit 0
            fi
            cleanup_services
            setup_directories
            setup_multi_mode
            ;;
        3)
            echo "취소되었습니다."
            exit 0
            ;;
        *)
            echo -e "${RED}잘못된 선택입니다.${NC}"
            exit 1
            ;;
    esac
}

# 공통 설정 (Health Check, 로그 로테이션)
setup_common() {
    echo ""
    echo "공통 설정 적용 중..."
    
    # Health Check Crontab 설정
    if [ -f "/home/ubuntu/AlbraTrading/scripts/health_check.py" ]; then
        chmod +x /home/ubuntu/AlbraTrading/scripts/health_check.py
        
        # Crontab에 추가 (중복 방지)
        if ! crontab -l 2>/dev/null | grep -q "health_check.py"; then
            (crontab -l 2>/dev/null; echo "*/5 * * * * /home/ubuntu/AlbraTrading/venv/bin/python /home/ubuntu/AlbraTrading/scripts/health_check.py >> /home/ubuntu/AlbraTrading/logs/health_check.log 2>&1") | crontab -
            echo -e "${GREEN}✓ Health Check crontab 등록 완료${NC}"
        fi
    fi
    
    # 로그 로테이션 설정
    sudo tee /etc/logrotate.d/albratrading > /dev/null << 'EOF'
/home/ubuntu/AlbraTrading/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0644 ubuntu ubuntu
    sharedscripts
    postrotate
        # 활성 서비스만 리로드
        if systemctl is-active --quiet albratrading-single; then
            sudo systemctl reload albratrading-single >/dev/null 2>&1 || true
        fi
        if systemctl is-active --quiet albratrading-multi; then
            sudo systemctl reload albratrading-multi >/dev/null 2>&1 || true
        fi
    endscript
}
EOF
    
    echo -e "${GREEN}✓ 공통 설정 완료${NC}"
}

# 메인 로직
case "$MODE" in
    single)
        cleanup_services
        setup_directories
        setup_single_mode
        setup_common
        ;;
    multi)
        cleanup_services
        setup_directories
        setup_multi_mode
        setup_common
        ;;
    status)
        show_status
        exit 0
        ;;
    switch)
        switch_mode
        setup_common
        ;;
    *)
        echo -e "${RED}알 수 없는 모드: $MODE${NC}"
        usage
        ;;
esac

# 완료 메시지
echo ""
echo "================================"
echo -e "${GREEN}✓ 설정 완료!${NC}"
echo ""
echo "유용한 명령어:"
echo "  서비스 상태:     sudo systemctl status albratrading-$MODE"
echo "  서비스 시작:     sudo systemctl start albratrading-$MODE"
echo "  서비스 중지:     sudo systemctl stop albratrading-$MODE"
echo "  서비스 재시작:   sudo systemctl restart albratrading-$MODE"
echo "  실시간 로그:     sudo journalctl -u albratrading-$MODE -f"
echo "  모드 전환:       ./setup_systemd_multi.sh switch"
echo ""
echo "멀티 계좌 CLI:    python /home/ubuntu/AlbraTrading/scripts/multi_account_cli.py --help"
echo "웹 대시보드:      http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_IP'):5000"
echo "================================"
