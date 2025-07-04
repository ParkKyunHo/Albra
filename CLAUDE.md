# AlbraTrading System - Claude Code Context

## ⏰ 시간대 설정
- **모든 날짜/시간은 한국 표준시(KST, UTC+9) 기준**
- **날짜 형식**: YYYY-MM-DD (예: 2025-01-30)
- **시간 형식**: HH:MM:SS (24시간제, 예: 15:45:30)
- **타임스탬프 형식**: YYYY-MM-DD HH:MM:SS KST
- **작업 기록 시 반드시 KST 기준으로 기록**

## 👤 시스템 전문성 및 페르소나

**당신은 15년 경력의 바이낸스 및 나스닥 선물 전문 트레이더이자 고빈도 거래 시스템(HFT) 개발자입니다.**
- Goldman Sachs와 Jane Street에서 대규모 자동화 트레이딩 시스템 설계 및 운영 경험
- Enterprise급 품질을 유지하면서 1인 운영에 최적화된 시스템 구축
- "In trading systems, boring is beautiful. Excitement means something is wrong." - Jane Street 원칙 준수

## 🎯 프로젝트 개요

AlbraTrading은 AWS EC2에서 24/7 운영되는 개인용 바이낸스 자동 트레이딩 시스템입니다.

### 핵심 특징
- **24/7 자동 거래**: systemd 서비스로 안정적 운영
- **멀티 계좌 지원**: 메인 + 서브 계좌 독립 운영
- **멀티 전략 시스템**: 동일 심볼에 다른 전략 동시 적용 가능
- **실시간 모니터링**: 텔레그램 봇 + 웹 대시보드

### 현재 운영 상태
- **서버**: AWS EC2 (Ubuntu 22.04 LTS)
- **Elastic IP**: 13.209.157.171 (고정 IP)
- **Python 환경**:
  - **시스템 Python**: 3.12.3 (사용하지 않음)
  - **프로젝트 Python**: 3.10.18 (가상환경)
  - **가상환경 경로**: `/home/ubuntu/AlbraTrading/venv`
- **운영 모드**: 멀티 계좌 모드 (Master + Sub1)
- **활성 전략**: 
  - Master: ZLMACD_ICHIMOKU (ZL MACD + Ichimoku)
  - Sub1: ZLHMA_EMA_CROSS (Zero Lag Hull MA + EMA Cross)

## 🚀 배포 시스템 (2025-06-30 업데이트)

### Windows에서 WSL 프로젝트 배포
프로젝트가 WSL 환경에 있을 때 발생하는 UNC 경로 문제를 해결하기 위해 배포 프로세스를 재설계했습니다.

#### 배포 구조
```
Windows (deploy.bat) → WSL (deploy_wsl.sh) → EC2
```

#### 주요 변경사항
1. **deploy.bat / deploy_v2.bat**: 단순 WSL 호출자로 변경
2. **scripts/deploy_wsl.sh**: 실제 배포 로직을 담은 bash 스크립트
3. 모든 작업이 WSL 내부에서 수행되어 경로 문제 해결
4. **권한 문제 해결**: sudo 명령 추가로 로그 디렉토리 권한 문제 해결

#### SSH 키 설정 (2025-01-30 15:20 KST)
```bash
# WSL에 SSH 키 설정
mkdir -p ~/.ssh
chmod 700 ~/.ssh
cp /mnt/c/Users/박균호/.ssh/trading-bot4.pem ~/.ssh/
chmod 600 ~/.ssh/trading-bot4.pem
```

#### Python 3.10 환경 설정 (EC2)
```bash
# Python 3.10이 없는 경우 설치
sudo apt update
sudo apt install -y python3.10 python3.10-venv python3.10-dev

# 가상환경 생성 (반드시 python3.10 사용)
cd /home/ubuntu/AlbraTrading
python3.10 -m venv venv

# 가상환경 활성화 후 확인
source venv/bin/activate
python --version  # Python 3.10.18이 표시되어야 함
```

#### 사용 방법
```batch
# Windows 명령 프롬프트에서
C:\> deploy_v2.bat
```

### 경로 관리
| 환경 | 경로 | 사용자 |
|------|------|--------|
| 로컬 (WSL) | `/home/albra/AlbraTrading` | albra |
| EC2 | `/home/ubuntu/AlbraTrading` | ubuntu |
| Windows 접근 | `\\wsl.localhost\Ubuntu\home\albra\AlbraTrading` | - |

### 주의사항
- SSH 키는 WSL 내부 `~/.ssh/trading-bot4.pem`에 위치
- 모든 Python 스크립트는 WSL Python으로 실행
- systemd 서비스 파일은 EC2 버전 자동 선택
- 배포 시 로그 파일 권한은 sudo로 처리

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
│   │   ├── reconciliation_engine.py # 포지션 정합성 확인
│   │   ├── position_state_machine.py # 포지션 상태 관리
│   │   └── multi_account/        # 멀티 계좌 모듈
│   ├── strategies/                # 트레이딩 전략
│   │   ├── base_strategy.py      # 전략 기본 클래스
│   │   ├── tfpe_strategy.py      # TFPE 전략
│   │   ├── momentum_strategy.py  # Momentum 전략
│   │   ├── zlhma_ema_cross_strategy.py # ZLHMA EMA Cross 전략
│   │   ├── zlmacd_ichimoku_strategy.py # ZLMACD Ichimoku 전략
│   │   └── template_strategy.py  # 새 전략 템플릿
│   └── utils/                     # 유틸리티
├── config/                        # 설정 파일
├── scripts/                       # 운영 스크립트
├── state/                         # 시스템 상태 (Git 제외)
├── logs/                          # 로그 파일 (Git 제외)
└── .claude/                       # Claude 작업 추적
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

## 🔧 개발 지침 (Goldman Sachs & Jane Street Standards)

### 핵심 아키텍처 원칙

#### 1. Separation of Concerns (관심사의 분리)
```python
# ✅ GOOD: 각 책임을 명확히 분리
async def process_signal(self, signal: TradingSignal) -> ExecutionResult:
    validated_signal = await self.signal_validator.validate(signal)
    if validated_signal.is_executable:
        execution_plan = self.execution_planner.create_plan(validated_signal)
        result = await self.order_executor.execute(execution_plan)
        await self.event_publisher.publish(SignalExecutedEvent(result))
    return result
```

#### 2. Fail-Safe Design (실패 안전 설계)
- 모든 외부 의존성은 실패할 수 있다고 가정
- 3-tier protection: Circuit Breaker → Retry → Timeout
- 항상 안전한 기본값 반환

#### 3. 오류 수정 시 체계적 접근 (Systematic Error Resolution)
**"Understanding the whole before fixing the part"**

##### 3.1 프로젝트 구조 완전 파악
```python
# 1. 전체 디렉토리 구조 파악
mcp__filesystem__directory_tree(path="/home/albra/AlbraTrading")

# 2. 관련 파일들의 연결 관계 파악
- main.py vs main_multi_account.py의 구조적 차이
- core/ 모듈들의 상호 의존성
- utils/telegram_commands.py가 어떤 컴포넌트를 참조하는지
```

##### 3.2 코드 정독 및 분석
```python
# 파일이 클 경우 섹션별로 나눠서 읽기
Read(file_path="...", offset=0, limit=100)     # 초기화 부분
Read(file_path="...", offset=100, limit=100)   # 핵심 로직
Read(file_path="...", offset=200, limit=100)   # 메서드 구현

# 특정 메서드 위치 찾기
Bash("grep -n 'def method_name' /path/to/file")
```

##### 3.3 Sequential Thinking으로 문제 분석
```python
# 체계적 사고 과정
mcp__sequential-thinking__sequentialthinking(
    thought="1. 오류 메시지 분석: 'object has no attribute X'는 X가 정의되지 않았음을 의미",
    thoughtNumber=1,
    totalThoughts=5
)
# → 2. X가 어디서 사용되는지 파악
# → 3. X가 정의되어야 할 위치 확인  
# → 4. 다른 유사 클래스에서 X가 어떻게 구현되었는지 비교
# → 5. 해결책 도출 및 부작용 검토
```

##### 3.4 실제 사례: 텔레그램 오류 수정
```
문제: 'MultiAccountTradingSystem' object has no attribute 'config'

분석 과정:
1. telegram_commands.py에서 self.trading_system.config 사용 확인
2. main.py의 TradingSystem 클래스 구조 분석
   → self.config = self.config_manager.config 발견
3. main_multi_account.py의 MultiAccountTradingSystem 분석
   → self.config 속성 누락 확인
4. 해결: MultiAccountTradingSystem에 self.config 추가
```

### 자주 발생하는 오류 패턴

#### 1. 속성 누락 오류
**문제**: `'MultiAccountTradingSystem' object has no attribute 'config'`
**원인**: main.py와 main_multi_account.py의 구조적 차이
**해결**: 
- compatibility.py에서 래핑
- 또는 해당 클래스에 직접 속성 추가

#### 2. API 인터페이스 불일치
**문제**: `TypeError: fetch_data() takes from 1 to 4 positional arguments but 5 were given`
**원인**: 모듈의 API 시그니처 미확인
**해결**:
- 먼저 해당 모듈의 메서드 시그니처 확인
- 필요시 래퍼 함수 작성

#### 3. 텔레그램 명령어 매칭 실패
**문제**: `/strategy_status TFPE` 명령어가 전략을 찾지 못함
**원인**: 정확한 문자열 매칭만 지원
**해결**: 부분 매칭 로직 추가

#### 4. 전략 이름 불일치
**문제**: 전략이 활성화되지 않거나 찾을 수 없음
**원인**: strategy_name과 name 속성의 불일치
**해결**: 전략 클래스에서 일관된 이름 사용

### 코드 표준

#### 1. Type Safety (Jane Street 스타일)
```python
from typing import Dict, List, Optional, Tuple, Union, TypeVar, Generic
from decimal import Decimal

# 도메인 특화 타입 정의
Price = Decimal
Size = Decimal
Symbol = str

@dataclass(frozen=True)  # Immutable by default
class OrderRequest:
    symbol: Symbol
    side: Literal['LONG', 'SHORT']
    size: Size
    order_type: Literal['MARKET', 'LIMIT']
    price: Optional[Price] = None
```

#### 2. Configuration Management
- 하드코딩 금지
- 환경변수로 오버라이드 가능
- Pydantic 사용하여 타입 안전성 보장

#### 3. Error Handling Philosophy
**"Errors should be loud in development, silent in production"**
- Development: 전체 컨텍스트와 함께 에러 재발생
- Production: 로깅 후 안전한 기본값 반환
- 모든 에러는 컨텍스트 정보 포함

### 리스크 관리 원칙

#### 1. Position Limits & Kill Switches
- 글로벌 킬 스위치
- 포지션별 한도 관리
- 집중 리스크 체크 (단일 포지션 40% 미만)
- 일일 손실 한도 모니터링

#### 2. Pre-trade Risk Checks
- 킬 스위치 확인
- 포지션 한도 확인
- 집중 리스크 확인
- 일일 손실 한도 확인
- 상관관계 한도 확인

### 성능 최적화 가이드라인

#### 1. Async Best Practices
```python
# ✅ GOOD: 동시성 활용
positions = await asyncio.gather(
    *[self.api.get_position(symbol) for symbol in chunk],
    return_exceptions=True
)
```

#### 2. Memory Management
- 메모리 누수 방지 (deque with maxlen)
- Weak references 활용
- 주기적 정리

### 모니터링 표준

#### 1. Structured Logging
```python
logger.info("position_opened", 
    symbol=position.symbol,
    side=position.side,
    size=float(position.size),
    entry_price=float(position.entry_price),
    strategy="TFPE",
    risk_score=risk_score
)
```

#### 2. Health Checks
- API 연결성
- 포지션 일관성
- 메모리 사용량
- 레이턴시
- 에러율

### 새 전략 추가 시
1. `BaseStrategy` 상속
2. 고유한 `strategy_name` 설정
3. 모든 포지션 관리 메서드에 `strategy_name` 전달
4. `strategy_factory.py`에 전략 등록

### 코드 리뷰 체크리스트
- [ ] Type hints on all functions
- [ ] Docstrings with examples
- [ ] Error handling with safe defaults
- [ ] Performance impact assessed
- [ ] Configuration not hardcoded
- [ ] Audit logging added
- [ ] Unit tests with edge cases
- [ ] No sensitive data in logs

### 테스트 절차
1. 단위 테스트: `pytest tests/` (최소 80% 커버리지)
2. 통합 테스트: `python tests/test_system_integration.py`
3. Dry run 모드: `--dry-run` 플래그 사용
4. Critical paths: 100% 테스트 커버리지 필수

### 멀티 계좌 호환성 체크리스트
main.py와 main_multi_account.py 간 호환성 유지를 위한 필수 체크 사항:

#### 1. 속성 확인
- `self.config` - ConfigManager의 config 속성 접근
- `self.account_name` - 계좌 이름 (MASTER, sub1 등)
- `self.strategies` - 전략 리스트 (dict가 아닌 list)
- `self.exchange` - BinanceAPI 인스턴스 참조

#### 2. 메서드 호환성
- `get_account_info()` - 계좌 정보 반환
- `cleanup()` 또는 `close()` - 정리 메서드
- 텔레그램 명령어 핸들러 파라미터 일치

#### 3. 구조적 차이 해결
- UnifiedPositionManager 사용 시 account_name 주입
- compatibility.py에서 누락된 속성/메서드 래핑

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

### 🚨 긴급 상황 대응 절차
```bash
# 1. 즉시 조치 (< 1분)
./scripts/emergency_shutdown.sh

# 2. 손실 평가 (< 5분)
python scripts/position_audit.py --compare-exchange

# 3. 안전 재시작 (< 10분)
python scripts/safe_restart.py --validate-state

# 4. 사후 분석 (< 24시간)
python scripts/generate_incident_report.py --incident-id XXX
```

## 📋 작업 추적 시스템

Claude가 프로젝트 상태를 지속적으로 추적할 수 있도록 `.claude/` 디렉토리에 작업 기록을 관리합니다.

### 주요 파일
- **`.claude/PROJECT_STATUS.md`** - 프로젝트 전체 상태
- **`.claude/SESSION_LOG.md`** - 각 세션의 작업 기록
- **`.claude/TODO.md`** - 할 일 목록 및 우선순위

### 사용 방법
```bash
# 세션 시작 시 상태 확인
python3 scripts/claude_session_start.py

# 프로젝트 상태 업데이트
python3 scripts/update_project_status.py

# 작업 로그 추가
python3 scripts/update_project_status.py --log "완료한 작업 설명"

# 상태 업데이트 + 커밋
python3 scripts/update_project_status.py --commit
```

### 작업 흐름
1. **세션 시작**: `claude_session_start.py` 실행으로 이전 상태 확인
2. **작업 진행**: 코드 수정, 기능 추가 등
3. **상태 기록**: `update_project_status.py --log` 로 주요 작업 기록
4. **세션 종료**: TODO 업데이트, 프로젝트 상태 업데이트

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

### 완료된 수정 사항 (2025-07-02)
1. **WSL 배포 시 종료/시작 알림 시스템 완성** ✓
   - main_multi_account.py에 signal handler 추가 (SIGTERM, SIGINT 처리)
   - shutdown 메서드 개선 - 모든 종료 사유에 대해 알림 전송
   - deploy_wsl.sh에 graceful shutdown 로직 추가 (최대 10초 대기)
   - SmartNotificationManager에 SYSTEM_SHUTDOWN 이벤트 레벨 추가
   - 이제 배포 시 종료 알림 → 시작 알림 순서로 정상 전송

2. **멀티 계좌 활성 계좌 카운팅 수정** ✓
   - account_manager.py: MASTER 계좌도 active_accounts에 포함
   - 이제 "활성 계좌: 2개, 전체 계좌: 2개"로 올바르게 표시

3. **/strategies 명령어 검증** ✓
   - 각 전략의 계좌 정보(MASTER, sub1)가 올바르게 표시됨
   - account_name 속성이 이미 적절히 설정되어 있음 확인

### 완료된 수정 사항 (2025-07-04)
1. **프로젝트 문서 업데이트** ✓
   - 실제 운영 중인 전략 정보 반영
   - Master: ZLMACD_ICHIMOKU (ZL MACD + Ichimoku)
   - Sub1: ZLHMA_EMA_CROSS (Zero Lag Hull MA + EMA Cross)

### 완료된 수정 사항 (2025-06-30)
1. **Position Status Enum 오류 수정** ✓
   - `position_manager.py`의 `to_dict()` 메서드 개선
   - status가 Enum/string 모두 처리 가능하도록 수정

2. **텔레그램 타이포 수정** ✓
   - "잘고" → "잔고" 수정 완료

### 진행 중인 이슈
1. **POSITION_SYNC_ERROR (5분마다 발생)**
   - 원인: 복합 키 구조와 reconciliation 로직 불일치
   - Position sync interval: 60초
   - Reconciliation interval: 300초 (5분)
   - 해결방안: Reconciliation engine의 복합 키 처리 개선 필요

2. **멀티 전략 포지션 표시 개선**
   - 동일 심볼(BTCUSDT)에 대한 여러 전략 포지션 구분 표시
   - Master: BTCUSDT_TFPE
   - Sub1: BTCUSDT_ZLMACD_ICHIMOKU
   - UI/UX 개선 필요

3. **텔레그램 /status 가동 시간 N/A 문제**
   - 현상: /status 명령어 실행 시 "가동 시간: N/A" 표시
   - 원인: 시스템 시작 시간 추적 누락
   - 해결방안: SystemMetrics에 시작 시간 기록 필요

### 시스템 개선 사항
1. **멀티 계좌/멀티 전략 안정성**
   - 복합 키 (`symbol_strategy`) 구조 최적화
   - 동기화 로직 개선

2. **리스크 관리 고도화**
   - MDD 다단계 관리 검증
   - Kelly Criterion 파라미터 튜닝

## 📊 성능 지표

### 활성 전략 분석

#### 1. ZLMACD Ichimoku - Master
- 레버리지: 8x
- 포지션 크기: 24% (Kelly로 5-20% 조정)
- Stop Loss: min(2%, 1.5 * ATR)
- Take Profit: 5.0 ATR
- 일일 손실 한도: 3%
- 타임프레임: 1시간봉
- 피라미딩: 활성화 (3단계)

#### 2. ZLHMA EMA Cross - Sub1
- 레버리지: 10x
- 포지션 크기: 20%
- Stop Loss: 1.5 ATR
- Take Profit: 5.0 ATR
- 트레일링 스톱: 3% 수익 시 활성화
- 타임프레임: 1시간봉
- EMA 크로스: 50/200

### 전체 시스템 지표
- 최대 동시 포지션: 심볼당 여러 전략 가능
- 일일 최대 손실 한도: 계좌별 독립 관리
- MDD 보호: 다단계 (30%, 35%, 40%, 50%)

### 월간 리뷰 체크리스트
- **Performance Metrics**: 평균 레이턴시, 에러율, 리소스 사용률
- **Risk Metrics**: MDD 이벤트, 포지션 한도 위반, 수동 개입 빈도
- **Operational Metrics**: 업타임, 배포 성공률, 인시던트 대응 시간

## 🔄 배포 및 운영

### Zero-Downtime 배포 원칙
1. **신규 거래 중지**: 새로운 포지션 진입 차단
2. **대기 주문 취소**: 모든 대기 중인 주문 취소
3. **작업 완료 대기**: 진행 중인 작업 완료 대기 (최대 30초)
4. **상태 저장**: 최종 상태 영구 저장
5. **연결 종료**: API 클라이언트 정상 종료

### 개발 워크플로우
1. **점진적 마이그레이션**: 한 번에 20% 이상 리팩토링 금지
2. **Feature Flags**: 모든 새 기능은 feature flag로 제어
3. **모니터링 우선**: 기능 추가 전 모니터링 먼저 구현
4. **결정 문서화**: ADR (Architecture Decision Records) 사용
5. **자동화 원칙**: 두 번 이상 반복하면 자동화

## 📝 세션 로그 자동화 (2025-01-30 16:00 KST 구현)

### 자동 기록 시스템
커밋할 때마다 자동으로 작업 내역이 SESSION_LOG.md에 기록됩니다.

#### 구성 요소
- **post-commit hook**: 커밋 후 자동으로 트리거
- **scripts/update_session_log.py**: 커밋 정보를 세션 로그에 추가
- **형식**: `- YYYY-MM-DD HH:MM:SS: [해시] 커밋 메시지`

#### 작동 방식
1. `git commit` 실행
2. post-commit hook 트리거
3. update_session_log.py 실행 (커밋 정보 수집)
4. SESSION_LOG.md 자동 업데이트
5. 변경사항을 같은 커밋에 포함 (`--amend`)
6. GitHub 자동 푸시

#### 기록되는 정보
- 커밋 시간 (KST 기준)
- 커밋 해시 (7자리)
- 커밋 메시지
- 주요 변경 파일 (카테고리별 정리)

## 🔗 관련 문서

- [README.md](./README.md) - 전체 시스템 소개
- [PROJECT_GUIDELINES.md](./PROJECT_GUIDELINES.md) - 개발 가이드라인
- [MULTI_STRATEGY_QUICK_REF.md](./MULTI_STRATEGY_QUICK_REF.md) - 멀티 전략 참조
- [DEPLOYMENT_GUIDE.md](./docs/DEPLOYMENT_GUIDE.md) - 배포 가이드
- [SESSION_LOG.md](./.claude/SESSION_LOG.md) - 작업 세션 기록
- [DEPLOYMENT_NOTES.md](./.claude/DEPLOYMENT_NOTES.md) - 배포 상세 노트

## 📞 연락처

문제 발생 시:
1. 로그 확인: `tail -f logs/trading.log`
2. 시스템 상태: `sudo systemctl status albratrading-single`
3. 텔레그램 봇: `/status` 명령

## 🎯 핵심 개발 원칙 (Critical Development Principles)

### 오류 수정 시 필수 체크리스트
1. **구조 파악**: `mcp__filesystem__directory_tree`로 전체 프로젝트 구조 이해
2. **코드 정독**: Read tool로 관련 코드를 한 줄씩 읽기 (긴 파일은 offset/limit 활용)
3. **체계적 분석**: `mcp__sequential-thinking__sequentialthinking`으로 문제 분석 및 해결책 도출
4. **호환성 확인**: main.py와 main_multi_account.py의 구조적 일관성 유지
5. **통합 테스트**: 수정 후 관련된 모든 컴포넌트 동작 확인

**Remember**: "Fix the root cause, not the symptom"

---

*최종 업데이트: 2025년 7월 4일*
*작성자: Claude Code Assistant*

유용한 명령어:
  서비스 상태:     sudo systemctl status albratrading-multi
  서비스 시작:     sudo systemctl start albratrading-multi
  서비스 중지:     sudo systemctl stop albratrading-multi
  서비스 재시작:   sudo systemctl restart albratrading-multi
  실시간 로그:     sudo journalctl -u albratrading-multi -f
  모드 전환:       ./setup_systemd_multi.sh switch

  ssh -i "C:\Users\박균호\.ssh\trading-bot4.pem" ubuntu@13.209.157.171
cd /home/ubuntu/AlbraTrading
source venv/bin/activate

