# EC2 인스턴스 안정성 가이드

## 개요
이 문서는 AlbraTrading 시스템의 EC2 인스턴스 안정성을 높이기 위한 설정과 모니터링 시스템에 대해 설명합니다.

## 주요 개선 사항

### 1. Systemd 서비스 설정 강화

#### 재시작 정책 개선
```ini
# 이전 (너무 공격적)
Restart=always
RestartSec=10
StartLimitBurst=5

# 개선 (안정적)
Restart=on-failure
RestartSec=30
StartLimitBurst=3
StartLimitInterval=600
StartLimitAction=none
```

**변경 이유:**
- `Restart=on-failure`: 정상 종료 시에는 재시작하지 않음
- `RestartSec=30`: 재시작 간격을 30초로 늘려 크래시 루프 방지
- `StartLimitBurst=3`: 10분 내 3회로 제한하여 무한 재시작 방지

#### 메모리 관리 강화
```ini
MemoryMax=3G
MemorySwapMax=0
OOMPolicy=stop
```

**설정 의미:**
- `MemoryMax=3G`: 최대 3GB로 제한 (t3.medium은 4GB RAM)
- `MemorySwapMax=0`: 스왑 사용 금지로 성능 저하 방지
- `OOMPolicy=stop`: 메모리 부족 시 깔끔하게 종료

### 2. System Watchdog 구현

#### 기능
- **서비스 상태 모니터링**: 30초마다 체크
- **리소스 모니터링**: CPU, 메모리, 디스크 사용률
- **자동 복구**: 3회 연속 실패 시 서비스 재시작
- **스마트 재시작**: 쿨다운 및 횟수 제한

#### 주요 체크 항목
1. **서비스 상태**: systemd 서비스 활성 여부
2. **프로세스 건강성**: Python 프로세스 존재 및 나이
3. **리소스 사용률**: CPU 85%, 메모리 80%, 디스크 90% 임계값
4. **API 응답**: 대시보드 API 상태 확인
5. **로그 오류**: 최근 5분간 심각한 오류 확인

### 3. Crash Prevention System

#### 예방 기능
- **메모리 누수 감지**: tracemalloc으로 메모리 추적
- **가비지 컬렉션**: 메모리 위험 시 강제 GC
- **로그 관리**: 자동 로테이션 및 오래된 로그 삭제
- **파일 디스크립터 관리**: 연결 수 모니터링

#### 자동 조치
- 메모리 70% 초과: 가비지 컬렉션
- 메모리 85% 초과: 강제 GC + 로그 정리
- 디스크 80% 초과: 로그 로테이션
- 파일 디스크립터 80% 초과: 연결 정리 권고

## 설치 방법

### 1. 파일 업로드
배포 스크립트로 자동 업로드되거나, 수동으로 복사:
```bash
scp -i ~/.ssh/trading-bot-key scripts/monitoring/* ubuntu@EC2_IP:/home/ubuntu/AlbraTrading/scripts/monitoring/
```

### 2. 모니터링 시스템 설치
EC2 인스턴스에서:
```bash
cd /home/ubuntu/AlbraTrading
./scripts/monitoring/setup_monitoring.sh
```

### 3. 메인 서비스 업데이트
```bash
sudo cp scripts/systemd/albratrading-multi.service.ec2 /etc/systemd/system/albratrading-multi.service
sudo systemctl daemon-reload
sudo systemctl restart albratrading-multi
```

## 모니터링 명령어

### Watchdog 관리
```bash
# 상태 확인
sudo systemctl status albratrading-watchdog

# 로그 확인
sudo journalctl -u albratrading-watchdog -f

# 재시작
sudo systemctl restart albratrading-watchdog
```

### Crash Prevention
```bash
# 수동 실행
cd /home/ubuntu/AlbraTrading
source venv/bin/activate
python scripts/monitoring/crash_prevention.py

# 로그 확인
tail -f logs/monitoring/crash_prevention.log

# cron 로그 확인
tail -f logs/monitoring/cron.log
```

### 시스템 리소스 확인
```bash
# 메모리 사용량
free -h

# 프로세스별 메모리
ps aux | grep python | sort -k 6 -n -r

# 디스크 사용량
df -h

# 파일 디스크립터
lsof -p $(pgrep -f main_multi_account.py) | wc -l
```

## 문제 해결

### 크래시 루프 발생 시
1. Watchdog 일시 중지
   ```bash
   sudo systemctl stop albratrading-watchdog
   ```

2. 메인 서비스 중지
   ```bash
   sudo systemctl stop albratrading-multi
   ```

3. 로그 확인
   ```bash
   tail -100 logs/systemd_multi_error.log
   tail -100 logs/trading.log
   ```

4. 수동으로 문제 해결 후 재시작

### 메모리 부족 시
1. Crash Prevention 수동 실행
   ```bash
   python scripts/monitoring/crash_prevention.py
   ```

2. 오래된 로그 정리
   ```bash
   find logs/ -name "*.log*" -mtime +7 -delete
   ```

3. 프로세스 재시작
   ```bash
   sudo systemctl restart albratrading-multi
   ```

## 권장 사항

### 1. 정기 점검
- 일일: Watchdog 로그 확인
- 주간: 리소스 사용 추세 분석
- 월간: 로그 아카이브 및 정리

### 2. 알림 설정
Watchdog은 다음 상황에서 텔레그램 알림을 전송합니다:
- 서비스 재시작
- 메모리/CPU 임계값 초과
- 연속 실패 감지

### 3. 백업 전략
- 상태 파일: 일일 백업
- 로그 파일: 주간 아카이브
- 설정 파일: 변경 시 즉시 백업

## 성능 튜닝

### 1. 메모리 최적화
```python
# config.yaml에 추가
system:
  gc_interval: 300  # 5분마다 GC
  max_memory_percent: 75  # 메모리 사용 제한
```

### 2. 연결 풀 관리
```python
# binance_api.py 설정
connector = aiohttp.TCPConnector(
    limit=100,  # 전체 연결 제한
    limit_per_host=30,  # 호스트별 제한
    ttl_dns_cache=300  # DNS 캐시
)
```

### 3. 로그 레벨 조정
```yaml
# Production 환경
logging:
  level: WARNING  # INFO → WARNING으로 변경
  max_file_size: 100MB
  backup_count: 5
```

## 모니터링 지표

### 정상 범위
- CPU: < 70%
- 메모리: < 70%
- 디스크: < 80%
- API 응답: < 1초
- 에러율: < 1%

### 경고 수준
- CPU: 70-85%
- 메모리: 70-80%
- 디스크: 80-90%
- API 응답: 1-5초
- 에러율: 1-5%

### 위험 수준
- CPU: > 85%
- 메모리: > 80%
- 디스크: > 90%
- API 응답: > 5초
- 에러율: > 5%

## 업데이트 이력

### 2025-07-02
- System Watchdog 구현
- Crash Prevention System 추가
- Systemd 서비스 설정 강화
- 모니터링 자동화 스크립트 추가

---

*이 문서는 EC2 인스턴스의 안정적인 운영을 위한 가이드입니다. 정기적으로 업데이트하여 최신 상태를 유지하세요.*