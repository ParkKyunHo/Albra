# 멀티 계좌 설정 가이드

## 🎯 계좌별 전략 할당 방법

### 1. 서브 계좌 추가 예시

```yaml
multi_account:
  enabled: true
  
  sub_accounts:
    # 첫 번째 서브 계좌 (이미 설정됨)
    test_account_1:
      type: "SUB_FUTURES"
      enabled: true
      strategy: "ZLHMA_EMA_CROSS"  # 이 계좌에서 실행할 전략
      leverage: 5
      position_size: 10.0
      max_positions: 1
      daily_loss_limit: 2.0
      max_drawdown: 10.0
      symbols:
        - BTCUSDT
    
    # 두 번째 서브 계좌 추가 예시
    test_account_2:
      type: "SUB_FUTURES"
      enabled: true
      strategy: "MOMENTUM"         # 다른 전략 실행
      leverage: 8
      position_size: 15.0
      max_positions: 2
      daily_loss_limit: 3.0
      max_drawdown: 15.0
      symbols:
        - ETHUSDT
        - BNBUSDT
    
    # 세 번째 서브 계좌 추가 예시
    scalping_account:
      type: "SUB_FUTURES"
      enabled: false              # 비활성화 가능
      strategy: "SCALPING"        # 향후 추가할 전략
      leverage: 20
      position_size: 5.0
      max_positions: 5
      daily_loss_limit: 1.0
      max_drawdown: 5.0
      symbols:
        - BTCUSDT
```

### 2. 사용 가능한 전략

현재 시스템에서 사용 가능한 전략:
- **TFPE**: Trend Following Pullback Entry (Donchian Channel)
- **MOMENTUM**: Momentum Breakout Strategy
- **ZLHMA_EMA_CROSS**: Zero Lag Hull MA + EMA Cross Strategy

### 3. 계좌별 전략 설정 파라미터

각 서브 계좌에서 설정 가능한 파라미터:

| 파라미터 | 설명 | 권장 범위 |
|---------|------|----------|
| `type` | 계좌 타입 | SUB_FUTURES 또는 SUB_SPOT |
| `enabled` | 활성화 여부 | true/false |
| `strategy` | 실행할 전략 이름 | TFPE, MOMENTUM, ZLHMA_EMA_CROSS |
| `leverage` | 레버리지 | 1-20 (전략별 권장값 참고) |
| `position_size` | 포지션 크기 (%) | 5-30 |
| `max_positions` | 최대 동시 포지션 수 | 1-5 |
| `daily_loss_limit` | 일일 손실 한도 (%) | 1-5 |
| `max_drawdown` | 최대 낙폭 한도 (%) | 5-20 |
| `symbols` | 거래할 심볼 목록 | 전략별 권장 심볼 |

### 4. 마스터 계좌 전략 설정

마스터 계좌는 `strategies` 섹션에서 활성화된 전략을 실행합니다:

```yaml
strategies:
  tfpe:
    enabled: true  # 마스터 계좌에서 실행
  
  momentum:
    enabled: false # 비활성화 (서브 계좌에서만 실행하려면)
  
  zlhma_ema_cross:
    enabled: false # 서브 계좌 전용
```

### 5. 환경 변수 설정

각 서브 계좌의 API 키를 `.env` 파일에 추가:

```bash
# 마스터 계좌
BINANCE_API_KEY=your_master_api_key
BINANCE_SECRET_KEY=your_master_secret_key

# 서브 계좌 1
TEST_ACCOUNT_1_API_KEY=your_sub1_api_key
TEST_ACCOUNT_1_API_SECRET=your_sub1_secret_key

# 서브 계좌 2
TEST_ACCOUNT_2_API_KEY=your_sub2_api_key
TEST_ACCOUNT_2_API_SECRET=your_sub2_secret_key
```

## 🚀 실행 방법

### 1. 멀티 계좌 모드 실행

```bash
# 모든 활성 계좌 실행
python src/main_multi_account.py --mode multi

# 특정 계좌만 실행
python src/main_multi_account.py --mode multi --account test_account_1

# 드라이런 모드
python src/main_multi_account.py --mode multi --dry-run
```

### 2. 단일 계좌 모드 (기존 방식)

```bash
# 마스터 계좌만 사용
python src/main.py

# 또는
python src/main_multi_account.py --mode single
```

### 3. 설정 검증

```bash
# 멀티 계좌 설정 검증
python src/main_multi_account.py --validate

# 시스템 상태 확인
python src/main_multi_account.py --status
```

## 📊 모니터링 및 관리

### 텔레그램 명령어

멀티 계좌 모드에서 사용 가능한 명령어:

- `/status` - 전체 시스템 상태
- `/accounts` - 계좌별 상태
- `/position [account_id]` - 특정 계좌 포지션
- `/performance [account_id]` - 계좌별 성과
- `/stop_account [account_id]` - 특정 계좌 중지
- `/resume_account [account_id]` - 특정 계좌 재개

### 웹 대시보드

`http://localhost:5000` 에서 모든 계좌 통합 모니터링 가능

## ⚠️ 주의사항

1. **API 키 권한**
   - 각 서브 계좌 API 키는 선물 거래 권한 필요
   - IP 화이트리스트 설정 권장

2. **리스크 관리**
   - 계좌별 `daily_loss_limit` 설정 필수
   - 전체 계좌 합산 리스크 고려

3. **전략 충돌**
   - 같은 심볼을 여러 계좌에서 거래 시 주의
   - 전략 간 상관관계 고려

## 🔧 고급 설정

### 계좌 간 재배분 (선택사항)

```yaml
multi_account:
  rebalancing:
    enabled: true
    check_interval: 86400  # 24시간마다
    min_balance_ratio: 0.8  # 최소 잔고 비율
    target_allocation:
      MASTER: 0.5          # 50%
      test_account_1: 0.3  # 30%
      test_account_2: 0.2  # 20%
```

### 계좌별 커스텀 파라미터

각 계좌에서 전략 파라미터를 오버라이드할 수 있습니다:

```yaml
test_account_1:
  strategy: "TFPE"
  custom_params:
    signal_threshold: 5    # 더 엄격한 신호
    stop_loss_atr: 2.0    # 더 넓은 손절
```
