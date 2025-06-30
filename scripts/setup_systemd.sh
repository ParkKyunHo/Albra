#!/bin/bash
# AlbraTrading Systemd Service Setup Script

set -e  # 에러 발생 시 스크립트 중단

echo "=== AlbraTrading Systemd 서비스 설정 ==="
echo ""

# 색상 코드
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. 기존 프로세스 정리
echo "1. 기존 프로세스 정리 중..."
sudo systemctl stop albratrading 2>/dev/null || true
tmux kill-session -t trading 2>/dev/null || true
pkill -f supervisor.py 2>/dev/null || true
pkill -f main.py 2>/dev/null || true
sleep 2

# 2. 필요한 디렉토리 생성
echo "2. 디렉토리 구조 확인 중..."
mkdir -p /home/ubuntu/AlbraTrading/logs
mkdir -p /home/ubuntu/AlbraTrading/data
mkdir -p /home/ubuntu/AlbraTrading/scripts

# 3. 서비스 파일 생성
echo "3. Systemd 서비스 파일 생성 중..."
sudo tee /etc/systemd/system/albratrading.service > /dev/null << 'EOF'
[Unit]
Description=AlbraTrading Bot Service
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/AlbraTrading
Environment="PATH=/home/ubuntu/AlbraTrading/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="PYTHONPATH=/home/ubuntu/AlbraTrading"
ExecStart=/home/ubuntu/AlbraTrading/venv/bin/python /home/ubuntu/AlbraTrading/src/main.py
Restart=always
RestartSec=10
StandardOutput=append:/home/ubuntu/AlbraTrading/logs/systemd.log
StandardError=append:/home/ubuntu/AlbraTrading/logs/systemd_error.log

# 프로세스 제한
LimitNOFILE=65536
LimitNPROC=4096

# 실패 시 재시작 정책
StartLimitInterval=300
StartLimitBurst=5

[Install]
WantedBy=multi-user.target
EOF

# 4. 서비스 활성화
echo "4. Systemd 서비스 활성화 중..."
sudo systemctl daemon-reload
sudo systemctl enable albratrading.service

# 5. 서비스 시작
echo "5. 서비스 시작 중..."
sudo systemctl start albratrading.service
sleep 5

# 6. 상태 확인
echo ""
echo "6. 서비스 상태 확인:"
echo "================================"
sudo systemctl status albratrading.service --no-pager

# 7. Health Check Crontab 설정
echo ""
echo "7. Health Check 설정 중..."
if [ -f "/home/ubuntu/AlbraTrading/scripts/health_check.py" ]; then
    chmod +x /home/ubuntu/AlbraTrading/scripts/health_check.py
    
    # Crontab에 추가 (중복 방지)
    if ! crontab -l 2>/dev/null | grep -q "health_check.py"; then
        (crontab -l 2>/dev/null; echo "*/5 * * * * /home/ubuntu/AlbraTrading/venv/bin/python /home/ubuntu/AlbraTrading/scripts/health_check.py >> /home/ubuntu/AlbraTrading/logs/health_check.log 2>&1") | crontab -
        echo -e "${GREEN}✓ Health Check crontab 등록 완료${NC}"
    fi
fi

# 8. 로그 로테이션 설정
echo ""
echo "8. 로그 로테이션 설정 중..."
sudo tee /etc/logrotate.d/albratrading > /dev/null << 'EOF'
/home/ubuntu/AlbraTrading/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 ubuntu ubuntu
    sharedscripts
    postrotate
        sudo systemctl reload albratrading >/dev/null 2>&1 || true
    endscript
}
EOF

# 9. 유용한 명령어 안내
echo ""
echo "================================"
echo -e "${GREEN}✓ Systemd 서비스 설정 완료!${NC}"
echo ""
echo "유용한 명령어:"
echo "  서비스 상태:     sudo systemctl status albratrading"
echo "  서비스 시작:     sudo systemctl start albratrading"
echo "  서비스 중지:     sudo systemctl stop albratrading"
echo "  서비스 재시작:   sudo systemctl restart albratrading"
echo "  실시간 로그:     sudo journalctl -u albratrading -f"
echo "  최근 로그:       sudo journalctl -u albratrading --since '10 minutes ago'"
echo "  애플리케이션 로그: tail -f /home/ubuntu/AlbraTrading/logs/trading.log"
echo ""
echo "웹 대시보드:      http://$(curl -s ifconfig.me):5000"
echo "================================"

# 10. 최종 확인
echo ""
echo "서비스가 정상적으로 실행 중인지 확인하는 중..."
sleep 3

if sudo systemctl is-active --quiet albratrading; then
    echo -e "${GREEN}✓ AlbraTrading 서비스가 정상적으로 실행 중입니다!${NC}"
else
    echo -e "${RED}✗ 서비스 시작에 실패했습니다. 로그를 확인해주세요:${NC}"
    echo "  sudo journalctl -u albratrading -n 50"
    exit 1
fi

echo ""
echo "설정이 완료되었습니다! 🎉"