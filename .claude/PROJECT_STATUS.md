# AlbraTrading 프로젝트 상태

## 📊 프로젝트 개요
- **프로젝트명**: AlbraTrading
- **설명**: AWS EC2에서 24/7 운영되는 바이낸스 자동 트레이딩 시스템
- **시작일**: 2025년 이전
- **현재 버전**: v2.0 (Multi-Account Edition)
- **마지막 업데이트**: 2025-07-01 12:33:05

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
- **변경된 파일**: 4개
- **마지막 커밋**: 2025-07-01 12:17:07

### 최근 커밋
- 1e85b71 feat: 새 AWS EC2 인스턴스(54.88.60.48) 설정 및 배포 스크립트 업데이트
- cfbe762 fix: 시스템 구조 완전 분석 후 핵심 오류 수정
- ba946f1 fix: Flask 대시보드 실행 방법 및 알림 파라미터 수정
- 8ccdd7d fix: 시스템 설계를 고려한 모니터링 및 종료 처리 개선
- 2bcb08c fix: ImprovedMDDManager initialize() 메서드 호출 제거

### 변경된 파일
- M  .claude/SESSION_LOG.md
-  M .claude/settings.local.json
-  M requirements.txt
-  M scripts/systemd/albratrading-multi.service

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
- **총 오류**: 31개
- **치명적 오류**: 0개
### 최근 오류
- 2025-06-15 14:41:42 - __main__ - ERROR - 호환성 테스트 실패: BinanceAPI.__init__() missing 2 required positi
- 2025-06-15 14:41:42 - __main__ - ERROR - 신호 테스트 실패: BinanceAPI.__init__() missing 2 required positio
- 2025-06-15 14:41:42 - __main__ - ERROR - 모드 전환 테스트 실패: BinanceAPI.__init__() missing 2 required posi

## 📈 진행 상황

### 🚨 긴급 작업 (1개)
- 없음

### 🔴 높은 우선순위 (8개)
- 성능 모니터링 대시보드 개선
- 실시간 차트 업데이트 최적화
- 메모리 사용량 모니터링 추가

### 🟡 중간 우선순위 (12개)
- 백테스트 모듈 리팩토링
- 데이터 로더 성능 최적화
- 병렬 처리 구현

### ✅ 최근 완료된 작업
- Git/GitHub 연동 설정 (2025-01-30)
- CLAUDE.md 작성 및 자동화 (2025-01-30)
- 작업 추적 시스템 구축 (2025-01-30)

## 🏗️ 시스템 아키텍처
- **운영 환경**: AWS EC2 (Ubuntu 22.04)
- **런타임**: Python 3.12 (venv)
- **주요 전략**: TFPE (Trend Following with Price Extremes)
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
*자동 생성: 2025-07-01 12:33:05*
