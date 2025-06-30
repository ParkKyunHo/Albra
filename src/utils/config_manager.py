# src/utils/config_manager.py
import yaml
import os
import json
from typing import Dict, Any, Optional, List
import asyncio
import logging

logger = logging.getLogger(__name__)

class ConfigManager:
    """설정 관리자"""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = config_path
        self.config = self._load_config()
        self.runtime_config = {}  # 런타임 설정
        self._lock = asyncio.Lock()
        
    def _load_config(self) -> Dict[str, Any]:
        """설정 파일 로드"""
        try:
            if not os.path.exists(self.config_path):
                logger.warning(f"설정 파일이 없습니다: {self.config_path}")
                return self._get_default_config()
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            logger.info(f"설정 파일 로드 완료: {self.config_path}")
            return config
            
        except Exception as e:
            logger.error(f"설정 파일 로드 실패: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """기본 설정 반환"""
        return {
            'system': {
                'mode': 'testnet',
                'log_level': 'INFO',
                'timezone': 'Asia/Seoul'
            },
            'monitoring': {
                'sync_interval': 300,
                'position_check_interval': 30
            },
            'strategies': {
                'tfpe': {
                    'leverage': 10,
                    'position_size': 20,
                    'stop_loss_atr': 2.0,
                    'take_profit_atr': 4.0,
                    'adx_min': 20,
                    'min_signal_interval': 8,
                    'max_positions': 3,
                    'signal_threshold': 3,
                    'min_momentum': 2.0,
                    'rsi_pullback_long': 40,
                    'rsi_pullback_short': 65,
                    'volume_spike': 1.5,
                    'ema_distance_max': 0.015,
                    'major_coins': ['BTCUSDT', 'ETHUSDT']
                }
            },
            'web_dashboard': {
                'enabled': True,
                'host': '0.0.0.0',
                'port': 5000
            }
        }
    
    def get_config(self) -> Dict[str, Any]:
        """전체 설정 반환"""
        return self.config
    
    def get(self, key: str, default: Any = None) -> Any:
        """특정 설정 값 조회 (점 표기법 지원)"""
        try:
            keys = key.split('.')
            value = self.config
            
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            
            return value
            
        except Exception as e:
            logger.error(f"설정 조회 실패 ({key}): {e}")
            return default
    
    def get_strategy_config(self, strategy_name: str) -> Dict[str, Any]:
        """전략 설정 조회"""
        return self.config.get('strategies', {}).get(strategy_name.lower(), {})
    
    def get_enabled_coins(self) -> List[str]:
        """활성화된 코인 목록 조회"""
        # 런타임 설정 우선
        if 'enabled_coins' in self.runtime_config:
            return self.runtime_config['enabled_coins']
        
        # 전략별 코인 목록 수집
        coins = set()
        for strategy_config in self.config.get('strategies', {}).values():
            if 'major_coins' in strategy_config:
                coins.update(strategy_config['major_coins'])
        
        return list(coins)
    
    def get_all_coins(self) -> Dict[str, Dict]:
        """모든 코인 설정 조회"""
        # 런타임 코인 설정
        if 'coins' in self.runtime_config:
            return self.runtime_config['coins']
        
        # 기본 설정으로 코인 목록 생성
        coins = {}
        enabled_coins = self.get_enabled_coins()
        
        for symbol in enabled_coins:
            coins[symbol] = {
                'enabled': True,
                'position_size': 20,
                'leverage': 10,
                'strategy': 'TFPE'
            }
        
        return coins
    
    def get_coin_config(self, symbol: str) -> Dict[str, Any]:
        """특정 코인 설정 조회"""
        all_coins = self.get_all_coins()
        return all_coins.get(symbol, {
            'enabled': False,
            'position_size': 20,
            'leverage': 10,
            'strategy': 'TFPE'
        })
    
    async def update_coin_config(self, symbol: str, config: Dict[str, Any]):
        """코인 설정 업데이트"""
        async with self._lock:
            if 'coins' not in self.runtime_config:
                self.runtime_config['coins'] = {}
            
            if symbol not in self.runtime_config['coins']:
                self.runtime_config['coins'][symbol] = {}
            
            self.runtime_config['coins'][symbol].update(config)
            await self._save_runtime_config()
            
            logger.info(f"코인 설정 업데이트: {symbol}")
    
    async def enable_coin(self, symbol: str, enabled: bool = True):
        """코인 활성화/비활성화"""
        await self.update_coin_config(symbol, {'enabled': enabled})
        
        # 활성 코인 목록 업데이트
        enabled_coins = self.get_enabled_coins()
        
        if enabled and symbol not in enabled_coins:
            enabled_coins.append(symbol)
        elif not enabled and symbol in enabled_coins:
            enabled_coins.remove(symbol)
        
        self.runtime_config['enabled_coins'] = enabled_coins
        await self._save_runtime_config()
    
    async def _save_runtime_config(self):
        """런타임 설정 저장"""
        try:
            runtime_path = 'config/runtime_config.json'
            os.makedirs(os.path.dirname(runtime_path), exist_ok=True)
            
            with open(runtime_path, 'w', encoding='utf-8') as f:
                json.dump(self.runtime_config, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"런타임 설정 저장 실패: {e}")
    
    def reload_config(self):
        """설정 파일 다시 로드"""
        self.config = self._load_config()
        logger.info("설정 파일 리로드 완료")
    
    def get_notification_config(self) -> Dict[str, Any]:
        """알림 설정 조회"""
        return self.config.get('notifications', {})
    
    def get_risk_config(self) -> Dict[str, Any]:
        """리스크 관리 설정 조회"""
        return self.config.get('risk_management', {})
    
    def get_telegram_config(self) -> Dict[str, Any]:
        """텔레그램 설정 조회"""
        telegram_config = self.config.get('telegram', {})
        
        # 환경 변수에서 가져오기
        import os
        if os.getenv('TELEGRAM_CHAT_ID'):
            telegram_config['chat_id'] = os.getenv('TELEGRAM_CHAT_ID')
        if os.getenv('TELEGRAM_BOT_TOKEN'):
            telegram_config['bot_token'] = os.getenv('TELEGRAM_BOT_TOKEN')
            
        return telegram_config