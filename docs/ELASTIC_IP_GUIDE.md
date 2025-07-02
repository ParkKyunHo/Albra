# Elastic IP 설정 가이드

## 🔒 왜 Elastic IP가 필요한가요?

현재 EC2 인스턴스를 Stop/Start할 때마다 퍼블릭 IP가 변경되어 매번 설정을 업데이트해야 합니다.
Elastic IP를 사용하면 고정 IP를 유지할 수 있습니다.

## 📋 Elastic IP 설정 방법

### 1. AWS 콘솔에서 Elastic IP 할당

1. AWS Management Console 로그인
2. EC2 → Elastic IP 이동
3. **"Elastic IP 주소 할당"** 클릭
4. 네트워크 경계 그룹: `ap-northeast-2` (서울)
5. **"할당"** 클릭

### 2. EC2 인스턴스에 연결

1. 할당된 Elastic IP 선택
2. **"작업"** → **"Elastic IP 주소 연결"**
3. 인스턴스 선택: 현재 트레이딩 봇 인스턴스
4. **"연결"** 클릭

### 3. 설정 파일 업데이트

Elastic IP 할당 후 새로운 고정 IP로 모든 설정 파일 업데이트:

```bash
# 예시: 새 Elastic IP가 13.125.XXX.XXX인 경우
# WSL에서 실행
cd /home/albra/AlbraTrading
find . -type f \( -name "*.sh" -o -name "*.bat" -o -name "*.yaml" -o -name "*.md" \) -exec grep -l "43.200.179.200" {} \; | xargs sed -i 's/43.200.179.200/13.125.XXX.XXX/g'
```

## 💰 비용 고려사항

- **연결된 상태**: 무료
- **연결 해제 상태**: 시간당 $0.005 (약 ₩6)
- 월간 약 $3.6 (약 ₩4,500) - 연결 해제 시

## ⚠️ 주의사항

1. **인스턴스 종료 시**: Elastic IP 해제하여 불필요한 과금 방지
2. **리전 제한**: Elastic IP는 할당된 리전에서만 사용 가능
3. **제한**: 리전당 기본 5개까지 할당 가능

## 🔧 Terraform으로 자동화 (선택사항)

`aws_infrastructure/terraform/main.tf`에 이미 Elastic IP 리소스가 정의되어 있습니다:

```hcl
resource "aws_eip" "trading_eip" {
  instance = aws_instance.trading_bot.id
  domain   = "vpc"
  
  tags = {
    Name = "trading-bot-eip"
  }
}
```

Terraform을 사용하여 인프라를 관리하는 경우:
```bash
cd aws_infrastructure/terraform
terraform apply
```

## 📌 권장사항

24/7 운영되는 트레이딩 봇의 경우 Elastic IP 사용을 강력히 권장합니다.
- 안정적인 접속 환경
- 설정 파일 변경 불필요
- 외부 서비스 화이트리스트 관리 용이