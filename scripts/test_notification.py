#!/usr/bin/env python3
"""
알림 시스템 테스트 스크립트
notification_manager가 정상 작동하는지 확인
"""

import asyncio
import sys
import os
from datetime import datetime

# 프로젝트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.smart_notification_manager import SmartNotificationManager
from src.utils.telegram_notifier import TelegramNotifier
from src.utils.config_manager import ConfigManager
from dotenv import load_dotenv

load_dotenv()

async def test_notification():
    """알림 전송 테스트"""
    try:
        # 설정 로드
        config_manager = ConfigManager()
        telegram_config = config_manager.config.get('telegram', {})
        
        # 텔레그램 설정
        bot_token = telegram_config.get('bot_token') or os.getenv('TELEGRAM_BOT_TOKEN')
        chat_id = telegram_config.get('chat_id') or os.getenv('TELEGRAM_CHAT_ID')
        
        if not bot_token or not chat_id:
            print("텔레그램 설정이 없습니다.")
            return
        
        # 텔레그램 초기화
        telegram_notifier = TelegramNotifier(bot_token=bot_token, chat_id=chat_id)
        await telegram_notifier.initialize()
        
        # 알림 매니저 초기화
        notification_manager = SmartNotificationManager(telegram_notifier=telegram_notifier)
        await notification_manager.start()
        
        print("알림 시스템 초기화 완료")
        
        # 테스트 알림 전송
        await notification_manager.send_alert(
            event_type='SYSTEM_ERROR',  # CRITICAL 레벨
            title='🧪 알림 시스템 테스트',
            message=(
                f"테스트 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                "알림 시스템이 정상적으로 작동합니다.\n"
                "이 메시지가 보이면 알림 기능이 정상입니다."
            ),
            force=True
        )
        
        print("테스트 알림을 전송했습니다. 텔레그램을 확인하세요.")
        
        # 정리
        await notification_manager.stop()
        
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_notification())
