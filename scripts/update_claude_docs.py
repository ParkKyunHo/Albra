#!/usr/bin/env python3
"""
CLAUDE.md 자동 업데이트 스크립트
프로젝트의 현재 상태를 수집하여 CLAUDE.md 파일을 업데이트합니다.
"""

import os
import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

def get_git_info() -> Dict[str, str]:
    """Git 정보 수집"""
    info = {}
    try:
        # 현재 브랜치
        result = subprocess.run(['git', 'branch', '--show-current'], 
                              capture_output=True, text=True, cwd=PROJECT_ROOT)
        info['branch'] = result.stdout.strip() if result.returncode == 0 else 'unknown'
        
        # 최근 커밋
        result = subprocess.run(['git', 'log', '-1', '--oneline'], 
                              capture_output=True, text=True, cwd=PROJECT_ROOT)
        info['last_commit'] = result.stdout.strip() if result.returncode == 0 else 'No commits'
        
        # 변경된 파일 수
        result = subprocess.run(['git', 'status', '--porcelain'], 
                              capture_output=True, text=True, cwd=PROJECT_ROOT)
        if result.returncode == 0:
            changed_files = [line for line in result.stdout.strip().split('\n') if line]
            info['changed_files'] = len(changed_files)
        else:
            info['changed_files'] = 0
            
    except Exception as e:
        print(f"Git 정보 수집 실패: {e}")
        info = {'branch': 'unknown', 'last_commit': 'unknown', 'changed_files': 0}
    
    return info

def get_system_status() -> Dict[str, Any]:
    """시스템 상태 정보 수집"""
    status = {}
    
    # 설정 파일 읽기
    config_path = PROJECT_ROOT / 'config' / 'config.yaml'
    if config_path.exists():
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            
        # 활성 전략 확인
        active_strategies = []
        strategies_config = config.get('strategies', {})
        for strategy_name, strategy_config in strategies_config.items():
            if strategy_config.get('enabled', False):
                active_strategies.append(strategy_name.upper())
        
        status['active_strategies'] = active_strategies
        status['multi_account_enabled'] = config.get('multi_account', {}).get('enabled', False)
        status['mode'] = config.get('multi_account', {}).get('mode', 'single')
    
    # 상태 파일 확인
    state_dir = PROJECT_ROOT / 'state'
    if state_dir.exists():
        status['state_files'] = len(list(state_dir.glob('*.json')))
    
    # 로그 파일 확인
    log_dir = PROJECT_ROOT / 'logs'
    if log_dir.exists():
        recent_logs = sorted(log_dir.glob('*.log'), key=lambda x: x.stat().st_mtime, reverse=True)[:5]
        status['recent_logs'] = [log.name for log in recent_logs]
    
    return status

def get_performance_metrics() -> Dict[str, Any]:
    """성능 지표 수집"""
    metrics = {}
    
    # 거래 기록 파일 확인
    trade_history_path = PROJECT_ROOT / 'data' / 'performance' / 'trade_history.json'
    if trade_history_path.exists():
        try:
            with open(trade_history_path, 'r') as f:
                trades = json.load(f)
                
            if trades:
                # 승률 계산
                winning_trades = sum(1 for trade in trades if trade.get('profit', 0) > 0)
                total_trades = len(trades)
                win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
                
                metrics['total_trades'] = total_trades
                metrics['win_rate'] = f"{win_rate:.1f}%"
                metrics['last_trade_date'] = trades[-1].get('exit_time', 'Unknown') if trades else 'No trades'
        except Exception as e:
            print(f"거래 기록 읽기 실패: {e}")
    
    # 전략 통계 파일 확인
    stats_path = PROJECT_ROOT / 'data' / 'performance' / 'strategy_stats.json'
    if stats_path.exists():
        try:
            with open(stats_path, 'r') as f:
                stats = json.load(f)
                metrics.update(stats)
        except Exception as e:
            print(f"전략 통계 읽기 실패: {e}")
    
    return metrics

def update_claude_md():
    """CLAUDE.md 파일 업데이트"""
    
    # 정보 수집
    git_info = get_git_info()
    system_status = get_system_status()
    performance = get_performance_metrics()
    
    # 템플릿 읽기
    claude_md_path = PROJECT_ROOT / 'CLAUDE.md'
    with open(claude_md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 업데이트할 섹션 찾기 및 교체
    update_marker = "*최종 업데이트:"
    if update_marker in content:
        # 최종 업데이트 날짜 변경
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if line.startswith(update_marker):
                lines[i] = f"*최종 업데이트: {datetime.now().strftime('%Y년 %m월 %d일')}*"
                break
        content = '\n'.join(lines)
    
    # 시스템 상태 섹션 업데이트
    if "### 현재 운영 상태" in content:
        status_section = f"""### 현재 운영 상태
- **서버**: AWS EC2 (Ubuntu 22.04 LTS)
- **Python**: 3.12 (venv 가상환경)
- **운영 모드**: {system_status.get('mode', '단일')} 계좌 모드
- **활성 전략**: {', '.join(system_status.get('active_strategies', ['없음']))}
- **Git 브랜치**: {git_info['branch']}
- **변경된 파일**: {git_info['changed_files']}개"""
        
        # 정규식을 사용한 섹션 교체
        import re
        pattern = r"### 현재 운영 상태\n.*?(?=\n##|\Z)"
        content = re.sub(pattern, status_section, content, flags=re.DOTALL)
    
    # 성능 지표 섹션 업데이트 (있는 경우)
    if performance and "## 📊 성능 지표" in content:
        perf_section = f"""## 📊 성능 지표

### 현재 전략 성과
- 총 거래 수: {performance.get('total_trades', 0)}
- 승률: {performance.get('win_rate', 'N/A')}
- 마지막 거래: {performance.get('last_trade_date', 'N/A')}"""
        
        if 'sharpe_ratio' in performance:
            perf_section += f"\n- 샤프 비율: {performance['sharpe_ratio']:.2f}"
        if 'max_drawdown' in performance:
            perf_section += f"\n- 최대 낙폭: {performance['max_drawdown']:.1f}%"
        
        import re
        pattern = r"## 📊 성능 지표\n.*?(?=\n##|\Z)"
        content = re.sub(pattern, perf_section, content, flags=re.DOTALL)
    
    # 파일 저장
    with open(claude_md_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ CLAUDE.md 업데이트 완료")
    print(f"   - Git 브랜치: {git_info['branch']}")
    print(f"   - 활성 전략: {', '.join(system_status.get('active_strategies', ['없음']))}")
    print(f"   - 변경된 파일: {git_info['changed_files']}개")
    
    return True

def commit_and_push(message: str = None):
    """변경사항 커밋 및 푸시"""
    try:
        # CLAUDE.md 파일 스테이징
        subprocess.run(['git', 'add', 'CLAUDE.md'], cwd=PROJECT_ROOT, check=True)
        
        # 변경사항 확인
        result = subprocess.run(['git', 'status', '--porcelain', 'CLAUDE.md'], 
                              capture_output=True, text=True, cwd=PROJECT_ROOT)
        
        if not result.stdout.strip():
            print("📝 변경사항이 없습니다.")
            return False
        
        # 커밋 메시지 생성
        if not message:
            message = f"docs: CLAUDE.md 자동 업데이트 - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        # 커밋
        subprocess.run(['git', 'commit', '-m', message], cwd=PROJECT_ROOT, check=True)
        print(f"✅ 커밋 완료: {message}")
        
        # 푸시 (옵션)
        if '--push' in sys.argv:
            subprocess.run(['git', 'push'], cwd=PROJECT_ROOT, check=True)
            print("✅ GitHub에 푸시 완료")
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Git 작업 실패: {e}")
        return False

def main():
    """메인 실행 함수"""
    print("🔄 CLAUDE.md 업데이트 시작...")
    
    # CLAUDE.md 업데이트
    if update_claude_md():
        # Git 커밋 (--commit 플래그가 있을 때만)
        if '--commit' in sys.argv:
            commit_and_push()
        else:
            print("\n💡 팁: --commit 플래그를 추가하면 자동으로 커밋됩니다.")
            print("   예: python scripts/update_claude_docs.py --commit")
            print("   푸시까지 하려면: python scripts/update_claude_docs.py --commit --push")

if __name__ == "__main__":
    main()