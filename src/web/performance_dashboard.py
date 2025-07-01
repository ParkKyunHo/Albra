"""
Performance Analysis Dashboard
과거 데이터 분석과 전략 성과 비교에 특화된 대시보드
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from flask import Blueprint, jsonify, request
import pandas as pd
import numpy as np
from collections import defaultdict

logger = logging.getLogger(__name__)

class PerformanceDashboard:
    """성과 분석 대시보드"""
    
    def __init__(self, performance_tracker=None, state_manager=None):
        """
        Args:
            performance_tracker: PerformanceTracker 인스턴스
            state_manager: StateManager 인스턴스
        """
        self.performance_tracker = performance_tracker
        self.state_manager = state_manager
        
        # Blueprint 생성
        self.blueprint = Blueprint('performance', __name__, url_prefix='/api/performance')
        self._setup_routes()
        
        logger.info("PerformanceDashboard 초기화 완료")
    
    def _setup_routes(self):
        """API 라우트 설정"""
        
        @self.blueprint.route('/overview')
        def performance_overview():
            """전체 성과 개요"""
            try:
                overview = self._build_performance_overview()
                return jsonify(overview)
            except Exception as e:
                logger.error(f"Performance overview 오류: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.blueprint.route('/strategy/<strategy_name>')
        def strategy_performance(strategy_name):
            """특정 전략 상세 성과"""
            try:
                performance = self._build_strategy_performance(strategy_name)
                return jsonify(performance)
            except Exception as e:
                logger.error(f"Strategy performance 오류: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.blueprint.route('/comparison')
        def strategy_comparison():
            """전략 간 성과 비교"""
            try:
                comparison = self._build_strategy_comparison()
                return jsonify(comparison)
            except Exception as e:
                logger.error(f"Strategy comparison 오류: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.blueprint.route('/returns')
        def returns_analysis():
            """수익률 분석 (일별/주별/월별)"""
            try:
                period = request.args.get('period', 'daily')
                strategy = request.args.get('strategy', None)
                returns = self._build_returns_analysis(period, strategy)
                return jsonify(returns)
            except Exception as e:
                logger.error(f"Returns analysis 오류: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.blueprint.route('/drawdown')
        def drawdown_analysis():
            """MDD 분석"""
            try:
                strategy = request.args.get('strategy', None)
                drawdown = self._build_drawdown_analysis(strategy)
                return jsonify(drawdown)
            except Exception as e:
                logger.error(f"Drawdown analysis 오류: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.blueprint.route('/trades')
        def trades_history():
            """거래 내역"""
            try:
                strategy = request.args.get('strategy', None)
                days = int(request.args.get('days', 30))
                limit = int(request.args.get('limit', 100))
                trades = self._build_trades_history(strategy, days, limit)
                return jsonify(trades)
            except Exception as e:
                logger.error(f"Trades history 오류: {e}")
                return jsonify({'error': str(e)}), 500
    
    def _build_performance_overview(self) -> Dict[str, Any]:
        """전체 성과 개요 빌드"""
        if not self.performance_tracker:
            # Performance tracker가 없어도 빈 데이터 반환
            return {
                'overall': {
                    'start_date': None,
                    'total_trades': 0,
                    'total_strategies': 0,
                    'active_days': 0,
                    'total_pnl': 0,
                    'win_rate': 0,
                    'best_strategy': 'N/A',
                    'worst_strategy': 'N/A'
                },
                'strategies': [],
                'timestamp': datetime.now().isoformat()
            }
        
        overall = self.performance_tracker.overall_stats
        strategies = self.performance_tracker.strategy_stats
        
        # 전략별 요약
        strategy_summaries = []
        for name, stats in strategies.items():
            if stats['total_trades'] > 0:
                strategy_summaries.append({
                    'name': name,
                    'total_trades': stats['total_trades'],
                    'win_rate': round(stats['win_rate'] * 100, 2),
                    'profit_factor': round(stats['profit_factor'], 2),
                    'total_pnl_pct': round(stats['total_pnl_pct'], 2),
                    'sharpe_ratio': round(stats['sharpe_ratio'], 2),
                    'max_drawdown': round(stats['max_drawdown'] * 100, 2),
                    'expectancy': round(stats['expectancy'], 2)
                })
        
        return {
            'overall': {
                'start_date': overall.get('start_date', '').isoformat() if overall.get('start_date') else None,
                'total_trades': overall.get('total_trades', 0),
                'total_strategies': len(strategy_summaries),
                'active_days': overall.get('active_days', 0),
                'total_pnl': round(overall.get('total_pnl', 0), 2),
                'win_rate': round(overall.get('win_rate', 0) * 100, 2),
                'best_strategy': overall.get('best_strategy', ''),
                'worst_strategy': overall.get('worst_strategy', '')
            },
            'strategies': strategy_summaries,
            'timestamp': datetime.now().isoformat()
        }
    
    def _build_strategy_performance(self, strategy_name: str) -> Dict[str, Any]:
        """특정 전략 상세 성과"""
        if not self.performance_tracker:
            return {
                'strategy_name': strategy_name,
                'statistics': {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'win_rate': 0,
                    'profit_factor': 0,
                    'sharpe_ratio': 0,
                    'expectancy': 0,
                    'kelly_fraction': 0,
                    'avg_win': 0,
                    'avg_loss': 0,
                    'max_win': 0,
                    'max_loss': 0,
                    'max_consecutive_wins': 0,
                    'max_consecutive_losses': 0,
                    'current_streak': 0,
                    'max_drawdown': 0,
                    'current_drawdown': 0
                },
                'recent_trades': [],
                'hourly_performance': [],
                'symbol_performance': [],
                'timestamp': datetime.now().isoformat()
            }
        
        stats = self.performance_tracker.strategy_stats.get(strategy_name)
        if not stats:
            return {
                'strategy_name': strategy_name,
                'error': f'Strategy {strategy_name} not found',
                'statistics': {},
                'recent_trades': [],
                'hourly_performance': [],
                'symbol_performance': [],
                'timestamp': datetime.now().isoformat()
            }
        
        # 거래 내역 필터링
        recent_trades = [
            trade for trade in self.performance_tracker.trade_history
            if trade.strategy_name == strategy_name
        ][-20:]  # 최근 20개
        
        # 시간대별 분석
        hourly_performance = defaultdict(lambda: {'count': 0, 'pnl': 0})
        for trade in self.performance_tracker.trade_history:
            if trade.strategy_name == strategy_name:
                hour = trade.entry_time.hour
                hourly_performance[hour]['count'] += 1
                hourly_performance[hour]['pnl'] += trade.pnl_pct
        
        # 심볼별 성과
        symbol_performance = []
        for symbol, count in stats.get('trades_by_symbol', {}).items():
            pnl = stats.get('pnl_by_symbol', {}).get(symbol, 0)
            symbol_performance.append({
                'symbol': symbol,
                'trades': count,
                'total_pnl': round(pnl, 2),
                'avg_pnl': round(pnl / count if count > 0 else 0, 2)
            })
        
        return {
            'strategy_name': strategy_name,
            'statistics': {
                'total_trades': stats['total_trades'],
                'winning_trades': stats['winning_trades'],
                'losing_trades': stats['losing_trades'],
                'win_rate': round(stats['win_rate'] * 100, 2),
                'profit_factor': round(stats['profit_factor'], 2),
                'sharpe_ratio': round(stats['sharpe_ratio'], 2),
                'expectancy': round(stats['expectancy'], 2),
                'kelly_fraction': round(stats['kelly_fraction'] * 100, 2),
                'avg_win': round(stats['avg_win'], 2),
                'avg_loss': round(stats['avg_loss'], 2),
                'max_win': round(stats['max_win'], 2),
                'max_loss': round(stats['max_loss'], 2),
                'max_consecutive_wins': stats['max_consecutive_wins'],
                'max_consecutive_losses': stats['max_consecutive_losses'],
                'current_streak': stats['current_streak'],
                'max_drawdown': round(stats['max_drawdown'] * 100, 2),
                'current_drawdown': round(stats['current_drawdown'] * 100, 2)
            },
            'recent_trades': [
                {
                    'symbol': t.symbol,
                    'side': t.side,
                    'entry_time': t.entry_time.isoformat(),
                    'exit_time': t.exit_time.isoformat(),
                    'pnl_pct': round(t.pnl_pct, 2),
                    'reason': t.reason
                } for t in recent_trades
            ],
            'hourly_performance': [
                {
                    'hour': hour,
                    'trades': data['count'],
                    'avg_pnl': round(data['pnl'] / data['count'] if data['count'] > 0 else 0, 2)
                } for hour, data in sorted(hourly_performance.items())
            ],
            'symbol_performance': sorted(symbol_performance, key=lambda x: x['total_pnl'], reverse=True),
            'timestamp': datetime.now().isoformat()
        }
    
    def _build_strategy_comparison(self) -> Dict[str, Any]:
        """전략 간 성과 비교"""
        if not self.performance_tracker:
            return {
                'strategies': [],
                'rankings': {},
                'timestamp': datetime.now().isoformat()
            }
        
        comparisons = []
        
        for name, stats in self.performance_tracker.strategy_stats.items():
            if stats['total_trades'] > 0:
                comparisons.append({
                    'strategy': name,
                    'metrics': {
                        'trades': stats['total_trades'],
                        'win_rate': round(stats['win_rate'] * 100, 2),
                        'profit_factor': round(stats['profit_factor'], 2),
                        'sharpe_ratio': round(stats['sharpe_ratio'], 2),
                        'total_pnl': round(stats['total_pnl_pct'], 2),
                        'avg_pnl': round(stats['expectancy'], 2),
                        'max_drawdown': round(stats['max_drawdown'] * 100, 2),
                        'kelly_fraction': round(stats['kelly_fraction'] * 100, 2),
                        'consistency': round(stats['win_rate'] * stats['profit_factor'], 2)  # 일관성 지표
                    }
                })
        
        # 메트릭별 랭킹
        rankings = {
            'win_rate': sorted(comparisons, key=lambda x: x['metrics']['win_rate'], reverse=True),
            'profit_factor': sorted(comparisons, key=lambda x: x['metrics']['profit_factor'], reverse=True),
            'total_pnl': sorted(comparisons, key=lambda x: x['metrics']['total_pnl'], reverse=True),
            'sharpe_ratio': sorted(comparisons, key=lambda x: x['metrics']['sharpe_ratio'], reverse=True),
            'consistency': sorted(comparisons, key=lambda x: x['metrics']['consistency'], reverse=True)
        }
        
        return {
            'strategies': comparisons,
            'rankings': {
                metric: [{'rank': i+1, 'strategy': s['strategy'], 'value': s['metrics'][metric]} 
                        for i, s in enumerate(strategies[:5])]  # Top 5
                for metric, strategies in rankings.items()
            },
            'timestamp': datetime.now().isoformat()
        }
    
    def _build_returns_analysis(self, period: str, strategy: Optional[str]) -> Dict[str, Any]:
        """수익률 분석"""
        if not self.performance_tracker:
            return {
                'period': period.capitalize(),
                'strategy': strategy or 'All',
                'returns': [],
                'statistics': {
                    'total_return': 0,
                    'avg_return': 0,
                    'std_dev': 0,
                    'sharpe_ratio': 0,
                    'best_period': 0,
                    'worst_period': 0,
                    'positive_periods': 0,
                    'negative_periods': 0,
                    'win_rate': 0
                },
                'timestamp': datetime.now().isoformat()
            }
        
        # 거래 내역 필터링
        trades = self.performance_tracker.trade_history
        if strategy:
            trades = [t for t in trades if t.strategy_name == strategy]
        
        if not trades:
            return {'error': 'No trades found'}
        
        # DataFrame 생성
        df = pd.DataFrame([{
            'date': t.exit_time.date(),
            'pnl': t.pnl_pct,
            'strategy': t.strategy_name
        } for t in trades])
        
        # 기간별 집계
        if period == 'daily':
            returns = df.groupby('date')['pnl'].agg(['sum', 'count', 'mean'])
            period_label = 'Daily'
        elif period == 'weekly':
            df['week'] = pd.to_datetime(df['date']).dt.to_period('W')
            returns = df.groupby('week')['pnl'].agg(['sum', 'count', 'mean'])
            period_label = 'Weekly'
        else:  # monthly
            df['month'] = pd.to_datetime(df['date']).dt.to_period('M')
            returns = df.groupby('month')['pnl'].agg(['sum', 'count', 'mean'])
            period_label = 'Monthly'
        
        # 누적 수익률 계산
        returns['cumulative'] = returns['sum'].cumsum()
        
        # 결과 포맷팅
        returns_data = []
        for idx, row in returns.iterrows():
            returns_data.append({
                'period': str(idx),
                'return': round(row['sum'], 2),
                'trades': int(row['count']),
                'avg_return': round(row['mean'], 2),
                'cumulative': round(row['cumulative'], 2)
            })
        
        # 통계 계산
        returns_series = returns['sum']
        statistics = {
            'total_return': round(returns_series.sum(), 2),
            'avg_return': round(returns_series.mean(), 2),
            'std_dev': round(returns_series.std(), 2),
            'sharpe_ratio': round(returns_series.mean() / returns_series.std() * np.sqrt(252) 
                                if returns_series.std() > 0 else 0, 2),
            'best_period': round(returns_series.max(), 2),
            'worst_period': round(returns_series.min(), 2),
            'positive_periods': int((returns_series > 0).sum()),
            'negative_periods': int((returns_series < 0).sum()),
            'win_rate': round((returns_series > 0).sum() / len(returns_series) * 100 
                            if len(returns_series) > 0 else 0, 2)
        }
        
        return {
            'period': period_label,
            'strategy': strategy or 'All',
            'returns': returns_data[-30:],  # 최근 30개 기간
            'statistics': statistics,
            'timestamp': datetime.now().isoformat()
        }
    
    def _build_drawdown_analysis(self, strategy: Optional[str]) -> Dict[str, Any]:
        """MDD 분석"""
        if not self.performance_tracker:
            return {
                'strategy': strategy or 'All',
                'current_drawdown': 0,
                'max_drawdown': 0,
                'peak_value': 0,
                'drawdown_periods': [],
                'cumulative_returns': [],
                'statistics': {
                    'total_periods': 0,
                    'avg_duration': 0,
                    'avg_drawdown': 0,
                    'worst_drawdown': 0,
                    'current_underwater': False,
                    'underwater_duration': 0
                },
                'timestamp': datetime.now().isoformat()
            }
        
        # 거래 내역 필터링
        trades = self.performance_tracker.trade_history
        if strategy:
            trades = [t for t in trades if t.strategy_name == strategy]
            stats = self.performance_tracker.strategy_stats.get(strategy, {})
        else:
            stats = self.performance_tracker.overall_stats
        
        if not trades:
            return {'error': 'No trades found'}
        
        # 누적 수익률 계산
        cumulative_returns = []
        cumulative = 0
        peak = 0
        drawdowns = []
        
        for trade in sorted(trades, key=lambda x: x.exit_time):
            cumulative += trade.pnl_pct
            cumulative_returns.append({
                'date': trade.exit_time.isoformat(),
                'cumulative_return': round(cumulative, 2),
                'trade_return': round(trade.pnl_pct, 2)
            })
            
            # Peak 업데이트
            if cumulative > peak:
                peak = cumulative
            
            # Drawdown 계산
            if peak > 0:
                dd = (cumulative - peak) / (100 + peak) * 100
                drawdowns.append({
                    'date': trade.exit_time.isoformat(),
                    'drawdown': round(dd, 2),
                    'peak': round(peak, 2),
                    'current': round(cumulative, 2)
                })
        
        # Drawdown 기간 분석
        dd_periods = []
        in_drawdown = False
        dd_start = None
        dd_peak = 0
        
        for i, dd in enumerate(drawdowns):
            if dd['drawdown'] < 0 and not in_drawdown:
                in_drawdown = True
                dd_start = i
                dd_peak = dd['peak']
            elif dd['drawdown'] >= 0 and in_drawdown:
                in_drawdown = False
                if dd_start is not None:
                    dd_periods.append({
                        'start': drawdowns[dd_start]['date'],
                        'end': dd['date'],
                        'duration_trades': i - dd_start,
                        'max_drawdown': round(min(d['drawdown'] for d in drawdowns[dd_start:i]), 2),
                        'recovery_return': round(dd['current'] - drawdowns[dd_start]['current'], 2)
                    })
        
        # 현재 drawdown 상태
        current_dd = drawdowns[-1] if drawdowns else {'drawdown': 0, 'peak': 0}
        
        return {
            'strategy': strategy or 'All',
            'current_drawdown': round(current_dd['drawdown'], 2),
            'max_drawdown': round(stats.get('max_drawdown', 0) * 100, 2),
            'peak_value': round(current_dd['peak'], 2),
            'drawdown_periods': dd_periods[-5:],  # 최근 5개 DD 기간
            'cumulative_returns': cumulative_returns[-100:],  # 최근 100개 거래
            'statistics': {
                'total_periods': len(dd_periods),
                'avg_duration': round(np.mean([p['duration_trades'] for p in dd_periods]) 
                                    if dd_periods else 0, 1),
                'avg_drawdown': round(np.mean([p['max_drawdown'] for p in dd_periods]) 
                                    if dd_periods else 0, 2),
                'worst_drawdown': round(min([p['max_drawdown'] for p in dd_periods]) 
                                      if dd_periods else 0, 2),
                'current_underwater': in_drawdown,
                'underwater_duration': i - dd_start if in_drawdown and dd_start is not None else 0
            },
            'timestamp': datetime.now().isoformat()
        }
    
    def _build_trades_history(self, strategy: Optional[str], days: int, limit: int) -> Dict[str, Any]:
        """거래 내역"""
        if not self.performance_tracker:
            return {
                'strategy': strategy or 'All',
                'period_days': days,
                'trades': [],
                'summary': {
                    'total_trades': 0,
                    'wins': 0,
                    'losses': 0,
                    'win_rate': 0,
                    'total_pnl': 0,
                    'avg_pnl': 0,
                    'best_trade': 0,
                    'worst_trade': 0
                },
                'timestamp': datetime.now().isoformat()
            }
        
        # 날짜 필터
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # 거래 필터링
        trades = self.performance_tracker.trade_history
        if strategy:
            trades = [t for t in trades if t.strategy_name == strategy]
        
        trades = [t for t in trades if t.exit_time >= cutoff_date]
        trades = sorted(trades, key=lambda x: x.exit_time, reverse=True)[:limit]
        
        # 포맷팅
        trades_data = []
        for trade in trades:
            trades_data.append({
                'id': f"{trade.strategy_name}_{trade.symbol}_{trade.exit_time.timestamp()}",
                'strategy': trade.strategy_name,
                'symbol': trade.symbol,
                'side': trade.side,
                'leverage': trade.leverage,
                'entry_price': round(trade.entry_price, 2),
                'exit_price': round(trade.exit_price, 2),
                'size': round(trade.size, 4),
                'entry_time': trade.entry_time.isoformat(),
                'exit_time': trade.exit_time.isoformat(),
                'duration': str(trade.exit_time - trade.entry_time),
                'pnl_pct': round(trade.pnl_pct, 2),
                'pnl_amount': round(trade.pnl_amount, 2),
                'commission': round(trade.commission, 2),
                'reason': trade.reason,
                'result': 'WIN' if trade.pnl_pct > 0 else 'LOSS'
            })
        
        # 요약 통계
        if trades_data:
            total_pnl = sum(t['pnl_pct'] for t in trades_data)
            wins = [t for t in trades_data if t['result'] == 'WIN']
            losses = [t for t in trades_data if t['result'] == 'LOSS']
            
            summary = {
                'total_trades': len(trades_data),
                'wins': len(wins),
                'losses': len(losses),
                'win_rate': round(len(wins) / len(trades_data) * 100, 2),
                'total_pnl': round(total_pnl, 2),
                'avg_pnl': round(total_pnl / len(trades_data), 2),
                'best_trade': round(max(t['pnl_pct'] for t in trades_data), 2),
                'worst_trade': round(min(t['pnl_pct'] for t in trades_data), 2)
            }
        else:
            summary = {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'avg_pnl': 0,
                'best_trade': 0,
                'worst_trade': 0
            }
        
        return {
            'strategy': strategy or 'All',
            'period_days': days,
            'trades': trades_data,
            'summary': summary,
            'timestamp': datetime.now().isoformat()
        }