#!/bin/bash
#====================================
# AlbraTrading 모니터링 시스템 설치 스크립트
# EC2에서 실행하여 watchdog 서비스 설치
#====================================

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== AlbraTrading 모니터링 시스템 설치 ===${NC}"

# 1. 현재 디렉토리 확인
if [ ! -f "/home/ubuntu/AlbraTrading/scripts/monitoring/system_watchdog.py" ]; then
    echo -e "${RED}오류: /home/ubuntu/AlbraTrading 디렉토리에서 실행해주세요.${NC}"
    exit 1
fi

# 2. 로그 디렉토리 생성
echo -e "${YELLOW}로그 디렉토리 생성 중...${NC}"
sudo mkdir -p /home/ubuntu/AlbraTrading/logs/watchdog
sudo mkdir -p /home/ubuntu/AlbraTrading/logs/monitoring
sudo chown -R ubuntu:ubuntu /home/ubuntu/AlbraTrading/logs

# 3. 실행 권한 설정
echo -e "${YELLOW}실행 권한 설정 중...${NC}"
chmod +x /home/ubuntu/AlbraTrading/scripts/monitoring/system_watchdog.py
chmod +x /home/ubuntu/AlbraTrading/scripts/monitoring/crash_prevention.py

# 4. systemd 서비스 파일 복사
echo -e "${YELLOW}systemd 서비스 설치 중...${NC}"
sudo cp /home/ubuntu/AlbraTrading/scripts/systemd/albratrading-watchdog.service /etc/systemd/system/

# 5. systemd 재로드
echo -e "${YELLOW}systemd 데몬 재로드 중...${NC}"
sudo systemctl daemon-reload

# 6. watchdog 서비스 활성화
echo -e "${YELLOW}watchdog 서비스 활성화 중...${NC}"
sudo systemctl enable albratrading-watchdog.service

# 7. watchdog 서비스 시작
echo -e "${YELLOW}watchdog 서비스 시작 중...${NC}"
sudo systemctl start albratrading-watchdog.service

# 8. cron 작업 추가 (crash prevention을 5분마다 실행)
echo -e "${YELLOW}cron 작업 추가 중...${NC}"
(crontab -l 2>/dev/null || true; echo "*/5 * * * * cd /home/ubuntu/AlbraTrading && /home/ubuntu/AlbraTrading/venv/bin/python /home/ubuntu/AlbraTrading/scripts/monitoring/crash_prevention.py >> /home/ubuntu/AlbraTrading/logs/monitoring/cron.log 2>&1") | crontab -

# 9. 상태 확인
echo -e "${GREEN}=== 설치 완료 ===${NC}"
echo -e "${YELLOW}서비스 상태 확인:${NC}"
sudo systemctl status albratrading-watchdog.service --no-pager

echo -e "\n${GREEN}모니터링 명령어:${NC}"
echo "  - Watchdog 상태: sudo systemctl status albratrading-watchdog"
echo "  - Watchdog 로그: sudo journalctl -u albratrading-watchdog -f"
echo "  - Crash prevention 로그: tail -f /home/ubuntu/AlbraTrading/logs/monitoring/crash_prevention.log"
echo "  - 수동 예방 체크: python scripts/monitoring/crash_prevention.py"

echo -e "\n${YELLOW}주의: 메인 서비스 파일도 업데이트되었습니다.${NC}"
echo "다음 명령으로 적용하세요:"
echo "  sudo cp /home/ubuntu/AlbraTrading/scripts/systemd/albratrading-multi.service.ec2 /etc/systemd/system/albratrading-multi.service"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl restart albratrading-multi"