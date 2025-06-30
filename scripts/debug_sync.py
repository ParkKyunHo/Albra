#!/usr/bin/env python3
"""
포지션 동기화 디버깅 스크립트
sync_positions가 제대로 실행되는지 확인
"""

import asyncio
import sys
import os
from datetime import datetime

# 프로젝트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.binance_api import BinanceAPI
from src.core.position_manager import PositionManager
from src.core.state_manager import StateManager
from src.utils.smart_notification_manager import SmartNotificationManager
from src.utils.telegram_notifier import TelegramNotifier
from src.utils.config_manager import ConfigManager
from src.utils.logger import setup_logger
from dotenv import load_dotenv

load_dotenv()

# 디버깅을 위해 로그 레벨을 DEBUG로 설정
logger = setup_logger('debug_sync', log_level='DEBUG')

async def debug_sync():
    """sync_positions 디버깅"""
    try:
        logger.info("=" * 60)
        logger.info("포지션 동기화 디버깅 시작")
        logger.info("=" * 60)
        
        # 설정 로드
        config_manager = ConfigManager()
        
        # API 초기화
        api_key = os.getenv('BINANCE_API_KEY')
        secret_key = os.getenv('BINANCE_SECRET_KEY')
        
        logger.info("1. 바이낸스 API 초기화")
        binance_api = BinanceAPI(api_key=api_key, secret_key=secret_key, testnet=False)
        await binance_api.initialize()
        
        # 현재 포지션 조회
        logger.info("2. 현재 포지션 조회")
        positions = await binance_api.get_positions()
        logger.info(f"바이낸스 포지션 수: {len(positions) if positions else 0}")
        
        for pos in positions or []:
            symbol = pos.get('symbol')
            amt = float(pos.get('positionAmt', 0))
            if amt != 0:
                logger.info(f"  - {symbol}: {amt}")
        
        # 상태 관리자
        logger.info("3. 상태 관리자 초기화")
        state_manager = StateManager()
        
        # 알림 시스템
        logger.info("4. 알림 시스템 초기화")
        telegram_config = config_manager.config.get('telegram', {})
        bot_token = telegram_config.get('bot_token') or os.getenv('TELEGRAM_BOT_TOKEN')
        chat_id = telegram_config.get('chat_id') or os.getenv('TELEGRAM_CHAT_ID')
        
        notification_manager = None
        if bot_token and chat_id:
            telegram_notifier = TelegramNotifier(bot_token=bot_token, chat_id=chat_id)
            if await telegram_notifier.initialize():
                notification_manager = SmartNotificationManager(telegram_notifier=telegram_notifier)
                await notification_manager.start()
                logger.info("  ✓ 알림 시스템 초기화 성공")
            else:
                logger.error("  ✗ 텔레그램 초기화 실패")
        else:
            logger.error("  ✗ 텔레그램 설정 없음")
        
        # 포지션 매니저
        logger.info("5. 포지션 매니저 초기화")
        position_manager = PositionManager(
            binance_api=binance_api,
            state_manager=state_manager,
            notification_manager=notification_manager,
            config_manager=config_manager
        )
        
        # 캐시 확인
        logger.info("6. 캐시된 포지션 확인")
        cached_positions = await state_manager.load_position_cache()
        logger.info(f"캐시된 포지션 수: {len(cached_positions)}")
        for symbol, pos in cached_positions.items():
            logger.info(f"  - {symbol}: {pos.get('side')} {pos.get('size')}")
        
        # 포지션 매니저 초기화 (sync_positions 실행됨)
        logger.info("7. 포지션 매니저 초기화 (sync_positions 포함)")
        await position_manager.initialize()
        
        # 수동으로 sync_positions 한 번 더 실행
        logger.info("8. 수동 sync_positions 실행")
        sync_report = await position_manager.sync_positions()
        
        logger.info("=" * 60)
        logger.info("동기화 결과:")
        logger.info(f"- 새 수동 포지션: {sync_report['new_manual']}")
        logger.info(f"- 청산된 포지션: {sync_report['closed']}")
        logger.info(f"- 수정된 포지션: {sync_report['modified']}")
        logger.info(f"- 크기 변경: {len(sync_report['size_changed'])}")
        logger.info(f"- 에러: {sync_report['errors']}")
        logger.info("=" * 60)
        
        # 알림 테스트
        if notification_manager and sync_report['new_manual']:
            logger.info("9. 테스트 알림 전송")
            await notification_manager.send_alert(
                event_type='SYSTEM_ERROR',
                title='🧪 디버깅 테스트',
                message=f"새 포지션 감지: {sync_report['new_manual']}",
                force=True
            )
        
        # 정리
        if notification_manager:
            await notification_manager.stop()
        
    except Exception as e:
        logger.error(f"디버깅 중 오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_sync())
