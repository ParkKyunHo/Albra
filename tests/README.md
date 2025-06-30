# AlbraTrading System - 테스트 가이드

## 🚀 배포 전 테스트 프로세스

### 1. 빠른 체크 (1분)
가장 기본적인 시스템 체크를 수행합니다.

```bash
python tests/quick_check.py
```

확인 항목:
- 환경변수 설정
- 설정 파일 존재
- 핵심 모듈 임포트
- Binance API 연결
- 전략 활성화 상태

### 2. Pre-flight 체크 (3분)
시스템 시작 전 필수 확인 사항을 점검합니다.

```bash
python tests/pre_flight_check.py
```

확인 항목:
- API 키 유효성
- 시간 동기화
- 계좌 잔고
- 전략 설정
- MDD 보호 설정
- 기존 포지션 상태

### 3. 전체 시스템 통합 테스트 (10분)
모든 컴포넌트의 상세한 테스트를 수행합니다.

```bash
python tests/test_system_integration.py
```

테스트 항목:
- 환경 설정
- 데이터베이스 연결
- Binance API 기능
- 모든 핵심 컴포넌트
- 전략 초기화
- 이벤트 시스템
- 알림 시스템
- 포지션 관리
- 리스크 관리
- 성과 추적
- Phase 2 컴포넌트
- 실시간 모니터링
- 웹 대시보드
- 거래 시뮬레이션

### 4. 시스템 시작
모든 테스트를 통과한 후 시스템을 시작합니다.

```bash
# 런처 사용 (권장)
python run.py

# 또는 직접 실행
python src/main.py
```

## 📋 테스트 결과 해석

### ✅ 모든 테스트 통과
- 시스템을 안전하게 시작할 수 있습니다
- 실제 거래를 시작하기 전에 소액으로 테스트하세요

### ⚠️ 일부 테스트 실패
- **Critical 실패**: 시스템 시작 불가, 반드시 해결 필요
- **Important 실패**: 조건부 시작 가능, 주의 필요
- **Optional 실패**: 시작 가능, 일부 기능 제한

### ❌ 주요 실패 원인 및 해결

1. **API 키 오류**
   ```bash
   # .env 파일 확인
   BINANCE_API_KEY=your_api_key
   BINANCE_SECRET_KEY=your_secret_key
   ```

2. **설정 파일 오류**
   - `config/config.yaml` 파일 확인
   - YAML 문법 오류 체크

3. **모듈 임포트 실패**
   ```bash
   pip install -r requirements.txt
   ```

4. **데이터베이스 오류**
   - `data/` 디렉토리 권한 확인
   - 디스크 공간 확인

## 🔍 테스트 로그

테스트 결과는 `logs/` 디렉토리에 저장됩니다:
- `test_report_YYYYMMDD_HHMMSS.json`: 상세 테스트 결과

## 🛡️ 안전 권장사항

1. **테스트넷에서 먼저 실행**
   - `config.yaml`에서 `mode: testnet` 설정
   - 최소 24시간 테스트

2. **소액으로 시작**
   - `position_size: 5` (5%로 시작)
   - `leverage: 5` (낮은 레버리지)

3. **모니터링 설정**
   - 텔레그램 알림 설정 필수
   - 첫 주는 집중 모니터링

4. **백업 준비**
   - `state/` 디렉토리 정기 백업
   - `data/` 디렉토리 백업

## 📞 문제 발생 시

1. 즉시 시스템 중지: `Ctrl+C`
2. 로그 확인: `logs/` 디렉토리
3. 상태 확인: `state/positions.json`
4. Pre-flight 체크 재실행

## 🚀 정상 시작 순서

1. `python tests/quick_check.py` ✅
2. `python tests/pre_flight_check.py` ✅
3. `python run.py` → 옵션 1 선택
4. 웹 대시보드 확인: `http://localhost:5000`
5. 텔레그램 알림 확인

---

**중요**: 실제 자금으로 거래하기 전에 반드시 테스트넷에서 충분히 테스트하세요!
