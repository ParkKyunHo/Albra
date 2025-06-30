"""
전략 설정 관리자
각 전략의 파라미터와 설정을 중앙 관리
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json
import os

@dataclass
class StrategyConfig:
    """전략 설정 데이터 클래스"""
    name: str
    enabled: bool = True
    symbols: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    risk_settings: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "name": self.name,
            "enabled": self.enabled,
            "symbols": self.symbols,
            "parameters": self.parameters,
            "risk_settings": self.risk_settings,
            "description": self.description,
            "created_at": self.created_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StrategyConfig':
        """딕셔너리에서 생성"""
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)


class StrategyConfigManager:
    """전략 설정 관리자"""
    
    # 기본 전략 템플릿
    DEFAULT_STRATEGIES = {
        "TFPE": {
            "name": "TFPE",
            "description": "Trend Following Pullback Entry - 추세 추종 풀백 진입 전략",
            "enabled": True,
            "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"],
            "parameters": {
                "position_size": 0.24,
                "leverage": 15,
                "signal_threshold": 3,
                "enable_hedge": False,
                "hedge_threshold": 1.5,
                "atr_period": 14,
                "atr_multiplier": 1.5,
                "partial_profit_ratio": 0.5,
                "partial_profit_target": 0.02,
                "max_holding_hours": 24
            },
            "risk_settings": {
                "max_positions": 4,
                "max_leverage": 20,
                "stop_loss_percent": 0.02,
                "max_daily_loss": 0.1,
                "max_drawdown": 0.25
            }
        },
        "GRID": {
            "name": "GRID",
            "description": "Grid Trading - 그리드 거래 전략",
            "enabled": False,
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "parameters": {
                "grid_levels": 10,
                "grid_spacing": 0.01,
                "position_size_per_grid": 0.05,
                "leverage": 5,
                "price_range_percent": 0.1,
                "rebalance_threshold": 0.05
            },
            "risk_settings": {
                "max_positions": 20,
                "max_leverage": 10,
                "stop_loss_percent": 0.05,
                "max_daily_loss": 0.05,
                "max_drawdown": 0.15
            }
        },
        "SCALPING": {
            "name": "SCALPING",
            "description": "Scalping - 단타 전략",
            "enabled": False,
            "symbols": ["BTCUSDT"],
            "parameters": {
                "position_size": 0.5,
                "leverage": 20,
                "entry_threshold": 0.001,
                "exit_threshold": 0.002,
                "max_holding_minutes": 30,
                "volume_filter": 1000000,
                "spread_limit": 0.0002
            },
            "risk_settings": {
                "max_positions": 1,
                "max_leverage": 25,
                "stop_loss_percent": 0.005,
                "max_daily_loss": 0.03,
                "max_drawdown": 0.1
            }
        },
        "MOMENTUM": {
            "name": "MOMENTUM",
            "description": "Momentum Breakout - 모멘텀 돌파 전략",
            "enabled": False,
            "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            "parameters": {
                "position_size": 0.3,
                "leverage": 10,
                "momentum_period": 20,
                "breakout_threshold": 0.02,
                "volume_increase_ratio": 2.0,
                "trailing_stop": 0.01,
                "time_filter": {"start": "09:00", "end": "17:00"}
            },
            "risk_settings": {
                "max_positions": 3,
                "max_leverage": 15,
                "stop_loss_percent": 0.015,
                "max_daily_loss": 0.08,
                "max_drawdown": 0.2
            }
        }
    }
    
    def __init__(self, config_file: str = "config/strategy_configs.json"):
        """초기화"""
        self.config_file = config_file
        self.strategies: Dict[str, StrategyConfig] = {}
        self.load_configs()
    
    def load_configs(self) -> None:
        """설정 파일에서 전략 설정 로드"""
        # 설정 파일이 없으면 기본 전략으로 초기화
        if not os.path.exists(self.config_file):
            self.initialize_default_strategies()
            self.save_configs()
            return
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for name, config_data in data.items():
                    self.strategies[name] = StrategyConfig.from_dict(config_data)
        except Exception as e:
            print(f"설정 로드 실패, 기본값 사용: {e}")
            self.initialize_default_strategies()
    
    def save_configs(self) -> None:
        """전략 설정을 파일에 저장"""
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        
        data = {}
        for name, config in self.strategies.items():
            data[name] = config.to_dict()
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def initialize_default_strategies(self) -> None:
        """기본 전략들로 초기화"""
        for name, config_data in self.DEFAULT_STRATEGIES.items():
            self.strategies[name] = StrategyConfig(**config_data)
    
    def get_strategy_config(self, name: str) -> Optional[StrategyConfig]:
        """특정 전략 설정 조회"""
        return self.strategies.get(name)
    
    def get_active_strategies(self) -> List[StrategyConfig]:
        """활성화된 전략 목록 조회"""
        return [config for config in self.strategies.values() if config.enabled]
    
    def update_strategy_config(self, name: str, updates: Dict[str, Any]) -> bool:
        """전략 설정 업데이트"""
        if name not in self.strategies:
            return False
        
        config = self.strategies[name]
        
        # 각 필드 업데이트
        if 'enabled' in updates:
            config.enabled = updates['enabled']
        if 'symbols' in updates:
            config.symbols = updates['symbols']
        if 'parameters' in updates:
            config.parameters.update(updates['parameters'])
        if 'risk_settings' in updates:
            config.risk_settings.update(updates['risk_settings'])
        
        self.save_configs()
        return True
    
    def add_custom_strategy(self, config: StrategyConfig) -> bool:
        """커스텀 전략 추가"""
        if config.name in self.strategies:
            return False
        
        self.strategies[config.name] = config
        self.save_configs()
        return True
    
    def remove_strategy(self, name: str) -> bool:
        """전략 제거 (기본 전략은 비활성화만)"""
        if name not in self.strategies:
            return False
        
        if name in self.DEFAULT_STRATEGIES:
            # 기본 전략은 삭제하지 않고 비활성화만
            self.strategies[name].enabled = False
        else:
            # 커스텀 전략은 완전 삭제
            del self.strategies[name]
        
        self.save_configs()
        return True
    
    def get_strategy_status(self) -> Dict[str, Any]:
        """전체 전략 상태 조회"""
        status = {
            "total": len(self.strategies),
            "active": len(self.get_active_strategies()),
            "strategies": {}
        }
        
        for name, config in self.strategies.items():
            status["strategies"][name] = {
                "enabled": config.enabled,
                "symbols": config.symbols,
                "description": config.description,
                "created_at": config.created_at.isoformat()
            }
        
        return status
    
    def validate_risk_settings(self, name: str) -> Dict[str, Any]:
        """리스크 설정 검증"""
        config = self.strategies.get(name)
        if not config:
            return {"valid": False, "errors": ["전략을 찾을 수 없습니다"]}
        
        errors = []
        warnings = []
        
        # 레버리지 검증
        leverage = config.parameters.get("leverage", 1)
        max_leverage = config.risk_settings.get("max_leverage", 20)
        
        if leverage > max_leverage:
            errors.append(f"레버리지({leverage})가 최대 허용치({max_leverage})를 초과합니다")
        
        if leverage > 15:
            warnings.append(f"높은 레버리지({leverage})는 위험할 수 있습니다")
        
        # 포지션 크기 검증
        position_size = config.parameters.get("position_size", 0)
        max_positions = config.risk_settings.get("max_positions", 1)
        
        if position_size * max_positions > 1.0:
            warnings.append("최대 포지션 시 자본의 100%를 초과할 수 있습니다")
        
        # 손실 한도 검증
        stop_loss = config.risk_settings.get("stop_loss_percent", 0)
        if stop_loss == 0:
            warnings.append("손절 설정이 없습니다")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }