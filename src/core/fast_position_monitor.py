# src/core/fast_position_monitor.py
"""빠른 포지션 모니터링 - 수동 포지션 감지 전용"""
import asyncio
import logging
from typing import Optional, Set, Dict
from datetime import datetime

logger = logging.getLogger(__name__)

class FastPositionMonitor:
    """빠른 포지션 감지를 위한 경량 모니터"""
    
    def __init__(self, position_manager, binance_api, notification_manager=None):
        self.position_manager = position_manager
        self.binance_api = binance_api
        self.notification_manager = notification_manager
        
        # 설정
        self.check_interval = 10  # 10초마다 체크
        self.running = False
        self.task = None
        
        # 마지막 확인한 포지션
        self.last_positions: Set[str] = set()
        self.last_position_sizes: Dict[str, float] = {}  # 포지션 크기 추적
        self.last_position_details: Dict[str, dict] = {}  # 포지션 상세 정보 저장
        
        logger.info("빠른 포지션 모니터 초기화")
    
    async def start(self):
        """모니터링 시작"""
        if self.running:
            logger.warning("이미 실행 중입니다")
            return
        
        # 시작 전 현재 포지션 상태 저장
        try:
            logger.info("현재 포지션 초기화 중...")
            positions = await self.binance_api.get_positions()
            
            for pos in positions:
                try:
                    pos_amt = float(pos.get('positionAmt', '0'))
                    if pos_amt != 0:
                        symbol = pos['symbol']
                        self.last_positions.add(symbol)
                        self.last_position_sizes[symbol] = abs(pos_amt)
                        self.last_position_details[symbol] = pos
                        logger.info(f"초기 포지션: {symbol} - amt: {pos_amt}")
                except Exception as e:
                    logger.error(f"초기 포지션 처리 오류: {e}")
            
            logger.info(f"초기화 완료: {len(self.last_positions)}개 포지션")
        except Exception as e:
            logger.error(f"포지션 초기화 실패: {e}")
        
        self.running = True
        self.task = asyncio.create_task(self._monitor_loop())
        logger.info("빠른 포지션 모니터링 시작")
    
    async def stop(self):
        """모니터링 중지"""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("빠른 포지션 모니터링 중지")
    
    async def _monitor_loop(self):
        """메인 모니터링 루프"""
        while self.running:
            try:
                await self._check_new_positions()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"빠른 모니터링 오류: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _check_new_positions(self):
        """새 포지션만 빠르게 체크"""
        try:
            logger.info("[FastPositionMonitor] 체크 시작 - 현재 시간: %s", datetime.now().strftime('%H:%M:%S'))
            
            # 바이낸스에서 현재 포지션 조회
            positions = await self.binance_api.get_positions()
            logger.info(f"[FastPositionMonitor] API에서 받은 포지션 수: {len(positions) if positions else 0}")
            
            if not positions:
                # 포지션이 없어졌다면 청산 확인
                if self.last_positions:
                    for symbol in self.last_positions:
                        await self._send_close_alert(symbol)
                self.last_positions.clear()
                self.last_position_sizes.clear()
                self.last_position_details.clear()
                return
            
            # 현재 활성 포지션 심볼 집합 - 간단한 체크
            current_symbols = set()
            position_details = {}  # 포지션 상세 정보 저장
            
            for pos in positions:
                try:
                    pos_amt = float(pos.get('positionAmt', '0'))
                    notional = float(pos.get('notional', '0'))
                    unrealized = float(pos.get('unrealizedProfit', '0'))
                    
                    # 포지션이 있는지 확인
                    if pos_amt != 0 or abs(notional) > 0.01 or abs(unrealized) > 0.01:
                        symbol = pos['symbol']
                        current_symbols.add(symbol)
                        position_details[symbol] = pos
                        logger.info(f"[FastPositionMonitor] 활성 포지션: {symbol} - amt: {pos_amt}, notional: {notional}")
                except Exception as e:
                    logger.error(f"[FastPositionMonitor] 포지션 처리 오류: {e}")
                    continue
            
            logger.info(f"[FastPositionMonitor] 현재: {current_symbols}, 마지막: {self.last_positions}")
            
            # 새 포지션 감지
            new_symbols = current_symbols - self.last_positions
            
            # 새 포지션 발견 시 알림 전송
            if new_symbols:
                logger.info(f"새 포지션 감지 (빠른 모니터): {new_symbols}")
                
                for symbol in new_symbols:
                    pos_info = position_details.get(symbol)
                    if pos_info:
                        position_amt = float(pos_info['positionAmt'])
                        side = 'LONG' if position_amt > 0 else 'SHORT'
                        size = abs(position_amt)
                        entry_price = float(pos_info.get('entryPrice', 0))
                        
                        logger.info(f"[빠른 감지] {symbol}: {side} {size:.4f} @ ${entry_price:.2f}")
                        
                        # 알림 전송 활성화
                        if self.notification_manager:
                            await self._send_detailed_alert(symbol, pos_info)
            
            # 부분 청산 및 추가 매수 감지
            for symbol in current_symbols & self.last_positions:  # 공통 포지션
                current_size = abs(float(position_details[symbol]['positionAmt']))
                last_size = self.last_position_sizes.get(symbol, 0)
                
                if abs(current_size - last_size) > 0.0001:  # 크기 변경 감지
                    if current_size > last_size:
                        # 추가 매수
                        size_change = current_size - last_size
                        logger.info(f"추가 매수 감지: {symbol} {last_size:.4f} -> {current_size:.4f}")
                        await self._send_position_increase_alert(symbol, size_change, current_size, position_details[symbol])
                    else:
                        # 부분 청산
                        size_change = last_size - current_size
                        logger.info(f"부분 청산 감지: {symbol} {last_size:.4f} -> {current_size:.4f}")
                        await self._send_partial_close_alert(symbol, size_change, current_size, position_details[symbol])
            
            # 완전 청산 감지
            closed_symbols = self.last_positions - current_symbols
            if closed_symbols:
                logger.info(f"포지션 청산 감지: {closed_symbols}")
                for symbol in closed_symbols:
                    await self._send_close_alert(symbol)
            
            # 마지막 포지션 업데이트
            self.last_positions = current_symbols
            self.last_position_sizes = {symbol: abs(float(position_details[symbol]['positionAmt'])) 
                                       for symbol in current_symbols}
            self.last_position_details = position_details.copy()
            
        except Exception as e:
            logger.error(f"빠른 포지션 체크 실패: {e}")
    
    async def _send_quick_alert(self, symbol: str, pos_info: dict):
        """빠른 알림 전송"""
        try:
            position_amt = float(pos_info['positionAmt'])
            side = 'LONG' if position_amt > 0 else 'SHORT'
            size = abs(position_amt)
            
            message = (
                f"⚡ <b>새 포지션 빠른 감지</b>\n\n"
                f"<b>심볼:</b> {symbol}\n"
                f"<b>방향:</b> {side}\n"
                f"<b>수량:</b> {size:.4f}\n\n"
                f"<i>상세 정보는 곧 전송됩니다...</i>"
            )
            
            # 빠른 알림은 MEDIUM 레벨로 (즉시 전송되지만 쿨다운 있음)
            await self.notification_manager.send_alert(
                event_type='POSITION_OPENED',
                title=f'⚡ {symbol} 포지션 감지',
                message=message,
                force=True  # 쿨다운 무시
            )
            
        except Exception as e:
            logger.error(f"빠른 알림 전송 실패: {e}")
    
    async def _send_detailed_alert(self, symbol: str, pos_info: dict):
        """상세 알림 전송"""
        try:
            position_amt = float(pos_info['positionAmt'])
            side = 'LONG' if position_amt > 0 else 'SHORT'
            size = abs(position_amt)
            entry_price = float(pos_info['entryPrice'])
            leverage = int(pos_info['leverage'])
            
            # 이벤트 ID 생성: "심볼_사이드_진입가_fast"
            event_id = f"{symbol}_{side}_{entry_price}_fast"
            
            message = (
                f"<b>심볼:</b> {symbol}\n"
                f"<b>방향:</b> {side}\n"
                f"<b>수량:</b> {size:.4f}\n"
                f"<b>진입가:</b> ${entry_price:.2f}\n"
                f"<b>레버리지:</b> {leverage}x\n\n"
                f"수동으로 생성된 포지션이 감지되었습니다."
            )
            
            await self.notification_manager.send_alert(
                event_type='USER_INTERVENTION',
                title=f'🔔 새로운 수동 포지션 감지',
                message=message,
                data={
                    'symbol': symbol,
                    'side': side,
                    'size': size,
                    'entry_price': entry_price,
                    'leverage': leverage
                },
                event_id=event_id
            )
            
            logger.info(f"상세 알림 전송 완료: {symbol}")
            
        except Exception as e:
            logger.error(f"상세 알림 전송 실패: {e}")
    
    async def _send_close_alert(self, symbol: str):
        """청산 알림 전송"""
        try:
            # position_manager에서 이전 포지션 정보 가져오기
            position = self.position_manager.get_position(symbol)
            
            if self.notification_manager:
                if position:
                    # position_manager에 정보가 있는 경우
                    message = (
                        f"<b>방향:</b> {position.side}\n"
                        f"<b>진입가:</b> ${position.entry_price:.2f}\n"
                        f"<b>수량:</b> {position.size:.4f}\n\n"
                        f"{'수동' if position.is_manual else '자동'} 포지션이 청산되었습니다."
                    )
                    
                    event_type = 'MANUAL_POSITION_CLOSED' if position.is_manual else 'POSITION_CLOSED'
                    
                    data = {
                        'symbol': symbol,
                        'side': position.side,
                        'entry_price': position.entry_price,
                        'size': position.size,
                        'is_manual': position.is_manual
                    }
                else:
                    # position_manager에 정보가 없는 경우 - 마지막 저장된 정보 사용
                    last_details = self.last_position_details.get(symbol, {})
                    last_size = self.last_position_sizes.get(symbol, 0)
                    
                    if last_details:
                        position_amt = float(last_details.get('positionAmt', 0))
                        side = 'LONG' if position_amt > 0 else 'SHORT'
                        entry_price = float(last_details.get('entryPrice', 0))
                    else:
                        side = 'UNKNOWN'
                        entry_price = 0
                    
                    message = (
                        f"<b>방향:</b> {side}\n"
                        f"<b>진입가:</b> ${entry_price:.2f}\n"
                        f"<b>수량:</b> {last_size:.4f}\n\n"
                        f"포지션이 완전히 청산되었습니다."
                    )
                    
                    event_type = 'MANUAL_POSITION_CLOSED'  # 정보가 없으면 수동으로 간주
                    
                    data = {
                        'symbol': symbol,
                        'side': side,
                        'entry_price': entry_price,
                        'size': last_size,
                        'is_manual': True
                    }
                
                # 이벤트 ID 생성: "심볼_closed_fast_타임스탬프"
                event_id = f"{symbol}_closed_fast_{datetime.now().timestamp()}"
                
                await self.notification_manager.send_alert(
                    event_type=event_type,
                    title=f"🔴 {symbol} 포지션 청산",
                    message=message,
                    data=data,
                    event_id=event_id
                )
                
                logger.info(f"청산 알림 전송 완료: {symbol} (position_manager 정보: {'있음' if position else '없음'})")
            
        except Exception as e:
            logger.error(f"청산 알림 전송 실패 ({symbol}): {e}")
    
    async def _send_partial_close_alert(self, symbol: str, closed_size: float, remaining_size: float, pos_info: dict):
        """부분 청산 알림 전송"""
        try:
            if self.notification_manager:
                position_amt = float(pos_info['positionAmt'])
                side = 'LONG' if position_amt > 0 else 'SHORT'
                
                message = (
                    f"<b>청산 수량:</b> {closed_size:.4f}\n"
                    f"<b>남은 수량:</b> {remaining_size:.4f}\n"
                    f"<b>방향:</b> {side}\n\n"
                    f"포지션이 부분 청산되었습니다."
                )
                
                # 이벤트 ID 생성: "심볼_partial_fast_남은크기_타임스탬프"
                event_id = f"{symbol}_partial_fast_{remaining_size}_{datetime.now().timestamp()}"
                
                await self.notification_manager.send_alert(
                    event_type='PARTIAL_CLOSE',
                    title=f"✂️ {symbol} 부분 청산",
                    message=message,
                    data={
                        'symbol': symbol,
                        'closed_size': closed_size,
                        'remaining_size': remaining_size,
                        'side': side
                    },
                    event_id=event_id
                )
                
                logger.info(f"부분 청산 알림 전송 완료: {symbol}")
            
        except Exception as e:
            logger.error(f"부분 청산 알림 전송 실패 ({symbol}): {e}")
    
    async def _send_position_increase_alert(self, symbol: str, added_size: float, total_size: float, pos_info: dict):
        """포지션 추가 매수 알림 전송"""
        try:
            if self.notification_manager:
                position_amt = float(pos_info['positionAmt'])
                side = 'LONG' if position_amt > 0 else 'SHORT'
                avg_price = float(pos_info.get('entryPrice', 0))
                leverage = int(pos_info.get('leverage', 1))
                
                # 포지션 타입 확인 (시스템/수동)
                position_type = "수동"
                warning_msg = ""
                if self.position_manager:
                    pos = self.position_manager.get_position(symbol)
                    if pos and not pos.is_manual:
                        position_type = "시스템"
                        warning_msg = "\n\n⚠️ 시스템 포지션에 수동으로 추가하셨습니다.\n자동 거래가 영향을 받을 수 있습니다."
                
                message = (
                    f"<b>포지션 타입:</b> {position_type}\n"
                    f"<b>추가 수량:</b> {added_size:.4f}\n"
                    f"<b>총 수량:</b> {total_size:.4f}\n"
                    f"<b>평균 진입가:</b> ${avg_price:.2f}\n"
                    f"<b>방향:</b> {side}\n"
                    f"<b>레버리지:</b> {leverage}x{warning_msg}"
                )
                
                # 시스템 포지션에 수동 추가 시 다른 이벤트 타입 사용
                event_type = 'POSITION_MODIFIED' if position_type == "시스템" else 'POSITION_SIZE_CHANGED'
                
                # 이벤트 ID 생성: "심볼_increase_fast_총크기_타임스탬프"
                event_id = f"{symbol}_increase_fast_{total_size}_{datetime.now().timestamp()}"
                
                await self.notification_manager.send_alert(
                    event_type=event_type,
                    title=f"📈 {symbol} {position_type} 포지션 추가",
                    message=message,
                    data={
                        'symbol': symbol,
                        'added_size': added_size,
                        'total_size': total_size,
                        'side': side,
                        'avg_price': avg_price,
                        'leverage': leverage,
                        'position_type': position_type
                    },
                    event_id=event_id
                )
                
                logger.info(f"{position_type} 포지션 추가 알림 전송 완료: {symbol}")
            
        except Exception as e:
            logger.error(f"포지션 추가 알림 전송 실패 ({symbol}): {e}")
