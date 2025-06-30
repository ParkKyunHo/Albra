#!/usr/bin/env python3
"""main.py 구문 검증 스크립트"""
import ast
import sys

def verify_main_py():
    try:
        with open('src/main.py', 'r', encoding='utf-8') as f:
            code = f.read()
        
        # AST 파싱 시도
        ast.parse(code)
        
        print("✅ main.py 구문 검증 성공!")
        return True
        
    except SyntaxError as e:
        print(f"❌ 구문 오류 발견!")
        print(f"  파일: {e.filename}")
        print(f"  줄 번호: {e.lineno}")
        print(f"  컬럼: {e.offset}")
        print(f"  오류: {e.msg}")
        if e.text:
            print(f"  문제 라인: {e.text.strip()}")
        return False
        
    except Exception as e:
        print(f"❌ 기타 오류: {e}")
        return False

if __name__ == "__main__":
    if verify_main_py():
        sys.exit(0)
    else:
        sys.exit(1)
