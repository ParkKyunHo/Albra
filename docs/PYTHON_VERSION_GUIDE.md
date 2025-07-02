# Python 버전 관리 가이드

## 🐍 Python 버전 정책

AlbraTrading 시스템은 **Python 3.10**을 사용합니다.

### 버전 선택 이유
- **안정성**: Python 3.10은 LTS(Long Term Support) 버전
- **호환성**: 모든 의존성 패키지가 3.10에서 안정적으로 동작
- **성능**: asyncio 및 typing 개선사항 포함

## 📋 환경별 Python 설정

### 1. 로컬 개발 환경 (WSL)
```bash
# Python 3.10 설치 (pyenv 권장)
curl https://pyenv.run | bash

# bashrc에 추가
echo 'export PATH="$HOME/.pyenv/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc
source ~/.bashrc

# Python 3.10.12 설치
pyenv install 3.10.12
pyenv local 3.10.12

# 가상환경 생성
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. EC2 운영 환경
```bash
# Python 3.10이 없는 경우 설치
sudo apt update
sudo apt install -y python3.10 python3.10-venv python3.10-dev

# 가상환경 생성 (반드시 python3.10 명시)
cd /home/ubuntu/AlbraTrading
python3.10 -m venv venv
source venv/bin/activate
python --version  # Python 3.10.18 확인
```

## ⚠️ 시스템 Python과의 충돌 방지

### 문제점
Ubuntu 22.04 LTS는 기본적으로 Python 3.12를 사용하며, 이로 인해 다음 문제가 발생할 수 있습니다:
- 패키지 호환성 문제
- 가상환경 생성 시 잘못된 Python 버전 사용
- systemd 서비스가 시스템 Python 사용

### 해결 방법

#### 1. 명시적 Python 버전 사용
```bash
# ❌ 잘못된 방법
python -m venv venv
python3 -m venv venv

# ✅ 올바른 방법
python3.10 -m venv venv
```

#### 2. 가상환경 활성화 확인
```bash
# 가상환경 활성화
source venv/bin/activate

# Python 버전 확인 (반드시 3.10.x여야 함)
python --version
which python  # /home/ubuntu/AlbraTrading/venv/bin/python
```

#### 3. pip 사용 시 주의사항
```bash
# 가상환경 활성화 후
pip install -r requirements.txt

# 가상환경 비활성화 상태에서 설치 필요 시
/home/ubuntu/AlbraTrading/venv/bin/pip install -r requirements.txt
```

#### 4. systemd 서비스 설정
systemd 서비스는 항상 가상환경의 Python을 사용하도록 설정되어 있습니다:
```ini
ExecStart=/home/ubuntu/AlbraTrading/venv/bin/python /home/ubuntu/AlbraTrading/src/main_multi_account.py
```

## 🔧 문제 해결

### Python 버전 확인
```bash
# 시스템 Python
python3 --version      # Python 3.12.3
python3.10 --version   # Python 3.10.18

# 가상환경 Python
source venv/bin/activate
python --version       # Python 3.10.18 (올바름)
```

### 잘못된 버전으로 생성된 가상환경 재생성
```bash
cd /home/ubuntu/AlbraTrading
rm -rf venv
python3.10 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt --no-cache-dir --prefer-binary
```

### 패키지 설치 실패 시
t3.micro의 메모리 제한으로 인한 문제일 수 있습니다:
```bash
# 메모리 절약 옵션 사용
pip install -r requirements.txt --no-cache-dir --prefer-binary

# 개별 설치 (문제가 있는 패키지만)
pip install numpy==1.24.3 --only-binary :all:
pip install pandas==2.0.3 --only-binary :all:
```

## 📝 개발 팁

### 1. VS Code 설정
`.vscode/settings.json`:
```json
{
    "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python",
    "python.terminal.activateEnvironment": true
}
```

### 2. pre-commit 설정
`.pre-commit-config.yaml`에 Python 버전 체크 추가:
```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - id: check-python
        language_version: python3.10
```

### 3. GitHub Actions
`.github/workflows/test.yml`:
```yaml
- uses: actions/setup-python@v4
  with:
    python-version: '3.10'
```

## ✅ 체크리스트

배포 전 확인사항:
- [ ] 로컬에서 Python 3.10 사용 중
- [ ] `.python-version` 파일이 `3.10.12` 설정
- [ ] EC2에 Python 3.10 설치됨
- [ ] 가상환경이 Python 3.10으로 생성됨
- [ ] 모든 패키지가 정상 설치됨

## 🚨 주의사항

1. **절대 시스템 Python을 업그레이드하지 마세요**
   - Ubuntu 시스템 도구들이 의존하고 있습니다
   
2. **pyenv 사용 권장**
   - 여러 Python 버전을 안전하게 관리
   
3. **가상환경은 필수**
   - 시스템 패키지와 격리된 환경 보장

---

*최종 업데이트: 2025년 7월 3일*