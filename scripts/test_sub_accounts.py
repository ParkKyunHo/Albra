#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
서브계좌 연결 및 전략 테스트 스크립트
"""

import asyncio
import sys
import os
from datetime import datetime

# 프로젝트 루트 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.config_manager import ConfigManager
from src.core.state_manager import StateManager
from src.core.multi_account.account_manager import MultiAccountManager
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


async def test_sub_accounts():
    """서브계좌 연결 테스트"""
    try:
        # 설정 로드
        config_manager = ConfigManager()
        state_manager = StateManager()
        
        # 멀티계좌 관리자 생성
        multi_account_manager = MultiAccountManager(
            config_manager=config_manager,
            state_manager=state_manager
        )
        
        # 초기화
        logger.info("멀티계좌 시스템 초기화 시작...")
        if not await multi_account_manager.initialize():
            logger.error("멀티계좌 초기화 실패")
            return
        
        # 시스템 상태 출력
        stats = multi_account_manager.get_system_stats()
        logger.info(f"\n{'='*60}")
        logger.info("멀티계좌 시스템 상태")
        logger.info(f"{'='*60}")
        logger.info(f"활성화: {stats['enabled']}")
        logger.info(f"초기화: {stats['initialized']}")
        logger.info(f"총 계좌: {stats['accounts']['total']}")
        logger.info(f"활성 계좌: {stats['accounts']['active']}")
        logger.info(f"{'='*60}\n")
        
        # 각 계좌별 상태 확인
        logger.info("계좌별 상세 정보:")
        logger.info("-" * 60)
        
        # 마스터 계좌
        master_summary = await multi_account_manager.get_account_summary('MASTER')
        logger.info("\n[MASTER 계좌]")
        logger.info(f"상태: {master_summary.get('status', 'N/A')}")
        logger.info(f"잔고: ${master_summary.get('balance', 0):.2f}")
        logger.info(f"포지션: {len(master_summary.get('positions', []))}개")
        
        # 서브 계좌
        for account_id, account_info in multi_account_manager.accounts.items():
            summary = await multi_account_manager.get_account_summary(account_id)
            
            logger.info(f"\n[{account_id} 계좌]")
            logger.info(f"상태: {account_info.status.value}")
            logger.info(f"전략: {account_info.strategy}")
            logger.info(f"심볼: {', '.join(account_info.symbols)}")
            logger.info(f"레버리지: {account_info.leverage}x")
            logger.info(f"포지션 크기: {account_info.position_size}%")
            logger.info(f"일일 손실 한도: {account_info.daily_loss_limit}%")
            logger.info(f"최대 DD: {account_info.max_drawdown}%")
            
            if 'error' not in summary:
                logger.info(f"잔고: ${summary.get('balance', 0):.2f}")
                logger.info(f"포지션: {len(summary.get('positions', []))}개")
            else:
                logger.error(f"오류: {summary['error']}")
        
        logger.info("-" * 60)
        
        # API 연결 테스트
        logger.info("\nAPI 연결 테스트:")
        for account_id, api_client in multi_account_manager.api_clients.items():
            try:
                # 서버 시간 조회로 연결 테스트
                server_time = await api_client.get_server_time()
                logger.info(f"✓ {account_id}: API 연결 정상 (서버 시간: {datetime.fromtimestamp(server_time/1000)})")
            except Exception as e:
                logger.error(f"✗ {account_id}: API 연결 실패 - {e}")
        
        # 포지션 매니저 테스트
        logger.info("\n포지션 매니저 테스트:")
        for account_id, position_manager in multi_account_manager.position_managers.items():
            positions = position_manager.get_active_positions()
            logger.info(f"{account_id}: {len(positions)}개 활성 포지션")
            for pos in positions:
                logger.info(f"  - {pos.symbol} {pos.side} {pos.size:.4f} @ ${pos.entry_price:.2f}")
        
        # 전체 동기화 테스트
        logger.info("\n전체 계좌 동기화 테스트...")
        sync_report = await multi_account_manager.sync_all_accounts()
        
        logger.info(f"\n동기화 결과:")
        logger.info(f"총 포지션: {sync_report['total_positions']}")
        logger.info(f"총 잔고: ${sync_report['total_balance']:.2f}")
        
        for account_id, account_sync in sync_report['accounts'].items():
            if 'error' not in account_sync:
                logger.info(f"{account_id}: 잔고=${account_sync.get('balance', 0):.2f}, "
                          f"포지션={account_sync.get('position_count', 0)}개")
        
        # 정리
        await multi_account_manager.cleanup()
        logger.info("\n✓ 테스트 완료")
        
    except Exception as e:
        logger.error(f"테스트 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()


async def test_sub_account_trading():
    """서브계좌 거래 테스트 (주의: 실제 거래 발생)"""
    # 실제 거래를 수행하므로 주의!
    logger.warning("⚠️ 이 테스트는 실제 거래를 수행합니다!")
    
    confirm = input("계속하시겠습니까? (yes/no): ")
    if confirm.lower() != 'yes':
        logger.info("테스트 취소됨")
        return
    
    try:
        # 설정 로드
        config_manager = ConfigManager()
        state_manager = StateManager()
        
        # 멀티계좌 관리자 생성
        multi_account_manager = MultiAccountManager(
            config_manager=config_manager,
            state_manager=state_manager
        )
        
        # 초기화
        if not await multi_account_manager.initialize():
            logger.error("멀티계좌 초기화 실패")
            return
        
        # 테스트할 계좌 선택
        test_account = 'sub1'  # 테스트할 서브계좌
        
        if test_account not in multi_account_manager.accounts:
            logger.error(f"{test_account} 계좌를 찾을 수 없습니다")
            return
        
        account_info = multi_account_manager.accounts[test_account]
        logger.info(f"\n{test_account} 계좌로 거래 테스트")
        logger.info(f"전략: {account_info.strategy}")
        logger.info(f"심볼: {account_info.symbols[0]}")
        
        # 현재 가격 조회
        api_client = multi_account_manager.api_clients[test_account]
        symbol = account_info.symbols[0]
        current_price = await api_client.get_current_price(symbol)
        logger.info(f"현재가: ${current_price:.2f}")
        
        # 최소 거래 수량 계산 (매우 작은 테스트 주문)
        min_quantity = 0.001  # BTC 기준
        
        # 테스트 주문 (시장가 매수)
        logger.info(f"\n테스트 주문: {symbol} 매수 {min_quantity}")
        
        result = await multi_account_manager.execute_order(
            account_id=test_account,
            symbol=symbol,
            side='BUY',
            quantity=min_quantity,
            order_type='MARKET'
        )
        
        if result:
            logger.info("✓ 주문 성공!")
            logger.info(f"주문 ID: {result.get('orderId')}")
            logger.info(f"체결가: ${result.get('fills', [{}])[0].get('price', 'N/A')}")
        else:
            logger.error("✗ 주문 실패")
        
        # 포지션 확인
        await asyncio.sleep(2)  # 잠시 대기
        
        position_manager = multi_account_manager.position_managers[test_account]
        await position_manager.sync_positions()
        
        positions = position_manager.get_active_positions()
        logger.info(f"\n현재 포지션: {len(positions)}개")
        
        # 정리
        await multi_account_manager.cleanup()
        
    except Exception as e:
        logger.error(f"거래 테스트 중 오류: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("\n서브계좌 테스트 메뉴:")
    print("1. 서브계좌 연결 상태 확인")
    print("2. 서브계좌 거래 테스트 (주의: 실제 거래)")
    
    choice = input("\n선택 (1 또는 2): ")
    
    if choice == '1':
        asyncio.run(test_sub_accounts())
    elif choice == '2':
        asyncio.run(test_sub_account_trading())
    else:
        print("잘못된 선택입니다")
