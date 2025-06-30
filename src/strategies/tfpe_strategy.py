# src/strategies/tfpe_strategy.py
import asyncio
import pandas as pd
import pandas_ta as ta
import numpy as np
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
import logging

from .base_strategy import BaseStrategy
from ..core.mdd_manager_improved import ImprovedMDDManager
from ..analysis.market_regime_analyzer import get_regime_analyzer, MarketRegime
from ..analysis.performance_tracker import get_performance_tracker
from ..core.risk_parity_allocator import get_risk_parity_allocator

logger = logging.getLogger(__name__)

class TFPEStrategy(BaseStrategy):
    """TFPE (Trend Following Pullback Entry) Donchian Channel 전략"""
    
    def __init__(self, binance_api, position_manager, config: Dict, config_manager=None):
        super().__init__(binance_api, position_manager, config)
        
        # 전략 이름 설정
        self.strategy_name = "TFPE"
        self.name = "TFPE Donchian"
        
        # 기본 파라미터
        self.position_size = config.get('position_size', 24)  # 계좌의 24%
        self.signal_threshold = config.get('signal_threshold', 4)  # 백테스트 개선: 3 → 4
        self.min_momentum = config.get('min_momentum', 2.0)  # 최소 2% 모멘텀
        self.volume_spike = config.get('volume_spike', 1.5)
        self.ema_distance_max = config.get('ema_distance_max', 0.015)  # 1.5%
        
        # Donchian Channel 파라미터
        self.dc_period = config.get('dc_period', 20)  # Donchian 기간
        self.price_position_high = config.get('price_position_high', 0.7)
        self.price_position_low = config.get('price_position_low', 0.3)
        self.price_position_neutral_min = config.get('price_position_neutral_min', 0.4)
        self.price_position_neutral_max = config.get('price_position_neutral_max', 0.6)
        
        # RSI 파라미터
        self.rsi_pullback_long = config.get('rsi_pullback_long', 40)
        self.rsi_pullback_short = config.get('rsi_pullback_short', 60)
        self.rsi_neutral_long = config.get('rsi_neutral_long', 20)
        self.rsi_neutral_short = config.get('rsi_neutral_short', 80)
        
        # 횡보장 RSI 극단값 (백테스팅과 동일)
        self.rsi_oversold = config.get('rsi_oversold', 30)
        self.rsi_overbought = config.get('rsi_overbought', 70)
        
        # 채널폭 파라미터
        self.channel_width_threshold = config.get('channel_width_threshold', 0.05)  # 5%
        
        # 피보나치 되돌림 레벨 (백테스팅과 동일)
        self.fib_min = config.get('fib_min', 0.382)
        self.fib_max = config.get('fib_max', 0.786)
        
        # 손절/익절 (백테스팅과 동일)
        self.stop_loss_atr = config.get('stop_loss_atr', 1.5)
        self.take_profit_atr = config.get('take_profit_atr', 5.0)  # 백테스트 개선: 3.0 → 5.0
        
        # ADX 파라미터
        self.adx_min = config.get('adx_min', 25)  # 백테스트 개선: 20 → 25
        
        # 신호 간격
        self.min_signal_interval = config.get('min_signal_interval', 4)  # 4시간
        
        # 스윙/모멘텀 파라미터
        self.swing_period = config.get('swing_period', 20)
        self.momentum_lookback = config.get('momentum_lookback', 20)
        
        # 전략 모드 (기본: donchian, 레거시: ma)
        self.trend_mode = config.get('trend_mode', 'donchian')
        
        # 데이터 캐시
        self.data_cache = {}
        self.last_data_update = {}
        self.df_4h_cache = None  # 4시간봉 데이터 캐시 추가
        
        # 스마트 재개 관리자 참조 (나중에 주입)
        self.smart_resume_manager = None
        
        # 알림 매니저 참조 (나중에 주입)
        self.notification_manager = None
        
        # 분석 컴포넌트
        self.performance_tracker = None
        self.market_regime_analyzer = None
        self.risk_parity_allocator = None
        self.last_regime_check = None
        self.current_regime = None
        self.regime_check_interval = config.get('regime_check_interval', 30)
        self.regime_adjustments = {}
        
        # MDD 관리자 (나중에 초기화)
        self.mdd_manager = None
        
        # 메이저 코인 목록 (설정에서 로드)
        self.major_coins = config.get('major_coins', [
            'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 
            'SOLUSDT', 'XRPUSDT', 'ADAUSDT'
        ])
        
        # 실시간 모니터링 컴포넌트
        self.price_monitor = None
        self.signal_processor = None
        self.realtime_enabled = config.get('realtime_enabled', True)
        
        # 실시간 체크 설정
        self.realtime_config = {
            'quick_rsi_oversold': config.get('quick_rsi_oversold', 35),
            'quick_rsi_overbought': config.get('quick_rsi_overbought', 65),
            'price_spike_threshold': config.get('price_spike_threshold', 0.01),
            'realtime_cooldown': config.get('realtime_cooldown', 30)
        }
        
        # 시장 레짐 분석기
        self.regime_analyzer = None  # 나중에 초기화
        self.last_regime_check = None
        self.current_regime = MarketRegime.NORMAL
        
        # 성과 추적기
        self.performance_tracker = get_performance_tracker()
        self.historical_performance = None  # Kelly Criterion용
        
        logger.info(f"TFPE Donchian Channel 전략 초기화 완료")
        logger.info(f"추세 모드: {self.trend_mode}, DC 기간: {self.dc_period}")
        logger.info(f"파라미터: 포지션크기={self.position_size}%, 신호임계값={self.signal_threshold}/5")
        logger.info(f"손절/익절: SL={self.stop_loss_atr}xATR, TP={self.take_profit_atr}xATR")
        logger.info(f"RSI 극단값: 과매도={self.rsi_oversold}, 과매수={self.rsi_overbought}")
        logger.info(f"실시간 모니터링: {'활성화' if self.realtime_enabled else '비활성화'}")
        logger.info(f"거래 코인: {', '.join(self.major_coins)}")
        
        # 리포트 관련 초기화 추가
        self._last_status_report = None
        self._report_lock = asyncio.Lock()  # 중복 방지용 락
    
    async def run_cycle(self):
        """전략 실행 사이클 - BaseStrategy 인터페이스 구현 (수정됨)"""
        try:
            # 초기화 체크
            if not hasattr(self, '_initialized'):
                await self._initialize()
                self._initialized = True
            
            # 캔들 준비 단계 체크 (14분 50초)
            is_prep_time, next_candle_time = await self._is_candle_preparation_time()
            if is_prep_time:
                await self._prepare_for_candle_close(next_candle_time)
            
            # 캔들 종가 기반 체크
            await self._run_candle_close_cycle()
            
            # 공통 작업 (동기화 등)
            await self._periodic_maintenance()
            
        except Exception as e:
            logger.error(f"{self.name} 사이� 실행 실패: {e}")
            # 에러 발생해도 다음 사이클은 계속 실행
    
    async def _get_binance_server_time(self) -> datetime:
        """바이낸스 서버 시간 조회"""
        try:
            server_time_ms = await self.binance_api.get_server_time()
            if server_time_ms:
                return datetime.fromtimestamp(server_time_ms / 1000)
            else:
                # 실패 시 로컬 시간 사용
                logger.warning("서버 시간 조회 실패, 로컬 시간 사용")
                return datetime.now()
        except Exception as e:
            logger.error(f"서버 시간 조회 오류: {e}")
            return datetime.now()
    
    async def _is_candle_close_time(self) -> Tuple[bool, Optional[datetime]]:
        """캔들 종가 체크 시간인지 확인 - 서버 시간 기준"""
        candle_config = self.config.get('candle_close_check', {})
        use_server_time = candle_config.get('use_server_time', True)
        check_window = candle_config.get('check_window_seconds', 30)
        
        # 시간 기준 선택
        if use_server_time:
            current_time = await self._get_binance_server_time()
        else:
            current_time = datetime.now()
        
        current_minute = current_time.minute
        current_second = current_time.second
        
        # 15분 캔들 체크 시간인지 확인
        if current_minute % 15 == 0 and current_second < check_window:
            # 캔들 시간 계산
            candle_time = current_time.replace(minute=(current_minute // 15) * 15, second=0, microsecond=0)
            return True, candle_time
        
        return False, None
    
    async def _is_candle_preparation_time(self) -> Tuple[bool, Optional[datetime]]:
        """캔들 준비 시간인지 확인 - 14분 50초"""
        candle_config = self.config.get('candle_close_check', {})
        use_server_time = candle_config.get('use_server_time', True)
        preparation_seconds = candle_config.get('preparation_seconds', 10)  # 기본 10초 전
        
        # 시간 기준 선택
        if use_server_time:
            current_time = await self._get_binance_server_time()
        else:
            current_time = datetime.now()
        
        current_minute = current_time.minute
        current_second = current_time.second
        minutes_in_cycle = current_minute % 15
        
        # 14분 50초 ~ 14분 59초 사이인지 확인
        if minutes_in_cycle == 14 and current_second >= (60 - preparation_seconds):
            # 다음 캔들 시간 계산 - 안전한 방법
            # 15분 캔들이므로 현재 시간에서 남은 시간을 더함
            minutes_to_add = 15 - minutes_in_cycle
            next_candle_time = current_time + timedelta(minutes=minutes_to_add)
            next_candle_time = next_candle_time.replace(second=0, microsecond=0)
            return True, next_candle_time
        
        return False, None
    
    async def _prepare_for_candle_close(self, next_candle_time: datetime):
        """캔들 종가 전 준비 작업"""
        try:
            # 준비 시간에 한 번만 실행되도록 체크
            if not hasattr(self, '_last_prepare_time'):
                self._last_prepare_time = {}
            
            # 이미 이 캔들에 대해 준비했는지 확인
            for symbol in self.major_coins:
                if symbol in self._last_prepare_time and self._last_prepare_time[symbol] >= next_candle_time:
                    continue
                
                # 준비 완료 표시
                self._last_prepare_time[symbol] = next_candle_time
                
                # 미리 데이터 로드 및 캐시
                logger.info(f"🔔 {symbol} 캔들 종가 준비 중... (다음 캔들: {next_candle_time.strftime('%H:%M')})")  
                await self.fetch_and_prepare_data(symbol)
                
                # 준비된 포지션 체크로 미리 계산
                position = self.position_manager.get_position(symbol)
                if position and position.status == 'ACTIVE' and not position.is_manual:
                    logger.debug(f"  {symbol}: 포지션 관리 준비 완료")
                elif await self.can_enter_position(symbol):
                    logger.debug(f"  {symbol}: 진입 신호 체크 준비 완료")
            
            logger.info("✅ 캔들 종가 준비 완료 - 종가 시점에 즉시 실행 가능")
            
        except Exception as e:
            logger.error(f"캔들 준비 실패: {e}")
    
    async def _run_candle_close_cycle(self):
        """캔들 종가 기반 사이클 - 백테스팅과 동일"""
        tasks = []
        
        # 캔들 종가 체크 시간 확인
        is_check_time, candle_time = await self._is_candle_close_time()
        if not is_check_time or not candle_time:
            return

        
        if not hasattr(self, '_last_checked_candle'):
            self._last_checked_candle = {}
        
        # 새로운 캔들인지 확인 (전체 심볼에 대해 한 번만 체크)
        any_new_candle = False
        for symbol in self.major_coins:
            if symbol not in self._last_checked_candle or self._last_checked_candle[symbol] < candle_time:
                any_new_candle = True
                break
        
        if not any_new_candle:
            return
        
        logger.info(f"\n{'='*60}")
        logger.info(f"🕰️ 15분 캔들 종가 체크: {candle_time.strftime('%Y-%m-%d %H:%M')}")
        logger.info(f"{'='*60}")
    
        
        for symbol in self.major_coins:
            # 이미 이번 캔들에서 체크했으면 스킵
            if symbol in self._last_checked_candle and self._last_checked_candle[symbol] >= candle_time:
                continue
            
            # 체크 완료 표시
            self._last_checked_candle[symbol] = candle_time
            
            # 현재 포지션 확인 - 전략명 포함
            position = self.position_manager.get_position(symbol, self.strategy_name)
            
            # 1. 포지션이 있으면 관리
            if position and position.status == 'ACTIVE':
                # 자동 전략 포지션만 관리
                if not position.is_manual and position.strategy_name == self.strategy_name:
                    logger.info(f"  📈 {symbol}: 포지션 관리")
                    tasks.append(self._manage_position(position))
                else:
                    logger.info(f"  🤖 {symbol}: 수동 포지션 또는 다른 전략 포지션 - 건드리지 않음")
            
            # 2. 포지션이 없으면 진입 체크
            else:
                # 이중 체크: 포지션 매니저에서 다시 한번 확인
                if self.position_manager.is_position_exist(symbol, self.strategy_name):
                    logger.warning(f"  ⚠️ {symbol}: TFPE 포지션이 이미 존재합니다!")
                    continue
                    
                can_enter = await self.can_enter_position(symbol)
                
                if can_enter:
                    logger.info(f"  🔍 {symbol}: 진입 신호 체크")
                    tasks.append(self._check_new_entry(symbol))
                else:
                    # 쿨다운 상태 확인
                    if symbol in self.last_signal_time:
                        time_since_last = (datetime.now() - self.last_signal_time[symbol]).total_seconds() / 3600
                        logger.debug(f"  ⏸️ {symbol}: 쿨다운 {time_since_last:.1f}/{self.min_signal_interval}시간")
                    else:
                        logger.debug(f"  ❌ {symbol}: can_enter_position() = False")
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # 결과 로그
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"작업 실패: {result}")
        
        logger.info(f"{'='*60}\n")

    async def _initialize(self):
        """전략 초기화 (한 번만 실행)"""
        logger.info(f"{self.name} 전략 초기화 시작")
        
        # MDD 관리자 초기화
        mdd_config = self.config.get('mdd_protection', {
            'max_allowed_mdd': 40.0,
            'mdd_recovery_threshold': 15.0,
            'mdd_position_reduction': 0.5,
            'mdd_stop_new_trades': True,
            'mdd_force_close_threshold': 50.0
        })
        self.mdd_manager = ImprovedMDDManager(mdd_config, self.notification_manager)
        logger.info("✓ MDD 보호 기능 활성화")
        
        if self.realtime_enabled:
            await self.initialize_realtime_monitoring()
            logger.info("✓ 실시간 모니터링 활성화")
        else:
            logger.info("✓ 주기적 체크 모드 활성화")
        
        # 시장 레짐 분석기 초기화
        regime_config = self.config.get('market_regime', {})
        self.regime_analyzer = get_regime_analyzer(regime_config)
        logger.info("✓ 시장 레짐 분석기 초기화")
        
        # 리스크 패리티 할당기 초기화
        self.risk_parity_allocator = get_risk_parity_allocator(self.performance_tracker)
        logger.info("✓ 리스크 패리티 할당기 초기화")
        
        logger.info("✓ 리포트 타이머 초기화")

    async def _periodic_maintenance(self):
        """주기적 유지보수 작업"""
        try:
            # 시장 레짐 체크 (30분마다)
            if not self.last_regime_check or (datetime.now() - self.last_regime_check).seconds > 1800:
                await self._check_market_regime()
                self.last_regime_check = datetime.now()
            
            # MDD 체크 및 강제 청산
            if self.mdd_manager:
                # 활성 포지션 수 업데이트
                active_positions = self.position_manager.get_active_positions(include_manual=False)
                tfpe_positions = [p for p in active_positions if p.strategy_name == self.strategy_name]
                self.mdd_manager.update_position_count(len(tfpe_positions))
                
                current_balance = await self.binance_api.get_account_balance()
                mdd_restrictions = await self.mdd_manager.check_mdd_restrictions(current_balance)
                
                # 강제 청산 필요 시
                if mdd_restrictions['force_close_positions']:
                    logger.critical(f"MDD 강제 청산 실행: {mdd_restrictions['reason']}")
                    await self._force_close_all_positions("MDD 강제 청산")
            
            # 동적 동기화 주기 적용
            if not hasattr(self, '_last_sync'):
                self._last_sync = datetime.now()
            
            # 포지션 상태에 따른 동기화 주기
            sync_interval = self._get_sync_interval_for_strategy()
            
            if (datetime.now() - self._last_sync).seconds >= sync_interval:
                if hasattr(self.position_manager, 'sync_positions'):
                    await self.position_manager.sync_positions()
                self._last_sync = datetime.now()
                logger.debug(f"포지션 동기화 완료 - 다음 동기화: {sync_interval}초 후")
            
            # 실시간 모니터 상태 체크
            if self.realtime_enabled and self.price_monitor:
                if not self.price_monitor.is_running:
                    logger.warning("실시간 모니터 재시작 필요")
                    await self.initialize_realtime_monitoring()
            
            # 30분마다 시스템 상태 리포트 전송
            await self._send_system_status_report()
                    
        except Exception as e:
            logger.error(f"유지보수 작업 실패: {e}")
    
    async def _force_close_all_positions(self, reason: str):
        """모든 포지션 강제 청산"""
        try:
            active_positions = self.position_manager.get_active_positions(include_manual=False)
            tfpe_positions = [p for p in active_positions if p.strategy_name == self.strategy_name]
            
            if not tfpe_positions:
                logger.info("강제 청산할 TFPE 포지션이 없습니다")
                return
            
            logger.warning(f"MDD 강제 청산: {len(tfpe_positions)}개 포지션")
            
            # 모든 포지션 청산
            for position in tfpe_positions:
                try:
                    logger.info(f"강제 청산 실행: {position.symbol}")
                    success = await self.execute_exit(position, reason)
                    if success:
                        logger.info(f"✅ {position.symbol} 강제 청산 성공")
                    else:
                        logger.error(f"❌ {position.symbol} 강제 청산 실패")
                    
                    # API 레이트 리밋 방지
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"{position.symbol} 강제 청산 중 오류: {e}")
            
        except Exception as e:
            logger.error(f"강제 청산 작업 실패: {e}")
    
    async def _send_system_status_report(self):
        """시스템 상태 리포트 텔레그램 전송 (30분마다)"""
        # 중복 방지 락
        async with self._report_lock:
            try:
                # 서버 시간 먼저 가져오기
                server_time = await self._get_binance_server_time()
                
                # 초기화 체크 (_initialize에서 이미 설정됨)
                if self._last_status_report is None:
                    is_first_run = True
                    self._last_status_report = server_time - timedelta(minutes=30)  # 즉시 전송되도록
                    logger.info("시스템 상태 리포트 첫 실행 - 즉시 전송")
                else:
                    is_first_run = False
                
                # 서버 시간 기준으로 체크
                elapsed_seconds = (server_time - self._last_status_report).total_seconds()
                
                # config에서 값 읽기
                status_report_config = self.config.get('status_report', {})
                MIN_INTERVAL = status_report_config.get('min_interval', 1500)  # 기본값 25분
                MAX_INTERVAL = status_report_config.get('max_interval', 2100)  # 기본값 35분
                
                # 최소 간격 미달이라면 리턴  
                if elapsed_seconds < MIN_INTERVAL and not is_first_run:
                    return
                
                # 캔들 체크 주기와 동기화를 위해 15분 단위로 정렬
                current_minute = server_time.minute
                # 0, 15, 30, 45분에만 전송 (캔들 체크 주기와 동일)
                if current_minute % 15 != 0 and elapsed_seconds < MAX_INTERVAL and not is_first_run:
                    return
            
                # 현재 포지션 정보
                active_positions = self.position_manager.get_active_positions(include_manual=False)
                tfpe_positions = [p for p in active_positions if p.strategy_name == self.strategy_name]
                
                # 계좌 잔고
                balance = await self.binance_api.get_account_balance()
            
                # MDD 상태
                mdd_info = None
                mdd_level_text = ""
                if self.mdd_manager:
                    mdd_info = await self.mdd_manager.check_mdd_restrictions(balance)
                    current_mdd = self.mdd_manager.current_mdd
                    
                    # MDD 레벨별 텍스트
                    mdd_level = mdd_info.get('mdd_level', 0)
                    if mdd_level >= 3:
                        mdd_level_text = " 🔴 Level 3"
                    elif mdd_level >= 2:
                        mdd_level_text = " 🟡 Level 2"
                    elif mdd_level >= 1:
                        mdd_level_text = " 🟠 Level 1"
                    else:
                        mdd_level_text = " 🟢"
                else:
                    current_mdd = 0
            
                # 포지션별 상태 - 병렬 처리로 성능 개선
                position_details = []
                if tfpe_positions:
                    # 현재가 병렬 조회
                    price_tasks = [
                        self.binance_api.get_current_price(pos.symbol) 
                        for pos in tfpe_positions
                    ]
                    current_prices = await asyncio.gather(*price_tasks, return_exceptions=True)
                    
                    for pos, current_price in zip(tfpe_positions, current_prices):
                        if isinstance(current_price, Exception):
                            logger.error(f"가격 조회 실패 ({pos.symbol}): {current_price}")
                            position_details.append(
                                f"  • {pos.symbol}: {pos.side} @ ${pos.entry_price:.2f}\n"
                                f"    현재가: 조회 실패"
                            )
                        elif current_price:
                            # 손익률 계산
                            if pos.side.upper() == 'LONG':
                                pnl_pct = (current_price - pos.entry_price) / pos.entry_price * 100 * self.leverage
                            else:
                                pnl_pct = (pos.entry_price - current_price) / pos.entry_price * 100 * self.leverage
                            
                            position_details.append(
                                f"  • {pos.symbol}: {pos.side} @ ${pos.entry_price:.2f}\n"
                                f"    현재가: ${current_price:.2f} ({pnl_pct:+.1f}%)"
                            )
                
                # 모니터링 심볼 목록
                monitoring_symbols = ', '.join(self.major_coins[:5])  # 처음 5개만 표시
                if len(self.major_coins) > 5:
                    monitoring_symbols += f" 외 {len(self.major_coins) - 5}개"
                
                # 시스템 시작 시간 확인
                if not hasattr(self, '_strategy_start_time'):
                    self._strategy_start_time = datetime.now()
                
                uptime_seconds = (datetime.now() - self._strategy_start_time).total_seconds()
                uptime_hours = int(uptime_seconds // 3600)
                uptime_minutes = int((uptime_seconds % 3600) // 60)
                
                # 리포트 생성
                report = f"""
📈 <b>TFPE 전략 상태 리포트</b>

⏰ 시간: {server_time.strftime('%Y-%m-%d %H:%M:%S')}
🏃 가동 시간: {uptime_hours}시간 {uptime_minutes}분
💰 계좌 잔고: ${balance:,.2f}
📉 현재 MDD: {current_mdd:.1f}%{mdd_level_text}
🎯 포지션: {len(tfpe_positions)}개 / 최대 {self.config.get('max_positions', 3)}개

🔍 <b>모니터링 심볼:</b>
{monitoring_symbols}

📦 <b>활성 포지션:</b>
{chr(10).join(position_details) if position_details else '  포지션 없음'}

⚙️ <b>전략 파라미터:</b>
  • 레버리지: {self.leverage}x
  • 포지션 크기: {self.position_size}%
  • 신호 임계값: {self.signal_threshold}/5
  • 쿨다운: {self.min_signal_interval}시간
"""
                
                # 첫 실행 안내 추가
                if is_first_run:
                    report += "\n🆕 <b>시스템 시작</b>: 첫 상태 리포트입니다."
                
                # MDD 제한 상태 추가
                if mdd_info:
                    if mdd_info.get('mdd_level', 0) > 0:
                        report += f"\n\n📋 <b>MDD 관리 상태:</b>"
                        report += f"\n  • 현재 레벨: {mdd_info.get('mdd_level', 0)}"
                        report += f"\n  • 포지션 크기: {mdd_info.get('position_size_multiplier', 1.0)*100:.0f}%"
                        report += f"\n  • 상태: {mdd_info.get('reason', '')}"
                    
                    if not mdd_info['allow_new_trades']:
                        report += f"\n\n⚠️ <b>경고:</b> 신규 거래 중단"
                
                # 전송
                if self.notification_manager:
                    await self.notification_manager.send_alert(
                        event_type='HEARTBEAT',
                        title='📈 시스템 상태 리포트',
                        message=report,
                        force=True  # 강제 전송 (중복 방지 무시)
                    )
                    logger.info("시스템 상태 리포트 전송 완료")
                
                self._last_status_report = server_time
                
            except Exception as e:
                logger.error(f"시스템 상태 리포트 전송 실패: {e}")
    
    def _get_sync_interval_for_strategy(self) -> int:
        """전략용 동기화 주기 결정 (초)
        
        동기화 주기 최적화 이유:
        1. 자동 포지션 있을 때: 60초 - 빠른 변화 감지 필요
        2. 포지션 없을 때: 300초 - API 호출 최소화
        3. 높은 변동성 시: 30초 - 긴급 대응 필요
        """
        try:
            # 활성 포지션 확인
            active_positions = self.position_manager.get_active_positions(include_manual=False)
            
            # TFPE 전략 포지션만 필터링
            strategy_positions = [p for p in active_positions 
                                if p.strategy_name == self.strategy_name]
            
            if not strategy_positions:
                # 포지션 없으면 긴 주기
                return 300  # 5분
            
            # 포지션이 있으면 빠른 동기화
            return 60  # 1분
            
        except Exception as e:
            logger.error(f"동기화 주기 결정 오류: {e}")
            return 300  # 기본값
    
    async def initialize_realtime_monitoring(self):
        """실시간 모니터링 초기화 - 비활성화 (캔들 종가 기준으로 변경)"""
        # 실시간 모니터링을 사용하지 않고 캔들 종가 기준으로만 체크
        logger.info("실시간 모니터링 비활성화 - 캔들 종가 기준 사용")
        self.realtime_enabled = False
        return
            
        try:
            # 가격 모니터 생성
            from ..core.realtime_price_monitor import RealtimePriceMonitor
            self.price_monitor = RealtimePriceMonitor(self.binance_api)
            
            # 신호 프로세서 생성
            from ..core.realtime_signal_processor import RealtimeSignalProcessor
            self.signal_processor = RealtimeSignalProcessor(self, self.position_manager)
            
            # 이벤트 핸들러 등록
            self.price_monitor.on('price_update', self.signal_processor.on_price_update)
            self.price_monitor.on('kline_closed', self.signal_processor.on_kline_closed)
            self.price_monitor.on('connected', self._on_websocket_connected)
            self.price_monitor.on('disconnected', self._on_websocket_disconnected)
            
            # 모니터링할 심볼 추가
            await self.price_monitor.add_symbols(self.major_coins)
            
            # WebSocket 시작
            asyncio.create_task(self.price_monitor.start())
            
            logger.info("✓ 실시간 모니터링 초기화 완료")
            
        except Exception as e:
            logger.error(f"실시간 모니터링 초기화 실패: {e}")
            self.realtime_enabled = False
    
    async def _on_websocket_connected(self):
        """WebSocket 연결시 호출"""
        logger.info("✓ WebSocket 연결됨 - 실시간 모니터링 시작")
        
        if self.notification_manager:
            await self.notification_manager.send_alert(
                event_type="SYSTEM_INFO",
                title="🔌 실시간 모니터링 연결",
                message=f"WebSocket 연결 성공\n모니터링: {', '.join(self.major_coins[:3])}..."
            )
    
    async def _on_websocket_disconnected(self):
        """WebSocket 연결 해제시 호출"""
        logger.warning("WebSocket 연결 해제됨")
    
    async def fetch_and_prepare_data(self, symbol: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """데이터 수집 및 준비 (4시간봉 캐시 추가)"""
        try:
            # 캔들 완성 시점에만 체크하므로 캐시 비활성화
            # 매번 최신 데이터로 체크해야 백테스팅과 동일한 결과
            cache_key = f"{symbol}_data"
            # if cache_key in self.data_cache:
            #     last_update = self.last_data_update.get(cache_key, datetime.min)
            #     if datetime.now() - last_update < timedelta(minutes=1):
            #         # 캐시된 데이터 반환
            #         df_4h, df_15m = self.data_cache[cache_key]
            #         # 4시간봉 데이터를 인스턴스 변수에 저장 (신호 체크에서 사용)
            #         self.df_4h_cache = df_4h
            #         return df_4h, df_15m
            
            # 4시간봉 데이터 (추세 확인용)
            logger.debug(f"{symbol} 4시간봉 데이터 요청...")
            df_4h = await self.binance_api.get_klines(symbol, '4h', limit=200)
            
            # 15분봉 데이터 (진입 신호용) - 2주로 확장
            logger.debug(f"{symbol} 15분봉 데이터 요청...")
            # config에서 데이터 수집 설정 읽기
            data_config = self.config.get('data_collection', {})
            klines_15m_limit = data_config.get('klines_15m_limit', 1344)  # 기본값: 2주 (14일 * 24시간 * 4)
            df_15m = await self.binance_api.get_klines(symbol, '15m', limit=klines_15m_limit)
            
            if df_4h.empty or df_15m.empty:
                logger.error(f"데이터 수집 실패: {symbol} - 4H: {len(df_4h)} rows, 15M: {len(df_15m)} rows")
                return None, None
            
            logger.debug(f"{symbol} 데이터 수집 성공 - 4H: {len(df_4h)} rows, 15M: {len(df_15m)} rows")
            
            # 추세 모드에 따른 지표 계산
            if self.trend_mode == 'donchian':
                # Donchian Channel 기반 추세
                df_4h = self.calculate_donchian_trend(df_4h)
            else:
                # 기존 MA 기반 추세 (레거시 호환)
                df_4h['ma50'] = ta.sma(df_4h['close'], 50)
                df_4h['ma200'] = ta.sma(df_4h['close'], 200)
                df_4h['trend'] = np.where(df_4h['ma50'] > df_4h['ma200'], 1, -1)
            
            # 15분봉 지표 계산
            df_15m = self.calculate_indicators(df_15m)
            
            # Donchian 지표 추가
            if self.trend_mode == 'donchian':
                df_15m = self.add_donchian_indicators(df_15m)
            
            # 스윙 하이/로우 계산 추가 (백테스팅과 동일)
            swing_period = self.swing_period
            df_15m['swing_high'] = df_15m['high'].rolling(window=swing_period, center=True).max()
            df_15m['swing_low'] = df_15m['low'].rolling(window=swing_period, center=True).min()
            
            # NaN 처리: center=True로 인한 양 끝 NaN을 forward/backward fill
            df_15m['swing_high'] = df_15m['swing_high'].ffill().bfill()
            df_15m['swing_low'] = df_15m['swing_low'].ffill().bfill()
            
            # 유효한 데이터 체크 (center=True로 인해 양쪽 끝에 NaN이 있을 수 있음)
            valid_data_start = max(50, swing_period, 14)  # ADX가 14기간 필요
            logger.debug(f"{symbol} 유효한 데이터 시작 인덱스: {valid_data_start}")
            
            # 마지막 몇 개 데이터 확인
            last_rows = df_15m.iloc[-5:]
            logger.debug(f"{symbol} 마지막 5개 데이터 상태:")
            for idx, row in last_rows.iterrows():
                logger.debug(f"  {idx}: RSI={row.get('rsi', 'N/A')}, ADX={row.get('adx', 'N/A')}, "
                            f"Momentum={row.get('momentum', 'N/A')}, "
                            f"Swing High={row.get('swing_high', 'N/A')}, "
                            f"Swing Low={row.get('swing_low', 'N/A')}")
            
            # 캐시 저장
            self.data_cache[cache_key] = (df_4h, df_15m)
            self.last_data_update[cache_key] = datetime.now()
            
            # 4시간봉 데이터를 인스턴스 변수에 저장 (신호 체크에서 사용)
            self.df_4h_cache = df_4h
            
            return df_4h, df_15m
            
        except Exception as e:
            logger.error(f"데이터 준비 실패 ({symbol}): {e}")
            return None, None
    
    def calculate_donchian_trend(self, df: pd.DataFrame) -> pd.DataFrame:
        """Donchian Channel 기반 추세 계산"""
        try:
            # Donchian Channel 계산
            df['dc_upper'] = df['high'].rolling(window=self.dc_period).max()
            df['dc_lower'] = df['low'].rolling(window=self.dc_period).min()
            df['dc_middle'] = (df['dc_upper'] + df['dc_lower']) / 2
            
            # 가격 위치 계산
            df['dc_width'] = df['dc_upper'] - df['dc_lower']
            df['price_position'] = np.where(
                df['dc_width'] > 0,
                (df['close'] - df['dc_lower']) / df['dc_width'],
                0.5  # 채널폭이 0인 경우 중립
            )
            
            # 추세 판단: 가격이 중간선 위/아래
            df['trend'] = np.where(df['close'] > df['dc_middle'], 1, -1)
            
            # 채널폭 비율 (변동성 지표)
            df['channel_width_pct'] = df['dc_width'] / df['close']
            
            # 디버깅 정보
            latest = df.iloc[-1]
            logger.debug(f"DC 추세 - Upper: {latest['dc_upper']:.2f}, "
                        f"Middle: {latest['dc_middle']:.2f}, "
                        f"Lower: {latest['dc_lower']:.2f}, "
                        f"Position: {latest['price_position']:.3f}")
            
            return df
            
        except Exception as e:
            logger.error(f"Donchian 추세 계산 실패: {e}")
            # 실패 시 기본값
            df['trend'] = 0
            return df
    
    def add_donchian_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """15분봉에 Donchian 지표 추가"""
        try:
            # 15분봉용 Donchian Channel
            df['dc_upper'] = df['high'].rolling(window=self.dc_period).max()
            df['dc_lower'] = df['low'].rolling(window=self.dc_period).min()
            df['dc_middle'] = (df['dc_upper'] + df['dc_lower']) / 2
            
            # 가격 위치 및 채널폭
            df['dc_width'] = df['dc_upper'] - df['dc_lower']
            df['price_position'] = np.where(
                df['dc_width'] > 0,
                (df['close'] - df['dc_lower']) / df['dc_width'],
                0.5
            )
            df['channel_width_pct'] = df['dc_width'] / df['close']
            
            return df
            
        except Exception as e:
            logger.error(f"Donchian 지표 추가 실패: {e}")
            return df
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """기술 지표 계산 (기존 코드 유지 + 모멘텀 수정)"""
        try:
            logger.debug(f"지표 계산 시작 - DataFrame 크기: {len(df)}")
            
            # ADX/DI
            adx_data = ta.adx(df['high'], df['low'], df['close'], length=14)
            if adx_data is not None:
                df['adx'] = adx_data['ADX_14']
                df['plus_di'] = adx_data['DMP_14']
                df['minus_di'] = adx_data['DMN_14']
                logger.debug(f"ADX 계산 완료 - 마지막 값: {df['adx'].iloc[-1]:.1f}")
            else:
                logger.warning("ADX 계산 실패")
            
            # RSI
            df['rsi'] = ta.rsi(df['close'], length=14)
            
            # EMA
            df['ema12'] = ta.ema(df['close'], 12)
            df['ema_distance'] = abs(df['close'] - df['ema12']) / df['close']
            
            # ATR
            df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
            
            # 볼륨
            df['volume_ma'] = df['volume'].rolling(window=20).mean()
            df['volume_ratio'] = df['volume'] / df['volume_ma']
            
            # 모멘텀 (백테스팅과 동일하게 수정)
            lookback = self.momentum_lookback
            df['momentum'] = ((df['close'] - df['close'].shift(lookback)) / 
                              df['close'].shift(lookback) * 100).abs()
            
            # 지표 계산 결과 로그
            latest = df.iloc[-1]
            logger.debug(f"지표 계산 완료 - RSI: {latest.get('rsi', 'N/A')}, "
                        f"Momentum: {latest.get('momentum', 'N/A')}, "
                        f"Volume Ratio: {latest.get('volume_ratio', 'N/A')}")
            
            # NaN 값 체크
            nan_columns = df.columns[df.iloc[-1].isna()].tolist()
            if nan_columns:
                logger.warning(f"NaN 값이 있는 지표: {nan_columns}")
            
            return df
            
        except Exception as e:
            logger.error(f"지표 계산 실패: {e}")
            return df
    
    async def check_entry_signal(self, symbol: str, df_4h: pd.DataFrame, 
                                df_15m: pd.DataFrame, current_index: int) -> Tuple[bool, Optional[str]]:
        """Donchian Channel 기반 진입 신호 체크"""
        try:
            if current_index < 50:  # 충분한 데이터 필요
                logger.debug(f"{symbol} 데이터 부족: 인덱스 {current_index} < 50")
                return False, None
            
            current = df_15m.iloc[current_index]
            
            # 디버깅을 위한 현재 지표 값 출력
            logger.debug(f"{symbol} 현재 지표 - ADX: {current.get('adx', 'N/A')}, "
                        f"RSI: {current.get('rsi', 'N/A')}, "
                        f"Momentum: {current.get('momentum', 'N/A')}, "
                        f"Volume Ratio: {current.get('volume_ratio', 'N/A')}")
            
            # ADX 필터 (추세 강도)
            if pd.isna(current['adx']):
                logger.debug(f"{symbol} ADX 값이 NaN입니다")
                return False, None
            elif current['adx'] < self.adx_min:
                logger.debug(f"{symbol} ADX 부족: {current['adx']:.1f} < {self.adx_min}")
                return False, None
            
            # 필요한 값들 체크
            required_values = ['momentum', 'rsi', 'ema_distance']
            if self.trend_mode == 'donchian':
                required_values.extend(['price_position', 'channel_width_pct'])
            else:
                required_values.extend(['swing_high', 'swing_low'])
            
            nan_values = [val for val in required_values if pd.isna(current[val])]
            if nan_values:
                logger.debug(f"{symbol} NaN 값 발견: {nan_values}")
                return False, None
            
            # 4시간봉 추세 확인
            current_time = df_15m.index[current_index]
            aligned_time = current_time.floor('4H')
            
            if aligned_time not in df_4h.index:
                logger.debug(f"{symbol} 4H 정렬 실패: {aligned_time} not in df_4h.index")
                return False, None
            
            trend_4h = df_4h.loc[aligned_time, 'trend']
            
            # Donchian Channel 기반 신호 체크
            if self.trend_mode == 'donchian':
                # 4시간봉 데이터 저장 (신호 체크에서 사용)
                self.df_4h_cache = df_4h
                return await self._check_donchian_signal(current, trend_4h, symbol, aligned_time)
            else:
                # 기존 MA 기반 로직 (레거시)
                return await self._check_ma_signal(current, trend_4h, symbol)
            
        except Exception as e:
            logger.error(f"진입 신호 체크 실패: {e}")
            return False, None
    
    async def _check_donchian_signal(self, current, trend_4h: int, symbol: str, aligned_time) -> Tuple[bool, Optional[str]]:
        """Donchian Channel 기반 신호 체크 (백테스팅과 동일하게 수정)"""
        # 쿨다운 체크 추가 (청산 후 즉시 재진입 방지)
        if symbol in self.last_signal_time:
            time_since_last = (datetime.now() - self.last_signal_time[symbol]).total_seconds() / 3600
            if time_since_last < self.min_signal_interval:
                logger.debug(f"{symbol} 쿨다운 중: {time_since_last:.1f}/{self.min_signal_interval}시간")
                return False, None
        
        conditions_met = []
        direction = None
        
        # 가격 위치 및 채널폭 가져오기
        price_pos = current['price_position']
        rsi = current['rsi']
        
        # 4시간봉 채널폭 확인 (중요!)
        dc_width_4h = None
        if self.df_4h_cache is not None and aligned_time in self.df_4h_cache.index:
            dc_width_4h = self.df_4h_cache.loc[aligned_time, 'channel_width_pct']
        
        # 채널폭이 없으면 15분봉 값 사용
        if dc_width_4h is None:
            dc_width_4h = current['channel_width_pct']
        
        # 디버깅을 위한 현재 상태 로그
        logger.debug(f"{symbol} 진입 체크 - 4H추세: {'상승' if trend_4h == 1 else '하락'}, "
                    f"RSI: {rsi:.1f}, 가격위치: {price_pos:.3f}, "
                    f"채널폭(4H): {dc_width_4h:.1%}, "
                    f"모멘텀: {current['momentum']:.2f}%")
        
        # 1. 모멘텀 조건 (백테스팅과 동일)
        if current['momentum'] > self.min_momentum:
            conditions_met.append("momentum")
        else:
            logger.debug(f"   모멘텀 부족: {current['momentum']:.2f}% < {self.min_momentum}%")
        
        # 2. 피보나치 되돌림 (백테스팅 코드에서 추가)
        if 'swing_high' in current and 'swing_low' in current:
            swing_high = current['swing_high']
            swing_low = current['swing_low']
            
            if not pd.isna(swing_high) and not pd.isna(swing_low) and swing_high > swing_low:
                price = current['close']
                
                if trend_4h == 1:  # 상승 추세
                    retracement = (swing_high - price) / (swing_high - swing_low)
                    if self.fib_min <= retracement <= self.fib_max:
                        conditions_met.append("fibonacci")
                else:  # 하락 추세
                    retracement = (price - swing_low) / (swing_high - swing_low)
                    if self.fib_min <= retracement <= self.fib_max:
                        conditions_met.append("fibonacci")
        
        # 3. RSI 조건 (개선됨 - 백테스팅과 동일)
        # Donchian 기반 유연한 진입
        if trend_4h == 1:  # 상승 추세
            if price_pos < self.price_position_low and rsi <= 40:
                # 채널 하단 + 과매도 = 강한 롱 신호
                conditions_met.append("rsi")
                direction = 'long'
            elif self.price_position_neutral_min <= price_pos <= self.price_position_neutral_max and rsi <= 45:
                # 중립 구간 + RSI 낮음 = 롱 가능
                conditions_met.append("rsi")
                direction = 'long'
        else:  # 하락 추세
            if price_pos > self.price_position_high and rsi >= 60:
                # 채널 상단 + 과매수 = 강한 숏 신호
                conditions_met.append("rsi")
                direction = 'short'
            elif self.price_position_neutral_min <= price_pos <= self.price_position_neutral_max and rsi >= 55:
                # 중립 구간 + RSI 높음 = 숏 가능
                conditions_met.append("rsi")
                direction = 'short'
        
        # 4. 추세 약할 때 양방향 진입 (핵심 개선 - 백테스팅과 동일)
        if dc_width_4h < 0.05:  # 채널 폭이 좁음 = 횡보
            if rsi < self.rsi_oversold:
                conditions_met.append("rsi_extreme")
                direction = 'long'
            elif rsi > self.rsi_overbought:
                conditions_met.append("rsi_extreme")
                direction = 'short'
        
        # 5. EMA 거리
        if current['ema_distance'] <= self.ema_distance_max:
            conditions_met.append("ema_distance")
        else:
            logger.debug(f"   EMA 거리 초과: {current['ema_distance']:.3f} > {self.ema_distance_max}")
        
        # 6. 거래량 스파이크
        if current['volume_ratio'] >= self.volume_spike:
            conditions_met.append("volume")
        else:
            logger.debug(f"   거래량 부족: {current['volume_ratio']:.2f} < {self.volume_spike}")
        
        # 7. 가격 위치 보너스 (백테스팅에 있는 조건)
        if (direction == 'long' and price_pos < self.price_position_low) or \
           (direction == 'short' and price_pos > self.price_position_high):
            conditions_met.append("price_position")
        
        # 신호 판단
        if direction and len(conditions_met) >= self.signal_threshold:
            logger.info(f"📊 Donchian 신호 감지: {symbol} {direction}")
            logger.info(f"   충족 조건 ({len(conditions_met)}/{self.signal_threshold}): {', '.join(conditions_met)}")
            logger.info(f"   추세: {'상승' if trend_4h == 1 else '하락'}, "
                       f"가격위치: {price_pos:.3f}, "
                       f"채널폭(4H): {dc_width_4h:.1%}, "
                       f"RSI: {rsi:.1f}")
            
            # 마지막 신호 시간 업데이트 (진입 전에 미리 업데이트)
            self.last_signal_time[symbol] = datetime.now()
            
            # 디버깅 정보 추가
            logger.debug(f"   모멘텀: {current['momentum']:.2f}%, "
                        f"EMA거리: {current['ema_distance']:.3f}, "
                        f"볼륨비율: {current['volume_ratio']:.2f}")
            
            return True, direction
        
        # 신호가 없어도 조건 상태 로깅
        if len(conditions_met) > 0:
            logger.debug(f"{symbol} 조건 부족 ({len(conditions_met)}/{self.signal_threshold}): {conditions_met}")
            logger.debug(f"   세부정보 - 추세: {'상승' if trend_4h == 1 else '하락'}, "
                        f"가격위치: {price_pos:.3f}, RSI: {rsi:.1f}, "
                        f"채널폭(4H): {dc_width_4h:.1%}")
        else:
            logger.debug(f"{symbol} 충족 조건 없음 - 추세: {'상승' if trend_4h == 1 else '하락'}, "
                        f"가격위치: {price_pos:.3f}, RSI: {rsi:.1f}")
        
        return False, None
    
    async def _check_ma_signal(self, current, trend_4h: int, symbol: str) -> Tuple[bool, Optional[str]]:
        """기존 MA 기반 신호 체크 (레거시 호환)"""
        conditions_met = []
        
        # 1. 모멘텀 조건
        if current['momentum'] > self.min_momentum:
            conditions_met.append("momentum")
        
        # 2. 피보나치 되돌림
        swing_high = current['swing_high']
        swing_low = current['swing_low']
        
        if swing_high > swing_low:  # 유효한 스윙 범위
            price = current['close']
            
            if trend_4h == 1:  # 상승 추세
                retracement = (swing_high - price) / (swing_high - swing_low)
                retracement_ok = self.fib_min <= retracement <= self.fib_max
            else:  # 하락 추세
                retracement = (price - swing_low) / (swing_high - swing_low)
                retracement_ok = self.fib_min <= retracement <= self.fib_max
            
            if retracement_ok:
                conditions_met.append("fibonacci")
        
        # 3. RSI 조건
        rsi = current['rsi']
        if trend_4h == 1 and rsi <= self.rsi_pullback_long:
            conditions_met.append("rsi")
        elif trend_4h == -1 and rsi >= self.rsi_pullback_short:
            conditions_met.append("rsi")
        
        # 4. EMA 거리
        if current['ema_distance'] <= self.ema_distance_max:
            conditions_met.append("ema_distance")
        
        # 5. 거래량 스파이크
        if current['volume_ratio'] >= self.volume_spike:
            conditions_met.append("volume")
        
        # 신호 판단
        if len(conditions_met) >= self.signal_threshold:
            direction = 'long' if trend_4h == 1 else 'short'
            
            logger.info(f"📊 MA 풀백 신호 감지: {symbol} {direction}")
            logger.info(f"   충족 조건 ({len(conditions_met)}/5): {', '.join(conditions_met)}")
            logger.info(f"   추세: {'상승' if trend_4h == 1 else '하락'}, RSI: {rsi:.1f}, 모멘텀: {current['momentum']:.2f}%")
            
            return True, direction
        
        return False, None
    
    async def check_exit_signal(self, position, df_15m: pd.DataFrame, 
                               current_index: int) -> Tuple[bool, str]:
        """청산 신호 체크 (손절/익절)"""
        try:
            current = df_15m.iloc[current_index]
            current_price = current['close']
            
            # 손익률 계산
            if position.side == 'long':
                pnl_pct = (current_price - position.entry_price) / position.entry_price * 100
            else:
                pnl_pct = (position.entry_price - current_price) / position.entry_price * 100
            
            # ATR 기반 동적 손절/익절
            current_atr = current['atr']
            
            if position.side.upper() == 'LONG':
                stop_loss = position.entry_price - (current_atr * self.stop_loss_atr)
                take_profit = position.entry_price + (current_atr * self.take_profit_atr)
                
                if current_price <= stop_loss:
                    return True, f"손절 (SL: {stop_loss:.2f})"
                elif current_price >= take_profit:
                    return True, f"익절 (TP: {take_profit:.2f})"
            else:
                stop_loss = position.entry_price + (current_atr * self.stop_loss_atr)
                take_profit = position.entry_price - (current_atr * self.take_profit_atr)
                
                if current_price >= stop_loss:
                    return True, f"손절 (SL: {stop_loss:.2f})"
                elif current_price <= take_profit:
                    return True, f"익절 (TP: {take_profit:.2f})"
            
            # 추가 청산 조건: Donchian 기반 추세 전환
            if self.trend_mode == 'donchian' and 'dc_middle' in current:
                # 중간선 돌파시 청산 (옵션)
                if self.config.get('exit_on_middle_cross', False):
                    if position.side == 'long' and current_price < current['dc_middle']:
                        return True, "Donchian 중간선 하향 돌파"
                    elif position.side == 'short' and current_price > current['dc_middle']:
                        return True, "Donchian 중간선 상향 돌파"
            
            # 시간 기반 청산
            if 'max_holding_hours' in self.config:
                holding_hours = (datetime.now() - position.created_at).total_seconds() / 3600
                if holding_hours > self.config['max_holding_hours']:
                    return True, f"최대 보유 시간 초과 ({holding_hours:.1f}시간)"
            
            return False, ""
            
        except Exception as e:
            logger.error(f"청산 신호 체크 실패: {e}")
            return False, ""
    
    async def _check_new_entry(self, symbol: str):
        """신규 진입 체크 - 캔들 완성 확인 강화 + MDD 제한 + 시장 레진"""
        try:
            # 메이저 코인만 거래
            if symbol not in self.major_coins:
                return
            
            # MDD 제한 체크
            if self.mdd_manager:
                current_balance = await self.binance_api.get_account_balance()
                mdd_restrictions = await self.mdd_manager.check_mdd_restrictions(current_balance)
                
                if not mdd_restrictions['allow_new_trades']:
                    self.mdd_manager.skip_trade_by_mdd()
                    logger.warning(f"MDD 제한으로 신규 거래 차단: {mdd_restrictions['reason']}")
                    return
            
            # 스마트 재개 관리자 체크
            if self.smart_resume_manager and self.smart_resume_manager.is_symbol_paused(symbol):
                logger.debug(f"{symbol}은 일시정지 상태입니다")
                return
            
            # 데이터 준비
            logger.debug(f"{symbol} 데이터 수집 시작...")
            df_4h, df_15m = await self.fetch_and_prepare_data(symbol)
            
            if df_4h is None or df_15m is None:
                logger.warning(f"{symbol} 데이터 수집 실패 - df_4h: {df_4h is not None}, df_15m: {df_15m is not None}")
                return
            
            # 백테스팅과 동일하게 항상 완성된 캔들만 사용
            # -1: 현재 진행 중인 캔들 (사용하지 않음)
            # -2: 마지막 완성된 캔들 (사용)
            current_index = len(df_15m) - 2
            
            # 데이터 충분성 체크
            if current_index < 50:  # check_entry_signal에서 요구하는 최소 인덱스
                logger.warning(f"{symbol} 데이터 부족: 인덱스 {current_index}")
                return
            
            # 서버 시간 가져오기
            server_time = await self._get_binance_server_time()
            candle_time = df_15m.index[current_index]
            
            # 캔들 완성 확인 (이중 체크)
            candle_end_time = candle_time + timedelta(minutes=15)
            time_since_candle_end = (server_time - candle_end_time).total_seconds()
            
            if time_since_candle_end < 0:
                logger.error(f"⚠️ 미완성 캔들 사용 시도! {symbol}")
                logger.error(f"   캔들: {candle_time}, 종료: {candle_end_time}, 서버: {server_time}")
                return
            
            logger.debug(f"{symbol} 체크 - 캔들: {candle_time.strftime('%H:%M')}, "
                        f"완성 후 {time_since_candle_end:.0f}초 경과")
            
            # 진입 신호 체크
            logger.debug(f"{symbol} 진입 신호 체크 시작 (인덱스: {current_index})")
            signal, direction = await self.check_entry_signal(
                symbol, df_4h, df_15m, current_index
            )
            
            if not signal:
                logger.debug(f"{symbol} 진입 신호 없음")
                return
            
            logger.info(f"🎯 신호 확인! 즉시 진입 준비: {symbol} {direction}")
            
            # 손절/익절 계산 (완성된 캔들 기준)
            current_price = df_15m.iloc[current_index]['close']
            current_atr = df_15m.iloc[current_index]['atr']
            
            if direction == 'long':
                stop_loss = current_price - (current_atr * self.stop_loss_atr)
                take_profit = current_price + (current_atr * self.take_profit_atr)
            else:
                stop_loss = current_price + (current_atr * self.stop_loss_atr)
                take_profit = current_price - (current_atr * self.take_profit_atr)
            
            # 실제 시장가로 진입 (현재가는 다를 수 있음)
            logger.info(f"   신호 가격: ${current_price:.2f} (캔들 종가)")
            logger.info(f"   손절: ${stop_loss:.2f}, 익절: ${take_profit:.2f}")
            
            # 비동기로 진입 실행
            success = await self.execute_entry(symbol, direction, stop_loss, take_profit)
            
            if success:
                # 성공 알림
                if self.notification_manager:
                    # 실제 진입가는 execute_entry에서 처리되므로
                    # 여기서는 신호 정보만 전송
                    asyncio.create_task(self._send_entry_notification(
                        symbol, direction, current_price, stop_loss, take_profit
                    ))
                
                logger.info(f"⚡ {symbol} 진입 주문 완료")
            
        except Exception as e:
            logger.error(f"신규 진입 체크 실패 ({symbol}): {e}")
    
    async def _check_market_regime(self):
        """시장 레짐 체크 및 전략 파라미터 조정"""
        try:
            # 주요 심볼 중 첫 번째로 전체 시장 상태 판단
            main_symbol = self.major_coins[0] if self.major_coins else 'BTCUSDT'
            
            # 4시간봉 데이터 가져오기
            df_4h = await self.binance_api.get_klines(main_symbol, '4h', limit=100)
            if df_4h is None or df_4h.empty:
                logger.warning("시장 레짐 분석을 위한 데이터 부족")
                return
            
            # 지표 계산
            df_4h = self.calculate_donchian_trend(df_4h)
            df_4h = self.calculate_indicators(df_4h)
            
            # 시장 레짐 식별
            regime = self.regime_analyzer.identify_market_regime(df_4h)
            self.current_regime = regime
            
            # 레짐 통계 가져오기
            stats = self.regime_analyzer.get_regime_statistics()
            scores = {'confidence': 0.8}  # 기본값 설정
            
            # 레짐별 파라미터 조정
            # 현재 전략 파라미터를 기반으로 조정
            base_params = {
                'position_size': self.config.get('position_size', 24),
                'signal_threshold': self.config.get('signal_threshold', 3),
                'stop_loss_atr': self.config.get('stop_loss_atr', 1.5),
                'take_profit_atr': self.config.get('take_profit_atr', 3.0)
            }
            adjusted_params = self.regime_analyzer.adjust_parameters_for_regime(base_params, regime)
            
            # 조정을 위한 간단한 사전 생성
            adjustments = {
                'position_size_multiplier': adjusted_params.get('position_size', base_params['position_size']) / base_params['position_size'],
                'signal_threshold_adjustment': adjusted_params.get('signal_threshold', base_params['signal_threshold']) - base_params['signal_threshold'],
                'stop_loss_multiplier': adjusted_params.get('stop_loss_atr', base_params['stop_loss_atr']) / base_params['stop_loss_atr'],
                'take_profit_multiplier': adjusted_params.get('take_profit_atr', base_params['take_profit_atr']) / base_params['take_profit_atr']
            }
            
            # 파라미터 적용
            if adjustments:
                # 포지션 크기 조정
                base_position_size = self.config.get('position_size', 24)
                self.position_size = base_position_size * adjustments.get('position_size_multiplier', 1.0)
                
                # 신호 임계값 조정
                base_threshold = self.config.get('signal_threshold', 3)
                adjustment = adjustments.get('signal_threshold_adjustment', 0)
                self.signal_threshold = max(2, min(5, base_threshold + adjustment))
                
                # 손절/익절 조정
                base_sl = self.config.get('stop_loss_atr', 1.5)
                base_tp = self.config.get('take_profit_atr', 3.0)
                self.stop_loss_atr = base_sl * adjustments.get('stop_loss_multiplier', 1.0)
                self.take_profit_atr = base_tp * adjustments.get('take_profit_multiplier', 1.0)
                
                logger.info(f"시장 레짐 변경: {regime.value} (신뢰도: {scores['confidence']:.1%})")
                logger.info(f"  조정된 파라미터 - 포지션크기: {self.position_size:.1f}%, "
                           f"신호임계값: {self.signal_threshold}, "
                           f"SL: {self.stop_loss_atr:.1f}xATR, TP: {self.take_profit_atr:.1f}xATR")
                
                # 알림 전송
                if self.notification_manager and scores['confidence'] > 0.7:
                    await self.notification_manager.send_alert(
                        event_type='MARKET_REGIME_CHANGE',
                        title='🌍 시장 상태 변화',
                        message=(
                            f"<b>시장 레짐:</b> {regime.value}\n"
                            f"<b>신뢰도:</b> {scores['confidence']:.1%}\n"
                            f"<b>추세 강도:</b> {scores.get('trend', 0):.0f}/100\n"
                            f"<b>변동성:</b> {scores.get('volatility', 0):.0f}/100\n\n"
                            f"전략 파라미터가 자동 조정되었습니다."
                        )
                    )
        
        except Exception as e:
            logger.error(f"시장 레짐 체크 실패: {e}")
    
    async def calculate_dynamic_position_size(self, symbol: str, base_size: float) -> float:
        """
        동적 포지션 사이징 계산
        - Kelly Criterion
        - MDD 조정
        - 시장 레짐 조정
        - 리스크 패리티
        """
        try:
            # 1. 기본 크기
            position_size = base_size
            
            # 2. Kelly Criterion 적용
            kelly_params = self.performance_tracker.get_kelly_parameters(self.strategy_name)
            kelly_fraction = kelly_params.get('kelly_fraction', 0)
            if kelly_fraction > 0:
                # Kelly는 전체 자본 대비 비율이므로 포지션 크기에 반영
                kelly_multiplier = kelly_fraction / (base_size / 100)
                kelly_multiplier = max(0.5, min(1.5, kelly_multiplier))  # 50% ~ 150%
                position_size *= kelly_multiplier
                logger.debug(f"{symbol} Kelly 조정: {kelly_multiplier:.2f}x")
            
            # 3. MDD 조정
            if self.mdd_manager:
                current_balance = await self.binance_api.get_account_balance()
                mdd_restrictions = await self.mdd_manager.check_mdd_restrictions(current_balance)
                mdd_multiplier = mdd_restrictions.get('position_size_multiplier', 1.0)
                position_size *= mdd_multiplier
                logger.debug(f"{symbol} MDD 조정: {mdd_multiplier:.2f}x")
            
            # 4. 시장 레짐 조정 (이미 적용됨)
            # self.position_size는 이미 레짐에 따라 조정된 값
            
            # 5. 리스크 패리티 (선택적)
            if hasattr(self, 'risk_parity_allocator') and self.config.get('use_risk_parity', False):
                rp_multiplier = self.risk_parity_allocator.get_position_size_multiplier(
                    self.strategy_name, position_size, current_balance
                )
                position_size *= rp_multiplier
                logger.debug(f"{symbol} 리스크 패리티 조정: {rp_multiplier:.2f}x")
            
            # 6. 최종 제한
            min_size = self.config.get('min_position_size', 10)
            max_size = self.config.get('max_position_size', 50)
            position_size = max(min_size, min(max_size, position_size))
            
            logger.info(f"{symbol} 최종 포지션 크기: {position_size:.1f}% (기본: {base_size}%)")
            
            return position_size
            
        except Exception as e:
            logger.error(f"동적 포지션 사이징 실패: {e}")
            return base_size
    
    async def execute_entry(self, symbol: str, direction: str, stop_loss: float, take_profit: float):
        """진입 실행 - 동적 포지션 사이징 적용"""
        try:
            # 현재 잔고 확인
            balance = await self.binance_api.get_account_balance()
            if balance <= 0:
                logger.error("잔고 부족")
                return False
            
            # 동적 포지션 크기 계산
            dynamic_size = await self.calculate_dynamic_position_size(symbol, self.position_size)
            
            # 포지션 크기로 수량 계산
            position_value = balance * (dynamic_size / 100)
            current_price = await self.binance_api.get_current_price(symbol)
            quantity = position_value / current_price
            
            # 수량 정밀도 적용
            quantity = await self.binance_api.round_quantity(symbol, quantity)
            
            # 최소 주문 금액 체크
            min_notional = 10.0  # USDT
            if quantity * current_price < min_notional:
                logger.warning(f"주문 금액이 최소값 미만: ${quantity * current_price:.2f} < ${min_notional}")
                return False
            
            # 레버리지 설정
            await self.binance_api.set_leverage(symbol, self.leverage)
            
            # 슬리피지 보호를 위한 예상 체결가 체크
            expected_slippage = self.config.get('max_slippage_pct', 0.5)  # 최대 0.5% 슬리피지
            if direction == 'long':
                max_price = current_price * (1 + expected_slippage / 100)
            else:
                max_price = current_price * (1 - expected_slippage / 100)
            
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
            
            # 체결가 확인
            entry_price = 0.0
            if 'avgPrice' in order and order['avgPrice']:
                entry_price = float(order['avgPrice'])
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
            
            if entry_price <= 0:
                entry_price = current_price
            
            # 슬리피지 체크
            if direction == 'long':
                slippage_pct = ((entry_price - current_price) / current_price) * 100
                if slippage_pct > expected_slippage:
                    logger.warning(f"과도한 슬리피지 발생: {slippage_pct:.2f}% > {expected_slippage}%")
            else:
                slippage_pct = ((current_price - entry_price) / current_price) * 100
                if slippage_pct > expected_slippage:
                    logger.warning(f"과도한 슬리피지 발생: {slippage_pct:.2f}% > {expected_slippage}%")
            
            # 포지션 등록
            await asyncio.sleep(0.5)  # API 지연 대기
            
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
                # 성과 추적에 시장 레짐 포함
                if hasattr(position, 'market_regime'):
                    position.market_regime = self.current_regime.value
                
                logger.info(f"✅ {symbol} 포지션 등록 성공 (크기: {dynamic_size:.1f}%)")
                return True
            else:
                logger.error(f"❌ {symbol} 포지션 등록 실패")
                return False
                
        except Exception as e:
            logger.error(f"진입 실행 실패: {e}")
            return False
    
    async def execute_exit(self, position, reason: str) -> bool:
        """청산 실행 - 성과 기록 포함"""
        try:
            # 현재가 가져오기
            current_price = await self.binance_api.get_current_price(position.symbol)
            if not current_price:
                logger.error(f"현재가 조회 실패: {position.symbol}")
                return False
            
            # 청산 주문
            side = 'SELL' if position.side.upper() == 'LONG' else 'BUY'
            
            order = await self.binance_api.place_order(
                symbol=position.symbol,
                side=side,
                quantity=position.size,
                order_type='MARKET'
            )
            
            if not order:
                logger.error(f"청산 주문 실패: {position.symbol}")
                return False
            
            # 청산가 확인
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
            
            if exit_price <= 0:
                exit_price = current_price
            
            # PnL 계산
            if position.side.upper() == 'LONG':
                pnl = (exit_price - position.entry_price) * position.size
                pnl_pct = ((exit_price - position.entry_price) / position.entry_price) * 100
            else:
                pnl = (position.entry_price - exit_price) * position.size  
                pnl_pct = ((position.entry_price - exit_price) / position.entry_price) * 100
            
            pnl_pct *= position.leverage
            
            # 성과 기록
            if self.performance_tracker and not position.is_manual:
                try:
                    await self.performance_tracker.record_trade(
                        strategy_name=self.strategy_name,
                        symbol=position.symbol,
                        side=position.side,
                        entry_price=position.entry_price,
                        exit_price=exit_price,
                        size=position.size,
                        leverage=self.leverage,
                        entry_time=position.created_at,
                        exit_time=datetime.now(),
                        commission=0.0,
                        reason=reason
                    )
                    logger.debug(f"거래 성과 기록 완료: {position.symbol}")
                except Exception as e:
                    logger.error(f"성과 기록 실패: {e}")
            
            # MDD Manager에 결과 알림
            if self.mdd_manager:
                trade_won = pnl_pct > 0
                self.mdd_manager.update_recovery_status(trade_won)
            
            # 포지션 제거
            await self.position_manager.remove_position(position.symbol, reason, exit_price, self.strategy_name)
            
            # 쿨다운 업데이트
            self.last_signal_time[position.symbol] = datetime.now()
            
            logger.info(f"🔚 포지션 청산: {position.symbol} @ {exit_price} ({pnl_pct:+.2f}%) - {reason}")
            
            return True
            
        except Exception as e:
            logger.error(f"포지션 청산 실패: {e}")
            return False
    
    async def _send_entry_notification(self, symbol: str, direction: str, 
                                      entry_price: float, stop_loss: float, take_profit: float):
        """진입 알림 전송 (비동기)"""
        try:
            strategy_mode = "Donchian" if self.trend_mode == 'donchian' else "MA"
            
            # 예상 손익 계산
            if direction.lower() == 'long':
                risk = ((entry_price - stop_loss) / entry_price) * 100 * self.leverage
                reward = ((take_profit - entry_price) / entry_price) * 100 * self.leverage
            else:
                risk = ((stop_loss - entry_price) / entry_price) * 100 * self.leverage
                reward = ((entry_price - take_profit) / entry_price) * 100 * self.leverage
            
            rr_ratio = reward / risk if risk > 0 else 0
            
            message = (
                f"<b>TFPE {strategy_mode} 전략 진입</b>\n\n"
                f"<b>심볼:</b> {symbol}\n"
                f"<b>방향:</b> {direction.upper()}\n"
                f"<b>진입가:</b> ${entry_price:,.2f}\n"
                f"<b>손절가:</b> ${stop_loss:,.2f} (-{risk:.1f}%)\n"
                f"<b>목표가:</b> ${take_profit:,.2f} (+{reward:.1f}%)\n"
                f"<b>R:R:</b> 1:{rr_ratio:.1f}\n"
                f"<b>레버리지:</b> {self.leverage}x\n"
                f"<b>시간:</b> {datetime.now().strftime('%H:%M:%S')}"
            )
            
            await self.notification_manager.send_alert(
                event_type='POSITION_OPENED',
                title='📈 포지션 진입',
                message=message
            )
        except Exception as e:
            logger.error(f"알림 전송 실패: {e}")
    
    async def _manage_position(self, position):
        """포지션 관리 - 손절/익절 실행 추가"""
        try:
            # 수동 포지션은 관리하지 않음
            if position.is_manual:
                return
            
            # 전략이 생성한 포지션만 관리
            if position.strategy_name != self.strategy_name:
                return
            
            symbol = position.symbol
            
            # 데이터 준비
            df_4h, df_15m = await self.fetch_and_prepare_data(symbol)
            
            if df_4h is None or df_15m is None:
                return
            
            # 현재 인덱스 - 항상 마지막 완성된 캔들 사용
            current_index = len(df_15m) - 2
            
            # 안전성 체크 추가
            if current_index < 0:
                logger.warning(f"포지션 관리 - 데이터 부족: {symbol}")
                return
            
            # 서버 시간 확인 (옵션)
            server_time = await self._get_binance_server_time()
            candle_time = df_15m.index[current_index]
            logger.debug(f"포지션 관리 - {symbol} 캔들: {candle_time.strftime('%H:%M')}")
            
            # 청산 신호 체크
            should_exit, reason = await self.check_exit_signal(
                position, df_15m, current_index
            )
            
            if should_exit:
                logger.info(f"🚨 청산 신호 감지: {symbol} - {reason}")
                
                # 실제 청산 실행
                success = await self.execute_exit(position, reason)
                
                if success:
                    logger.info(f"✅ {symbol} 청산 완료: {reason}")
                    
                    # 청산 알림은 position_manager.remove_position에서 자동으로 전송됨
                    
                    # 통계 업데이트 (선택사항)
                    if hasattr(self, 'stats'):
                        self.stats['positions_closed'] = self.stats.get('positions_closed', 0) + 1
                else:
                    logger.error(f"❌ {symbol} 청산 실행 실패")
                    
                    # 청산 실패 알림
                    if self.notification_manager:
                        await self.notification_manager.send_alert(
                            event_type='SYSTEM_ERROR',
                            title=f'⚠️ {symbol} 청산 실패',
                            message=(
                                f"청산 시도가 실패했습니다.\n"
                                f"사유: {reason}\n"
                                f"수동으로 확인이 필요합니다."
                            ),
                            data={
                                'symbol': symbol,
                                'position_id': position.position_id,
                                'reason': reason
                            }
                        )
            else:
                # 청산 신호가 없어도 현재 상태 로깅 (디버깅용)
                current_price = df_15m.iloc[current_index]['close']
                
                # 손익률 계산
                if position.side.upper() == 'LONG':
                    pnl_pct = (current_price - position.entry_price) / position.entry_price * 100
                else:
                    pnl_pct = (position.entry_price - current_price) / position.entry_price * 100
                
                pnl_pct *= self.leverage
                
                # ATR 기반 손절/익절 레벨 계산
                current_atr = df_15m.iloc[current_index]['atr']
                
                if position.side == 'long':
                    stop_loss = position.entry_price - (current_atr * self.stop_loss_atr)
                    take_profit = position.entry_price + (current_atr * self.take_profit_atr)
                    sl_distance = ((current_price - stop_loss) / current_price) * 100
                    tp_distance = ((take_profit - current_price) / current_price) * 100
                else:
                    stop_loss = position.entry_price + (current_atr * self.stop_loss_atr)
                    take_profit = position.entry_price - (current_atr * self.take_profit_atr)
                    sl_distance = ((stop_loss - current_price) / current_price) * 100
                    tp_distance = ((current_price - take_profit) / current_price) * 100
                
                # 10분마다 한 번만 로깅 (너무 많은 로그 방지)
                log_key = f"position_log_{symbol}"
                if not hasattr(self, '_last_position_log'):
                    self._last_position_log = {}
                
                if (log_key not in self._last_position_log or 
                    (datetime.now() - self._last_position_log[log_key]).seconds > 600):
                    
                    logger.info(f"📊 {symbol} 포지션 현황:")
                    logger.info(f"   방향: {position.side}, 진입가: ${position.entry_price:.2f}")
                    logger.info(f"   현재가: ${current_price:.2f}, 손익: {pnl_pct:+.2f}%")
                    logger.info(f"   손절까지: {sl_distance:.1f}%, 익절까지: {tp_distance:.1f}%")
                    logger.info(f"   ATR: {current_atr:.2f}, SL: ${stop_loss:.2f}, TP: ${take_profit:.2f}")
                    
                    self._last_position_log[log_key] = datetime.now()
            
        except Exception as e:
            logger.error(f"포지션 관리 실패 ({position.symbol}): {e}")
            
            # 심각한 오류 시 알림
            if self.notification_manager:
                await self.notification_manager.send_alert(
                    event_type='SYSTEM_ERROR',
                    title=f'❌ 포지션 관리 오류',
                    message=(
                        f"심볼: {position.symbol}\n"
                        f"오류: {str(e)}\n"
                        f"수동 확인이 필요합니다."
                    ),
                    data={'symbol': position.symbol, 'error': str(e)}
                )
    
    async def on_realtime_signal(self, symbol: str, signal_type: str, indicators: Dict):
        """실시간 신호 수신시 호출 (WebSocket 이벤트)"""
        logger.info(f"⚡ 실시간 신호: {symbol} - {signal_type}")
        
        # 즉시 전체 체크 실행
        if await self.can_enter_position(symbol):
            await self._check_new_entry(symbol)
    
    async def stop(self):
        """전략 중지"""
        self.is_running = False
        
        # 실시간 모니터 중지
        if self.price_monitor:
            await self.price_monitor.stop()
        
        logger.info(f"{self.strategy_name} 전략 중지")
    
    def get_strategy_info(self) -> Dict:
        """전략 정보 반환"""
        mode_info = "Donchian Channel" if self.trend_mode == 'donchian' else "Moving Average"
        
        return {
            'name': f'TFPE ({mode_info} Strategy)',
            'version': '2.0',
            'parameters': {
                'mode': self.trend_mode,
                'leverage': self.leverage,
                'position_size': f"{self.position_size}%",
                'signal_threshold': f"{self.signal_threshold}/5",
                'stop_loss': f"ATR × {self.stop_loss_atr}",
                'take_profit': f"ATR × {self.take_profit_atr}",
                'min_momentum': f"{self.min_momentum}%",
                'dc_period': self.dc_period if self.trend_mode == 'donchian' else 'N/A',
                'price_position': f"Long≤{self.price_position_low}, Short≥{self.price_position_high}" if self.trend_mode == 'donchian' else 'N/A',
                'rsi_levels': f"Long≤{self.rsi_pullback_long}, Short≥{self.rsi_pullback_short}",
                'volume_spike': f"{self.volume_spike}x",
                'min_signal_interval': f"{self.min_signal_interval}시간",
                'realtime': '활성화' if self.realtime_enabled else '비활성화'
            },
            'description': f'Trend Following + Pullback Entry Strategy ({mode_info} based) with Realtime Monitoring'
        }