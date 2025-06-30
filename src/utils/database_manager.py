"""
데이터베이스 관리자
- SQLite 연결 관리 및 쿼리 실행
- 배치 처리 및 성능 최적화
"""

import os
import json
import sqlite3
import asyncio
import threading
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from contextlib import contextmanager, asynccontextmanager
from pathlib import Path
import time
from collections import defaultdict
import queue

from src.utils.logger import logger


class ConnectionPool:
    """SQLite 연결 풀 관리자"""
    
    def __init__(self, db_path: str, max_connections: int = 10):
        self.db_path = db_path
        self.max_connections = max_connections
        self.connections = queue.Queue(maxsize=max_connections)
        self.active_connections = 0
        self._lock = threading.Lock()
        self._closed = False
        
        # 초기 연결 생성
        for _ in range(min(3, max_connections)):
            self._create_connection()
    
    def _create_connection(self) -> sqlite3.Connection:
        """새 연결 생성"""
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            isolation_level=None  # autocommit mode
        )
        conn.row_factory = sqlite3.Row
        
        # WAL 모드 설정
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=10000")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA mmap_size=30000000000")
        
        return conn
    
    def get_connection(self, timeout: float = 5.0) -> sqlite3.Connection:
        """연결 획득"""
        if self._closed:
            raise RuntimeError("Connection pool is closed")
            
        try:
            # 사용 가능한 연결 확인
            conn = self.connections.get(timeout=timeout)
            
            # 연결 상태 확인
            try:
                conn.execute("SELECT 1")
            except:
                # 연결이 끊어진 경우 새로 생성
                conn = self._create_connection()
            
            return conn
            
        except queue.Empty:
            # 풀이 가득 찬 경우
            with self._lock:
                if self.active_connections < self.max_connections:
                    self.active_connections += 1
                    return self._create_connection()
                else:
                    raise TimeoutError("No available connections in pool")
    
    def return_connection(self, conn: sqlite3.Connection):
        """연결 반환"""
        if not self._closed and conn:
            try:
                self.connections.put(conn, timeout=1.0)
            except queue.Full:
                # 풀이 가득 찬 경우 연결 종료
                conn.close()
                with self._lock:
                    self.active_connections -= 1
    
    def close_all(self):
        """모든 연결 종료"""
        self._closed = True
        
        # 모든 연결 종료
        while not self.connections.empty():
            try:
                conn = self.connections.get_nowait()
                conn.close()
            except:
                pass
        
        self.active_connections = 0
    
    def get_stats(self) -> Dict:
        """풀 상태 반환"""
        return {
            'max_connections': self.max_connections,
            'active_connections': self.active_connections,
            'available_connections': self.connections.qsize(),
            'is_closed': self._closed
        }


class DatabaseManager:
    """데이터베이스 관리자"""
    
    def __init__(self, db_path: str = "data/trading_bot.db"):
        self.db_path = db_path
        self.connection_pool = None
        self._batch_queue = []
        self._batch_lock = asyncio.Lock()
        self._batch_task = None
        self._last_commit = datetime.now()
        self._is_running = False
        
        # 배치 처리 설정
        self.batch_config = {
            'size': 100,
            'interval': 5.0,  # 초
            'enabled': True
        }
        
        # 통계
        self.stats = {
            'queries_executed': 0,
            'batch_commits': 0,
            'errors': 0,
            'last_error': None
        }
        
        # 디렉토리 생성
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        # 연결 풀 초기화
        self.connection_pool = ConnectionPool(db_path, max_connections=10)
        
        # 테이블 생성
        self._init_database()
        
        logger.info(f"데이터베이스 매니저 초기화 완료: {db_path}")
    
    def _init_database(self):
        """데이터베이스 초기화"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 기존 테이블 확인 및 마이그레이션
                self._migrate_existing_tables(cursor)
                
                # 포지션 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS positions (
                        position_id TEXT PRIMARY KEY,
                        symbol TEXT NOT NULL,
                        side TEXT NOT NULL,
                        size REAL NOT NULL,
                        entry_price REAL NOT NULL,
                        exit_price REAL,
                        status TEXT NOT NULL,
                        pnl REAL DEFAULT 0,
                        pnl_percent REAL DEFAULT 0,
                        reason TEXT,
                        stop_loss REAL,
                        take_profit REAL,
                        strategy_name TEXT,
                        metadata JSON,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        closed_at TIMESTAMP,
                        last_check TIMESTAMP,
                        peak_price REAL,
                        peak_pnl_percent REAL DEFAULT 0,
                        valley_price REAL,
                        valley_pnl_percent REAL DEFAULT 0,
                        max_drawdown_percent REAL DEFAULT 0,
                        holding_hours REAL,
                        market_condition TEXT,
                        entry_reason TEXT,
                        exit_reason TEXT,
                        partial_close_count INTEGER DEFAULT 0,
                        total_fees REAL DEFAULT 0,
                        risk_reward_ratio REAL,
                        entry_signal_strength REAL,
                        exit_signal_strength REAL,
                        data JSON
                    )
                """)
                
                # 거래 이력
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS trades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        position_id TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        action TEXT NOT NULL,
                        size REAL NOT NULL,
                        price REAL NOT NULL,
                        pnl REAL DEFAULT 0,
                        pnl_percent REAL DEFAULT 0,
                        fees REAL DEFAULT 0,
                        reason TEXT,
                        strategy_name TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        market_price REAL,
                        slippage REAL,
                        execution_time_ms INTEGER,
                        FOREIGN KEY (position_id) REFERENCES positions (position_id)
                    )
                """)
                
                # 일일 요약
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS daily_summary (
                        date DATE PRIMARY KEY,
                        total_trades INTEGER DEFAULT 0,
                        win_trades INTEGER DEFAULT 0,
                        loss_trades INTEGER DEFAULT 0,
                        total_pnl REAL DEFAULT 0,
                        total_pnl_percent REAL DEFAULT 0,
                        max_drawdown REAL DEFAULT 0,
                        total_volume REAL DEFAULT 0,
                        total_fees REAL DEFAULT 0,
                        best_trade REAL DEFAULT 0,
                        worst_trade REAL DEFAULT 0,
                        avg_holding_time REAL DEFAULT 0,
                        data JSON,
                        sharpe_ratio REAL,
                        win_rate REAL,
                        profit_factor REAL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 시스템 이벤트
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS system_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_type TEXT NOT NULL,
                        level TEXT NOT NULL,
                        title TEXT,
                        message TEXT,
                        data JSON,
                        source TEXT DEFAULT 'SYSTEM',
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        user_id TEXT,
                        session_id TEXT,
                        correlation_id TEXT
                    )
                """)
                
                # 성능 메트릭
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS performance_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        strategy_name TEXT NOT NULL,
                        metric_name TEXT NOT NULL,
                        metric_value REAL NOT NULL,
                        period_start TIMESTAMP NOT NULL,
                        period_end TIMESTAMP NOT NULL,
                        timeframe TEXT NOT NULL,
                        symbol TEXT,
                        additional_data JSON,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(strategy_name, metric_name, period_start, timeframe, symbol)
                    )
                """)
                
                # 인덱스 생성
                indexes = [
                    "CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol)",
                    "CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status)",
                    "CREATE INDEX IF NOT EXISTS idx_positions_strategy ON positions(strategy_name)",
                    "CREATE INDEX IF NOT EXISTS idx_positions_created_at ON positions(created_at)",
                    "CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp)",
                    "CREATE INDEX IF NOT EXISTS idx_trades_action ON trades(action)",
                    "CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy_name)",
                    "CREATE INDEX IF NOT EXISTS idx_trades_symbol_timestamp ON trades(symbol, timestamp)",
                    "CREATE INDEX IF NOT EXISTS idx_trades_position_id ON trades(position_id)",
                    "CREATE INDEX IF NOT EXISTS idx_events_timestamp ON system_events(timestamp)",
                    "CREATE INDEX IF NOT EXISTS idx_events_correlation ON system_events(correlation_id)",
                    "CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_summary(date)",
                    "CREATE INDEX IF NOT EXISTS idx_metrics_strategy ON performance_metrics(strategy_name)",
                    "CREATE INDEX IF NOT EXISTS idx_metrics_timeframe ON performance_metrics(timeframe)",
                    "CREATE INDEX IF NOT EXISTS idx_metrics_created ON performance_metrics(created_at)"
                ]
                
                for idx_sql in indexes:
                    cursor.execute(idx_sql)
                
                conn.commit()
                
                logger.info("데이터베이스 테이블 초기화 완료")
                
        except Exception as e:
            logger.error(f"데이터베이스 초기화 실패: {e}")
            raise
    
    def _migrate_existing_tables(self, cursor):
        """기존 테이블 마이그레이션"""
        try:
            # positions 테이블에 strategy_name 컬럼 추가
            cursor.execute("PRAGMA table_info(positions)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'strategy_name' not in columns:
                cursor.execute("ALTER TABLE positions ADD COLUMN strategy_name TEXT")
                logger.info("positions 테이블에 strategy_name 컬럼 추가")
            
            # trades 테이블에 strategy_name 컬럼 추가
            cursor.execute("PRAGMA table_info(trades)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'strategy_name' not in columns:
                cursor.execute("ALTER TABLE trades ADD COLUMN strategy_name TEXT")
                logger.info("trades 테이블에 strategy_name 컬럼 추가")
            
            # system_events 테이블에 correlation_id 컬럼 추가
            cursor.execute("PRAGMA table_info(system_events)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'correlation_id' not in columns:
                cursor.execute("ALTER TABLE system_events ADD COLUMN correlation_id TEXT")
                logger.info("system_events 테이블에 correlation_id 컬럼 추가")
            
            # test_table이 있으면 확인
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='test_table'")
            if cursor.fetchone():
                # test_table에도 strategy_name 추가 (테스트를 위해)
                cursor.execute("PRAGMA table_info(test_table)")
                columns = [row[1] for row in cursor.fetchall()]
                
                if 'strategy_name' not in columns:
                    cursor.execute("ALTER TABLE test_table ADD COLUMN strategy_name TEXT")
                    logger.info("test_table에 strategy_name 컬럼 추가")
                    
        except Exception as e:
            logger.warning(f"마이그레이션 중 경고: {e}")
            # 마이그레이션 오류는 무시하고 계속 진행
    
    @contextmanager
    def get_connection(self):
        """동기 연결 컨텍스트 매니저"""
        conn = None
        try:
            conn = self.connection_pool.get_connection()
            yield conn
        finally:
            if conn:
                self.connection_pool.return_connection(conn)
    
    @asynccontextmanager
    async def get_async_connection(self):
        """비동기 연결 컨텍스트 매니저"""
        conn = None
        try:
            # 동기 함수를 비동기로 실행
            loop = asyncio.get_event_loop()
            conn = await loop.run_in_executor(
                None, self.connection_pool.get_connection
            )
            yield conn
        finally:
            if conn:
                await loop.run_in_executor(
                    None, self.connection_pool.return_connection, conn
                )
    
    async def execute_async(self, sql: str, params: Tuple = None, 
                          use_batch: bool = True) -> bool:
        """비동기 쿼리 실행"""
        try:
            if use_batch and self.batch_config['enabled'] and sql.upper().startswith(('INSERT', 'UPDATE')):
                # 배치 큐에 추가
                async with self._batch_lock:
                    self._batch_queue.append((sql, params))
                    
                    # 배치 크기 도달 시 즉시 처리
                    if len(self._batch_queue) >= self.batch_config['size']:
                        await self._process_batch()
                
                return True
            else:
                # 즉시 실행
                async with self.get_async_connection() as conn:
                    cursor = conn.cursor()
                    if params:
                        cursor.execute(sql, params)
                    else:
                        cursor.execute(sql)
                    conn.commit()
                    
                    self.stats['queries_executed'] += 1
                    return True
                    
        except Exception as e:
            logger.error(f"쿼리 실행 실패: {e}")
            self.stats['errors'] += 1
            self.stats['last_error'] = str(e)
            return False
    
    async def execute_many_async(self, sql: str, params_list: List[Tuple]) -> bool:
        """비동기 다중 쿼리 실행"""
        try:
            async with self.get_async_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(sql, params_list)
                conn.commit()
                
                self.stats['queries_executed'] += len(params_list)
                return True
                
        except Exception as e:
            logger.error(f"다중 쿼리 실행 실패: {e}")
            self.stats['errors'] += 1
            self.stats['last_error'] = str(e)
            return False
    
    async def fetch_async(self, sql: str, params: Tuple = None) -> List[Dict]:
        """비동기 조회"""
        try:
            async with self.get_async_connection() as conn:
                cursor = conn.cursor()
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                
                rows = cursor.fetchall()
                self.stats['queries_executed'] += 1
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"조회 실패: {e}")
            self.stats['errors'] += 1
            self.stats['last_error'] = str(e)
            return []
    
    async def fetch_one_async(self, sql: str, params: Tuple = None) -> Optional[Dict]:
        """비동기 단일 조회"""
        try:
            async with self.get_async_connection() as conn:
                cursor = conn.cursor()
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                
                row = cursor.fetchone()
                self.stats['queries_executed'] += 1
                
                return dict(row) if row else None
                
        except Exception as e:
            logger.error(f"단일 조회 실패: {e}")
            self.stats['errors'] += 1
            self.stats['last_error'] = str(e)
            return None
    
    async def _process_batch(self):
        """배치 처리"""
        if not self._batch_queue:
            return
            
        try:
            async with self.get_async_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("BEGIN TRANSACTION")
                
                try:
                    # 배치 실행
                    for sql, params in self._batch_queue:
                        if params:
                            cursor.execute(sql, params)
                        else:
                            cursor.execute(sql)
                    
                    cursor.execute("COMMIT")
                    
                    self.stats['queries_executed'] += len(self._batch_queue)
                    self.stats['batch_commits'] += 1
                    
                    # 큐 비우기
                    self._batch_queue.clear()
                    self._last_commit = datetime.now()
                    
                except Exception as e:
                    cursor.execute("ROLLBACK")
                    raise e
                    
        except Exception as e:
            logger.error(f"배치 처리 실패: {e}")
            self.stats['errors'] += 1
            self.stats['last_error'] = str(e)
            
            # 실패한 쿼리들을 개별 실행 시도
            for sql, params in self._batch_queue:
                await self.execute_async(sql, params, use_batch=False)
            
            self._batch_queue.clear()
    
    async def _batch_processor(self):
        """배치 처리 루프"""
        logger.info("배치 프로세서 시작")
        
        while self._is_running:
            try:
                # 지정된 시간 대기
                await asyncio.sleep(self.batch_config['interval'])
                
                # 배치 처리
                async with self._batch_lock:
                    if self._batch_queue:
                        await self._process_batch()
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"배치 프로세서 오류: {e}")
                await asyncio.sleep(1)
        
        # 종료 시 남은 배치 처리
        async with self._batch_lock:
            if self._batch_queue:
                await self._process_batch()
        
        logger.info("배치 프로세서 종료")
    
    async def start(self):
        """배치 프로세서 시작"""
        if not self._is_running:
            self._is_running = True
            self._batch_task = asyncio.create_task(self._batch_processor())
            logger.info("데이터베이스 배치 프로세서 시작됨")
    
    async def stop(self):
        """배치 프로세서 중지"""
        if self._is_running:
            self._is_running = False
            
            if self._batch_task:
                self._batch_task.cancel()
                try:
                    await self._batch_task
                except asyncio.CancelledError:
                    pass
            
            # 남은 배치 처리
            async with self._batch_lock:
                if self._batch_queue:
                    await self._process_batch()
            
            logger.info("데이터베이스 배치 프로세서 중지됨")
    
    # 포지션 관련 메서드
    async def save_position(self, position_data: Dict) -> bool:
        """포지션 저장"""
        try:
            # 필수 필드 검증
            required_fields = ['position_id', 'symbol', 'side', 'size', 'entry_price', 'status']
            for field in required_fields:
                if field not in position_data:
                    logger.error(f"필수 필드 누락: {field}")
                    return False
            
            # metadata와 data 필드를 JSON으로 변환
            if 'metadata' in position_data and isinstance(position_data['metadata'], dict):
                position_data['metadata'] = json.dumps(position_data['metadata'])
            
            if 'data' in position_data and isinstance(position_data['data'], dict):
                position_data['data'] = json.dumps(position_data['data'])
            
            # 기존 포지션 확인
            existing = await self.get_position(position_data['position_id'])
            
            if existing:
                # 업데이트
                update_fields = []
                update_values = []
                
                for key, value in position_data.items():
                    if key != 'position_id':
                        update_fields.append(f"{key} = ?")
                        update_values.append(value)
                
                update_values.append(position_data['position_id'])
                
                sql = f"""
                    UPDATE positions 
                    SET {', '.join(update_fields)}, updated_at = CURRENT_TIMESTAMP
                    WHERE position_id = ?
                """
                
                return await self.execute_async(sql, tuple(update_values))
                
            else:
                # 신규 생성
                fields = list(position_data.keys())
                placeholders = ['?' for _ in fields]
                values = list(position_data.values())
                
                sql = f"""
                    INSERT INTO positions ({', '.join(fields)})
                    VALUES ({', '.join(placeholders)})
                """
                
                return await self.execute_async(sql, tuple(values))
                
        except Exception as e:
            logger.error(f"포지션 저장 실패: {e}")
            return False
    
    async def get_position(self, position_id: str) -> Optional[Dict]:
        """포지션 조회"""
        sql = "SELECT * FROM positions WHERE position_id = ?"
        result = await self.fetch_one_async(sql, (position_id,))
        
        if result:
            # JSON 필드 파싱
            if result.get('metadata'):
                try:
                    result['metadata'] = json.loads(result['metadata'])
                except:
                    result['metadata'] = {}
            
            if result.get('data'):
                try:
                    result['data'] = json.loads(result['data'])
                except:
                    result['data'] = {}
        
        return result
    
    async def get_active_positions(self, symbol: str = None) -> List[Dict]:
        """활성 포지션 조회"""
        if symbol:
            sql = "SELECT * FROM positions WHERE status = 'ACTIVE' AND symbol = ?"
            params = (symbol,)
        else:
            sql = "SELECT * FROM positions WHERE status = 'ACTIVE'"
            params = None
        
        results = await self.fetch_async(sql, params)
        
        # JSON 필드 파싱
        for result in results:
            if result.get('metadata'):
                try:
                    result['metadata'] = json.loads(result['metadata'])
                except:
                    result['metadata'] = {}
            
            if result.get('data'):
                try:
                    result['data'] = json.loads(result['data'])
                except:
                    result['data'] = {}
        
        return results
    
    async def update_position_status(self, position_id: str, status: str, 
                                   exit_price: float = None, pnl: float = None,
                                   pnl_percent: float = None, reason: str = None) -> bool:
        """포지션 상태 업데이트"""
        try:
            update_data = {
                'status': status,
                'updated_at': datetime.now().isoformat()
            }
            
            if exit_price is not None:
                update_data['exit_price'] = exit_price
            
            if pnl is not None:
                update_data['pnl'] = pnl
            
            if pnl_percent is not None:
                update_data['pnl_percent'] = pnl_percent
            
            if reason:
                update_data['reason'] = reason
            
            if status == 'CLOSED':
                update_data['closed_at'] = datetime.now().isoformat()
                
                # 보유 시간 계산
                position = await self.get_position(position_id)
                if position and position.get('created_at'):
                    created_at = datetime.fromisoformat(position['created_at'])
                    holding_hours = (datetime.now() - created_at).total_seconds() / 3600
                    update_data['holding_hours'] = holding_hours
            
            # SQL 생성
            fields = []
            values = []
            for key, value in update_data.items():
                fields.append(f"{key} = ?")
                values.append(value)
            
            values.append(position_id)
            
            sql = f"""
                UPDATE positions 
                SET {', '.join(fields)}
                WHERE position_id = ?
            """
            
            return await self.execute_async(sql, tuple(values))
            
        except Exception as e:
            logger.error(f"포지션 상태 업데이트 실패: {e}")
            return False
    
    # 거래 기록 관련 메서드
    async def record_trade(self, trade_data: Dict) -> bool:
        """거래 기록"""
        try:
            sql = """
                INSERT INTO trades 
                (position_id, symbol, action, size, price, pnl, pnl_percent, 
                 fees, reason, strategy_name, market_price, slippage, execution_time_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            params = (
                trade_data['position_id'],
                trade_data['symbol'],
                trade_data['action'],
                trade_data['size'],
                trade_data['price'],
                trade_data.get('pnl', 0),
                trade_data.get('pnl_percent', 0),
                trade_data.get('fees', 0),
                trade_data.get('reason', ''),
                trade_data.get('strategy_name'),
                trade_data.get('market_price'),
                trade_data.get('slippage'),
                trade_data.get('execution_time_ms')
            )
            
            success = await self.execute_async(sql, params, use_batch=True)
            
            if success:
                # 일일 요약 업데이트 (비동기)
                asyncio.create_task(self._update_daily_summary(trade_data))
            
            return success
            
        except Exception as e:
            logger.error(f"거래 기록 실패: {e}")
            return False
    
    async def _update_daily_summary(self, trade_data: Dict):
        """일일 요약 업데이트"""
        try:
            today = datetime.now().date()
            
            # 트랜잭션으로 처리
            async with self.get_async_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("BEGIN TRANSACTION")
                
                try:
                    # 기존 요약 조회
                    cursor.execute("SELECT * FROM daily_summary WHERE date = ?", (today,))
                    row = cursor.fetchone()
                    
                    pnl = trade_data.get('pnl', 0)
                    pnl_percent = trade_data.get('pnl_percent', 0)
                    volume = trade_data['size'] * trade_data['price']
                    fees = trade_data.get('fees', 0)
                    
                    if row:
                        # 기존 데이터 업데이트
                        cursor.execute("""
                            UPDATE daily_summary 
                            SET total_trades = total_trades + 1,
                                win_trades = win_trades + ?,
                                loss_trades = loss_trades + ?,
                                total_pnl = total_pnl + ?,
                                total_pnl_percent = total_pnl_percent + ?,
                                total_volume = total_volume + ?,
                                total_fees = total_fees + ?,
                                best_trade = MAX(best_trade, ?),
                                worst_trade = MIN(worst_trade, ?),
                                updated_at = CURRENT_TIMESTAMP
                            WHERE date = ?
                        """, (
                            1 if pnl > 0 else 0,
                            1 if pnl < 0 else 0,
                            pnl,
                            pnl_percent,
                            volume,
                            fees,
                            pnl,
                            pnl,
                            today
                        ))
                        
                        # 승률 계산 및 업데이트
                        cursor.execute("""
                            UPDATE daily_summary 
                            SET win_rate = CASE 
                                WHEN total_trades > 0 
                                THEN CAST(win_trades AS REAL) / total_trades * 100 
                                ELSE 0 
                            END
                            WHERE date = ?
                        """, (today,))
                        
                    else:
                        # 신규 생성
                        cursor.execute("""
                            INSERT INTO daily_summary 
                            (date, total_trades, win_trades, loss_trades, total_pnl, 
                             total_pnl_percent, total_volume, total_fees, best_trade, 
                             worst_trade, win_rate)
                            VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            today,
                            1 if pnl > 0 else 0,
                            1 if pnl < 0 else 0,
                            pnl,
                            pnl_percent,
                            volume,
                            fees,
                            pnl,
                            pnl,
                            100.0 if pnl > 0 else 0.0
                        ))
                    
                    # Profit Factor 계산 (승리 거래의 총 수익 / 패배 거래의 총 손실)
                    cursor.execute("""
                        SELECT 
                            SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END) as total_wins,
                            SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END) as total_losses
                        FROM trades
                        WHERE DATE(timestamp) = ?
                    """, (today,))
                    
                    result = cursor.fetchone()
                    if result:
                        total_wins = result['total_wins'] or 0
                        total_losses = result['total_losses'] or 0
                        
                        profit_factor = (
                            total_wins / total_losses 
                            if total_losses > 0 
                            else float('inf') if total_wins > 0 else 0
                        )
                        
                        cursor.execute("""
                            UPDATE daily_summary 
                            SET profit_factor = ?
                            WHERE date = ?
                        """, (profit_factor, today))
                    
                    # 평균 보유 시간 계산 (오늘 청산된 포지션 기준)
                    cursor.execute("""
                        SELECT AVG(
                            JULIANDAY(closed_at) - JULIANDAY(created_at)
                        ) * 24 as avg_hours
                        FROM positions
                        WHERE DATE(closed_at) = ? AND status = 'CLOSED'
                    """, (today,))
                    
                    avg_result = cursor.fetchone()
                    if avg_result and avg_result['avg_hours']:
                        cursor.execute("""
                            UPDATE daily_summary 
                            SET avg_holding_time = ?
                            WHERE date = ?
                        """, (avg_result['avg_hours'], today))
                    
                    # 최대 낙폭 계산 (오늘의 거래 기준)
                    cursor.execute("""
                        SELECT MIN(
                            SUM(pnl) OVER (ORDER BY timestamp)
                        ) as max_drawdown
                        FROM trades
                        WHERE DATE(timestamp) = ?
                    """, (today,))
                    
                    dd_result = cursor.fetchone()
                    if dd_result and dd_result['max_drawdown']:
                        max_drawdown = abs(min(0, dd_result['max_drawdown']))
                        cursor.execute("""
                            UPDATE daily_summary 
                            SET max_drawdown = ?
                            WHERE date = ?
                        """, (max_drawdown, today))
                    
                    # 추가 메타데이터 저장
                    metadata = {
                        'last_trade_time': trade_data.get('timestamp', datetime.now().isoformat()),
                        'last_symbol': trade_data.get('symbol'),
                        'last_action': trade_data.get('action'),
                        'strategies_used': []
                    }
                    
                    # 오늘 사용된 전략 목록
                    cursor.execute("""
                        SELECT DISTINCT strategy_name 
                        FROM trades 
                        WHERE DATE(timestamp) = ? AND strategy_name IS NOT NULL
                    """, (today,))
                    
                    strategies = cursor.fetchall()
                    if strategies:
                        metadata['strategies_used'] = [s['strategy_name'] for s in strategies]
                    
                    cursor.execute("""
                        UPDATE daily_summary 
                        SET data = ?
                        WHERE date = ?
                    """, (json.dumps(metadata), today))
                    
                    # 트랜잭션 커밋
                    cursor.execute("COMMIT")
                    
                    logger.debug(f"일일 요약 업데이트 완료: {today}")
                    
                except Exception as e:
                    cursor.execute("ROLLBACK")
                    raise e
                    
        except Exception as e:
            logger.error(f"일일 요약 업데이트 실패: {e}")
            # 오류가 발생해도 메인 플로우에 영향을 주지 않도록 예외를 다시 발생시키지 않음
    
    async def record_partial_close(self, position_id: str, symbol: str, 
                                 closed_size: float, remaining_size: float,
                                 exit_price: float, entry_price: float, 
                                 side: str) -> bool:
        """부분 청산 기록"""
        try:
            # PnL 계산
            if side == 'LONG':
                pnl_percent = (exit_price - entry_price) / entry_price * 100
            else:
                pnl_percent = (entry_price - exit_price) / entry_price * 100
            
            pnl_amount = closed_size * entry_price * (pnl_percent / 100)
            
            # 거래 기록
            trade_data = {
                'position_id': position_id,
                'symbol': symbol,
                'action': 'PARTIAL_CLOSE',
                'size': closed_size,
                'price': exit_price,
                'pnl': pnl_amount,
                'pnl_percent': pnl_percent,
                'reason': f'부분 청산 (남은 수량: {remaining_size:.4f})'
            }
            
            await self.record_trade(trade_data)
            
            logger.info(
                f"부분 청산 기록: {symbol} {closed_size:.4f} @ {exit_price:.2f} "
                f"(PnL: {pnl_percent:+.2f}%)"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"부분 청산 기록 실패: {e}")
            return False
    
    async def get_position_history(self, position_id: str) -> List[Dict]:
        """포지션 거래 이력 조회"""
        try:
            async with self.get_async_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT * FROM trades 
                    WHERE position_id = ?
                    ORDER BY timestamp ASC
                """, (position_id,))
                
                rows = cursor.fetchall()
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"포지션 이력 조회 실패: {e}")
            return []
    
    async def save_system_event(self, event_type: str, level: str, 
                              title: str, message: str, data: Dict = None) -> bool:
        """시스템 이벤트 저장"""
        try:
            sql = """
                INSERT INTO system_events 
                (event_type, level, title, message, data)
                VALUES (?, ?, ?, ?, ?)
            """
            
            params = (
                event_type,
                level,
                title,
                message,
                json.dumps(data) if data else None
            )
            
            return await self.execute_async(sql, params, use_batch=True)
                
        except Exception as e:
            logger.error(f"시스템 이벤트 저장 실패: {e}")
            return False
    
    async def get_hourly_summary(self, hours: int = 1) -> Dict:
        """시간별 요약 조회"""
        try:
            async with self.get_async_connection() as conn:
                cursor = conn.cursor()
                
                since = datetime.now() - timedelta(hours=hours)
                
                # 거래 요약
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as win_trades,
                        SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as loss_trades,
                        SUM(pnl) as total_pnl,
                        AVG(pnl_percent) as avg_pnl_percent
                    FROM trades
                    WHERE timestamp >= ?
                """, (since,))
                
                trade_summary = dict(cursor.fetchone())
                
                # 이벤트 요약
                cursor.execute("""
                    SELECT event_type, level, COUNT(*) as count
                    FROM system_events
                    WHERE timestamp >= ?
                    GROUP BY event_type, level
                """, (since,))
                
                events = cursor.fetchall()
                event_summary = {row['event_type']: row['count'] for row in events}
                
                # 활성 포지션
                cursor.execute("""
                    SELECT symbol, side, size, entry_price
                    FROM positions
                    WHERE status = 'ACTIVE'
                """)
                
                active_positions = [dict(row) for row in cursor.fetchall()]
                
                return {
                    'period_hours': hours,
                    'trades': trade_summary,
                    'events': event_summary,
                    'active_positions': active_positions,
                    'timestamp': datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"시간별 요약 조회 실패: {e}")
            return {}
    
    async def get_system_stats(self) -> Dict:
        """시스템 통계 반환"""
        pool_stats = self.connection_pool.get_stats() if self.connection_pool else {}
        
        return {
            'database_path': self.db_path,
            'connection_pool': pool_stats,
            'query_stats': self.stats.copy(),
            'batch_config': self.batch_config.copy(),
            'batch_queue_size': len(self._batch_queue),
            'last_commit_time': self._last_commit,
            'is_batch_processing': self._is_running
        }
    
    async def cleanup(self):
        """정리 작업"""
        try:
            # 배치 처리 중지
            await self.stop()
            
            # 연결 풀 정리
            if self.connection_pool:
                self.connection_pool.close_all()
            
            logger.info("데이터베이스 매니저 정리 완료")
            
        except Exception as e:
            logger.error(f"데이터베이스 정리 실패: {e}")


# 싱글톤 인스턴스
_database_manager: Optional[DatabaseManager] = None

def get_database_manager(db_path: str = "data/trading_bot.db") -> DatabaseManager:
    """데이터베이스 매니저 싱글톤 반환"""
    global _database_manager
    if _database_manager is None:
        _database_manager = DatabaseManager(db_path)
    return _database_manager