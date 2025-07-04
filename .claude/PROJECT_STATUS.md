# AlbraTrading 프로젝트 상태

## 📊 프로젝트 개요
- **프로젝트명**: AlbraTrading
- **설명**: AWS EC2에서 24/7 운영되는 바이낸스 자동 트레이딩 시스템
- **시작일**: 2025년 이전
- **현재 버전**: v2.0 (Multi-Account Edition)
- **마지막 업데이트**: 2025-07-04 11:48:00

## 🎯 프로젝트 목표
1. 안정적인 24/7 자동 트레이딩 시스템 운영
2. 멀티 계좌/멀티 전략 지원
3. 실시간 모니터링 및 리스크 관리
4. Claude Code를 통한 효율적인 개발 워크플로우

## 📊 프로젝트 통계
- **Python 파일**: 151개
- **테스트 파일**: 21개
- **문서 파일**: 33개
- **설정 파일**: 52개
- **총 코드 라인**: 62,291줄

## 🔀 Git 상태
- **현재 브랜치**: main
- **변경된 파일**: 0개
- **마지막 커밋**: 2025-07-03 05:58:10

### 최근 커밋
- 838a4f5 fix: EC2 t3.micro 메모리 부족 문제 해결 - t3.small 업그레이드 및 스왑 설정
- 516789b fix: TFPE 백테스팅 진입 조건 대폭 단순화 - 거래 발생 문제 해결
- 2f59512 fix: TFPE 백테스팅 개선 - BTC만 분석, 차트 제거, 디버그 로그 추가
- 5a5f5f9 feat: TFPE 전략 백테스팅 프레임워크 구현 및 전진분석 추가
- acb1d22 fix: 크래시 루프 원인 제거 - 중복 시작 메시지 제거 및 가동 시간 표시 수정

### 변경된 파일
- 없음

## 🔧 시스템 구성 요소

### 활성 전략 (5개)
- **momentum_strategy**: momentum_strategy.py
- **tfpe_strategy**: tfpe_strategy.py
- **zlmacd_ichimoku_strategy**: zlmacd_ichimoku_strategy.py
- **template_strategy**: template_strategy.py
- **zlhma_ema_cross_strategy**: zlhma_ema_cross_strategy.py

### 핵심 모듈 (20개)
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
- TFPE 백테스팅 실행 및 결과 분석
- 백테스팅 결과 기반 전략 파라미터 최적화
- 멀티 전략 동시 실행 시 리스크 관리 강화
- 성능 모니터링 대시보드 개선
- 실시간 차트 업데이트 최적화
- 메모리 사용량 모니터링 추가

### 🟡 중간 우선순위 (12개)
- 백테스트 모듈 리팩토링
- 데이터 로더 성능 최적화
- 병렬 처리 구현

### ✅ 최근 완료된 작업
- EC2 t3.micro → t3.small 업그레이드 (2025-07-03)
- EC2 메모리 부족 문제 해결 - 스왑 파일 추가 (2025-07-03)
- SSH 접속 timeout 문제 해결 (2025-07-03)
- 시스템 포지션 인식 개선 (2025-07-03)
- 텔레그램 /strategy_status 명령어 부분 매칭 추가 (2025-07-03)
- TFPE 전략 전진분석 백테스팅 구현 (2025-07-03)
- WSL 배포 시 종료/시작 알림 시스템 완성 (2025-07-02)
- 멀티 계좌 활성 계좌 카운팅 수정 (2025-07-02)

## 🏗️ 시스템 아키텍처
- **운영 환경**: AWS EC2 t3.small (Ubuntu 22.04)
- **런타임**: Python 3.10.18 (venv)
- **주요 전략**: 
  - Master: ZLMACD_ICHIMOKU (ZL MACD + Ichimoku)
  - Sub1: ZLHMA_EMA_CROSS (Zero Lag Hull MA + EMA Cross)
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
*자동 생성: 2025-07-04 11:48:00*
