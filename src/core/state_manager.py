# src/core/state_manager.py
import json
import os
from typing import Any, Dict, Optional, List
from datetime import datetime
import shutil
import asyncio
import logging

logger = logging.getLogger(__name__)

class StateManager:
    """시스템 상태 관리 및 캐싱"""
    
    def __init__(self, state_dir: str = "state"):
        self.state_dir = state_dir
        self._ensure_state_directory()
        self._lock = asyncio.Lock()
    
    def _ensure_state_directory(self):
        """상태 디렉토리 확인 및 생성"""
        os.makedirs(self.state_dir, exist_ok=True)
        
        # 필수 파일 초기화
        required_files = [
            'position_cache.json',
            'strategy_state.json',
            'trade_history.json',
            'system_state.json'
        ]
        
        for filename in required_files:
            filepath = os.path.join(self.state_dir, filename)
            if not os.path.exists(filepath):
                with open(filepath, 'w') as f:
                    json.dump({
                        'data': {},
                        'metadata': {
                            'created_at': datetime.now().isoformat(),
                            'version': '1.0'
                        }
                    }, f, indent=2)
    
    async def save_state(self, filename: str, data: Dict[str, Any]):
        """상태 저장 (비동기)"""
        async with self._lock:
            try:
                filepath = os.path.join(self.state_dir, f"{filename}.json")
                
                # 백업 생성
                if os.path.exists(filepath):
                    backup_path = f"{filepath}.backup"
                    shutil.copy2(filepath, backup_path)
                
                # 메타데이터 추가
                wrapped_data = {
                    'data': data,
                    'metadata': {
                        'saved_at': datetime.now().isoformat(),
                        'version': '1.0'
                    }
                }
                
                # 원자적 쓰기
                temp_path = f"{filepath}.tmp"
                with open(temp_path, 'w') as f:
                    json.dump(wrapped_data, f, indent=2, ensure_ascii=False)
                
                os.replace(temp_path, filepath)
                logger.debug(f"상태 저장 완료: {filename}")
                
            except Exception as e:
                # 백업에서 복구
                backup_path = f"{filepath}.backup"
                if os.path.exists(backup_path):
                    os.replace(backup_path, filepath)
                    logger.error(f"상태 저장 실패, 백업에서 복구: {e}")
                raise e
    
    async def load_state(self, filename: str) -> Optional[Dict[str, Any]]:
        """상태 로드 (비동기)"""
        async with self._lock:
            try:
                filepath = os.path.join(self.state_dir, f"{filename}.json")
                
                if not os.path.exists(filepath):
                    return None
                
                with open(filepath, 'r') as f:
                    wrapped_data = json.load(f)
                
                # 버전 체크 가능
                if isinstance(wrapped_data, dict) and 'data' in wrapped_data:
                    return wrapped_data['data']
                else:
                    # 구버전 형식
                    return wrapped_data
                    
            except Exception as e:
                logger.error(f"상태 로드 실패 ({filename}): {e}")
                return None
    
    async def append_trade_history(self, trade: Dict[str, Any]):
        """거래 이력 추가"""
        history = await self.load_state('trade_history') or {'trades': []}
        
        if 'trades' not in history:
            history['trades'] = []
        
        # 거래 정보에 타임스탬프 추가
        trade_with_timestamp = {
            **trade,
            'timestamp': datetime.now().isoformat()
        }
        
        history['trades'].append(trade_with_timestamp)
        
        # 최근 1000개만 유지
        if len(history['trades']) > 1000:
            history['trades'] = history['trades'][-1000:]
        
        await self.save_state('trade_history', history)
    
    async def get_recent_trades(self, limit: int = 50) -> List[Dict]:
        """최근 거래 조회"""
        history = await self.load_state('trade_history') or {'trades': []}
        trades = history.get('trades', [])
        return trades[-limit:] if trades else []
    
    async def save_position_cache(self, positions: Dict[str, Any]):
        """포지션 캐시 저장"""
        await self.save_state('position_cache', positions)
    
    async def load_position_cache(self) -> Dict[str, Any]:
        """포지션 캐시 로드"""
        return await self.load_state('position_cache') or {}
    
    async def save_strategy_state(self, strategy_name: str, state: Dict[str, Any]):
        """전략 상태 저장"""
        all_strategies = await self.load_state('strategy_state') or {}
        all_strategies[strategy_name] = {
            'state': state,
            'updated_at': datetime.now().isoformat()
        }
        await self.save_state('strategy_state', all_strategies)
    
    async def load_strategy_state(self, strategy_name: str) -> Optional[Dict[str, Any]]:
        """전략 상태 로드"""
        all_strategies = await self.load_state('strategy_state') or {}
        strategy_data = all_strategies.get(strategy_name)
        
        if strategy_data and 'state' in strategy_data:
            return strategy_data['state']
        return None
    
    async def save_system_state(self, state: Dict[str, Any]):
        """시스템 전체 상태 저장"""
        await self.save_state('system_state', state)
    
    async def load_system_state(self) -> Dict[str, Any]:
        """시스템 전체 상태 로드"""
        return await self.load_state('system_state') or {}
    
    async def save_multi_account_state(self, state: Dict[str, Any]):
        """멀티 계좌 상태 저장"""
        await self.save_state('multi_account_state', state)
    
    async def load_multi_account_state(self) -> Dict[str, Any]:
        """멀티 계좌 상태 로드"""
        return await self.load_state('multi_account_state') or {}
    
    async def cleanup(self):
        """정리 작업"""
        # 필요시 추가 정리 작업
        logger.info("상태 관리자 정리 완료")