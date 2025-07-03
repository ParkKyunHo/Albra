# 🚀 AlbraTrading System v2.0 (Multi-Account Edition)

개인용 바이낸스 자동 트레이딩 시스템 - 단일/멀티 계좌 모드 지원

## 📋 목차
- [시스템 개요](#-시스템-개요)
- [주요 기능](#-주요-기능)
- [설치 방법](#-설치-방법)
- [사용 방법](#-사용-방법)
- [멀티 계좌 시스템](#-멀티-계좌-시스템)
- [운영 가이드](#-운영-가이드)
- [문제 해결](#-문제-해결)
- [주의사항](#-주의사항)

## 🎯 시스템 개요

AlbraTrading은 1인 사용자를 위한 바이낸스 자동 트레이딩 시스템입니다.  
**v2.0부터 멀티 계좌 모드를 지원하여 메인/서브 계좌를 독립적으로 운영할 수 있습니다.**

### 핵심 원칙
- **1인 전용**: 과도한 확장성보다 안정성 우선
- **24/7 운영**: AWS EC2에서 안정적인 자동 거래
- **심플함 유지**: 필요한 기능만 구현, 복잡성 최소화
- **멀티 계좌 지원**: 전략별 계좌 분리 운영 (Phase 2)

### 현재 운영 환경
- **서버**: AWS EC2 (Ubuntu 22.04 LTS)
- **Elastic IP**: 13.209.157.171 (고정 IP)
- **Python**: 3.10.18 (venv 가상환경)
- **실행 방식**: systemd 서비스 (단일/멀티 모드 선택 가능)
- **운영 모드**: 단일 계좌 모드 또는 멀티 계좌 모드

## 🔧 주요 기능

### 1. 실시간 가격 모니터링
- WebSocket 기반 실시간 가격 추적 (선택적)
- 이벤트 기반 신호 처리
- 멀티 심볼 동시 모니터링

### 2. 포지션 관리
- **통합 관리**: 자동/수동 포지션 통합 관리
- **상태 추적**: ACTIVE, CLOSED, MODIFIED, PAUSED
- **실시간 동기화**: 60초 간격 자동 동기화
- **멀티 계좌 지원**: 계좌별 독립적 포지션 관리

### 3. 멀티 계좌 시스템 (Phase 2)
- **계좌 관리**: 메인 + 다중 서브 계좌 지원
- **전략 할당**: 계좌별 다른 전략 운영
- **통합 모니터링**: 포트폴리오 전체 상태 확인
- **리스크 분산**: 계좌별 독립적 리스크 관리
- **전략 독립성**: 각 전략이 리스크를 독립적으로 판단하고 결정

### 4. 알림 시스템
- **우선순위 기반**: CRITICAL > HIGH > MEDIUM > LOW
- **텔레그램 통합**: 실시간 알림 및 명령어
- **스마트 필터링**: 중요 이벤트만 선별 알림
- **멀티 계좌 알림**: 계좌별 구분된 알림

### 5. 현재 운영 전략

#### TFPE (Trend Following with Price Extremes)
- **계좌**: Master
- **타임프레임**: 4시간봉 기준
- **특징**:
  - 20기간 Donchian Channel 추세 감지
  - 다중 신호 확인 시스템 (4/7 이상)
  - ATR 기반 동적 손절/익절
  - Kelly Criterion 기반 포지션 사이징
  - 레버리지: 10x

#### ZLMACD Ichimoku (Zero Lag MACD + Ichimoku Cloud)
- **계좌**: Master
- **타임프레임**: 1시간봉 전용
- **특징**:
  - Zero Lag MACD 크로스 신호
  - Ichimoku Cloud 추세 확인
  - 3단계 부분 익절 시스템 (5%, 10%, 15%)
  - 3단계 피라미딩 (4%, 6%, 9% 수익 시)
  - Kelly Criterion 동적 포지션 사이징 (5-20%)
  - 레버리지: 10x (백테스트 개선)
  - 초기 손절: 1.5% (백테스트 개선)
  - Walk-Forward 백테스트 결과: 평균 수익률 68.4%, Sharpe 3.18

#### ZLHMA EMA Cross (Zero Lag HMA + 50/200 EMA Cross)
- **계좌**: Sub1
- **타임프레임**: 1시간봉
- **특징**:
  - Zero Lag Hull MA + 50/200 EMA 골든/데드 크로스
  - ADX 추세 필터 (>25)
  - 트레일링 스톱 (5% 수익 시 활성화, 2% 트레일)
  - 3단계 부분 익절 (5%, 10%, 15%)
  - Kelly Criterion 포지션 사이징
  - 레버리지: 10x

### 6. Multi-Strategy Position Management ⭐ NEW
시스템은 여러 전략이 동일한 심볼을 독립적으로 거래할 수 있도록 설계되었습니다.

#### 핵심 개념
- **복합 키 구조**: 포지션은 `{symbol}_{strategy_name}` 형식으로 저장
- **전략 독립성**: 각 전략은 다른 전략의 포지션에 영향을 주지 않음
- **동일 심볼 거래**: TFPE와 ZLMACD가 동시에 BTCUSDT 거래 가능

#### 새 전략 추가 시 필수 사항
```python
# 1. 전략명 설정 (고유해야 함)
self.strategy_name = "MY_NEW_STRATEGY"

# 2. 포지션 조회 시 strategy_name 전달
position = self.position_manager.get_position(symbol, self.strategy_name)

# 3. 포지션 추가 시 strategy_name 전달
await self.position_manager.add_position(
    symbol=symbol,
    strategy_name=self.strategy_name  # 필수!
)
```

#### 참고 문서
- [PROJECT_GUIDELINES.md](./PROJECT_GUIDELINES.md) - 전략 추가 상세 가이드
- [template_strategy.py](./src/strategies/template_strategy.py) - 전략 템플릿

## 💻 설치 방법

### 1. 새 컴퓨터에 설치 (Windows)

#### 사전 준비
```bash
# Python 3.12 이상 설치
# Git 설치
```

#### 프로젝트 클론
```bash
cd C:\
git clone [repository-url] AlbraTrading
cd AlbraTrading
```

#### Python 3.10 확인 및 가상환경 설정
```bash
# Python 3.10 확인 (필수)
python --version  # 3.10.x여야 함

# Python 버전이 다른 경우 pyenv 사용 권장
# pyenv install 3.10.12
# pyenv local 3.10.12

# 가상환경 생성 (Python 3.10 사용)
python -m venv venv

# 가상환경 활성화
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac/WSL

# Python 버전 재확인
python --version  # 3.10.x여야 함

# 의존성 설치
pip install -r requirements.txt
```

#### 환경 변수 설정
```bash
# .env 파일 생성
copy .env.example .env

# .env 파일 편집 (메모장으로 열기)
notepad .env
```

`.env` 파일 내용:
```
# Main Account (필수)
BINANCE_API_KEY=your_main_api_key_here
BINANCE_SECRET_KEY=your_main_secret_key_here

# Sub Account 1 (멀티 계좌 모드용, 선택)
SUB1_API_KEY=your_sub1_api_key_here
SUB1_API_SECRET=your_sub1_api_secret_here

# Sub Account 2 (선택)
SUB2_API_KEY=your_sub2_api_key_here
SUB2_API_SECRET=your_sub2_api_secret_here

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# System Configuration
LOG_LEVEL=INFO
```

#### 설정 파일 확인
```yaml
# config/config.yaml 확인 및 수정
# 주요 설정:

# 멀티 계좌 설정 (선택적)
multi_account:
  enabled: false  # true로 변경하여 멀티 계좌 활성화
  mode: "single"  # "single" 또는 "multi"
  sub_accounts:
    - account_id: "sub1"
      api_key: "${SUB1_API_KEY}"
      api_secret: "${SUB1_API_SECRET}"
      enabled: true
      strategy_preferences:
        - "TFPE"
      risk_limits:
        daily_loss_limit_pct: 3.0
        max_leverage: 5

strategies:
  tfpe:
    enabled: true
    leverage: 10
    position_size: 24  # 계좌의 24%
```

### 2. AWS EC2 설치 (Ubuntu)

#### SSH 접속
```bash
ssh -i "your-key.pem" ubuntu@your-server-ip
```

#### Python 환경 설정
```bash
# Python 3.12 설치
sudo apt update
sudo apt install python3.12 python3.12-venv python3-pip

# 프로젝트 디렉토리
cd /home/ubuntu/AlbraTrading

# 가상환경 생성
python3.12 -m venv venv

# 가상환경 활성화
source venv/bin/activate

# 의존성 설치
pip install --upgrade pip
pip install -r requirements.txt
```

#### Systemd 서비스 설정 (멀티모드 지원)
```bash
# 설치 스크립트 실행
cd /home/ubuntu/AlbraTrading/scripts
chmod +x setup_systemd_multi.sh

# 단일 계좌 모드 설치
./setup_systemd_multi.sh single

# 또는 멀티 계좌 모드 설치
./setup_systemd_multi.sh multi

# 현재 상태 확인
./setup_systemd_multi.sh status
```

## 📖 사용 방법

### 1. 운영 모드 선택

#### 단일 계좌 모드 (기본)
```bash
# 로컬 실행
python src/main_multi_account.py --mode single

# 또는 기존 방식
python src/main.py

# Systemd 서비스
sudo systemctl start albratrading-single
```

#### 멀티 계좌 모드
```bash
# 로컬 실행
python src/main_multi_account.py --mode multi

# 특정 계좌만 활성화
python src/main_multi_account.py --mode multi --account sub1

# Systemd 서비스
sudo systemctl start albratrading-multi
```

### 2. 멀티 계좌 CLI 관리 도구

```bash
# 전체 상태 확인
python scripts/multi_account_cli.py status

# 모든 계좌 잔고
python scripts/multi_account_cli.py balance

# 포지션 확인
python scripts/multi_account_cli.py positions

# 성과 분석
python scripts/multi_account_cli.py performance

# 리스크 체크
python scripts/multi_account_cli.py risk-check

# 전략 변경
python scripts/multi_account_cli.py switch-strategy sub1 TFPE

# 계좌 일시정지/재개
python scripts/multi_account_cli.py pause sub1
python scripts/multi_account_cli.py resume sub1

# 보고서 생성
python scripts/multi_account_cli.py report --type daily -o report.json
```

### 3. 텔레그램 명령어

#### 기본 명령어 (단일/멀티 모드 공통)
- `/status` - 시스템 상태 확인
- `/balance` - 계좌 잔고 확인
- `/positions` - 활성 포지션 목록
- `/help` - 도움말

#### 멀티 계좌 전용 명령어
- `/accounts` - 모든 계좌 상태
- `/balance all` - 전체 계좌 잔고
- `/positions sub1` - 특정 계좌 포지션
- `/pause sub1` - 특정 계좌 일시정지
- `/resume sub1` - 특정 계좌 재개

### 4. 웹 대시보드
```
http://your-server-ip:5000
```
- 실시간 포지션 모니터링
- 손익 현황
- 시스템 상태
- 멀티 계좌 통합 뷰 (멀티 모드)

## 🎯 멀티 계좌 시스템

### 멀티 계좌 아키텍처
```
┌─────────────────┐
│  Main Account   │ ← 메인 전략 운영 (독립적)
├─────────────────┤
│  Sub Account 1  │ ← 실험적 전략 (독립적)
├─────────────────┤
│  Sub Account 2  │ ← 보수적 전략 (독립적)
└─────────────────┘
         ↓
  통합 모니터링
 (권고사항만 제공)
```

**중요**: 각 계좌와 전략은 완전히 독립적으로 운영됩니다.
- 통합 리스크 매니저는 모니터링과 권고만 합니다
- 각 전략은 리스크 상태를 확인하고 자체적으로 결정합니다
- 강제 포지션 조작이나 청산은 없습니다

### 설정 예시

#### 시나리오 1: 전략 분리
```yaml
# 메인 계좌: 검증된 TFPE 전략
# 서브1: 새로운 전략 테스트
# 서브2: 보수적 운영

multi_account:
  sub_accounts:
    - account_id: "experimental"
      strategy_preferences: ["NEW_STRATEGY"]
      risk_limits:
        daily_loss_limit_pct: 2.0  # 더 엄격한 제한
        
    - account_id: "conservative"
      strategy_preferences: ["TFPE"]
      risk_limits:
        max_leverage: 3  # 낮은 레버리지
        position_size_pct: 10  # 작은 포지션
```

#### 시나리오 2: 리스크 분산
```yaml
# 각 계좌에 다른 리스크 프로파일 적용
# 전체 포트폴리오 리스크 분산
```

### 모드 전환 가이드

#### 단일 → 멀티 전환
```bash
# 1. 백업
cp config/config.yaml config/config_backup.yaml

# 2. 설정 수정
# config.yaml에서 multi_account.enabled: true

# 3. 서브 계좌 API 키 추가
# .env 파일에 SUB1_API_KEY 등 추가

# 4. 서비스 전환
cd /home/ubuntu/AlbraTrading/scripts
./setup_systemd_multi.sh switch
# → 멀티 모드 선택

# 5. 확인
python scripts/multi_account_cli.py status
```

#### 멀티 → 단일 전환
```bash
# 1. 모든 서브 계좌 포지션 정리
python scripts/multi_account_cli.py positions

# 2. 서비스 전환
./setup_systemd_multi.sh switch
# → 단일 모드 선택
```

## 🔍 운영 가이드

### 일일 점검 (5-10분)

#### 단일 모드
```bash
# 1. 시스템 상태
sudo systemctl status albratrading-single

# 2. 텔레그램 확인
/status
/positions

# 3. 웹 대시보드
http://your-server-ip:5000
```

#### 멀티 모드
```bash
# 1. 전체 상태
python scripts/multi_account_cli.py status

# 2. 리스크 체크
python scripts/multi_account_cli.py risk-check

# 3. 성과 확인
python scripts/multi_account_cli.py performance
```

### 주간 점검 (30분)
```bash
# 1. 로그 분석
grep ERROR logs/trading.log | tail -50

# 2. 성과 보고서
python scripts/multi_account_cli.py report --type weekly

# 3. 시스템 리소스
df -h
free -h

# 4. 로그 정리
find logs/ -name "*.log" -mtime +14 -delete
```

### 월간 점검
- 전략 성과 분석
- 계좌별 수익률 비교
- 리스크 파라미터 조정
- 시스템 업데이트

## 🚨 문제 해결

### 1. 서비스 실행 문제
```bash
# 로그 확인 (단일 모드)
sudo journalctl -u albratrading-single -n 100

# 로그 확인 (멀티 모드)
sudo journalctl -u albratrading-multi -n 100

# 환경변수 확인
cat .env | grep API_KEY
```

### 2. 멀티 계좌 연결 문제
```bash
# API 키 확인
python src/main_multi_account.py --validate

# 개별 계좌 테스트
python scripts/validate_multi_account.py
```

### 3. 포지션 불일치
```bash
# 단일 계좌
/sync

# 멀티 계좌 - 전체 동기화
python scripts/multi_account_cli.py sync-all

# 특정 계좌만
python scripts/multi_account_cli.py sync sub1
```

### 4. 긴급 상황

#### 단일 계좌
```bash
# 모든 포지션 청산
/close_all

# 시스템 중지
sudo systemctl stop albratrading-single
```

#### 멀티 계좌
```bash
# 특정 계좌 긴급 정지
python scripts/multi_account_cli.py emergency-stop sub1

# 전체 시스템 중지
python scripts/multi_account_cli.py emergency-stop all

# 서비스 중지
sudo systemctl stop albratrading-multi
```

## ⚠️ 주의사항

### 멀티 계좌 운영 시 주의
1. **API 한도**: 계좌가 많을수록 API 호출 증가
2. **리스크 관리**: 계좌별 독립적 리스크 설정 필수
3. **전략 충돌**: 같은 심볼에 다른 전략 적용 시 주의
4. **모니터링**: 계좌 수만큼 모니터링 부담 증가

### 보안 수칙
1. **API 키 분리**: 계좌별 다른 API 키 사용
2. **권한 최소화**: 필요한 권한만 부여
3. **정기 교체**: 3개월마다 API 키 교체
4. **접근 제한**: IP 화이트리스트 설정

### 백업 정책
```bash
# 일일 백업 (자동)
- state/ 디렉토리
- position_cache.json
- 데이터베이스

# 주간 백업 (수동)
- config/
- logs/
- 전체 시스템 스냅샷
```

## 📊 성과 모니터링

### 주요 지표
- **계좌별 수익률**: 일간/주간/월간
- **샤프 비율**: 위험 조정 수익률
- **최대 낙폭(MDD)**: 계좌별 및 전체
- **승률**: 전략별 성과
- **API 사용률**: 한도 대비 사용량

### 리포트 자동화
```bash
# Cron 설정 (일일 리포트)
0 9 * * * /home/ubuntu/AlbraTrading/venv/bin/python /home/ubuntu/AlbraTrading/scripts/multi_account_cli.py report --type daily

# 주간 리포트 (월요일 오전)
0 9 * * 1 /home/ubuntu/AlbraTrading/venv/bin/python /home/ubuntu/AlbraTrading/scripts/multi_account_cli.py report --type weekly
```

## 📞 지원

### 로그 위치
- **시스템 로그**: 
  - 단일: `/home/ubuntu/AlbraTrading/logs/systemd_single.log`
  - 멀티: `/home/ubuntu/AlbraTrading/logs/systemd_multi.log`
- **애플리케이션 로그**: `/home/ubuntu/AlbraTrading/logs/trading.log`
- **에러 로그**: `/home/ubuntu/AlbraTrading/logs/trading_error.log`

### 유용한 명령어 모음
```bash
# 서비스 상태 (현재 모드 확인)
./scripts/setup_systemd_multi.sh status

# 모드 전환
./scripts/setup_systemd_multi.sh switch

# 실시간 로그 (단일)
sudo journalctl -u albratrading-single -f

# 실시간 로그 (멀티)
sudo journalctl -u albratrading-multi -f

# 프로세스 확인
ps aux | grep main_multi_account

# 포트 확인
sudo netstat -tlnp | grep 5000
```

## 🎉 마무리

AlbraTrading v2.0은 개인 트레이더를 위한 확장 가능한 시스템입니다.
- **단일 모드**: 간단하고 안정적인 운영
- **멀티 모드**: 전략 분리 및 리스크 분산
- **점진적 확장**: 필요에 따라 계좌 추가

**중요**: 
- 작동하는 코드를 함부로 수정하지 마세요
- 멀티 모드는 충분한 테스트 후 사용하세요
- 문제 발생 시 로그를 먼저 확인하세요

**Happy Trading! 🚀**

---

## 📚 추가 문서
- [ALBRA_TRADING_SYSTEM.md](./ALBRA_TRADING_SYSTEM.md) - 상세 시스템 아키텍처
- [PROJECT_GUIDELINES.md](./PROJECT_GUIDELINES.md) - 프로젝트 개발 지침
- [MULTI_STRATEGY_QUICK_REF.md](./MULTI_STRATEGY_QUICK_REF.md) - 멀티 전략 빠른 참조
- [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) - 배포 가이드
- [template_strategy.py](./src/strategies/template_strategy.py) - 전략 템플릿
- [docs/](./docs/) - 개발 문서

최종 업데이트: 2025년 1월
