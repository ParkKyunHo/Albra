"""
Visualization Module

This module provides comprehensive visualization tools for backtesting results,
including equity curves, drawdown charts, trade analysis, and performance metrics.
"""

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import seaborn as sns
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime


# Set style
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")


class BacktestVisualizer:
    """
    Comprehensive visualization tools for backtest results.
    
    This class provides various plotting methods to visualize
    backtesting performance and analysis.
    """
    
    def __init__(self, figsize: Tuple[int, int] = (15, 10)):
        """
        Initialize visualizer.
        
        Args:
            figsize: Default figure size for plots
        """
        self.figsize = figsize
        self.colors = {
            'profit': '#2ecc71',
            'loss': '#e74c3c',
            'equity': '#3498db',
            'drawdown': '#e74c3c',
            'long': '#2ecc71',
            'short': '#e74c3c',
            'neutral': '#95a5a6'
        }
    
    def plot_backtest_results(
        self,
        results: Dict[str, Any],
        save_path: Optional[str] = None,
        show: bool = True
    ):
        """
        Create comprehensive backtest results visualization.
        
        Args:
            results: Backtest results dictionary
            save_path: Path to save the figure
            show: Whether to display the plot
        """
        fig = plt.figure(figsize=(self.figsize[0], self.figsize[1] * 1.5))
        
        # Create subplots
        gs = fig.add_gridspec(5, 2, height_ratios=[2, 1, 1, 1, 1], hspace=0.3, wspace=0.2)
        
        # 1. Equity curve
        ax1 = fig.add_subplot(gs[0, :])
        self._plot_equity_curve(ax1, results['equity_curve'])
        
        # 2. Drawdown
        ax2 = fig.add_subplot(gs[1, :])
        self._plot_drawdown(ax2, results['equity_curve'])
        
        # 3. Monthly returns heatmap
        ax3 = fig.add_subplot(gs[2, :])
        self._plot_monthly_returns_heatmap(ax3, results.get('monthly_returns', pd.Series()))
        
        # 4. Trade distribution
        ax4 = fig.add_subplot(gs[3, 0])
        self._plot_trade_distribution(ax4, results.get('trades', pd.DataFrame()))
        
        # 5. Win/Loss analysis
        ax5 = fig.add_subplot(gs[3, 1])
        self._plot_win_loss_analysis(ax5, results.get('trades', pd.DataFrame()))
        
        # 6. Performance metrics
        ax6 = fig.add_subplot(gs[4, :])
        self._plot_performance_metrics(ax6, results['metrics'])
        
        # Add title
        fig.suptitle('Backtest Performance Analysis', fontsize=16, y=0.995)
        
        # Adjust layout
        plt.tight_layout()
        
        # Save if requested
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        # Show if requested
        if show:
            plt.show()
        else:
            plt.close()
    
    def plot_equity_curve(
        self,
        equity_curve: pd.DataFrame,
        trades: Optional[pd.DataFrame] = None,
        save_path: Optional[str] = None,
        show: bool = True
    ):
        """
        Plot detailed equity curve with trade markers.
        
        Args:
            equity_curve: DataFrame with equity values
            trades: Optional trades DataFrame for markers
            save_path: Path to save the figure
            show: Whether to display the plot
        """
        fig, ax = plt.subplots(figsize=self.figsize)
        
        # Plot equity curve
        ax.plot(equity_curve.index, equity_curve['equity'], 
                color=self.colors['equity'], linewidth=2, label='Equity')
        
        # Add initial capital line
        if 'equity' in equity_curve.columns:
            initial_capital = equity_curve['equity'].iloc[0]
            ax.axhline(y=initial_capital, color='gray', linestyle='--', 
                      alpha=0.5, label='Initial Capital')
        
        # Add trade markers if provided
        if trades is not None and len(trades) > 0:
            self._add_trade_markers(ax, trades, equity_curve)
        
        # Fill area under curve
        ax.fill_between(equity_curve.index, equity_curve['equity'], 
                       alpha=0.1, color=self.colors['equity'])
        
        # Formatting
        ax.set_title('Equity Curve', fontsize=14, fontweight='bold')
        ax.set_xlabel('Date')
        ax.set_ylabel('Equity ($)')
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3)
        
        # Format x-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        plt.xticks(rotation=45)
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        if show:
            plt.show()
        else:
            plt.close()
    
    def plot_drawdown(
        self,
        equity_curve: pd.DataFrame,
        save_path: Optional[str] = None,
        show: bool = True
    ):
        """
        Plot drawdown chart.
        
        Args:
            equity_curve: DataFrame with equity values
            save_path: Path to save the figure
            show: Whether to display the plot
        """
        fig, ax = plt.subplots(figsize=self.figsize)
        
        # Calculate drawdown
        equity = equity_curve['equity']
        running_max = equity.expanding().max()
        drawdown = (equity - running_max) / running_max * 100
        
        # Plot drawdown
        ax.fill_between(drawdown.index, 0, drawdown, 
                       color=self.colors['drawdown'], alpha=0.7, label='Drawdown')
        ax.plot(drawdown.index, drawdown, 
               color=self.colors['drawdown'], linewidth=1.5)
        
        # Add max drawdown line
        max_dd = drawdown.min()
        max_dd_idx = drawdown.idxmin()
        ax.axhline(y=max_dd, color='red', linestyle='--', 
                  alpha=0.8, label=f'Max DD: {max_dd:.2f}%')
        ax.scatter([max_dd_idx], [max_dd], color='red', s=100, zorder=5)
        
        # Formatting
        ax.set_title('Drawdown Analysis', fontsize=14, fontweight='bold')
        ax.set_xlabel('Date')
        ax.set_ylabel('Drawdown (%)')
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3)
        ax.set_ylim(top=0)
        
        # Format x-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        plt.xticks(rotation=45)
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        if show:
            plt.show()
        else:
            plt.close()
    
    def plot_returns_distribution(
        self,
        returns: pd.Series,
        save_path: Optional[str] = None,
        show: bool = True
    ):
        """
        Plot returns distribution with statistics.
        
        Args:
            returns: Series of returns
            save_path: Path to save the figure
            show: Whether to display the plot
        """
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=self.figsize)
        
        # Histogram
        ax1.hist(returns * 100, bins=50, alpha=0.7, 
                color=self.colors['equity'], edgecolor='black')
        ax1.axvline(x=0, color='red', linestyle='--', alpha=0.5)
        ax1.axvline(x=returns.mean() * 100, color='green', 
                   linestyle='--', alpha=0.8, label=f'Mean: {returns.mean()*100:.2f}%')
        
        ax1.set_title('Returns Distribution', fontsize=12, fontweight='bold')
        ax1.set_xlabel('Return (%)')
        ax1.set_ylabel('Frequency')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Q-Q plot
        from scipy import stats
        stats.probplot(returns, dist="norm", plot=ax2)
        ax2.set_title('Q-Q Plot', fontsize=12, fontweight='bold')
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        if show:
            plt.show()
        else:
            plt.close()
    
    def plot_trade_analysis(
        self,
        trades: pd.DataFrame,
        save_path: Optional[str] = None,
        show: bool = True
    ):
        """
        Create comprehensive trade analysis visualization.
        
        Args:
            trades: DataFrame with trade history
            save_path: Path to save the figure
            show: Whether to display the plot
        """
        if len(trades) == 0:
            print("No trades to analyze")
            return
        
        fig, axes = plt.subplots(2, 2, figsize=self.figsize)
        axes = axes.flatten()
        
        # 1. P&L by trade
        ax = axes[0]
        colors = [self.colors['profit'] if pnl > 0 else self.colors['loss'] 
                 for pnl in trades['pnl']]
        ax.bar(range(len(trades)), trades['pnl'], color=colors, alpha=0.7)
        ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax.set_title('P&L by Trade', fontsize=12, fontweight='bold')
        ax.set_xlabel('Trade Number')
        ax.set_ylabel('P&L ($)')
        ax.grid(True, alpha=0.3)
        
        # 2. Cumulative P&L
        ax = axes[1]
        cum_pnl = trades['pnl'].cumsum()
        ax.plot(cum_pnl.index, cum_pnl.values, 
               color=self.colors['equity'], linewidth=2)
        ax.fill_between(cum_pnl.index, 0, cum_pnl.values, 
                       alpha=0.3, color=self.colors['equity'])
        ax.set_title('Cumulative P&L', fontsize=12, fontweight='bold')
        ax.set_xlabel('Trade Number')
        ax.set_ylabel('Cumulative P&L ($)')
        ax.grid(True, alpha=0.3)
        
        # 3. Win/Loss distribution
        ax = axes[2]
        win_loss_data = pd.DataFrame({
            'Wins': [len(trades[trades['pnl'] > 0])],
            'Losses': [len(trades[trades['pnl'] < 0])]
        })
        win_loss_data.plot(kind='bar', ax=ax, 
                          color=[self.colors['profit'], self.colors['loss']])
        ax.set_title('Win/Loss Distribution', fontsize=12, fontweight='bold')
        ax.set_xticklabels(['Trades'], rotation=0)
        ax.set_ylabel('Count')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # 4. Holding period analysis
        ax = axes[3]
        if 'duration' in trades:
            ax.hist(trades['duration'], bins=30, 
                   color=self.colors['neutral'], alpha=0.7, edgecolor='black')
            ax.axvline(x=trades['duration'].mean(), color='red', 
                      linestyle='--', label=f"Avg: {trades['duration'].mean():.1f}h")
            ax.set_title('Holding Period Distribution', fontsize=12, fontweight='bold')
            ax.set_xlabel('Duration (hours)')
            ax.set_ylabel('Frequency')
            ax.legend()
        else:
            ax.text(0.5, 0.5, 'No duration data', 
                   ha='center', va='center', transform=ax.transAxes)
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        if show:
            plt.show()
        else:
            plt.close()
    
    def _plot_equity_curve(self, ax, equity_curve: pd.DataFrame):
        """Plot equity curve on given axes."""
        ax.plot(equity_curve.index, equity_curve['equity'], 
               color=self.colors['equity'], linewidth=2)
        ax.fill_between(equity_curve.index, equity_curve['equity'], 
                       alpha=0.1, color=self.colors['equity'])
        
        # Add grid
        ax.grid(True, alpha=0.3)
        ax.set_title('Equity Curve', fontsize=12, fontweight='bold')
        ax.set_ylabel('Equity ($)')
        
        # Format dates
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%y-%m'))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    
    def _plot_drawdown(self, ax, equity_curve: pd.DataFrame):
        """Plot drawdown on given axes."""
        equity = equity_curve['equity']
        running_max = equity.expanding().max()
        drawdown = (equity - running_max) / running_max * 100
        
        ax.fill_between(drawdown.index, 0, drawdown, 
                       color=self.colors['drawdown'], alpha=0.7)
        ax.set_title('Drawdown', fontsize=12, fontweight='bold')
        ax.set_ylabel('Drawdown (%)')
        ax.grid(True, alpha=0.3)
        ax.set_ylim(top=0)
        
        # Format dates
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%y-%m'))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    
    def _plot_monthly_returns_heatmap(self, ax, monthly_returns: pd.Series):
        """Plot monthly returns heatmap."""
        if len(monthly_returns) == 0:
            ax.text(0.5, 0.5, 'No monthly data', 
                   ha='center', va='center', transform=ax.transAxes)
            return
        
        # Prepare data for heatmap
        monthly_returns.index = pd.to_datetime(monthly_returns.index)
        pivot_data = pd.DataFrame({
            'Year': monthly_returns.index.year,
            'Month': monthly_returns.index.month,
            'Return': monthly_returns.values * 100
        })
        
        # Create pivot table
        heatmap_data = pivot_data.pivot(index='Month', columns='Year', values='Return')
        
        # Plot heatmap
        sns.heatmap(heatmap_data, annot=True, fmt='.1f', cmap='RdYlGn', 
                   center=0, ax=ax, cbar_kws={'label': 'Return (%)'})
        ax.set_title('Monthly Returns Heatmap', fontsize=12, fontweight='bold')
        ax.set_xlabel('Year')
        ax.set_ylabel('Month')
    
    def _plot_trade_distribution(self, ax, trades: pd.DataFrame):
        """Plot trade P&L distribution."""
        if len(trades) == 0:
            ax.text(0.5, 0.5, 'No trades', 
                   ha='center', va='center', transform=ax.transAxes)
            return
        
        ax.hist(trades['pnl'], bins=30, alpha=0.7, 
               color=self.colors['neutral'], edgecolor='black')
        ax.axvline(x=0, color='red', linestyle='--', alpha=0.5)
        ax.axvline(x=trades['pnl'].mean(), color='green', 
                  linestyle='--', alpha=0.8, 
                  label=f'Mean: ${trades["pnl"].mean():.2f}')
        ax.set_title('Trade P&L Distribution', fontsize=12, fontweight='bold')
        ax.set_xlabel('P&L ($)')
        ax.set_ylabel('Frequency')
        ax.legend()
        ax.grid(True, alpha=0.3)
    
    def _plot_win_loss_analysis(self, ax, trades: pd.DataFrame):
        """Plot win/loss analysis."""
        if len(trades) == 0:
            ax.text(0.5, 0.5, 'No trades', 
                   ha='center', va='center', transform=ax.transAxes)
            return
        
        wins = trades[trades['pnl'] > 0]
        losses = trades[trades['pnl'] < 0]
        
        data = {
            'Count': [len(wins), len(losses)],
            'Avg P&L': [wins['pnl'].mean() if len(wins) > 0 else 0,
                       -losses['pnl'].mean() if len(losses) > 0 else 0]
        }
        
        df = pd.DataFrame(data, index=['Wins', 'Losses'])
        df.plot(kind='bar', ax=ax, color=[self.colors['profit'], self.colors['loss']])
        
        ax.set_title('Win/Loss Analysis', fontsize=12, fontweight='bold')
        ax.set_xticklabels(['Wins', 'Losses'], rotation=0)
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3)
    
    def _plot_performance_metrics(self, ax, metrics: Dict[str, float]):
        """Plot key performance metrics as text."""
        ax.axis('off')
        
        # Prepare metrics text
        metrics_text = [
            f"Total Return: {metrics.get('total_return', 0):.2%}",
            f"Annual Return: {metrics.get('annual_return', 0):.2%}",
            f"Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}",
            f"Max Drawdown: {metrics.get('max_drawdown', 0):.2%}",
            f"Win Rate: {metrics.get('win_rate', 0):.1f}%",
            f"Profit Factor: {metrics.get('profit_factor', 0):.2f}",
            f"Total Trades: {metrics.get('total_trades', 0)}",
            f"Avg Holding Period: {metrics.get('avg_holding_period', 0):.1f}h"
        ]
        
        # Display metrics in columns
        n_cols = 4
        n_rows = len(metrics_text) // n_cols + (1 if len(metrics_text) % n_cols else 0)
        
        for i, metric in enumerate(metrics_text):
            row = i // n_cols
            col = i % n_cols
            x = col / n_cols + 0.05
            y = 1 - (row + 1) / (n_rows + 1)
            ax.text(x, y, metric, fontsize=10, transform=ax.transAxes)
        
        ax.set_title('Performance Summary', fontsize=12, fontweight='bold', y=0.95)
    
    def _add_trade_markers(self, ax, trades: pd.DataFrame, equity_curve: pd.DataFrame):
        """Add trade entry/exit markers to equity curve."""
        for _, trade in trades.iterrows():
            # Entry marker
            if 'entry_time' in trade and pd.notna(trade['entry_time']):
                entry_time = pd.to_datetime(trade['entry_time'])
                if entry_time in equity_curve.index:
                    entry_equity = equity_curve.loc[entry_time, 'equity']
                    color = self.colors['long'] if trade.get('side', '').upper() == 'LONG' else self.colors['short']
                    ax.scatter(entry_time, entry_equity, color=color, 
                             marker='^', s=100, alpha=0.7, zorder=5)
            
            # Exit marker
            if 'exit_time' in trade and pd.notna(trade['exit_time']):
                exit_time = pd.to_datetime(trade['exit_time'])
                if exit_time in equity_curve.index:
                    exit_equity = equity_curve.loc[exit_time, 'equity']
                    color = self.colors['profit'] if trade['pnl'] > 0 else self.colors['loss']
                    ax.scatter(exit_time, exit_equity, color=color, 
                             marker='v', s=100, alpha=0.7, zorder=5)


def plot_backtest_results(results: Dict[str, Any], save_path: Optional[str] = None):
    """
    Convenience function to plot backtest results.
    
    Args:
        results: Backtest results dictionary
        save_path: Optional path to save the figure
    """
    visualizer = BacktestVisualizer()
    visualizer.plot_backtest_results(results, save_path=save_path)