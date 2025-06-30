#!/usr/bin/env python
"""
AlbraTrading Health Check Script
시스템 상태를 주기적으로 확인하고 문제 발생 시 자동 복구
"""

import os
import sys
import requests
import subprocess
import psutil
import time
import json
from datetime import datetime, timedelta
from pathlib import Path

# 프로젝트 루트 디렉토리 설정
PROJECT_ROOT = Path("/home/ubuntu/AlbraTrading")
LOG_DIR = PROJECT_ROOT / "logs"
STATE_FILE = PROJECT_ROOT / "data" / "system_state.json"

class HealthChecker:
    def __init__(self):
        self.dashboard_url = "http://localhost:5000/api/status"
        self.max_memory_percent = 85  # 메모리 사용률 임계값
        self.max_cpu_percent = 90     # CPU 사용률 임계값
        self.check_interval = 60      # 체크 간격 (초)
        
    def check_dashboard(self):
        """웹 대시보드 응답 확인"""
        try:
            response = requests.get(self.dashboard_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                # 마지막 업데이트 시간 확인
                last_update = data.get('last_update', '')
                if last_update:
                    last_time = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                    if datetime.utcnow() - last_time > timedelta(minutes=5):
                        return False, "대시보드 업데이트 지연"
                return True, "정상"
            return False, f"HTTP {response.status_code}"
        except requests.exceptions.RequestException as e:
            return False, f"연결 실패: {str(e)}"
    
    def check_process(self):
        """프로세스 상태 확인"""
        supervisor_running = False
        main_running = False
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if 'supervisor.py' in cmdline:
                    supervisor_running = True
                elif 'main.py' in cmdline and 'AlbraTrading' in cmdline:
                    main_running = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if not supervisor_running:
            return False, "Supervisor 프로세스 없음"
        if not main_running:
            return False, "Main 프로세스 없음"
        
        return True, "정상"
    
    def check_resources(self):
        """시스템 리소스 확인"""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory_percent = psutil.virtual_memory().percent
        disk_percent = psutil.disk_usage('/').percent
        
        issues = []
        if cpu_percent > self.max_cpu_percent:
            issues.append(f"CPU 사용률 높음: {cpu_percent}%")
        if memory_percent > self.max_memory_percent:
            issues.append(f"메모리 사용률 높음: {memory_percent}%")
        if disk_percent > 90:
            issues.append(f"디스크 사용률 높음: {disk_percent}%")
        
        if issues:
            return False, ", ".join(issues)
        return True, f"CPU: {cpu_percent}%, MEM: {memory_percent}%, DISK: {disk_percent}%"
    
    def check_logs(self):
        """최근 로그에서 에러 확인"""
        error_keywords = ['ERROR', 'CRITICAL', 'Connection lost', 'API error']
        recent_errors = []
        
        try:
            # 최근 5분간의 로그 확인
            five_minutes_ago = time.time() - 300
            
            for log_file in LOG_DIR.glob("*.log"):
                if log_file.stat().st_mtime > five_minutes_ago:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        # 파일 끝에서 최근 100줄만 확인
                        lines = f.readlines()[-100:]
                        for line in lines:
                            for keyword in error_keywords:
                                if keyword in line:
                                    recent_errors.append(line.strip()[:100])
                                    break
        except Exception as e:
            return False, f"로그 확인 실패: {str(e)}"
        
        if len(recent_errors) > 10:
            return False, f"최근 에러 {len(recent_errors)}개 발견"
        
        return True, "정상"
    
    def restart_service(self, reason=""):
        """서비스 재시작"""
        try:
            print(f"[{datetime.now()}] 서비스 재시작 시도. 이유: {reason}")
            
            # 로그 기록
            with open(LOG_DIR / "health_check.log", "a") as f:
                f.write(f"[{datetime.now()}] 재시작 - {reason}\n")
            
            # systemd 서비스 재시작
            result = subprocess.run(
                ["sudo", "systemctl", "restart", "albratrading"],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print("서비스 재시작 성공")
                # 30초 대기 후 상태 확인
                time.sleep(30)
                return True
            else:
                print(f"서비스 재시작 실패: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"재시작 중 오류: {str(e)}")
            return False
    
    def run_checks(self):
        """모든 체크 실행"""
        results = {
            'timestamp': datetime.now().isoformat(),
            'checks': {},
            'healthy': True
        }
        
        # 1. 대시보드 체크
        dashboard_ok, dashboard_msg = self.check_dashboard()
        results['checks']['dashboard'] = {
            'status': dashboard_ok,
            'message': dashboard_msg
        }
        
        # 2. 프로세스 체크
        process_ok, process_msg = self.check_process()
        results['checks']['process'] = {
            'status': process_ok,
            'message': process_msg
        }
        
        # 3. 리소스 체크
        resource_ok, resource_msg = self.check_resources()
        results['checks']['resources'] = {
            'status': resource_ok,
            'message': resource_msg
        }
        
        # 4. 로그 체크
        log_ok, log_msg = self.check_logs()
        results['checks']['logs'] = {
            'status': log_ok,
            'message': log_msg
        }
        
        # 전체 상태 결정
        results['healthy'] = all([
            dashboard_ok,
            process_ok,
            resource_ok,
            log_ok
        ])
        
        return results
    
    def save_status(self, results):
        """상태 저장"""
        try:
            status_file = LOG_DIR / "health_status.json"
            with open(status_file, 'w') as f:
                json.dump(results, f, indent=2)
        except Exception as e:
            print(f"상태 저장 실패: {str(e)}")
    
    def run(self):
        """메인 실행 루프"""
        print(f"[{datetime.now()}] Health Checker 시작")
        consecutive_failures = 0
        
        while True:
            try:
                results = self.run_checks()
                self.save_status(results)
                
                if not results['healthy']:
                    consecutive_failures += 1
                    failed_checks = [
                        f"{k}: {v['message']}" 
                        for k, v in results['checks'].items() 
                        if not v['status']
                    ]
                    reason = f"실패한 체크: {', '.join(failed_checks)}"
                    
                    print(f"[{datetime.now()}] 문제 감지 - {reason}")
                    
                    # 3회 연속 실패 시 재시작
                    if consecutive_failures >= 3:
                        self.restart_service(reason)
                        consecutive_failures = 0
                        time.sleep(60)  # 재시작 후 1분 대기
                else:
                    consecutive_failures = 0
                    print(f"[{datetime.now()}] 모든 체크 통과")
                
            except KeyboardInterrupt:
                print("Health Checker 종료")
                break
            except Exception as e:
                print(f"체크 중 오류: {str(e)}")
            
            time.sleep(self.check_interval)

if __name__ == "__main__":
    checker = HealthChecker()
    checker.run()