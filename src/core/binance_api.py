# src/core/binance_api.py
import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal, ROUND_DOWN
from datetime import datetime, timedelta
import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException
import aiohttp
import json
import time

logger = logging.getLogger(__name__)

class ImprovedRateLimiter:
    """개선된 레이트 리미터 - 이벤트 루프 오류 수정"""
    
    def __init__(self, max_requests: int = 1200, window: int = 60):
        self.max_requests = max_requests
        self.window = window  # seconds
        self.requests = {}  # {timestamp: count}
        self.lock = asyncio.Lock()
        
        # 정리 태스크 상태
        self._cleanup_task = None
        self._is_running = False
        
        # 더 정확한 가중치 설정
        self.endpoint_weights = {
            'futures_klines': 5,
            'futures_order': 1,
            'futures_cancel_order': 1,
            'futures_account': 5,
            'futures_position_risk': 1,
            'futures_order_book': 2,
            'futures_ticker': 1,
            'futures_exchange_info': 40,
            'futures_change_leverage': 1,
            'futures_change_margin_type': 1,
        }
        
        logger.debug("ImprovedRateLimiter 초기화 (이벤트 루프 없이)")
    
    async def start(self):
        """레이트 리미터 시작 (비동기 컨텍스트에서만 호출)"""
        if not self._is_running:
            self._is_running = True
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
            logger.debug("레이트 리미터 정리 태스크 시작")
    
    async def stop(self):
        """레이트 리미터 중지"""
        self._is_running = False
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logger.debug("레이트 리미터 정리 태스크 중지")
    
    async def _periodic_cleanup(self):
        """주기적으로 오래된 요청 기록 정리"""
        while self._is_running:
            try:
                await asyncio.sleep(30)  # 30초마다 정리
                async with self.lock:
                    current_time = time.time()
                    cutoff_time = current_time - self.window
                    
                    # 오래된 기록 제거
                    old_timestamps = [ts for ts in self.requests if ts < cutoff_time]
                    for ts in old_timestamps:
                        del self.requests[ts]
                    
                    if old_timestamps:
                        logger.debug(f"레이트 리미터: {len(old_timestamps)}개 오래된 기록 정리")
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"레이트 리미터 정리 중 오류: {e}")
                await asyncio.sleep(60)
    
    async def acquire(self, endpoint: str = 'default', count: int = 1):
        """레이트 리밋 체크 및 대기"""
        weight = self.endpoint_weights.get(endpoint, 1) * count
        
        async with self.lock:
            current_time = time.time()
            current_window_start = current_time - self.window
            
            # 현재 윈도우의 요청 수 계산
            current_requests = sum(
                req_count for timestamp, req_count in self.requests.items()
                if timestamp >= current_window_start
            )
            
            # 리밋 체크
            if current_requests + weight > self.max_requests:
                # 가장 오래된 요청 찾기
                oldest_timestamp = min(
                    ts for ts in self.requests if ts >= current_window_start
                )
                wait_time = self.window - (current_time - oldest_timestamp) + 0.1
                
                if wait_time > 0:
                    logger.warning(
                        f"레이트 리밋 도달 ({current_requests}/{self.max_requests}). "
                        f"{wait_time:.1f}초 대기... (endpoint: {endpoint}, weight: {weight})"
                    )
                    await asyncio.sleep(wait_time)
                    
                    # 대기 후 다시 정리
                    current_time = time.time()
                    current_window_start = current_time - self.window
                    
                    # 오래된 요청 제거
                    self.requests = {
                        ts: count for ts, count in self.requests.items()
                        if ts >= current_window_start
                    }
            
            # 요청 기록
            self.requests[current_time] = weight
    
    def get_current_usage(self) -> Tuple[int, int]:
        """현재 사용량 반환 (used, limit)"""
        current_time = time.time()
        current_window_start = current_time - self.window
        
        current_requests = sum(
            req_count for timestamp, req_count in self.requests.items()
            if timestamp >= current_window_start
        )
        
        return current_requests, self.max_requests

class BinanceAPI:
    """바이낸스 API 클라이언트 - 이벤트 루프 오류 수정"""
    
    def __init__(self, api_key: str, secret_key: str, testnet: bool = False):
        self.api_key = api_key
        self.secret_key = secret_key
        self.testnet = testnet
        
        # 동기 클라이언트 (python-binance)
        self.client: Optional[Client] = None
        
        # 비동기 세션 (aiohttp)
        self.session: Optional[aiohttp.ClientSession] = None
        
        # API 엔드포인트
        if testnet:
            self.base_url = "https://testnet.binancefuture.com"
            self.ws_url = "wss://stream.binancefuture.com"
        else:
            self.base_url = "https://fapi.binance.com"
            self.ws_url = "wss://fstream.binance.com"
        
        # 심볼 정보 캐시
        self.symbol_info_cache = {}
        self.exchange_info_last_update = None
        
        # 레이트 리밋 관리 (초기화만 하고 start는 나중에)
        self.rate_limiter = ImprovedRateLimiter()
        
        self.is_connected = False
        
        logger.info(f"바이낸스 API 초기화 (테스트넷: {testnet})")
    
    async def initialize(self) -> bool:
        """API 초기화 및 연결 확인"""
        try:
            # 동기 클라이언트 초기화
            self.client = Client(
                api_key=self.api_key,
                api_secret=self.secret_key
            )
            
            # 비동기 세션 생성
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
            
            # 레이트 리미터 시작 (이제 이벤트 루프가 있음)
            await self.rate_limiter.start()
            
            # 연결 테스트
            server_time = await self.get_server_time()
            if not server_time:
                raise Exception("서버 시간 조회 실패")
            
            logger.info(f"서버 시간: {datetime.fromtimestamp(server_time/1000)}")
            
            # 계정 정보 확인
            account_info = await self.get_account_info()
            if account_info:
                balance = float(account_info.get('totalWalletBalance', 0))
                logger.info(f"계정 잔고: {balance:.2f} USDT")
            
            # 거래소 정보 로드
            await self.load_exchange_info()
            
            # 포지션 모드 확인 및 설정
            position_mode = await self.get_position_mode()
            logger.info(f"현재 포지션 모드: {position_mode}")
            
            # One-way 모드가 아니면 변경 시도
            if position_mode != 'One-way':
                logger.warning(f"포지션 모드가 {position_mode}입니다. One-way로 변경 시도...")
                try:
                    # 포지션이 없을 때만 변경 가능
                    positions = await self.get_positions()
                    if not positions:
                        # API 호출로 포지션 모드 변경
                        self.client.futures_change_position_mode(dualSidePosition=False)
                        logger.info("✅ 포지션 모드를 One-way로 변경 성공")
                    else:
                        logger.warning("⚠️ 활성 포지션이 있어 포지션 모드를 변경할 수 없습니다.")
                        logger.warning(f"   활성 포지션: {len(positions)}개")
                except Exception as e:
                    logger.error(f"포지션 모드 변경 실패: {e}")
                    logger.warning("현재 모드로 계속 진행합니다.")
            
            self.is_connected = True
            logger.info("✅ 바이낸스 API 연결 성공")
            return True
            
        except Exception as e:
            logger.error(f"바이낸스 API 초기화 실패: {e}")
            # 실패 시 세션 정리
            if self.session and not self.session.closed:
                await self.session.close()
                await asyncio.sleep(0.25)  # graceful shutdown을 위한 대기
            # 레이트 리미터 정리
            if self.rate_limiter:
                await self.rate_limiter.stop()
            return False
    
    async def get_server_time(self) -> Optional[int]:
        """서버 시간 조회"""
        try:
            response = self.client.get_server_time()
            return response['serverTime']
        except Exception as e:
            logger.error(f"서버 시간 조회 실패: {e}")
            return None
    
    async def get_account_info(self) -> Optional[Dict]:
        """계정 정보 조회"""
        try:
            await self.rate_limiter.acquire('futures_account')
            account = self.client.futures_account()
            return account
        except Exception as e:
            logger.error(f"계정 정보 조회 실패: {e}")
            return None
    
    async def get_account_balance(self) -> float:
        """USDT 잔고 조회"""
        try:
            account = await self.get_account_info()
            if account:
                return float(account.get('totalWalletBalance', 0))
            return 0.0
        except Exception as e:
            logger.error(f"잔고 조회 실패: {e}")
            return 0.0
    
    async def load_exchange_info(self) -> bool:
        """거래소 정보 로드 (심볼 정보 캐싱)"""
        try:
            # 캐시 유효성 체크 (1시간)
            if self.exchange_info_last_update:
                if datetime.now() - self.exchange_info_last_update < timedelta(hours=1):
                    return True
            
            await self.rate_limiter.acquire('futures_exchange_info')
            exchange_info = self.client.futures_exchange_info()
            
            self.symbol_info_cache.clear()
            
            for symbol_info in exchange_info['symbols']:
                if symbol_info['status'] == 'TRADING':
                    symbol = symbol_info['symbol']
                    
                    # 필요한 정보만 추출
                    self.symbol_info_cache[symbol] = {
                        'symbol': symbol,
                        'baseAsset': symbol_info['baseAsset'],
                        'quoteAsset': symbol_info['quoteAsset'],
                        'pricePrecision': symbol_info['pricePrecision'],
                        'quantityPrecision': symbol_info['quantityPrecision'],
                        'filters': {f['filterType']: f for f in symbol_info['filters']}
                    }
            
            self.exchange_info_last_update = datetime.now()
            logger.info(f"거래소 정보 로드 완료: {len(self.symbol_info_cache)}개 심볼")
            return True
            
        except Exception as e:
            logger.error(f"거래소 정보 로드 실패: {e}")
            return False
    
    async def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """심볼 정보 조회"""
        if symbol in self.symbol_info_cache:
            return self.symbol_info_cache[symbol]
        
        # 캐시에 없으면 재로드
        await self.load_exchange_info()
        return self.symbol_info_cache.get(symbol)
    
    async def get_current_price(self, symbol: str) -> Optional[float]:
        """현재 가격 조회"""
        try:
            await self.rate_limiter.acquire('futures_ticker')
            ticker = self.client.futures_symbol_ticker(symbol=symbol)
            return float(ticker['price'])
        except Exception as e:
            logger.error(f"가격 조회 실패 ({symbol}): {e}")
            return None
    
    async def get_multiple_prices(self, symbols: List[str]) -> Dict[str, float]:
        """여러 심볼 가격 배치 조회"""
        try:
            await self.rate_limiter.acquire('futures_ticker', len(symbols))
            tickers = self.client.futures_ticker()
            
            prices = {}
            for ticker in tickers:
                if ticker['symbol'] in symbols:
                    prices[ticker['symbol']] = float(ticker['price'])
            
            return prices
            
        except Exception as e:
            logger.error(f"배치 가격 조회 실패: {e}")
            return {}
    
    async def get_klines(self, symbol: str, interval: str, limit: int = 500) -> pd.DataFrame:
        """캔들스틱 데이터 조회"""
        try:
            # 레이트 리밋 체크
            await self.rate_limiter.acquire('futures_klines')
            
            klines = self.client.futures_klines(
                symbol=symbol,
                interval=interval,
                limit=min(limit, 1500)  # 최대 1500개
            )
            
            if not klines:
                return pd.DataFrame()
            
            # DataFrame 변환
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])
            
            # 데이터 타입 변환
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])
            
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('datetime', inplace=True)
            
            return df
            
        except Exception as e:
            logger.error(f"캔들스틱 조회 실패 ({symbol}): {e}")
            return pd.DataFrame()
    
    async def get_positions(self) -> List[Dict]:
        """현재 포지션 조회 - 간단한 버전"""
        try:
            account = await self.get_account_info()
            if not account:
                logger.warning("계정 정보 없음")
                return []
            
            positions = []
            
            for pos in account.get('positions', []):
                try:
                    # 모든 값을 float로 변환
                    position_amt = float(pos.get('positionAmt', '0'))
                    notional = float(pos.get('notional', '0'))
                    unrealized_profit = float(pos.get('unrealizedProfit', '0'))
                    
                    # 포지션이 있는지 확인 - 어떤 값이든 0이 아니면 활성
                    if position_amt != 0 or abs(notional) > 0.01 or abs(unrealized_profit) > 0.01:
                        
                        # Side 결정
                        position_side = pos.get('positionSide', 'BOTH')
                        if position_side == 'BOTH':
                            side = 'LONG' if position_amt > 0 else 'SHORT'
                        else:
                            side = position_side
                        
                        position_data = {
                            'symbol': pos['symbol'],
                            'side': side,
                            'positionAmt': position_amt,  # 원본 값 보존 (부호 포함)
                            'entryPrice': float(pos.get('entryPrice', '0')),
                            'markPrice': float(pos.get('markPrice', '0')),
                            'unRealizedPnl': unrealized_profit,
                            'leverage': int(pos.get('leverage', '1')),
                            'marginType': 'cross' if not pos.get('isolated') else 'isolated',
                            'positionSide': position_side
                        }
                        
                        positions.append(position_data)
                        logger.info(f"활성 포지션: {pos['symbol']} amt={position_amt} notional={notional}")
                        
                except (ValueError, TypeError) as e:
                    logger.debug(f"포지션 데이터 처리 실패 ({pos.get('symbol')}): {e}")
                    continue
            
            logger.info(f"총 활성 포지션: {len(positions)}개")
            return positions
            
        except Exception as e:
            logger.error(f"포지션 조회 실패: {e}")
            return []
    
    async def place_order(self, symbol: str, side: str, quantity: float, 
                         order_type: str = 'MARKET', price: float = None,
                         reduce_only: bool = False) -> Optional[Dict]:
        """주문 실행"""
        try:
            # 레이트 리밋 체크
            await self.rate_limiter.acquire('futures_order')
            
            # 수량 검증 및 포맷
            quantity = await self.validate_quantity(symbol, quantity)
            if quantity <= 0:
                logger.error(f"유효하지 않은 수량: {quantity}")
                return None
            
            # 주문 파라미터
            order_params = {
                'symbol': symbol,
                'side': side,
                'type': order_type,
                'quantity': quantity
            }
            
            if reduce_only:
                order_params['reduceOnly'] = True
            
            if order_type == 'LIMIT' and price:
                price = await self.validate_price(symbol, price)
                order_params['price'] = price
                order_params['timeInForce'] = 'GTC'
            
            # 주문 실행
            result = self.client.futures_create_order(**order_params)
            
            logger.info(f"주문 성공: {symbol} {side} {quantity} @ {order_type}")
            logger.debug(f"주문 결과: {result}")
            
            return result
            
        except BinanceAPIException as e:
            logger.error(f"바이낸스 API 오류: {e.message}")
            return None
        except Exception as e:
            logger.error(f"주문 실패 ({symbol}): {e}")
            return None
    
    async def close_position(self, symbol: str) -> Optional[Dict]:
        """포지션 청산"""
        try:
            # 현재 포지션 조회
            positions = await self.get_positions()
            position = next((p for p in positions if p['symbol'] == symbol), None)
            
            if not position:
                logger.warning(f"청산할 포지션 없음: {symbol}")
                return None
            
            # 반대 주문으로 청산
            side = 'SELL' if position['side'] == 'LONG' else 'BUY'
            quantity = position['positionAmt']
            
            result = await self.place_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type='MARKET',
                reduce_only=True
            )
            
            if result:
                logger.info(f"포지션 청산 성공: {symbol}")
            
            return result
            
        except Exception as e:
            logger.error(f"포지션 청산 실패 ({symbol}): {e}")
            return None
    
    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """레버리지 설정 및 마진 타입 확인"""
        try:
            # 마진 타입 먼저 확인 및 설정 (ISOLATED로)
            await self.set_margin_type(symbol, 'ISOLATED')
            
            # 레이트 리밋 체크
            await self.rate_limiter.acquire('futures_change_leverage')
            
            self.client.futures_change_leverage(symbol=symbol, leverage=leverage)
            logger.info(f"레버리지 설정: {symbol} {leverage}x")
            return True
            
        except BinanceAPIException as e:
            # 이미 설정된 경우 성공으로 처리
            if "No need to change leverage" in str(e):
                logger.debug(f"레버리지 이미 설정됨: {symbol} {leverage}x")
                return True
            logger.error(f"레버리지 설정 실패: {e.message}")
            return False
        except Exception as e:
            logger.error(f"레버리지 설정 실패 ({symbol}): {e}")
            return False
    
    async def set_margin_type(self, symbol: str, margin_type: str = 'ISOLATED') -> bool:
        """마진 타입 설정"""
        try:
            # 레이트 리밋 체크
            await self.rate_limiter.acquire('futures_change_margin_type')
            
            self.client.futures_change_margin_type(symbol=symbol, marginType=margin_type)
            logger.info(f"마진 타입 설정: {symbol} {margin_type}")
            return True
            
        except BinanceAPIException as e:
            # 이미 설정된 경우 성공으로 처리
            if "No need to change margin type" in str(e):
                logger.debug(f"마진 타입 이미 설정됨: {symbol} {margin_type}")
                return True
            logger.error(f"마진 타입 설정 실패: {e.message}")
            return False
        except Exception as e:
            logger.error(f"마진 타입 설정 실패 ({symbol}): {e}")
            return False
    
    async def validate_quantity(self, symbol: str, quantity: float) -> float:
        """수량 검증 및 포맷팅"""
        try:
            symbol_info = await self.get_symbol_info(symbol)
            if not symbol_info:
                return quantity
            
            filters = symbol_info.get('filters', {})
            
            # LOT_SIZE 필터
            lot_size = filters.get('LOT_SIZE', {})
            if lot_size:
                min_qty = float(lot_size.get('minQty', 0))
                max_qty = float(lot_size.get('maxQty', float('inf')))
                step_size = float(lot_size.get('stepSize', 0))
                
                # 최소/최대 수량 체크
                quantity = max(min_qty, min(quantity, max_qty))
                
                # 스텝 사이즈 조정
                if step_size > 0:
                    decimal_qty = Decimal(str(quantity))
                    decimal_step = Decimal(str(step_size))
                    quantity = float(
                        (decimal_qty / decimal_step).quantize(Decimal('1'), rounding=ROUND_DOWN) * decimal_step
                    )
            
            # 정밀도 적용
            precision = symbol_info.get('quantityPrecision', 8)
            quantity = round(quantity, precision)
            
            return quantity
            
        except Exception as e:
            logger.error(f"수량 검증 실패 ({symbol}): {e}")
            return quantity
    
    async def validate_price(self, symbol: str, price: float) -> float:
        """가격 검증 및 포맷팅"""
        try:
            symbol_info = await self.get_symbol_info(symbol)
            if not symbol_info:
                return price
            
            filters = symbol_info.get('filters', {})
            
            # PRICE_FILTER
            price_filter = filters.get('PRICE_FILTER', {})
            if price_filter:
                min_price = float(price_filter.get('minPrice', 0))
                max_price = float(price_filter.get('maxPrice', float('inf')))
                tick_size = float(price_filter.get('tickSize', 0))
                
                # 최소/최대 가격 체크
                price = max(min_price, min(price, max_price))
                
                # 틱 사이즈 조정
                if tick_size > 0:
                    decimal_price = Decimal(str(price))
                    decimal_tick = Decimal(str(tick_size))
                    price = float(
                        (decimal_price / decimal_tick).quantize(Decimal('1')) * decimal_tick
                    )
            
            # 정밀도 적용
            precision = symbol_info.get('pricePrecision', 8)
            price = round(price, precision)
            
            return price
            
        except Exception as e:
            logger.error(f"가격 검증 실패 ({symbol}): {e}")
            return price
    
    async def round_quantity(self, symbol: str, quantity: float) -> float:
        """수량 라운딩 (간단한 버전)"""
        return await self.validate_quantity(symbol, quantity)
    
    async def get_24h_ticker(self, symbol: str) -> Optional[Dict]:
        """24시간 티커 정보 조회"""
        try:
            await self.rate_limiter.acquire('futures_ticker')
            ticker = self.client.futures_ticker(symbol=symbol)
            return {
                'symbol': ticker['symbol'],
                'priceChange': float(ticker['priceChange']),
                'priceChangePercent': float(ticker['priceChangePercent']),
                'lastPrice': float(ticker['lastPrice']),
                'volume': float(ticker['volume']),
                'quoteVolume': float(ticker['quoteVolume']),
                'highPrice': float(ticker['highPrice']),
                'lowPrice': float(ticker['lowPrice'])
            }
        except Exception as e:
            logger.error(f"티커 조회 실패 ({symbol}): {e}")
            return None
    
    async def get_order_book(self, symbol: str, limit: int = 20) -> Optional[Dict]:
        """오더북 조회"""
        try:
            await self.rate_limiter.acquire('futures_order_book')
            order_book = self.client.futures_order_book(symbol=symbol, limit=limit)
            
            return {
                'bids': [[float(price), float(qty)] for price, qty in order_book['bids']],
                'asks': [[float(price), float(qty)] for price, qty in order_book['asks']],
                'lastUpdateId': order_book['lastUpdateId']
            }
        except Exception as e:
            logger.error(f"오더북 조회 실패 ({symbol}): {e}")
            return None
    
    def get_system_stats(self) -> Dict:
        """시스템 통계 반환"""
        usage, limit = self.rate_limiter.get_current_usage()
        
        return {
            'is_connected': self.is_connected,
            'testnet': self.testnet,
            'rate_limit': {
                'current_usage': usage,
                'limit': limit,
                'usage_percent': (usage / limit * 100) if limit > 0 else 0
            },
            'cache': {
                'symbols_cached': len(self.symbol_info_cache),
                'last_exchange_info_update': self.exchange_info_last_update.isoformat() if self.exchange_info_last_update else None
            }
        }
    
    async def get_position_mode(self) -> str:
        """현재 포지션 모드 확인
        Returns: 'One-way' or 'Hedge'
        """
        try:
            # API 호출로 포지션 모드 확인
            result = self.client.futures_get_position_mode()
            dual_side_position = result.get('dualSidePosition', False)
            
            mode = 'Hedge' if dual_side_position else 'One-way'
            logger.info(f"포지션 모드: {mode} (dualSidePosition={dual_side_position})")
            return mode
            
        except Exception as e:
            logger.error(f"포지션 모드 확인 실패: {e}")
            # 기본값은 One-way
            return 'One-way'
    
    async def cleanup(self):
        """리소스 정리"""
        try:
            # 레이트 리미터 정리
            if self.rate_limiter:
                await self.rate_limiter.stop()
            
            # 세션 정리
            if self.session and not self.session.closed:
                await self.session.close()
                await asyncio.sleep(0.25)
            
            self.is_connected = False
            logger.info("바이낸스 API 연결 종료")
            
        except Exception as e:
            logger.error(f"API 정리 중 오류: {e}")