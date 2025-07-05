# 자동 문서 업데이트 시스템 가이드

## 개요
커밋할 때마다 프로젝트 문서들이 자동으로 업데이트되어 항상 최신 상태를 유지합니다.

## 작동 방식

### 1. 자동 업데이트되는 문서
- **SESSION_LOG.md** - 모든 커밋에서 작업 내역 기록
- **CLAUDE.md** - 중요 디렉토리 변경 시 업데이트
- **PROJECT_STATUS.md** - 주요 변경사항이 있을 때 업데이트

### 2. 스마트 업데이트 로직
- SESSION_LOG.md: 항상 업데이트
- CLAUDE.md: src/, src/core/, src/strategies/, config/ 변경 시
- PROJECT_STATUS.md: src/, scripts/, config/ 등 주요 디렉토리 변경 시

### 3. 업데이트 내용
- 커밋 정보 (해시, 메시지, 시간)
- 변경된 파일 목록
- 활성 전략 상태
- 프로젝트 통계
- Git 브랜치 정보

## 사용 방법

일반적인 Git 워크플로우를 따르시면 됩니다:

```bash
# 파일 수정 후
git add .
git commit -m "feat: 새로운 기능 추가"

# 자동으로 실행되는 작업:
# 1. 문서 업데이트
# 2. 같은 커밋에 포함 (--amend)
# 3. GitHub에 자동 푸시
```

## 주요 파일

### 1. scripts/update_all_docs.py
- 통합 문서 업데이트 스크립트
- SESSION_LOG, CLAUDE.md, PROJECT_STATUS.md 업데이트

### 2. .git/hooks/pre-commit
- 커밋 전 플래그 파일 생성

### 3. .git/hooks/post-commit
- 커밋 후 문서 업데이트 실행
- --amend로 같은 커밋에 포함
- GitHub 자동 푸시

## 장점
- 문서 관리 자동화
- 프로젝트 상태 실시간 추적
- Claude Code 세션 간 연속성 보장
- 커밋 히스토리와 문서 동기화

## 주의사항
- 첫 커밋은 정상적으로 진행됩니다
- 문서 업데이트는 백그라운드에서 자동 처리
- 푸시 실패 시 수동으로 `git push` 실행 필요

## 문제 해결
- 문서가 업데이트되지 않는 경우: 플래그 파일 확인 (`/tmp/albratrading_commit_pending`)
- 무한 루프 발생 시: `SKIP_POST_COMMIT_HOOK=1` 환경변수 설정
- 수동 업데이트: `python3 scripts/update_all_docs.py`