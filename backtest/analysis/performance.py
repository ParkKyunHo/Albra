"""
Performance Analysis Module

This module provides comprehensive performance analysis for backtesting results,
including metrics calculation, period analysis, and performance attribution.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd
from dataclasses import dataclass

from ..risk.metrics import RiskCalculator, RiskMetrics


logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics container."""
    # Return metrics
    total_return: float
    annual_return: float
    monthly_return: float
    daily_return: float
    
    # Risk metrics
    volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    
    # Drawdown metrics
    max_drawdown: float
    max_drawdown_duration: int
    average_drawdown: float
    drawdown_frequency: float
    
    # Trade metrics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    expectancy: float
    
    # Efficiency metrics
    total_commission: float
    total_slippage: float
    net_profit: float
    return_on_capital: float
    
    # Time metrics
    time_in_market: float
    avg_holding_period: float
    longest_winning_streak: int
    longest_losing_streak: int


class PerformanceAnalyzer:
    """
    Comprehensive performance analyzer for backtesting results.
    
    This class calculates detailed performance metrics and provides
    various analysis methods for understanding strategy performance.
    """
    
    def __init__(self, risk_free_rate: float = 0.02):
        """
        Initialize performance analyzer.
        
        Args:
            risk_free_rate: Annual risk-free rate
        """
        self.risk_calculator = RiskCalculator(risk_free_rate)
    
    def calculate_metrics(
        self,
        equity_curve: pd.DataFrame,
        trades: pd.DataFrame,
        initial_capital: float
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive performance metrics.
        
        Args:
            equity_curve: DataFrame with equity values over time
            trades: DataFrame with trade history
            initial_capital: Starting capital
            
        Returns:
            Dictionary containing all performance metrics
        """
        # Calculate returns
        returns = self._calculate_returns(equity_curve)
        
        # Risk metrics
        risk_metrics = self.risk_calculator.calculate_metrics(returns, trades)
        
        # Performance metrics
        perf_metrics = self._calculate_performance_metrics(
            equity_curve, trades, initial_capital, returns
        )
        
        # Combine all metrics
        metrics = {
            # Returns
            'total_return': perf_metrics.total_return,
            'annual_return': perf_metrics.annual_return,
            'monthly_return': perf_metrics.monthly_return,
            'daily_return': perf_metrics.daily_return,
            
            # Risk
            'volatility': risk_metrics.volatility,
            'sharpe_ratio': risk_metrics.sharpe_ratio,
            'sortino_ratio': risk_metrics.sortino_ratio,
            'calmar_ratio': risk_metrics.calmar_ratio,
            'max_drawdown': risk_metrics.max_drawdown,
            'var_95': risk_metrics.var_95,
            'cvar_95': risk_metrics.cvar_95,
            
            # Trades
            'total_trades': perf_metrics.total_trades,
            'win_rate': perf_metrics.win_rate,
            'profit_factor': perf_metrics.profit_factor,
            'expectancy': perf_metrics.expectancy,
            'avg_win': perf_metrics.avg_win,
            'avg_loss': perf_metrics.avg_loss,
            
            # Efficiency
            'total_commission': perf_metrics.total_commission,
            'total_slippage': perf_metrics.total_slippage,
            'time_in_market': perf_metrics.time_in_market,
            'avg_holding_period': perf_metrics.avg_holding_period,
            
            # Additional analysis
            'monthly_returns': self._calculate_monthly_returns(equity_curve),
            'annual_returns': self._calculate_annual_returns(equity_curve),
            'rolling_metrics': self._calculate_rolling_metrics(returns),
            'trade_analysis': self._analyze_trades(trades)
        }
        
        return metrics
    
    def _calculate_returns(self, equity_curve: pd.DataFrame) -> pd.Series:
        """Calculate period returns from equity curve."""
        if 'equity' in equity_curve.columns:
            equity = equity_curve['equity']
        else:
            equity = equity_curve.iloc[:, 0]  # Use first column
        
        returns = equity.pct_change().dropna()
        return returns
    
    def _calculate_performance_metrics(
        self,
        equity_curve: pd.DataFrame,
        trades: pd.DataFrame,
        initial_capital: float,
        returns: pd.Series
    ) -> PerformanceMetrics:
        """Calculate detailed performance metrics."""
        
        # Final equity
        final_equity = equity_curve['equity'].iloc[-1]
        
        # Return calculations
        total_return = (final_equity - initial_capital) / initial_capital
        days = (equity_curve.index[-1] - equity_curve.index[0]).days
        annual_return = (1 + total_return) ** (365 / days) - 1 if days > 0 else 0
        monthly_return = (1 + total_return) ** (30 / days) - 1 if days > 0 else 0
        daily_return = returns.mean()
        
        # Drawdown analysis
        drawdowns = self._calculate_drawdown_series(equity_curve['equity'])
        max_drawdown = drawdowns.min()
        avg_drawdown = drawdowns[drawdowns < 0].mean() if len(drawdowns[drawdowns < 0]) > 0 else 0
        drawdown_frequency = len(drawdowns[drawdowns < 0]) / len(drawdowns) if len(drawdowns) > 0 else 0
        
        # Drawdown duration
        max_dd_duration = self._calculate_max_drawdown_duration(drawdowns)
        
        # Trade analysis
        if len(trades) > 0:
            total_trades = len(trades)
            winning_trades = len(trades[trades['pnl'] > 0])
            losing_trades = len(trades[trades['pnl'] < 0])
            win_rate = winning_trades / total_trades * 100
            
            avg_win = trades[trades['pnl'] > 0]['pnl'].mean() if winning_trades > 0 else 0
            avg_loss = abs(trades[trades['pnl'] < 0]['pnl'].mean()) if losing_trades > 0 else 0
            
            gross_profit = trades[trades['pnl'] > 0]['pnl'].sum() if winning_trades > 0 else 0
            gross_loss = abs(trades[trades['pnl'] < 0]['pnl'].sum()) if losing_trades > 0 else 0
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf
            
            expectancy = trades['pnl'].mean()
            
            # Commission and slippage
            total_commission = trades['commission'].sum() if 'commission' in trades else 0
            total_slippage = trades['slippage'].sum() if 'slippage' in trades else 0
            
            # Holding period
            if 'duration' in trades:
                avg_holding_period = trades['duration'].mean()
            else:
                avg_holding_period = 0
            
            # Streaks
            longest_winning_streak = self._calculate_longest_streak(trades['pnl'] > 0)
            longest_losing_streak = self._calculate_longest_streak(trades['pnl'] < 0)
        else:
            # No trades
            total_trades = 0
            winning_trades = 0
            losing_trades = 0
            win_rate = 0
            avg_win = 0
            avg_loss = 0
            profit_factor = 0
            expectancy = 0
            total_commission = 0
            total_slippage = 0
            avg_holding_period = 0
            longest_winning_streak = 0
            longest_losing_streak = 0
        
        # Time in market
        if 'positions_count' in equity_curve:
            time_in_market = (equity_curve['positions_count'] > 0).sum() / len(equity_curve) * 100
        else:
            time_in_market = 0
        
        # Net profit
        net_profit = final_equity - initial_capital
        return_on_capital = net_profit / initial_capital * 100
        
        return PerformanceMetrics(
            total_return=total_return,
            annual_return=annual_return,
            monthly_return=monthly_return,
            daily_return=daily_return,
            volatility=returns.std() * np.sqrt(252),
            sharpe_ratio=self.risk_calculator.calculate_sharpe_ratio(returns),
            sortino_ratio=self.risk_calculator.calculate_sortino_ratio(returns),
            calmar_ratio=self.risk_calculator.calculate_calmar_ratio(returns, abs(max_drawdown)),
            max_drawdown=abs(max_drawdown),
            max_drawdown_duration=max_dd_duration,
            average_drawdown=abs(avg_drawdown),
            drawdown_frequency=drawdown_frequency,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            expectancy=expectancy,
            total_commission=total_commission,
            total_slippage=total_slippage,
            net_profit=net_profit,
            return_on_capital=return_on_capital,
            time_in_market=time_in_market,
            avg_holding_period=avg_holding_period,
            longest_winning_streak=longest_winning_streak,
            longest_losing_streak=longest_losing_streak
        )
    
    def _calculate_drawdown_series(self, equity: pd.Series) -> pd.Series:
        """Calculate drawdown series from equity curve."""
        rolling_max = equity.expanding().max()
        drawdown = (equity - rolling_max) / rolling_max
        return drawdown
    
    def _calculate_max_drawdown_duration(self, drawdowns: pd.Series) -> int:
        """Calculate maximum drawdown duration in periods."""
        in_drawdown = drawdowns < 0
        drawdown_groups = (in_drawdown != in_drawdown.shift()).cumsum()
        drawdown_periods = in_drawdown.groupby(drawdown_groups).sum()
        
        if len(drawdown_periods[drawdown_periods > 0]) > 0:
            return int(drawdown_periods[drawdown_periods > 0].max())
        return 0
    
    def _calculate_longest_streak(self, condition: pd.Series) -> int:
        """Calculate longest streak where condition is True."""
        groups = (condition != condition.shift()).cumsum()
        streak_lengths = condition.groupby(groups).sum()
        
        if len(streak_lengths[streak_lengths > 0]) > 0:
            return int(streak_lengths[streak_lengths > 0].max())
        return 0
    
    def _calculate_monthly_returns(self, equity_curve: pd.DataFrame) -> pd.Series:
        """Calculate monthly returns."""
        monthly_equity = equity_curve['equity'].resample('M').last()
        monthly_returns = monthly_equity.pct_change().dropna()
        return monthly_returns
    
    def _calculate_annual_returns(self, equity_curve: pd.DataFrame) -> pd.Series:
        """Calculate annual returns."""
        annual_equity = equity_curve['equity'].resample('Y').last()
        annual_returns = annual_equity.pct_change().dropna()
        return annual_returns
    
    def _calculate_rolling_metrics(self, returns: pd.Series, window: int = 252) -> Dict[str, pd.Series]:
        """Calculate rolling metrics."""
        rolling_metrics = {}
        
        if len(returns) >= window:
            # Rolling volatility
            rolling_metrics['rolling_volatility'] = returns.rolling(window).std() * np.sqrt(252)
            
            # Rolling Sharpe
            rolling_sharpe = []
            for i in range(window, len(returns) + 1):
                window_returns = returns.iloc[i-window:i]
                sharpe = self.risk_calculator.calculate_sharpe_ratio(window_returns)
                rolling_sharpe.append(sharpe)
            rolling_metrics['rolling_sharpe'] = pd.Series(
                rolling_sharpe, index=returns.index[window-1:]
            )
            
            # Rolling maximum drawdown
            rolling_dd = []
            for i in range(window, len(returns) + 1):
                window_returns = returns.iloc[i-window:i]
                equity = (1 + window_returns).cumprod()
                dd_series = self._calculate_drawdown_series(equity)
                rolling_dd.append(dd_series.min())
            rolling_metrics['rolling_max_drawdown'] = pd.Series(
                rolling_dd, index=returns.index[window-1:]
            )
        
        return rolling_metrics
    
    def _analyze_trades(self, trades: pd.DataFrame) -> Dict[str, Any]:
        """Perform detailed trade analysis."""
        if len(trades) == 0:
            return {}
        
        analysis = {}
        
        # Distribution of returns
        analysis['return_distribution'] = {
            'mean': trades['pnl_percent'].mean() if 'pnl_percent' in trades else 0,
            'std': trades['pnl_percent'].std() if 'pnl_percent' in trades else 0,
            'skew': trades['pnl_percent'].skew() if 'pnl_percent' in trades else 0,
            'kurtosis': trades['pnl_percent'].kurtosis() if 'pnl_percent' in trades else 0
        }
        
        # Trade duration analysis
        if 'duration' in trades:
            analysis['duration_stats'] = {
                'avg_duration': trades['duration'].mean(),
                'min_duration': trades['duration'].min(),
                'max_duration': trades['duration'].max(),
                'winning_avg_duration': trades[trades['pnl'] > 0]['duration'].mean() if len(trades[trades['pnl'] > 0]) > 0 else 0,
                'losing_avg_duration': trades[trades['pnl'] < 0]['duration'].mean() if len(trades[trades['pnl'] < 0]) > 0 else 0
            }
        
        # Best and worst trades
        analysis['best_trade'] = trades.loc[trades['pnl'].idxmax()].to_dict() if len(trades) > 0 else {}
        analysis['worst_trade'] = trades.loc[trades['pnl'].idxmin()].to_dict() if len(trades) > 0 else {}
        
        # Trade frequency by time
        if 'entry_time' in trades:
            trades['hour'] = pd.to_datetime(trades['entry_time']).dt.hour
            trades['weekday'] = pd.to_datetime(trades['entry_time']).dt.dayofweek
            
            analysis['trades_by_hour'] = trades.groupby('hour').size().to_dict()
            analysis['trades_by_weekday'] = trades.groupby('weekday').size().to_dict()
        
        return analysis
    
    def generate_report(self, metrics: Dict[str, Any]) -> str:
        """
        Generate a formatted performance report.
        
        Args:
            metrics: Dictionary of performance metrics
            
        Returns:
            Formatted report string
        """
        report = []
        report.append("=" * 80)
        report.append("BACKTEST PERFORMANCE REPORT")
        report.append("=" * 80)
        
        # Returns
        report.append("\n📈 RETURNS")
        report.append(f"Total Return: {metrics['total_return']:.2%}")
        report.append(f"Annual Return: {metrics['annual_return']:.2%}")
        report.append(f"Monthly Return: {metrics['monthly_return']:.2%}")
        report.append(f"Daily Return: {metrics['daily_return']:.4%}")
        
        # Risk metrics
        report.append("\n📊 RISK METRICS")
        report.append(f"Volatility: {metrics['volatility']:.2%}")
        report.append(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
        report.append(f"Sortino Ratio: {metrics['sortino_ratio']:.2f}")
        report.append(f"Calmar Ratio: {metrics['calmar_ratio']:.2f}")
        report.append(f"Max Drawdown: {metrics['max_drawdown']:.2%}")
        report.append(f"VaR (95%): {metrics['var_95']:.2%}")
        report.append(f"CVaR (95%): {metrics['cvar_95']:.2%}")
        
        # Trade statistics
        report.append("\n📊 TRADE STATISTICS")
        report.append(f"Total Trades: {metrics['total_trades']}")
        report.append(f"Win Rate: {metrics['win_rate']:.1f}%")
        report.append(f"Profit Factor: {metrics['profit_factor']:.2f}")
        report.append(f"Expectancy: ${metrics['expectancy']:.2f}")
        report.append(f"Average Win: ${metrics['avg_win']:.2f}")
        report.append(f"Average Loss: ${metrics['avg_loss']:.2f}")
        
        # Costs
        report.append("\n💰 COSTS")
        report.append(f"Total Commission: ${metrics['total_commission']:.2f}")
        report.append(f"Total Slippage: ${metrics['total_slippage']:.2f}")
        
        # Efficiency
        report.append("\n⚡ EFFICIENCY")
        report.append(f"Time in Market: {metrics['time_in_market']:.1f}%")
        report.append(f"Avg Holding Period: {metrics['avg_holding_period']:.1f} hours")
        
        report.append("\n" + "=" * 80)
        
        return "\n".join(report)