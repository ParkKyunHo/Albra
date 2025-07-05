# Claude API 설정 가이드

## 1. API 키 발급

1. [Anthropic Console](https://console.anthropic.com/) 접속
2. 계정 생성 또는 로그인
3. API Keys 섹션에서 새 API 키 생성
4. 키를 안전한 곳에 복사

## 2. 환경 변수 설정

### WSL/Linux에서 설정

#### 방법 1: 현재 세션에만 적용
```bash
export ANTHROPIC_API_KEY='sk-ant-api03-...'
```

#### 방법 2: 영구 설정 (.bashrc)
```bash
echo "export ANTHROPIC_API_KEY='sk-ant-api03-...'" >> ~/.bashrc
source ~/.bashrc
```

#### 방법 3: .env 파일 사용
```bash
# 프로젝트 루트에 .env 파일 생성
cd /home/albra/AlbraTrading
echo "ANTHROPIC_API_KEY=sk-ant-api03-..." > .env
```

## 3. Streamlit에서 사용

### 환경 변수 로드 (이미 구현됨)
```python
import os
api_key = os.getenv('ANTHROPIC_API_KEY')
```

### Streamlit 실행 시 환경 변수 전달
```bash
# 방법 1: 직접 전달
ANTHROPIC_API_KEY='sk-ant-api03-...' streamlit run backtest/app/streamlit_app.py

# 방법 2: .env 파일 사용 (python-dotenv 필요)
pip install python-dotenv
```

## 4. 보안 주의사항

- **절대 API 키를 코드에 하드코딩하지 마세요**
- `.env` 파일은 `.gitignore`에 추가되어 있습니다
- API 키를 공개 저장소에 커밋하지 마세요

## 5. 사용량 및 비용

- Claude API는 사용량 기반 과금
- 현재 구현은 매 전략 파싱마다 API 호출
- 예상 비용:
  - Claude 3 Opus: ~$15/백만 토큰 (입력)
  - 평균 전략 파싱: ~1,000 토큰
  - 1,000회 파싱 ≈ $0.015

## 6. 문제 해결

### API 키가 인식되지 않을 때
```bash
# 환경 변수 확인
echo $ANTHROPIC_API_KEY

# Streamlit 재시작
pkill -f streamlit
streamlit run backtest/app/streamlit_app.py
```

### 권한 오류
```bash
# .env 파일 권한 설정
chmod 600 .env
```

## 7. 고급 설정

### 모델 선택
```python
# claude_parser.py에서 모델 변경
self.model = "claude-3-opus-20240229"  # 최고 성능
# self.model = "claude-3-sonnet-20240229"  # 균형
# self.model = "claude-3-haiku-20240307"  # 빠른 응답
```

### 프롬프트 커스터마이징
`claude_parser.py`의 `_create_parsing_prompt` 메서드를 수정하여
프롬프트를 최적화할 수 있습니다.