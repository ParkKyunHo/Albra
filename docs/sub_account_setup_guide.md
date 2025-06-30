# 서브계좌 API 설정 가이드

## 1. 바이낸스에서 서브계좌 생성

1. 바이낸스 메인 계정에 로그인
2. 계정 > 서브계정 관리로 이동
3. "서브계정 생성" 클릭
4. 서브계정 생성:
   - sub1: ZLMACD_ICHIMOKU 전략용
   - sub2: MOMENTUM 전략용 (선택사항)

## 2. 서브계좌 API 키 생성

각 서브계좌에 대해:

1. 서브계정 목록에서 해당 계정의 "API 관리" 클릭
2. "API 키 생성" 클릭
3. API 권한 설정:
   - ✅ 선물 거래 활성화 (Enable Futures)
   - ✅ 읽기 권한 (Can Read)
   - ✅ 선물 거래 권한 (Enable Futures Trading)
   - ❌ 출금 권한은 비활성화 (보안상)
4. API Key와 Secret Key 저장

## 3. .env 파일 설정

```bash
# 마스터 계좌 (기존)
BINANCE_API_KEY=your_master_api_key
BINANCE_SECRET_KEY=your_master_secret_key

# 서브계좌 1 (ZLMACD_ICHIMOKU 전략)
SUB1_API_KEY=your_sub1_api_key
SUB1_API_SECRET=your_sub1_secret_key

# 서브계좌 2 (MOMENTUM 전략) - 선택사항
SUB2_API_KEY=your_sub2_api_key
SUB2_API_SECRET=your_sub2_secret_key

# 텔레그램 설정 (기존)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

## 4. config.yaml 확인

```yaml
multi_account:
  enabled: true  # 멀티계좌 활성화
  mode: "multi"  # multi 모드
  
  sub_accounts:
    sub1:
      enabled: true  # 활성화
      strategy: "ZLMACD_ICHIMOKU"
      # ... 기타 설정
    
    sub2:
      enabled: false  # 필요시 true로 변경
      strategy: "MOMENTUM"
      # ... 기타 설정
```

## 5. 서브계좌 자금 이체

1. 바이낸스 메인 계정에서 서브계정으로 자금 이체
2. 각 서브계좌에 충분한 USDT 입금
3. 권장 최소 금액:
   - 테스트: $100 이상
   - 운영: $1000 이상

## 6. 테스트 실행

```bash
# 서브계좌 연결 테스트
python scripts/test_sub_accounts.py

# 선택 1: 연결 상태 확인 (안전)
# 선택 2: 실제 거래 테스트 (주의!)
```

## 7. 시스템 실행

```bash
# 멀티계좌 모드로 실행
python src/main.py
```

## 8. 모니터링

텔레그램 명령어:
- `/accounts` - 계좌별 현황
- `/account_status sub1` - 특정 계좌 상태
- `/strategies` - 전략 상태
- `/fix_positions` - 포지션 인식 문제 수정

## 주의사항

1. **API 권한**: 출금 권한은 절대 활성화하지 마세요
2. **자금 관리**: 각 서브계좌에 적절한 자금 배분
3. **리스크 관리**: 서브계좌별 손실 한도 설정 확인
4. **모니터링**: 정기적으로 각 계좌 상태 확인

## 문제 해결

### API 키 인식 안됨
- .env 파일 경로 확인 (프로젝트 루트)
- 환경변수 이름 확인 (대소문자 구분)
- .env 파일 다시 로드: 시스템 재시작

### 서브계좌 비활성
- config.yaml에서 enabled: true 확인
- API 키가 올바르게 설정되었는지 확인
- 바이낸스에서 API 권한 확인

### 전략이 실행되지 않음
- 해당 전략이 config.yaml에서 활성화되었는지 확인
- 서브계좌에 충분한 자금이 있는지 확인
- 로그 파일에서 오류 메시지 확인
