# Python 버전 충돌 해결 가이드

## 🔍 문제 진단

### 증상
1. **배포 시 패키지 설치 실패**
   - `ERROR: Package requires Python >= 3.11`
   - 빌드 중 메모리 부족으로 프로세스 종료

2. **서비스 시작 실패**
   - `ModuleNotFoundError` 에러
   - Python 버전 불일치로 인한 import 오류

3. **가상환경 활성화 후에도 잘못된 Python 사용**
   - `python --version`이 3.12를 표시
   - pip가 시스템 패키지를 설치

## 🛠️ 즉시 해결 방법

### 1. Python 버전 확인 스크립트 실행
```bash
cd /home/ubuntu/AlbraTrading
./scripts/check_python_version.sh
```

### 2. 수동으로 Python 3.10 환경 설정
```bash
# Python 3.10 설치 확인
which python3.10

# 기존 가상환경 삭제
rm -rf venv

# Python 3.10으로 새 가상환경 생성
python3.10 -m venv venv

# 가상환경 활성화
source venv/bin/activate

# Python 버전 확인 (3.10.x여야 함)
python --version

# pip 업그레이드
python -m pip install --upgrade pip

# 의존성 설치 (메모리 절약 옵션)
pip install -r requirements.txt --no-cache-dir --prefer-binary
```

## 🚫 시스템 Python 충돌 방지

### 1. 절대 하지 말아야 할 것들
- ❌ `sudo apt upgrade python3` - 시스템 Python 업그레이드
- ❌ `sudo pip install` - 시스템 전역 패키지 설치
- ❌ `/usr/bin/python3` 심볼릭 링크 변경
- ❌ `update-alternatives`로 기본 Python 변경

### 2. 항상 해야 할 것들
- ✅ 가상환경 사용 (`venv` 또는 `virtualenv`)
- ✅ 명시적 Python 버전 지정 (`python3.10`)
- ✅ 프로젝트 루트의 `.python-version` 파일 확인
- ✅ systemd 서비스에 전체 경로 사용

## 🔧 고급 해결 방법

### 1. pyenv를 사용한 Python 버전 관리
```bash
# pyenv 설치
curl https://pyenv.run | bash

# bashrc 설정 추가
echo 'export PATH="$HOME/.pyenv/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init --path)"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc
source ~/.bashrc

# Python 3.10.12 설치
pyenv install 3.10.12
pyenv local 3.10.12

# 확인
python --version  # Python 3.10.12
```

### 2. Docker를 사용한 격리된 환경
```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["python", "src/main_multi_account.py"]
```

### 3. 환경변수로 Python 경로 고정
```bash
# .bashrc 또는 .profile에 추가
export ALBRATRADING_PYTHON="/home/ubuntu/AlbraTrading/venv/bin/python"
alias atpython="$ALBRATRADING_PYTHON"

# 사용
atpython src/main_multi_account.py
```

## 📝 배포 체크리스트

배포 전 반드시 확인:

1. **로컬 환경 (WSL)**
   ```bash
   cd /home/albra/AlbraTrading
   ./scripts/check_python_version.sh
   ```

2. **EC2 환경**
   ```bash
   ssh -i ~/.ssh/trading-bot4 ubuntu@13.209.157.171
   cd /home/ubuntu/AlbraTrading
   ./scripts/check_python_version.sh
   ```

3. **systemd 서비스 파일 확인**
   ```bash
   grep ExecStart /etc/systemd/system/albratrading-multi.service
   # /home/ubuntu/AlbraTrading/venv/bin/python 경로 확인
   ```

## 🚨 문제 발생 시

### 1. 서비스가 시작되지 않을 때
```bash
# 상세 로그 확인
sudo journalctl -u albratrading-multi -n 100

# Python 경로 확인
sudo systemctl cat albratrading-multi | grep ExecStart

# 직접 실행 테스트
/home/ubuntu/AlbraTrading/venv/bin/python /home/ubuntu/AlbraTrading/src/main_multi_account.py
```

### 2. 패키지 import 오류
```bash
# 가상환경 재생성
cd /home/ubuntu/AlbraTrading
rm -rf venv
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt --no-cache-dir
```

### 3. 메모리 부족 오류
```bash
# 스왑 파일 생성 (임시)
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 패키지 설치
pip install -r requirements.txt --no-cache-dir --prefer-binary

# 설치 후 스왑 제거
sudo swapoff /swapfile
sudo rm /swapfile
```

## 📚 참고 자료

- [Python Virtual Environments](https://docs.python.org/3.10/tutorial/venv.html)
- [pyenv Documentation](https://github.com/pyenv/pyenv)
- [Ubuntu Python Management](https://wiki.ubuntu.com/Python)

---

*최종 업데이트: 2025년 7월 3일*
*작성: Claude Code Assistant*