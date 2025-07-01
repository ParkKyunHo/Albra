#!/bin/bash

# 이전 EC2 인스턴스 백업 스크립트
# 중요한 상태 파일과 로그를 백업합니다

OLD_EC2_IP="54.88.60.48"
SSH_KEY="$HOME/.ssh/trading-bot2"
BACKUP_DIR="$HOME/AlbraTrading/backups/old_ec2_$(date +%Y%m%d_%H%M%S)"

echo "======================================"
echo "   이전 EC2 백업 시작"
echo "   IP: $OLD_EC2_IP"
echo "   시간: $(date '+%Y-%m-%d %H:%M:%S KST')"
echo "======================================"

# 백업 디렉토리 생성
echo "📁 백업 디렉토리 생성 중..."
mkdir -p "$BACKUP_DIR"

# 상태 파일 백업
echo "💾 상태 파일 백업 중..."
scp -i "$SSH_KEY" ubuntu@$OLD_EC2_IP:/home/ubuntu/AlbraTrading/state/*.json "$BACKUP_DIR/" 2>/dev/null || echo "상태 파일이 없습니다"

# 중요 로그 백업 (최근 1000줄만)
echo "📝 로그 파일 백업 중..."
ssh -i "$SSH_KEY" ubuntu@$OLD_EC2_IP "cd /home/ubuntu/AlbraTrading && tail -1000 logs/trading.log 2>/dev/null" > "$BACKUP_DIR/trading_last_1000.log" || echo "trading.log가 없습니다"

# .env 파일 백업 (있는 경우)
echo "🔐 환경 설정 백업 중..."
scp -i "$SSH_KEY" ubuntu@$OLD_EC2_IP:/home/ubuntu/AlbraTrading/.env "$BACKUP_DIR/.env.backup" 2>/dev/null || echo ".env 파일이 없습니다"

# 백업 요약
echo
echo "✅ 백업 완료!"
echo "백업 위치: $BACKUP_DIR"
echo
ls -la "$BACKUP_DIR"

echo
echo "======================================"
echo "백업이 완료되었습니다."
echo "이제 이전 EC2 인스턴스를 중지할 수 있습니다."
echo "======================================"