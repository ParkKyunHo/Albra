# AlbraTrading 시스템 전체 구조

## 🏗️ 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                     AlbraTrading System                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │   Binance   │  │   Telegram   │  │  Web Dashboard  │  │
│  │     API     │  │     Bot      │  │   (Flask)       │  │
│  └──────┬──────┘  └──────┬───────┘  └────────┬────────┘  │
│         │                 │                    │           │
│  ┌──────┴─────────────────┴────────────────────┴────────┐ │
│  │                    Event Bus System                   │ │
│  └──────┬─────────────────┬────────────────────┬────────┘ │
│         │                 │                    │           │
│  ┌──────┴──────┐  ┌──────┴──────┐  ┌─────────┴────────┐ │
│  │  Position    │  │  Strategy   │  │   Monitoring     │ │
│  │  Manager     │  │   Engine    │  │    System        │ │
│  └─────────────┘  └─────────────┘  └──────────────────┘ │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │              State Management & Database             │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## 📁 핵심 모듈 구조

### 1. **Core 모듈** (`src/core/`)
핵심 비즈니스 로직을 담당하는 모듈들

#### 주요 컴포넌트:
- **binance_api.py**: Binance 거래소 API 클라이언트
  - REST API 및 WebSocket 연결 관리
  - 자동 재연결 및 에러 처리
  
- **position_manager.py**: 포지션 통합 관리
  - 멀티 전략 포지션 지원 (`symbol_strategy` 키)
  - 자동/수동 포지션 통합
  - 실시간 동기화
  
- **event_bus.py**: 이벤트 기반 통신 시스템
  - 컴포넌트 간 느슨한 결합
  - 비동기 이벤트 처리
  
- **mdd_manager_improved.py**: MDD(Maximum Drawdown) 관리
  - 다단계 리스크 관리
  - 실시간 손실 추적

### 2. **Strategies 모듈** (`src/strategies/`)
트레이딩 전략 구현

#### 현재 전략:
- **TFPE (Trend Following with Price Extremes)**:
  - 20기간 Donchian Channel
  - 다중 신호 확인 (4/7 이상)
  - ATR 기반 동적 손절/익절
  - Kelly Criterion 포지션 사이징

### 3. **Monitoring 모듈** (`src/monitoring/`)
시스템 상태 감시

- **health_checker.py**: 시스템 헬스 체크
- **position_sync_monitor.py**: 포지션 동기화 모니터

### 4. **Utils 모듈** (`src/utils/`)
유틸리티 및 헬퍼 함수

- **telegram_notifier.py**: 텔레그램 알림
- **config_manager.py**: 설정 관리
- **logger.py**: 로깅 시스템

## 🔄 데이터 흐름

### 1. **신호 생성 흐름**
```
Market Data → Price Monitor → Strategy Engine → Signal Generation
                                                        ↓
                                              Signal Validation
                                                        ↓
                                              Position Manager
```

### 2. **주문 실행 흐름**
```
Valid Signal → Risk Check → Order Creation → Binance API
                                                   ↓
                                            Order Execution
                                                   ↓
                                         Position Update & Event
```

### 3. **모니터링 흐름**
```
All Components → Event Bus → Event Logger → State Manager
                    ↓              ↓              ↓
              Telegram Bot    Database      Log Files
```

## 📊 주요 설정 (`config/config.yaml`)

### 시스템 설정
- **거래 심볼**: BTCUSDT, ETHUSDT, BNBUSDT
- **레버리지**: 10x (기본)
- **포지션 크기**: 계좌의 24%
- **최대 동시 포지션**: 3개

### 리스크 관리
- **일일 최대 손실**: 5%
- **MDD 한도**: 40%
- **포지션당 최대 손실**: 2%

### 운영 설정
- **동기화 간격**: 60초
- **헬스체크 간격**: 300초
- **로그 레벨**: INFO

## 🚀 시작 및 종료 프로세스

### 시작 순서
1. 설정 파일 로드
2. 데이터베이스 초기화
3. API 연결 확인
4. 기존 포지션 동기화
5. 전략 엔진 시작
6. 모니터링 시작
7. 웹 대시보드 시작

### 종료 순서 (Graceful Shutdown)
1. 새 포지션 진입 중지
2. 대기 주문 취소
3. 진행 중 작업 완료 대기
4. 상태 저장
5. 연결 종료

## 📈 성능 메트릭

### 시스템 성능
- **평균 응답 시간**: < 100ms
- **메모리 사용량**: < 500MB
- **CPU 사용률**: < 20%

### 트레이딩 성능
- **평균 승률**: ~45%
- **리스크/리워드**: 1:2
- **연간 수익률**: 측정 중

## 🔧 확장 포인트

### 새 전략 추가
1. `BaseStrategy` 클래스 상속
2. `strategy_factory.py`에 등록
3. `config.yaml`에 설정 추가

### 새 거래소 추가
1. API 클라이언트 구현
2. 포지션 매핑 로직 추가
3. 설정 파일 업데이트

---

*최종 업데이트: 2025-01-30*