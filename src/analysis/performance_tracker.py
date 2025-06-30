"""
Performance Tracker
전략별 성과를 추적하고 분석하는 시스템
Kelly Criterion과 리스크 관리를 위한 통계 제공
"""

import json
import os
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import asyncio
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class TradeResult:
    """거래 결과 데이터"""
    strategy_name: str
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    size: float
    leverage: int
    entry_time: datetime
    exit_time: datetime
    pnl_pct: float
    pnl_amount: float
    commission: float
    reason: str
    
    def to_dict(self) -> Dict:
        data = asdict(self)
        data['entry_time'] = self.entry_time.isoformat()
        data['exit_time'] = self.exit_time.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TradeResult':
        data['entry_time'] = datetime.fromisoformat(data['entry_time'])
        data['exit_time'] = datetime.fromisoformat(data['exit_time'])
        return cls(**data)


class PerformanceTracker:
    """전략 성과 추적기"""
    
    def __init__(self, data_dir: str = "data/performance"):
        """
        Args:
            data_dir: 성과 데이터 저장 디렉토리
        """
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        
        # 메모리 캐시
        self.trade_history: List[TradeResult] = []
        self.strategy_stats: Dict[str, Dict] = defaultdict(lambda: {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0.0,
            'total_pnl_pct': 0.0,
            'max_win': 0.0,
            'max_loss': 0.0,
            'consecutive_wins': 0,
            'consecutive_losses': 0,
            'max_consecutive_wins': 0,
            'max_consecutive_losses': 0,
            'last_trade_won': None,
            'sharpe_ratio': 0.0,
            'win_rate': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'profit_factor': 0.0,
            'expectancy': 0.0,
            'kelly_fraction': 0.0,
            'current_streak': 0,
            'trades_by_symbol': defaultdict(int),
            'pnl_by_symbol': defaultdict(float),
            'trades_by_hour': defaultdict(int),
            'trades_by_day': defaultdict(int),
            'monthly_returns': defaultdict(float),
            'drawdown_history': [],
            'peak_balance': 0.0,
            'current_drawdown': 0.0,
            'max_drawdown': 0.0,
            'recovery_trades': 0,
            'last_update': None
        })
        
        # 전체 통계
        self.overall_stats = {
            'start_date': None,
            'total_trades': 0,
            'total_pnl': 0.0,
            'peak_balance': 0.0,
            'current_drawdown': 0.0,
            'max_drawdown': 0.0,
            'sharpe_ratio': 0.0,
            'sortino_ratio': 0.0,
            'calmar_ratio': 0.0
        }
        
        # 로드 기존 데이터
        self._load_history()
        
        # 자동 저장 태스크
        self._save_task = None
        self._save_interval = 300  # 5분마다 저장
        
        logger.info(f"Performance Tracker 초기화 완료 - 데이터 디렉토리: {data_dir}")
    
    def _load_history(self):
        """저장된 거래 히스토리 로드"""
        try:
            # 거래 히스토리 로드
            history_file = os.path.join(self.data_dir, "trade_history.json")
            if os.path.exists(history_file):
                with open(history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.trade_history = [TradeResult.from_dict(trade) for trade in data['trades']]
                    logger.info(f"거래 히스토리 로드: {len(self.trade_history)}개 거래")
            
            # 통계 로드
            stats_file = os.path.join(self.data_dir, "strategy_stats.json")
            if os.path.exists(stats_file):
                with open(stats_file, 'r', encoding='utf-8') as f:
                    saved_stats = json.load(f)
                    # defaultdict 재구성
                    for strategy, stats in saved_stats.items():
                        self.strategy_stats[strategy].update(stats)
                        # 중첩된 defaultdict 재구성
                        for key in ['trades_by_symbol', 'pnl_by_symbol', 'trades_by_hour', 
                                   'trades_by_day', 'monthly_returns']:
                            if key in stats:
                                self.strategy_stats[strategy][key] = defaultdict(
                                    float if 'pnl' in key or 'returns' in key else int,
                                    stats[key]
                                )
                
                # 통계 재계산으로 검증
                self._recalculate_all_stats()
                
        except Exception as e:
            logger.error(f"히스토리 로드 실패: {e}")
    
    async def start_auto_save(self):
        """자동 저장 시작"""
        self._save_task = asyncio.create_task(self._auto_save_loop())
        logger.info("성과 자동 저장 시작")
    
    async def stop_auto_save(self):
        """자동 저장 중지"""
        if self._save_task:
            self._save_task.cancel()
            await self.save_history()  # 마지막 저장
            logger.info("성과 자동 저장 중지")
    
    async def _auto_save_loop(self):
        """자동 저장 루프"""
        while True:
            try:
                await asyncio.sleep(self._save_interval)
                await self.save_history()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"자동 저장 실패: {e}")
    
    async def record_trade(self, strategy_name: str, symbol: str, side: str,
                          entry_price: float, exit_price: float, size: float,
                          leverage: int, entry_time: datetime, exit_time: datetime,
                          commission: float = 0.0, reason: str = "") -> TradeResult:
        """거래 결과 기록
        
        Args:
            strategy_name: 전략 이름
            symbol: 거래 심볼
            side: LONG/SHORT
            entry_price: 진입가
            exit_price: 청산가
            size: 포지션 크기
            leverage: 레버리지
            entry_time: 진입 시간
            exit_time: 청산 시간
            commission: 수수료
            reason: 청산 사유
            
        Returns:
            거래 결과 객체
        """
        try:
            # PnL 계산
            if side.upper() == 'LONG':
                pnl_pct = ((exit_price - entry_price) / entry_price) * 100
            else:
                pnl_pct = ((entry_price - exit_price) / entry_price) * 100
            
            # 레버리지 적용
            pnl_pct *= leverage
            
            # 금액 계산
            position_value = size * entry_price
            pnl_amount = position_value * (pnl_pct / 100) - commission
            
            # 거래 결과 생성
            trade = TradeResult(
                strategy_name=strategy_name,
                symbol=symbol,
                side=side.upper(),
                entry_price=entry_price,
                exit_price=exit_price,
                size=size,
                leverage=leverage,
                entry_time=entry_time,
                exit_time=exit_time,
                pnl_pct=pnl_pct,
                pnl_amount=pnl_amount,
                commission=commission,
                reason=reason
            )
            
            # 히스토리에 추가
            self.trade_history.append(trade)
            
            # 통계 업데이트
            self._update_strategy_stats(strategy_name, trade)
            
            # 전체 통계 업데이트
            self._update_overall_stats(trade)
            
            logger.info(f"거래 기록: {strategy_name} {symbol} {side} "
                       f"PnL: {pnl_pct:+.2f}% (${pnl_amount:+.2f})")
            
            return trade
            
        except Exception as e:
            logger.error(f"거래 기록 실패: {e}")
            raise
    
    def _update_strategy_stats(self, strategy_name: str, trade: TradeResult):
        """전략별 통계 업데이트"""
        stats = self.strategy_stats[strategy_name]
        
        # 기본 카운트
        stats['total_trades'] += 1
        stats['total_pnl'] += trade.pnl_amount
        stats['total_pnl_pct'] += trade.pnl_pct
        
        # 승/패 구분
        is_win = trade.pnl_pct > 0
        if is_win:
            stats['winning_trades'] += 1
            stats['max_win'] = max(stats['max_win'], trade.pnl_pct)
            
            # 연승 카운트
            if stats['last_trade_won'] is True:
                stats['consecutive_wins'] += 1
            else:
                stats['consecutive_wins'] = 1
            stats['consecutive_losses'] = 0
            
        else:
            stats['losing_trades'] += 1
            stats['max_loss'] = min(stats['max_loss'], trade.pnl_pct)
            
            # 연패 카운트
            if stats['last_trade_won'] is False:
                stats['consecutive_losses'] += 1
            else:
                stats['consecutive_losses'] = 1
            stats['consecutive_wins'] = 0
        
        # 최대 연승/연패 업데이트
        stats['max_consecutive_wins'] = max(stats['max_consecutive_wins'], 
                                           stats['consecutive_wins'])
        stats['max_consecutive_losses'] = max(stats['max_consecutive_losses'], 
                                             stats['consecutive_losses'])
        
        stats['last_trade_won'] = is_win
        stats['current_streak'] = stats['consecutive_wins'] if is_win else -stats['consecutive_losses']
        
        # 심볼별 통계
        stats['trades_by_symbol'][trade.symbol] += 1
        stats['pnl_by_symbol'][trade.symbol] += trade.pnl_pct
        
        # 시간대별 통계
        hour = trade.entry_time.hour
        weekday = trade.entry_time.weekday()
        stats['trades_by_hour'][hour] += 1
        stats['trades_by_day'][weekday] += 1
        
        # 월별 수익
        month_key = trade.exit_time.strftime('%Y-%m')
        stats['monthly_returns'][month_key] += trade.pnl_pct
        
        # 고급 통계 계산
        self._calculate_advanced_stats(strategy_name)
        
        stats['last_update'] = datetime.now().isoformat()
    
    def _calculate_advanced_stats(self, strategy_name: str):
        """고급 통계 계산"""
        stats = self.strategy_stats[strategy_name]
        
        if stats['total_trades'] == 0:
            return
        
        # 승률
        stats['win_rate'] = (stats['winning_trades'] / stats['total_trades']) * 100
        
        # 평균 손익
        if stats['winning_trades'] > 0:
            winning_pnls = [t.pnl_pct for t in self.trade_history 
                           if t.strategy_name == strategy_name and t.pnl_pct > 0]
            stats['avg_win'] = np.mean(winning_pnls) if winning_pnls else 0
        
        if stats['losing_trades'] > 0:
            losing_pnls = [t.pnl_pct for t in self.trade_history 
                          if t.strategy_name == strategy_name and t.pnl_pct <= 0]
            stats['avg_loss'] = np.mean(losing_pnls) if losing_pnls else 0
        
        # Profit Factor
        total_wins = sum(t.pnl_amount for t in self.trade_history 
                        if t.strategy_name == strategy_name and t.pnl_pct > 0)
        total_losses = abs(sum(t.pnl_amount for t in self.trade_history 
                              if t.strategy_name == strategy_name and t.pnl_pct <= 0))
        
        stats['profit_factor'] = total_wins / total_losses if total_losses > 0 else float('inf')
        
        # Expectancy
        stats['expectancy'] = (stats['win_rate'] / 100 * stats['avg_win']) + \
                             ((100 - stats['win_rate']) / 100 * stats['avg_loss'])
        
        # Kelly Criterion
        if stats['avg_loss'] != 0:
            p = stats['win_rate'] / 100  # 승률
            q = 1 - p  # 패율
            b = abs(stats['avg_win'] / stats['avg_loss'])  # 손익비
            
            kelly = (p * b - q) / b if b > 0 else 0
            stats['kelly_fraction'] = max(0, min(kelly, 0.25))  # 최대 25%로 제한
        
        # Sharpe Ratio (간단 버전)
        returns = [t.pnl_pct for t in self.trade_history 
                  if t.strategy_name == strategy_name]
        
        if len(returns) > 1:
            returns_series = pd.Series(returns)
            stats['sharpe_ratio'] = (returns_series.mean() / returns_series.std() * np.sqrt(252)) \
                                   if returns_series.std() > 0 else 0
        
        # Drawdown 계산
        self._calculate_drawdown(strategy_name)
    
    def _calculate_drawdown(self, strategy_name: str):
        """드로우다운 계산"""
        stats = self.strategy_stats[strategy_name]
        
        # 누적 수익 곡선
        strategy_trades = [t for t in self.trade_history if t.strategy_name == strategy_name]
        if not strategy_trades:
            return
        
        cumulative_returns = []
        cumsum = 0
        for trade in strategy_trades:
            cumsum += trade.pnl_pct
            cumulative_returns.append(cumsum)
        
        # Peak와 Drawdown 계산
        peak = 0
        max_dd = 0
        current_dd = 0
        
        for ret in cumulative_returns:
            if ret > peak:
                peak = ret
            
            dd = (peak - ret) / peak * 100 if peak > 0 else 0
            current_dd = dd
            max_dd = max(max_dd, dd)
        
        stats['peak_balance'] = peak
        stats['current_drawdown'] = current_dd
        stats['max_drawdown'] = max_dd
    
    def _update_overall_stats(self, trade: TradeResult):
        """전체 통계 업데이트"""
        if self.overall_stats['start_date'] is None:
            self.overall_stats['start_date'] = trade.entry_time
        
        self.overall_stats['total_trades'] += 1
        self.overall_stats['total_pnl'] += trade.pnl_amount
        
        # 전체 Sharpe, Sortino 등은 주기적으로 계산
    
    def get_strategy_performance(self, strategy_name: str, lookback_days: Optional[int] = None) -> Dict:
        """전략 성과 조회
        
        Args:
            strategy_name: 전략 이름
            lookback_days: 조회 기간 (일)
            
        Returns:
            성과 통계
        """
        if strategy_name not in self.strategy_stats:
            return {}
        
        stats = self.strategy_stats[strategy_name].copy()
        
        # lookback_days가 지정된 경우 필터링
        if lookback_days:
            cutoff_date = datetime.now() - timedelta(days=lookback_days)
            recent_trades = [t for t in self.trade_history 
                           if t.strategy_name == strategy_name and t.exit_time >= cutoff_date]
            
            if recent_trades:
                # 기간별 통계 재계산
                period_stats = self._calculate_period_stats(recent_trades)
                stats['period_stats'] = period_stats
        
        return stats
    
    def _calculate_period_stats(self, trades: List[TradeResult]) -> Dict:
        """특정 기간 통계 계산"""
        if not trades:
            return {}
        
        wins = [t for t in trades if t.pnl_pct > 0]
        losses = [t for t in trades if t.pnl_pct <= 0]
        
        return {
            'total_trades': len(trades),
            'win_rate': (len(wins) / len(trades) * 100) if trades else 0,
            'avg_win': np.mean([t.pnl_pct for t in wins]) if wins else 0,
            'avg_loss': np.mean([t.pnl_pct for t in losses]) if losses else 0,
            'total_pnl': sum(t.pnl_pct for t in trades),
            'best_trade': max(t.pnl_pct for t in trades) if trades else 0,
            'worst_trade': min(t.pnl_pct for t in trades) if trades else 0,
            'avg_trade_duration': np.mean([(t.exit_time - t.entry_time).total_seconds() / 3600 
                                          for t in trades])  # 시간
        }
    
    def get_kelly_parameters(self, strategy_name: str) -> Dict[str, float]:
        """Kelly Criterion 파라미터 반환
        
        Returns:
            win_rate, avg_win, avg_loss, kelly_fraction
        """
        stats = self.strategy_stats.get(strategy_name, {})
        
        return {
            'win_rate': stats.get('win_rate', 50) / 100,  # 비율로 변환
            'avg_win': stats.get('avg_win', 2.0),
            'avg_loss': stats.get('avg_loss', -1.0),
            'kelly_fraction': stats.get('kelly_fraction', 0.25),
            'recommended_size': stats.get('kelly_fraction', 0.25) * 100  # 퍼센트
        }
    
    def get_symbol_performance(self, symbol: str) -> Dict:
        """심볼별 성과 조회"""
        symbol_stats = {
            'total_trades': 0,
            'total_pnl': 0.0,
            'win_rate': 0.0,
            'by_strategy': {}
        }
        
        symbol_trades = [t for t in self.trade_history if t.symbol == symbol]
        if not symbol_trades:
            return symbol_stats
        
        wins = [t for t in symbol_trades if t.pnl_pct > 0]
        
        symbol_stats['total_trades'] = len(symbol_trades)
        symbol_stats['total_pnl'] = sum(t.pnl_pct for t in symbol_trades)
        symbol_stats['win_rate'] = (len(wins) / len(symbol_trades) * 100) if symbol_trades else 0
        
        # 전략별 분석
        for strategy in set(t.strategy_name for t in symbol_trades):
            strategy_symbol_trades = [t for t in symbol_trades if t.strategy_name == strategy]
            strategy_wins = [t for t in strategy_symbol_trades if t.pnl_pct > 0]
            
            symbol_stats['by_strategy'][strategy] = {
                'trades': len(strategy_symbol_trades),
                'pnl': sum(t.pnl_pct for t in strategy_symbol_trades),
                'win_rate': (len(strategy_wins) / len(strategy_symbol_trades) * 100) 
                           if strategy_symbol_trades else 0
            }
        
        return symbol_stats
    
    def get_time_analysis(self) -> Dict:
        """시간대별 성과 분석"""
        analysis = {
            'by_hour': defaultdict(lambda: {'trades': 0, 'pnl': 0.0, 'win_rate': 0.0}),
            'by_day': defaultdict(lambda: {'trades': 0, 'pnl': 0.0, 'win_rate': 0.0}),
            'by_month': defaultdict(lambda: {'trades': 0, 'pnl': 0.0, 'win_rate': 0.0})
        }
        
        # 시간대별
        for hour in range(24):
            hour_trades = [t for t in self.trade_history if t.entry_time.hour == hour]
            if hour_trades:
                wins = [t for t in hour_trades if t.pnl_pct > 0]
                analysis['by_hour'][hour] = {
                    'trades': len(hour_trades),
                    'pnl': sum(t.pnl_pct for t in hour_trades),
                    'win_rate': (len(wins) / len(hour_trades) * 100)
                }
        
        # 요일별
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        for day in range(7):
            day_trades = [t for t in self.trade_history if t.entry_time.weekday() == day]
            if day_trades:
                wins = [t for t in day_trades if t.pnl_pct > 0]
                analysis['by_day'][day_names[day]] = {
                    'trades': len(day_trades),
                    'pnl': sum(t.pnl_pct for t in day_trades),
                    'win_rate': (len(wins) / len(day_trades) * 100)
                }
        
        return analysis
    
    def export_to_dataframe(self, strategy_name: Optional[str] = None) -> pd.DataFrame:
        """거래 히스토리를 DataFrame으로 내보내기"""
        trades = self.trade_history
        if strategy_name:
            trades = [t for t in trades if t.strategy_name == strategy_name]
        
        if not trades:
            return pd.DataFrame()
        
        data = [t.to_dict() for t in trades]
        df = pd.DataFrame(data)
        
        # 시간 컬럼 변환
        df['entry_time'] = pd.to_datetime(df['entry_time'])
        df['exit_time'] = pd.to_datetime(df['exit_time'])
        
        # 추가 컬럼
        df['duration_hours'] = (df['exit_time'] - df['entry_time']).dt.total_seconds() / 3600
        df['entry_hour'] = df['entry_time'].dt.hour
        df['entry_day'] = df['entry_time'].dt.day_name()
        df['month'] = df['exit_time'].dt.to_period('M')
        
        return df
    
    async def save_history(self):
        """거래 히스토리와 통계 저장"""
        try:
            # 거래 히스토리 저장
            history_file = os.path.join(self.data_dir, "trade_history.json")
            history_data = {
                'last_update': datetime.now().isoformat(),
                'total_trades': len(self.trade_history),
                'trades': [t.to_dict() for t in self.trade_history]
            }
            
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history_data, f, indent=2, ensure_ascii=False)
            
            # 전략별 통계 저장
            stats_file = os.path.join(self.data_dir, "strategy_stats.json")
            
            # defaultdict를 일반 dict로 변환
            stats_data = {}
            for strategy, stats in self.strategy_stats.items():
                stats_copy = stats.copy()
                # defaultdict 변환
                for key in ['trades_by_symbol', 'pnl_by_symbol', 'trades_by_hour', 
                           'trades_by_day', 'monthly_returns']:
                    if key in stats_copy and isinstance(stats_copy[key], defaultdict):
                        stats_copy[key] = dict(stats_copy[key])
                stats_data[strategy] = stats_copy
            
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(stats_data, f, indent=2, ensure_ascii=False)
            
            # CSV 내보내기 (분석용)
            df = self.export_to_dataframe()
            if not df.empty:
                csv_file = os.path.join(self.data_dir, "trade_history.csv")
                df.to_csv(csv_file, index=False)
            
            logger.debug(f"성과 데이터 저장 완료: {len(self.trade_history)}개 거래")
            
        except Exception as e:
            logger.error(f"성과 데이터 저장 실패: {e}")
    
    def _recalculate_all_stats(self):
        """모든 통계 재계산 (검증용)"""
        # 기존 통계 백업
        backup_stats = self.strategy_stats.copy()
        
        # 초기화
        self.strategy_stats.clear()
        
        # 재계산
        for trade in self.trade_history:
            self._update_strategy_stats(trade.strategy_name, trade)
        
        logger.info("전체 통계 재계산 완료")
    
    def get_recovery_status(self, strategy_name: str) -> Dict:
        """MDD 회복 상태 조회"""
        stats = self.strategy_stats.get(strategy_name, {})
        
        return {
            'current_drawdown': stats.get('current_drawdown', 0),
            'max_drawdown': stats.get('max_drawdown', 0),
            'consecutive_wins': stats.get('consecutive_wins', 0),
            'recovery_progress': (1 - stats.get('current_drawdown', 0) / 
                                stats.get('max_drawdown', 1)) * 100 if stats.get('max_drawdown', 0) > 0 else 100
        }


    def get_recent_trades(self, strategy: str, limit: int = 100) -> List[TradeResult]:
        """최근 거래 조회"""
        strategy_trades = [t for t in self.trade_history if t.strategy_name == strategy]
        strategy_trades.sort(key=lambda x: x.exit_time, reverse=True)
        return strategy_trades[:limit] if len(strategy_trades) > limit else strategy_trades

    async def get_performance_metrics(self, strategy: str) -> Optional[object]:
        """성과 지표 조회"""
        stats = self.get_strategy_performance(strategy)
        if not stats:
            return None
        
        from types import SimpleNamespace
        return SimpleNamespace(
            sharpe_ratio=stats.get('sharpe_ratio', 0),
            win_rate=stats.get('win_rate', 0) / 100,
            profit_factor=stats.get('profit_factor', 1.0),
            expectancy=stats.get('expectancy', 0),
            kelly_fraction=stats.get('kelly_fraction', 0.25),
            max_drawdown=stats.get('max_drawdown', 0),
            current_drawdown=stats.get('current_drawdown', 0),
            total_trades=stats.get('total_trades', 0),
            winning_trades=stats.get('winning_trades', 0),
            losing_trades=stats.get('losing_trades', 0),
            avg_win=stats.get('avg_win', 0),
            avg_loss=stats.get('avg_loss', 0),
            consecutive_wins=stats.get('consecutive_wins', 0),
            consecutive_losses=stats.get('consecutive_losses', 0)
        )

    def get_daily_returns(self, strategy: str, days: int = 30) -> pd.Series:
        """일별 수익률 시계열 반환"""
        cutoff_date = datetime.now() - timedelta(days=days)
        trades = [t for t in self.trade_history 
                  if t.strategy_name == strategy and t.exit_time >= cutoff_date]
        
        daily_pnl = {}
        for trade in trades:
            date = trade.exit_time.date()
            if date not in daily_pnl:
                daily_pnl[date] = 0
            daily_pnl[date] += trade.pnl_pct / 100
        
        if daily_pnl:
            series = pd.Series(daily_pnl)
            series.index = pd.to_datetime(series.index)
            date_range = pd.date_range(start=cutoff_date.date(), end=datetime.now().date(), freq='D')
            series = series.reindex(date_range, fill_value=0)
            return series
        else:
            return pd.Series(dtype=float)

    def calculate_strategy_volatility(self, strategy: str, lookback_days: int = 60) -> float:
        """전략 변동성 계산"""
        daily_returns = self.get_daily_returns(strategy, lookback_days)
        if len(daily_returns) > 1:
            return daily_returns.std() * np.sqrt(252)
        else:
            return 0.2


# 전역 인스턴스
_performance_tracker = None

def get_performance_tracker() -> PerformanceTracker:
    """싱글톤 성과 추적기 반환"""
    global _performance_tracker
    if _performance_tracker is None:
        _performance_tracker = PerformanceTracker()
    return _performance_tracker
