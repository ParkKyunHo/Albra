#!/usr/bin/env python3
"""
세션 로그 자동 업데이트 스크립트
커밋 시 자동으로 SESSION_LOG.md를 업데이트합니다.
"""

import os
import sys
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent.parent
SESSION_LOG_PATH = PROJECT_ROOT / '.claude' / 'SESSION_LOG.md'

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

def update_session_log(commit_info):
    """세션 로그 업데이트"""
    if not SESSION_LOG_PATH.exists():
        print("SESSION_LOG.md 파일이 없습니다.")
        return False
    
    # 한국 표준시(KST) 설정
    KST = timezone(timedelta(hours=9))
    now_kst = datetime.now(KST)
    
    # 현재 날짜와 시간 (KST)
    today = now_kst.strftime('%Y-%m-%d')
    current_time = now_kst.strftime('%Y-%m-%d %H:%M:%S KST')
    
    # 세션 로그 읽기
    with open(SESSION_LOG_PATH, 'r', encoding='utf-8') as f:
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
    with open(SESSION_LOG_PATH, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ 세션 로그 업데이트 완료: {new_entry.strip()}")
    return True

def main():
    """메인 함수"""
    # 커밋 정보 가져오기
    commit_info = get_last_commit_info()
    if not commit_info:
        print("커밋 정보를 가져올 수 없습니다.")
        return
    
    # 세션 로그 업데이트
    update_session_log(commit_info)

if __name__ == "__main__":
    main()