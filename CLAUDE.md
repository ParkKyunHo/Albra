# AlbraTrading System - Claude Code Context

## 🎯 프로젝트 개요

AlbraTrading은 AWS EC2에서 24/7 운영되는 개인용 바이낸스 자동 트레이딩 시스템입니다.

### 핵심 특징
- **24/7 자동 거래**: systemd 서비스로 안정적 운영
- **멀티 계좌 지원**: 메인 + 서브 계좌 독립 운영
- **멀티 전략 시스템**: 동일 심볼에 다른 전략 동시 적용 가능
- **실시간 모니터링**: 텔레그램 봇 + 웹 대시보드

### 현재 운영 상태
- **서버**: AWS EC2 (Ubuntu 22.04 LTS)
- **Python**: 3.12 (venv 가상환경)
- **운영 모드**: 단일 계좌 모드 (멀티 계좌 지원 가능)
- **활성 전략**: TFPE (Trend Following with Price Extremes)

## 🏗️ 시스템 아키텍처

### 디렉토리 구조
```
AlbraTrading/
├── src/
│   ├── main.py                    # 단일 계좌 진입점
│   ├── main_multi_account.py      # 멀티 계좌 진입점
│   ├── core/                      # 핵심 모듈
│   │   ├── binance_api.py        # 바이낸스 API 래퍼
│   │   ├── position_manager.py    # 포지션 관리 (멀티 전략 지원)
│   │   ├── event_bus.py          # 이벤트 기반 통신
│   │   └── multi_account/        # 멀티 계좌 모듈
│   ├── strategies/                # 트레이딩 전략
│   │   ├── base_strategy.py      # 전략 기본 클래스
│   │   ├── tfpe_strategy.py      # TFPE 전략
│   │   └── template_strategy.py  # 새 전략 템플릿
│   └── utils/                     # 유틸리티
├── config/                        # 설정 파일
├── scripts/                       # 운영 스크립트
├── state/                         # 시스템 상태 (Git 제외)
└── logs/                          # 로그 파일 (Git 제외)
```

### 주요 컴포넌트

#### 1. Position Manager (Multi-Strategy)
- 포지션 키: `{symbol}_{strategy_name}` (예: "BTCUSDT_TFPE")
- 동일 심볼에 다른 전략 포지션 공존 가능
- 자동/수동 포지션 통합 관리

#### 2. Event Bus System
- 컴포넌트 간 느슨한 결합
- 실시간 이벤트 기반 통신
- 주요 이벤트: SIGNAL_GENERATED, POSITION_OPENED, POSITION_CLOSED

#### 3. Risk Management
- MDD (Maximum Drawdown) 관리
- Kelly Criterion 기반 포지션 사이징
- 계좌별 독립적 리스크 관리

## 🔧 개발 지침

### 새 전략 추가 시
1. `BaseStrategy` 상속
2. 고유한 `strategy_name` 설정
3. 모든 포지션 관리 메서드에 `strategy_name` 전달
4. `strategy_factory.py`에 전략 등록

### 코드 컨벤션
- Type hints 사용
- 비동기 함수는 `async/await` 패턴
- 로깅 시 전략명 포함: `[{strategy_name}] 메시지`
- 에러 처리 필수

### 테스트 절차
1. 단위 테스트: `pytest tests/`
2. 통합 테스트: `python tests/test_system_integration.py`
3. Dry run 모드: `--dry-run` 플래그 사용

## 📝 작업 시 주의사항

### 민감한 정보
- API 키는 절대 코드에 하드코딩하지 않음
- `.env` 파일 사용 (Git 제외됨)
- 상태 파일(`state/`)은 Git에 포함하지 않음

### EC2 배포 관련
- 변경사항은 먼저 로컬에서 테스트
- `scripts/safe_deploy_v2.sh` 사용하여 안전한 배포
- systemd 서비스 재시작 필요 시 주의

### 실시간 거래 중 수정
- 포지션이 열려있을 때 코드 수정 자제
- 긴급 수정 시 `/pause` 명령 사용
- 배포 전 백업 필수

## 🔧 Git 설정

### 자동 푸시 설정
커밋 후 자동으로 GitHub에 푸시하려면 다음 Git hook을 설정하세요:

1. **post-commit hook 생성** (✅ 이미 설정됨)
   ```bash
   # .git/hooks/post-commit 파일이 생성되어 있습니다
   # 내용: 커밋 후 자동으로 origin main에 푸시
   ```

2. **Git alias 사용 (선택사항)**
   ```bash
   # 커밋과 푸시를 한 번에
   git config --local alias.cap '!git add -A && git commit -m "$1" && git push origin main'
   # 사용: git cap "커밋 메시지"
   ```

### GitHub 리포지토리
- **Repository**: https://github.com/ParkKyunHo/Albra.git
- **기본 브랜치**: main
- **자동 푸시**: 활성화됨 (post-commit hook)

## 🚀 현재 작업 우선순위

1. **Git/GitHub 연동 설정**
   - 로컬 Git 초기화 ✓
   - GitHub 리포지토리 연결
   - 자동 문서 업데이트 스크립트 ✓

2. **문서 자동화**
   - CLAUDE.md 자동 업데이트 ✓
   - 성능 리포트 생성
   - GitHub Actions 설정 ✓

3. **시스템 개선**
   - 멀티 전략 안정성 검증
   - 리스크 관리 고도화
   - 모니터링 강화

## 📊 성능 지표

### 현재 전략 (TFPE)
- 평균 승률: ~45%
- 리스크/리워드 비율: 1:2
- 최대 동시 포지션: 3개
- 일일 최대 손실 한도: 5%

## 🔗 관련 문서

- [README.md](./README.md) - 전체 시스템 소개
- [PROJECT_GUIDELINES.md](./PROJECT_GUIDELINES.md) - 개발 가이드라인
- [MULTI_STRATEGY_QUICK_REF.md](./MULTI_STRATEGY_QUICK_REF.md) - 멀티 전략 참조
- [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) - 배포 가이드

## 📞 연락처

문제 발생 시:
1. 로그 확인: `tail -f logs/trading.log`
2. 시스템 상태: `sudo systemctl status albratrading-single`
3. 텔레그램 봇: `/status` 명령

---

*최종 업데이트: 2025년 1월 30일*
*작성자: Claude Code Assistant*