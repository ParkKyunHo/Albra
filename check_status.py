#!/usr/bin/env python3
"""
AlbraTrading 시스템 상태 확인 스크립트
메인 계좌와 서브 계좌의 전략 실행 상태를 확인합니다.
"""

import json
import os
import sys
from datetime import datetime, timedelta
import glob

# 프로젝트 루트 경로
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

def check_system_status():
    print("=" * 60)
    print("AlbraTrading System Status Check")
    print("=" * 60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 1. 프로세스 확인
    print("1. Process Check:")
    try:
        import psutil
        python_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                cmdline = proc.info.get('cmdline', [])
                if cmdline and any('main.py' in arg for arg in cmdline):
                    python_processes.append(proc)
                    print(f"   ✓ Found main.py process (PID: {proc.info['pid']})")
        
        if not python_processes:
            print("   ✗ No main.py process found - System may not be running!")
    except ImportError:
        print("   ⚠️ psutil not installed - Cannot check processes")
    except Exception as e:
        print(f"   ⚠️ Process check error: {e}")

    # 2. 로그 파일 확인
    print("\n2. Recent Logs:")
    log_dir = os.path.join(project_root, "logs")
    if os.path.exists(log_dir):
        log_files = glob.glob(os.path.join(log_dir, "*.log"))
        if log_files:
            # 최신 로그 파일 찾기
            latest_log = max(log_files, key=os.path.getmtime)
            log_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(latest_log))
            
            print(f"   Latest log: {os.path.basename(latest_log)}")
            print(f"   Last updated: {log_age.total_seconds():.0f} seconds ago")
            
            # 최근 로그 내용 확인
            try:
                with open(latest_log, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    recent_lines = lines[-20:]  # 마지막 20줄
                    
                    # 주요 이벤트 찾기
                    strategy_status = {}
                    errors = []
                    
                    for line in recent_lines:
                        if "전략 초기화 완료" in line:
                            if "TFPE" in line:
                                strategy_status["TFPE"] = "Initialized"
                            elif "ZLMACD" in line:
                                strategy_status["ZLMACD_ICHIMOKU"] = "Initialized"
                        elif "포지션 진입" in line or "Position opened" in line:
                            print(f"   📈 Recent trade: {line.strip()[-100:]}")
                        elif "ERROR" in line:
                            errors.append(line.strip()[-100:])
                    
                    if strategy_status:
                        print("\n   Active Strategies:")
                        for strat, status in strategy_status.items():
                            print(f"   - {strat}: {status}")
                    
                    if errors:
                        print("\n   Recent Errors:")
                        for err in errors[-3:]:  # 최근 3개만
                            print(f"   ⚠️ {err}")
            except Exception as e:
                print(f"   Error reading log: {e}")
        else:
            print("   ✗ No log files found")
    else:
        print("   ✗ Log directory not found")

    # 3. 상태 파일 확인
    print("\n3. State Files:")
    state_dir = os.path.join(project_root, "state")
    if os.path.exists(state_dir):
        # 포지션 캐시 확인
        position_cache = os.path.join(state_dir, "position_cache.json")
        if os.path.exists(position_cache):
            try:
                with open(position_cache, 'r') as f:
                    positions = json.load(f)
                    active_positions = sum(1 for p in positions.values() if p.get('status') == 'ACTIVE')
                    print(f"   Active positions: {active_positions}")
                    
                    for key, pos in positions.items():
                        if pos.get('status') == 'ACTIVE':
                            symbol = pos.get('symbol', 'Unknown')
                            side = pos.get('side', 'Unknown')
                            strategy = pos.get('strategy_name', 'Unknown')
                            print(f"   - {symbol}: {side} (Strategy: {strategy})")
            except Exception as e:
                print(f"   Error reading positions: {e}")
        
        # 시스템 상태 확인
        system_state = os.path.join(state_dir, "system_state.json")
        if os.path.exists(system_state):
            try:
                with open(system_state, 'r') as f:
                    state = json.load(f)
                    if 'last_check' in state:
                        last_check = datetime.fromisoformat(state['last_check'])
                        age = (datetime.now() - last_check).total_seconds()
                        print(f"\n   System last check: {age:.0f} seconds ago")
                        if age > 300:  # 5분 이상
                            print("   ⚠️ System may be inactive!")
            except Exception as e:
                print(f"   Error reading system state: {e}")

    # 4. 설정 확인
    print("\n4. Configuration:")
    config_file = os.path.join(project_root, "config", "config.yaml")
    if os.path.exists(config_file):
        try:
            import yaml
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                
            # 멀티 계좌 설정
            multi_account = config.get('multi_account', {})
            print(f"   Multi-account mode: {multi_account.get('mode', 'single')}")
            
            # 활성화된 전략
            strategies = config.get('strategies', {})
            print("\n   Strategy Status:")
            
            # TFPE (메인 계좌)
            tfpe = strategies.get('tfpe', {})
            if tfpe.get('enabled'):
                print(f"   ✓ TFPE: Enabled (Main Account)")
                print(f"     - Leverage: {tfpe.get('leverage')}x")
                print(f"     - Position size: {tfpe.get('position_size')}%")
                print(f"     - Symbols: {', '.join(tfpe.get('major_coins', [])[:3])}...")
            else:
                print("   ✗ TFPE: Disabled")
            
            # ZLMACD (서브 계좌)
            if multi_account.get('mode') == 'multi' or multi_account.get('enabled'):
                for sub in multi_account.get('sub_accounts', []):
                    if sub.get('enabled'):
                        account_id = sub.get('account_id')
                        strategies_list = sub.get('strategy_preferences', [])
                        print(f"\n   ✓ Sub Account '{account_id}': Enabled")
                        print(f"     - Strategies: {', '.join(strategies_list)}")
                        print(f"     - Max positions: {sub.get('max_positions')}")
                        print(f"     - Position size: {sub.get('position_size')}%")
            
        except Exception as e:
            print(f"   Error reading config: {e}")
    
    # 5. 웹 대시보드 확인
    print("\n5. Web Dashboard:")
    try:
        import requests
        response = requests.get("http://localhost:5000", timeout=2)
        if response.status_code == 200:
            print("   ✓ Dashboard is running at http://localhost:5000")
        else:
            print(f"   ⚠️ Dashboard returned status: {response.status_code}")
    except requests.ConnectionError:
        print("   ✗ Dashboard not accessible (may not be running)")
    except Exception as e:
        print(f"   ⚠️ Dashboard check error: {e}")

    # 6. 최근 이벤트 (Event Bus)
    print("\n6. Recent Events:")
    event_log = os.path.join(project_root, "logs", "event_log.json")
    if os.path.exists(event_log):
        try:
            with open(event_log, 'r') as f:
                # 파일이 크므로 마지막 부분만 읽기
                f.seek(0, 2)  # 파일 끝으로
                file_size = f.tell()
                f.seek(max(0, file_size - 5000))  # 마지막 5KB
                content = f.read()
                
                # JSON 라인 파싱
                lines = content.strip().split('\n')
                recent_events = []
                for line in lines[-10:]:  # 마지막 10개 이벤트
                    try:
                        event = json.loads(line)
                        recent_events.append(event)
                    except:
                        pass
                
                if recent_events:
                    for event in recent_events[-5:]:  # 최근 5개만 표시
                        event_type = event.get('event_type', 'Unknown')
                        timestamp = event.get('timestamp', '')
                        print(f"   - {timestamp}: {event_type}")
        except Exception as e:
            print(f"   Error reading events: {e}")
    
    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)
    print("• Check logs with: view_logs.bat")
    print("• View dashboard at: http://localhost:5000")
    print("• Telegram notifications should appear if system is active")
    print("• System status reports are sent every 30 minutes")

if __name__ == "__main__":
    check_system_status()
