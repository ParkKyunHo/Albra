# AlbraTrading 배포 시스템 상세 노트

## 배포 시스템 재설계 (2025-01-30)

### 문제 상황
프로젝트가 WSL 환경에 있을 때 Windows 배치 파일에서 직접 접근하려고 하면 다음과 같은 문제 발생:

1. **UNC 경로 문제**
   - Windows에서 WSL 파일 접근: `\\wsl.localhost\Ubuntu\home\albra\AlbraTrading`
   - CMD.exe는 UNC 경로를 현재 디렉토리로 설정 불가
   - 에러: "UNC 경로는 지원되지 않습니다"

2. **경로 파싱 오류**
   - 배치 파일 변수가 제대로 파싱되지 않음
   - 'pt', '_IP', 'g' 등의 알 수 없는 명령어 오류

### 해결 방안
Windows 배치 파일을 단순 래퍼로 만들고, 실제 로직은 WSL bash 스크립트에서 처리

### 새로운 배포 구조
```
Windows 환경                WSL 환경                    EC2 환경
deploy.bat       →        deploy_wsl.sh      →       AlbraTrading
(단순 호출)              (실제 배포 로직)           (운영 시스템)
```

### 파일별 역할

#### deploy.bat / deploy_v2.bat
- 역할: WSL 스크립트 호출만 수행
- 내용:
  ```batch
  wsl bash -c "cd /home/albra/AlbraTrading && chmod +x ./scripts/deploy_wsl.sh && ./scripts/deploy_wsl.sh"
  ```

#### scripts/deploy_wsl.sh
- 역할: 실제 배포 로직 수행
- 주요 기능:
  1. 로컬 검증 (Python 스크립트 실행)
  2. SSH 연결 테스트
  3. 파일 업로드 (SCP)
  4. 서비스 설정 및 시작
  5. 배포 결과 확인

### 경로 관리 전략

| 용도 | 경로 | 사용 위치 |
|------|------|-----------|
| WSL 내부 작업 | `/home/albra/AlbraTrading` | bash 스크립트 |
| EC2 배포 경로 | `/home/ubuntu/AlbraTrading` | SSH/SCP 명령 |
| SSH 키 | `~/.ssh/trading-bot-key` | WSL 내부 |

### systemd 서비스 파일 관리

EC2와 로컬 환경의 경로 차이를 해결하기 위해 버전별 서비스 파일 관리:
- `*.service.local`: 로컬 환경용 (사용자: albra)
- `*.service.ec2`: EC2 환경용 (사용자: ubuntu)
- `*.service`: 기본 파일 (EC2용)

배포 시 자동으로 EC2 버전 선택하여 업로드

### 주의사항

1. **SSH 키 위치**
   - Windows: `%USERPROFILE%\.ssh\trading-bot-key`
   - WSL: `~/.ssh/trading-bot-key`
   - 배포 스크립트는 WSL 키 사용

2. **Python 실행**
   - Windows Python이 아닌 WSL Python 사용
   - `wsl python3` 명령으로 실행

3. **파일 권한**
   - bash 스크립트는 실행 권한 필요
   - `chmod +x` 자동 수행

### 배포 프로세스

1. Windows 명령 프롬프트에서 `deploy_v2.bat` 실행
2. WSL bash 환경으로 전환
3. `deploy_wsl.sh` 스크립트 실행
4. 로컬 검증 → 파일 업로드 → 서비스 시작
5. 결과 확인 및 알림

### 트러블슈팅

#### "command not found" 오류
- 원인: WSL이 설치되지 않음
- 해결: WSL2 설치 필요

#### SSH 연결 실패
- 원인: SSH 키 경로 문제
- 해결: WSL 내부 `~/.ssh/trading-bot-key` 확인

#### 파일 업로드 실패
- 원인: 경로 또는 권한 문제
- 해결: WSL 내부에서 직접 scp 명령 테스트

---
*작성일: 2025-01-30*