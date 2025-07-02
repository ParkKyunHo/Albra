# src/core/position_manager.py
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict
import hashlib
import asyncio
import logging
from enum import Enum

logger = logging.getLogger(__name__)

class PositionStatus(Enum):
    """포지션 상태"""
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    MODIFIED = "MODIFIED"
    PAUSED = "PAUSED"
    ERROR = "ERROR"

class PositionSource(Enum):
    """포지션 소스"""
    AUTO = "AUTO"  # 자동 전략
    MANUAL = "MANUAL"  # 수동 거래
    IMPORTED = "IMPORTED"  # 외부 가져오기

class PositionError(Exception):
    """포지션 관련 에러"""
    pass

@dataclass
class Position:
    """포지션 정보 - 개선된 버전"""
    symbol: str
    side: str  # LONG/SHORT
    size: float
    entry_price: float
    leverage: int
    position_id: str  # 고유 ID
    is_manual: bool  # 수동 거래 여부
    strategy_name: Optional[str]  # 전략 이름 (자동인 경우)
    created_at: str
    last_updated: str
    initial_size: float  # 초기 포지션 크기
    status: str  # ACTIVE, CLOSED, MODIFIED
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    
    # 추가 메타데이터
    source: str = "AUTO"  # AUTO, MANUAL, IMPORTED
    partial_closes: int = 0  # 부분 청산 횟수
    total_pnl: float = 0.0  # 누적 손익
    fees_paid: float = 0.0  # 지불한 수수료
    avg_entry_price: float = 0.0  # 평균 진입가 (추가 매수 시)
    notes: str = ""  # 메모
    tags: List[str] = None  # 태그
    
    def __post_init__(self):
        """초기화 후 처리"""
        if self.tags is None:
            self.tags = []
        if self.avg_entry_price == 0.0:
            self.avg_entry_price = self.entry_price
    
    def to_dict(self) -> Dict:
        """딕셔너리 변환 - 개선된 버전"""
        data = asdict(self)
        # Enum 값들을 문자열로 변환
        # status가 이미 문자열인 경우와 Enum인 경우 모두 처리
        if hasattr(self.status, 'value'):
            data['status'] = self.status.value
        elif isinstance(self.status, str):
            data['status'] = self.status
        else:
            data['status'] = str(self.status)
            
        # source도 동일하게 처리
        if hasattr(self.source, 'value'):
            data['source'] = self.source.value
        elif isinstance(self.source, str):
            data['source'] = self.source
        else:
            data['source'] = str(self.source)
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Position':
        """딕셔너리에서 생성 - 에러 처리 강화"""
        try:
            # 필수 필드 검증
            required_fields = ['symbol', 'side', 'size', 'entry_price', 'position_id']
            for field in required_fields:
                if field not in data:
                    raise PositionError(f"필수 필드 누락: {field}")
            
            # 타입 변환
            if 'tags' in data and isinstance(data['tags'], str):
                try:
                    data['tags'] = json.loads(data['tags'])
                except json.JSONDecodeError:
                    data['tags'] = []
            
            return cls(**data)
        except Exception as e:
            logger.error(f"Position 생성 실패: {e}")
            raise PositionError(f"Position 생성 실패: {e}")
    
    def update_size(self, new_size: float, reason: str = ""):
        """포지션 크기 업데이트"""
        if new_size < 0:
            raise PositionError("포지션 크기는 음수일 수 없습니다")
        
        old_size = self.size
        self.size = new_size
        self.last_updated = datetime.now().isoformat()
        
        if new_size < old_size:
            self.partial_closes += 1
        
        logger.info(f"{self.symbol} 포지션 크기 변경: {old_size} → {new_size} ({reason})")
    
    def add_tag(self, tag: str):
        """태그 추가"""
        if tag not in self.tags:
            self.tags.append(tag)
            self.last_updated = datetime.now().isoformat()
    
    def remove_tag(self, tag: str):
        """태그 제거"""
        if tag in self.tags:
            self.tags.remove(tag)
            self.last_updated = datetime.now().isoformat()
    
    def get_unrealized_pnl(self, current_price: float) -> float:
        """미실현 손익 계산"""
        if self.side == 'LONG':
            return (current_price - self.entry_price) / self.entry_price * 100
        else:
            return (self.entry_price - current_price) / self.entry_price * 100
    
    def get_risk_reward_ratio(self) -> Optional[float]:
        """리스크/리워드 비율 계산"""
        if not self.stop_loss or not self.take_profit:
            return None
        
        if self.side == 'LONG':
            risk = abs(self.entry_price - self.stop_loss)
            reward = abs(self.take_profit - self.entry_price)
        else:
            risk = abs(self.stop_loss - self.entry_price)
            reward = abs(self.entry_price - self.take_profit)
        
        return reward / risk if risk > 0 else None

class PositionValidator:
    """포지션 검증 클래스"""
    
    @staticmethod
    def validate_position_data(data: Dict) -> Tuple[bool, List[str]]:
        """포지션 데이터 검증"""
        errors = []
        
        # 필수 필드 검증
        required_fields = ['symbol', 'side', 'size', 'entry_price', 'position_id']
        for field in required_fields:
            if field not in data or data[field] is None:
                errors.append(f"필수 필드 누락: {field}")
        
        # 데이터 타입 검증
        if 'size' in data:
            try:
                size = float(data['size'])
                if size <= 0:
                    errors.append("포지션 크기는 양수여야 합니다")
            except (ValueError, TypeError):
                errors.append("포지션 크기는 숫자여야 합니다")
        
        if 'entry_price' in data:
            try:
                price = float(data['entry_price'])
                if price <= 0:
                    errors.append("진입가는 양수여야 합니다")
            except (ValueError, TypeError):
                errors.append("진입가는 숫자여야 합니다")
        
        if 'side' in data:
            if data['side'] not in ['LONG', 'SHORT']:
                errors.append("포지션 방향은 LONG 또는 SHORT여야 합니다")
        
        if 'leverage' in data:
            try:
                leverage = int(data['leverage'])
                if leverage < 1 or leverage > 125:
                    errors.append("레버리지는 1-125 범위여야 합니다")
            except (ValueError, TypeError):
                errors.append("레버리지는 정수여야 합니다")
        
        return len(errors) == 0, errors

class PositionManager:
    """수동/자동 포지션 통합 관리 - 개선된 버전"""
    
    def __init__(self, binance_api, state_manager, notification_manager=None, database_manager=None, config_manager=None):
        self.binance_api = binance_api
        self.state_manager = state_manager
        self.notification_manager = notification_manager  # SmartNotificationManager
        self.db = database_manager
        self.config_manager = config_manager
        
        # 포지션 저장소 - 복합 키 구조로 변경
        # 기존: {symbol: Position}
        # 변경: {"symbol_strategy": Position}
        self.positions: Dict[str, Position] = {}
        
        # 전략별 포지션 빠른 조회를 위한 인덱스
        self.strategy_positions: Dict[str, List[str]] = {}  # {strategy_name: [position_keys]}
        
        # 동기화 락
        self._lock = asyncio.Lock()
        
        # 검증기
        self.validator = PositionValidator()
        
        # 설정 - config.yaml에서 로드
        if config_manager:
            sync_config = config_manager.config.get('position_sync', {})
            self.config = {
                'sync_on_start': True,
                'auto_sync_interval': sync_config.get('auto_sync_interval', 60),  # config.yaml 값 사용
                'max_position_age_days': 30,
                'enable_auto_cleanup': True,
                'batch_operation_size': 50
            }
        else:
            # 기본값 (60초로 변경)
            self.config = {
                'sync_on_start': True,
                'auto_sync_interval': 60,  # 60초로 변경
                'max_position_age_days': 30,
                'enable_auto_cleanup': True,
                'batch_operation_size': 50
            }
        
        # 통계
        self.stats = {
            'total_positions_created': 0,
            'total_positions_closed': 0,
            'sync_operations': 0,
            'errors': 0,
            'last_sync_time': None,
            'last_error_time': None,
            'position_changes_detected': 0,
            'partial_closes_detected': 0
        }
        
        # 시스템 포지션 ID 추적
        self.system_position_ids = set()
        # 시스템 포지션 상세 정보 (새로 추가)
        self.system_position_data = {}  # {position_id: {symbol, strategy, account, created_at, etc}}
        self._load_system_positions()
        
        # 이벤트 핸들러
        self._event_handlers = {
            'position_created': [],
            'position_updated': [],
            'position_closed': [],
            'position_modified': [],
            'sync_completed': []
        }
        
        # 캐시 무효화 플래그
        self._cache_invalidated = False
        
        logger.info("포지션 매니저 초기화 (개선된 버전)")
        
        # notification_manager 상태 로그 (디버깅 강화)
        if self.notification_manager:
            logger.info("✅ 알림 매니저 연결됨")
            logger.info(f"[DEBUG] notification_manager 타입: {type(self.notification_manager)}")
            logger.info(f"[DEBUG] send_alert 메서드 존재: {hasattr(self.notification_manager, 'send_alert')}")
        else:
            logger.warning("⚠️ 알림 매니저가 연결되지 않음 - 알림이 작동하지 않습니다")
    
    def _load_system_positions(self):
        """시스템 포지션 정보 로드 (개선된 버전)"""
        try:
            file_path = os.path.join('state', 'system_positions.json')
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    
                    # 기존 형식 호환성 유지
                    if 'position_ids' in data and isinstance(data['position_ids'], list):
                        # 구버전 형식
                        self.system_position_ids = set(data['position_ids'])
                        self.system_position_data = {}
                        logger.info(f"시스템 포지션 ID 로드 (구버전): {len(self.system_position_ids)}개")
                    elif 'positions' in data:
                        # 새 형식
                        self.system_position_data = data['positions']
                        self.system_position_ids = set(self.system_position_data.keys())
                        logger.info(f"시스템 포지션 정보 로드: {len(self.system_position_ids)}개")
                        
                        # 디버깅: 로드된 포지션 정보 출력
                        for pos_id, pos_info in self.system_position_data.items():
                            logger.debug(f"  - {pos_info.get('symbol')} ({pos_info.get('strategy')})")
        except Exception as e:
            logger.error(f"시스템 포지션 로드 실패: {e}")
            self.system_position_ids = set()
            self.system_position_data = {}
    
    def _save_system_positions(self):
        """시스템 포지션 정보 저장 (개선된 버전)"""
        try:
            os.makedirs('state', exist_ok=True)
            
            # 새 형식으로 저장
            save_data = {
                'positions': self.system_position_data,
                'version': '2.0',
                'last_updated': datetime.now().isoformat()
            }
            
            # 백업 생성
            file_path = os.path.join('state', 'system_positions.json')
            if os.path.exists(file_path):
                backup_path = f"{file_path}.backup"
                try:
                    with open(file_path, 'r') as f:
                        backup_data = f.read()
                    with open(backup_path, 'w') as f:
                        f.write(backup_data)
                except Exception:
                    pass
            
            # 저장
            with open(file_path, 'w') as f:
                json.dump(save_data, f, indent=2)
                
            logger.debug(f"시스템 포지션 정보 저장: {len(self.system_position_data)}개")
            
        except Exception as e:
            logger.error(f"시스템 포지션 저장 실패: {e}")
    
    def add_event_handler(self, event_type: str, handler):
        """이벤트 핸들러 추가"""
        if event_type in self._event_handlers:
            self._event_handlers[event_type].append(handler)
        else:
            logger.warning(f"알 수 없는 이벤트 타입: {event_type}")
    
    async def _emit_event(self, event_type: str, data: Dict):
        """이벤트 발생"""
        try:
            handlers = self._event_handlers.get(event_type, [])
            for handler in handlers:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
        except Exception as e:
            logger.error(f"이벤트 핸들러 실행 실패 ({event_type}): {e}")
    
    async def initialize(self) -> bool:
        """초기화 및 포지션 동기화 - 강화된 에러 처리"""
        try:
            logger.info("포지션 매니저 초기화 중...")
            
            # 1. 캐시된 포지션 로드 (에러 복구 포함)
            await self._load_cached_positions_with_recovery()
            
            # 1-1. 캐시 유효성 검증 (새로 추가)
            await self._validate_cache_freshness()
            
            # 2. 초기 동기화
            if self.config['sync_on_start']:
                sync_report = await self.sync_positions()
                
                # 동기화 결과 검증
                if not await self._validate_sync_result(sync_report):
                    logger.warning("동기화 결과 검증 실패")
                
                # 동기화 결과 알림 (초기화 시에는 생략 - 이미 _detect_new_positions에서 알림 전송됨)
                # if sync_report['new_manual'] or sync_report['modified']:
                #     await self._notify_sync_results(sync_report)
            
            # 3. 자동 정리 작업 스케줄링
            if self.config['enable_auto_cleanup']:
                asyncio.create_task(self._periodic_cleanup())
            
            logger.info("✅ 포지션 매니저 초기화 완료")
            return True
            
        except Exception as e:
            logger.error(f"포지션 매니저 초기화 실패: {e}")
            self.stats['errors'] += 1
            self.stats['last_error_time'] = datetime.now().isoformat()
            return False
    
    async def _load_cached_positions_with_recovery(self):
        """캐시된 포지션 로드 - 복구 기능 포함"""
        try:
            cached_data = await self.state_manager.load_position_cache()
            
            self.positions.clear()
            self.strategy_positions.clear()
            corrupted_positions = []
            
            for key, pos_data in cached_data.items():
                # 기존 데이터 마이그레이션: key가 심볼만 있는 경우
                if '_' not in key and isinstance(pos_data, dict) and 'symbol' in pos_data:
                    # 기존 형식: {symbol: position_data}
                    symbol = key
                    # 전략명 추출
                    strategy_name = pos_data.get('strategy_name', 'TFPE')  # 기본값 TFPE
                    if not strategy_name:
                        strategy_name = 'MANUAL' if pos_data.get('is_manual', False) else 'TFPE'
                    
                    # 새 키 생성
                    new_key = f"{symbol}_{strategy_name}"
                    pos_data['symbol'] = symbol  # symbol 필드 확실히 설정
                else:
                    # 이미 마이그레이션된 데이터
                    new_key = key
                try:
                    # 데이터 검증
                    is_valid, errors = self.validator.validate_position_data(pos_data)
                    if not is_valid:
                        logger.warning(f"포지션 데이터 오류 ({new_key}): {errors}")
                        corrupted_positions.append(new_key)
                        continue
                    
                    position = Position.from_dict(pos_data)
                    
                    # 만료된 포지션 체크
                    last_update = datetime.fromisoformat(position.last_updated)
                    age_days = (datetime.now() - last_update).days
                    
                    if age_days > self.config['max_position_age_days']:
                        logger.warning(f"만료된 포지션 제거: {position.symbol} (나이: {age_days}일)")
                        continue
                    
                    self.positions[new_key] = position
                    
                    # 전략별 인덱스 업데이트
                    strategy_key = position.strategy_name or 'MANUAL'
                    if strategy_key not in self.strategy_positions:
                        self.strategy_positions[strategy_key] = []
                    self.strategy_positions[strategy_key].append(new_key)
                    
                except Exception as e:
                    logger.error(f"포지션 로드 실패 ({new_key}): {e}")
                    corrupted_positions.append(new_key)
            
            # 손상된 포지션 복구 시도
            if corrupted_positions:
                await self._recover_corrupted_positions(corrupted_positions)
            
            logger.info(f"캐시된 포지션 로드: {len(self.positions)}개 (손상: {len(corrupted_positions)}개)")
            
        except Exception as e:
            logger.error(f"포지션 캐시 로드 실패: {e}")
            # 빈 포지션으로 시작
            self.positions.clear()
    
    async def _recover_corrupted_positions(self, corrupted_symbols: List[str]):
        """손상된 포지션 복구"""
        try:
            if not self.db:
                return
            
            logger.info(f"손상된 포지션 복구 시도: {corrupted_symbols}")
            
            # DB에서 최신 포지션 정보 조회
            for symbol in corrupted_symbols:
                try:
                    # DB 복구 로직 (실제 구현 시 추가)
                    pass
                except Exception as e:
                    logger.error(f"포지션 복구 실패 ({symbol}): {e}")
                    
        except Exception as e:
            logger.error(f"포지션 복구 프로세스 실패: {e}")
    
    async def _validate_cache_freshness(self):
        """캐시 유효성 검증 - 오래된 캐시 처리"""
        try:
            # 시스템 상태 파일 확인
            system_state = await self.state_manager.load_system_state()
            if system_state and 'shutdown_time' in system_state:
                shutdown_time = datetime.fromisoformat(system_state['shutdown_time'])
                time_since_shutdown = datetime.now() - shutdown_time
                
                # 시스템이 10분 이상 중지되어 있었다면 캐시를 신뢰할 수 없음
                if time_since_shutdown.total_seconds() > 600:  # 10분
                    logger.warning(f"시스템이 {time_since_shutdown.total_seconds()/60:.1f}분 동안 중지되어 있었습니다.")
                    logger.warning("포지션 캐시를 무시하고 거래소에서 직접 조회합니다.")
                    
                    # 모든 포지션에 'stale_cache' 태그 추가
                    for position in self.positions.values():
                        position.add_tag("stale_cache")
                        position.add_tag(f"shutdown_{shutdown_time.strftime('%Y%m%d_%H%M')}")
                    
                    # 캐시 무효화 플래그 설정
                    self._cache_invalidated = True
                else:
                    logger.info(f"시스템 중지 시간: {time_since_shutdown.total_seconds()/60:.1f}분 - 캐시 유효")
                    self._cache_invalidated = False
            else:
                # 시스템 상태를 알 수 없으면 캐시 무효화
                logger.warning("시스템 상태를 확인할 수 없습니다. 포지션 캐시를 무시합니다.")
                self._cache_invalidated = True
                
        except Exception as e:
            logger.error(f"캐시 유효성 검증 실패: {e}")
            # 안전을 위해 캐시 무효화
            self._cache_invalidated = True
    
    async def _validate_sync_result(self, sync_report: Dict) -> bool:
        """동기화 결과 검증"""
        try:
            # 기본 검증
            if 'errors' in sync_report and sync_report['errors']:
                logger.warning(f"동기화 에러: {sync_report['errors']}")
                return False
            
            # 포지션 수 일관성 체크
            active_count = len([p for p in self.positions.values() if p.status == PositionStatus.ACTIVE.value])
            exchange_positions = await self.binance_api.get_positions()
            exchange_count = len(exchange_positions)
            
            if abs(active_count - exchange_count) > 2:  # 2개 이상 차이
                logger.warning(f"포지션 수 불일치: 시스템={active_count}, 거래소={exchange_count}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"동기화 결과 검증 실패: {e}")
            return False
    
    async def _notify_sync_results(self, sync_report: Dict):
        """동기화 결과 알림"""
        if not self.notification_manager:
            return
            
        try:
            # 새로운 수동 포지션 알림
            if sync_report['new_manual']:
                for symbol in sync_report['new_manual']:
                    position = self.positions.get(symbol)
                    if position:
                        await self.notification_manager.send_alert(
                            event_type='USER_INTERVENTION',
                            title=f'🔔 새로운 수동 포지션 감지',
                            message=(
                                f"<b>심볼:</b> {position.symbol}\n"
                                f"<b>방향:</b> {position.side}\n"
                                f"<b>수량:</b> {position.size:.4f}\n"
                                f"<b>진입가:</b> ${position.entry_price:.2f}\n"
                                f"<b>레버리지:</b> {position.leverage}x"
                            ),
                            data={
                                'symbol': symbol,
                                'side': position.side,
                                'size': position.size,
                                'entry_price': position.entry_price
                            }
                        )
            
            # 수정된 포지션 알림
            if sync_report['modified']:
                for symbol in sync_report['modified']:
                    position = self.positions.get(symbol)
                    if position:
                        await self.notification_manager.send_alert(
                            event_type='POSITION_MODIFIED',
                            title=f'✏️ 포지션 수동 변경 감지',
                            message=(
                                f"<b>심볼:</b> {position.symbol}\n"
                                f"시스템 포지션이 수동으로 변경되었습니다.\n"
                                f"자동 거래가 일시 중지될 수 있습니다."
                            ),
                            data={'symbol': symbol}
                        )
        except Exception as e:
            logger.error(f"동기화 결과 알림 실패: {e}")
    
    async def sync_positions(self) -> Dict[str, List]:
        """바이낸스 실제 포지션과 시스템 포지션 동기화 - 강화된 버전"""
        async with self._lock:
            sync_report = {
                'new_manual': [],
                'closed': [],
                'modified': [],
                'size_changed': [],
                'partial_closed': [],
                'active': [],
                'errors': [],
                'warnings': [],
                'sync_time': datetime.now().isoformat()
            }
            
            try:
                start_time = datetime.now()
                self.stats['sync_operations'] += 1
                logger.info(f"포지션 동기화 시작 - 현재 시간: {start_time.strftime('%H:%M:%S')}")
                
                # 1. 바이낸스에서 현재 포지션 조회 (재시도 포함)
                exchange_positions = await self._get_exchange_positions_with_retry()
                if exchange_positions is None:
                    sync_report['errors'].append("거래소 포지션 조회 실패")
                    return sync_report
                
                exchange_dict = {pos['symbol']: pos for pos in exchange_positions}
                
                # 2. 새로운 수동 포지션 감지 (배치 처리)
                new_positions = await self._detect_new_positions(exchange_dict, sync_report)
                
                # 3. 기존 포지션 변경사항 체크 (병렬 처리)
                await self._check_position_changes(exchange_dict, sync_report)
                
                # 4. 청산된 포지션 처리
                await self._handle_closed_positions(exchange_dict, sync_report)
                
                # 5. 상태 저장 (배치)
                await self._save_positions_batch()
                
                # 6. 통계 업데이트
                sync_duration = (datetime.now() - start_time).total_seconds()
                self.stats['last_sync_time'] = sync_report['sync_time']
                self.stats['position_changes_detected'] += len(sync_report['size_changed'])
                self.stats['partial_closes_detected'] += len(sync_report['partial_closed'])
                
                logger.info(f"포지션 동기화 완료 ({sync_duration:.2f}초): "
                          f"신규={len(sync_report['new_manual'])}, "
                          f"변경={len(sync_report['size_changed'])}, "
                          f"청산={len(sync_report['closed'])}")
                
                # 이벤트 발생
                await self._emit_event('sync_completed', sync_report)
                
                return sync_report
                
            except Exception as e:
                error_msg = f"포지션 동기화 실패: {e}"
                logger.error(error_msg)
                sync_report['errors'].append(error_msg)
                
                self.stats['errors'] += 1
                self.stats['last_error_time'] = datetime.now().isoformat()
                
                return sync_report
    
    async def _get_exchange_positions_with_retry(self, max_retries: int = 3) -> Optional[List[Dict]]:
        """거래소 포지션 조회 - 재시도 포함"""
        for attempt in range(max_retries):
            try:
                return await self.binance_api.get_positions()
            except Exception as e:
                logger.warning(f"포지션 조회 재시도 {attempt + 1}/{max_retries}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # 지수 백오프
        
        logger.error("모든 재시도 실패")
        return None
    
    def _convert_binance_side(self, exchange_position: Dict) -> str:
        """바이낸스 포지션 데이터에서 side 변환
        
        One-way Mode: positionAmt의 부호로 판단
        Hedge Mode: positionSide 필드 사용
        """
        # 원본 positionAmt 보존 (이미 abs 처리된 값이 들어올 수 있음)
        # 바이낸스 API에서 받은 원본 데이터 확인
        position_amt = float(exchange_position.get('positionAmt', 0))
        position_side = exchange_position.get('positionSide', 'BOTH')
        
        # 로그로 현재 데이터 확인
        logger.debug(f"_convert_binance_side: symbol={exchange_position.get('symbol')}, positionAmt={position_amt}, positionSide={position_side}")
        
        # Hedge Mode인 경우 positionSide 사용
        if position_side in ['LONG', 'SHORT']:
            return position_side
        
        # One-way Mode인 경우 positionAmt의 부호로 판단
        # 주의: positionAmt가 이미 abs() 처리되어 있을 수 있음
        if position_amt > 0:
            return 'LONG'
        elif position_amt < 0:
            return 'SHORT'
        else:
            # 포지션이 없는 경우 또는 판단 불가
            logger.warning(f"포지션 방향 판단 불가: symbol={exchange_position.get('symbol')}, amt={position_amt}, side={position_side}")
            return 'LONG'  # 기본값
    
    async def _is_system_position_improved(self, symbol: str, side: str, size: float, 
                                         entry_price: float, position_id: str) -> bool:
        """시스템 포지션인지 확인 - 개선된 매칭 로직 (시간 제한 없음)
        
        1. system_position_data에서 정확한 정보 확인
        2. 캐시된 포지션에서 전략명이 있는 포지션 확인
        3. 유사 포지션 매칭 (가격/크기 유사성)
        """
        # 1. system_position_data에서 확인 (가장 정확한 방법)
        if position_id in self.system_position_data:
            pos_data = self.system_position_data[position_id]
            logger.info(f"{symbol} 시스템 포지션 데이터 매칭: {pos_data.get('strategy')}")
            return True
        
        # 2. 시스템 포지션 ID 확인 (레거시 호환)
        if position_id in self.system_position_ids:
            logger.debug(f"{symbol} 시스템 포지션 ID 매칭")
            return True
        
        # 3. 캐시된 포지션에서 확인 - 전략명이 있으면 시스템 포지션
        for key, existing_pos in self.positions.items():
            if (existing_pos.symbol == symbol and
                existing_pos.side == side and
                existing_pos.status == PositionStatus.ACTIVE.value):
                
                # 전략명이 있으면 무조건 시스템 포지션
                if existing_pos.strategy_name is not None and not existing_pos.is_manual:
                    # 가격과 크기 유사성 체크 (슬리피지 허용)
                    price_diff_pct = abs(existing_pos.entry_price - entry_price) / existing_pos.entry_price
                    size_diff_pct = abs(existing_pos.size - size) / existing_pos.size if existing_pos.size > 0 else 1.0
                    
                    if price_diff_pct < 0.005 and size_diff_pct < 0.001:  # 0.5% 가격차, 0.1% 크기차
                        logger.info(f"{symbol} 시스템 포지션 매칭 (전략: {existing_pos.strategy_name}): "
                                  f"가격차={price_diff_pct*100:.3f}%, 크기차={size_diff_pct*100:.3f}%")
                        
                        # 매칭된 포지션 저장
                        self._matched_system_position = existing_pos
                        
                        # 새 포지션 ID를 시스템 포지션에 추가
                        self.system_position_data[position_id] = {
                            'symbol': symbol,
                            'strategy': existing_pos.strategy_name,
                            'account': getattr(self, 'account_name', 'MASTER'),
                            'created_at': existing_pos.created_at,
                            'entry_price': entry_price,
                            'side': side,
                            'matched_from': key  # 어떤 포지션에서 매칭되었는지
                        }
                        self.system_position_ids.add(position_id)
                        self._save_system_positions()
                        
                        return True
                    else:
                        logger.debug(f"{symbol} 가격/크기 차이로 매칭 실패: "
                                   f"가격차={price_diff_pct*100:.3f}%, 크기차={size_diff_pct*100:.3f}%")
        
        # 4. 매칭 실패 - 수동 포지션으로 처리
        logger.debug(f"{symbol} 시스템 포지션 매칭 실패 - 수동 포지션으로 처리")
        return False
    
    async def _detect_new_positions(self, exchange_dict: Dict, sync_report: Dict) -> List[Position]:
        """새로운 포지션 감지 - 배치 처리 (알림 추가)"""
        new_positions = []
        
        for symbol, ex_pos in exchange_dict.items():
            # 캐시가 무효화되었거나 포지션이 없는 경우
            # 복합 키 구조를 감안하여 심볼로 포지션 찾기
            existing_position = None
            for key, pos in self.positions.items():
                if pos.symbol == symbol and pos.status == PositionStatus.ACTIVE.value:
                    existing_position = pos
                    break
            
            is_new_position = existing_position is None
            
            # 캐시가 무효화되고 'stale_cache' 태그가 있는 경우도 새 포지션으로 처리
            if not is_new_position and self._cache_invalidated:
                existing_pos = self.positions.get(symbol)
                if existing_pos and 'stale_cache' in existing_pos.tags:
                    logger.info(f"{symbol} 포지션은 오래된 캐시에서 로드됨. 새 포지션으로 처리합니다.")
                    is_new_position = True
                    # 기존 포지션 제거
                    del self.positions[symbol]
            
            if is_new_position:
                try:
                    # 바이낸스 side 값을 올바르게 변환
                    position_side = self._convert_binance_side(ex_pos)
                    
                    # 포지션 ID 생성
                    position_id = self._generate_position_id(
                        symbol, position_side, ex_pos['entryPrice']
                    )
                    
                    # 시스템 포지션인지 확인 - 개선된 매칭 로직
                    is_system = await self._is_system_position_improved(
                        symbol, position_side, 
                        abs(float(ex_pos['positionAmt'])), 
                        float(ex_pos['entryPrice']),
                        position_id
                    )
                    
                    # 시스템 포지션이 매칭되었고 기존 포지션이 있으면 업데이트
                    if is_system and hasattr(self, '_matched_system_position') and self._matched_system_position:
                        # 기존 시스템 포지션 업데이트
                        matched_pos = self._matched_system_position
                        old_price = matched_pos.entry_price
                        old_size = matched_pos.size
                        
                        # 실제 체결 정보로 업데이트
                        matched_pos.entry_price = float(ex_pos['entryPrice'])
                        matched_pos.size = abs(float(ex_pos['positionAmt']))
                        matched_pos.last_updated = datetime.now().isoformat()
                        
                        logger.info(f"시스템 포지션 정보 업데이트: {symbol} "
                                  f"가격: {old_price:.2f} → {matched_pos.entry_price:.2f}, "
                                  f"수량: {old_size:.4f} → {matched_pos.size:.4f}")
                        
                        # 매칭 완료 후 참조 제거
                        self._matched_system_position = None
                        
                        # 이미 등록된 포지션이므로 new_positions에 추가하지 않음
                        continue
                    
                    # 새로운 포지션 발견
                    # 시스템 포지션인 경우 전략명 파악
                    detected_strategy_name = None
                    if is_system:
                        # 현재 활성 전략들을 확인하여 어떤 전략의 포지션인지 파악
                        # TODO: 더 정교한 로직 필요 (예: 진입 시간, 크기 등으로 판단)
                        detected_strategy_name = 'TFPE'  # 기본값
                    
                    new_position = Position(
                        symbol=symbol,
                        side=position_side,  # 변환된 side 사용
                        size=abs(float(ex_pos['positionAmt'])),  # 절대값 사용
                        entry_price=float(ex_pos['entryPrice']),
                        leverage=int(ex_pos['leverage']),
                        position_id=position_id,
                        is_manual=not is_system,  # 시스템 포지션이 아니면 수동
                        strategy_name=detected_strategy_name,
                        created_at=datetime.now().isoformat(),
                        last_updated=datetime.now().isoformat(),
                        initial_size=abs(float(ex_pos['positionAmt'])),
                        status=PositionStatus.ACTIVE.value,
                        source=PositionSource.AUTO.value if is_system else PositionSource.MANUAL.value
                    )
                    
                    # 복합 키로 저장
                    if detected_strategy_name:
                        key = f"{symbol}_{detected_strategy_name}"
                    else:
                        key = f"{symbol}_MANUAL"  # 수동 포지션
                    
                    self.positions[key] = new_position
                    
                    # 전략별 인덱스 업데이트
                    strategy_key = detected_strategy_name or "MANUAL"
                    if strategy_key not in self.strategy_positions:
                        self.strategy_positions[strategy_key] = []
                    self.strategy_positions[strategy_key].append(key)
                    
                    # 태그 추가
                    if not is_system:
                        new_position.add_tag("manual_detected")
                        new_position.add_tag(f"detected_{datetime.now().strftime('%Y%m%d')}")
                        sync_report['new_manual'].append(symbol)
                    else:
                        new_position.add_tag("system_recovered")
                        logger.info(f"시스템 포지션 복구: {symbol}")
                    
                    new_positions.append(new_position)
                    
                    # 통계 업데이트
                    self.stats['total_positions_created'] += 1
                    
                    # DB에 저장
                    if self.db:
                        await self.db.save_position(new_position.to_dict())
                    
                    # 이벤트 발생
                    await self._emit_event('position_created', {
                        'symbol': symbol,
                        'position': new_position.to_dict(),
                        'reason': 'manual_detected'
                    })
                    
                    log_msg = f"포지션 감지: {symbol} {position_side} {abs(float(ex_pos['positionAmt'])):.4f}"
                    if is_system:
                        log_msg += " (시스템)"
                    else:
                        log_msg += " (수동)"
                    logger.info(log_msg)
                    
                    # 알림 전송 - 수동 포지션만
                    if not is_system and self.notification_manager:
                        # 이벤트 ID 생성: "심볼_포지션ID_new"
                        event_id = f"{symbol}_{new_position.position_id}_new"
                        
                        await self.notification_manager.send_alert(
                            event_type='USER_INTERVENTION',
                            title=f'🔔 새로운 수동 포지션 감지',
                            message=(
                                f"<b>심볼:</b> {symbol}\n"
                                f"<b>방향:</b> {position_side}\n"
                                f"<b>수량:</b> {abs(float(ex_pos['positionAmt'])):.4f}\n"
                                f"<b>진입가:</b> ${float(ex_pos['entryPrice']):.2f}\n"
                                f"<b>레버리지:</b> {ex_pos['leverage']}x\n\n"
                                f"수동으로 생성된 포지션이 감지되었습니다."
                            ),
                            data={
                                'symbol': symbol,
                                'side': position_side,
                                'size': abs(float(ex_pos['positionAmt'])),
                                'entry_price': float(ex_pos['entryPrice']),
                                'leverage': int(ex_pos['leverage'])
                            },
                            event_id=event_id
                        )
                    else:
                        logger.warning(f"알림 매니저가 없어 수동 포지션 감지 알림을 보낼 수 없습니다")
                    
                except Exception as e:
                    logger.error(f"새 포지션 생성 실패 ({symbol}): {e}")
                    sync_report['errors'].append(f"새 포지션 생성 실패 ({symbol}): {e}")
        
        return new_positions
    
    async def _check_position_changes(self, exchange_dict: Dict, sync_report: Dict):
        """포지션 변경사항 체크 - 병렬 처리"""
        
        # 활성 포지션들을 배치로 처리
        active_positions = [
            (key, pos) for key, pos in self.positions.items() 
            if pos.status == PositionStatus.ACTIVE.value
        ]
        
        # 병렬 처리를 위한 태스크 생성
        tasks = []
        for key, sys_pos in active_positions:
            # 심볼을 추출하여 거래소 데이터와 비교
            symbol = sys_pos.symbol
            if symbol in exchange_dict:
                task = self._check_single_position_change(
                    symbol, sys_pos, exchange_dict[symbol], sync_report
                )
                tasks.append(task)
        
        # 병렬 실행
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _check_single_position_change(self, symbol: str, sys_pos: Position, 
                                          ex_pos: Dict, sync_report: Dict):
        """단일 포지션 변경 체크"""
        try:
            # 포지션 방향 변경 감지 (새로 추가)
            ex_pos_side = self._convert_binance_side(ex_pos)
            if ex_pos_side != sys_pos.side:
                # 방향이 바뀌었으면 기존 포지션은 청산된 것으로 처리
                logger.warning(f"{symbol} 포지션 방향 변경 감지: {sys_pos.side} → {ex_pos_side}")
                
                # 1. 기존 포지션을 청산으로 처리
                sys_pos.status = PositionStatus.CLOSED.value
                sys_pos.last_updated = datetime.now().isoformat()
                sync_report['closed'].append(symbol)
                
                # 2. 기존 포지션 청산 알림
                if self.notification_manager:
                    await self.notification_manager.send_alert(
                        event_type='MANUAL_POSITION_CLOSED',
                        title=f"🔴 {symbol} 포지션 청산 (방향 변경)",
                        message=(
                            f"<b>이전 방향:</b> {sys_pos.side}\n"
                            f"<b>진입가:</b> ${sys_pos.entry_price:.2f}\n"
                            f"<b>수량:</b> {sys_pos.size:.4f}\n\n"
                            f"포지션 방향이 변경되어 기존 포지션은 청산 처리됩니다."
                        ),
                        data={'symbol': symbol, 'old_side': sys_pos.side, 'new_side': ex_pos_side}
                    )
                
                # 3. 새 포지션을 완전히 새로운 포지션으로 생성
                del self.positions[symbol]  # 기존 포지션 제거
                
                # 4. 다음 sync 사이클에서 새 포지션으로 감지되도록 함
                logger.info(f"{symbol} 포지션이 제거되어 다음 사이클에서 새 포지션으로 감지됩니다")
                return  # 더 이상 체크하지 않음
            
            # 포지션 크기 변경 감지
            ex_pos_size = abs(float(ex_pos['positionAmt']))
            if abs(ex_pos_size - sys_pos.size) > 0.0001:
                await self._handle_size_change(symbol, sys_pos, ex_pos, sync_report)
            
            # 레버리지 변경 감지
            ex_leverage = int(ex_pos['leverage'])
            if ex_leverage != sys_pos.leverage:
                old_leverage = sys_pos.leverage
                sys_pos.leverage = ex_leverage
                sys_pos.last_updated = datetime.now().isoformat()
                
                logger.info(f"{symbol} 레버리지 변경: {old_leverage}x → {ex_leverage}x")
            
            # 평균 진입가 업데이트
            ex_entry_price = float(ex_pos['entryPrice'])
            if abs(ex_entry_price - sys_pos.entry_price) > 0.01:
                old_price = sys_pos.entry_price
                sys_pos.entry_price = ex_entry_price
                sys_pos.avg_entry_price = ex_entry_price
                sys_pos.last_updated = datetime.now().isoformat()
                
                logger.info(f"{symbol} 평균 진입가 업데이트: {old_price} → {ex_entry_price}")
            
            sync_report['active'].append(symbol)
            
            # DB 업데이트
            if self.db:
                await self.db.save_position(sys_pos.to_dict())
                
        except Exception as e:
            logger.error(f"포지션 변경 체크 실패 ({symbol}): {e}")
            sync_report['errors'].append(f"포지션 변경 체크 실패 ({symbol}): {e}")
    
    async def _handle_size_change(self, symbol: str, sys_pos: Position, 
                                ex_pos: Dict, sync_report: Dict):
        """포지션 크기 변경 처리 (알림 추가)"""
        old_size = sys_pos.size
        new_size = abs(float(ex_pos['positionAmt']))
        size_change_ratio = abs(new_size - old_size) / old_size
        
        # 포지션 크기 업데이트
        sys_pos.update_size(new_size, f"거래소 동기화 ({size_change_ratio*100:.1f}% 변화)")
        
        # 부분 청산 감지 및 기록
        if new_size < old_size:
            await self._record_partial_close(symbol, sys_pos, old_size, new_size, sync_report)
        
        # 크기 변경 기록
        change_data = {
            'symbol': symbol,
            'old_size': old_size,
            'new_size': new_size,
            'change_ratio': size_change_ratio,
            'is_manual': sys_pos.is_manual,
            'timestamp': datetime.now().isoformat()
        }
        
        sync_report['size_changed'].append(change_data)
        
        # 포지션 변경 알림 (시스템/수동 모두)
        if size_change_ratio > 0.05:  # 5% 이상 변경 시 알림
            # 시스템 포지션 수동 변경
            if not sys_pos.is_manual and size_change_ratio > 0.1:  # 10% 이상
                sys_pos.status = PositionStatus.MODIFIED.value
                sys_pos.add_tag("manually_modified")
                sync_report['modified'].append(symbol)
            
            # 알림 전송 (시스템/수동 모두)
            if self.notification_manager:
                # 포지션 타입에 따른 이벤트 타입 결정
                if sys_pos.is_manual:
                    # 수동 포지션
                    if new_size > old_size:
                        event_type = 'POSITION_SIZE_CHANGED'  # MEDIUM
                        title = '📈 수동 포지션 증가'
                        action_msg = '포지션이 추가되었습니다.'
                    else:
                        event_type = 'PARTIAL_CLOSE'  # HIGH
                        title = '✂️ 수동 포지션 부분 청산'
                        action_msg = '포지션이 부분 청산되었습니다.'
                else:
                    # 시스템 포지션
                    event_type = 'POSITION_PAUSED' if new_size > old_size else 'POSITION_MODIFIED'
                    title = '⚠️ 시스템 포지션 수동 변경' if new_size > old_size else '✏️ 포지션 크기 변경'
                    action_msg = '자동 거래가 일시 중지될 수 있습니다.' if new_size > old_size else '부분 청산이 감지되었습니다.'
                
                # 이벤트 ID로 중복 방지
                event_id = f"{symbol}_size_{old_size}_{new_size}_{datetime.now().timestamp()}"
                
                await self.notification_manager.send_alert(
                    event_type=event_type,
                    title=title,
                    message=(
                        f"<b>심볼:</b> {symbol}\n"
                        f"<b>이전 크기:</b> {old_size:.4f}\n"
                        f"<b>현재 크기:</b> {new_size:.4f}\n"
                        f"<b>변경률:</b> {size_change_ratio*100:.1f}%\n\n"
                        f"{action_msg}"
                    ),
                    data=change_data,
                    event_id=event_id
                )
        
        # 이벤트 발생
        await self._emit_event('position_updated', {
            'symbol': symbol,
            'change_type': 'size_change',
            'change_data': change_data
        })
        
        logger.info(f"포지션 변경 감지: {symbol} {old_size} → {new_size} ({size_change_ratio*100:.1f}% 변화)")
    
    async def _record_partial_close(self, symbol: str, position: Position, 
                                  old_size: float, new_size: float, sync_report: Dict):
        """부분 청산 기록"""
        try:
            closed_size = old_size - new_size
            current_price = await self.binance_api.get_current_price(symbol)
            
            if current_price and self.db:
                await self.db.record_partial_close(
                    position_id=position.position_id,
                    symbol=symbol,
                    closed_size=closed_size,
                    remaining_size=new_size,
                    exit_price=current_price,
                    entry_price=position.entry_price,
                    side=position.side
                )
            
            # 부분 청산 정보 추가
            partial_close_data = {
                'symbol': symbol,
                'closed_size': closed_size,
                'remaining_size': new_size,
                'exit_price': current_price,
                'timestamp': datetime.now().isoformat()
            }
            
            sync_report['partial_closed'].append(partial_close_data)
            
            # 알림 전송 (notification_manager 사용)
            if self.notification_manager:
                # 이벤트 ID 생성: "심볼_partial_남은크기_타임스탬프"
                event_id = f"{symbol}_partial_{new_size}_{datetime.now().timestamp()}"
                
                await self.notification_manager.send_alert(
                    event_type='PARTIAL_CLOSE',
                    title=f"✂️ {symbol} 부분 청산",
                    message=(
                        f"<b>청산 수량:</b> {closed_size:.4f}\n"
                        f"<b>남은 수량:</b> {new_size:.4f}\n"
                        f"<b>청산가:</b> ${current_price:.2f}"
                    ),
                    data=partial_close_data,
                    event_id=event_id
                )
            
            logger.info(f"부분 청산 기록: {symbol} {closed_size:.4f} @ {current_price:.2f}")
            
        except Exception as e:
            logger.error(f"부분 청산 기록 실패 ({symbol}): {e}")
    
    async def _handle_closed_positions(self, exchange_dict: Dict, sync_report: Dict):
        """청산된 포지션 처리"""
        closed_keys = []
        
        for key, sys_pos in list(self.positions.items()):
            # 활성 포지션이고 거래소에 없는 경우
            if sys_pos.status == PositionStatus.ACTIVE.value and sys_pos.symbol not in exchange_dict:
                closed_keys.append(key)
        
        # 배치로 청산 처리
        for key in closed_keys:
            try:
                sys_pos = self.positions[key]
                symbol = sys_pos.symbol
                sys_pos.status = PositionStatus.CLOSED.value
                sys_pos.last_updated = datetime.now().isoformat()
                
                sync_report['closed'].append(symbol)
                self.stats['total_positions_closed'] += 1
                
                # 완전 청산 기록
                if self.db:
                    current_price = await self.binance_api.get_current_price(symbol)
                    if current_price:
                        await self.db.record_trade({
                            'position_id': sys_pos.position_id,
                            'symbol': symbol,
                            'action': 'CLOSE',
                            'size': sys_pos.size,
                            'price': current_price,
                            'reason': '포지션 청산 감지'
                        })
                
                # 청산 알림 - 모든 포지션에 대해 전송
                if self.notification_manager:
                    # 이벤트 ID 생성: "심볼_closed_포지션ID"
                    event_id = f"{symbol}_closed_{sys_pos.position_id}"
                    
                    # 수동/시스템 포지션 구분하여 다른 이벤트 타입 사용
                    if sys_pos.is_manual:
                        event_type = 'MANUAL_POSITION_CLOSED'
                        title = f"🔴 {symbol} 수동 포지션 청산"
                        description = "수동 포지션이 완전히 청산되었습니다."
                    else:
                        event_type = 'POSITION_CLOSED'
                        title = f"🔵 {symbol} 시스템 포지션 청산"
                        description = f"시스템 포지션이 청산되었습니다. (전략: {sys_pos.strategy_name or 'Unknown'})"
                    
                    # 현재가 조회 시도
                    current_price = None
                    try:
                        current_price = await self.binance_api.get_current_price(symbol)
                    except Exception:
                        pass
                    
                    # PnL 계산 (가능한 경우)
                    pnl_text = ""
                    if current_price:
                        if sys_pos.side == 'LONG':
                            pnl_pct = (current_price - sys_pos.entry_price) / sys_pos.entry_price * 100
                        else:
                            pnl_pct = (sys_pos.entry_price - current_price) / sys_pos.entry_price * 100
                        pnl_pct *= sys_pos.leverage
                        pnl_emoji = '🟢' if pnl_pct >= 0 else '🔴'
                        pnl_text = f"<b>손익:</b> {pnl_emoji} {pnl_pct:+.2f}%\n"
                    
                    await self.notification_manager.send_alert(
                        event_type=event_type,
                        title=title,
                        message=(
                            f"<b>방향:</b> {sys_pos.side}\n"
                            f"<b>진입가:</b> ${sys_pos.entry_price:.2f}\n"
                            f"<b>수량:</b> {sys_pos.size:.4f}\n"
                            f"{pnl_text}"
                            f"\n{description}"
                        ),
                        data={
                            'symbol': symbol,
                            'side': sys_pos.side,
                            'entry_price': sys_pos.entry_price,
                            'size': sys_pos.size,
                            'strategy': sys_pos.strategy_name,
                            'is_manual': sys_pos.is_manual,
                            'current_price': current_price
                        },
                        event_id=event_id
                    )
                
                # 이벤트 발생
                await self._emit_event('position_closed', {
                    'symbol': symbol,
                    'position': sys_pos.to_dict(),
                    'reason': 'detected_closure'
                })
                
                logger.info(f"포지션 청산 감지: {symbol}")
                
            except Exception as e:
                logger.error(f"청산 포지션 처리 실패 ({symbol}): {e}")
                sync_report['errors'].append(f"청산 포지션 처리 실패 ({symbol}): {e}")
    
    async def _save_positions_batch(self):
        """포지션 배치 저장"""
        try:
            # 복합 키 구조 그대로 저장
            positions_dict = {
                key: position.to_dict() 
                for key, position in self.positions.items()
            }
            
            await self.state_manager.save_position_cache(positions_dict)
            
        except Exception as e:
            logger.error(f"포지션 배치 저장 실패: {e}")
    
    async def _periodic_cleanup(self):
        """주기적 정리 작업"""
        while True:
            try:
                await asyncio.sleep(3600)  # 1시간마다
                
                # 오래된 청산 포지션 제거
                await self._cleanup_old_positions()
                
                # 메모리 최적화
                await self._optimize_memory()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"주기적 정리 작업 실패: {e}")
    
    async def _cleanup_old_positions(self):
        """오래된 포지션 정리"""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.config['max_position_age_days'])
            removed_count = 0
            
            for symbol in list(self.positions.keys()):
                position = self.positions[symbol]
                
                if position.status == PositionStatus.CLOSED.value:
                    last_update = datetime.fromisoformat(position.last_updated)
                    
                    if last_update < cutoff_date:
                        del self.positions[symbol]
                        removed_count += 1
            
            if removed_count > 0:
                logger.info(f"오래된 포지션 {removed_count}개 정리 완료")
                await self._save_positions_batch()
                
        except Exception as e:
            logger.error(f"포지션 정리 실패: {e}")
    
    async def _optimize_memory(self):
        """메모리 최적화"""
        try:
            # 큰 태그 목록 정리
            for position in self.positions.values():
                if len(position.tags) > 20:  # 태그가 너무 많으면 정리
                    position.tags = position.tags[-10:]  # 최근 10개만 유지
            
        except Exception as e:
            logger.error(f"메모리 최적화 실패: {e}")
    
    def _generate_position_id(self, symbol: str, side: str, entry_price: float) -> str:
        """포지션 고유 ID 생성 - 개선된 버전"""
        timestamp = datetime.now().isoformat()
        data = f"{symbol}{side}{entry_price}{timestamp}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]  # 16자리로 단축
    
    # 기존 메서드들도 에러 처리 강화 (add_position, remove_position 등)
    async def add_position(self, symbol: str, side: str, size: float, 
                          entry_price: float, leverage: int, 
                          strategy_name: str, stop_loss: Optional[float] = None,
                          take_profit: Optional[float] = None) -> Position:
        """자동 전략에 의한 포지션 추가 - 강화된 버전"""
        async with self._lock:
            try:
                # 포지션 ID 생성 시 현재 시간 고정
                creation_time = datetime.now().isoformat()
                
                # 입력 검증
                position_data = {
                    'symbol': symbol,
                    'side': side.upper(),
                    'size': size,
                    'entry_price': entry_price,
                    'leverage': leverage,
                    'position_id': self._generate_position_id(symbol, side, entry_price)
                }
                
                is_valid, errors = self.validator.validate_position_data(position_data)
                if not is_valid:
                    raise PositionError(f"포지션 데이터 검증 실패: {errors}")
                
                # 중복 확인 - 전략별로 확인
                key = f"{symbol}_{strategy_name}"
                if key in self.positions and self.positions[key].status == PositionStatus.ACTIVE.value:
                    raise PositionError(f"이미 활성 포지션이 존재합니다: {symbol} ({strategy_name})")
                
                # 기존 호환성을 위해 다른 전략의 활성 포지션도 확인
                existing_position = self.get_position(symbol)  # 전략명 없이 호출
                if existing_position and existing_position.status == PositionStatus.ACTIVE.value:
                    logger.warning(f"{symbol}에 다른 전략({existing_position.strategy_name})의 포지션이 있습니다")
                
                position = Position(
                    symbol=symbol,
                    side=side.upper(),
                    size=size,
                    entry_price=entry_price,
                    leverage=leverage,
                    position_id=position_data['position_id'],
                    is_manual=False,
                    strategy_name=strategy_name,
                    created_at=creation_time,  # 고정된 시간 사용
                    last_updated=creation_time,  # 고정된 시간 사용
                    initial_size=size,
                    status=PositionStatus.ACTIVE.value,
                    source=PositionSource.AUTO.value,
                    stop_loss=stop_loss,
                    take_profit=take_profit
                )
                
                # 전략 태그 추가
                position.add_tag(f"strategy_{strategy_name.lower()}")
                position.add_tag(f"created_{datetime.now().strftime('%Y%m%d')}")
                
                # 복합 키로 저장
                self.positions[key] = position
                
                # 전략별 인덱스 업데이트
                if strategy_name not in self.strategy_positions:
                    self.strategy_positions[strategy_name] = []
                self.strategy_positions[strategy_name].append(key)
                
                # 시스템 포지션 정보 완전 저장
                self.system_position_ids.add(position.position_id)
                
                # system_position_data에 전체 메타데이터 저장
                self.system_position_data[position.position_id] = {
                    'symbol': symbol,
                    'strategy': strategy_name,
                    'account': getattr(self, 'account_name', 'MASTER'),
                    'created_at': creation_time,
                    'entry_price': entry_price,
                    'side': side.upper(),
                    'size': size,
                    'leverage': leverage,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'source': 'add_position'  # 포지션이 어떻게 생성되었는지 추적
                }
                
                self._save_system_positions()
                
                await self._save_positions_batch()
                
                # 통계 업데이트
                self.stats['total_positions_created'] += 1
                
                # DB에 저장
                if self.db:
                    await self.db.save_position(position.to_dict())
                    await self.db.record_trade({
                        'position_id': position.position_id,
                        'symbol': symbol,
                        'action': 'OPEN',
                        'size': size,
                        'price': entry_price,
                        'strategy_name': strategy_name,
                        'reason': f'Strategy: {strategy_name}'
                    })
                
                logger.info(f"포지션 추가: {symbol} {side} {size} by {strategy_name}")
                logger.info(f"[DEBUG] 알림 전송 시작 - notification_manager: {self.notification_manager is not None}")
                
                # 이벤트 발생
                await self._emit_event('position_created', {
                    'symbol': symbol,
                    'position': position.to_dict(),
                    'reason': f'strategy_{strategy_name}'
                })
                
                # 알림 전송 (notification_manager 사용)
                if self.notification_manager:
                    await self.notification_manager.send_alert(
                        event_type='POSITION_OPENED',
                        title=f'🔵 {symbol} 포지션 진입',
                        message=(
                            f"<b>방향:</b> {side}\n"
                            f"<b>수량:</b> {size:.4f}\n"
                            f"<b>진입가:</b> ${entry_price:.2f}\n"
                            f"<b>레버리지:</b> {leverage}x\n"
                            f"<b>전략:</b> {strategy_name}"
                        ),
                        data={
                            'symbol': symbol,
                            'side': side,
                            'size': size,
                            'entry_price': entry_price,
                            'leverage': leverage,
                            'strategy_name': strategy_name
                        }
                    )
                else:
                    logger.warning("알림 매니저가 없어 포지션 진입 알림을 보낼 수 없습니다")
                
                return position
                
            except Exception as e:
                logger.error(f"포지션 추가 실패: {e}")
                self.stats['errors'] += 1
                raise PositionError(f"포지션 추가 실패: {e}")
    
    async def remove_position(self, symbol: str, reason: str = "unknown", 
                            exit_price: float = None, strategy_name: str = None) -> bool:
        """포지션 제거 (청산)
        
        Args:
            symbol: 심볼
            reason: 청산 사유
            exit_price: 청산가
            strategy_name: 전략 이름 (None이면 첫 번째 활성 포지션)
        """
        async with self._lock:
            try:
                # 전략명이 지정된 경우 복합 키 사용
                if strategy_name:
                    key = f"{symbol}_{strategy_name}"
                    if key not in self.positions:
                        logger.warning(f"제거할 포지션이 없습니다: {symbol} ({strategy_name})")
                        return False
                    position = self.positions[key]
                else:
                    # 전략명이 없으면 해당 심볼의 첫 번째 포지션 찾기
                    position = self.get_position(symbol)
                    if not position:
                        logger.warning(f"제거할 포지션이 없습니다: {symbol}")
                        return False
                    key = f"{symbol}_{position.strategy_name}"
                
                # 상태 업데이트
                position.status = PositionStatus.CLOSED.value
                position.last_updated = datetime.now().isoformat()
                
                # 전략별 인덱스에서 제거
                if position.strategy_name:
                    strategy_key = position.strategy_name
                else:
                    strategy_key = 'MANUAL'
                    
                if strategy_key in self.strategy_positions and key in self.strategy_positions[strategy_key]:
                    self.strategy_positions[strategy_key].remove(key)
                
                # 손익 계산 (exit_price가 있는 경우)
                if exit_price:
                    if position.side == 'LONG':
                        pnl_percent = (exit_price - position.entry_price) / position.entry_price * 100
                    else:
                        pnl_percent = (position.entry_price - exit_price) / position.entry_price * 100
                    
                    position.total_pnl = pnl_percent * position.leverage
                    
                    # MDD Manager에 거래 결과 알림 (개선된 MDD를 위해 추가)
                    # strategy의 mdd_manager에 접근 필요
                    # 이 부분은 TFPE 전략에서 처리하도록 함
                
                # DB에 기록
                if self.db:
                    await self.db.record_trade({
                        'position_id': position.position_id,
                        'symbol': symbol,
                        'action': 'CLOSE',
                        'size': position.size,
                        'price': exit_price,
                        'reason': reason
                    })
                
                # 상태 저장
                await self._save_positions_batch()
                
                # 통계 업데이트
                self.stats['total_positions_closed'] += 1
                
                # 이벤트 발생
                await self._emit_event('position_closed', {
                    'symbol': symbol,
                    'position': position.to_dict(),
                    'reason': reason,
                    'exit_price': exit_price
                })
                
                # 알림 전송
                if self.notification_manager and exit_price:
                    pnl_text = f"{position.total_pnl:+.2f}%" if position.total_pnl else "N/A"
                    
                    await self.notification_manager.send_alert(
                        event_type='POSITION_CLOSED',
                        title=f'🔴 {symbol} 포지션 청산',
                        message=(
                            f"<b>방향:</b> {position.side}\n"
                            f"<b>진입가:</b> ${position.entry_price:.2f}\n"
                            f"<b>청산가:</b> ${exit_price:.2f}\n"
                            f"<b>손익:</b> {pnl_text}\n"
                            f"<b>사유:</b> {reason}"
                        ),
                        data={
                            'symbol': symbol,
                            'side': position.side,
                            'entry_price': position.entry_price,
                            'exit_price': exit_price,
                            'pnl': position.total_pnl,
                            'reason': reason
                        }
                    )
                
                logger.info(f"포지션 청산: {symbol} - {reason}")
                return True
                
            except Exception as e:
                logger.error(f"포지션 제거 실패 ({symbol}): {e}")
                return False
    
    def get_system_stats(self) -> Dict:
        """시스템 통계 반환"""
        return {
            'total_positions': len(self.positions),
            'active_positions': len([p for p in self.positions.values() if p.status == PositionStatus.ACTIVE.value]),
            'strategies': self.get_active_strategies(),
            'strategy_positions': {k: len(v) for k, v in self.strategy_positions.items()},
            'config': self.config.copy(),
            'stats': self.stats.copy(),
            'event_handlers': {k: len(v) for k, v in self._event_handlers.items()}
        }
    
    def get_active_strategies(self) -> List[str]:
        """현재 활성 포지션을 가진 전략 목록"""
        strategies = set()
        for position in self.positions.values():
            if (position.status == PositionStatus.ACTIVE.value and 
                position.strategy_name and 
                not position.is_manual):
                strategies.add(position.strategy_name)
        return list(strategies)
    
    def get_positions_by_strategy(self, strategy_name: str) -> List[Position]:
        """특정 전략의 모든 포지션 조회"""
        positions = []
        for key in self.strategy_positions.get(strategy_name, []):
            if key in self.positions:
                positions.append(self.positions[key])
        return positions
    
    async def cleanup(self):
        """정리 작업 - 강화된 버전"""
        try:
            # 최종 상태 저장
            await self._save_positions_batch()
            
            # 이벤트 핸들러 정리
            self._event_handlers.clear()
            
            logger.info("포지션 매니저 정리 완료")
            
        except Exception as e:
            logger.error(f"포지션 매니저 정리 실패: {e}")
    
    # 기존 메서드들 (get_position, get_all_positions 등)은 동일하게 유지
    def get_position(self, symbol: str, strategy_name: str = None) -> Optional[Position]:
        """특정 포지션 조회
        
        Args:
            symbol: 심볼
            strategy_name: 전략 이름 (None이면 첫 번째 활성 포지션 반환)
        """
        # 전략명이 지정된 경우: 복합 키로 직접 조회
        if strategy_name:
            key = f"{symbol}_{strategy_name}"
            position = self.positions.get(key)
            if position and position.status == PositionStatus.ACTIVE.value:
                return position
            return None
        
        # 전략명이 없는 경우: 해당 심볼의 첫 번째 활성 포지션 반환 (하위 호환성)
        for key, position in self.positions.items():
            if (position.symbol == symbol and 
                position.status == PositionStatus.ACTIVE.value):
                logger.warning(f"get_position({symbol}) called without strategy_name. "
                              f"Returning position from {position.strategy_name}")
                return position
        
        return None
    
    def get_all_positions(self) -> Dict[str, Position]:
        """모든 포지션 조회"""
        return self.positions.copy()
    
    def get_active_positions(self, include_manual: bool = True, strategy_name: str = None) -> List[Position]:
        """활성 포지션 목록 조회
        
        Args:
            include_manual: 수동 포지션 포함 여부
            strategy_name: 특정 전략만 필터링 (None이면 모든 전략)
        """
        positions = []
        
        for position in self.positions.values():
            if position.status == PositionStatus.ACTIVE.value:
                # 수동 포지션 필터
                if not include_manual and position.is_manual:
                    continue
                    
                # 전략 필터
                if strategy_name and position.strategy_name != strategy_name:
                    continue
                    
                positions.append(position)
        
        return positions
    
    def is_position_exist(self, symbol: str, strategy_name: str = None) -> bool:
        """포지션 존재 여부 확인
        
        Args:
            symbol: 심볼
            strategy_name: 전략 이름 (None이면 모든 전략 포함)
        """
        if strategy_name:
            key = f"{symbol}_{strategy_name}"
            return (key in self.positions and 
                    self.positions[key].status == PositionStatus.ACTIVE.value)
        else:
            # 전략명이 없으면 해당 심볼의 아무 포지션이라도 있는지 확인
            return self.get_position(symbol) is not None
    
    def get_position_count(self, include_manual: bool = True) -> int:
        """활성 포지션 개수"""
        return len(self.get_active_positions(include_manual))
    
    def get_position_summary(self) -> Dict:
        """포지션 요약 정보"""
        active_positions = self.get_active_positions()
        
        # 전략별 포지션 수 계산
        strategy_counts = {}
        for p in active_positions:
            if p.strategy_name:
                strategy_counts[p.strategy_name] = strategy_counts.get(p.strategy_name, 0) + 1
        
        # 심볼별 전략 목록
        symbol_strategies = {}
        for p in active_positions:
            if p.symbol not in symbol_strategies:
                symbol_strategies[p.symbol] = []
            if p.strategy_name:
                symbol_strategies[p.symbol].append(p.strategy_name)
        
        # 중복 제거된 심볼 리스트 (실제 포지션 수)
        unique_symbols = list(set([p.symbol for p in active_positions]))
        
        # 실제 포지션 수 계산 (심볼 기준)
        actual_position_count = len(unique_symbols)
        
        # 수동/자동 포지션을 실제 포지션 기준으로 재계산
        manual_count = 0
        auto_count = 0
        long_count = 0
        short_count = 0
        
        # 심볼별로 그룹화하여 실제 포지션 수 계산
        symbol_positions = {}
        for p in active_positions:
            if p.symbol not in symbol_positions:
                symbol_positions[p.symbol] = []
            symbol_positions[p.symbol].append(p)
        
        # 각 심볼별로 포지션 타입 판단
        for symbol, positions in symbol_positions.items():
            # 해당 심볼의 포지션들 중 하나라도 수동이면 수동으로 카운트
            is_manual = any(p.is_manual for p in positions)
            if is_manual:
                manual_count += 1
            else:
                auto_count += 1
            
            # 방향은 첫 번째 포지션의 방향 사용 (동일 심볼은 같은 방향이어야 함)
            if positions[0].side == 'LONG':
                long_count += 1
            else:
                short_count += 1
        
        return {
            'total_positions': actual_position_count,  # 실제 포지션 수 (심볼 기준)
            'total_entries': len(active_positions),   # 전체 엔트리 수 (전략별 카운트)
            'manual_positions': manual_count,  # 수동 포지션 수 (심볼 기준)
            'auto_positions': auto_count,      # 자동 포지션 수 (심볼 기준)
            'long_positions': long_count,      # 롱 포지션 수 (심볼 기준)
            'short_positions': short_count,    # 숏 포지션 수 (심볼 기준)
            'manual_entries': len([p for p in active_positions if p.is_manual]),  # 수동 엔트리 수
            'auto_entries': len([p for p in active_positions if not p.is_manual]), # 자동 엔트리 수
            'symbols': unique_symbols,  # 중복 제거된 심볼 리스트
            'all_symbols': [p.symbol for p in active_positions],  # 모든 심볼 (중복 포함)
            'strategies': list(set([p.strategy_name for p in active_positions if p.strategy_name])),
            'strategy_counts': strategy_counts,
            'symbol_strategies': symbol_strategies,
            'total_initial_value': sum([p.initial_size * p.entry_price for p in active_positions]),
            'modified_positions': len([p for p in active_positions if p.status == PositionStatus.MODIFIED.value])
        }
    
    def calculate_kelly_position_size(self, win_rate: float, avg_win: float, avg_loss: float, 
                                    kelly_fraction: float = 0.25) -> float:
        """Kelly Criterion으로 최적 포지션 크기 계산
        
        Args:
            win_rate: 승률 (0-1)
            avg_win: 평균 수익률 (%)
            avg_loss: 평균 손실률 (%) - 음수여도 절대값으로 처리
            kelly_fraction: Kelly 비율 (보수적 적용)
            
        Returns:
            최적 포지션 크기 (%)
        """
        if win_rate <= 0 or avg_loss == 0:
            return 20.0  # 기본값 20%
        
        p = win_rate  # 승률
        q = 1 - win_rate  # 패율
        b = abs(avg_win) / abs(avg_loss)  # 손익비
        
        # Kelly 공식: f = (p * b - q) / b
        kelly_pct = (p * b - q) / b
        
        # 보수적 적용 (Kelly의 일부만 사용)
        conservative_kelly = max(0, kelly_pct * kelly_fraction)
        
        # 최대 포지션 크기 제한 (레버리지 고려)
        if self.config_manager:
            leverage = self.config_manager.config.get('strategies', {}).get('tfpe', {}).get('leverage', 10)
        else:
            leverage = 10  # 기본값
        
        max_position = 100 / leverage  # 최대 포지션 크기 %
        
        return min(conservative_kelly * 100, max_position)
    
    def calculate_volatility_adjusted_position_size(self, current_vol: float, base_size: float) -> float:
        """변동성 조정 포지션 사이징
        
        Args:
            current_vol: 현재 변동성
            base_size: 기본 포지션 크기 (%)
            
        Returns:
            조정된 포지션 크기 (%)
        """
        target_vol = 0.15  # 목표 변동성 15%
        vol_scalar = min(1.0, target_vol / current_vol) if current_vol > 0 else 1.0
        return base_size * vol_scalar
    
    def calculate_dynamic_position_size(self, 
                                      strategy_type: str,
                                      current_risk_used: float,
                                      current_atr: float,
                                      current_price: float,
                                      historical_performance: Optional[Dict] = None,
                                      current_volatility: Optional[float] = None) -> float:
        """리스크 기반 동적 포지션 크기 계산 (Kelly Criterion + 변동성 조정 포함)
        
        백테스트 개선사항 적용:
        1. Kelly Criterion 기반 사이징
        2. 변동성 기반 조정
        3. 리스크 패리티 적용
        4. MDD 상태 반영
        
        Args:
            strategy_type: 전략 타입 (TFPE, MOMENTUM 등)
            current_risk_used: 현재 사용 중인 일일 리스크 (%)
            current_atr: 현재 ATR
            current_price: 현재 가격
            historical_performance: 과거 성과 데이터
            current_volatility: 현재 변동성
            
        Returns:
            동적 포지션 크기 (%)
        """
        try:
            if not self.config_manager:
                logger.warning("Config manager not available, using default position size")
                return 20.0  # 기본값
            
            # 전략 설정 가져오기
            strategy_config = self.config_manager.config.get('strategies', {}).get(strategy_type.lower(), {})
            
            # 동적 포지션 사이징 설정 확인
            dynamic_sizing_config = strategy_config.get('dynamic_position_sizing', {})
            if not dynamic_sizing_config.get('enabled', False):
                # 동적 사이징 비활성화시 기본값 반환
                return float(strategy_config.get('position_size', 24))
            
            # 기본 파라미터
            leverage = float(strategy_config.get('leverage', 10))
            base_position_size = float(strategy_config.get('position_size', 24))
            stop_loss_atr = float(strategy_config.get('stop_loss_atr', 1.5))
            
            # 동적 사이징 파라미터
            kelly_fraction = dynamic_sizing_config.get('kelly_fraction', 0.25)
            target_volatility = dynamic_sizing_config.get('target_volatility', 0.15)
            min_position_size = dynamic_sizing_config.get('min_position_size', 10)
            max_position_size = dynamic_sizing_config.get('max_position_size', 40)
            use_risk_parity = dynamic_sizing_config.get('use_risk_parity', True)
            
            # 1. Kelly Criterion 적용 (historical_performance가 있을 경우)
            kelly_multiplier = 1.0
            if historical_performance and strategy_type in historical_performance:
                perf = historical_performance[strategy_type]
                if all(k in perf for k in ['win_rate', 'avg_win', 'avg_loss']):
                    kelly_size = self.calculate_kelly_position_size(
                        win_rate=perf['win_rate'],
                        avg_win=perf['avg_win'],
                        avg_loss=perf['avg_loss'],
                        kelly_fraction=kelly_fraction
                    )
                    # Kelly 배수 계산 (0.5 ~ 1.5 범위로 제한)
                    kelly_multiplier = max(0.5, min(1.5, kelly_size / base_position_size))
                    logger.info(f"Kelly multiplier for {strategy_type}: {kelly_multiplier:.2f}")
            
            # 2. 기본 포지션 크기에 Kelly 적용
            position_size = base_position_size * kelly_multiplier
            
            # 3. 변동성 조정 적용
            if current_volatility and current_volatility > 0:
                vol_adjusted_size = self.calculate_volatility_adjusted_position_size(
                    current_volatility, position_size
                )
                logger.info(f"Volatility adjusted size: {position_size:.1f}% → {vol_adjusted_size:.1f}%")
                position_size = vol_adjusted_size
            
            # 4. ATR 기반 리스크 조정
            # 포지션 크기 = (계정 리스크 %) / (ATR 기반 손절 %)
            stop_distance_pct = (current_atr / current_price) * stop_loss_atr
            if stop_distance_pct > 0:
                # 계정 리스크 설정
                account_risk_config = self.config_manager.config.get('account_risk', {})
                max_risk_per_trade = account_risk_config.get('max_risk_per_trade', 0.015) * 100  # 1.5%
                
                # 남은 일일 리스크 확인
                max_daily_risk = account_risk_config.get('max_daily_risk', 0.05) * 100  # 5%
                remaining_daily_risk = max_daily_risk - current_risk_used
                
                # 실제 적용 리스크 (남은 일일 리스크를 초과하지 않도록)
                actual_risk = min(max_risk_per_trade, remaining_daily_risk)
                
                # ATR 기반 포지션 크기 계산
                atr_based_size = (actual_risk / stop_distance_pct) / leverage * 100
                
                # 더 보수적인 크기 선택
                position_size = min(position_size, atr_based_size)
                logger.info(f"ATR-based size limit: {atr_based_size:.1f}%, final: {position_size:.1f}%")
            
            # 5. MDD 상태 반영 (MDD Manager가 있는 경우)
            # 이 부분은 TFPE 전략에서 mdd_manager.get_position_size_multiplier()로 처리
            
            # 6. 최종 크기 제한
            position_size = max(min_position_size, min(position_size, max_position_size))
            
            # 7. 레버리지 제한
            max_leveraged_size = 100 / leverage
            position_size = min(position_size, max_leveraged_size)
            
            logger.info(f"Dynamic position size for {strategy_type}: {position_size:.1f}% "
                       f"(base: {base_position_size}%, kelly: {kelly_multiplier:.2f}x)")
            
            return position_size
            
        except Exception as e:
            logger.error(f"Dynamic position sizing failed: {e}")
            # 에러시 기본값 반환
            if self.config_manager:
                return float(self.config_manager.config.get('strategies', {}).get(strategy_type.lower(), {}).get('position_size', 24))
            return 20.0  # 최종 기본값
    
    def calculate_position_size(self, balance: float, leverage: int = 15, size_percent: float = 24) -> float:
        """포지션 크기 계산 (기존 메서드 - 하위 호환성 유지)
        
        Args:
            balance: 계좌 잔고
            leverage: 레버리지
            size_percent: 포지션 크기 비율 (%)
            
        Returns:
            USDT 기준 포지션 크기
        """
        return balance * (size_percent / 100) * leverage
