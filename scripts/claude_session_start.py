#!/usr/bin/env python3
"""
Claude 세션 시작 스크립트
이전 작업 내용과 현재 프로젝트 상태를 요약해서 보여줍니다.
"""

import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent.parent
CLAUDE_DIR = PROJECT_ROOT / '.claude'

def print_header(title: str):
    """헤더 출력"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def get_recent_commits(days: int = 7) -> List[str]:
    """최근 커밋 가져오기"""
    try:
        since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        result = subprocess.run(
            ['git', 'log', f'--since={since_date}', '--oneline', '--no-merges'],
            capture_output=True, text=True, cwd=PROJECT_ROOT
        )
        if result.stdout:
            return result.stdout.strip().split('\n')[:10]
    except:
        pass
    return []

def get_changed_files() -> List[str]:
    """변경된 파일 목록"""
    try:
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            capture_output=True, text=True, cwd=PROJECT_ROOT
        )
        if result.stdout:
            return result.stdout.strip().split('\n')[:10]
    except:
        pass
    return []

def read_todo_summary() -> Dict[str, int]:
    """TODO 요약 정보"""
    todo_file = CLAUDE_DIR / 'TODO.md'
    summary = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0, 'total': 0}
    
    if todo_file.exists():
        try:
            with open(todo_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 간단한 카운팅
            summary['critical'] = content.count('🚨')
            summary['high'] = content.count('- [ ]', content.find('높음'))
            summary['medium'] = content.count('- [ ]', content.find('중간'))
            summary['low'] = content.count('- [ ]', content.find('낮음'))
            summary['total'] = sum([summary['critical'], summary['high'], 
                                   summary['medium'], summary['low']])
        except:
            pass
    
    return summary

def read_last_session() -> str:
    """마지막 세션 정보 읽기"""
    session_log = CLAUDE_DIR / 'SESSION_LOG.md'
    
    if session_log.exists():
        try:
            with open(session_log, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 가장 최근 세션 찾기
            sessions = content.split('## 세션:')
            if len(sessions) > 1:
                last_session = sessions[1].split('## ')[0].strip()
                # 첫 100자만 반환
                lines = last_session.split('\n')[:10]
                return '\n'.join(lines)
        except:
            pass
    
    return "이전 세션 기록 없음"

def show_project_summary():
    """프로젝트 요약 정보 표시"""
    print_header("🚀 AlbraTrading 프로젝트 상태")
    
    # Git 정보
    try:
        branch = subprocess.run(['git', 'branch', '--show-current'], 
                               capture_output=True, text=True, cwd=PROJECT_ROOT)
        print(f"📍 현재 브랜치: {branch.stdout.strip()}")
    except:
        print("📍 Git 정보를 가져올 수 없습니다.")
    
    # 프로젝트 정보
    print(f"📁 프로젝트 경로: {PROJECT_ROOT}")
    print(f"🐍 Python 버전: Python 3.12")
    print(f"🌐 GitHub: https://github.com/ParkKyunHo/Albra.git")
    
    # TODO 요약
    todo_summary = read_todo_summary()
    print(f"\n📋 TODO 현황:")
    print(f"   - 전체: {todo_summary['total']}개")
    if todo_summary['critical'] > 0:
        print(f"   - 🚨 긴급: {todo_summary['critical']}개")
    if todo_summary['high'] > 0:
        print(f"   - 🔴 높음: {todo_summary['high']}개")
    
    # 변경된 파일
    changed_files = get_changed_files()
    if changed_files:
        print(f"\n📝 변경된 파일: {len(changed_files)}개")
        for file in changed_files[:5]:
            print(f"   {file}")
        if len(changed_files) > 5:
            print(f"   ... 외 {len(changed_files) - 5}개")

def show_recent_activity():
    """최근 활동 표시"""
    print_header("📊 최근 활동")
    
    # 최근 커밋
    recent_commits = get_recent_commits(7)
    if recent_commits:
        print("최근 커밋 (7일):")
        for commit in recent_commits[:5]:
            print(f"  {commit}")
        if len(recent_commits) > 5:
            print(f"  ... 외 {len(recent_commits) - 5}개")
    else:
        print("최근 7일간 커밋 없음")

def show_last_session():
    """마지막 세션 정보 표시"""
    print_header("📝 이전 세션 요약")
    
    last_session = read_last_session()
    print(last_session)

def show_quick_commands():
    """자주 사용하는 명령어 표시"""
    print_header("⚡ 빠른 명령어")
    
    print("Git 명령어:")
    print("  git cap \"메시지\"        # 커밋 + 푸시")
    print("  git status              # 상태 확인")
    print("  git log --oneline -10   # 최근 커밋")
    
    print("\n프로젝트 명령어:")
    print("  python scripts/update_claude_docs.py --commit     # CLAUDE.md 업데이트")
    print("  python scripts/update_project_status.py           # 프로젝트 상태 업데이트")
    print("  python scripts/update_project_status.py --log \"작업내용\"  # 세션 로그 추가")
    
    print("\n주요 파일:")
    print("  .claude/PROJECT_STATUS.md  # 프로젝트 상태")
    print("  .claude/SESSION_LOG.md     # 세션 기록")
    print("  .claude/TODO.md           # 할 일 목록")
    print("  CLAUDE.md                 # 프로젝트 컨텍스트")

def show_project_overview():
    """프로젝트 전체 개요 표시"""
    print_header("📊 프로젝트 개요")
    
    # 시스템 개요 파일 읽기
    overview_file = CLAUDE_DIR / 'SYSTEM_OVERVIEW.md'
    if overview_file.exists():
        try:
            with open(overview_file, 'r', encoding='utf-8') as f:
                content = f.read()
            # 주요 섹션만 추출
            lines = content.split('\n')
            in_section = False
            for line in lines:
                if '## 📁 핵심 모듈 구조' in line:
                    in_section = True
                elif '## 🔄 데이터 흐름' in line:
                    break
                elif in_section and line.strip():
                    print(line[:80] + '...' if len(line) > 80 else line)
        except:
            pass
    
    print("\n🎯 시스템 목적: AWS EC2에서 24/7 운영되는 바이낸스 자동 트레이딩")
    print("📈 현재 전략: TFPE (Trend Following with Price Extremes)")
    print("💰 포지션 관리: 멀티 전략 지원, 자동/수동 통합")

def show_recent_errors():
    """최근 오류 및 해결 표시"""
    print_header("📛 최근 오류 및 해결")
    
    error_file = CLAUDE_DIR / 'ERROR_HISTORY.md'
    if error_file.exists():
        try:
            with open(error_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 최근 오류 섹션 추출
            if '## 2025년' in content:
                recent_section = content.split('## 2025년')[1].split('## ')[0]
                lines = recent_section.strip().split('\n')[:10]
                for line in lines:
                    if line.strip():
                        print(line)
            
            # 미해결 이슈 확인
            if '### 알려진 이슈' in content:
                print("\n⚠️  알려진 이슈:")
                issues_section = content.split('### 알려진 이슈')[1].split('##')[0]
                lines = issues_section.strip().split('\n')[:5]
                for line in lines:
                    if line.startswith('###'):
                        print(f"  - {line.replace('###', '').strip()}")
        except:
            pass
    else:
        print("오류 히스토리 없음 (새 프로젝트)")

def main():
    """메인 실행 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Claude 세션 시작')
    parser.add_argument('--full', action='store_true', help='전체 프로젝트 분석')
    args = parser.parse_args()
    
    print("\n" + "🤖 " * 20)
    print("         Claude Code Session 시작")
    print("🤖 " * 20)
    
    # 기본 정보
    show_project_summary()
    
    # --full 옵션 사용 시 추가 정보
    if args.full:
        show_project_overview()
        show_recent_errors()
    
    # 최근 활동
    show_recent_activity()
    
    # 이전 세션
    show_last_session()
    
    # 빠른 명령어
    show_quick_commands()
    
    print(f"\n{'='*60}")
    print("  준비 완료! 작업을 시작하세요.")
    print(f"{'='*60}\n")
    
    # 프로젝트 상태 자동 업데이트
    print("💡 팁:")
    print("   - 전체 분석: python scripts/claude_session_start.py --full")
    print("   - 상태 업데이트: python scripts/update_project_status.py")

if __name__ == "__main__":
    main()