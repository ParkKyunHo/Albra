#!/usr/bin/env python3
"""
바이낸스 API 지역 제한 테스트 스크립트
EC2에서 바이낸스 API 접속이 가능한지 테스트합니다.
"""

import json
import requests
import socket
from datetime import datetime

def get_instance_metadata():
    """EC2 인스턴스 메타데이터 가져오기"""
    metadata = {}
    try:
        # 퍼블릭 IP
        r = requests.get('http://checkip.amazonaws.com', timeout=5)
        metadata['public_ip'] = r.text.strip()
        
        # EC2 메타데이터 서비스 v2 사용
        token_r = requests.put(
            'http://169.254.169.254/latest/api/token',
            headers={'X-aws-ec2-metadata-token-ttl-seconds': '21600'},
            timeout=2
        )
        if token_r.status_code == 200:
            token = token_r.text
            headers = {'X-aws-ec2-metadata-token': token}
            
            # 리전
            r = requests.get(
                'http://169.254.169.254/latest/meta-data/placement/region',
                headers=headers,
                timeout=2
            )
            metadata['region'] = r.text if r.status_code == 200 else 'Unknown'
            
            # 인스턴스 타입
            r = requests.get(
                'http://169.254.169.254/latest/meta-data/instance-type',
                headers=headers,
                timeout=2
            )
            metadata['instance_type'] = r.text if r.status_code == 200 else 'Unknown'
    except:
        pass
    
    return metadata

def test_binance_connectivity():
    """바이낸스 API 연결 테스트"""
    print("="*60)
    print(f"바이낸스 API 지역 제한 테스트")
    print(f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S KST')}")
    print("="*60)
    print()
    
    # 인스턴스 정보
    metadata = get_instance_metadata()
    print("📍 인스턴스 정보:")
    print(f"   - 퍼블릭 IP: {metadata.get('public_ip', 'Unknown')}")
    print(f"   - 리전: {metadata.get('region', 'Unknown')}")
    print(f"   - 타입: {metadata.get('instance_type', 'Unknown')}")
    print()
    
    # DNS 해석 테스트
    print("🔍 DNS 해석 테스트:")
    try:
        ip = socket.gethostbyname('api.binance.com')
        print(f"   ✅ api.binance.com → {ip}")
    except Exception as e:
        print(f"   ❌ DNS 해석 실패: {e}")
        return
    print()
    
    # API 엔드포인트 테스트
    endpoints = [
        ('시스템 상태', 'https://api.binance.com/api/v3/ping'),
        ('서버 시간', 'https://api.binance.com/api/v3/time'),
        ('거래소 정보', 'https://api.binance.com/api/v3/exchangeInfo?symbol=BTCUSDT'),
        ('현재가 조회', 'https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT'),
    ]
    
    print("🌐 API 엔드포인트 테스트:")
    all_success = True
    
    for name, url in endpoints:
        try:
            print(f"\n   테스트: {name}")
            print(f"   URL: {url}")
            
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                print(f"   ✅ 성공 (HTTP {response.status_code})")
                
                # 응답 내용 표시
                if 'ping' not in url:
                    data = response.json()
                    if 'price' in url:
                        print(f"   BTC 가격: ${data.get('price', 'N/A')}")
                    elif 'time' in url:
                        server_time = datetime.fromtimestamp(data['serverTime']/1000)
                        print(f"   서버 시간: {server_time.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                print(f"   ❌ 실패 (HTTP {response.status_code})")
                print(f"   응답: {response.text[:200]}")
                all_success = False
                
                # 403이나 451은 지역 제한을 의미
                if response.status_code in [403, 451]:
                    print(f"   ⚠️  지역 제한 감지!")
                    
        except requests.exceptions.Timeout:
            print(f"   ❌ 타임아웃")
            all_success = False
        except requests.exceptions.ConnectionError as e:
            print(f"   ❌ 연결 오류: {e}")
            all_success = False
        except Exception as e:
            print(f"   ❌ 오류: {e}")
            all_success = False
    
    print("\n" + "="*60)
    print("📊 테스트 결과:")
    if all_success:
        print("   ✅ 모든 테스트 통과 - 바이낸스 API 사용 가능!")
        print("   이 리전에서 AlbraTrading을 실행할 수 있습니다.")
    else:
        print("   ❌ 일부 테스트 실패 - 바이낸스 API 접속 제한!")
        print("   다른 리전(한국/일본)으로 마이그레이션이 필요합니다.")
    print("="*60)

if __name__ == "__main__":
    test_binance_connectivity()