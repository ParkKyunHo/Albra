#!/usr/bin/env python3
"""
API 키 자동 수정 스크립트 - UTF-8 인코딩 지원
"""

import os
import shutil
from datetime import datetime

def fix_api_keys():
    print("=== API Key Auto-Fix Tool ===\n")
    
    env_path = ".env"
    if not os.path.exists(env_path):
        print(f"❌ .env file not found!")
        return
    
    # 백업 생성
    backup_path = f".env.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(env_path, backup_path)
    print(f"✓ Backup created: {backup_path}")
    
    # 파일 읽기 (UTF-8 인코딩 명시)
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        # UTF-8 실패시 cp949로 시도
        with open(env_path, 'r', encoding='cp949') as f:
            lines = f.readlines()
    
    # 수정된 라인들
    new_lines = []
    changes_made = False
    
    for line in lines:
        original_line = line
        
        # 주석이나 빈 줄은 그대로 유지
        if line.strip().startswith('#') or not line.strip():
            new_lines.append(line)
            continue
        
        # KEY=VALUE 형식 파싱
        if '=' in line and not line.strip().startswith('#'):
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()  # 줄바꿈 포함해서 strip
            
            # 환경 변수 이름은 그대로 유지 (시스템이 BINANCE_SECRET_KEY 사용)
            
            # 값에서 따옴표 제거 (있는 경우)
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
                changes_made = True
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
                changes_made = True
            
            # 재조합
            new_line = f"{key}={value}\n"
            
            # 변경사항 표시
            if new_line != original_line:
                if 'SECRET' in key or 'KEY' in key:
                    print(f"✓ Fixed: {key} (removed extra spaces/quotes)")
                else:
                    print(f"✓ Fixed: {key}")
            
            new_lines.append(new_line)
        else:
            new_lines.append(line)
    
    # 파일 저장 (UTF-8로 저장)
    if changes_made:
        with open(env_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print(f"\n✓ .env file has been fixed!")
        print("  Please restart your trading system.")
    else:
        print("\n✓ No changes needed - .env file looks good!")
    
    # 현재 설정 확인
    print("\n=== Current Configuration ===")
    from dotenv import load_dotenv
    load_dotenv(env_path, override=True)
    
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_SECRET_KEY')
    
    if api_key:
        print(f"BINANCE_API_KEY: {api_key[:8]}...{api_key[-4:]}")
    else:
        print("BINANCE_API_KEY: Not found!")
    
    if api_secret:
        print(f"BINANCE_SECRET_KEY: Found (length: {len(api_secret)})")
    else:
        print("BINANCE_SECRET_KEY: Not found!")

if __name__ == "__main__":
    fix_api_keys()
