#!/usr/bin/env python3
"""
로컬 Python 코드 검증 스크립트
배포 전 문법 오류와 기본적인 문제를 체크합니다.
"""
import ast
import os
import sys
import json
from pathlib import Path
from typing import List, Tuple

class CodeVerifier:
    def __init__(self, project_root: str = None):
        # 프로젝트 루트 자동 감지
        if project_root:
            self.project_root = Path(project_root)
        else:
            # 스크립트 위치에서 프로젝트 루트 찾기
            script_path = Path(__file__).absolute()
            # scripts 폴더에 있다고 가정
            if script_path.parent.name == 'scripts':
                self.project_root = script_path.parent.parent
            else:
                self.project_root = Path.cwd()
        
        print(f"Project root: {self.project_root}")
        
        self.errors: List[Tuple[str, str]] = []
        self.warnings: List[Tuple[str, str]] = []
        
    def verify_python_syntax(self, directory: str) -> bool:
        """Python 파일 문법 검증"""
        dir_path = self.project_root / directory
        
        if not dir_path.exists():
            print(f"\n⚠️  Directory not found: {directory}/")
            return True  # 디렉토리가 없는 것은 에러가 아님
            
        print(f"\n🔍 Checking Python syntax in {directory}/...")
        
        py_files = list(dir_path.rglob("*.py"))
        
        if not py_files:
            print(f"  No Python files found in {directory}/")
            return True
        
        for filepath in py_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    ast.parse(content)
                print(f"  ✓ {filepath.relative_to(self.project_root)}")
            except SyntaxError as e:
                self.errors.append((str(filepath), f"Syntax error: {e}"))
                print(f"  ✗ {filepath.relative_to(self.project_root)}: {e}")
            except Exception as e:
                self.warnings.append((str(filepath), f"Parse error: {e}"))
                print(f"  ⚠ {filepath.relative_to(self.project_root)}: {e}")
        
        return len(self.errors) == 0
    
    def verify_required_files(self) -> bool:
        """필수 파일 존재 확인"""
        print("\n📋 Checking required files...")
        
        # supervisor.py는 선택사항으로 변경
        required_files = [
            "src/main.py",
            "src/web/templates/dashboard.html",
            "src/utils/telegram_commands.py",
            "requirements.txt",
            "config/config.yaml"
        ]
        
        optional_files = [
            "supervisor.py",
            ".env"
        ]
        
        all_exist = True
        
        # 필수 파일 체크
        for file_path in required_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                print(f"  ✓ {file_path}")
            else:
                print(f"  ✗ {file_path} - NOT FOUND!")
                self.errors.append((file_path, "Required file not found"))
                all_exist = False
        
        # 선택 파일 체크
        print("\n📋 Checking optional files...")
        for file_path in optional_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                print(f"  ✓ {file_path}")
            else:
                print(f"  ⚠ {file_path} - Not found (optional)")
                self.warnings.append((file_path, "Optional file not found"))
        
        return all_exist
    
    def verify_config_files(self) -> bool:
        """설정 파일 유효성 검증"""
        print("\n⚙️ Checking configuration files...")
        
        # config.yaml 검증
        config_path = self.project_root / "config/config.yaml"
        if config_path.exists():
            try:
                import yaml
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                print(f"  ✓ config.yaml is valid")
                
                # 필수 설정 키 확인
                required_keys = ['system', 'strategies']
                for key in required_keys:
                    if key not in config:
                        self.warnings.append(("config.yaml", f"Missing key: {key}"))
                        print(f"  ⚠ config.yaml missing key: {key}")
                        
            except Exception as e:
                self.errors.append(("config.yaml", f"Invalid YAML: {e}"))
                print(f"  ✗ config.yaml: {e}")
                return False
        else:
            print(f"  ⚠ config.yaml not found")
        
        return True
    
    def verify_imports(self) -> bool:
        """import 문 검증"""
        print("\n📦 Checking imports...")
        
        # requirements.txt 읽기
        req_path = self.project_root / "requirements.txt"
        required_packages = set()
        
        if req_path.exists():
            with open(req_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        pkg = line.split('==')[0].split('>=')[0].split('<=')[0]
                        # python-binance -> binance 변환
                        if pkg == 'python-binance':
                            pkg = 'binance'
                        required_packages.add(pkg.lower())
        
        # 기본 import 체크
        import_errors = []
        check_packages = ['pandas', 'numpy', 'flask', 'binance', 'asyncio', 'websockets']
        
        for package in check_packages:
            try:
                if package == 'binance':
                    # binance 패키지 특별 처리
                    try:
                        import binance
                    except ImportError:
                        __import__('python-binance')
                else:
                    __import__(package)
                print(f"  ✓ {package} is installed")
            except ImportError:
                if package in required_packages or package in ['pandas', 'numpy', 'binance']:
                    self.warnings.append((package, "Package not installed locally"))
                    print(f"  ⚠ {package} not installed (will be installed on server)")
        
        return True
    
    def verify_project_structure(self) -> bool:
        """프로젝트 구조 확인"""
        print("\n📁 Checking project structure...")
        
        required_dirs = [
            "src",
            "src/core",
            "src/strategies",
            "src/utils",
            "src/web",
            "config",
            "scripts"
        ]
        
        all_exist = True
        for dir_path in required_dirs:
            full_path = self.project_root / dir_path
            if full_path.exists() and full_path.is_dir():
                print(f"  ✓ {dir_path}/")
            else:
                print(f"  ✗ {dir_path}/ - NOT FOUND!")
                self.errors.append((dir_path, "Directory not found"))
                all_exist = False
        
        return all_exist
    
    def run_all_checks(self) -> bool:
        """모든 검증 실행"""
        print("="*50)
        print("🚀 AlbraTrading Code Verification")
        print("="*50)
        
        # 프로젝트 루트 확인
        if not self.project_root.exists():
            print(f"❌ Project root not found: {self.project_root}")
            return False
        
        checks = [
            self.verify_project_structure(),
            self.verify_required_files(),
            self.verify_python_syntax("src"),
            self.verify_python_syntax("scripts"),
            self.verify_config_files(),
            self.verify_imports()
        ]
        
        print("\n" + "="*50)
        print("📊 Verification Summary")
        print("="*50)
        
        if self.errors:
            print(f"\n❌ Found {len(self.errors)} errors:")
            for file, error in self.errors:
                print(f"  - {file}: {error}")
        
        if self.warnings:
            print(f"\n⚠️ Found {len(self.warnings)} warnings:")
            for file, warning in self.warnings:
                print(f"  - {file}: {warning}")
        
        if not self.errors:
            print("\n✅ All checks passed! Ready for deployment.")
            return True
        else:
            print("\n❌ Fix errors before deployment!")
            return False

def main():
    # 커맨드라인 인자로 프로젝트 루트 전달 가능
    project_root = sys.argv[1] if len(sys.argv) > 1 else None
    
    verifier = CodeVerifier(project_root)
    if not verifier.run_all_checks():
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()