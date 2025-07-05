"""
Walk-Forward Analysis Module

This module provides walk-forward analysis capabilities for robust
strategy validation and parameter optimization.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Callable
import pandas as pd
import numpy as np
from dataclasses import dataclass
import itertools
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

from ..core.engine import Backtest
from ..strategies.base import BaseStrategy


logger = logging.getLogger(__name__)


@dataclass
class WalkForwardWindow:
    """Represents a single walk-forward window."""
    window_id: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    
    def __str__(self) -> str:
        return (f"Window {self.window_id}: "
                f"Train {self.train_start.date()} to {self.train_end.date()}, "
                f"Test {self.test_start.date()} to {self.test_end.date()}")


@dataclass
class WalkForwardResult:
    """Results from a single walk-forward window."""
    window: WalkForwardWindow
    best_params: Dict[str, Any]
    in_sample_metrics: Dict[str, float]
    out_sample_metrics: Dict[str, float]
    efficiency_ratio: float
    overfitting_score: float


class WalkForwardAnalyzer:
    """
    Walk-forward analysis for strategy validation.
    
    This class implements walk-forward analysis to test strategy robustness
    and optimize parameters in a realistic way that avoids overfitting.
    """
    
    def __init__(
        self,
        strategy_class: type,
        symbol: str = 'BTC/USDT',
        timeframe: str = '1h',
        initial_capital: float = 10000,
        commission: float = 0.001,
        slippage: float = 0.001
    ):
        """
        Initialize walk-forward analyzer.
        
        Args:
            strategy_class: Strategy class to analyze
            symbol: Trading symbol
            timeframe: Data timeframe
            initial_capital: Starting capital for each window
            commission: Trading commission
            slippage: Expected slippage
        """
        self.strategy_class = strategy_class
        self.symbol = symbol
        self.timeframe = timeframe
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        
        # Walk-forward parameters
        self.train_period_months = 12
        self.test_period_months = 3
        self.step_months = 3
        
        # Optimization settings
        self.optimization_metric = 'sharpe_ratio'
        self.min_trades = 30  # Minimum trades for valid result
        
        logger.info(f"WalkForwardAnalyzer initialized for {strategy_class.__name__}")
    
    def run_analysis(
        self,
        start_date: str,
        end_date: str,
        param_grid: Dict[str, List[Any]],
        n_jobs: int = -1,
        show_progress: bool = True
    ) -> List[WalkForwardResult]:
        """
        Run walk-forward analysis.
        
        Args:
            start_date: Overall start date (YYYY-MM-DD)
            end_date: Overall end date (YYYY-MM-DD)
            param_grid: Parameter grid for optimization
            n_jobs: Number of parallel jobs (-1 for all CPUs)
            show_progress: Whether to show progress bar
            
        Returns:
            List of walk-forward results
        """
        # Generate windows
        windows = self._generate_windows(start_date, end_date)
        logger.info(f"Generated {len(windows)} walk-forward windows")
        
        # Run walk-forward analysis for each window
        results = []
        
        if show_progress:
            windows_iter = tqdm(windows, desc="Walk-Forward Windows")
        else:
            windows_iter = windows
        
        for window in windows_iter:
            result = self._analyze_window(window, param_grid, n_jobs)
            if result:
                results.append(result)
        
        # Calculate overall statistics
        self._print_summary(results)
        
        return results
    
    def _generate_windows(self, start_date: str, end_date: str) -> List[WalkForwardWindow]:
        """Generate walk-forward windows."""
        windows = []
        
        current_start = pd.to_datetime(start_date)
        overall_end = pd.to_datetime(end_date)
        window_id = 1
        
        while True:
            # Training period
            train_start = current_start
            train_end = train_start + pd.DateOffset(months=self.train_period_months)
            
            # Test period
            test_start = train_end + pd.Timedelta(days=1)
            test_end = test_start + pd.DateOffset(months=self.test_period_months)
            
            # Check if we have enough data
            if test_end > overall_end:
                break
            
            window = WalkForwardWindow(
                window_id=window_id,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end
            )
            windows.append(window)
            
            # Move to next window
            current_start += pd.DateOffset(months=self.step_months)
            window_id += 1
        
        return windows
    
    def _analyze_window(
        self,
        window: WalkForwardWindow,
        param_grid: Dict[str, List[Any]],
        n_jobs: int
    ) -> Optional[WalkForwardResult]:
        """Analyze a single walk-forward window."""
        logger.info(f"Analyzing {window}")
        
        # Optimize on training data
        best_params, in_sample_metrics = self._optimize_parameters(
            window.train_start,
            window.train_end,
            param_grid,
            n_jobs
        )
        
        if best_params is None:
            logger.warning(f"No valid parameters found for {window}")
            return None
        
        # Test on out-of-sample data
        out_sample_metrics = self._test_parameters(
            window.test_start,
            window.test_end,
            best_params
        )
        
        # Calculate efficiency ratio
        efficiency_ratio = self._calculate_efficiency_ratio(
            in_sample_metrics,
            out_sample_metrics
        )
        
        # Calculate overfitting score
        overfitting_score = self._calculate_overfitting_score(
            in_sample_metrics,
            out_sample_metrics
        )
        
        return WalkForwardResult(
            window=window,
            best_params=best_params,
            in_sample_metrics=in_sample_metrics,
            out_sample_metrics=out_sample_metrics,
            efficiency_ratio=efficiency_ratio,
            overfitting_score=overfitting_score
        )
    
    def _optimize_parameters(
        self,
        start_date: datetime,
        end_date: datetime,
        param_grid: Dict[str, List[Any]],
        n_jobs: int
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, float]]:
        """Optimize parameters on training data."""
        # Generate parameter combinations
        param_combinations = list(itertools.product(*param_grid.values()))
        param_names = list(param_grid.keys())
        
        # Prepare tasks
        tasks = []
        for param_values in param_combinations:
            params = dict(zip(param_names, param_values))
            tasks.append((start_date, end_date, params))
        
        # Run backtests in parallel
        results = []
        
        if n_jobs == 1:
            # Sequential execution
            for task in tasks:
                result = self._run_single_backtest(*task)
                if result:
                    results.append(result)
        else:
            # Parallel execution
            with ProcessPoolExecutor(max_workers=n_jobs if n_jobs > 0 else None) as executor:
                futures = [executor.submit(self._run_single_backtest, *task) for task in tasks]
                
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        results.append(result)
        
        # Find best parameters
        if not results:
            return None, {}
        
        # Sort by optimization metric
        results.sort(key=lambda x: x[1].get(self.optimization_metric, -np.inf), reverse=True)
        best_params, best_metrics = results[0]
        
        return best_params, best_metrics
    
    def _test_parameters(
        self,
        start_date: datetime,
        end_date: datetime,
        params: Dict[str, Any]
    ) -> Dict[str, float]:
        """Test parameters on out-of-sample data."""
        _, metrics = self._run_single_backtest(start_date, end_date, params)
        return metrics or {}
    
    def _run_single_backtest(
        self,
        start_date: datetime,
        end_date: datetime,
        params: Dict[str, Any]
    ) -> Optional[Tuple[Dict[str, Any], Dict[str, float]]]:
        """Run a single backtest with given parameters."""
        try:
            # Create strategy with parameters
            strategy = self.strategy_class()
            strategy.set_parameters(params)
            
            # Run backtest
            backtest = Backtest(
                strategy=strategy,
                symbol=self.symbol,
                timeframe=self.timeframe,
                initial_capital=self.initial_capital,
                commission=self.commission,
                slippage=self.slippage
            )
            
            results = backtest.run(
                start_date=start_date.strftime('%Y-%m-%d'),
                end_date=end_date.strftime('%Y-%m-%d'),
                show_progress=False
            )
            
            # Check if we have enough trades
            if results['metrics']['total_trades'] < self.min_trades:
                return None
            
            return params, results['metrics']
            
        except Exception as e:
            logger.error(f"Backtest failed for params {params}: {e}")
            return None
    
    def _calculate_efficiency_ratio(
        self,
        in_sample: Dict[str, float],
        out_sample: Dict[str, float]
    ) -> float:
        """
        Calculate efficiency ratio (out-sample performance / in-sample performance).
        
        A ratio close to 1 indicates good out-of-sample performance.
        """
        in_sample_metric = in_sample.get(self.optimization_metric, 0)
        out_sample_metric = out_sample.get(self.optimization_metric, 0)
        
        if in_sample_metric == 0:
            return 0
        
        return out_sample_metric / in_sample_metric
    
    def _calculate_overfitting_score(
        self,
        in_sample: Dict[str, float],
        out_sample: Dict[str, float]
    ) -> float:
        """
        Calculate overfitting score.
        
        Higher scores indicate more overfitting.
        """
        # Compare multiple metrics
        metrics_to_compare = ['sharpe_ratio', 'total_return', 'win_rate']
        
        scores = []
        for metric in metrics_to_compare:
            in_val = in_sample.get(metric, 0)
            out_val = out_sample.get(metric, 0)
            
            if in_val != 0:
                degradation = 1 - (out_val / in_val)
                scores.append(max(0, degradation))
        
        return np.mean(scores) * 100 if scores else 0
    
    def _print_summary(self, results: List[WalkForwardResult]):
        """Print summary of walk-forward analysis."""
        if not results:
            print("No valid walk-forward results")
            return
        
        print("\n" + "=" * 80)
        print("WALK-FORWARD ANALYSIS SUMMARY")
        print("=" * 80)
        
        # Overall statistics
        efficiency_ratios = [r.efficiency_ratio for r in results]
        overfitting_scores = [r.overfitting_score for r in results]
        
        print(f"\nWindows analyzed: {len(results)}")
        print(f"Average efficiency ratio: {np.mean(efficiency_ratios):.3f}")
        print(f"Average overfitting score: {np.mean(overfitting_scores):.1f}%")
        
        # Consistency check
        positive_oos = sum(1 for r in results if r.out_sample_metrics.get('total_return', 0) > 0)
        consistency = positive_oos / len(results) * 100
        print(f"Out-of-sample win rate: {consistency:.1f}%")
        
        # Best and worst windows
        best_window = max(results, key=lambda r: r.out_sample_metrics.get('total_return', -np.inf))
        worst_window = min(results, key=lambda r: r.out_sample_metrics.get('total_return', np.inf))
        
        print(f"\nBest window: {best_window.window.window_id} "
              f"(Return: {best_window.out_sample_metrics.get('total_return', 0):.2%})")
        print(f"Worst window: {worst_window.window.window_id} "
              f"(Return: {worst_window.out_sample_metrics.get('total_return', 0):.2%})")
        
        # Parameter stability
        print("\nParameter stability:")
        param_counts = {}
        for result in results:
            for param, value in result.best_params.items():
                if param not in param_counts:
                    param_counts[param] = {}
                param_counts[param][str(value)] = param_counts[param].get(str(value), 0) + 1
        
        for param, value_counts in param_counts.items():
            most_common = max(value_counts.items(), key=lambda x: x[1])
            stability = most_common[1] / len(results) * 100
            print(f"  {param}: {most_common[0]} ({stability:.1f}% of windows)")
        
        print("=" * 80)


class WalkForwardOptimizer:
    """
    Advanced walk-forward optimizer with multiple optimization algorithms.
    """
    
    def __init__(self, analyzer: WalkForwardAnalyzer):
        """
        Initialize optimizer.
        
        Args:
            analyzer: WalkForwardAnalyzer instance
        """
        self.analyzer = analyzer
    
    def optimize_genetic(
        self,
        param_ranges: Dict[str, Tuple[float, float]],
        population_size: int = 50,
        generations: int = 20,
        mutation_rate: float = 0.1
    ) -> Dict[str, Any]:
        """
        Optimize parameters using genetic algorithm.
        
        Args:
            param_ranges: Parameter ranges (min, max)
            population_size: Size of population
            generations: Number of generations
            mutation_rate: Mutation probability
            
        Returns:
            Best parameters found
        """
        # Implementation of genetic algorithm
        # This is a placeholder - implement actual GA if needed
        pass
    
    def optimize_bayesian(
        self,
        param_ranges: Dict[str, Tuple[float, float]],
        n_calls: int = 100
    ) -> Dict[str, Any]:
        """
        Optimize parameters using Bayesian optimization.
        
        Args:
            param_ranges: Parameter ranges
            n_calls: Number of optimization iterations
            
        Returns:
            Best parameters found
        """
        # Implementation of Bayesian optimization
        # This is a placeholder - implement actual BO if needed
        pass