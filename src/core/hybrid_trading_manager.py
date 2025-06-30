"""
Hybrid Trading Manager - 수동/자동 거래 통합 관리
수동 거래와 자동 거래를 명확히 분리하여 충돌 없이 운영
"""

import asyncio
from typing import Dict, Optional, Tuple, List
from datetime import datetime
import logging

from src.utils.logger import setup_logger
from src.core.event_logger import log_event

logger = setup_logger(__name__)


class HybridTradingManager:
    """
    수동/자동 거래 통합 관리자
    
    주요 기능:
    1. 수동 거래 등록 및 관리
    2. 자동 거래와의 완전한 분리
    3. 수동 거래 전용 알림
    4. 포지션 크기 및 레버리지 개별 설정
    """
    
    def __init__(self, position_manager, binance_api, notification_manager):
        self.position_manager = position_manager
        self.binance_api = binance_api
        self.notification_manager = notification_manager
        
        # 수동 거래 추적 (심볼별)
        self.manual_trades = {}
        
        # 수동 거래 설정
        self.manual_leverage_override = {}  # 심볼별 레버리지 오버라이드
        self.manual_size_override = {}  # 심볼별 포지션 크기 오버라이드
        
        logger.info("Hybrid Trading Manager 초기화 완료")
    
    async def register_manual_trade(
        self,
        symbol: str,
        side: str,
        size: float = None,
        leverage: int = None,
        entry_price: float = None,
        comment: str = "수동 거래"
    ) -> Tuple[bool, str]:
        """
        수동 거래 등록
        
        Args:
            symbol: 거래 심볼 (예: BTCUSDT)
            side: 'long' 또는 'short'
            size: 포지션 크기 (None이면 기본값 사용)
            leverage: 레버리지 (None이면 기본값 사용)
            entry_price: 진입가격 (None이면 현재가 사용)
            comment: 거래 메모
            
        Returns:
            (성공여부, 메시지)
        """
        try:
            # 기존 포지션 확인
            existing_position = self.position_manager.get_position(symbol)
            if existing_position and existing_position.status == 'ACTIVE':
                if existing_position.is_manual:
                    return False, f"이미 수동 포지션이 있습니다: {symbol}"
                else:
                    return False, f"자동 거래 포지션이 있습니다: {symbol}"
            
            # 현재가 가져오기
            if not entry_price:
                current_price = await self.binance_api.get_current_price(symbol)
                if not current_price:
                    return False, "현재가를 가져올 수 없습니다"
                entry_price = current_price
            
            # 레버리지 설정
            if leverage:
                self.manual_leverage_override[symbol] = leverage
                await self.binance_api.set_leverage(symbol, leverage)
                logger.info(f"{symbol} 레버리지 설정: {leverage}x")
            else:
                # 기본 레버리지 사용
                leverage = self.position_manager.config.get('leverage', 15)
            
            # 포지션 크기 계산
            if not size:
                # 기본 포지션 크기 사용
                balance = await self.binance_api.get_account_balance()
                position_size_pct = self.position_manager.config.get('position_size', 24) / 100
                size = (balance * position_size_pct * leverage) / entry_price
            
            # 수동 거래로 포지션 등록
            position_data = {
                'symbol': symbol,
                'side': side.upper(),
                'entry_price': entry_price,
                'size': size,
                'leverage': leverage,
                'strategy_name': 'MANUAL',
                'is_manual': True,  # 중요: 수동 거래 플래그
                'comment': comment
            }
            
            # 포지션 등록
            position = await self.position_manager.register_position(**position_data)
            
            if position:
                # 수동 거래 추적
                self.manual_trades[symbol] = {
                    'position_id': position.position_id,
                    'entry_time': datetime.now(),
                    'leverage': leverage,
                    'size': size,
                    'comment': comment
                }
                
                # 수동 거래 전용 알림
                await self._send_manual_trade_notification(
                    symbol, side, size, entry_price, leverage, comment
                )
                
                # 이벤트 로깅
                await log_event(
                    "MANUAL_TRADE_REGISTERED",
                    {
                        'symbol': symbol,
                        'side': side,
                        'size': size,
                        'leverage': leverage,
                        'entry_price': entry_price,
                        'comment': comment
                    },
                    "INFO"
                )
                
                return True, f"수동 거래 등록 성공: {symbol} {side.upper()}"
            else:
                return False, "포지션 등록 실패"
                
        except Exception as e:
            logger.error(f"수동 거래 등록 실패: {e}")
            return False, f"오류: {str(e)}"
    
    async def close_manual_trade(
        self,
        symbol: str,
        percentage: float = 100.0,
        comment: str = "수동 청산"
    ) -> Tuple[bool, str]:
        """
        수동 거래 청산
        
        Args:
            symbol: 거래 심볼
            percentage: 청산 비율 (0-100)
            comment: 청산 사유
            
        Returns:
            (성공여부, 메시지)
        """
        try:
            position = self.position_manager.get_position(symbol)
            
            if not position:
                return False, f"포지션을 찾을 수 없습니다: {symbol}"
            
            if not position.is_manual:
                return False, f"자동 거래 포지션입니다. 수동 청산 불가: {symbol}"
            
            # 부분 청산
            if percentage < 100:
                # 부분 청산 로직
                close_size = position.size * (percentage / 100)
                success = await self.position_manager.partial_close_position(
                    symbol, close_size, comment
                )
            else:
                # 전체 청산
                success = await self.position_manager.close_position(
                    symbol, comment, force=True  # 수동 청산은 강제 실행
                )
            
            if success:
                # 수동 거래 추적에서 제거
                if percentage >= 100 and symbol in self.manual_trades:
                    del self.manual_trades[symbol]
                
                return True, f"수동 청산 성공: {symbol} ({percentage}%)"
            else:
                return False, "청산 실패"
                
        except Exception as e:
            logger.error(f"수동 청산 실패: {e}")
            return False, f"오류: {str(e)}"
    
    async def modify_manual_trade(
        self,
        symbol: str,
        new_size: float = None,
        new_leverage: int = None,
        add_size: float = None
    ) -> Tuple[bool, str]:
        """
        수동 거래 수정 (피라미딩 등)
        
        Args:
            symbol: 거래 심볼
            new_size: 새로운 전체 크기
            new_leverage: 새로운 레버리지
            add_size: 추가할 크기 (피라미딩)
            
        Returns:
            (성공여부, 메시지)
        """
        try:
            position = self.position_manager.get_position(symbol)
            
            if not position:
                return False, f"포지션을 찾을 수 없습니다: {symbol}"
            
            if not position.is_manual:
                return False, f"자동 거래 포지션은 수정할 수 없습니다: {symbol}"
            
            # 레버리지 변경
            if new_leverage and new_leverage != position.leverage:
                await self.binance_api.set_leverage(symbol, new_leverage)
                self.manual_leverage_override[symbol] = new_leverage
                logger.info(f"{symbol} 레버리지 변경: {position.leverage}x → {new_leverage}x")
            
            # 포지션 크기 변경
            if add_size:
                # 피라미딩 (추가)
                current_price = await self.binance_api.get_current_price(symbol)
                # 추가 매수/매도 로직
                # ... (실제 거래 실행 코드)
                
            elif new_size:
                # 크기 조정
                if new_size > position.size:
                    # 추가
                    add_amount = new_size - position.size
                    # ... (추가 로직)
                else:
                    # 부분 청산
                    close_percentage = ((position.size - new_size) / position.size) * 100
                    return await self.close_manual_trade(symbol, close_percentage, "크기 조정")
            
            return True, f"수동 거래 수정 완료: {symbol}"
            
        except Exception as e:
            logger.error(f"수동 거래 수정 실패: {e}")
            return False, f"오류: {str(e)}"
    
    async def _send_manual_trade_notification(
        self,
        symbol: str,
        side: str,
        size: float,
        entry_price: float,
        leverage: int,
        comment: str
    ):
        """수동 거래 전용 알림 전송"""
        try:
            if not self.notification_manager:
                return
            
            message = f"""
🤚 <b>수동 거래 등록</b>

<b>심볼:</b> {symbol}
<b>방향:</b> {side.upper()}
<b>수량:</b> {size:.4f}
<b>진입가:</b> ${entry_price:.2f}
<b>레버리지:</b> {leverage}x
<b>메모:</b> {comment}
<b>시간:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

⚠️ 이 포지션은 자동 청산되지 않습니다.
수동으로 관리해주세요.
"""
            
            await self.notification_manager.send_alert(
                event_type='MANUAL_TRADE',
                title='🤚 수동 거래',
                message=message,
                priority='HIGH'
            )
            
        except Exception as e:
            logger.error(f"수동 거래 알림 전송 실패: {e}")
    
    def get_manual_positions(self) -> List[Dict]:
        """현재 활성 수동 포지션 목록 반환"""
        manual_positions = []
        
        for symbol, trade_info in self.manual_trades.items():
            position = self.position_manager.get_position(symbol)
            if position and position.status == 'ACTIVE':
                manual_positions.append({
                    'symbol': symbol,
                    'position': position,
                    'trade_info': trade_info
                })
        
        return manual_positions
    
    def get_leverage_override(self, symbol: str) -> Optional[int]:
        """심볼별 레버리지 오버라이드 반환"""
        return self.manual_leverage_override.get(symbol)
    
    def is_manual_trade(self, symbol: str) -> bool:
        """해당 심볼이 수동 거래인지 확인"""
        return symbol in self.manual_trades
