# AlbraTrading 프로젝트 상태

## 📊 프로젝트 개요
- **프로젝트명**: AlbraTrading
- **설명**: AWS EC2에서 24/7 운영되는 바이낸스 자동 트레이딩 시스템
- **시작일**: 2025년 이전
- **현재 버전**: v2.0 (Multi-Account Edition)
- **마지막 업데이트**: 2025-07-02 05:56:00

## 🎯 프로젝트 목표
1. 안정적인 24/7 자동 트레이딩 시스템 운영
2. 멀티 계좌/멀티 전략 지원
3. 실시간 모니터링 및 리스크 관리
4. Claude Code를 통한 효율적인 개발 워크플로우

## 📊 프로젝트 통계
- **Python 파일**: 144개
- **테스트 파일**: 18개
- **문서 파일**: 27개
- **설정 파일**: 47개
- **총 코드 라인**: 60,169줄

## 🔀 Git 상태
- **현재 브랜치**: main
- **변경된 파일**: 3개 (CLAUDE.md, SESSION_LOG.md 업데이트 중)
- **마지막 커밋**: 2025-07-02 05:55:33

### 최근 커밋
- be0b4a6 feat: WSL 배포 알림 시스템 완성 및 멀티계좌 카운팅 개선
- 41ad9d6 fix: 멀티 계좌 활성 계좌 카운팅 수정 - MASTER 계좌도 active_accounts에 포함
- 9313f77 fix: SmartNotificationManager에 SYSTEM_SHUTDOWN 이벤트 레벨 추가
- 9c8f6fd fix: 종료 프로세스 디버깅 로그 추가 및 에러 처리 개선
- ebde3b8 fix: UnifiedBinanceAPI cleanup 메서드 체크 추가

### 변경된 파일
- M  CLAUDE.md
- M  .claude/PROJECT_STATUS.md
- M  .claude/SESSION_LOG.md

## 🔧 시스템 구성 요소

### 활성 전략 (5개)
- **momentum_strategy**: momentum_strategy.py
- **tfpe_strategy**: tfpe_strategy.py
- **zlmacd_ichimoku_strategy**: zlmacd_ichimoku_strategy.py
- **template_strategy**: template_strategy.py
- **zlhma_ema_cross_strategy**: zlhma_ema_cross_strategy.py

### 핵심 모듈 (19개)
- **mdd_manager_improved**: 최종 수정 2025-06-30
- **candle_close_monitor**: 최종 수정 2025-06-27
- **hybrid_trading_manager**: 최종 수정 2025-06-22
- **risk_parity_allocator**: 최종 수정 2025-06-27
- **smart_resume_manager**: 최종 수정 2025-06-14

## 🚨 오류 현황
- **총 오류**: 0개 (모든 주요 오류 해결됨)
- **치명적 오류**: 0개
### 최근 해결된 오류
- WSL 배포 시 종료/시작 알림 미전송 문제 해결 (2025-07-02)
- 멀티 계좌 활성 계좌 카운팅 오류 해결 (2025-07-02)
- 텔레그램 명령어 호환성 문제 해결 (2025-07-02)

## 📈 진행 상황

### 🚨 긴급 작업 (0개)
- 없음

### 🔴 높은 우선순위 (2개)
- POSITION_SYNC_ERROR (5분마다 발생) 해결
- 멀티 전략 포지션 표시 UI/UX 개선

### 🟡 중간 우선순위 (3개)
- 백테스트 모듈 리팩토링
- 데이터 로더 성능 최적화
- 병렬 처리 구현

### ✅ 최근 완료된 작업
- WSL 배포 알림 시스템 완성 (2025-07-02)
- 멀티 계좌 활성 계좌 카운팅 수정 (2025-07-02)
- /strategies 명령어 계좌 정보 표시 확인 (2025-07-02)
- EC2 서울 리전 이전 완료 (2025-07-02)
- 멀티 계좌 모드 완전 활성화 (2025-07-02)

## 🏗️ 시스템 아키텍처
- **운영 환경**: AWS EC2 (Ubuntu 22.04) - 서울 리전
- **EC2 IP**: 43.201.76.89
- **런타임**: Python 3.10 (venv) on EC2
- **운영 모드**: 멀티 계좌 모드 (MASTER + Sub1)
- **활성 전략**: 
  - MASTER: TFPE (Trend Following with Price Extremes)
  - Sub1: ZLMACD_ICHIMOKU
- **데이터베이스**: SQLite (trading_bot.db)
- **모니터링**: 텔레그램 봇 + 웹 대시보드

## 🔧 개발 환경
- **Git 브랜치**: main
- **원격 저장소**: GitHub (https://github.com/ParkKyunHo/Albra.git)
- **자동화**: GitHub Actions, Git Hooks
- **문서화**: CLAUDE.md 자동 업데이트

## 📝 참고사항
- EC2 배포 시 `scripts/safe_deploy_v2.sh` 사용
- 실시간 거래 중 코드 수정 자제
- 모든 API 키는 `.env` 파일에 보관
- 작업 추적: `.claude/` 디렉토리 참조

---
*자동 생성: 2025-07-02 05:57:00*
