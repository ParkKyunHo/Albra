# src/strategies/strategy_factory.py
"""
전략 팩토리 - 전략 생성 및 관리
원본 기능을 유지하면서 Donchian 지원 추가
"""

import logging
import importlib
import inspect
import os
from typing import Dict, List, Optional, Type, Any
from .base_strategy import BaseStrategy
from .tfpe_strategy import TFPEStrategy
from .momentum_strategy import MomentumStrategy
from .zlhma_ema_cross_strategy import ZLHMAEMACrossStrategy
from .zlmacd_ichimoku_strategy import ZLMACDIchimokuStrategy
from ..utils.config_manager import ConfigManager

logger = logging.getLogger(__name__)

class StrategyFactory:
    """전략 팩토리 클래스"""
    
    def __init__(self):
        self._strategies: Dict[str, Type[BaseStrategy]] = {}
        self._instances: Dict[str, BaseStrategy] = {}
        self.config_manager = ConfigManager()
        self.config = self.config_manager.config
        
        # 전략 등록 (현재는 TFPE만)
        self._register_default_strategies()
        
        # 자동 등록 (옵션)
        if self.config.get('system', {}).get('auto_register_strategies', False):
            self._auto_register_strategies()
    
    def _register_default_strategies(self):
        """기본 전략 등록"""
        self.register_strategy('TFPE', TFPEStrategy)
        self.register_strategy('tfpe', TFPEStrategy)  # 소문자 호환성
        self.register_strategy('MOMENTUM', MomentumStrategy)
        self.register_strategy('momentum', MomentumStrategy)  # 소문자 호환성
        
        # ZLHMA EMA Cross 전략 추가
        self.register_strategy('ZLHMA_EMA_CROSS', ZLHMAEMACrossStrategy)
        self.register_strategy('zlhma_ema_cross', ZLHMAEMACrossStrategy)  # 소문자 호환성
        
        # ZL MACD + Ichimoku 전략 추가
        self.register_strategy('ZLMACD_ICHIMOKU', ZLMACDIchimokuStrategy)
        self.register_strategy('zlmacd_ichimoku', ZLMACDIchimokuStrategy)  # 소문자 호환성
        
        logger.info("기본 전략 등록 완료: TFPE, MOMENTUM, ZLHMA_EMA_CROSS, ZLMACD_ICHIMOKU")
    
    def _auto_register_strategies(self) -> None:
        """strategies 폴더의 모든 전략 자동 등록"""
        strategies_dir = os.path.dirname(__file__)
        excluded_files = ['base_strategy.py', 'strategy_factory.py', 'strategy_config.py']
        
        for filename in os.listdir(strategies_dir):
            if filename.endswith('_strategy.py') and filename not in excluded_files:
                module_name = filename[:-3]  # .py 제거
                try:
                    # 모듈 동적 임포트
                    module = importlib.import_module(f'.{module_name}', package='src.strategies')
                    
                    # 모듈 내의 모든 클래스 검사
                    for name, obj in inspect.getmembers(module):
                        if (inspect.isclass(obj) and 
                            issubclass(obj, BaseStrategy) and 
                            obj is not BaseStrategy and
                            not inspect.isabstract(obj)):
                            # 전략 이름 추출
                            strategy_name = name.replace('Strategy', '').upper()
                            self.register_strategy(strategy_name, obj)
                            logger.info(f"전략 자동 등록: {strategy_name} ({name})")
                            
                except Exception as e:
                    logger.error(f"전략 모듈 로드 실패 {module_name}: {e}")
    
    def register_strategy(self, name: str, strategy_class: Type[BaseStrategy]):
        """전략 등록"""
        self._strategies[name] = strategy_class
        logger.debug(f"전략 등록: {name}")
    
    def create_strategy(self, name: str, binance_api, position_manager, 
                       custom_config: Optional[Dict] = None) -> Optional[BaseStrategy]:
        """개별 전략 생성"""
        try:
            # 전략 클래스 찾기
            strategy_class = self._strategies.get(name.upper()) or self._strategies.get(name.lower())
            
            if not strategy_class:
                logger.error(f"전략을 찾을 수 없습니다: {name}")
                return None
            
            # 설정 로드
            if custom_config:
                strategy_config = custom_config
            else:
                strategy_config = self.config.get('strategies', {}).get(name.lower(), {})
            
            if not strategy_config:
                logger.error(f"전략 설정이 없습니다: {name}")
                return None
            
            # 활성화 확인 (기본값: True)
            if not strategy_config.get('enabled', True):
                logger.info(f"전략이 비활성화되어 있습니다: {name}")
                return None
            
            # 전략 모드 로깅 (TFPE의 경우)
            if name.upper() == 'TFPE':
                trend_mode = strategy_config.get('trend_mode', 'ma')
                logger.info(f"TFPE 전략 생성 중... (모드: {trend_mode})")
                
                # Donchian 파라미터 확인
                if trend_mode == 'donchian':
                    self._validate_donchian_params(strategy_config)
            
            # 전략 인스턴스 생성
            strategy = strategy_class(
                binance_api=binance_api,
                position_manager=position_manager,
                config=strategy_config,
                config_manager=self.config_manager
            )
            
            # 인스턴스 저장
            self._instances[name] = strategy
            
            logger.info(f"✅ {name} 전략 생성 완료")
            return strategy
            
        except Exception as e:
            logger.error(f"전략 생성 실패 ({name}): {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _validate_donchian_params(self, config: Dict):
        """Donchian 파라미터 검증"""
        required_params = ['dc_period', 'price_position_high', 'price_position_low']
        missing_params = [p for p in required_params if p not in config]
        
        if missing_params:
            logger.warning(f"Donchian 파라미터 누락: {missing_params}")
            logger.warning("기본값을 사용합니다.")
            
            # 기본값 설정
            defaults = {
                'dc_period': 20,
                'price_position_high': 0.7,
                'price_position_low': 0.3,
                'channel_width_threshold': 0.05
            }
            
            for param, value in defaults.items():
                if param not in config:
                    config[param] = value
                    logger.info(f"{param} = {value} (기본값)")
    
    def create_active_strategies(self, binance_api, position_manager) -> List[BaseStrategy]:
        """활성화된 모든 전략 생성"""
        strategies = []
        
        # 설정에서 활성 전략 찾기
        strategies_config = self.config.get('strategies', {})
        
        for strategy_name, strategy_config in strategies_config.items():
            # 활성화 상태 확인 (기본값: True)
            if strategy_config.get('enabled', True):
                strategy = self.create_strategy(
                    name=strategy_name,
                    binance_api=binance_api,
                    position_manager=position_manager,
                    custom_config=strategy_config
                )
                
                if strategy:
                    strategies.append(strategy)
        
        logger.info(f"총 {len(strategies)}개 전략 활성화")
        return strategies
    
    def get_strategy(self, name: str) -> Optional[BaseStrategy]:
        """생성된 전략 인스턴스 반환"""
        return self._instances.get(name)
    
    def get_strategy_info(self, name: str) -> Dict:
        """전략 정보 반환"""
        strategy_class = self._strategies.get(name.upper()) or self._strategies.get(name.lower())
        
        if not strategy_class:
            return {'error': f'전략을 찾을 수 없습니다: {name}'}
        
        # 기본 정보
        info = {
            'name': name,
            'class': strategy_class.__name__,
            'description': strategy_class.__doc__ or '설명 없음'
        }
        
        # TFPE 전략의 경우 추가 정보
        if name.upper() == 'TFPE':
            config = self.config.get('strategies', {}).get('tfpe', {})
            trend_mode = config.get('trend_mode', 'ma')
            
            info.update({
                'mode': trend_mode,
                'mode_description': {
                    'donchian': 'Donchian Channel 기반 추세 감지',
                    'ma': '이동평균선 기반 추세 감지 (레거시)'
                }.get(trend_mode, '알 수 없음'),
                'parameters': {
                    'leverage': config.get('leverage', 15),
                    'position_size': config.get('position_size', 24),
                    'signal_threshold': config.get('signal_threshold', 3)
                }
            })
            
            if trend_mode == 'donchian':
                info['donchian_params'] = {
                    'period': config.get('dc_period', 20),
                    'price_position_long': config.get('price_position_low', 0.3),
                    'price_position_short': config.get('price_position_high', 0.7),
                    'channel_width': config.get('channel_width_threshold', 0.05)
                }
        
        # ZLHMA EMA CROSS 전략의 경우 추가 정보
        elif name.upper() == 'ZLHMA_EMA_CROSS':
            config = self.config.get('strategies', {}).get('zlhma_ema_cross', {})
            
            info.update({
                'description': 'Zero Lag Hull MA + EMA 50/200 크로스 전략',
                'indicators': {
                    'zlhma_period': config.get('zlhma_period', 14),
                    'fast_ema': config.get('fast_ema_period', 50),
                    'slow_ema': config.get('slow_ema_period', 200),
                    'adx_threshold': config.get('adx_threshold', 25)
                },
                'risk_management': {
                    'stop_loss_atr': config.get('stop_loss_atr', 1.5),
                    'take_profit_atr': config.get('take_profit_atr', 5.0),
                    'pyramiding_enabled': config.get('pyramiding_enabled', True)
                },
                'parameters': {
                    'leverage': config.get('leverage', 10),
                    'position_size': config.get('position_size', 20),
                    'signal_strength_threshold': config.get('signal_strength_threshold', 2.5)
                }
            })
        
        # ZL MACD + Ichimoku 전략의 경우 추가 정보
        elif name.upper() == 'ZLMACD_ICHIMOKU':
            config = self.config.get('strategies', {}).get('zlmacd_ichimoku', {})
            
            info.update({
                'description': 'ZL MACD + Ichimoku Cloud 결합 전략 (비트코인 1시간봉 특화)',
                'indicators': {
                    'zlmacd': {
                        'fast': config.get('zlmacd_fast', 12),
                        'slow': config.get('zlmacd_slow', 26),
                        'signal': config.get('zlmacd_signal', 9)
                    },
                    'ichimoku': {
                        'tenkan': config.get('tenkan_period', 9),
                        'kijun': config.get('kijun_period', 26),
                        'senkou_b': config.get('senkou_b_period', 52)
                    },
                    'adx_threshold': config.get('adx_threshold', 25)
                },
                'risk_management': {
                    'stop_loss_atr': config.get('stop_loss_atr', 1.5),
                    'take_profit_atr': config.get('take_profit_atr', 5.0),
                    'trailing_stop': config.get('trailing_stop_activation', 0.03),
                    'partial_exits': len(config.get('partial_exit_levels', [])),
                    'pyramiding_levels': len(config.get('pyramiding_levels', [])),
                    'daily_loss_limit': config.get('daily_loss_limit_pct', 3.0)
                },
                'parameters': {
                    'leverage': config.get('leverage', 10),
                    'position_size': config.get('position_size', 20),
                    'symbols': config.get('symbols', ['BTCUSDT']),
                    'timeframe': '1h',
                    'use_kelly': config.get('use_kelly', True)
                }
            })
        
        return info
    
    def get_available_strategies(self) -> List[str]:
        """사용 가능한 전략 목록"""
        return list(set(name.upper() for name in self._strategies.keys()))
    
    def validate_strategy(self, name: str) -> Dict[str, Any]:
        """전략 검증"""
        result = {
            'valid': False,
            'errors': [],
            'warnings': []
        }
        
        # 전략 존재 확인
        if name.upper() not in [s.upper() for s in self._strategies.keys()]:
            result['errors'].append(f"전략이 존재하지 않습니다: {name}")
            return result
        
        # 설정 확인
        config = self.config.get('strategies', {}).get(name.lower(), {})
        if not config:
            result['errors'].append(f"전략 설정이 없습니다: {name}")
            return result
        
        # TFPE 전략 검증
        if name.upper() == 'TFPE':
            # 필수 파라미터 확인
            required = ['leverage', 'position_size', 'stop_loss_atr', 'take_profit_atr']
            missing = [p for p in required if p not in config]
            
            if missing:
                result['errors'].append(f"필수 파라미터 누락: {missing}")
            
            # Donchian 모드 검증
            if config.get('trend_mode') == 'donchian':
                dc_params = ['dc_period', 'price_position_high', 'price_position_low']
                dc_missing = [p for p in dc_params if p not in config]
                
                if dc_missing:
                    result['warnings'].append(f"Donchian 파라미터 누락 (기본값 사용): {dc_missing}")
            
            # 심볼 확인
            if not config.get('major_coins'):
                result['warnings'].append("거래 심볼이 설정되지 않았습니다")
        
        # ZLHMA EMA CROSS 전략 검증
        elif name.upper() == 'ZLHMA_EMA_CROSS':
            # 필수 파라미터 확인
            required = ['leverage', 'position_size', 'zlhma_period', 
                        'fast_ema_period', 'slow_ema_period', 'adx_threshold']
            missing = [p for p in required if p not in config]
            
            if missing:
                result['errors'].append(f"필수 파라미터 누락: {missing}")
            
            # 심볼 확인
            if not config.get('symbols'):
                result['warnings'].append("거래 심볼이 설정되지 않았습니다")
            
            # ADX 임계값 검증
            adx = config.get('adx_threshold', 25)
            if adx < 20:
                result['warnings'].append(f"ADX 임계값이 너무 낮습니다 ({adx}). 권장: 25 이상")
        
        # ZL MACD + Ichimoku 전략 검증
        elif name.upper() == 'ZLMACD_ICHIMOKU':
            # 필수 파라미터 확인
            required = ['leverage', 'position_size', 'zlmacd_fast', 'zlmacd_slow', 
                        'zlmacd_signal', 'tenkan_period', 'kijun_period', 
                        'senkou_b_period', 'adx_threshold']
            missing = [p for p in required if p not in config]
            
            if missing:
                result['errors'].append(f"필수 파라미터 누락: {missing}")
            
            # 심볼 확인 (비트코인만 지원)
            symbols = config.get('symbols', ['BTCUSDT'])
            if symbols != ['BTCUSDT']:
                result['warnings'].append("이 전략은 BTCUSDT 1시간봉에 특화되어 있습니다")
            
            # Kelly Criterion 확인
            if config.get('use_kelly', True):
                if config.get('kelly_lookback', 100) < 20:
                    result['warnings'].append("Kelly lookback이 너무 짧습니다. 최소 20개 거래 필요")
        
        result['valid'] = len(result['errors']) == 0
        return result
    
    async def stop_all_strategies(self):
        """모든 활성 전략 중지"""
        for name, strategy in self._instances.items():
            try:
                if hasattr(strategy, 'stop'):
                    await strategy.stop()
                    logger.info(f"{name} 전략 중지")
            except Exception as e:
                logger.error(f"전략 중지 실패 ({name}): {e}")
        
        self._instances.clear()
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """전체 전략 성과 요약"""
        summary = {
            'total_strategies': len(self._strategies),
            'active_strategies': len(self._instances),
            'strategies': {}
        }
        
        for name, strategy in self._instances.items():
            if hasattr(strategy, 'get_strategy_info'):
                summary['strategies'][name] = strategy.get_strategy_info()
            else:
                summary['strategies'][name] = {'name': name, 'status': 'active'}
        
        return summary


# 전역 팩토리 인스턴스
_strategy_factory = None

def get_strategy_factory() -> StrategyFactory:
    """전략 팩토리 싱글톤 반환"""
    global _strategy_factory
    if _strategy_factory is None:
        _strategy_factory = StrategyFactory()
    return _strategy_factory