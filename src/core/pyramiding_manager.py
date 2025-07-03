"""
PyramidingManager - Enterprise-grade Pyramiding System for AlbraTrading
15년 경력의 Goldman Sachs & Jane Street 스타일 구현

피라미딩(Pyramiding): 수익이 발생한 포지션에 추가로 진입하여 수익을 극대화하는 전략
- 초기 포지션이 수익을 내고 있을 때만 추가 진입
- 리스크 관리를 위해 추가 진입 시 포지션 크기를 점진적으로 줄임
- 전체 포지션의 평균 진입가를 관리하여 리스크 컨트롤
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime
from decimal import Decimal
import asyncio
import logging
from enum import Enum

from src.core.event_bus import Event, EventCategory, EventPriority

logger = logging.getLogger(__name__)


class PyramidingType(Enum):
    """피라미딩 타입"""
    FIXED = "FIXED"      # 고정 크기
    SCALED = "SCALED"    # 점진적 축소
    MARTINGALE = "MARTINGALE"  # 마틴게일 (위험)


class ExitMethod(Enum):
    """청산 방식"""
    FIFO = "FIFO"  # First In First Out
    LIFO = "LIFO"  # Last In First Out
    PROPORTIONAL = "PROPORTIONAL"  # 비례 청산


@dataclass
class SubPosition:
    """피라미딩 서브 포지션
    
    각 피라미딩 레벨의 개별 포지션 정보를 관리
    """
    entry_price: Decimal
    size: Decimal
    entry_time: datetime
    level: int  # 피라미딩 레벨 (0=초기, 1,2,3=추가)
    stop_loss: Optional[Decimal] = None
    position_id: str = field(default_factory=lambda: f"sub_{datetime.now().timestamp()}")
    
    def __post_init__(self):
        """타입 보장"""
        self.entry_price = Decimal(str(self.entry_price))
        self.size = Decimal(str(self.size))
    
    @property
    def value(self) -> Decimal:
        """포지션 가치"""
        return self.entry_price * self.size
    
    def calculate_pnl(self, current_price: Decimal, side: str) -> Decimal:
        """손익 계산"""
        if side == 'LONG':
            return (current_price - self.entry_price) * self.size
        else:  # SHORT
            return (self.entry_price - current_price) * self.size


@dataclass
class PyramidingPosition:
    """피라미딩 포지션 전체 관리
    
    여러 서브 포지션을 통합 관리하며 평균 진입가와 전체 크기를 추적
    """
    symbol: str
    side: str  # LONG/SHORT
    strategy_name: str
    sub_positions: List[SubPosition] = field(default_factory=list)
    max_levels: int = 3
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    
    # 리스크 관리
    max_total_size: Optional[Decimal] = None  # 최대 전체 포지션 크기
    risk_score: float = 0.0  # 리스크 점수 (0-100)
    
    @property
    def total_size(self) -> Decimal:
        """전체 포지션 크기"""
        return sum(sub.size for sub in self.sub_positions)
    
    @property
    def average_entry_price(self) -> Decimal:
        """가중평균 진입가"""
        if not self.sub_positions:
            return Decimal('0')
        total_value = sum(sub.value for sub in self.sub_positions)
        return total_value / self.total_size if self.total_size > 0 else Decimal('0')
    
    @property
    def current_level(self) -> int:
        """현재 피라미딩 레벨 (0-based)"""
        return len(self.sub_positions) - 1
    
    @property
    def is_full(self) -> bool:
        """최대 레벨 도달 여부"""
        return self.current_level >= self.max_levels
    
    def calculate_total_pnl(self, current_price: Decimal) -> Decimal:
        """전체 손익 계산"""
        return sum(sub.calculate_pnl(current_price, self.side) for sub in self.sub_positions)
    
    def get_level_sizes(self) -> Dict[int, Decimal]:
        """레벨별 포지션 크기"""
        level_sizes = {}
        for sub in self.sub_positions:
            level_sizes[sub.level] = level_sizes.get(sub.level, Decimal('0')) + sub.size
        return level_sizes
    
    def update_risk_score(self, market_volatility: float, account_risk: float):
        """리스크 점수 업데이트"""
        # 피라미딩 레벨이 높을수록 리스크 증가
        level_risk = (self.current_level / self.max_levels) * 30
        
        # 시장 변동성 반영
        volatility_risk = min(market_volatility * 100, 40)
        
        # 계좌 리스크 반영
        account_risk_score = min(account_risk * 100, 30)
        
        self.risk_score = min(level_risk + volatility_risk + account_risk_score, 100)
        self.last_updated = datetime.now()


class PyramidingManager:
    """피라미딩 관리자 - Goldman Sachs 스타일의 엄격한 리스크 관리
    
    모든 전략에서 재사용 가능한 피라미딩 시스템
    - Fail-Safe Design: 모든 작업에 실패 안전 장치
    - Event-Driven: Event Bus를 통한 느슨한 결합
    - Type Safety: 모든 수치는 Decimal 타입 사용
    """
    
    def __init__(self, position_manager, event_bus, config: Dict):
        self.position_manager = position_manager
        self.event_bus = event_bus
        self.config = config
        
        # 피라미딩 포지션 저장소
        self.pyramiding_positions: Dict[str, PyramidingPosition] = {}
        
        # 설정 로드
        self._load_config(config)
        
        # 통계
        self.stats = {
            'total_pyramids_created': 0,
            'total_pyramids_closed': 0,
            'total_sub_positions': 0,
            'successful_pyramids': 0,
            'failed_pyramids': 0
        }
        
        # 락
        self._lock = asyncio.Lock()
        
        logger.info("PyramidingManager 초기화 완료")
        logger.info(f"  기본 레벨: {self.default_levels}")
        logger.info(f"  크기 비율: {self.default_size_ratios}")
        logger.info(f"  타입: {self.pyramiding_type}")
    
    def _load_config(self, config: Dict):
        """설정 로드 및 검증"""
        # 피라미딩 레벨 (수익률)
        self.default_levels = [Decimal(str(x)) for x in config.get('pyramiding_levels', [0.03, 0.06, 0.09])]
        
        # 크기 비율
        self.default_size_ratios = [Decimal(str(x)) for x in config.get('pyramiding_size_ratios', [0.75, 0.50, 0.25])]
        
        # 피라미딩 타입
        self.pyramiding_type = PyramidingType(config.get('pyramiding_type', 'SCALED'))
        
        # 청산 방식
        self.exit_method = ExitMethod(config.get('pyramiding_exit_method', 'FIFO'))
        
        # 리스크 한도
        self.max_pyramiding_per_symbol = config.get('max_pyramiding_per_symbol', 3)
        self.max_total_exposure_ratio = Decimal(str(config.get('max_total_exposure_ratio', 2.0)))  # 초기 대비 최대 2배
        
        # 최소 간격
        self.min_pyramid_interval_seconds = config.get('min_pyramid_interval_seconds', 300)  # 5분
        
        # 검증
        if len(self.default_levels) != len(self.default_size_ratios):
            raise ValueError("pyramiding_levels와 pyramiding_size_ratios의 길이가 일치해야 합니다")
    
    def _get_position_key(self, symbol: str, strategy_name: str) -> str:
        """포지션 키 생성"""
        return f"{symbol}_{strategy_name}"
    
    async def can_add_pyramiding(self, symbol: str, strategy_name: str, 
                                current_price: Decimal, current_pnl_pct: float) -> Tuple[bool, str]:
        """피라미딩 추가 가능 여부 확인
        
        Returns:
            Tuple[bool, str]: (가능 여부, 불가능한 경우 이유)
        """
        key = self._get_position_key(symbol, strategy_name)
        
        async with self._lock:
            # 포지션이 없으면 초기화 필요
            if key not in self.pyramiding_positions:
                return True, "initial_position"
            
            pyramid_pos = self.pyramiding_positions[key]
            
            # 최대 레벨 체크
            if pyramid_pos.is_full:
                return False, f"최대 레벨 도달 ({pyramid_pos.current_level}/{pyramid_pos.max_levels})"
            
            # 시간 간격 체크
            if pyramid_pos.sub_positions:
                last_entry = pyramid_pos.sub_positions[-1].entry_time
                time_diff = (datetime.now() - last_entry).total_seconds()
                if time_diff < self.min_pyramid_interval_seconds:
                    return False, f"최소 간격 미충족 ({time_diff:.0f}초/{self.min_pyramid_interval_seconds}초)"
            
            # 다음 레벨 진입 조건 체크
            next_level = pyramid_pos.current_level + 1
            if next_level < len(self.default_levels):
                required_pnl = float(self.default_levels[next_level])
                if current_pnl_pct < required_pnl:
                    return False, f"수익률 미달 ({current_pnl_pct:.2%} < {required_pnl:.2%})"
            
            # 최대 노출 체크
            if pyramid_pos.max_total_size:
                next_size = self._calculate_next_size(pyramid_pos)
                if pyramid_pos.total_size + next_size > pyramid_pos.max_total_size:
                    return False, f"최대 노출 한도 초과"
            
            # 리스크 점수 체크
            if pyramid_pos.risk_score > 70:
                return False, f"리스크 점수 초과 ({pyramid_pos.risk_score:.0f}/100)"
            
            return True, "ok"
    
    def _calculate_next_size(self, pyramid_pos: PyramidingPosition) -> Decimal:
        """다음 피라미딩 크기 계산"""
        if not pyramid_pos.sub_positions:
            return Decimal('0')
        
        initial_size = pyramid_pos.sub_positions[0].size
        next_level = pyramid_pos.current_level + 1
        
        if self.pyramiding_type == PyramidingType.FIXED:
            return initial_size
        elif self.pyramiding_type == PyramidingType.SCALED:
            if next_level < len(self.default_size_ratios):
                return initial_size * self.default_size_ratios[next_level]
            else:
                return initial_size * Decimal('0.25')  # 기본값
        else:  # MARTINGALE (위험!)
            return initial_size * Decimal(str(2 ** next_level))
    
    async def initialize_position(self, symbol: str, strategy_name: str, 
                                 position) -> Optional[PyramidingPosition]:
        """초기 포지션으로 피라미딩 포지션 초기화"""
        key = self._get_position_key(symbol, strategy_name)
        
        async with self._lock:
            if key in self.pyramiding_positions:
                logger.warning(f"피라미딩 포지션이 이미 존재함: {key}")
                return self.pyramiding_positions[key]
            
            # 초기 서브 포지션 생성
            initial_sub = SubPosition(
                entry_price=Decimal(str(position.entry_price)),
                size=Decimal(str(position.size)),
                entry_time=datetime.now(),
                level=0,
                stop_loss=Decimal(str(position.stop_loss)) if position.stop_loss else None
            )
            
            # 피라미딩 포지션 생성
            pyramid_pos = PyramidingPosition(
                symbol=symbol,
                side=position.side,
                strategy_name=strategy_name,
                sub_positions=[initial_sub],
                max_levels=self.max_pyramiding_per_symbol,
                max_total_size=initial_sub.size * self.max_total_exposure_ratio
            )
            
            self.pyramiding_positions[key] = pyramid_pos
            self.stats['total_pyramids_created'] += 1
            
            # 이벤트 발행
            await self._publish_event("PYRAMIDING_INITIALIZED", pyramid_pos, {
                'initial_size': float(initial_sub.size),
                'initial_price': float(initial_sub.entry_price)
            })
            
            logger.info(f"피라미딩 포지션 초기화: {key}")
            return pyramid_pos
    
    async def add_pyramiding(self, symbol: str, strategy_name: str, 
                           size: Decimal, entry_price: Decimal,
                           stop_loss: Optional[Decimal] = None) -> Optional[SubPosition]:
        """피라미딩 포지션 추가"""
        key = self._get_position_key(symbol, strategy_name)
        
        async with self._lock:
            if key not in self.pyramiding_positions:
                logger.error(f"피라미딩 포지션이 존재하지 않음: {key}")
                return None
            
            pyramid_pos = self.pyramiding_positions[key]
            
            # 재확인
            current_pnl_pct = 0  # 실제로는 외부에서 계산된 값 사용
            can_add, reason = await self.can_add_pyramiding(symbol, strategy_name, entry_price, current_pnl_pct)
            if not can_add:
                logger.warning(f"피라미딩 추가 불가: {reason}")
                return None
            
            # 새 서브 포지션 생성
            new_level = pyramid_pos.current_level + 1
            sub_position = SubPosition(
                entry_price=entry_price,
                size=size,
                entry_time=datetime.now(),
                level=new_level,
                stop_loss=stop_loss
            )
            
            pyramid_pos.sub_positions.append(sub_position)
            pyramid_pos.last_updated = datetime.now()
            
            self.stats['total_sub_positions'] += 1
            
            # 이벤트 발행
            await self._publish_event("PYRAMIDING_ADDED", pyramid_pos, {
                'level': new_level,
                'size': float(size),
                'entry_price': float(entry_price),
                'total_size': float(pyramid_pos.total_size),
                'avg_price': float(pyramid_pos.average_entry_price)
            })
            
            logger.info(f"피라미딩 추가 성공: {key} 레벨 {new_level}, 크기 {size}, 가격 {entry_price}")
            return sub_position
    
    async def reduce_pyramiding(self, symbol: str, strategy_name: str, 
                              reduction_size: Decimal) -> List[SubPosition]:
        """피라미딩 포지션 축소
        
        Returns:
            List[SubPosition]: 축소된 서브 포지션 리스트
        """
        key = self._get_position_key(symbol, strategy_name)
        
        async with self._lock:
            if key not in self.pyramiding_positions:
                logger.warning(f"피라미딩 포지션이 존재하지 않음: {key}")
                return []
            
            pyramid_pos = self.pyramiding_positions[key]
            reduced_positions = []
            remaining_reduction = reduction_size
            
            # 청산 방식에 따라 순서 결정
            if self.exit_method == ExitMethod.FIFO:
                positions_to_reduce = list(pyramid_pos.sub_positions)
            elif self.exit_method == ExitMethod.LIFO:
                positions_to_reduce = list(reversed(pyramid_pos.sub_positions))
            else:  # PROPORTIONAL
                # 비례 청산은 각 서브 포지션에서 동일 비율 청산
                ratio = reduction_size / pyramid_pos.total_size
                for sub_pos in pyramid_pos.sub_positions:
                    reduced_size = sub_pos.size * ratio
                    if reduced_size > Decimal('0'):
                        reduced_sub = SubPosition(
                            entry_price=sub_pos.entry_price,
                            size=reduced_size,
                            entry_time=sub_pos.entry_time,
                            level=sub_pos.level
                        )
                        reduced_positions.append(reduced_sub)
                        sub_pos.size -= reduced_size
                
                # 크기가 0인 서브 포지션 제거
                pyramid_pos.sub_positions = [sp for sp in pyramid_pos.sub_positions if sp.size > Decimal('0')]
                pyramid_pos.last_updated = datetime.now()
                
                # 이벤트 발행
                await self._publish_event("PYRAMIDING_REDUCED", pyramid_pos, {
                    'method': self.exit_method.value,
                    'reduced_size': float(reduction_size),
                    'remaining_size': float(pyramid_pos.total_size)
                })
                
                return reduced_positions
            
            # FIFO/LIFO 처리
            for sub_pos in list(positions_to_reduce):
                if remaining_reduction <= Decimal('0'):
                    break
                
                if sub_pos.size <= remaining_reduction:
                    # 전체 서브 포지션 제거
                    reduced_positions.append(sub_pos)
                    remaining_reduction -= sub_pos.size
                    pyramid_pos.sub_positions.remove(sub_pos)
                else:
                    # 부분 축소
                    reduced_size = remaining_reduction
                    sub_pos.size -= reduced_size
                    
                    # 축소된 부분을 새 객체로 반환
                    reduced_sub = SubPosition(
                        entry_price=sub_pos.entry_price,
                        size=reduced_size,
                        entry_time=sub_pos.entry_time,
                        level=sub_pos.level
                    )
                    reduced_positions.append(reduced_sub)
                    remaining_reduction = Decimal('0')
            
            pyramid_pos.last_updated = datetime.now()
            
            # 모든 서브 포지션이 제거되면 피라미딩 포지션도 제거
            if not pyramid_pos.sub_positions:
                del self.pyramiding_positions[key]
                self.stats['total_pyramids_closed'] += 1
                
                # 이벤트 발행
                await self._publish_event("PYRAMIDING_CLOSED", None, {
                    'symbol': symbol,
                    'strategy': strategy_name,
                    'final_pnl': 0  # 실제로는 계산 필요
                })
            else:
                # 이벤트 발행
                await self._publish_event("PYRAMIDING_REDUCED", pyramid_pos, {
                    'method': self.exit_method.value,
                    'reduced_size': float(reduction_size),
                    'remaining_size': float(pyramid_pos.total_size)
                })
            
            return reduced_positions
    
    async def close_pyramiding(self, symbol: str, strategy_name: str) -> Optional[PyramidingPosition]:
        """피라미딩 포지션 전체 청산"""
        key = self._get_position_key(symbol, strategy_name)
        
        async with self._lock:
            if key not in self.pyramiding_positions:
                return None
            
            pyramid_pos = self.pyramiding_positions.pop(key)
            self.stats['total_pyramids_closed'] += 1
            
            # 이벤트 발행
            await self._publish_event("PYRAMIDING_CLOSED", None, {
                'symbol': symbol,
                'strategy': strategy_name,
                'total_size': float(pyramid_pos.total_size),
                'avg_price': float(pyramid_pos.average_entry_price),
                'levels_used': pyramid_pos.current_level + 1
            })
            
            logger.info(f"피라미딩 포지션 청산 완료: {key}")
            return pyramid_pos
    
    def get_pyramiding_info(self, symbol: str, strategy_name: str) -> Optional[Dict]:
        """피라미딩 정보 조회"""
        key = self._get_position_key(symbol, strategy_name)
        
        if key not in self.pyramiding_positions:
            return None
        
        pyramid_pos = self.pyramiding_positions[key]
        
        return {
            'symbol': symbol,
            'strategy': strategy_name,
            'side': pyramid_pos.side,
            'total_size': float(pyramid_pos.total_size),
            'average_price': float(pyramid_pos.average_entry_price),
            'current_level': pyramid_pos.current_level,
            'max_levels': pyramid_pos.max_levels,
            'is_full': pyramid_pos.is_full,
            'risk_score': pyramid_pos.risk_score,
            'created_at': pyramid_pos.created_at.isoformat(),
            'last_updated': pyramid_pos.last_updated.isoformat(),
            'sub_positions': [
                {
                    'level': sub.level,
                    'size': float(sub.size),
                    'entry_price': float(sub.entry_price),
                    'entry_time': sub.entry_time.isoformat(),
                    'position_id': sub.position_id
                }
                for sub in pyramid_pos.sub_positions
            ],
            'level_sizes': {k: float(v) for k, v in pyramid_pos.get_level_sizes().items()}
        }
    
    def get_all_pyramiding_positions(self) -> Dict[str, Dict]:
        """모든 피라미딩 포지션 조회"""
        result = {}
        for key, pyramid_pos in self.pyramiding_positions.items():
            symbol, strategy = key.split('_', 1)
            result[key] = self.get_pyramiding_info(symbol, strategy)
        return result
    
    def update_risk_scores(self, market_data: Dict[str, float], account_risk: float):
        """모든 피라미딩 포지션의 리스크 점수 업데이트"""
        for key, pyramid_pos in self.pyramiding_positions.items():
            symbol = pyramid_pos.symbol
            market_volatility = market_data.get(symbol, 0.02)  # 기본 2%
            pyramid_pos.update_risk_score(market_volatility, account_risk)
    
    async def _publish_event(self, event_type: str, pyramid_pos: Optional[PyramidingPosition], 
                           additional_data: Dict):
        """이벤트 발행"""
        if not self.event_bus:
            return
        
        data = additional_data.copy()
        if pyramid_pos:
            data.update({
                'symbol': pyramid_pos.symbol,
                'strategy': pyramid_pos.strategy_name,
                'side': pyramid_pos.side,
                'current_level': pyramid_pos.current_level,
                'risk_score': pyramid_pos.risk_score
            })
        
        event = Event(
            event_type=event_type,
            category=EventCategory.POSITION,
            data=data,
            priority=EventPriority.HIGH,
            source="PyramidingManager"
        )
        
        await self.event_bus.publish(event)
    
    def get_stats(self) -> Dict:
        """통계 정보 반환"""
        return {
            **self.stats,
            'active_pyramids': len(self.pyramiding_positions),
            'total_sub_positions_active': sum(
                len(pp.sub_positions) for pp in self.pyramiding_positions.values()
            )
        }