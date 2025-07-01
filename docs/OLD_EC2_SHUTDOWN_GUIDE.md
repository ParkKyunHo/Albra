# 이전 EC2 인스턴스 종료 가이드

## 📋 인스턴스 정보
- **IP**: 54.88.60.48
- **리전**: us-east-1 (미국 동부)
- **상태**: 서비스 중지됨, 백업 완료

## ✅ 완료된 작업
1. **백업 완료** (2025-07-02 00:31 KST)
   - 위치: `/home/albra/AlbraTrading/backups/old_ec2_20250702_003119`
   - 백업 파일:
     - `.env.backup` - 환경 설정
     - `multi_account_state.json` - 멀티 계좌 상태
     - `position_cache.json` - 포지션 캐시
     - `strategy_state.json` - 전략 상태
     - `system_state.json` - 시스템 상태
     - `trade_history.json` - 거래 내역
     - `trading_last_1000.log` - 최근 로그

2. **서비스 비활성화**
   - systemd 서비스 disable 완료

## 🛑 EC2 인스턴스 중지 방법

### AWS 콘솔에서:
1. AWS Management Console 로그인
2. EC2 대시보드로 이동
3. 리전을 **US East (N. Virginia) us-east-1**로 변경
4. 인스턴스 목록에서 IP `54.88.60.48` 찾기
5. 인스턴스 선택 → Actions → Instance State → **Stop Instance**
6. 확인 대화상자에서 **Stop** 클릭

### AWS CLI에서:
```bash
aws ec2 stop-instances --instance-ids [INSTANCE_ID] --region us-east-1
```

## ⚠️ 주의사항

### 즉시 종료하지 마세요!
- **Stop** (중지): 인스턴스를 일시 중지, 데이터 보존, 재시작 가능
- **Terminate** (종료): 인스턴스 영구 삭제, 복구 불가능

### 권장 절차:
1. **지금**: Stop Instance (중지)
2. **1주일 후**: 새 시스템에 문제 없으면 Terminate
3. **EBS 스냅샷**: 필요시 백업용 스냅샷 생성

## 💰 비용 관련
- **중지된 인스턴스**: 
  - EC2 인스턴스 요금 없음
  - EBS 스토리지 요금만 부과 (약 $0.10/GB/월)
- **종료 후**: 모든 요금 없음

## 📊 체크리스트

### 중지 전 확인:
- [x] 모든 중요 데이터 백업
- [x] 새 EC2에서 서비스 정상 작동
- [x] 바이낸스 API 연결 확인
- [x] 텔레그램 봇 작동 확인

### 중지 후 확인:
- [ ] AWS 콘솔에서 인스턴스 상태 "stopped" 확인
- [ ] 불필요한 Elastic IP 해제 (있는 경우)
- [ ] 보안 그룹 정리 (필요시)

## 🔄 롤백 계획
만약 새 EC2에 문제 발생 시:
1. AWS 콘솔에서 이전 인스턴스 Start
2. `deployment.yaml`의 IP를 54.88.60.48로 되돌림
3. 바이낸스 API 화이트리스트는 그대로 유지 (작동 안 함)

## 📝 최종 정리 (1주일 후)
1. 인스턴스 Terminate
2. 관련 EBS 볼륨 삭제
3. 스냅샷 삭제 (백업 불필요시)
4. 보안 그룹 삭제 (전용 그룹인 경우)

---
*작성일: 2025-07-02*
*작성자: Claude Code Assistant*