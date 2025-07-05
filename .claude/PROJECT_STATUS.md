# AlbraTrading 프로젝트 상태

## 📊 프로젝트 개요
- **프로젝트명**: AlbraTrading
- **설명**: AWS EC2에서 24/7 운영되는 바이낸스 자동 트레이딩 시스템
- **시작일**: 2025년 이전
- **현재 버전**: v2.0 (Multi-Account Edition)
- **마지막 업데이트**: 2025-07-05 22:05:55

## 🎯 프로젝트 목표
1. 안정적인 24/7 자동 트레이딩 시스템 운영
2. 멀티 계좌/멀티 전략 지원
3. 실시간 모니터링 및 리스크 관리
4. Claude Code를 통한 효율적인 개발 워크플로우

## 📊 프로젝트 통계
- **Python 파일**: 9377개
- **테스트 파일**: 2259개
- **문서 파일**: 50개
- **설정 파일**: 81개
- **총 코드 라인**: 4,367,320줄

## 🔀 Git 상태
- **현재 브랜치**: main
- **변경된 파일**: 10개
- **마지막 커밋**: 2025-07-05 21:59:33

### 최근 커밋
- a655db3 feat: Streamlit 백테스팅 플랫폼 구현
- c214097 feat: 엔터프라이즈급 백테스팅 시스템 및 자연어 전략 빌더 구현
- 50438ca docs: 자동 문서 업데이트 시스템 가이드 추가
- da83830 test: CLAUDE.md 자동 업데이트 테스트 - src 파일 수정
- 55b94b9 docs: 자동 업데이트된 프로젝트 문서

### 변경된 파일
- ?? venv_linux/bin/jsonschema
- ?? venv_linux/bin/plotly_get_chrome
- ?? venv_linux/bin/pwiz.py
- ?? venv_linux/bin/sample
- ?? venv_linux/bin/streamlit
- ?? venv_linux/bin/streamlit.cmd
- ?? venv_linux/bin/watchmedo
- ?? venv_linux/bin/websockets
- ?? venv_linux/etc/
- ?? venv_linux/share/jupyter/

## 🔧 시스템 구성 요소

### 활성 전략 (5개)
- **momentum_strategy**: momentum_strategy.py
- **tfpe_strategy**: tfpe_strategy.py
- **zlmacd_ichimoku_strategy**: zlmacd_ichimoku_strategy.py
- **template_strategy**: template_strategy.py
- **zlhma_ema_cross_strategy**: zlhma_ema_cross_strategy.py

### 핵심 모듈 (21개)
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

### 🔴 높은 우선순위 (11개)
- analyze_btc_detailed.py 크로스 윈도우 적용
- 운영 전략(zlmacd_ichimoku_strategy.py)에 크로스 윈도우 적용
- 1시간마다 시스템 상태 리포트 미수신 문제 확인

### 🟡 중간 우선순위 (13개)
- POSITION_SYNC_ERROR 해결방안 검토
- 백테스트 모듈 리팩토링
- 데이터 로더 성능 최적화

### ✅ 최근 완료된 작업
- ZLMACD Ichimoku 크로스 윈도우 방식 구현 (2025-07-05)
- ZLMACD Ichimoku 4개 조건 필수 변경 (2025-07-04)
- ZLMACD Ichimoku Day Trading 백테스트 구현 (2025-07-04)
- 프로젝트 문서 업데이트 - 실제 운영 전략 반영 (2025-07-04)
- EC2 t3.micro → t3.small 업그레이드 (2025-07-03)

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
*자동 생성: 2025-07-05 22:05:55*
