# src/monitoring/health_checker.py
"""시스템 건강 상태 체크 (읽기 전용, 안전함)"""
import asyncio
import time
import psutil
from datetime import datetime
from typing import Dict
import logging

logger = logging.getLogger(__name__)

class SystemHealthChecker:
    """시스템 건강 상태 모니터링 - 기존 거래에 영향 없음"""
    
    def __init__(self, components: Dict):
        self.components = components
        self.is_running = False
        
    async def check_health(self) -> Dict:
        """건강 상태 체크 (읽기만 함)"""
        results = {}
        
        # 1. Exchange 연결 체크
        try:
            start = time.time()
            server_time = await self.components['exchange'].get_server_time()
            latency = (time.time() - start) * 1000
            
            results['exchange'] = {
                'status': 'healthy' if latency < 1000 else 'degraded',
                'latency_ms': latency
            }
        except Exception as e:
            results['exchange'] = {'status': 'unhealthy', 'error': str(e)}
        
        # 2. 메모리 사용량
        process = psutil.Process()
        memory = process.memory_info()
        results['memory'] = {
            'status': 'healthy' if memory.rss < 1024*1024*1024 else 'warning',
            'rss_mb': memory.rss / 1024 / 1024
        }
        
        # 3. 포지션 불일치 체크
        if 'position_manager' in self.components:
            try:
                local_positions = self.components['position_manager'].get_active_positions()
                exchange_positions = await self.components['exchange'].get_positions()
                
                discrepancies = abs(len(local_positions) - len(exchange_positions))
                results['position_sync'] = {
                    'status': 'healthy' if discrepancies == 0 else 'warning',
                    'local_count': len(local_positions),
                    'exchange_count': len(exchange_positions)
                }
            except Exception as e:
                results['position_sync'] = {'status': 'error', 'error': str(e)}
        
        return results
    
    async def start_monitoring(self):
        """백그라운드 모니터링 시작"""
        self.is_running = True
        
        while self.is_running:
            try:
                health = await self.check_health()
                
                # 심각한 문제만 로그
                if health.get('exchange', {}).get('status') == 'unhealthy':
                    logger.error("거래소 연결 문제 감지!")
                
                if health.get('memory', {}).get('status') == 'warning':
                    logger.warning(f"메모리 사용량 높음: {health['memory']['rss_mb']:.0f}MB")
                
                await asyncio.sleep(60)  # 1분마다 체크
                
            except Exception as e:
                logger.error(f"Health check 오류: {e}")
                await asyncio.sleep(300)  # 오류 시 5분 대기
    
    def stop(self):
        """모니터링 중지"""
        self.is_running = False
