#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pre-flight Check - 시스템 시작 전 최종 점검
실제 거래 시작 전 반드시 실행
"""

import asyncio
import sys
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List

# 프로젝트 루트 경로 추가
current_file = os.path.abspath(__file__)
tests_dir = os.path.dirname(current_file)
project_root = os.path.dirname(tests_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv()


class PreFlightCheck:
    """시스템 시작 전 체크리스트"""
    
    def __init__(self):
        self.checks = {
            'critical': {},  # 필수 체크
            'important': {}, # 중요 체크
            'optional': {}   # 선택 체크
        }
        self.start_time = datetime.now()
    
    async def run(self):
        """모든 체크 실행"""
        print("\n" + "="*70)
        print("✈️  AlbraTrading Pre-flight Check")
        print("="*70)
        print(f"시작 시간: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*70 + "\n")
        
        # 1. 필수 체크
        await self.critical_checks()
        
        # 2. 중요 체크
        await self.important_checks()
        
        # 3. 선택 체크
        await self.optional_checks()
        
        # 4. 결과 요약
        self.print_summary()
        
        # 5. 최종 판정
        return self.final_verdict()
    
    async def critical_checks(self):
        """필수 체크 항목"""
        print("🔴 필수 체크 항목")
        print("-" * 50)
        
        # 1. API 키 확인
        api_key = os.getenv('BINANCE_API_KEY')
        secret_key = os.getenv('BINANCE_SECRET_KEY')
        
        if api_key and secret_key:
            self.checks['critical']['API Keys'] = True
            print("  ✅ Binance API 키 설정됨")
            
            # API 연결 테스트
            try:
                from src.core.binance_api import BinanceAPI
                api = BinanceAPI(api_key, secret_key, testnet=True)
                await api.initialize()
                
                server_time = await api.get_server_time()
                if server_time:
                    self.checks['critical']['API Connection'] = True
                    print("  ✅ Binance API 연결 성공")
                    
                    # 시간 동기화 체크
                    server_dt = datetime.fromtimestamp(server_time / 1000)
                    time_diff = abs((datetime.now() - server_dt).total_seconds())
                    if time_diff < 60:  # 1분 이내
                        print(f"  ✅ 시간 동기화 정상 (차이: {time_diff:.1f}초)")
                    else:
                        print(f"  ⚠️ 시간 동기화 문제 (차이: {time_diff:.1f}초)")
                        self.checks['important']['Time Sync'] = False
                    
                    # 잔고 확인
                    balance = await api.get_account_balance()
                    if balance > 0:
                        self.checks['critical']['Account Balance'] = True
                        print(f"  ✅ 계좌 잔고: ${balance:,.2f}")
                    else:
                        self.checks['critical']['Account Balance'] = False
                        print(f"  ❌ 계좌 잔고 없음")
                else:
                    self.checks['critical']['API Connection'] = False
                    print("  ❌ API 연결 실패")
                
                await api.cleanup()
                
            except Exception as e:
                self.checks['critical']['API Connection'] = False
                print(f"  ❌ API 테스트 실패: {e}")
        else:
            self.checks['critical']['API Keys'] = False
            print("  ❌ API 키 설정 안됨")
        
        # 2. 설정 파일 확인
        config_file = os.path.join(project_root, 'config', 'config.yaml')
        if os.path.exists(config_file):
            self.checks['critical']['Config File'] = True
            print("  ✅ 설정 파일 존재")
            
            # 설정 유효성 검사
            try:
                from src.utils.config_manager import ConfigManager
                config = ConfigManager().config
                
                # 필수 설정 확인
                if 'strategies' in config and 'trading' in config:
                    self.checks['critical']['Config Valid'] = True
                    print("  ✅ 설정 파일 유효")
                else:
                    self.checks['critical']['Config Valid'] = False
                    print("  ❌ 설정 파일 불완전")
                    
            except Exception as e:
                self.checks['critical']['Config Valid'] = False
                print(f"  ❌ 설정 파일 오류: {e}")
        else:
            self.checks['critical']['Config File'] = False
            print("  ❌ 설정 파일 없음")
        
        # 3. 필수 디렉토리
        required_dirs = ['data', 'logs', 'state']
        all_dirs_exist = True
        for dir_name in required_dirs:
            dir_path = os.path.join(project_root, dir_name)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
                print(f"  ✅ {dir_name}/ 디렉토리 생성됨")
            else:
                print(f"  ✅ {dir_name}/ 디렉토리 존재")
        self.checks['critical']['Directories'] = True
        
        print()
    
    async def important_checks(self):
        """중요 체크 항목"""
        print("🟡 중요 체크 항목")
        print("-" * 50)
        
        # 1. 전략 설정 확인
        try:
            from src.utils.config_manager import ConfigManager
            config = ConfigManager().config
            
            # TFPE 전략 확인
            tfpe_config = config.get('strategies', {}).get('tfpe', {})
            if tfpe_config.get('enabled', False):
                self.checks['important']['TFPE Strategy'] = True
                print("  ✅ TFPE 전략 활성화")
                
                # 거래 코인 확인
                coins = tfpe_config.get('major_coins', [])
                print(f"    - 거래 코인: {', '.join(coins[:3])}... (총 {len(coins)}개)")
                
                # 리스크 설정 확인
                leverage = tfpe_config.get('leverage', 15)
                position_size = tfpe_config.get('position_size', 24)
                
                if leverage > 20:
                    print(f"    ⚠️ 높은 레버리지: {leverage}x")
                else:
                    print(f"    - 레버리지: {leverage}x")
                
                if position_size > 30:
                    print(f"    ⚠️ 큰 포지션 크기: {position_size}%")
                else:
                    print(f"    - 포지션 크기: {position_size}%")
                
            else:
                self.checks['important']['TFPE Strategy'] = False
                print("  ❌ TFPE 전략 비활성화")
                
        except Exception as e:
            self.checks['important']['TFPE Strategy'] = False
            print(f"  ❌ 전략 설정 확인 실패: {e}")
        
        # 2. MDD 보호 설정
        try:
            mdd_config = config.get('mdd_protection', {})
            if mdd_config.get('enabled', True):
                self.checks['important']['MDD Protection'] = True
                print("  ✅ MDD 보호 활성화")
                print(f"    - 최대 MDD: {mdd_config.get('max_allowed_mdd', 40)}%")
                print(f"    - 강제 청산: {mdd_config.get('mdd_force_close_threshold', 50)}%")
            else:
                self.checks['important']['MDD Protection'] = False
                print("  ⚠️ MDD 보호 비활성화")
                
        except:
            self.checks['important']['MDD Protection'] = False
            print("  ❌ MDD 설정 확인 실패")
        
        # 3. 알림 시스템
        telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        telegram_chat = os.getenv('TELEGRAM_CHAT_ID')
        
        if telegram_token and telegram_chat:
            self.checks['important']['Telegram'] = True
            print("  ✅ 텔레그램 알림 설정됨")
        else:
            self.checks['important']['Telegram'] = False
            print("  ⚠️ 텔레그램 알림 미설정 (선택사항)")
        
        # 4. 기존 포지션 확인
        try:
            from src.core.state_manager import StateManager
            state_manager = StateManager()
            
            # 저장된 상태 확인
            state_file = os.path.join(project_root, 'state', 'positions.json')
            if os.path.exists(state_file):
                with open(state_file, 'r') as f:
                    saved_positions = json.load(f)
                    
                active_count = len([p for p in saved_positions.values() 
                                  if p.get('status') == 'ACTIVE'])
                
                if active_count > 0:
                    print(f"  ⚠️ 기존 활성 포지션 {active_count}개 발견")
                    self.checks['important']['Clean Start'] = False
                else:
                    print("  ✅ 깨끗한 시작 상태")
                    self.checks['important']['Clean Start'] = True
            else:
                print("  ✅ 첫 실행")
                self.checks['important']['Clean Start'] = True
                
        except Exception as e:
            print(f"  ⚠️ 상태 확인 실패: {e}")
            self.checks['important']['Clean Start'] = True
        
        print()
    
    async def optional_checks(self):
        """선택 체크 항목"""
        print("🟢 선택 체크 항목")
        print("-" * 50)
        
        # 1. 웹 대시보드
        try:
            import flask
            self.checks['optional']['Web Dashboard'] = True
            print("  ✅ 웹 대시보드 사용 가능")
        except ImportError:
            self.checks['optional']['Web Dashboard'] = False
            print("  ⚠️ Flask 미설치 (웹 대시보드 사용 불가)")
        
        # 2. Phase 2 기능
        try:
            from src.utils.config_manager import ConfigManager
            config = ConfigManager().config
            
            if config.get('phase2', {}).get('enabled', False):
                self.checks['optional']['Phase 2'] = True
                print("  ✅ Phase 2 기능 활성화")
            else:
                self.checks['optional']['Phase 2'] = False
                print("  ⚠️ Phase 2 기능 비활성화")
                
        except:
            self.checks['optional']['Phase 2'] = False
        
        # 3. 성과 기록
        perf_dir = os.path.join(project_root, 'data', 'performance')
        if os.path.exists(perf_dir):
            files = os.listdir(perf_dir)
            if files:
                self.checks['optional']['Performance History'] = True
                print(f"  ✅ 성과 기록 존재 ({len(files)}개 파일)")
            else:
                self.checks['optional']['Performance History'] = False
                print("  ⚠️ 성과 기록 없음")
        else:
            self.checks['optional']['Performance History'] = False
            print("  ⚠️ 성과 기록 디렉토리 없음")
        
        print()
    
    def print_summary(self):
        """체크 결과 요약"""
        print("="*70)
        print("📊 체크 결과 요약")
        print("="*70)
        
        # 카테고리별 집계
        for category, checks in self.checks.items():
            passed = sum(1 for v in checks.values() if v)
            total = len(checks)
            
            if category == 'critical':
                icon = "🔴"
                name = "필수"
            elif category == 'important':
                icon = "🟡"
                name = "중요"
            else:
                icon = "🟢"
                name = "선택"
            
            print(f"{icon} {name} 항목: {passed}/{total} 통과")
            
            # 실패 항목 출력
            failed = [k for k, v in checks.items() if not v]
            if failed:
                for item in failed:
                    print(f"   ❌ {item}")
        
        print()
    
    def final_verdict(self) -> bool:
        """최종 판정"""
        print("="*70)
        print("🎯 최종 판정")
        print("="*70)
        
        # 필수 항목 모두 통과 여부
        critical_passed = all(self.checks['critical'].values())
        
        # 중요 항목 통과율
        important_total = len(self.checks['important'])
        important_passed = sum(1 for v in self.checks['important'].values() if v)
        important_rate = important_passed / important_total if important_total > 0 else 0
        
        if critical_passed and important_rate >= 0.7:
            print("✅ 시스템 시작 준비 완료!")
            print("   모든 필수 항목을 통과했습니다.")
            print("\n🚀 다음 명령어로 시스템을 시작하세요:")
            print("   python src/main.py")
            
            if important_rate < 1.0:
                print("\n⚠️ 주의사항:")
                failed_important = [k for k, v in self.checks['important'].items() if not v]
                for item in failed_important:
                    if item == 'Telegram':
                        print("   - 텔레그램 알림이 설정되지 않았습니다")
                    elif item == 'Clean Start':
                        print("   - 기존 포지션이 있습니다. 확인 필요!")
            
            return True
            
        elif critical_passed:
            print("⚠️ 조건부 시작 가능")
            print("   필수 항목은 통과했지만 중요 항목에 문제가 있습니다.")
            print("   위험을 감수하고 시작하시겠습니까?")
            return True
            
        else:
            print("❌ 시스템 시작 불가!")
            print("   필수 항목을 먼저 해결해주세요.")
            
            # 해결 방법 안내
            print("\n📝 해결 방법:")
            if not self.checks['critical'].get('API Keys', False):
                print("   1. .env 파일에 BINANCE_API_KEY와 BINANCE_SECRET_KEY 설정")
            if not self.checks['critical'].get('Config File', False):
                print("   2. config/config.yaml 파일 확인")
            if not self.checks['critical'].get('API Connection', False):
                print("   3. 인터넷 연결 및 API 키 유효성 확인")
            if not self.checks['critical'].get('Account Balance', False):
                print("   4. 테스트넷 또는 실제 계좌에 잔고 입금")
            
            return False
        
        print("="*70)


async def main():
    """메인 함수"""
    checker = PreFlightCheck()
    ready = await checker.run()
    
    if ready:
        print("\n시스템을 시작하시겠습니까? (y/n): ", end='')
        response = input().strip().lower()
        
        if response == 'y':
            print("\n시스템을 시작합니다...")
            # 실제로 main.py를 실행하려면:
            # os.system(f"python {os.path.join(project_root, 'src', 'main.py')}")
        else:
            print("\n시작을 취소했습니다.")
    else:
        print("\n문제를 해결한 후 다시 실행해주세요.")


if __name__ == "__main__":
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
