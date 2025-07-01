"""
Position Key Manager for AlbraTrading System
복합 키(symbol_strategy) 관리 유틸리티
"""

from typing import Tuple, Optional, Dict, List
import logging

logger = logging.getLogger(__name__)


class PositionKeyManager:
    """포지션 키 관리 유틸리티"""
    
    SEPARATOR = '_'
    DEFAULT_STRATEGY = 'MANUAL'
    
    @classmethod
    def create_key(cls, symbol: str, strategy_name: Optional[str] = None) -> str:
        """복합 키 생성
        
        Args:
            symbol: 거래 심볼 (예: BTCUSDT)
            strategy_name: 전략 이름 (None인 경우 MANUAL)
            
        Returns:
            복합 키 문자열 (예: BTCUSDT_TFPE)
        """
        if not symbol:
            raise ValueError("Symbol cannot be empty")
            
        if not strategy_name:
            strategy_name = cls.DEFAULT_STRATEGY
            
        return f"{symbol}{cls.SEPARATOR}{strategy_name}"
    
    @classmethod
    def parse_key(cls, key: str) -> Tuple[str, str]:
        """복합 키 파싱
        
        Args:
            key: 파싱할 키
            
        Returns:
            (symbol, strategy_name) 튜플
        """
        if not key:
            raise ValueError("Key cannot be empty")
            
        if cls.SEPARATOR not in key:
            # 레거시 키 (심볼만 있는 경우)
            logger.warning(f"Legacy key detected: {key}")
            return key, cls.DEFAULT_STRATEGY
        
        parts = key.split(cls.SEPARATOR, 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f"Invalid key format: {key}")
            
        return parts[0], parts[1]
    
    @classmethod
    def is_legacy_key(cls, key: str) -> bool:
        """레거시 키 여부 확인
        
        Args:
            key: 확인할 키
            
        Returns:
            레거시 키인 경우 True
        """
        return cls.SEPARATOR not in key
    
    @classmethod
    def migrate_key(cls, legacy_key: str, position_data: Dict) -> str:
        """레거시 키를 복합 키로 마이그레이션
        
        Args:
            legacy_key: 레거시 키 (심볼)
            position_data: 포지션 데이터 딕셔너리
            
        Returns:
            마이그레이션된 복합 키
        """
        # 포지션 데이터에서 전략명 추출
        strategy_name = position_data.get('strategy_name')
        
        # 전략명이 없거나 빈 문자열인 경우
        if not strategy_name:
            # is_manual 플래그 확인
            if position_data.get('is_manual', False):
                strategy_name = cls.DEFAULT_STRATEGY
            else:
                # 기본 전략은 TFPE로 가정
                strategy_name = 'TFPE'
                logger.info(f"No strategy name found for {legacy_key}, assuming TFPE")
        
        return cls.create_key(legacy_key, strategy_name)
    
    @classmethod
    def group_by_symbol(cls, keys: List[str]) -> Dict[str, List[str]]:
        """키 목록을 심볼별로 그룹핑
        
        Args:
            keys: 키 목록
            
        Returns:
            {symbol: [strategy_names]} 딕셔너리
        """
        grouped = {}
        
        for key in keys:
            try:
                symbol, strategy = cls.parse_key(key)
                if symbol not in grouped:
                    grouped[symbol] = []
                grouped[symbol].append(strategy)
            except ValueError as e:
                logger.error(f"Invalid key during grouping: {key} - {e}")
                continue
                
        return grouped
    
    @classmethod
    def group_by_strategy(cls, keys: List[str]) -> Dict[str, List[str]]:
        """키 목록을 전략별로 그룹핑
        
        Args:
            keys: 키 목록
            
        Returns:
            {strategy: [symbols]} 딕셔너리
        """
        grouped = {}
        
        for key in keys:
            try:
                symbol, strategy = cls.parse_key(key)
                if strategy not in grouped:
                    grouped[strategy] = []
                grouped[strategy].append(symbol)
            except ValueError as e:
                logger.error(f"Invalid key during grouping: {key} - {e}")
                continue
                
        return grouped


# 사용 예시
if __name__ == "__main__":
    # 키 생성
    key1 = PositionKeyManager.create_key("BTCUSDT", "TFPE")
    key2 = PositionKeyManager.create_key("ETHUSDT", "MOMENTUM")
    key3 = PositionKeyManager.create_key("BNBUSDT")  # MANUAL
    
    print(f"Key 1: {key1}")
    print(f"Key 2: {key2}")
    print(f"Key 3: {key3}")
    
    # 키 파싱
    symbol, strategy = PositionKeyManager.parse_key(key1)
    print(f"Parsed: {symbol}, {strategy}")
    
    # 레거시 키 확인
    print(f"Is legacy 'BTCUSDT': {PositionKeyManager.is_legacy_key('BTCUSDT')}")
    print(f"Is legacy 'BTCUSDT_TFPE': {PositionKeyManager.is_legacy_key('BTCUSDT_TFPE')}")