#!/usr/bin/env python3
"""
AlbraTrading System Watchdog
시스템 크래시 방지 및 자동 복구 모니터링 데몬
"""

import os
import sys
import time
import json
import psutil
import logging
import signal
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Tuple, Optional
import asyncio
import aiohttp

# 프로젝트 루트 디렉토리 설정
PROJECT_ROOT = Path("/home/ubuntu/AlbraTrading")
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.notification_manager import SmartNotificationManager

# 로깅 설정
LOG_DIR = PROJECT_ROOT / "logs" / "watchdog"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "watchdog.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SystemWatchdog:
    """시스템 상태 모니터링 및 자동 복구"""
    
    def __init__(self):
        self.service_name = "albratrading-multi"
        self.check_interval = 30  # 30초마다 체크
        self.cpu_threshold = 85  # CPU 사용률 임계값
        self.memory_threshold = 80  # 메모리 사용률 임계값
        self.disk_threshold = 90  # 디스크 사용률 임계값
        self.api_timeout = 10  # API 응답 타임아웃
        self.restart_cooldown = 300  # 재시작 후 5분 대기
        self.max_restarts = 3  # 1시간 내 최대 재시작 횟수
        
        self.last_restart = None
        self.restart_count = 0
        self.restart_history = []
        self.running = True
        
        # 상태 파일
        self.state_file = PROJECT_ROOT / "state" / "watchdog_state.json"
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 알림 매니저
        self.notification_manager = None
        
    async def init_notification(self):
        """알림 매니저 초기화"""
        try:
            self.notification_manager = SmartNotificationManager()
            await self.notification_manager.send_notification(
                "🔍 Watchdog 시작",
                "시스템 모니터링이 시작되었습니다.",
                alert_type="SYSTEM"
            )
        except Exception as e:
            logger.error(f"알림 매니저 초기화 실패: {e}")
    
    def load_state(self):
        """저장된 상태 로드"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    self.restart_history = [
                        datetime.fromisoformat(ts) for ts in state.get('restart_history', [])
                    ]
                    self.restart_count = state.get('restart_count', 0)
                    if state.get('last_restart'):
                        self.last_restart = datetime.fromisoformat(state['last_restart'])
        except Exception as e:
            logger.error(f"상태 로드 실패: {e}")
    
    def save_state(self):
        """현재 상태 저장"""
        try:
            state = {
                'restart_history': [ts.isoformat() for ts in self.restart_history],
                'restart_count': self.restart_count,
                'last_restart': self.last_restart.isoformat() if self.last_restart else None,
                'last_check': datetime.now().isoformat()
            }
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"상태 저장 실패: {e}")
    
    def check_service_status(self) -> Tuple[bool, str]:
        """systemd 서비스 상태 확인"""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", self.service_name],
                capture_output=True,
                text=True
            )
            is_active = result.stdout.strip() == "active"
            
            if not is_active:
                # 상세 상태 확인
                status_result = subprocess.run(
                    ["systemctl", "status", self.service_name],
                    capture_output=True,
                    text=True
                )
                return False, f"서비스 비활성: {result.stdout.strip()}"
            
            return True, "서비스 활성"
        except Exception as e:
            return False, f"서비스 상태 확인 실패: {e}"
    
    def check_process_health(self) -> Tuple[bool, str]:
        """프로세스 상태 확인"""
        try:
            python_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
                try:
                    if proc.info['name'] == 'python' or proc.info['name'] == 'python3':
                        cmdline = ' '.join(proc.info['cmdline'] or [])
                        if 'main_multi_account.py' in cmdline or 'main.py' in cmdline:
                            python_processes.append(proc)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if not python_processes:
                return False, "트레이딩 프로세스 없음"
            
            # 프로세스 나이 확인 (너무 새로운 프로세스는 크래시 루프 가능성)
            for proc in python_processes:
                age = time.time() - proc.info['create_time']
                if age < 60:  # 1분 미만
                    return False, f"프로세스가 너무 새로움 (나이: {age:.0f}초)"
            
            return True, f"{len(python_processes)}개 프로세스 정상"
        except Exception as e:
            return False, f"프로세스 확인 실패: {e}"
    
    def check_resource_usage(self) -> Tuple[bool, str]:
        """시스템 리소스 사용률 확인"""
        try:
            issues = []
            
            # CPU 사용률
            cpu_percent = psutil.cpu_percent(interval=1)
            if cpu_percent > self.cpu_threshold:
                issues.append(f"CPU 과부하: {cpu_percent}%")
            
            # 메모리 사용률
            memory = psutil.virtual_memory()
            if memory.percent > self.memory_threshold:
                issues.append(f"메모리 과부하: {memory.percent}%")
            
            # 디스크 사용률
            disk = psutil.disk_usage('/')
            if disk.percent > self.disk_threshold:
                issues.append(f"디스크 부족: {disk.percent}%")
            
            # 스왑 사용 확인
            swap = psutil.swap_memory()
            if swap.percent > 50:
                issues.append(f"스왑 사용 높음: {swap.percent}%")
            
            if issues:
                return False, ", ".join(issues)
            
            return True, f"CPU: {cpu_percent}%, MEM: {memory.percent}%, DISK: {disk.percent}%"
        except Exception as e:
            return False, f"리소스 확인 실패: {e}"
    
    async def check_api_health(self) -> Tuple[bool, str]:
        """API 연결 상태 확인"""
        try:
            # localhost API 상태 확인
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'http://localhost:5000/api/status',
                    timeout=aiohttp.ClientTimeout(total=self.api_timeout)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        last_update = data.get('last_update')
                        if last_update:
                            # 업데이트 시간 확인
                            update_time = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                            age = (datetime.utcnow() - update_time).total_seconds()
                            if age > 300:  # 5분 이상 오래됨
                                return False, f"API 업데이트 지연: {age:.0f}초"
                        return True, "API 정상"
                    else:
                        return False, f"API 응답 오류: HTTP {response.status}"
        except asyncio.TimeoutError:
            return False, "API 응답 시간 초과"
        except Exception as e:
            return False, f"API 확인 실패: {e}"
    
    def check_log_errors(self) -> Tuple[bool, str]:
        """최근 로그의 심각한 오류 확인"""
        try:
            error_patterns = [
                "CRITICAL",
                "ERROR.*Connection lost",
                "ERROR.*API rate limit",
                "Traceback",
                "SystemExit",
                "KeyboardInterrupt"
            ]
            
            log_files = [
                PROJECT_ROOT / "logs" / "trading.log",
                PROJECT_ROOT / "logs" / "systemd_multi_error.log"
            ]
            
            recent_errors = 0
            critical_errors = []
            
            for log_file in log_files:
                if log_file.exists():
                    # 최근 5분간의 로그만 확인
                    five_minutes_ago = time.time() - 300
                    if log_file.stat().st_mtime > five_minutes_ago:
                        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                            # 파일 끝에서 1000줄 확인
                            lines = f.readlines()[-1000:]
                            for line in lines:
                                for pattern in error_patterns:
                                    if pattern in line:
                                        recent_errors += 1
                                        if "CRITICAL" in line or "Traceback" in line:
                                            critical_errors.append(line.strip()[:100])
            
            if critical_errors:
                return False, f"심각한 오류 {len(critical_errors)}개 발견"
            elif recent_errors > 50:
                return False, f"최근 오류 {recent_errors}개 (임계값 초과)"
            
            return True, f"로그 정상 (최근 오류: {recent_errors}개)"
        except Exception as e:
            return False, f"로그 확인 실패: {e}"
    
    async def perform_health_check(self) -> Dict:
        """전체 헬스 체크 수행"""
        results = {
            'timestamp': datetime.now().isoformat(),
            'checks': {},
            'healthy': True,
            'issues': []
        }
        
        # 1. 서비스 상태
        service_ok, service_msg = self.check_service_status()
        results['checks']['service'] = {'ok': service_ok, 'message': service_msg}
        if not service_ok:
            results['issues'].append(service_msg)
        
        # 2. 프로세스 상태
        process_ok, process_msg = self.check_process_health()
        results['checks']['process'] = {'ok': process_ok, 'message': process_msg}
        if not process_ok:
            results['issues'].append(process_msg)
        
        # 3. 리소스 사용률
        resource_ok, resource_msg = self.check_resource_usage()
        results['checks']['resources'] = {'ok': resource_ok, 'message': resource_msg}
        if not resource_ok:
            results['issues'].append(resource_msg)
        
        # 4. API 상태
        api_ok, api_msg = await self.check_api_health()
        results['checks']['api'] = {'ok': api_ok, 'message': api_msg}
        if not api_ok:
            results['issues'].append(api_msg)
        
        # 5. 로그 오류
        log_ok, log_msg = self.check_log_errors()
        results['checks']['logs'] = {'ok': log_ok, 'message': log_msg}
        if not log_ok:
            results['issues'].append(log_msg)
        
        # 전체 상태 판단
        results['healthy'] = all([
            service_ok,
            process_ok,
            resource_ok,
            # API와 로그는 경고만
        ])
        
        return results
    
    def can_restart(self) -> bool:
        """재시작 가능 여부 확인"""
        now = datetime.now()
        
        # 마지막 재시작으로부터 쿨다운 확인
        if self.last_restart:
            cooldown_elapsed = (now - self.last_restart).total_seconds()
            if cooldown_elapsed < self.restart_cooldown:
                logger.warning(f"재시작 쿨다운 중 (남은 시간: {self.restart_cooldown - cooldown_elapsed:.0f}초)")
                return False
        
        # 1시간 내 재시작 횟수 확인
        one_hour_ago = now - timedelta(hours=1)
        recent_restarts = [ts for ts in self.restart_history if ts > one_hour_ago]
        
        if len(recent_restarts) >= self.max_restarts:
            logger.error(f"1시간 내 재시작 횟수 초과: {len(recent_restarts)}/{self.max_restarts}")
            return False
        
        return True
    
    async def restart_service(self, reason: str):
        """서비스 재시작"""
        try:
            if not self.can_restart():
                logger.warning("재시작 조건 미충족")
                return False
            
            logger.info(f"서비스 재시작 시작: {reason}")
            
            # 알림 전송
            if self.notification_manager:
                await self.notification_manager.send_notification(
                    "🔄 서비스 재시작",
                    f"사유: {reason}\n재시작 횟수: {len(self.restart_history) + 1}회",
                    alert_type="SYSTEM"
                )
            
            # systemd 재시작
            result = subprocess.run(
                ["sudo", "systemctl", "restart", self.service_name],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                self.last_restart = datetime.now()
                self.restart_history.append(self.last_restart)
                self.restart_count += 1
                self.save_state()
                
                logger.info("서비스 재시작 성공")
                
                # 30초 대기 후 상태 확인
                await asyncio.sleep(30)
                
                # 재시작 후 상태 확인
                service_ok, _ = self.check_service_status()
                if service_ok:
                    if self.notification_manager:
                        await self.notification_manager.send_notification(
                            "✅ 재시작 완료",
                            "서비스가 정상적으로 재시작되었습니다.",
                            alert_type="SYSTEM"
                        )
                    return True
                else:
                    logger.error("재시작 후 서비스 활성화 실패")
                    return False
            else:
                logger.error(f"재시작 명령 실패: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"재시작 중 오류: {e}")
            return False
    
    def cleanup_old_history(self):
        """오래된 재시작 기록 정리"""
        cutoff = datetime.now() - timedelta(hours=24)
        self.restart_history = [ts for ts in self.restart_history if ts > cutoff]
    
    async def run(self):
        """메인 실행 루프"""
        logger.info("System Watchdog 시작")
        
        # 초기화
        self.load_state()
        await self.init_notification()
        
        consecutive_failures = 0
        
        while self.running:
            try:
                # 헬스 체크
                results = await self.perform_health_check()
                
                # 결과 로깅
                logger.info(f"헬스 체크 완료: {'정상' if results['healthy'] else '문제 감지'}")
                for check, result in results['checks'].items():
                    logger.debug(f"  {check}: {result['message']}")
                
                if not results['healthy']:
                    consecutive_failures += 1
                    logger.warning(f"연속 실패 횟수: {consecutive_failures}")
                    
                    # 3회 연속 실패 시 재시작 시도
                    if consecutive_failures >= 3:
                        issues_text = "\n".join(results['issues'])
                        await self.restart_service(f"헬스 체크 3회 연속 실패:\n{issues_text}")
                        consecutive_failures = 0
                else:
                    consecutive_failures = 0
                
                # 오래된 기록 정리
                self.cleanup_old_history()
                self.save_state()
                
            except KeyboardInterrupt:
                logger.info("Watchdog 종료 신호 수신")
                break
            except Exception as e:
                logger.error(f"Watchdog 실행 중 오류: {e}", exc_info=True)
            
            # 다음 체크까지 대기
            await asyncio.sleep(self.check_interval)
        
        logger.info("System Watchdog 종료")
    
    def signal_handler(self, signum, frame):
        """시그널 핸들러"""
        logger.info(f"시그널 {signum} 수신")
        self.running = False

async def main():
    """메인 함수"""
    watchdog = SystemWatchdog()
    
    # 시그널 핸들러 등록
    signal.signal(signal.SIGINT, watchdog.signal_handler)
    signal.signal(signal.SIGTERM, watchdog.signal_handler)
    
    try:
        await watchdog.run()
    except Exception as e:
        logger.error(f"Watchdog 실행 실패: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())