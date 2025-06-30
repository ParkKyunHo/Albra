# src/core/realtime_price_monitor.py
import asyncio
import json
import logging
from typing import Dict, List, Callable, Optional, Set
from datetime import datetime
import websockets
from collections import defaultdict

logger = logging.getLogger(__name__)

class RealtimePriceMonitor:
    """바이낸스 WebSocket을 통한 실시간 가격 모니터링"""
    
    def __init__(self, binance_api):
        self.binance_api = binance_api
        self.ws = None
        self.is_running = False
        
        # 이벤트 핸들러
        self.event_handlers = defaultdict(list)
        
        # 심볼별 데이터 캐시
        self.price_cache = {}
        self.kline_cache = {}
        
        # 모니터링 심볼
        self.symbols: Set[str] = set()
        
        # WebSocket URL
        self.ws_url = "wss://fstream.binance.com/ws"  # Futures WebSocket
        
        # 재연결 설정
        self.reconnect_delay = 5
        self.max_reconnect_attempts = 10
        
    def on(self, event: str, handler: Callable):
        """이벤트 핸들러 등록"""
        self.event_handlers[event].append(handler)
        logger.info(f"이벤트 핸들러 등록: {event}")
        
    def off(self, event: str, handler: Callable):
        """이벤트 핸들러 제거"""
        if handler in self.event_handlers[event]:
            self.event_handlers[event].remove(handler)
            
    async def emit(self, event: str, *args, **kwargs):
        """이벤트 발생"""
        handlers = self.event_handlers.get(event, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(*args, **kwargs)
                else:
                    handler(*args, **kwargs)
            except Exception as e:
                logger.error(f"이벤트 핸들러 오류 ({event}): {e}")
    
    async def add_symbols(self, symbols: List[str]):
        """모니터링할 심볼 추가"""
        new_symbols = set(symbols) - self.symbols
        if new_symbols:
            self.symbols.update(new_symbols)
            logger.info(f"모니터링 심볼 추가: {', '.join(new_symbols)}")
            
            # 이미 연결중이면 구독 추가
            if self.ws and not self.ws.closed:
                await self._subscribe_symbols(list(new_symbols))
    
    async def remove_symbols(self, symbols: List[str]):
        """모니터링 심볼 제거"""
        self.symbols -= set(symbols)
        # 구독 해제는 재연결시 자동 처리
        
    async def start(self):
        """WebSocket 연결 시작"""
        self.is_running = True
        reconnect_count = 0
        
        while self.is_running and reconnect_count < self.max_reconnect_attempts:
            try:
                logger.info("WebSocket 연결 시작...")
                await self._connect()
                reconnect_count = 0  # 연결 성공시 카운트 리셋
                
            except Exception as e:
                reconnect_count += 1
                logger.error(f"WebSocket 연결 실패 (시도 {reconnect_count}/{self.max_reconnect_attempts}): {e}")
                
                if reconnect_count < self.max_reconnect_attempts:
                    await asyncio.sleep(self.reconnect_delay * reconnect_count)
                else:
                    logger.error("최대 재연결 시도 횟수 초과")
                    await self.emit('connection_failed')
                    break
    
    async def _connect(self):
        """WebSocket 연결 및 메시지 처리"""
        async with websockets.connect(self.ws_url) as websocket:
            self.ws = websocket
            logger.info("✓ WebSocket 연결 성공")
            
            # 심볼 구독
            if self.symbols:
                await self._subscribe_symbols(list(self.symbols))
            
            # 연결 성공 이벤트
            await self.emit('connected')
            
            # 메시지 수신 루프
            async for message in websocket:
                if not self.is_running:
                    break
                    
                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON 파싱 오류: {e}")
                except Exception as e:
                    logger.error(f"메시지 처리 오류: {e}")
    
    async def _subscribe_symbols(self, symbols: List[str]):
        """심볼 구독"""
        if not self.ws or self.ws.closed:
            return
            
        # 스트림 리스트 생성
        streams = []
        for symbol in symbols:
            symbol_lower = symbol.lower()
            streams.extend([
                f"{symbol_lower}@kline_1m",    # 1분봉
                f"{symbol_lower}@kline_15m",   # 15분봉  
                f"{symbol_lower}@aggTrade",     # 체결 데이터
                f"{symbol_lower}@markPrice"     # 마크 가격
            ])
        
        # 구독 메시지
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": 1
        }
        
        await self.ws.send(json.dumps(subscribe_msg))
        logger.info(f"구독 요청: {len(symbols)}개 심볼")
    
    async def _handle_message(self, data: Dict):
        """WebSocket 메시지 처리"""
        if 'e' not in data:
            return
            
        event_type = data['e']
        
        # 캔들 데이터
        if event_type == 'kline':
            await self._handle_kline(data)
            
        # 체결 데이터
        elif event_type == 'aggTrade':
            await self._handle_trade(data)
            
        # 마크 가격
        elif event_type == 'markPriceUpdate':
            await self._handle_mark_price(data)
    
    async def _handle_kline(self, data: Dict):
        """캔들 데이터 처리"""
        kline = data['k']
        symbol = kline['s']
        interval = kline['i']
        
        # 캔들 정보
        candle_info = {
            'time': datetime.fromtimestamp(kline['t'] / 1000),
            'open': float(kline['o']),
            'high': float(kline['h']),
            'low': float(kline['l']),
            'close': float(kline['c']),
            'volume': float(kline['v']),
            'is_closed': kline['x']  # 캔들 완성 여부
        }
        
        # 캐시 업데이트
        if symbol not in self.kline_cache:
            self.kline_cache[symbol] = {}
        self.kline_cache[symbol][interval] = candle_info
        
        # 이벤트 발생
        await self.emit('kline_update', symbol, interval, candle_info)
        
        # 캔들 완성시 추가 이벤트
        if candle_info['is_closed']:
            await self.emit('kline_closed', symbol, interval, candle_info)
    
    async def _handle_trade(self, data: Dict):
        """체결 데이터 처리"""
        symbol = data['s']
        trade_info = {
            'time': datetime.fromtimestamp(data['T'] / 1000),
            'price': float(data['p']),
            'quantity': float(data['q']),
            'is_buyer_maker': data['m']
        }
        
        # 가격 캐시 업데이트
        self.price_cache[symbol] = trade_info['price']
        
        # 이벤트 발생
        await self.emit('trade', symbol, trade_info)
        await self.emit('price_update', symbol, trade_info['price'])
    
    async def _handle_mark_price(self, data: Dict):
        """마크 가격 처리"""
        symbol = data['s']
        mark_price = float(data['p'])
        
        # 이벤트 발생
        await self.emit('mark_price_update', symbol, mark_price)
    
    def get_cached_price(self, symbol: str) -> Optional[float]:
        """캐시된 가격 조회"""
        return self.price_cache.get(symbol)
    
    def get_cached_kline(self, symbol: str, interval: str) -> Optional[Dict]:
        """캐시된 캔들 조회"""
        return self.kline_cache.get(symbol, {}).get(interval)
    
    async def stop(self):
        """WebSocket 연결 종료"""
        self.is_running = False
        
        if self.ws and not self.ws.closed:
            await self.ws.close()
            
        logger.info("WebSocket 연결 종료")
        await self.emit('disconnected')