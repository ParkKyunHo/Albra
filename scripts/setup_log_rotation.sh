#!/bin/bash
# Health check 로그 로테이션 설정

cat > /tmp/health_check_logrotate << 'EOF'
/home/ubuntu/AlbraTrading/logs/health_check.log {
    daily
    rotate 7
    maxsize 10M
    compress
    delaycompress
    missingok
    notifempty
    create 644 ubuntu ubuntu
}
EOF

# EC2에 로그 로테이션 설정 복사
scp -i ~/.ssh/trading-bot4.pem /tmp/health_check_logrotate ubuntu@13.209.157.171:/tmp/

# EC2에서 로그 로테이션 설정 적용
ssh -i ~/.ssh/trading-bot4.pem ubuntu@13.209.157.171 "sudo mv /tmp/health_check_logrotate /etc/logrotate.d/health_check && sudo chown root:root /etc/logrotate.d/health_check && echo 'Log rotation 설정 완료'"