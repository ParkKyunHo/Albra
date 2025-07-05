"""
Risk Metrics Calculation Module

This module provides comprehensive risk metrics calculations including
VaR, CVaR, Sharpe ratio, maximum drawdown, and other risk measures.
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional, List
from scipy import stats
from dataclasses import dataclass


@dataclass
class RiskMetrics:
    """Container for risk metrics."""
    volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_duration: int
    var_95: float
    cvar_95: float
    calmar_ratio: float
    omega_ratio: float
    downside_deviation: float
    win_rate: float
    profit_factor: float
    recovery_factor: float
    risk_reward_ratio: float


class RiskCalculator:
    """
    Calculator for various risk metrics.
    
    This class provides methods to calculate comprehensive risk metrics
    from returns data and trade history.
    """
    
    def __init__(self, risk_free_rate: float = 0.02):
        """
        Initialize risk calculator.
        
        Args:
            risk_free_rate: Annual risk-free rate for Sharpe calculation
        """
        self.risk_free_rate = risk_free_rate
        self.daily_rf_rate = risk_free_rate / 252
    
    def calculate_metrics(
        self,
        returns: pd.Series,
        trades: Optional[pd.DataFrame] = None
    ) -> RiskMetrics:
        """
        Calculate comprehensive risk metrics.
        
        Args:
            returns: Series of returns (daily or period returns)
            trades: Optional DataFrame of trades
            
        Returns:
            RiskMetrics object with calculated values
        """
        # Basic statistics
        volatility = self.calculate_volatility(returns)
        sharpe = self.calculate_sharpe_ratio(returns)
        sortino = self.calculate_sortino_ratio(returns)
        
        # Drawdown metrics
        max_dd, max_dd_duration = self.calculate_max_drawdown(returns)
        
        # Value at Risk
        var_95 = self.calculate_var(returns, confidence=0.95)
        cvar_95 = self.calculate_cvar(returns, confidence=0.95)
        
        # Other ratios
        calmar = self.calculate_calmar_ratio(returns, max_dd)
        omega = self.calculate_omega_ratio(returns)
        downside_dev = self.calculate_downside_deviation(returns)
        
        # Trade-based metrics
        if trades is not None and len(trades) > 0:
            win_rate = self.calculate_win_rate(trades)
            profit_factor = self.calculate_profit_factor(trades)
            recovery_factor = self.calculate_recovery_factor(returns, max_dd)
            risk_reward = self.calculate_risk_reward_ratio(trades)
        else:
            win_rate = 0.0
            profit_factor = 0.0
            recovery_factor = 0.0
            risk_reward = 0.0
        
        return RiskMetrics(
            volatility=volatility,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=max_dd,
            max_drawdown_duration=max_dd_duration,
            var_95=var_95,
            cvar_95=cvar_95,
            calmar_ratio=calmar,
            omega_ratio=omega,
            downside_deviation=downside_dev,
            win_rate=win_rate,
            profit_factor=profit_factor,
            recovery_factor=recovery_factor,
            risk_reward_ratio=risk_reward
        )
    
    def calculate_volatility(self, returns: pd.Series, annualize: bool = True) -> float:
        """
        Calculate volatility (standard deviation of returns).
        
        Args:
            returns: Series of returns
            annualize: Whether to annualize the volatility
            
        Returns:
            Volatility value
        """
        vol = returns.std()
        
        if annualize:
            # Assume daily returns
            vol *= np.sqrt(252)
        
        return vol
    
    def calculate_sharpe_ratio(self, returns: pd.Series) -> float:
        """
        Calculate Sharpe ratio.
        
        Args:
            returns: Series of returns
            
        Returns:
            Sharpe ratio
        """
        excess_returns = returns - self.daily_rf_rate
        
        if returns.std() == 0:
            return 0.0
        
        sharpe = np.sqrt(252) * excess_returns.mean() / returns.std()
        return sharpe
    
    def calculate_sortino_ratio(self, returns: pd.Series) -> float:
        """
        Calculate Sortino ratio (uses downside deviation).
        
        Args:
            returns: Series of returns
            
        Returns:
            Sortino ratio
        """
        excess_returns = returns - self.daily_rf_rate
        downside_returns = returns[returns < 0]
        
        if len(downside_returns) == 0 or downside_returns.std() == 0:
            return 0.0
        
        sortino = np.sqrt(252) * excess_returns.mean() / downside_returns.std()
        return sortino
    
    def calculate_max_drawdown(self, returns: pd.Series) -> Tuple[float, int]:
        """
        Calculate maximum drawdown and duration.
        
        Args:
            returns: Series of returns
            
        Returns:
            Tuple of (max_drawdown, max_duration_in_periods)
        """
        # Calculate cumulative returns
        cum_returns = (1 + returns).cumprod()
        
        # Calculate running maximum
        running_max = cum_returns.expanding().max()
        
        # Calculate drawdown
        drawdown = (cum_returns - running_max) / running_max
        
        # Find maximum drawdown
        max_drawdown = drawdown.min()
        
        # Calculate drawdown duration
        drawdown_start = None
        max_duration = 0
        current_duration = 0
        
        for i, dd in enumerate(drawdown):
            if dd < 0:
                if drawdown_start is None:
                    drawdown_start = i
                current_duration = i - drawdown_start + 1
                max_duration = max(max_duration, current_duration)
            else:
                drawdown_start = None
                current_duration = 0
        
        return abs(max_drawdown), max_duration
    
    def calculate_var(self, returns: pd.Series, confidence: float = 0.95) -> float:
        """
        Calculate Value at Risk (VaR).
        
        Args:
            returns: Series of returns
            confidence: Confidence level (e.g., 0.95 for 95% VaR)
            
        Returns:
            VaR value (positive number representing potential loss)
        """
        var_percentile = (1 - confidence) * 100
        var = np.percentile(returns, var_percentile)
        return abs(var)
    
    def calculate_cvar(self, returns: pd.Series, confidence: float = 0.95) -> float:
        """
        Calculate Conditional Value at Risk (CVaR) or Expected Shortfall.
        
        Args:
            returns: Series of returns
            confidence: Confidence level
            
        Returns:
            CVaR value
        """
        var = self.calculate_var(returns, confidence)
        conditional_returns = returns[returns <= -var]
        
        if len(conditional_returns) == 0:
            return var
        
        cvar = abs(conditional_returns.mean())
        return cvar
    
    def calculate_calmar_ratio(self, returns: pd.Series, max_drawdown: float) -> float:
        """
        Calculate Calmar ratio (annual return / max drawdown).
        
        Args:
            returns: Series of returns
            max_drawdown: Maximum drawdown (as positive number)
            
        Returns:
            Calmar ratio
        """
        if max_drawdown == 0:
            return 0.0
        
        annual_return = (1 + returns).prod() ** (252 / len(returns)) - 1
        calmar = annual_return / max_drawdown
        return calmar
    
    def calculate_omega_ratio(self, returns: pd.Series, threshold: float = 0) -> float:
        """
        Calculate Omega ratio.
        
        Args:
            returns: Series of returns
            threshold: Threshold return (default 0)
            
        Returns:
            Omega ratio
        """
        returns_above = returns[returns > threshold] - threshold
        returns_below = threshold - returns[returns <= threshold]
        
        if returns_below.sum() == 0:
            return np.inf
        
        omega = returns_above.sum() / returns_below.sum()
        return omega
    
    def calculate_downside_deviation(self, returns: pd.Series, threshold: float = 0) -> float:
        """
        Calculate downside deviation.
        
        Args:
            returns: Series of returns
            threshold: Minimum acceptable return
            
        Returns:
            Downside deviation
        """
        downside_returns = returns[returns < threshold]
        
        if len(downside_returns) == 0:
            return 0.0
        
        downside_dev = np.sqrt(np.mean((downside_returns - threshold) ** 2))
        return downside_dev * np.sqrt(252)  # Annualized
    
    def calculate_win_rate(self, trades: pd.DataFrame) -> float:
        """
        Calculate win rate from trades.
        
        Args:
            trades: DataFrame with 'pnl' column
            
        Returns:
            Win rate as percentage
        """
        if len(trades) == 0:
            return 0.0
        
        winning_trades = len(trades[trades['pnl'] > 0])
        total_trades = len(trades)
        
        return (winning_trades / total_trades) * 100
    
    def calculate_profit_factor(self, trades: pd.DataFrame) -> float:
        """
        Calculate profit factor (gross profit / gross loss).
        
        Args:
            trades: DataFrame with 'pnl' column
            
        Returns:
            Profit factor
        """
        if len(trades) == 0:
            return 0.0
        
        gross_profit = trades[trades['pnl'] > 0]['pnl'].sum()
        gross_loss = abs(trades[trades['pnl'] < 0]['pnl'].sum())
        
        if gross_loss == 0:
            return np.inf if gross_profit > 0 else 0.0
        
        return gross_profit / gross_loss
    
    def calculate_recovery_factor(self, returns: pd.Series, max_drawdown: float) -> float:
        """
        Calculate recovery factor (net profit / max drawdown).
        
        Args:
            returns: Series of returns
            max_drawdown: Maximum drawdown
            
        Returns:
            Recovery factor
        """
        if max_drawdown == 0:
            return 0.0
        
        total_return = (1 + returns).prod() - 1
        recovery_factor = total_return / max_drawdown
        
        return recovery_factor
    
    def calculate_risk_reward_ratio(self, trades: pd.DataFrame) -> float:
        """
        Calculate average risk/reward ratio from trades.
        
        Args:
            trades: DataFrame with 'pnl' column
            
        Returns:
            Average risk/reward ratio
        """
        if len(trades) == 0:
            return 0.0
        
        winning_trades = trades[trades['pnl'] > 0]['pnl']
        losing_trades = trades[trades['pnl'] < 0]['pnl']
        
        if len(winning_trades) == 0 or len(losing_trades) == 0:
            return 0.0
        
        avg_win = winning_trades.mean()
        avg_loss = abs(losing_trades.mean())
        
        if avg_loss == 0:
            return np.inf if avg_win > 0 else 0.0
        
        return avg_win / avg_loss
    
    def calculate_tail_ratio(self, returns: pd.Series, percentile: float = 5) -> float:
        """
        Calculate tail ratio (ratio of right tail to left tail).
        
        Args:
            returns: Series of returns
            percentile: Percentile for tail definition
            
        Returns:
            Tail ratio
        """
        right_tail = np.percentile(returns, 100 - percentile)
        left_tail = abs(np.percentile(returns, percentile))
        
        if left_tail == 0:
            return np.inf if right_tail > 0 else 0.0
        
        return right_tail / left_tail
    
    def calculate_information_ratio(
        self,
        returns: pd.Series,
        benchmark_returns: pd.Series
    ) -> float:
        """
        Calculate information ratio.
        
        Args:
            returns: Strategy returns
            benchmark_returns: Benchmark returns
            
        Returns:
            Information ratio
        """
        active_returns = returns - benchmark_returns
        
        if active_returns.std() == 0:
            return 0.0
        
        info_ratio = np.sqrt(252) * active_returns.mean() / active_returns.std()
        return info_ratio