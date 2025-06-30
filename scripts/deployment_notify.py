#!/usr/bin/env python3
"""
AlbraTrading Deployment Notification Script
배포 완료 후 텔레그램으로 알림 전송
"""

import os
import sys
import json
import requests
from datetime import datetime
from pathlib import Path

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

def load_env():
    """환경 변수 로드"""
    env_path = Path(__file__).parent.parent / '.env'
    env_vars = {}
    
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    env_vars[key] = value
    
    return env_vars

def send_telegram_message(bot_token, chat_id, message):
    """텔레그램 메시지 전송"""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, data=data, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Failed to send telegram message: {e}")
        return None

def get_service_status():
    """서비스 상태 확인"""
    import subprocess
    
    services = ['albratrading-single', 'albratrading-multi']
    active_service = None
    
    for service in services:
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', service],
                capture_output=True,
                text=True
            )
            if result.stdout.strip() == 'active':
                active_service = service
                break
        except:
            pass
    
    return active_service

def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Deployment notification')
    parser.add_argument('--status', choices=['success', 'failed'], required=True)
    parser.add_argument('--mode', choices=['single', 'multi'], default='multi')
    parser.add_argument('--message', help='Additional message')
    args = parser.parse_args()
    
    # 환경 변수 로드
    env_vars = load_env()
    bot_token = env_vars.get('TELEGRAM_BOT_TOKEN')
    chat_id = env_vars.get('TELEGRAM_CHAT_ID')
    
    if not bot_token or not chat_id:
        print("Telegram credentials not found in .env")
        return
    
    # 메시지 구성
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    hostname = os.uname().nodename
    
    if args.status == 'success':
        emoji = "✅"
        title = "배포 성공"
        
        # 서비스 상태 확인
        active_service = get_service_status()
        service_info = f"활성 서비스: {active_service}" if active_service else "서비스 상태 확인 실패"
    else:
        emoji = "❌"
        title = "배포 실패"
        service_info = ""
    
    message = f"""
{emoji} *AlbraTrading {title}*

🕐 시간: {timestamp}
🖥️ 서버: {hostname}
📦 모드: {args.mode.upper()}
{service_info}

{args.message if args.message else ''}
"""
    
    # 메시지 전송
    result = send_telegram_message(bot_token, chat_id, message.strip())
    
    if result and result.get('ok'):
        print("Notification sent successfully")
    else:
        print("Failed to send notification")

if __name__ == "__main__":
    main()