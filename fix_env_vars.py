#!/usr/bin/env python3
"""
.env 파일 환경 변수 이름 자동 수정 스크립트
BINANCE_SECRET_KEY를 BINANCE_API_SECRET으로 변경
"""

import os
import shutil
from datetime import datetime

def fix_env_file():
    env_path = ".env"
    
    if not os.path.exists(env_path):
        print(f"❌ .env 파일을 찾을 수 없습니다: {env_path}")
        return
    
    # 백업 생성
    backup_path = f".env.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(env_path, backup_path)
    print(f"✓ 백업 생성: {backup_path}")
    
    # 파일 읽기
    with open(env_path, 'r') as f:
        lines = f.readlines()
    
    # 수정된 내용
    modified = False
    new_lines = []
    
    for line in lines:
        # BINANCE_SECRET_KEY를 BINANCE_API_SECRET으로 변경
        if line.strip().startswith('BINANCE_SECRET_KEY='):
            # 기존 값 추출
            value = line.strip().split('=', 1)[1]
            new_line = f'BINANCE_API_SECRET={value}\n'
            new_lines.append(new_line)
            print(f"✓ 변경: BINANCE_SECRET_KEY → BINANCE_API_SECRET")
            modified = True
        else:
            new_lines.append(line)
    
    if modified:
        # 파일 저장
        with open(env_path, 'w') as f:
            f.writelines(new_lines)
        print(f"✓ .env 파일이 수정되었습니다.")
    else:
        print("ℹ️ 수정할 내용이 없습니다.")
    
    # 현재 환경 변수 확인
    print("\n현재 환경 변수:")
    for line in new_lines:
        if 'BINANCE' in line and '=' in line and not line.strip().startswith('#'):
            key = line.split('=')[0].strip()
            print(f"  - {key}")

if __name__ == "__main__":
    fix_env_file()
