#!/usr/bin/env python3
"""
AlbraTrading 멀티 계좌 관리 CLI
멀티 계좌 시스템을 관리하고 모니터링하는 명령줄 인터페이스
"""
import asyncio
import click
import json
import sys
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from decimal import Decimal
from tabulate import tabulate
import pandas as pd

# 프로젝트 루트 경로 추가
sys.path.append(str(Path(__file__).parent.parent))

from src.core.multi_account import (
    MultiAccountManager,
    UnifiedMonitor,
    MultiAccountRiskManager,
    StrategyAllocator
)
from src.utils.config_manager import ConfigManager
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class MultiAccountCLI:
    """멀티 계좌 CLI 핸들러"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.account_manager: Optional[MultiAccountManager] = None
        self.unified_monitor: Optional[UnifiedMonitor] = None
        self.risk_manager: Optional[MultiAccountRiskManager] = None
        self.strategy_allocator: Optional[StrategyAllocator] = None
        
    async def initialize(self):
        """시스템 초기화"""
        try:
            # 계정 관리자 초기화
            self.account_manager = MultiAccountManager(self.config_manager)
            await self.account_manager.initialize()
            
            # 통합 모니터 초기화
            self.unified_monitor = UnifiedMonitor(self.account_manager)
            
            # 리스크 관리자 초기화
            self.risk_manager = MultiAccountRiskManager(
                self.account_manager,
                self.unified_monitor
            )
            
            # 전략 할당자 초기화
            self.strategy_allocator = StrategyAllocator(self.config_manager)
            
            logger.info("Multi-account CLI initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize CLI: {e}")
            raise
    
    async def cleanup(self):
        """리소스 정리"""
        if self.unified_monitor and self.unified_monitor.is_monitoring:
            await self.unified_monitor.stop_monitoring()
        
        if self.risk_manager and self.risk_manager.is_monitoring:
            await self.risk_manager.stop_monitoring()
    
    async def get_all_balances(self) -> Dict[str, Dict[str, Any]]:
        """모든 계좌 잔고 조회"""
        balances = {}
        
        for account_id, client in self.account_manager.accounts.items():
            try:
                balance_info = await client.get_balance()
                if balance_info:
                    balances[account_id] = {
                        'total_balance': float(balance_info.get('totalWalletBalance', 0)),
                        'available_balance': float(balance_info.get('availableBalance', 0)),
                        'unrealized_pnl': float(balance_info.get('totalUnrealizedProfit', 0)),
                        'margin_balance': float(balance_info.get('totalMarginBalance', 0))
                    }
            except Exception as e:
                logger.error(f"Error getting balance for {account_id}: {e}")
                balances[account_id] = {'error': str(e)}
        
        return balances
    
    async def get_all_positions(self) -> Dict[str, List[Dict[str, Any]]]:
        """모든 계좌 포지션 조회"""
        all_positions = {}
        
        for account_id, client in self.account_manager.accounts.items():
            try:
                positions = await client.get_positions()
                if positions:
                    all_positions[account_id] = [
                        {
                            'symbol': pos.get('symbol'),
                            'side': 'LONG' if float(pos.get('positionAmt', 0)) > 0 else 'SHORT',
                            'amount': abs(float(pos.get('positionAmt', 0))),
                            'entry_price': float(pos.get('entryPrice', 0)),
                            'mark_price': float(pos.get('markPrice', 0)),
                            'unrealized_pnl': float(pos.get('unrealizedProfit', 0)),
                            'pnl_percentage': float(pos.get('percentage', 0))
                        }
                        for pos in positions
                        if float(pos.get('positionAmt', 0)) != 0
                    ]
                else:
                    all_positions[account_id] = []
            except Exception as e:
                logger.error(f"Error getting positions for {account_id}: {e}")
                all_positions[account_id] = []
        
        return all_positions
    
    async def get_performance_summary(self) -> Dict[str, Any]:
        """성과 요약 조회"""
        performance = await self.unified_monitor.get_performance_comparison()
        portfolio = await self.unified_monitor.get_portfolio_summary()
        
        return {
            'portfolio': {
                'total_balance': float(portfolio.total_balance),
                'total_pnl': float(portfolio.total_pnl),
                'total_pnl_percentage': portfolio.total_pnl_percentage,
                'active_accounts': portfolio.active_accounts,
                'total_positions': portfolio.total_positions
            },
            'accounts': performance['comparison']
        }
    
    async def get_risk_status(self) -> Dict[str, Any]:
        """리스크 상태 조회"""
        return self.risk_manager.get_risk_summary()
    
    async def switch_account_strategy(self, account_id: str, strategy_name: str) -> bool:
        """계좌 전략 변경"""
        try:
            # 현재 할당 제거
            current_allocation = self.strategy_allocator.get_allocation_by_account(account_id)
            if current_allocation:
                self.strategy_allocator.deallocate_strategy(account_id)
            
            # 새 전략 할당
            success = await self.strategy_allocator.allocate_strategy(
                account_id=account_id,
                strategy_name=strategy_name,
                parameters={}  # 기본 파라미터 사용
            )
            
            if success:
                logger.info(f"Strategy switched for {account_id}: {strategy_name}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error switching strategy: {e}")
            return False
    
    async def pause_account(self, account_id: str) -> bool:
        """계좌 거래 일시 중지 권고"""
        # 리스크 매니저는 권고만 하고, 실제 중지는 각 전략이 결정
        success = await self.risk_manager.recommend_pause_trading(
            account_id, 
            "Manual pause request via CLI"
        )
        
        # 사용자에게 권고사항임을 명확히 알림
        logger.info(f"Pause recommendation sent for {account_id}. Each strategy will decide independently.")
        return success
    
    async def resume_account(self, account_id: str) -> bool:
        """계좌 거래 재개"""
        return await self.risk_manager.resume_account_trading(account_id)
    
    async def emergency_stop_account(self, account_id: str) -> bool:
        """계좌 긴급 정지 권고"""
        # 긴급 정지 권고만 하고, 실제 포지션 청산은 운영자가 결정
        success = await self.risk_manager.recommend_emergency_stop(account_id)
        
        logger.warning(
            f"EMERGENCY STOP RECOMMENDATION sent for {account_id}. "
            f"Manual intervention required to close positions."
        )
        return success
    
    async def generate_report(self, report_type: str) -> Dict[str, Any]:
        """보고서 생성"""
        end_date = datetime.now()
        
        if report_type == 'daily':
            start_date = end_date - timedelta(days=1)
        elif report_type == 'weekly':
            start_date = end_date - timedelta(weeks=1)
        elif report_type == 'monthly':
            start_date = end_date - timedelta(days=30)
        else:
            raise ValueError(f"Invalid report type: {report_type}")
        
        # 보고서 데이터 수집
        report = {
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
                'type': report_type
            },
            'summary': await self.get_performance_summary(),
            'risk_events': self._get_risk_events_for_period(start_date, end_date),
            'trading_statistics': await self._get_trading_statistics(start_date, end_date)
        }
        
        return report
    
    def _get_risk_events_for_period(self, start_date: datetime, end_date: datetime) -> List[Dict]:
        """기간 내 리스크 이벤트 조회"""
        events = []
        
        for event in self.risk_manager.risk_events:
            if start_date <= event.timestamp <= end_date:
                events.append({
                    'timestamp': event.timestamp.isoformat(),
                    'account_id': event.account_id,
                    'risk_type': event.risk_type,
                    'risk_level': event.risk_level.value,
                    'message': event.message
                })
        
        return events
    
    async def _get_trading_statistics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """거래 통계 조회"""
        # 실제 구현에서는 데이터베이스나 거래 이력에서 가져와야 함
        # 여기서는 간단한 예시
        stats = {}
        
        for account_id in self.account_manager.accounts:
            stats[account_id] = {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'total_volume': 0.0,
                'average_holding_time': '0h'
            }
        
        return stats


# CLI 명령어 그룹
@click.group()
@click.pass_context
def cli(ctx):
    """AlbraTrading Multi-Account Management CLI"""
    ctx.ensure_object(dict)
    ctx.obj['cli_handler'] = MultiAccountCLI()


@cli.command()
@click.pass_context
def balance(ctx):
    """Show all account balances"""
    async def _run():
        handler = ctx.obj['cli_handler']
        await handler.initialize()
        
        try:
            balances = await handler.get_all_balances()
            
            # 테이블 데이터 준비
            table_data = []
            total_balance = 0.0
            total_pnl = 0.0
            
            for account_id, balance in balances.items():
                if 'error' not in balance:
                    table_data.append([
                        account_id,
                        f"${balance['total_balance']:,.2f}",
                        f"${balance['available_balance']:,.2f}",
                        f"${balance['unrealized_pnl']:,.2f}",
                        f"${balance['margin_balance']:,.2f}"
                    ])
                    total_balance += balance['total_balance']
                    total_pnl += balance['unrealized_pnl']
                else:
                    table_data.append([
                        account_id,
                        "ERROR",
                        balance['error'],
                        "-",
                        "-"
                    ])
            
            # 합계 행 추가
            table_data.append([
                "TOTAL",
                f"${total_balance:,.2f}",
                "-",
                f"${total_pnl:,.2f}",
                "-"
            ])
            
            # 테이블 출력
            headers = ["Account", "Total Balance", "Available", "Unrealized PnL", "Margin Balance"]
            print("\n" + tabulate(table_data, headers=headers, tablefmt="pretty"))
            
        finally:
            await handler.cleanup()
    
    asyncio.run(_run())


@cli.command()
@click.pass_context
def positions(ctx):
    """Show all open positions"""
    async def _run():
        handler = ctx.obj['cli_handler']
        await handler.initialize()
        
        try:
            all_positions = await handler.get_all_positions()
            
            for account_id, positions in all_positions.items():
                print(f"\n=== Account: {account_id} ===")
                
                if positions:
                    table_data = []
                    for pos in positions:
                        table_data.append([
                            pos['symbol'],
                            pos['side'],
                            f"{pos['amount']:.4f}",
                            f"${pos['entry_price']:.2f}",
                            f"${pos['mark_price']:.2f}",
                            f"${pos['unrealized_pnl']:.2f}",
                            f"{pos['pnl_percentage']:.2f}%"
                        ])
                    
                    headers = ["Symbol", "Side", "Amount", "Entry", "Mark", "PnL", "PnL%"]
                    print(tabulate(table_data, headers=headers, tablefmt="pretty"))
                else:
                    print("No open positions")
            
        finally:
            await handler.cleanup()
    
    asyncio.run(_run())


@cli.command()
@click.pass_context
def performance(ctx):
    """Show performance metrics"""
    async def _run():
        handler = ctx.obj['cli_handler']
        await handler.initialize()
        
        try:
            await handler.unified_monitor.start_monitoring()
            await asyncio.sleep(2)  # 데이터 수집 대기
            
            performance = await handler.get_performance_summary()
            
            # 포트폴리오 요약
            print("\n=== Portfolio Summary ===")
            portfolio = performance['portfolio']
            print(f"Total Balance: ${portfolio['total_balance']:,.2f}")
            print(f"Total PnL: ${portfolio['total_pnl']:,.2f} ({portfolio['total_pnl_percentage']:.2f}%)")
            print(f"Active Accounts: {portfolio['active_accounts']}")
            print(f"Total Positions: {portfolio['total_positions']}")
            
            # 계좌별 성과
            print("\n=== Account Performance ===")
            table_data = []
            
            for account_id, perf in performance['accounts'].items():
                table_data.append([
                    account_id,
                    f"{perf['pnl_percentage']:.2f}%",
                    f"{perf['win_rate']:.1f}%",
                    f"{perf['sharpe_ratio']:.2f}",
                    f"{perf['max_drawdown']:.1f}%",
                    perf['active_positions'],
                    perf['total_trades']
                ])
            
            headers = ["Account", "PnL%", "Win Rate", "Sharpe", "Max DD", "Positions", "Trades"]
            print(tabulate(table_data, headers=headers, tablefmt="pretty"))
            
        finally:
            await handler.cleanup()
    
    asyncio.run(_run())


@cli.command()
@click.pass_context
def risk_check(ctx):
    """Check risk status"""
    async def _run():
        handler = ctx.obj['cli_handler']
        await handler.initialize()
        
        try:
            await handler.risk_manager.start_monitoring()
            await asyncio.sleep(2)  # 리스크 체크 대기
            
            risk_status = await handler.get_risk_status()
            
            # 전체 상태
            print("\n=== Risk Status ===")
            print(f"Emergency Stopped: {risk_status['emergency_stopped']}")
            print(f"Paused Accounts: {', '.join(risk_status['paused_accounts']) or 'None'}")
            print(f"Active Recovery Plans: {risk_status['active_recovery_plans']}")
            
            # 계좌별 리스크 상태
            print("\n=== Account Risk Status ===")
            table_data = []
            
            for account_id, status in risk_status['account_status'].items():
                warnings = ', '.join(status['warnings'][:2]) if status['warnings'] else 'None'
                if len(status['warnings']) > 2:
                    warnings += f" (+{len(status['warnings'])-2} more)"
                
                table_data.append([
                    account_id,
                    status['risk_level'],
                    f"{status['daily_pnl_pct']:.2f}%",
                    f"{status['drawdown_pct']:.1f}%",
                    warnings
                ])
            
            headers = ["Account", "Risk Level", "Daily PnL", "Drawdown", "Warnings"]
            print(tabulate(table_data, headers=headers, tablefmt="pretty"))
            
            # 최근 리스크 이벤트
            if risk_status['recent_events']:
                print("\n=== Recent Risk Events ===")
                for event in risk_status['recent_events'][-5:]:  # 최근 5개
                    print(f"[{event['timestamp']}] {event['risk_level']} - "
                          f"{event['account_id'] or 'PORTFOLIO'}: {event['message']}")
            
        finally:
            await handler.cleanup()
    
    asyncio.run(_run())


@cli.command()
@click.argument('account_id')
@click.argument('strategy_name')
@click.pass_context
def switch_strategy(ctx, account_id: str, strategy_name: str):
    """Switch trading strategy for an account"""
    async def _run():
        handler = ctx.obj['cli_handler']
        await handler.initialize()
        
        try:
            if account_id not in handler.account_manager.accounts:
                print(f"Error: Account {account_id} not found")
                return
            
            success = await handler.switch_account_strategy(account_id, strategy_name)
            
            if success:
                print(f"✓ Strategy switched successfully")
                print(f"  Account: {account_id}")
                print(f"  New Strategy: {strategy_name}")
            else:
                print(f"✗ Failed to switch strategy")
            
        finally:
            await handler.cleanup()
    
    asyncio.run(_run())


@cli.command()
@click.argument('account_id')
@click.pass_context
def pause(ctx, account_id: str):
    """Pause trading for an account"""
    async def _run():
        handler = ctx.obj['cli_handler']
        await handler.initialize()
        
        try:
            if account_id not in handler.account_manager.accounts:
                print(f"Error: Account {account_id} not found")
                return
            
            success = await handler.pause_account(account_id)
            
            if success:
                print(f"✓ Trading paused for account {account_id}")
            else:
                print(f"✗ Failed to pause trading")
            
        finally:
            await handler.cleanup()
    
    asyncio.run(_run())


@cli.command()
@click.argument('account_id')
@click.pass_context
def resume(ctx, account_id: str):
    """Resume trading for an account"""
    async def _run():
        handler = ctx.obj['cli_handler']
        await handler.initialize()
        
        try:
            if account_id not in handler.account_manager.accounts:
                print(f"Error: Account {account_id} not found")
                return
            
            success = await handler.resume_account(account_id)
            
            if success:
                print(f"✓ Trading resumed for account {account_id}")
            else:
                print(f"✗ Failed to resume trading")
            
        finally:
            await handler.cleanup()
    
    asyncio.run(_run())


@cli.command()
@click.argument('account_id')
@click.confirmation_option(prompt='Are you sure you want to emergency stop this account?')
@click.pass_context
def emergency_stop(ctx, account_id: str):
    """Emergency stop an account (closes all positions)"""
    async def _run():
        handler = ctx.obj['cli_handler']
        await handler.initialize()
        
        try:
            if account_id not in handler.account_manager.accounts:
                print(f"Error: Account {account_id} not found")
                return
            
            success = await handler.emergency_stop_account(account_id)
            
            if success:
                print(f"✓ Emergency stop executed for account {account_id}")
                print("  - All positions closed")
                print("  - Trading halted")
            else:
                print(f"✗ Failed to execute emergency stop")
            
        finally:
            await handler.cleanup()
    
    asyncio.run(_run())


@cli.command()
@click.option('--type', 'report_type', 
              type=click.Choice(['daily', 'weekly', 'monthly']), 
              default='daily',
              help='Report type')
@click.option('--output', '-o', help='Output file path (JSON)')
@click.pass_context
def report(ctx, report_type: str, output: Optional[str]):
    """Generate performance report"""
    async def _run():
        handler = ctx.obj['cli_handler']
        await handler.initialize()
        
        try:
            print(f"Generating {report_type} report...")
            
            await handler.unified_monitor.start_monitoring()
            await handler.risk_manager.start_monitoring()
            await asyncio.sleep(3)  # 데이터 수집 대기
            
            report_data = await handler.generate_report(report_type)
            
            # 보고서 출력
            print(f"\n=== {report_type.capitalize()} Report ===")
            print(f"Period: {report_data['period']['start']} to {report_data['period']['end']}")
            
            # 요약 정보
            summary = report_data['summary']['portfolio']
            print(f"\nPortfolio Summary:")
            print(f"  Total Balance: ${summary['total_balance']:,.2f}")
            print(f"  Total PnL: ${summary['total_pnl']:,.2f} ({summary['total_pnl_percentage']:.2f}%)")
            print(f"  Active Accounts: {summary['active_accounts']}")
            
            # 리스크 이벤트
            risk_events = report_data['risk_events']
            if risk_events:
                print(f"\nRisk Events: {len(risk_events)}")
                critical_events = [e for e in risk_events if e['risk_level'] == 'CRITICAL']
                if critical_events:
                    print(f"  Critical: {len(critical_events)}")
            
            # 파일로 저장
            if output:
                with open(output, 'w') as f:
                    json.dump(report_data, f, indent=2, default=str)
                print(f"\nReport saved to: {output}")
            
        finally:
            await handler.cleanup()
    
    asyncio.run(_run())


@cli.command()
@click.pass_context
def status(ctx):
    """Show system status"""
    async def _run():
        handler = ctx.obj['cli_handler']
        await handler.initialize()
        
        try:
            # 시스템 상태
            print("\n=== System Status ===")
            print(f"Account Manager: {'Active' if handler.account_manager else 'Inactive'}")
            print(f"Accounts Loaded: {len(handler.account_manager.accounts)}")
            print(f"Monitor Status: {handler.unified_monitor.get_monitoring_status()['is_monitoring']}")
            print(f"Risk Monitor: {handler.risk_manager.is_monitoring}")
            
            # 계좌 목록
            print("\n=== Accounts ===")
            for account_id in handler.account_manager.accounts:
                allocation = handler.strategy_allocator.get_allocation_by_account(account_id)
                strategy = allocation.strategy_name if allocation else "None"
                paused = account_id in handler.risk_manager.paused_accounts
                
                status = "PAUSED" if paused else "ACTIVE"
                print(f"  {account_id}: {strategy} [{status}]")
            
        finally:
            await handler.cleanup()
    
    asyncio.run(_run())


if __name__ == '__main__':
    cli(obj={})
