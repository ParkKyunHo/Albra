# src/strategies/base_strategy.py
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging
import asyncio

# Signal 클래스 import 추가
from .signal import Signal, SignalType, SignalStrength

logger = logging.getLogger(__name__)

class BaseStrategy(ABC):
    """전략 기본 클래스"""
    
    def __init__(self, binance_api, position_manager, config: Dict):
        self.binance_api = binance_api
        self.position_manager = position_manager
        self.config = config
        
        # 리스크 매니저 참조 (멀티 계좌 모드에서 설정됨)
        self.risk_manager = None
        self.account_id = None  # 멀티 계좌 모드에서 계좌 ID
        
        # 공통 파라미터
        self.leverage = config.get('leverage', 15)
        self.position_size = config.get('position_size', 20)
        self.stop_loss_atr = config.get('stop_loss_atr', 2.0)
        self.take_profit_atr = config.get('take_profit_atr', 4.0)
        self.adx_min = config.get('adx_min', 20)
        self.min_signal_interval = config.get('min_signal_interval', 8)
        
        # 상태 관리
        self.is_running = False
        self.last_signal_time = {}
        self.strategy_name = self.__class__.__name__
        self.name = self.strategy_name
        
        # MDD 관리자 (하위 클래스에서 설정)
        self.mdd_manager = None
        
    @abstractmethod
    async def check_entry_signal(self, symbol: str, df_4h, df_15m, current_index: int) -> Tuple[bool, Optional[str]]:
        """진입 신호 체크 (구현 필요)"""
        pass
    
    @abstractmethod
    async def check_exit_signal(self, position, df_15m, current_index: int) -> Tuple[bool, str]:
        """청산 신호 체크 (구현 필요)"""
        pass
    
    async def calculate_position_size(self, symbol: str, use_dynamic_sizing: bool = True) -> float:
        """포지션 크기 계산 - 안전한 자금 관리 + MDD 제한 + 동적 사이징
        
        백테스트 개선사항 적용:
        1. Kelly Criterion 기반 동적 사이징
        2. 변동성 기반 조정
        3. ATR 기반 리스크 관리
        """
        try:
            # 계좌 잔고 조회
            account_balance = await self.binance_api.get_account_balance()
            
            # 현재 활성 포지션 수 확인
            active_positions = self.position_manager.get_active_positions(include_manual=False)
            active_count = len(active_positions)
            
            # 최대 포지션 수
            max_positions = self.config.get('max_positions', 3)
            
            # 현재 사용중인 일일 리스크 계산
            current_risk_used = 0.0
            for pos in active_positions:
                # 각 포지션의 리스크 계산 (간단히 포지션 크기로 추정)
                pos_risk = (pos.size * pos.entry_price) / account_balance * 100
                current_risk_used += pos_risk
            
            # 동적 포지션 크기 계산 시도
            if use_dynamic_sizing and hasattr(self.position_manager, 'calculate_dynamic_position_size'):
                try:
                    # 현재 가격과 ATR 가져오기
                    current_price = await self.binance_api.get_current_price(symbol)
                    
                    # 간단한 변동성 계산 (15분봉 기준)
                    klines = await self.binance_api.get_klines(symbol, '15m', limit=100)
                    if not klines.empty:
                        current_atr = klines['atr'].iloc[-1] if 'atr' in klines.columns else current_price * 0.02
                        returns = klines['close'].pct_change().dropna()
                        current_volatility = returns.std() * (96**0.5) * (252**0.5)  # 연환산
                    else:
                        current_atr = current_price * 0.02  # 기본값 2%
                        current_volatility = 0.15  # 기본 변동성 15%
                    
                    # 과거 성과 데이터 (있다면)
                    historical_performance = getattr(self, 'historical_performance', None)
                    
                    # 동적 포지션 크기 계산
                    dynamic_position_size_pct = self.position_manager.calculate_dynamic_position_size(
                        strategy_type=self.strategy_name,
                        current_risk_used=current_risk_used,
                        current_atr=current_atr,
                        current_price=current_price,
                        historical_performance=historical_performance,
                        current_volatility=current_volatility
                    )
                    
                    # 포지션 크기를 비율로 사용
                    base_position_size = dynamic_position_size_pct / 100
                    logger.info(f"동적 포지션 크기 적용: {dynamic_position_size_pct:.1f}%")
                    
                except Exception as e:
                    logger.warning(f"동적 포지션 크기 계산 실패, 기본값 사용: {e}")
                    base_position_size = self.position_size / 100
            else:
                # 기본 포지션 크기 (설정값)
                base_position_size = self.position_size / 100
            
            # MDD 제한에 따른 포지션 크기 조정
            if self.mdd_manager:
                mdd_restrictions = await self.mdd_manager.check_mdd_restrictions(account_balance)
                if mdd_restrictions['position_size_multiplier'] < 1.0:
                    logger.info(f"MDD 제한으로 포지션 크기 축소: {mdd_restrictions['position_size_multiplier']*100:.0f}%")
                    base_position_size *= mdd_restrictions['position_size_multiplier']
            
            # 2. 남은 자금 비율 계산 (최대 90% 사용)
            max_total_usage = 0.9  # 전체 자금의 90%만 사용
            used_percentage = active_count * base_position_size
            remaining_percentage = max_total_usage - used_percentage
            
            # 3. 실제 사용할 포지션 크기 결정
            if remaining_percentage <= 0:
                logger.warning(f"자금 한도 초과: 사용중 {used_percentage*100:.1f}%")
                return 0.0
            
            # 남은 포지션 슬롯 수
            remaining_slots = max_positions - active_count
            if remaining_slots <= 0:
                logger.warning(f"최대 포지션 수 도달: {active_count}/{max_positions}")
                return 0.0
            
            # 안전한 포지션 크기 = min(설정값, 남은자금/남은슬롯)
            safe_position_size = min(base_position_size, remaining_percentage / remaining_slots)
            
            # 포지션 가치 계산
            position_value = account_balance * safe_position_size
            
            logger.info(f"포지션 크기 계산: 잔고=${account_balance:.2f}, "
                       f"활성포지션={active_count}, "
                       f"사용비율={safe_position_size*100:.1f}%")
            
            # 현재 가격 조회 (이미 위에서 조회했으면 재사용)
            if 'current_price' not in locals():
                current_price = await self.binance_api.get_current_price(symbol)
            
            # 수량 계산
            quantity = position_value / current_price
            
            # 심볼별 정밀도 적용
            quantity = await self.binance_api.round_quantity(symbol, quantity)
            
            # 최소 주문 금액 체크 (보통 $10)
            min_notional = 10.0  # USDT
            if quantity * current_price < min_notional:
                logger.warning(f"주문 금액이 최소값 미만: ${quantity * current_price:.2f} < ${min_notional}")
                return 0.0
            
            return quantity
            
        except Exception as e:
            logger.error(f"포지션 크기 계산 실패: {e}")
            return 0.0
    
    async def can_enter_position(self, symbol: str) -> bool:
        """포지션 진입 가능 여부 체크"""
        # 1. 이미 포지션이 있는지 확인
        if self.position_manager.is_position_exist(symbol):
            return False
        
        # 2. 최소 신호 간격 체크
        if symbol in self.last_signal_time:
            time_since_last = (datetime.now() - self.last_signal_time[symbol]).total_seconds() / 3600
            if time_since_last < self.min_signal_interval:
                return False
        
        # 3. 최대 포지션 수 체크
        active_positions = self.position_manager.get_active_positions(include_manual=False)
        max_positions = self.config.get('max_positions', 3)
        
        if len(active_positions) >= max_positions:
            return False
        
        # 4. 리스크 상태 체크 (멀티 계좌 모드에서만)
        if await self._check_risk_status() == False:
            return False
        
        return True
    
    async def _check_risk_status(self) -> bool:
        """리스크 상태 체크 (각 전략이 독립적으로 판단)"""
        # 멀티 계좌 모드가 아니면 항상 허용
        if not self.risk_manager or not self.account_id:
            return True
        
        try:
            # 리스크 권고사항 확인
            risk_recommendation = self.risk_manager.get_risk_recommendation(self.account_id)
            risk_level = risk_recommendation.get('level', 'UNKNOWN')
            
            # 전략별 독립적 판단
            if risk_level == 'CRITICAL':
                # CRITICAL 레벨에서는 대부분의 전략이 거래 중단을 선택
                logger.warning(f"[{self.strategy_name}] Risk level CRITICAL - 자발적 거래 중단")
                return False
                
            elif risk_level == 'HIGH':
                # HIGH 레벨에서는 전략별로 다르게 대응 가능
                if self.config.get('pause_on_high_risk', True):
                    logger.warning(f"[{self.strategy_name}] Risk level HIGH - 설정에 따라 거래 중단")
                    return False
                else:
                    logger.info(f"[{self.strategy_name}] Risk level HIGH - 계속 거래 (설정에 따름)")
                    return True
                    
            # MEDIUM 이하는 정상 거래
            return True
            
        except Exception as e:
            logger.error(f"리스크 상태 체크 중 오류: {e}")
            # 에러 시에는 안전하게 거래 허용 (각 전략의 독립성 보장)
            return True
    
    async def execute_entry(self, symbol: str, direction: str, stop_loss: float, take_profit: float):
        """포지션 진입 실행 - 시장가 주문 체결가 문제 수정"""
        try:
            # 포지션 크기 계산
            quantity = await self.calculate_position_size(symbol)
            if quantity <= 0:
                logger.error(f"유효하지 않은 포지션 크기: {quantity}")
                return False
            
            # 레버리지 설정 (마진 타입도 함께 설정됨)
            await self.binance_api.set_leverage(symbol, self.leverage)
            
            # 주문 실행
            side = 'BUY' if direction == 'long' else 'SELL'
            order = await self.binance_api.place_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type='MARKET'
            )
            
            if not order:
                logger.error(f"주문 실행 실패: {symbol} {direction}")
                return False
            
            # 시장가 주문 체결가 확인 - 여러 방법으로 시도
            entry_price = 0.0
            
            # 1. avgPrice 확인 (바이낸스 시장가 주문 응답)
            if 'avgPrice' in order and order['avgPrice']:
                entry_price = float(order['avgPrice'])
                logger.debug(f"체결가 from avgPrice: {entry_price}")
            
            # 2. fills 정보에서 가중평균가 계산
            elif 'fills' in order and order['fills']:
                total_qty = 0
                total_value = 0
                for fill in order['fills']:
                    fill_qty = float(fill['qty'])
                    fill_price = float(fill['price'])
                    total_qty += fill_qty
                    total_value += fill_qty * fill_price
                
                if total_qty > 0:
                    entry_price = total_value / total_qty
                    logger.debug(f"체결가 from fills: {entry_price}")
            
            # 3. price 필드 확인 (일부 응답에서 사용)
            elif 'price' in order and order['price']:
                entry_price = float(order['price'])
                logger.debug(f"체결가 from price: {entry_price}")
            
            # 4. 그래도 없으면 현재가 조회
            if entry_price <= 0:
                current_price = await self.binance_api.get_current_price(symbol)
                if current_price:
                    entry_price = current_price
                    logger.warning(f"{symbol} 체결가 확인 실패, 현재가 사용: {entry_price}")
                else:
                    logger.error(f"{symbol} 체결가 확인 완전 실패")
                    return False
            
            # === 핫픽스: 포지션 등록 전 대기 ===
            await asyncio.sleep(0.5)  # 500ms 대기
            
            # 포지션 정보 저장 - 재시도 로직 추가
            position = None
            max_retries = 3
            
            for attempt in range(max_retries):
                try:
                    position = await self.position_manager.add_position(
                        symbol=symbol,
                        side=direction,
                        size=quantity,
                        entry_price=entry_price,
                        leverage=self.leverage,
                        strategy_name=self.strategy_name,
                        stop_loss=stop_loss,
                        take_profit=take_profit
                    )
                    
                    if position:
                        logger.info(f"✅ 포지션 등록 성공 (시도 {attempt+1}/{max_retries})")
                        break
                        
                except Exception as e:
                    logger.error(f"포지션 등록 시도 {attempt+1} 실패: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)  # 재시도 전 1초 대기
                    else:
                        raise
            
            # Position 객체가 반환되지 않으면 실패
            if not position:
                logger.error(f"포지션 추가 실패: {symbol}")
                return False
            
            # === 포지션 확인 ===
            await asyncio.sleep(1)  # 등록 완료 대기
            
            # 포지션이 실제로 등록되었는지 확인
            registered_position = self.position_manager.get_position(symbol)
            if not registered_position:
                logger.error(f"⚠️ 포지션 등록 검증 실패: {symbol}")
                # 강제 동기화 시도
                await self.position_manager.sync_positions()
                
            logger.info(f"✅ 포지션 객체 생성 성공: {position.symbol}")
            
            # 손절/익절 주문 설정 (옵션)
            if self.config.get('use_stop_orders', False):
                await self._place_stop_orders(symbol, direction, stop_loss, take_profit)
            
            # 마지막 신호 시간 업데이트
            self.last_signal_time[symbol] = datetime.now()
            
            logger.info(f"✅ 포지션 진입 성공: {symbol} {direction} {quantity} @ {entry_price}")
            
            # 알림 전송 (position_manager에서 처리됨)
            return True
            
        except Exception as e:
            logger.error(f"포지션 진입 실패: {e}", exc_info=True)
            return False
    
    async def execute_exit(self, position, reason: str):
        """포지션 청산 실행"""
        try:
            symbol = position.symbol
            
            # 청산 주문
            side = 'SELL' if position.side.upper() == 'LONG' else 'BUY'
            
            order = await self.binance_api.place_order(
                symbol=symbol,
                side=side,
                quantity=position.size,
                order_type='MARKET'
            )
            
            if not order:
                logger.error(f"청산 주문 실패: {symbol}")
                return False
            
            # 청산가 확인 (execute_entry와 동일한 로직)
            exit_price = 0.0
            
            if 'avgPrice' in order and order['avgPrice']:
                exit_price = float(order['avgPrice'])
            elif 'fills' in order and order['fills']:
                total_qty = 0
                total_value = 0
                for fill in order['fills']:
                    fill_qty = float(fill['qty'])
                    fill_price = float(fill['price'])
                    total_qty += fill_qty
                    total_value += fill_qty * fill_price
                if total_qty > 0:
                    exit_price = total_value / total_qty
            elif 'price' in order and order['price']:
                exit_price = float(order['price'])
            
            if exit_price <= 0:
                current_price = await self.binance_api.get_current_price(symbol)
                if current_price:
                    exit_price = current_price
            
            # 손익 계산
            if position.side.upper() == 'LONG':
                pnl_pct = (exit_price - position.entry_price) / position.entry_price * 100
            else:
                pnl_pct = (position.entry_price - exit_price) / position.entry_price * 100
            
            # 레버리지 적용한 실제 손익
            net_pnl_pct = pnl_pct * self.leverage
            
            # MDD Manager에 거래 결과 알림 (개선된 MDD 관리)
            if self.mdd_manager:
                trade_won = net_pnl_pct > 0
                self.mdd_manager.update_recovery_status(trade_won)
                check_mark = '\u2713' if trade_won else '\u2717'
                logger.info(f"MDD 회복 상태 업데이트: {check_mark} ({net_pnl_pct:+.2f}%)")
            
            # 포지션 제거
            await self.position_manager.remove_position(symbol, reason, exit_price)
            
            # 청산 후 쿨다운을 위해 last_signal_time 업데이트
            # 이렇게 하면 청산 직후 재진입을 방지할 수 있음
            self.last_signal_time[symbol] = datetime.now()
            
            logger.info(f"🔚 포지션 청산: {symbol} @ {exit_price} ({pnl_pct:+.2f}%) - {reason}")
            logger.info(f"   재진입 쿨다운: {self.min_signal_interval}시간")
            return True
            
        except Exception as e:
            logger.error(f"포지션 청산 실패: {e}")
            return False
    
    async def _place_stop_orders(self, symbol: str, direction: str, stop_loss: float, take_profit: float):
        """손절/익절 주문 설정"""
        try:
            # 손절 주문
            stop_side = 'SELL' if direction == 'long' else 'BUY'
            stop_type = 'STOP_MARKET'
            
            await self.binance_api.place_stop_order(
                symbol=symbol,
                side=stop_side,
                stop_price=stop_loss,
                order_type=stop_type
            )
            
            # 익절 주문 
            tp_side = 'SELL' if direction == 'long' else 'BUY'
            
            await self.binance_api.place_limit_order(
                symbol=symbol,
                side=tp_side,
                price=take_profit,
                reduce_only=True
            )
            
            logger.info(f"손절/익절 설정: SL={stop_loss:.2f}, TP={take_profit:.2f}")
            
        except Exception as e:
            logger.error(f"손절/익절 주문 실패: {e}")
    
    async def run(self):
        """전략 실행 (기본 구현)"""
        self.is_running = True
        logger.info(f"{self.strategy_name} 전략 시작")
        
        while self.is_running:
            try:
                # 활성 심볼 목록 (설정에서 가져오기)
                symbols = self.config.get('symbols', ['BTCUSDT'])
                
                for symbol in symbols:
                    # 포지션 체크 및 관리
                    position = self.position_manager.get_position(symbol)
                    
                    if position and position.status == 'ACTIVE':
                        # 기존 포지션 관리
                        await self._manage_position(position)
                    else:
                        # 신규 진입 체크
                        if await self.can_enter_position(symbol):
                            await self._check_new_entry(symbol)
                
                # 대기
                await asyncio.sleep(60)  # 1분마다 체크
                
            except Exception as e:
                logger.error(f"전략 실행 오류: {e}")
                await asyncio.sleep(30)
    
    async def _manage_position(self, position):
        """포지션 관리 (하위 클래스에서 구현 가능)"""
        pass
    
    async def _check_new_entry(self, symbol: str):
        """신규 진입 체크 (하위 클래스에서 구현 가능)"""
        pass
    
    async def stop(self):
        """전략 중지 - async로 변경"""
        self.is_running = False
        logger.info(f"{self.strategy_name} 전략 중지")