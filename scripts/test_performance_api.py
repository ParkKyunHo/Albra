#!/usr/bin/env python3
"""
Performance API 테스트 스크립트
"""

import requests
import json
import sys

def test_performance_api(base_url="http://localhost:5000"):
    """성과 API 테스트"""
    
    print(f"Testing Performance API at {base_url}")
    print("=" * 60)
    
    # API 엔드포인트 목록
    endpoints = [
        "/api/status",
        "/api/performance/overview",
        "/api/performance/comparison",
        "/api/performance/returns?period=daily",
        "/api/performance/drawdown",
        "/api/performance/trades?days=30"
    ]
    
    for endpoint in endpoints:
        url = f"{base_url}{endpoint}"
        print(f"\nTesting: {endpoint}")
        print("-" * 40)
        
        try:
            response = requests.get(url, timeout=5)
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"Response: {json.dumps(data, indent=2)[:200]}...")
            else:
                print(f"Error Response: {response.text[:200]}")
                
        except requests.exceptions.Timeout:
            print("Request timed out")
        except requests.exceptions.ConnectionError:
            print("Connection error")
        except Exception as e:
            print(f"Error: {e}")
    
    # Flask 라우트 확인
    print("\n\nChecking Flask Routes:")
    print("=" * 60)
    try:
        # Flask app의 URL 맵을 확인하는 특별한 엔드포인트 추가
        response = requests.get(f"{base_url}/api/routes", timeout=5)
        if response.status_code == 200:
            routes = response.json()
            for route in routes:
                print(f"  {route}")
    except:
        print("Could not fetch routes")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    else:
        base_url = "http://localhost:5000"
    
    test_performance_api(base_url)