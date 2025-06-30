#!/usr/bin/env python3
"""
환경 변수 디버깅 스크립트
.env 파일과 API 키 설정을 확인합니다.
"""

import os
from dotenv import load_dotenv

print("=== Environment Debug ===\n")

# 1. 현재 작업 디렉토리 확인
print(f"Current working directory: {os.getcwd()}")

# 2. .env 파일 위치 확인
possible_paths = [
    ".env",
    "../.env",
    "C:\\AlbraTrading\\.env"
]

env_found = False
for path in possible_paths:
    if os.path.exists(path):
        print(f"✓ Found .env at: {os.path.abspath(path)}")
        env_found = True
        # 파일 크기 확인
        size = os.path.getsize(path)
        print(f"  File size: {size} bytes")
        
        # .env 파일 로드
        load_dotenv(path)
        break
    else:
        print(f"✗ Not found: {path}")

if not env_found:
    print("\n❌ No .env file found!")

print("\n3. API Key Check:")

# 3. 환경 변수 확인
api_keys = [
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
    "API_KEY",
    "API_SECRET"
]

for key in api_keys:
    value = os.getenv(key)
    if value:
        # 보안을 위해 일부만 표시
        masked = value[:4] + "..." + value[-4:] if len(value) > 8 else "***"
        print(f"✓ {key}: {masked}")
    else:
        print(f"✗ {key}: Not found")

# 4. 모든 환경 변수 중 BINANCE 관련 찾기
print("\n4. All BINANCE related variables:")
binance_vars = {k: v for k, v in os.environ.items() if 'BINANCE' in k.upper()}
if binance_vars:
    for k, v in binance_vars.items():
        masked = v[:4] + "..." + v[-4:] if len(v) > 8 else "***"
        print(f"  {k}: {masked}")
else:
    print("  No BINANCE variables found in environment")

# 5. Python 패키지 확인
print("\n5. Package Check:")
try:
    import dotenv
    print(f"✓ python-dotenv version: {dotenv.__version__}")
except ImportError:
    print("✗ python-dotenv is not installed!")

# 6. .env 파일 내용 미리보기 (첫 몇 줄만, API 키는 마스킹)
print("\n6. .env file preview (if found):")
if env_found:
    try:
        with open(path, 'r') as f:
            lines = f.readlines()[:10]  # 처음 10줄만
            for line in lines:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    if 'KEY' in key.upper() or 'SECRET' in key.upper():
                        masked = value[:4] + "..." if len(value) > 4 else "***"
                        print(f"  {key}={masked}")
                    else:
                        print(f"  {line}")
                elif line:
                    print(f"  {line}")
    except Exception as e:
        print(f"  Error reading file: {e}")

print("\n=== End Debug ===")
