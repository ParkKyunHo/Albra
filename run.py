#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlbraTrading System Launcher
시스템 시작을 위한 런처 스크립트
"""

import os
import sys
import subprocess
import asyncio
from datetime import datetime

# 프로젝트 루트 경로
current_file = os.path.abspath(__file__)
project_root = os.path.dirname(current_file)

# Python 경로에 추가
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def print_banner():
    """시작 배너 출력"""
    banner = """
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║         █████╗ ██╗     ██████╗ ██████╗  █████╗               ║
    ║        ██╔══██╗██║     ██╔══██╗██╔══██╗██╔══██╗              ║
    ║        ███████║██║     ██████╔╝██████╔╝███████║              ║
    ║        ██╔══██║██║     ██╔══██╗██╔══██╗██╔══██║              ║
    ║        ██║  ██║███████╗██████╔╝██║  ██║██║  ██║              ║
    ║        ╚═╝  ╚═╝╚══════╝╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝              ║
    ║                                                               ║
    ║               TRADING SYSTEM v2.0                             ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """
    print(banner)


def check_requirements():
    """필수 요구사항 체크"""
    print("🔍 시스템 요구사항 체크 중...")
    
    # Python 버전 체크
    if sys.version_info < (3, 7):
        print("❌ Python 3.7 이상이 필요합니다.")
        return False
    print(f"✅ Python {sys.version.split()[0]}")
    
    # 필수 파일 체크
    required_files = [
        os.path.join(project_root, '.env'),
        os.path.join(project_root, 'config', 'config.yaml'),
        os.path.join(project_root, 'src', 'main.py')
    ]
    
    for file_path in required_files:
        if not os.path.exists(file_path):
            print(f"❌ 필수 파일 없음: {file_path}")
            return False
    
    print("✅ 모든 필수 파일 확인 완료")
    return True


async def run_pre_flight_check():
    """Pre-flight 체크 실행"""
    print("\n🛫 Pre-flight 체크 실행 중...")
    
    pre_flight_script = os.path.join(project_root, 'tests', 'pre_flight_check.py')
    if os.path.exists(pre_flight_script):
        result = subprocess.run([sys.executable, pre_flight_script], capture_output=True, text=True)
        
        # 결과 확인
        if "시스템 시작 준비 완료!" in result.stdout:
            return True
        else:
            print("\n❌ Pre-flight 체크 실패")
            print("상세 내용을 보려면 다음 명령어를 실행하세요:")
            print(f"python {pre_flight_script}")
            return False
    else:
        print("⚠️ Pre-flight 체크 스크립트가 없습니다. 건너뜁니다.")
        return True


def select_mode():
    """실행 모드 선택"""
    print("\n📋 실행 모드를 선택하세요:")
    print("1. 기본 실행 (모든 활성 전략)")
    print("2. TFPE 전략만 실행")
    print("3. 전략 목록 보기")
    print("4. 테스트 모드 (거래 없음)")
    print("5. 종료")
    
    while True:
        try:
            choice = input("\n선택 (1-5): ").strip()
            if choice in ['1', '2', '3', '4', '5']:
                return choice
            else:
                print("잘못된 선택입니다. 1-5 중에서 선택하세요.")
        except KeyboardInterrupt:
            return '5'


def start_system(mode: str):
    """시스템 시작"""
    main_script = os.path.join(project_root, 'src', 'main.py')
    
    try:
        if mode == '1':
            print("\n🚀 시스템을 시작합니다...")
            subprocess.run([sys.executable, main_script])
        
        elif mode == '2':
            print("\n🚀 TFPE 전략으로 시스템을 시작합니다...")
            subprocess.run([sys.executable, main_script, '--strategies', 'TFPE'])
        
        elif mode == '3':
            print("\n📋 전략 목록을 확인합니다...")
            subprocess.run([sys.executable, main_script, '--list-strategies'])
        
        elif mode == '4':
            print("\n🧪 테스트 모드로 실행합니다...")
            subprocess.run([sys.executable, main_script, '--validate'])
        
    except KeyboardInterrupt:
        print("\n\n⛔ 사용자에 의해 중단되었습니다.")
    except Exception as e:
        print(f"\n❌ 시스템 실행 중 오류 발생: {e}")


async def main():
    """메인 함수"""
    print_banner()
    print(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*65)
    
    # 1. 요구사항 체크
    if not check_requirements():
        print("\n필수 요구사항을 먼저 해결해주세요.")
        return
    
    # 2. Pre-flight 체크 (선택사항)
    print("\nPre-flight 체크를 실행하시겠습니까? (권장) (y/n): ", end='')
    response = input().strip().lower()
    
    if response == 'y':
        if not await run_pre_flight_check():
            print("\nPre-flight 체크를 통과하지 못했습니다.")
            print("문제를 해결한 후 다시 시도해주세요.")
            return
    
    # 3. 실행 모드 선택
    mode = select_mode()
    
    if mode == '5':
        print("\n종료합니다.")
        return
    
    # 4. 시스템 시작
    start_system(mode)
    
    print("\n시스템이 종료되었습니다.")
    print(f"종료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n종료합니다.")
