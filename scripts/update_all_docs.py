#!/usr/bin/env python3
"""
통합 문서 업데이트 스크립트
커밋 시 SESSION_LOG.md, CLAUDE.md, PROJECT_STATUS.md를 자동으로 업데이트합니다.
"""

import os
import sys
import subprocess
import json
import yaml
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Set

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent.parent
CLAUDE_DIR = PROJECT_ROOT / '.claude'
sys.path.append(str(PROJECT_ROOT))

# 한국 표준시(KST) 설정
KST = timezone(timedelta(hours=9))

# 중요 디렉토리 정의
IMPORTANT_DIRS = {
    'src/',
    'src/core/',
    'src/strategies/',
    'config/',
    'scripts/'
}

# CLAUDE.md 업데이트가 필요한 디렉토리
CLAUDE_UPDATE_DIRS = {
    'src/',
    'src/core/',
    'src/strategies/',
    'config/'
}

def get_last_commit_info():
    """최근 커밋 정보 가져오기"""
    try:
        # 커밋 해시
        commit_hash = subprocess.run(
            ['git', 'log', '-1', '--format=%h'],
            capture_output=True, text=True, cwd=PROJECT_ROOT
        ).stdout.strip()
        
        # 커밋 메시지
        commit_msg = subprocess.run(
            ['git', 'log', '-1', '--format=%s'],
            capture_output=True, text=True, cwd=PROJECT_ROOT
        ).stdout.strip()
        
        # 커밋 시간
        commit_time = subprocess.run(
            ['git', 'log', '-1', '--format=%ci'],
            capture_output=True, text=True, cwd=PROJECT_ROOT
        ).stdout.strip()
        
        # 변경된 파일들
        changed_files = subprocess.run(
            ['git', 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD'],
            capture_output=True, text=True, cwd=PROJECT_ROOT
        ).stdout.strip().split('\n')
        
        return {
            'hash': commit_hash,
            'message': commit_msg,
            'time': commit_time,
            'files': [f for f in changed_files if f]
        }
    except Exception as e:
        print(f"커밋 정보 가져오기 실패: {e}")
        return None

def should_update_claude_md(changed_files: List[str]) -> bool:
    """CLAUDE.md 업데이트가 필요한지 확인"""
    for file in changed_files:
        for important_dir in CLAUDE_UPDATE_DIRS:
            if file.startswith(important_dir):
                return True
    return False

def should_update_project_status(changed_files: List[str]) -> bool:
    """PROJECT_STATUS.md 업데이트가 필요한지 확인"""
    # 중요한 변경사항이 있을 때만 업데이트
    for file in changed_files:
        for important_dir in IMPORTANT_DIRS:
            if file.startswith(important_dir):
                return True
    return False

def update_session_log(commit_info):
    """SESSION_LOG.md 업데이트"""
    session_log_path = CLAUDE_DIR / 'SESSION_LOG.md'
    if not session_log_path.exists():
        print("SESSION_LOG.md 파일이 없습니다.")
        return False
    
    now_kst = datetime.now(KST)
    today = now_kst.strftime('%Y-%m-%d')
    current_time = now_kst.strftime('%Y-%m-%d %H:%M:%S KST')
    
    # 세션 로그 읽기
    with open(session_log_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 오늘 날짜의 세션 찾기
    session_marker = f"## 세션: {today}"
    
    # 새로운 작업 항목
    new_entry = f"\n- {current_time}: [{commit_info['hash']}] {commit_info['message']}"
    
    # 주요 파일 변경사항 추가
    if commit_info['files']:
        file_categories = {
            'src/': [],
            'scripts/': [],
            'config/': [],
            '.claude/': [],
            'docs/': []
        }
        
        for file in commit_info['files']:
            for prefix, file_list in file_categories.items():
                if file.startswith(prefix):
                    file_list.append(file)
                    break
        
        # 카테고리별로 정리
        details = []
        for category, files in file_categories.items():
            if files:
                details.append(f"  - {category}: {', '.join([f.split('/')[-1] for f in files[:3]])}")
        
        if details:
            new_entry += "\n" + "\n".join(details)
    
    # 세션이 있으면 업데이트, 없으면 새로 생성
    if session_marker in content:
        # 해당 세션의 작업 요약 섹션 찾기
        lines = content.split('\n')
        session_idx = None
        work_summary_idx = None
        next_section_idx = None
        
        for i, line in enumerate(lines):
            if line == session_marker:
                session_idx = i
            elif session_idx is not None and line == "### 작업 요약":
                work_summary_idx = i
            elif work_summary_idx is not None and line.startswith("###"):
                next_section_idx = i
                break
        
        if work_summary_idx is not None:
            # 작업 요약 섹션에 추가
            if next_section_idx is not None:
                # 다음 섹션 바로 전에 추가
                lines.insert(next_section_idx - 1, new_entry)
            else:
                # 작업 요약이 마지막 섹션인 경우
                insert_idx = work_summary_idx + 1
                while insert_idx < len(lines) and lines[insert_idx].strip() != '':
                    insert_idx += 1
                lines.insert(insert_idx, new_entry)
            
            content = '\n'.join(lines)
    else:
        # 새 세션 생성
        new_session = f"""
## 세션: {today}

### 작업 요약
{new_entry}

### 다음 작업
- [ ] 계속 진행

---
"""
        # 이전 세션 기록 앞에 삽입
        if "## 세션:" in content:
            # 첫 번째 세션 앞에 삽입
            first_session_idx = content.find("## 세션:")
            content = content[:first_session_idx] + new_session + "\n" + content[first_session_idx:]
        else:
            # 세션이 없으면 끝에 추가
            content += "\n" + new_session
    
    # 파일 쓰기
    with open(session_log_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ SESSION_LOG.md 업데이트 완료")
    return True

def update_claude_md():
    """CLAUDE.md 업데이트"""
    claude_md_path = PROJECT_ROOT / 'CLAUDE.md'
    if not claude_md_path.exists():
        print("CLAUDE.md 파일이 없습니다.")
        return False
    
    # Git 정보 수집
    git_branch = subprocess.run(
        ['git', 'branch', '--show-current'],
        capture_output=True, text=True, cwd=PROJECT_ROOT
    ).stdout.strip()
    
    git_status = subprocess.run(
        ['git', 'status', '--porcelain'],
        capture_output=True, text=True, cwd=PROJECT_ROOT
    )
    changed_files_count = len([line for line in git_status.stdout.strip().split('\n') if line])
    
    # 설정 파일에서 활성 전략 확인
    active_strategies = []
    config_path = PROJECT_ROOT / 'config' / 'config.yaml'
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            
        # 활성 전략 확인
        strategies_config = config.get('strategies', {})
        for strategy_name, strategy_config in strategies_config.items():
            if strategy_config.get('enabled', False):
                active_strategies.append(strategy_name.upper())
    
    # CLAUDE.md 읽기
    with open(claude_md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 최종 업데이트 날짜 변경
    update_marker = "*최종 업데이트:"
    if update_marker in content:
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if line.startswith(update_marker):
                lines[i] = f"*최종 업데이트: {datetime.now(KST).strftime('%Y년 %m월 %d일')}*"
                break
        content = '\n'.join(lines)
    
    # 운영 상태 섹션 업데이트
    if "### 현재 운영 상태" in content:
        # 현재 섹션 찾기
        import re
        pattern = r"(### 현재 운영 상태\n)(.*?)(?=\n##|\Z)"
        match = re.search(pattern, content, re.DOTALL)
        
        if match:
            # 기존 내용에서 필요한 정보 추출
            existing_content = match.group(2)
            
            # 활성 전략 라인 업데이트
            new_content = existing_content
            
            # 활성 전략 업데이트
            strategy_pattern = r"- \*\*활성 전략\*\*:.*"
            if active_strategies:
                strategy_line = f"- **활성 전략**: {', '.join(active_strategies)}"
            else:
                strategy_line = "- **활성 전략**: 없음"
            new_content = re.sub(strategy_pattern, strategy_line, new_content)
            
            # Git 브랜치 업데이트
            branch_pattern = r"- \*\*Git 브랜치\*\*:.*"
            branch_line = f"- **Git 브랜치**: {git_branch}"
            new_content = re.sub(branch_pattern, branch_line, new_content)
            
            # 변경된 파일 수 업데이트
            files_pattern = r"- \*\*변경된 파일\*\*:.*"
            files_line = f"- **변경된 파일**: {changed_files_count}개"
            new_content = re.sub(files_pattern, files_line, new_content)
            
            # 전체 섹션 교체
            content = content.replace(match.group(0), match.group(1) + new_content)
    
    # 파일 저장
    with open(claude_md_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ CLAUDE.md 업데이트 완료")
    return True

def update_project_status():
    """PROJECT_STATUS.md 간단한 업데이트"""
    status_file = CLAUDE_DIR / 'PROJECT_STATUS.md'
    
    # 기존 스크립트 실행 (전체 기능 활용)
    try:
        subprocess.run(
            [sys.executable, str(PROJECT_ROOT / 'scripts' / 'update_project_status.py')],
            cwd=PROJECT_ROOT,
            check=True
        )
        return True
    except subprocess.CalledProcessError:
        print("PROJECT_STATUS.md 업데이트 실패")
        return False

def main():
    """메인 함수"""
    # 커밋 정보 가져오기
    commit_info = get_last_commit_info()
    if not commit_info:
        print("커밋 정보를 가져올 수 없습니다.")
        return
    
    print(f"📝 문서 자동 업데이트 시작...")
    print(f"   커밋: [{commit_info['hash']}] {commit_info['message']}")
    
    # 변경된 파일 목록
    changed_files = commit_info['files']
    
    # 업데이트할 파일 목록
    files_to_add = []
    
    # 1. SESSION_LOG.md는 항상 업데이트
    if update_session_log(commit_info):
        files_to_add.append('.claude/SESSION_LOG.md')
    
    # 2. CLAUDE.md는 중요 디렉토리 변경 시에만 업데이트
    if should_update_claude_md(changed_files):
        print("📌 중요 파일 변경 감지 - CLAUDE.md 업데이트")
        if update_claude_md():
            files_to_add.append('CLAUDE.md')
    
    # 3. PROJECT_STATUS.md는 주요 변경사항이 있을 때만 업데이트
    if should_update_project_status(changed_files):
        print("📌 주요 변경사항 감지 - PROJECT_STATUS.md 업데이트")
        if update_project_status():
            files_to_add.append('.claude/PROJECT_STATUS.md')
    
    # 변경된 파일들을 스테이징
    if files_to_add:
        print(f"\n📝 업데이트된 문서 파일: {', '.join(files_to_add)}")
        
        # 파일들을 git에 추가
        for file in files_to_add:
            subprocess.run(['git', 'add', file], cwd=PROJECT_ROOT)
        
        print("✅ 모든 문서 업데이트 완료 - 다음 커밋에 포함됩니다")
    else:
        print("📝 업데이트할 문서가 없습니다")

if __name__ == "__main__":
    main()