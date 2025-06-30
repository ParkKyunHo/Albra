#!/usr/bin/env python3
"""
프로젝트 상태 자동 업데이트 스크립트
현재 프로젝트의 상태를 수집하여 .claude/PROJECT_STATUS.md를 업데이트합니다.
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
CLAUDE_DIR = PROJECT_ROOT / '.claude'
sys.path.append(str(PROJECT_ROOT))

def ensure_claude_dir():
    """Claude 디렉토리 확인 및 생성"""
    CLAUDE_DIR.mkdir(exist_ok=True)

def get_git_status() -> Dict[str, Any]:
    """Git 상태 정보 수집"""
    status = {}
    
    try:
        # 현재 브랜치
        result = subprocess.run(['git', 'branch', '--show-current'], 
                              capture_output=True, text=True, cwd=PROJECT_ROOT)
        status['current_branch'] = result.stdout.strip()
        
        # 최근 커밋 5개
        result = subprocess.run(['git', 'log', '--oneline', '-5'], 
                              capture_output=True, text=True, cwd=PROJECT_ROOT)
        status['recent_commits'] = result.stdout.strip().split('\n') if result.stdout else []
        
        # 변경된 파일
        result = subprocess.run(['git', 'status', '--porcelain'], 
                              capture_output=True, text=True, cwd=PROJECT_ROOT)
        if result.stdout:
            changed_files = result.stdout.strip().split('\n')
            status['changed_files'] = len(changed_files)
            status['changed_files_list'] = changed_files[:10]  # 최대 10개만
        else:
            status['changed_files'] = 0
            status['changed_files_list'] = []
            
        # 마지막 커밋 시간
        result = subprocess.run(['git', 'log', '-1', '--format=%cd', '--date=format:%Y-%m-%d %H:%M:%S'], 
                              capture_output=True, text=True, cwd=PROJECT_ROOT)
        status['last_commit_date'] = result.stdout.strip()
        
    except Exception as e:
        print(f"Git 정보 수집 실패: {e}")
        status = {
            'current_branch': 'unknown',
            'recent_commits': [],
            'changed_files': 0,
            'changed_files_list': [],
            'last_commit_date': 'unknown'
        }
    
    return status

def get_project_structure() -> Dict[str, int]:
    """프로젝트 구조 분석"""
    structure = {
        'python_files': 0,
        'test_files': 0,
        'doc_files': 0,
        'config_files': 0,
        'total_lines': 0
    }
    
    for root, dirs, files in os.walk(PROJECT_ROOT):
        # 제외할 디렉토리
        dirs[:] = [d for d in dirs if d not in ['.git', 'venv', '__pycache__', 'logs', 'cache_data']]
        
        for file in files:
            if file.endswith('.py'):
                structure['python_files'] += 1
                if 'test' in file.lower():
                    structure['test_files'] += 1
                    
                # 라인 수 계산
                try:
                    file_path = Path(root) / file
                    with open(file_path, 'r', encoding='utf-8') as f:
                        structure['total_lines'] += len(f.readlines())
                except:
                    pass
                    
            elif file.endswith('.md'):
                structure['doc_files'] += 1
            elif file.endswith(('.yaml', '.yml', '.json', '.toml')):
                structure['config_files'] += 1
    
    return structure

def read_todo_status() -> Dict[str, List[str]]:
    """TODO.md 파일에서 작업 상태 읽기"""
    todo_file = CLAUDE_DIR / 'TODO.md'
    todo_status = {
        'critical': [],
        'high': [],
        'medium': [],
        'low': [],
        'completed_recent': []
    }
    
    if not todo_file.exists():
        return todo_status
    
    try:
        with open(todo_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # 각 섹션에서 TODO 항목 추출 (간단한 파싱)
        lines = content.split('\n')
        current_section = None
        
        for line in lines:
            if '긴급 (Critical)' in line:
                current_section = 'critical'
            elif '높음 (High Priority)' in line:
                current_section = 'high'
            elif '중간 (Medium Priority)' in line:
                current_section = 'medium'
            elif '낮음 (Low Priority)' in line:
                current_section = 'low'
            elif '완료됨' in line:
                current_section = 'completed_recent'
            elif current_section and line.strip().startswith('- [ ]'):
                todo_status[current_section].append(line.strip()[6:])
            elif current_section == 'completed_recent' and line.strip().startswith('- [x]'):
                todo_status[current_section].append(line.strip()[6:])
                
    except Exception as e:
        print(f"TODO 파일 읽기 실패: {e}")
    
    return todo_status

def get_system_components() -> Dict[str, Dict]:
    """시스템 구성 요소 분석"""
    components = {
        'strategies': {},
        'core_modules': {},
        'monitoring': {},
        'utils': {}
    }
    
    # 전략 분석
    strategies_dir = PROJECT_ROOT / 'src' / 'strategies'
    if strategies_dir.exists():
        for file in strategies_dir.glob('*_strategy.py'):
            if file.name != 'base_strategy.py':
                components['strategies'][file.stem] = {
                    'file': file.name,
                    'size': file.stat().st_size
                }
    
    # 핵심 모듈 분석
    core_dir = PROJECT_ROOT / 'src' / 'core'
    if core_dir.exists():
        for file in core_dir.glob('*.py'):
            if not file.name.startswith('__'):
                components['core_modules'][file.stem] = {
                    'file': file.name,
                    'modified': datetime.fromtimestamp(file.stat().st_mtime).strftime('%Y-%m-%d')
                }
    
    return components

def analyze_recent_errors() -> Dict[str, any]:
    """최근 오류 분석"""
    error_summary = {
        'total': 0,
        'critical': 0,
        'recent': []
    }
    
    # 로그 디렉토리에서 최근 오류 확인
    logs_dir = PROJECT_ROOT / 'logs'
    if logs_dir.exists():
        for log_file in logs_dir.glob('*_error.log'):
            try:
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()[-10:]  # 마지막 10줄
                    for line in lines:
                        if 'ERROR' in line or 'CRITICAL' in line:
                            error_summary['total'] += 1
                            if 'CRITICAL' in line:
                                error_summary['critical'] += 1
                            error_summary['recent'].append(line.strip()[:100])
            except:
                pass
    
    return error_summary

def update_project_status():
    """PROJECT_STATUS.md 업데이트"""
    ensure_claude_dir()
    
    # 정보 수집
    git_status = get_git_status()
    project_structure = get_project_structure()
    todo_status = read_todo_status()
    system_components = get_system_components()
    error_summary = analyze_recent_errors()
    
    # 현재 시간
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # PROJECT_STATUS.md 내용 생성
    content = f"""# AlbraTrading 프로젝트 상태

## 📊 프로젝트 개요
- **프로젝트명**: AlbraTrading
- **설명**: AWS EC2에서 24/7 운영되는 바이낸스 자동 트레이딩 시스템
- **시작일**: 2025년 이전
- **현재 버전**: v2.0 (Multi-Account Edition)
- **마지막 업데이트**: {now}

## 🎯 프로젝트 목표
1. 안정적인 24/7 자동 트레이딩 시스템 운영
2. 멀티 계좌/멀티 전략 지원
3. 실시간 모니터링 및 리스크 관리
4. Claude Code를 통한 효율적인 개발 워크플로우

## 📊 프로젝트 통계
- **Python 파일**: {project_structure['python_files']}개
- **테스트 파일**: {project_structure['test_files']}개
- **문서 파일**: {project_structure['doc_files']}개
- **설정 파일**: {project_structure['config_files']}개
- **총 코드 라인**: {project_structure['total_lines']:,}줄

## 🔀 Git 상태
- **현재 브랜치**: {git_status['current_branch']}
- **변경된 파일**: {git_status['changed_files']}개
- **마지막 커밋**: {git_status['last_commit_date']}

### 최근 커밋
"""
    
    for commit in git_status['recent_commits'][:5]:
        content += f"- {commit}\n"
    
    if git_status['changed_files'] > 0:
        content += "\n### 변경된 파일\n"
        for file in git_status['changed_files_list'][:10]:
            content += f"- {file}\n"
    
    # 시스템 구성 요소 추가
    content += f"""
## 🔧 시스템 구성 요소

### 활성 전략 ({len(system_components['strategies'])}개)
"""
    for name, info in system_components['strategies'].items():
        content += f"- **{name}**: {info['file']}\n"
    
    content += f"""
### 핵심 모듈 ({len(system_components['core_modules'])}개)
"""
    for name, info in list(system_components['core_modules'].items())[:5]:
        content += f"- **{name}**: 최종 수정 {info['modified']}\n"
    
    # 오류 상태 추가
    if error_summary['total'] > 0:
        content += f"""
## 🚨 오류 현황
- **총 오류**: {error_summary['total']}개
- **치명적 오류**: {error_summary['critical']}개
"""
        if error_summary['recent']:
            content += "### 최근 오류\n"
            for error in error_summary['recent'][:3]:
                content += f"- {error}\n"
    
    # TODO 상태 추가
    content += f"""
## 📈 진행 상황

### 🚨 긴급 작업 ({len(todo_status['critical'])}개)
"""
    for item in todo_status['critical'][:3]:
        content += f"- {item}\n"
    
    content += f"""
### 🔴 높은 우선순위 ({len(todo_status['high'])}개)
"""
    for item in todo_status['high'][:3]:
        content += f"- {item}\n"
    
    content += f"""
### 🟡 중간 우선순위 ({len(todo_status['medium'])}개)
"""
    for item in todo_status['medium'][:3]:
        content += f"- {item}\n"
    
    content += f"""
### ✅ 최근 완료된 작업
"""
    for item in todo_status['completed_recent'][:5]:
        content += f"- {item}\n"
    
    content += f"""
## 🏗️ 시스템 아키텍처
- **운영 환경**: AWS EC2 (Ubuntu 22.04)
- **런타임**: Python 3.12 (venv)
- **주요 전략**: TFPE (Trend Following with Price Extremes)
- **데이터베이스**: SQLite (trading_bot.db)
- **모니터링**: 텔레그램 봇 + 웹 대시보드

## 🔧 개발 환경
- **Git 브랜치**: {git_status['current_branch']}
- **원격 저장소**: GitHub (https://github.com/ParkKyunHo/Albra.git)
- **자동화**: GitHub Actions, Git Hooks
- **문서화**: CLAUDE.md 자동 업데이트

## 📝 참고사항
- EC2 배포 시 `scripts/safe_deploy_v2.sh` 사용
- 실시간 거래 중 코드 수정 자제
- 모든 API 키는 `.env` 파일에 보관
- 작업 추적: `.claude/` 디렉토리 참조

---
*자동 생성: {now}*
"""
    
    # 파일 저장
    status_file = CLAUDE_DIR / 'PROJECT_STATUS.md'
    with open(status_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ PROJECT_STATUS.md 업데이트 완료")
    print(f"   - Git 브랜치: {git_status['current_branch']}")
    print(f"   - Python 파일: {project_structure['python_files']}개")
    print(f"   - 변경된 파일: {git_status['changed_files']}개")
    print(f"   - TODO 항목: {len(todo_status['critical'] + todo_status['high'] + todo_status['medium'])}개")

def update_session_log(message: str = None):
    """세션 로그에 항목 추가"""
    session_log = CLAUDE_DIR / 'SESSION_LOG.md'
    
    if not session_log.exists():
        return
    
    # 현재 시간
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 로그 항목 추가
    if message:
        with open(session_log, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 현재 세션 섹션 찾기
        today = datetime.now().strftime('%Y-%m-%d')
        session_marker = f"## 세션: {today}"
        
        if session_marker in content:
            # 오늘 세션에 추가
            parts = content.split(session_marker, 1)
            if len(parts) == 2:
                # 작업 요약 섹션 찾기
                if "### 작업 요약" in parts[1]:
                    # 적절한 위치에 추가
                    lines = parts[1].split('\n')
                    for i, line in enumerate(lines):
                        if line.startswith('### 다음 작업'):
                            lines.insert(i, f"\n- {now}: {message}")
                            break
                    parts[1] = '\n'.join(lines)
                
                content = session_marker.join(parts)
        else:
            # 새 세션 추가
            new_session = f"""
## 세션: {today}

### 작업 요약
- {now}: {message}

### 다음 작업
- [ ] 계속 진행

---
"""
            content = content.replace("## 이전 세션 기록", new_session + "\n## 이전 세션 기록")
        
        with open(session_log, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"📝 세션 로그 업데이트: {message}")

def main():
    """메인 실행 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description='프로젝트 상태 업데이트')
    parser.add_argument('--log', type=str, help='세션 로그에 추가할 메시지')
    parser.add_argument('--commit', action='store_true', help='변경사항을 Git에 커밋')
    
    args = parser.parse_args()
    
    print("🔄 프로젝트 상태 업데이트 시작...")
    
    # 프로젝트 상태 업데이트
    update_project_status()
    
    # 세션 로그 업데이트
    if args.log:
        update_session_log(args.log)
    
    # Git 커밋
    if args.commit:
        try:
            subprocess.run(['git', 'add', '.claude/'], cwd=PROJECT_ROOT, check=True)
            subprocess.run(['git', 'commit', '-m', f'docs: 프로젝트 상태 업데이트 - {datetime.now().strftime("%Y-%m-%d %H:%M")}'], 
                         cwd=PROJECT_ROOT, check=True)
            print("✅ Git 커밋 완료")
        except subprocess.CalledProcessError:
            print("📝 변경사항이 없거나 커밋 실패")

if __name__ == "__main__":
    main()