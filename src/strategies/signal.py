"""
트레이딩 시그널 데이터 클래스
전략 간 시그널 전달을 위한 표준 인터페이스
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


class SignalType(Enum):
    """시그널 타입"""
    ENTRY_LONG = "ENTRY_LONG"
    ENTRY_SHORT = "ENTRY_SHORT"
    EXIT_LONG = "EXIT_LONG"
    EXIT_SHORT = "EXIT_SHORT"
    CLOSE_ALL = "CLOSE_ALL"
    MODIFY_POSITION = "MODIFY_POSITION"
    PARTIAL_CLOSE = "PARTIAL_CLOSE"


class SignalStrength(Enum):
    """시그널 강도"""
    WEAK = 1
    MEDIUM = 2
    STRONG = 3
    VERY_STRONG = 4


@dataclass
class Signal:
    """트레이딩 시그널 데이터 클래스"""
    symbol: str
    signal_type: SignalType
    strength: SignalStrength
    price: float
    timestamp: datetime
    strategy_name: str
    
    # 선택적 필드
    quantity: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    leverage: Optional[int] = None
    reason: Optional[str] = None
    confidence: Optional[float] = None  # 0.0 ~ 1.0
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """초기화 후 처리"""
        # 타임스탬프가 없으면 현재 시간
        if self.timestamp is None:
            self.timestamp = datetime.now()
        
        # 메타데이터 초기화
        if self.metadata is None:
            self.metadata = {}
        
        # SignalType이 문자열로 들어온 경우 변환
        if isinstance(self.signal_type, str):
            self.signal_type = SignalType(self.signal_type)
        
        # SignalStrength가 숫자로 들어온 경우 변환
        if isinstance(self.strength, int):
            self.strength = SignalStrength(self.strength)
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 변환"""
        return {
            'symbol': self.symbol,
            'signal_type': self.signal_type.value,
            'strength': self.strength.value,
            'price': self.price,
            'timestamp': self.timestamp.isoformat(),
            'strategy_name': self.strategy_name,
            'quantity': self.quantity,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'leverage': self.leverage,
            'reason': self.reason,
            'confidence': self.confidence,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Signal':
        """딕셔너리에서 생성"""
        # 타임스탬프 파싱
        if 'timestamp' in data and isinstance(data['timestamp'], str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        
        # SignalType 변환
        if 'signal_type' in data and isinstance(data['signal_type'], str):
            data['signal_type'] = SignalType(data['signal_type'])
        
        # SignalStrength 변환
        if 'strength' in data:
            if isinstance(data['strength'], str):
                data['strength'] = SignalStrength[data['strength']]
            elif isinstance(data['strength'], int):
                data['strength'] = SignalStrength(data['strength'])
        
        return cls(**data)
    
    def is_entry_signal(self) -> bool:
        """진입 시그널 여부"""
        return self.signal_type in [SignalType.ENTRY_LONG, SignalType.ENTRY_SHORT]
    
    def is_exit_signal(self) -> bool:
        """청산 시그널 여부"""
        return self.signal_type in [SignalType.EXIT_LONG, SignalType.EXIT_SHORT, SignalType.CLOSE_ALL]
    
    def is_long_signal(self) -> bool:
        """롱 시그널 여부"""
        return self.signal_type in [SignalType.ENTRY_LONG, SignalType.EXIT_SHORT]
    
    def is_short_signal(self) -> bool:
        """숏 시그널 여부"""
        return self.signal_type in [SignalType.ENTRY_SHORT, SignalType.EXIT_LONG]
    
    def get_direction(self) -> Optional[str]:
        """포지션 방향 반환"""
        if self.signal_type == SignalType.ENTRY_LONG:
            return "LONG"
        elif self.signal_type == SignalType.ENTRY_SHORT:
            return "SHORT"
        return None
    
    def validate(self) -> bool:
        """시그널 유효성 검증"""
        # 필수 필드 확인
        if not self.symbol or not self.strategy_name:
            return False
        
        # 가격 유효성
        if self.price <= 0:
            return False
        
        # 수량 유효성 (설정된 경우)
        if self.quantity is not None and self.quantity <= 0:
            return False
        
        # 신뢰도 범위 (설정된 경우)
        if self.confidence is not None and not (0 <= self.confidence <= 1):
            return False
        
        return True
    
    def __str__(self) -> str:
        """문자열 표현"""
        return (
            f"Signal({self.symbol} {self.signal_type.value} "
            f"@ {self.price:.2f} [{self.strength.name}] "
            f"by {self.strategy_name})"
        )
    
    def __repr__(self) -> str:
        """개발자용 표현"""
        return (
            f"Signal(symbol='{self.symbol}', "
            f"signal_type={self.signal_type}, "
            f"strength={self.strength}, "
            f"price={self.price}, "
            f"strategy_name='{self.strategy_name}')"
        )