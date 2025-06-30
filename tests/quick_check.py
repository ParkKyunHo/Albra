#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick System Check - 빠른 시스템 체크
배포 전 핵심 기능만 빠르게 확인
"""

import asyncio
import sys
import os
from datetime import datetime

# 프로젝트 루트 경로 추가
current_file = os.path.abspath(__file__)
tests_dir = os.path.dirname(current_file)
project_root = os.path.dirname(tests_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv()


async def quick_check():
    """빠른 시스템 체크"""
    print("\n🚀 AlbraTrading Quick System Check")
    print("=" * 50)
    
    checks_passed = []
    
    # 1. 환경변수 체크
    print("\n1️⃣ 환경변수 체크")
    api_key = os.getenv('BINANCE_API_KEY')
    secret_key = os.getenv('BINANCE_SECRET_KEY')
    
    if api_key and secret_key:
        print("  ✅ Binance API 키 설정됨")
        checks_passed.append(True)
    else:
        print("  ❌ Binance API 키 없음")
        checks_passed.append(False)
    
    # 2. 설정 파일 체크
    print("\n2️⃣ 설정 파일 체크")
    config_file = os.path.join(project_root, 'config', 'config.yaml')
    if os.path.exists(config_file):
        print("  ✅ config.yaml 존재")
        checks_passed.append(True)
    else:
        print("  ❌ config.yaml 없음")
        checks_passed.append(False)
    
    # 3. 핵심 모듈 임포트 체크
    print("\n3️⃣ 핵심 모듈 체크")
    
    modules_to_check = [
        ('Binance API', 'src.core.binance_api', 'BinanceAPI'),
        ('Position Manager', 'src.core.position_manager', 'PositionManager'),
        ('TFPE Strategy', 'src.strategies.tfpe_strategy', 'TFPEStrategy'),
        ('Event Bus', 'src.core.event_bus', 'get_event_bus'),
        ('MDD Manager', 'src.core.mdd_manager_improved', 'ImprovedMDDManager'),
        ('Performance Tracker', 'src.analysis.performance_tracker', 'get_performance_tracker'),
        ('Market Regime', 'src.analysis.market_regime_analyzer', 'get_regime_analyzer')
    ]
    
    for name, module_path, class_name in modules_to_check:
        try:
            module = __import__(module_path, fromlist=[class_name])
            getattr(module, class_name)
            print(f"  ✅ {name}")
            checks_passed.append(True)
        except Exception as e:
            print(f"  ❌ {name}: {str(e)}")
            checks_passed.append(False)
    
    # 4. Binance API 연결 테스트
    if api_key and secret_key:
        print("\n4️⃣ Binance API 연결 테스트")
        try:
            from src.core.binance_api import BinanceAPI
            
            api = BinanceAPI(api_key, secret_key, testnet=True)
            await api.initialize()
            
            # 서버 시간 체크
            server_time = await api.get_server_time()
            if server_time:
                print("  ✅ API 연결 성공")
                
                # 잔고 체크
                balance = await api.get_account_balance()
                print(f"  ✅ 잔고 조회: ${balance:.2f}")
                checks_passed.append(True)
            else:
                print("  ❌ API 연결 실패")
                checks_passed.append(False)
            
            await api.cleanup()
            
        except Exception as e:
            print(f"  ❌ API 테스트 실패: {e}")
            checks_passed.append(False)
    
    # 5. 전략 활성화 체크
    print("\n5️⃣ 전략 설정 체크")
    try:
        from src.utils.config_manager import ConfigManager
        config = ConfigManager().config
        
        tfpe_enabled = config.get('strategies', {}).get('tfpe', {}).get('enabled', False)
        if tfpe_enabled:
            print("  ✅ TFPE 전략 활성화됨")
            
            # 주요 파라미터 출력
            tfpe_config = config['strategies']['tfpe']
            print(f"    - 레버리지: {tfpe_config.get('leverage')}x")
            print(f"    - 포지션 크기: {tfpe_config.get('position_size')}%")
            print(f"    - 거래 코인: {len(tfpe_config.get('major_coins', []))}개")
            checks_passed.append(True)
        else:
            print("  ❌ TFPE 전략 비활성화")
            checks_passed.append(False)
            
    except Exception as e:
        print(f"  ❌ 설정 체크 실패: {e}")
        checks_passed.append(False)
    
    # 결과 요약
    print("\n" + "=" * 50)
    total_checks = len(checks_passed)
    passed_checks = sum(checks_passed)
    
    print(f"✅ 성공: {passed_checks}/{total_checks}")
    print(f"❌ 실패: {total_checks - passed_checks}/{total_checks}")
    
    if passed_checks == total_checks:
        print("\n🎉 시스템 준비 완료! 배포 가능합니다.")
    elif passed_checks >= total_checks * 0.7:
        print("\n⚠️ 일부 문제가 있지만 기본 기능은 작동합니다.")
    else:
        print("\n❌ 시스템에 중요한 문제가 있습니다. 수정 필요!")
    
    print("=" * 50)
    
    # 추가 권장사항
    if not all(checks_passed):
        print("\n📝 권장사항:")
        if not checks_passed[0]:
            print("  • .env 파일에 Binance API 키를 설정하세요")
        if not checks_passed[1]:
            print("  • config/config.yaml 파일을 확인하세요")
        if not all(checks_passed[2:9]):
            print("  • pip install -r requirements.txt 실행하세요")
    
    return passed_checks == total_checks


async def check_realtime_data():
    """실시간 데이터 수신 테스트"""
    print("\n📊 실시간 데이터 테스트 (선택사항)")
    print("-" * 50)
    
    try:
        from src.core.binance_api import BinanceAPI
        
        api_key = os.getenv('BINANCE_API_KEY')
        secret_key = os.getenv('BINANCE_SECRET_KEY')
        
        if not api_key or not secret_key:
            print("API 키가 없어 테스트를 건너뜁니다.")
            return
        
        api = BinanceAPI(api_key, secret_key, testnet=True)
        await api.initialize()
        
        # BTCUSDT 현재가
        price = await api.get_current_price('BTCUSDT')
        print(f"BTC 현재가: ${price:,.2f}")
        
        # 15분봉 데이터
        df = await api.get_klines('BTCUSDT', '15m', limit=5)
        if not df.empty:
            latest = df.iloc[-1]
            print(f"최근 15분봉: O={latest['open']:.2f}, H={latest['high']:.2f}, "
                  f"L={latest['low']:.2f}, C={latest['close']:.2f}")
        
        await api.cleanup()
        
    except Exception as e:
        print(f"실시간 데이터 테스트 실패: {e}")


async def main():
    """메인 함수"""
    # 빠른 체크
    success = await quick_check()
    
    # 추가 테스트 실행 여부
    if success:
        print("\n실시간 데이터 테스트를 실행하시겠습니까? (y/n): ", end='')
        response = input().strip().lower()
        if response == 'y':
            await check_realtime_data()
    
    print("\n테스트 완료!")


if __name__ == "__main__":
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
