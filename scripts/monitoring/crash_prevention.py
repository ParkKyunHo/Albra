#!/usr/bin/env python3
"""
AlbraTrading Crash Prevention System
메모리 누수, 리소스 고갈 등으로 인한 크래시 예방
"""

import os
import sys
import psutil
import gc
import tracemalloc
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import json

# 프로젝트 루트 디렉토리 설정
PROJECT_ROOT = Path("/home/ubuntu/AlbraTrading")
sys.path.insert(0, str(PROJECT_ROOT))

# 로깅 설정
LOG_DIR = PROJECT_ROOT / "logs" / "monitoring"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "crash_prevention.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class CrashPrevention:
    """크래시 예방 시스템"""
    
    def __init__(self):
        self.memory_threshold_warning = 70  # 메모리 경고 임계값 (%)
        self.memory_threshold_critical = 85  # 메모리 위험 임계값 (%)
        self.file_descriptor_threshold = 80  # 파일 디스크립터 사용률 임계값 (%)
        self.connection_threshold = 1000  # 네트워크 연결 수 임계값
        
        # 메모리 추적
        tracemalloc.start()
        self.memory_snapshots = []
        self.max_snapshots = 10
        
        # 상태 저장
        self.state_file = PROJECT_ROOT / "state" / "crash_prevention.json"
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        
    def check_memory_usage(self) -> Dict:
        """메모리 사용량 확인"""
        memory = psutil.virtual_memory()
        process = psutil.Process()
        
        # 시스템 전체 메모리
        system_memory = {
            'total': memory.total,
            'available': memory.available,
            'percent': memory.percent,
            'used': memory.used
        }
        
        # 프로세스 메모리
        process_memory = process.memory_info()
        process_percent = (process_memory.rss / memory.total) * 100
        
        result = {
            'system': system_memory,
            'process': {
                'rss': process_memory.rss,
                'vms': process_memory.vms,
                'percent': process_percent
            },
            'status': 'normal'
        }
        
        # 상태 판단
        if memory.percent >= self.memory_threshold_critical:
            result['status'] = 'critical'
            result['action'] = 'immediate_gc_and_cleanup'
        elif memory.percent >= self.memory_threshold_warning:
            result['status'] = 'warning'
            result['action'] = 'gc_collect'
        
        return result
    
    def check_memory_leaks(self) -> Dict:
        """메모리 누수 확인"""
        # 현재 스냅샷 생성
        snapshot = tracemalloc.take_snapshot()
        self.memory_snapshots.append({
            'time': datetime.now(),
            'snapshot': snapshot
        })
        
        # 최대 개수 유지
        if len(self.memory_snapshots) > self.max_snapshots:
            self.memory_snapshots.pop(0)
        
        # 메모리 증가 추세 분석
        if len(self.memory_snapshots) >= 2:
            old_snapshot = self.memory_snapshots[0]['snapshot']
            stats = snapshot.compare_to(old_snapshot, 'lineno')
            
            # 가장 많이 증가한 상위 10개
            top_stats = stats[:10]
            
            leaks = []
            for stat in top_stats:
                if stat.size_diff > 1024 * 1024:  # 1MB 이상 증가
                    leaks.append({
                        'file': stat.traceback.format()[0],
                        'size_diff': stat.size_diff,
                        'size': stat.size,
                        'count_diff': stat.count_diff
                    })
            
            return {
                'potential_leaks': leaks,
                'total_diff': sum(stat.size_diff for stat in stats),
                'time_span': (datetime.now() - self.memory_snapshots[0]['time']).total_seconds()
            }
        
        return {'potential_leaks': [], 'total_diff': 0, 'time_span': 0}
    
    def check_file_descriptors(self) -> Dict:
        """파일 디스크립터 사용량 확인"""
        try:
            process = psutil.Process()
            
            # 열린 파일 수
            open_files = len(process.open_files())
            
            # 네트워크 연결 수
            connections = len(process.connections())
            
            # 시스템 제한
            import resource
            soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
            
            # 사용률 계산
            total_fds = open_files + connections
            usage_percent = (total_fds / soft_limit) * 100
            
            result = {
                'open_files': open_files,
                'connections': connections,
                'total': total_fds,
                'limit': soft_limit,
                'usage_percent': usage_percent,
                'status': 'normal'
            }
            
            # 상태 판단
            if usage_percent >= self.file_descriptor_threshold:
                result['status'] = 'warning'
                result['action'] = 'close_unused_connections'
            
            if connections > self.connection_threshold:
                result['status'] = 'critical'
                result['action'] = 'connection_cleanup_required'
            
            return result
            
        except Exception as e:
            logger.error(f"파일 디스크립터 확인 실패: {e}")
            return {'error': str(e)}
    
    def check_disk_space(self) -> Dict:
        """디스크 공간 확인"""
        disk = psutil.disk_usage('/')
        logs_dir = PROJECT_ROOT / "logs"
        
        # 로그 디렉토리 크기 계산
        log_size = 0
        try:
            for path in logs_dir.rglob('*'):
                if path.is_file():
                    log_size += path.stat().st_size
        except Exception as e:
            logger.error(f"로그 크기 계산 실패: {e}")
        
        result = {
            'total': disk.total,
            'used': disk.used,
            'free': disk.free,
            'percent': disk.percent,
            'log_size': log_size,
            'status': 'normal'
        }
        
        # 상태 판단
        if disk.percent >= 90:
            result['status'] = 'critical'
            result['action'] = 'log_rotation_required'
        elif disk.percent >= 80:
            result['status'] = 'warning'
        
        return result
    
    def perform_garbage_collection(self, force: bool = False) -> Dict:
        """가비지 컬렉션 수행"""
        before_memory = psutil.Process().memory_info().rss
        
        # GC 수행
        collected = {}
        collected['gen0'] = gc.collect(0)
        
        if force:
            collected['gen1'] = gc.collect(1)
            collected['gen2'] = gc.collect(2)
        
        after_memory = psutil.Process().memory_info().rss
        
        return {
            'collected': collected,
            'memory_freed': before_memory - after_memory,
            'memory_before': before_memory,
            'memory_after': after_memory
        }
    
    def cleanup_old_logs(self, days: int = 7) -> Dict:
        """오래된 로그 파일 정리"""
        logs_dir = PROJECT_ROOT / "logs"
        cutoff_date = datetime.now() - timedelta(days=days)
        
        deleted_files = []
        total_size = 0
        
        try:
            for log_file in logs_dir.rglob('*.log*'):
                if log_file.is_file():
                    mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                    if mtime < cutoff_date:
                        size = log_file.stat().st_size
                        log_file.unlink()
                        deleted_files.append(str(log_file))
                        total_size += size
        except Exception as e:
            logger.error(f"로그 정리 실패: {e}")
        
        return {
            'deleted_count': len(deleted_files),
            'freed_space': total_size,
            'deleted_files': deleted_files[:10]  # 처음 10개만
        }
    
    def rotate_large_logs(self, max_size: int = 100 * 1024 * 1024) -> Dict:
        """큰 로그 파일 로테이션"""
        import gzip
        import shutil
        
        logs_dir = PROJECT_ROOT / "logs"
        rotated_files = []
        
        try:
            for log_file in logs_dir.rglob('*.log'):
                if log_file.is_file() and log_file.stat().st_size > max_size:
                    # 압축 파일명
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    gz_file = log_file.with_suffix(f'.log.{timestamp}.gz')
                    
                    # 압축
                    with open(log_file, 'rb') as f_in:
                        with gzip.open(gz_file, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    
                    # 원본 파일 비우기
                    open(log_file, 'w').close()
                    
                    rotated_files.append({
                        'original': str(log_file),
                        'compressed': str(gz_file),
                        'size': log_file.stat().st_size
                    })
        except Exception as e:
            logger.error(f"로그 로테이션 실패: {e}")
        
        return {'rotated_count': len(rotated_files), 'files': rotated_files}
    
    def analyze_and_prevent(self) -> Dict:
        """전체 분석 및 예방 조치"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'checks': {},
            'actions': []
        }
        
        # 1. 메모리 확인
        memory_status = self.check_memory_usage()
        report['checks']['memory'] = memory_status
        
        if memory_status['status'] == 'critical':
            # 즉시 GC 수행
            gc_result = self.perform_garbage_collection(force=True)
            report['actions'].append({
                'type': 'garbage_collection',
                'result': gc_result
            })
            
            # 로그 정리
            log_cleanup = self.cleanup_old_logs(days=3)
            report['actions'].append({
                'type': 'log_cleanup',
                'result': log_cleanup
            })
        
        # 2. 메모리 누수 확인
        leak_status = self.check_memory_leaks()
        report['checks']['memory_leaks'] = leak_status
        
        # 3. 파일 디스크립터 확인
        fd_status = self.check_file_descriptors()
        report['checks']['file_descriptors'] = fd_status
        
        # 4. 디스크 공간 확인
        disk_status = self.check_disk_space()
        report['checks']['disk'] = disk_status
        
        if disk_status['status'] in ['warning', 'critical']:
            # 로그 로테이션
            rotation_result = self.rotate_large_logs()
            report['actions'].append({
                'type': 'log_rotation',
                'result': rotation_result
            })
        
        # 상태 저장
        self.save_report(report)
        
        return report
    
    def save_report(self, report: Dict):
        """분석 리포트 저장"""
        try:
            # 최근 리포트만 유지 (최대 100개)
            reports = []
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    reports = data.get('reports', [])
            
            reports.append(report)
            reports = reports[-100:]  # 최근 100개만
            
            with open(self.state_file, 'w') as f:
                json.dump({'reports': reports}, f, indent=2)
                
        except Exception as e:
            logger.error(f"리포트 저장 실패: {e}")

def run_prevention_check():
    """예방 체크 실행"""
    prevention = CrashPrevention()
    report = prevention.analyze_and_prevent()
    
    # 리포트 출력
    logger.info("=== Crash Prevention Report ===")
    logger.info(f"Timestamp: {report['timestamp']}")
    
    for check_name, check_result in report['checks'].items():
        status = check_result.get('status', 'unknown')
        logger.info(f"{check_name}: {status}")
        
        if status in ['warning', 'critical']:
            logger.warning(f"  Action: {check_result.get('action', 'none')}")
    
    if report['actions']:
        logger.info("Actions taken:")
        for action in report['actions']:
            logger.info(f"  - {action['type']}: {action['result']}")
    
    return report

if __name__ == "__main__":
    run_prevention_check()