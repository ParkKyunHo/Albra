# 🏛️ AlbraTrading System - Complete Architecture Documentation

## 📋 목차
1. [시스템 개요](#시스템-개요)
2. [아키텍처](#아키텍처)
3. [핵심 컴포넌트](#핵심-컴포넌트)
4. [전략 시스템](#전략-시스템)
5. [포지션 관리](#포지션-관리)
6. [리스크 관리](#리스크-관리)
7. [실시간 모니터링](#실시간-모니터링)
8. [알림 시스템](#알림-시스템)
9. [데이터 흐름](#데이터-흐름)
10. [운영 가이드](#운영-가이드)
11. [멀티 계좌 아키텍처](#멀티-계좌-아키텍처)
12. [데이터베이스 시스템](#데이터베이스-시스템)
13. [백테스트 시스템](#백테스트-시스템)
14. [인프라 및 배포](#인프라-및-배포)
15. [향후 로드맵](#향후-로드맵)

---

## 🎯 시스템 개요

### 프로젝트 정보
- **시스템명**: AlbraTrading System
- **버전**: 2.0 (Production)
- **목적**: Goldman Sachs & Jane Street 수준의 완전 자동화 트레이딩 시스템
- **운영 방식**: 1인 운영 시스템 (과도한 확장성보다 안정성 우선)
- **거래소**: Binance Futures (USDT-M)
- **기본 디렉토리**: `C:\AlbraTrading`

### 핵심 특징
1. **Multi-Strategy Support**: TFPE, ZLHMA EMA Cross, ZL MACD+Ichimoku 등 다양한 전략 동시 운영
2. **Multi-Account Architecture**: 메인/서브 계좌 분리 운영으로 전략별 독립 관리
3. **Hybrid Trading**: 자동/수동 거래 통합 관리
4. **Risk Management**: 다단계 MDD 관리, Kelly Criterion, 동적 포지션 사이징
5. **Real-time Monitoring**: WebSocket 기반 실시간 가격 모니터링 (선택적)
6. **Smart Notification**: 우선순위 기반 스마트 알림 시스템
7. **Event-Driven Architecture**: Phase 2 이벤트 기반 아키텍처 (선택적)
8. **Data Management**: Supabase + Redis + TimescaleDB 통합 데이터 관리

---

## 🏗️ 아키텍처

### 시스템 구조도
```
┌─────────────────────────────────────────────────────────────┐
│                     Main Entry Point                        │
│                     (src/main.py)                           │
└─────────────────┬───────────────────────────────────────────┘
                  │
     ┌────────────┴────────────┬────────────┬────────────────┐
     │                         │            │                │
┌────▼─────┐         ┌────────▼────────┐  ┌────▼─────┐  ┌──────▼──────┐
│ Exchange │         │   Multi-Strategy │  │ Position │  │ Notification│
│   APIs   │         │ • TFPE          │  │ Manager  │  │   Manager   │
│ • Main   │         │ • ZLHMA EMA     │  │          │  │             │
│ • Sub1   │         │ • ZL MACD       │  │          │  │             │
│ • Sub2   │         └─────────────────┘  └──────────┘  └─────────────┘
└──────────┘                │                   │               │
     │                      │                   │               │
     └──────────────────────┴───────────────────┴───────────────┘
                            │
                    ┌───────▼────────┐
                    │   Event Bus    │
                    └───────┬────────┘
                            │
         ┌──────────────────┴─────────────────┐
         │                                    │
    ┌────▼────┐                         ┌─────▼─────┐
    │ Database│                         │ Monitoring│
    │ • Supabase                        │ • Grafana │
    │ • Redis │                         │ • Metrics │
    └─────────┘                         └───────────┘
```

### 디렉토리 구조
```
AlbraTrading/
├── src/
│   ├── core/                     # 핵심 비즈니스 로직
│   │   ├── binance_api.py       # 거래소 API 래퍼
│   │   ├── position_manager.py   # 포지션 통합 관리
│   │   ├── event_bus.py         # 이벤트 시스템
│   │   ├── state_manager.py     # 상태 관리
│   │   └── mdd_manager_improved.py # MDD 관리
│   │
│   ├── strategies/              # 트레이딩 전략
│   │   ├── base_strategy.py    # 전략 기본 클래스
│   │   ├── tfpe_strategy.py    # TFPE Donchian 전략
│   │   ├── strategy_factory.py # 전략 팩토리
│   │   └── realtime/           # 실시간 전략 (개발 중)
│   │
│   ├── monitoring/              # 모니터링
│   │   ├── health_checker.py   # 시스템 헬스 체크
│   │   └── position_sync_monitor.py # 포지션 동기화
│   │
│   ├── utils/                   # 유틸리티
│   │   ├── config_manager.py   # 설정 관리
│   │   ├── logger.py           # 로깅 시스템
│   │   └── smart_notification_manager.py # 알림 관리
│   │
│   ├── analysis/               # 분석 도구
│   │   └── backtest_analyzer.py # 백테스트 결과 분석
│   │
│   └── main.py                 # 메인 진입점
│
├── backtest_modules/           # 백테스트 모듈
│   ├── backtest_engine_mmap.py # 메모리 맵 백테스트 엔진
│   ├── config.py               # 백테스트 설정
│   └── utils.py                # 백테스트 유틸리티
│
├── infrastructure/             # 인프라 설정
│   ├── aws/                   # AWS 인프라
│   │   ├── ec2_setup.sh      # EC2 설정 스크립트
│   │   └── user_data.sh      # EC2 사용자 데이터
│   └── docker/                # Docker 설정
│       ├── Dockerfile         # Docker 이미지
│       └── docker-compose.yml # Docker Compose
│
├── config/
│   ├── config.yaml            # 시스템 설정
│   └── backtest_config.yaml   # 백테스트 설정
│
├── data/                      # 데이터 저장소
│   ├── klines/               # 캔들 데이터
│   └── binance_ticker_data.parquet # 티커 데이터
│
├── logs/                      # 로그 파일
├── state/                     # 상태 파일
├── cache_data/                # 캐시 데이터
├── wf_cache_15m/             # Walk-forward 캐시 (15분)
├── wf_cache_5m/              # Walk-forward 캐시 (5분)
├── results/                   # 백테스트 결과
└── tests/                     # 테스트 코드
```

---

## 💎 핵심 컴포넌트

### 1. TradingSystem (`src/main.py`)
메인 시스템 클래스로 모든 컴포넌트를 초기화하고 조정합니다.

**주요 기능:**
- 시스템 초기화 및 종료
- 전략 실행 루프 관리
- 포지션 모니터링
- 웹 대시보드 실행
- 시그널 핸들링

**초기화 순서:**
1. API 키 확인 및 Exchange API 초기화
2. State Manager 초기화
3. Notification Manager 초기화
4. Position Manager 초기화 (알림 매니저 주입)
5. 안전 체크 실행
6. 전략 초기화
7. 보조 컴포넌트 초기화

### 2. BinanceAPI (`src/core/binance_api.py`)
거래소 API 래퍼 클래스입니다.

**주요 기능:**
- 주문 실행 (시장가/지정가)
- 포지션 조회
- 잔고 조회
- 가격 정보 조회
- 레버리지 설정
- WebSocket 스트림 관리

### 3. PositionManager (`src/core/position_manager.py`)
모든 포지션을 중앙에서 관리하는 핵심 컴포넌트입니다.

**주요 기능:**
- 자동/수동 포지션 통합 관리
- 거래소와 시스템 포지션 동기화
- 포지션 상태 추적
- 부분 청산 감지 및 기록
- 동적 포지션 사이징 (Kelly Criterion)
- 이벤트 기반 알림

**포지션 데이터 구조:**
```python
@dataclass
class Position:
    symbol: str              # 거래 심볼
    side: str               # LONG/SHORT
    size: float             # 포지션 크기
    entry_price: float      # 진입가
    leverage: int           # 레버리지
    position_id: str        # 고유 ID
    is_manual: bool         # 수동 거래 여부
    strategy_name: str      # 전략 이름
    status: str             # ACTIVE/CLOSED/MODIFIED
    stop_loss: float        # 손절가
    take_profit: float      # 익절가
```

### 4. SmartNotificationManager (`src/utils/smart_notification_manager.py`)
우선순위 기반 스마트 알림 시스템입니다.

**주요 기능:**
- 이벤트 우선순위 관리 (CRITICAL/HIGH/MEDIUM/LOW)
- 중복 알림 방지 (Event ID 기반)
- Rate Limiting
- 재시도 메커니즘 (Exponential Backoff)
- 알림 요약 및 집계

---

## 📈 전략 시스템

### TFPE (Trend Following Pullback Entry) Strategy
**파일**: `src/strategies/tfpe_strategy.py`

**전략 개요:**
- Donchian Channel 기반 추세 추종 전략
- ZL MACD와 Ichimoku를 대체하는 메인 전략
- 캔들 종가 기준 시그널 체크 (15분봉)

**핵심 파라미터:**
```yaml
leverage: 10              # 레버리지
position_size: 24         # 기본 포지션 크기 (%)
signal_threshold: 4       # 신호 임계값 (4/5)
stop_loss_atr: 1.5       # ATR x 1.5
take_profit_atr: 5.0     # ATR x 5.0
adx_min: 25              # 최소 ADX
dc_period: 20            # Donchian 기간
```

**진입 조건 (4개 이상 충족):**
1. **모멘텀**: 2% 이상
2. **피보나치 되돌림**: 38.2% ~ 78.6%
3. **RSI 조건**: 
   - 상승 추세: RSI ≤ 40 (채널 하단) 또는 ≤ 45 (중립)
   - 하락 추세: RSI ≥ 60 (채널 상단) 또는 ≥ 55 (중립)
4. **EMA 거리**: 1.5% 이내
5. **거래량**: 1.5배 이상
6. **가격 위치**: 채널 극단값
7. **횡보장 특별 조건**: RSI < 30 또는 > 70

**청산 조건:**
- ATR 기반 동적 손절/익절
- 시간 기반 청산 (선택적)
- Donchian 중간선 돌파 (선택적)

**실행 주기:**
- 캔들 종가 체크: 15분마다 (00, 15, 30, 45분)
- 캔들 준비: 14분 50초부터 데이터 미리 로드
- 포지션 동기화: 60초마다

### ZL MACD + Ichimoku Strategy ⭐ NEW
**파일**: `src/strategies/zlmacd_ichimoku_strategy.py`

**전략 개요:**
- Zero Lag MACD와 Ichimoku Cloud를 결합한 고급 전략
- 비트코인 1시간봉에 특화된 전략
- 다층적 확인으로 높은 승률 추구
- 백테스트 검증된 파라미터 사용

**핵심 특징:**
```yaml
leverage: 10              # 안전한 레버리지
position_size: 20         # 기본 포지션 크기 (%)
min_signal_strength: 3    # 최소 3개 신호 필요
adx_threshold: 25         # ADX > 25 (강한 추세)
timeframe: "1h"          # 1시간봉 전용
symbols: ["BTCUSDT"]     # 비트코인 전용
```

**진입 조건 (3개 이상 충족):**
1. **ZL MACD 크로스**: 골든크로스(롱) / 데드크로스(숏)
2. **가격-구름 관계**: 구름 위(롱) / 구름 아래(숏)
3. **Tenkan/Kijun 관계**: 전환선 > 기준선(롱) / 전환선 < 기준선(숏)
4. **구름 색상**: 녹색 구름(롱) / 빨간색 구름(숏)
5. **ADX 필터**: ADX > 25 (추세 강도 확인)

**청산 조건:**
1. **기준선 터치**: 가격이 Kijun-sen에 닿을 때
2. **구름 돌파**: 반대 방향으로 구름 돌파
3. **ZL MACD 반전**: 반대 신호 발생
4. **트레일링 스톱**: 3% 수익 후 활성화, 최고점에서 10% 하락
5. **최대 손실**: -2% (긴급 손절)

**리스크 관리 특징:**
- **Kelly Criterion**: 최근 100개 거래 기반 동적 사이징
- **3단계 부분 익절**: 5%(25%), 10%(35%), 15%(40%)
- **피라미딩**: 3%, 6%, 9% 수익 시 추가 진입
- **일일 손실 한도**: 3% 초과 시 24시간 거래 중단
- **연속 손실 조정**: 3/5/7회 연속 손실 시 포지션 축소

**백테스트 성과:**
- 평균 승률: 55~60%
- 평균 손익비: 1:3 이상
- 최대 드로우다운: 15~20%
- 연간 수익률: 80~120% (레버리지 포함)

**실행 주기:**
- 시그널 체크: 1시간봉 종가 기준 (정시 30초 후)
- 최소 신호 간격: 4시간 (과도한 거래 방지)
- 동시 포지션: 최대 2개 (리스크 분산)

### 동적 포지션 사이징

**Kelly Criterion 적용:**
```python
kelly_fraction = (win_rate * profit_loss_ratio - loss_rate) / profit_loss_ratio
position_size = base_size * kelly_fraction * 0.5  # Half Kelly
```

**조정 요소:**
1. Kelly Criterion (0.5x ~ 1.5x)
2. 시장 레짐 (0.6x ~ 1.2x)
3. MDD 상태 (0.1x ~ 1.0x)
4. 변동성 조정 (목표 15% 연간 변동성)

---

## 📊 포지션 관리

### 포지션 생명주기
```
생성 → 활성 → 수정(선택) → 청산
  ↓      ↓       ↓            ↓
알림   모니터링  알림         알림
```

### 포지션 동기화
**주기**: 60초 (config.yaml에서 설정)

**동기화 프로세스:**
1. 거래소 포지션 조회
2. 새 포지션 감지 (수동/자동 구분)
3. 기존 포지션 변경 체크
4. 청산된 포지션 처리
5. 상태 저장 및 알림

### 수동/자동 거래 통합
- **수동 포지션**: `is_manual=True`, 자동 전략이 간섭하지 않음
- **자동 포지션**: `is_manual=False`, 전략이 관리
- **충돌 방지**: 심볼별로 하나의 포지션만 허용

### 🔄 Multi-Strategy Position Management (멀티 전략 포지션 관리)
시스템은 여러 전략이 동일한 심볼을 독립적으로 거래할 수 있도록 설계되었습니다.

**복합 키 구조:**
```python
# 포지션은 {symbol}_{strategy_name} 형식의 키로 저장
# 예: "BTCUSDT_TFPE", "BTCUSDT_ZLMACD"
position_key = f"{symbol}_{strategy_name}"
```

**전략별 포지션 인덱스:**
```python
# 빠른 전략별 조회를 위한 인덱스
strategy_positions = {
    "TFPE": ["BTCUSDT_TFPE", "ETHUSDT_TFPE"],
    "ZLMACD": ["BTCUSDT_ZLMACD"]
}
```

**메서드 시그니처:**
```python
# 모든 포지션 관련 메서드는 strategy_name 파라미터 포함
get_position(symbol: str, strategy_name: str = None) -> Optional[Position]
is_position_exist(symbol: str, strategy_name: str = None) -> bool
remove_position(symbol: str, reason: str, exit_price: float, strategy_name: str = None)
get_active_positions(include_manual: bool = True, strategy_name: str = None) -> List[Position]
```

**전략별 포지션 관리:**
- 각 전략은 독립적으로 포지션 생성/관리
- 동일 심볼에 대해 여러 전략이 각각의 포지션 보유 가능
- 수동 포지션은 `{symbol}_MANUAL` 키로 구분

**하위 호환성:**
- 전략명 없이 호출 시 경고 로그 출력
- 기존 데이터는 자동으로 새 구조로 마이그레이션
- 첫 번째 활성 포지션 반환으로 기존 로직 유지

**신규 유틸리티 메서드:**
```python
get_active_strategies() -> List[str]  # 활성 전략 목록
get_positions_by_strategy(strategy_name: str) -> List[Position]  # 전략별 포지션
get_position_summary() -> Dict[str, Any]  # 전략별 통계 포함 요약
```

---

## 🛡️ 리스크 관리

### 1. MDD (Maximum Drawdown) 관리
**파일**: `src/core/mdd_manager_improved.py`

**다단계 MDD 관리:**
```
Level 0: MDD < 30% → 정상 거래 (100%)
Level 1: MDD 30-35% → 포지션 70%로 축소
Level 2: MDD 35-40% → 포지션 50%로 축소
Level 3: MDD 40-50% → 포지션 30%로 축소
Level 4: MDD > 50% → 긴급 모드 (10%)
```

**회복 메커니즘:**
- 연속 3승 시 포지션 크기 10%씩 증가
- 최대 100%까지 회복

### 2. 일일 리스크 관리
- **일일 최대 손실**: 5%
- **거래당 최대 리스크**: 1.5%
- **손실 한도 도달 시**: 24시간 거래 중단

### 3. 포지션 제한
- **최대 동시 포지션**: 3개
- **단일 포지션 최대 크기**: 50%
- **전체 자금 최대 사용률**: 90%

---

## 🔄 실시간 모니터링

### 캔들 종가 모드 (기본)
**현재 사용 중인 모드**
- 15분 캔들 종가에서만 체크
- 서버 시간 기준 동기화
- 14분 50초부터 데이터 준비

### 실시간 모드 (개발 중)
- WebSocket 기반 실시간 가격 모니터링
- 즉각적인 신호 감지
- 빠른 시장 변화 대응

---

## 📢 알림 시스템

### 이벤트 타입 및 우선순위
```
CRITICAL: 시스템 오류, 긴급 상황
HIGH: 포지션 청산, 큰 손실
MEDIUM: 포지션 진입, 일반 변경
LOW: 상태 리포트, 정보성 메시지
```

### 주요 알림
1. **포지션 진입/청산**: 자동/수동 모두 알림
2. **수동 포지션 감지**: 새로운 수동 거래 발견
3. **포지션 변경**: 크기 변경, 부분 청산
4. **시스템 상태**: 30분마다 자동 리포트
5. **리스크 경고**: MDD 레벨 변경, 일일 손실 한도

### 텔레그램 명령어
```
/status - 현재 상태 확인
/positions - 포지션 목록
/balance - 잔고 확인
/stop - 봇 일시정지
/resume - 봇 재개
/help - 명령어 도움말
```

---

## 🔀 데이터 흐름

### 1. 신호 생성 흐름
```
Market Data → Strategy Analysis → Signal Generation → Position Manager → Order Execution
     ↓              ↓                    ↓                   ↓                ↓
  WebSocket    Indicators          Entry Conditions    Risk Check        Binance API
```

### 2. 포지션 동기화 흐름
```
Binance Positions → Position Manager → State Manager → Cache
        ↓                  ↓                ↓            ↓
   API Query          Comparison      Save State    Local Storage
```

### 3. 알림 흐름
```
Event → Smart Notification Manager → Priority Check → Rate Limit → Telegram
  ↓              ↓                        ↓               ↓           ↓
Position    Deduplication            Queue Management  Throttle    Send Alert
```

---

## 🚀 운영 가이드

### 시스템 시작
```bash
# 기본 실행 (모든 활성 전략)
python src/main.py

# 특정 전략만 실행
python src/main.py --strategies TFPE

# 전략 목록 확인
python src/main.py --list-strategies
```

### 일일 운영 체크리스트
- [ ] 시스템 상태 리포트 확인 (30분마다 자동)
- [ ] 포지션 동기화 상태 확인
- [ ] MDD 레벨 확인
- [ ] 에러 로그 확인
- [ ] API 연결 상태 확인

### 문제 해결
1. **포지션 불일치**: 수동으로 `/sync` 명령 실행
2. **알림 미수신**: 텔레그램 봇 상태 확인
3. **거래 미실행**: 
   - MDD 제한 확인
   - 일일 손실 한도 확인
   - API 키 권한 확인

### 성능 최적화
- **동기화 주기**: 포지션 있을 때 60초, 없을 때 300초
- **캐시 활용**: 15분봉 데이터는 1분간 캐시
- **배치 처리**: 여러 심볼 동시 처리

### 백업 및 복구
- **상태 파일**: `state/` 디렉토리 백업
- **포지션 캐시**: `position_cache.json`
- **시스템 포지션 ID**: `system_positions.json`

---

## 📌 중요 설정 파일

### config.yaml 주요 섹션
```yaml
# 시스템 설정
system:
  mode: "live"          # 실전 모드

# 트레이딩 설정  
trading:
  max_positions: 3      # 최대 포지션 수
  
# 전략 설정
strategies:
  tfpe:
    enabled: true       # TFPE 활성화
    leverage: 10        # 레버리지
    
# MDD 보호
mdd_protection:
  enabled: true         # MDD 관리 활성화
  max_allowed_mdd: 40.0 # 최대 MDD
```

---

## 📊 백테스트 시스템

### 백테스트 아키텍처
프로덕션 전략 검증을 위한 고성능 백테스트 시스템입니다.

**주요 구성 요소:**
- **백테스트 엔진**: Memory-mapped 파일 기반 고속 처리
- **데이터 관리**: Parquet 형식 캔들 데이터
- **Walk-Forward 분석**: 15분/5분 캐시 시스템
- **결과 분석**: 성과 지표 및 시각화

### 백테스트 모듈 구조
```
backtest_modules/
├── backtest_engine_mmap.py  # 메모리 맵 백테스트 엔진
├── config.py                # 백테스트 설정
└── utils.py                 # 유틸리티 함수
```

### 백테스트 프로세스
1. **데이터 준비**
   - Binance 히스토리컬 데이터 다운로드
   - Parquet 형식으로 변환 및 저장
   - 메모리 맵 파일 생성

2. **전략 백테스트**
   - 전략 파라미터 설정
   - 신호 생성 및 거래 시뮬레이션
   - 수수료 및 슬리피지 반영

3. **성과 분석**
   - 수익률, 샤프 비율, MDD
   - 승률 및 손익비
   - 거래 분포 분석

4. **Walk-Forward 최적화**
   - In-sample/Out-of-sample 분석
   - 파라미터 강건성 테스트
   - 오버피팅 방지

### 백테스트 설정 (backtest_config.yaml)
```yaml
data:
  symbols: ["BTCUSDT", "ETHUSDT"]
  timeframe: "15m"
  start_date: "2023-01-01"
  end_date: "2024-12-31"

engine:
  initial_capital: 10000
  commission: 0.0004  # 0.04%
  slippage: 0.0001    # 0.01%

optimization:
  method: "walk_forward"
  in_sample_ratio: 0.7
  step_size: 30  # days
```

---

## 🐳 인프라 및 배포

### Docker 환경
프로덕션 환경을 위한 Docker 설정이 포함되어 있습니다.

**Dockerfile 주요 구성:**
- Python 3.12 기반 이미지
- 필수 패키지 및 의존성 설치
- 타임존 설정 (Asia/Seoul)
- 비루트 사용자 실행

**Docker Compose:**
- 서비스 자동 재시작
- 볼륨 마운트 (config, logs, state, data)
- 환경 변수 관리

### AWS EC2 배포
**EC2 설정 스크립트:**
- Amazon Linux 2023 기반
- 자동 업데이트 및 패키지 설치
- Docker 및 Docker Compose 설치
- 스왑 메모리 설정 (4GB)
- 보안 그룹 설정

**User Data 스크립트:**
- Git 저장소 클론
- 환경 설정
- 서비스 자동 시작

---

## 🔧 확장 및 커스터마이징

### 새 전략 추가
1. `BaseStrategy` 클래스 상속
2. `check_entry_signal()` 구현
3. `check_exit_signal()` 구현
4. `strategy_factory.py`에 등록
5. `config.yaml`에 설정 추가

### 새 지표 추가
1. `calculate_indicators()`에 지표 계산 추가
2. 진입/청산 조건에 통합
3. 백테스트로 검증

### 알림 커스터마이징
1. 새 이벤트 타입 정의
2. 우선순위 설정
3. 메시지 템플릿 작성

---

## 📞 지원 및 문의

### 로그 위치
- **시스템 로그**: `logs/trading.log`
- **에러 로그**: `logs/error.log`
- **거래 로그**: `data/trades.db`

### 디버깅 팁
1. 로그 레벨을 DEBUG로 변경
2. `--validate` 옵션으로 전략 검증
3. 테스트넷에서 먼저 테스트

---

## 📚 관련 문서

### 핵심 가이드
- **[PROJECT_GUIDELINES.md](./PROJECT_GUIDELINES.md)** - 새로운 전략 추가 시 반드시 참고해야 할 개발 지침
- **[MULTI_STRATEGY_QUICK_REF.md](./MULTI_STRATEGY_QUICK_REF.md)** - Multi-Strategy Position Management 빠른 참조 카드
- **[template_strategy.py](./src/strategies/template_strategy.py)** - 전략 개발을 위한 템플릿 코드

### 운영 및 배포
- **[README.md](./README.md)** - 시스템 설치 및 사용 가이드
- **[DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md)** - AWS EC2 배포 상세 가이드
- **[DEPLOYMENT_CHECKLIST.md](./DEPLOYMENT_CHECKLIST.md)** - 배포 전 체크리스트

### 기타 문서
- **[docs/](./docs/)** - 추가 개발 문서 및 가이드
- **[Phase 2 문서](./docs/PHASE2_*.md)** - 멀티 계좌 시스템 관련 문서

---

이 문서는 AlbraTrading System의 전체 구조와 운영 방법을 설명합니다. 
시스템은 안정성과 신뢰성을 최우선으로 설계되었으며, 1인 운영에 최적화되어 있습니다.

**💡 Tip**: 새로운 전략을 추가할 때는 반드시 [PROJECT_GUIDELINES.md](./PROJECT_GUIDELINES.md)를 참고하여 Multi-Strategy Position Management 시스템을 올바르게 활용하세요.




📋 AlbraTrading Phase 2 멀티 계좌 시스템 구현 진행 상황 문서
🎯 프로젝트 개요

프로젝트명: AlbraTrading 멀티 계좌 시스템
작업 일자: 2025년 6월 29일
담당자 역할: 15년 경력 바이낸스/나스닥 선물 전문 트레이더 (Goldman Sachs & Jane Street 경험)
목표: 단일 계좌 시스템을 멀티 계좌 시스템으로 확장 (무중단 전환)

✅ 완료된 작업 (Phase 2)
1. Phase 1 검토 [100% 완료]

✓ 백업 파일 검증 완료
✓ 멀티 계좌 핵심 모듈 검증 완료
✓ 설정 및 환경 검증 완료
✓ 테스트 인프라 확인 완료

2. Step 1: main_multi_account.py 구현 [100% 완료]

파일: C:\AlbraTrading\src\main_multi_account.py
크기: 45,919 bytes (약 1,100 라인)
주요 기능:

단일/멀티 모드 자유 전환
명령행 인터페이스 (--mode, --account, --dry-run, --validate, --status)
통합 포지션 관리 (UnifiedPositionManager)
엔터프라이즈급 에러 처리 및 복구
Graceful shutdown
시스템 메트릭 추적



3. Step 2: strategy_allocator.py 구현 [100% 완료]

파일: C:\AlbraTrading\src\core\multi_account\strategy_allocator.py
크기: 36,478 bytes (약 900 라인)
주요 클래스:

StrategyAllocator: 전략-계좌 할당 관리
StrategyCompatibilityChecker: 전략 호환성 검사
AllocationOptimizer: 포트폴리오 최적화


핵심 기능:

계좌별 독립적 전략 운영
심볼 충돌 방지
동적 전략 재할당
성과 추적 및 최적화



🔄 현재 상태

진행률: Phase 2의 33% 완료 (Step 2/6 완료)
시스템 상태: 안정적 (기존 시스템 영향 없음)
차단 이슈: 서브 계좌 전략 미결정

📝 남은 작업 목록
Step 3: 통합 모니터링 시스템 [대기]

unified_monitor.py 구현
계좌별 실시간 손익 추적
전체 포트폴리오 리스크 지표
성과 비교 분석

Step 4: 안전 관리 시스템 [대기]

risk_manager.py 구현
계좌별 일일 손실 한도
전체 포트폴리오 손실 한도
자동 복구 시스템

Step 5: 유틸리티 도구 [대기]

multi_account_cli.py 구현
balance, positions, performance 명령
switch-strategy, emergency-stop 명령

Step 6: 통합 테스트 [대기]

단일→멀티 모드 전환 테스트
계좌 간 격리 테스트
24시간 연속 운영 테스트

sudo systemctl stop albratrading
./scripts/setup_systemd_multi.sh multi

http://43.201.76.89:5000/
