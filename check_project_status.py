"""
Claude Code 환경 체크 및 프로젝트 정보 표시
"""
import os
import sys
import json
from datetime import datetime
import importlib.util

def check_environment():
    """Python 환경 및 의존성 체크"""
    print("="*60)
    print("AlbraTrading 프로젝트 환경 체크")
    print("="*60)
    
    # Python 버전
    print(f"\n1. Python 버전: {sys.version}")
    
    # 현재 디렉토리
    print(f"\n2. 현재 디렉토리: {os.getcwd()}")
    
    # 필수 패키지 체크
    print("\n3. 필수 패키지 상태:")
    required_packages = [
        'pandas', 'numpy', 'matplotlib', 'ccxt', 
        'flask', 'pydantic', 'pytest'
    ]
    
    for package in required_packages:
        spec = importlib.util.find_spec(package)
        if spec is not None:
            print(f"  ✓ {package} - 설치됨")
        else:
            print(f"  ✗ {package} - 미설치")
    
    # 프로젝트 파일 체크
    print("\n4. 프로젝트 핵심 파일:")
    core_files = [
        'turtle_trading_strategy.py',
        'portfolio_comparison_analysis.py',
        'PROJECT_CONTEXT.md',
        'CODE_STYLE_GUIDE.md'
    ]
    
    for file in core_files:
        if os.path.exists(file):
            size = os.path.getsize(file)
            print(f"  ✓ {file} ({size:,} bytes)")
        else:
            print(f"  ✗ {file} - 없음")
    
    # 최근 결과 파일
    print("\n5. 최근 백테스트 결과:")
    result_files = [f for f in os.listdir('.') if f.endswith('.json') and 'zlmacd' in f]
    result_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    
    for file in result_files[:5]:
        mtime = datetime.fromtimestamp(os.path.getmtime(file))
        print(f"  • {file} - {mtime.strftime('%Y-%m-%d %H:%M')}")
    
    # 프로젝트 컨텍스트 요약
    if os.path.exists('PROJECT_CONTEXT.md'):
        print("\n6. 프로젝트 현재 상태:")
        with open('PROJECT_CONTEXT.md', 'r', encoding='utf-8') as f:
            lines = f.readlines()
            in_progress = False
            for line in lines:
                if '현재 진행 상황' in line:
                    in_progress = True
                elif '다음 작업 예정' in line:
                    break
                elif in_progress and line.strip():
                    print(f"  {line.strip()}")

def load_recent_results():
    """최근 백테스트 결과 로드 및 요약"""
    print("\n" + "="*60)
    print("최근 백테스트 결과 요약")
    print("="*60)
    
    # 가장 최근 결과 파일 찾기
    result_files = [f for f in os.listdir('.') if f.endswith('.json') and 'portfolio_comparison' in f]
    
    if result_files:
        latest_file = max(result_files, key=os.path.getmtime)
        print(f"\n최근 결과 파일: {latest_file}")
        
        try:
            with open(latest_file, 'r') as f:
                data = json.load(f)
            
            # 개별 심볼 성과
            if 'individual_results' in data:
                print("\n개별 심볼 성과:")
                for symbol, results in data['individual_results'].items():
                    summary = results.get('summary', {})
                    print(f"  {symbol}:")
                    print(f"    - Total Return: {summary.get('total_return', 0):.1f}%")
                    print(f"    - Win Rate: {summary.get('avg_win_rate', 0):.1f}%")
                    print(f"    - Total Trades: {summary.get('total_trades', 0)}")
            
            # 포트폴리오 성과
            if 'portfolio_performance' in data:
                portfolio = data['portfolio_performance']
                print(f"\n포트폴리오 성과:")
                print(f"  - Total Return: {portfolio.get('total_return', 0):.1f}%")
                print(f"  - Final Value: ${portfolio.get('final_value', 0):,.0f}")
            
            # BTC 단독 성과
            if 'btc_only_performance' in data:
                btc = data['btc_only_performance']
                print(f"\nBTC 단독 성과:")
                print(f"  - Total Return: {btc.get('total_return', 0):.1f}%")
                print(f"  - Win Rate: {btc.get('avg_win_rate', 0):.1f}%")
                
        except Exception as e:
            print(f"결과 파일 읽기 오류: {e}")
    else:
        print("\n결과 파일이 없습니다.")

def show_next_steps():
    """다음 작업 안내"""
    print("\n" + "="*60)
    print("다음 단계 안내")
    print("="*60)
    
    print("\n1. 작업 이어가기:")
    print("   cat WORK_HISTORY.md  # 최근 작업 확인")
    print("   cat PROJECT_CONTEXT.md  # 프로젝트 상태 확인")
    
    print("\n2. 코드 수정 시:")
    print("   # 백업 먼저!")
    print("   cp file.py file.py.backup")
    print("   # 코드 스타일 가이드 확인")
    print("   cat CODE_STYLE_GUIDE.md")
    
    print("\n3. 테스트 실행:")
    print("   # 멀티 심볼 백테스트")
    print("   python turtle_trading_strategy.py")
    print("   # 포트폴리오 비교")
    print("   python portfolio_comparison_analysis.py")
    
    print("\n4. 새 기능 추가:")
    print("   # 실시간 거래 연동")
    print("   # src/live_trading/ 디렉토리 생성 예정")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    check_environment()
    load_recent_results()
    show_next_steps()
