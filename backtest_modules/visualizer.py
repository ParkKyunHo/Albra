# backtest_modules/visualizer.py
"""백테스트 결과 시각화 모듈"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import seaborn as sns
from typing import Dict, List


class Visualizer:
    """백테스트 결과 시각화 클래스"""
    
    def __init__(self, params: dict):
        self.params = params
        # Set matplotlib style
        plt.style.use('seaborn-v0_8-darkgrid')
        plt.rcParams['font.family'] = 'DejaVu Sans'
    
    def visualize_results_with_mdd(self, results: Dict, analysis: Dict, period_name: str, 
                                  df_15m: pd.DataFrame, initial_capital: float):
        """개선된 MDD 시각화"""
        equity_df = results['equity_df']
        trades_df = results['trades_df']
        mdd_df = results['mdd_df']
        
        # Create figure
        fig = plt.figure(figsize=(20, 16))
        
        # 1. Price and trades (top)
        ax1 = plt.subplot(5, 1, 1)
        
        # Plot price
        price_data = df_15m['close'].resample('4H').last()
        ax1.plot(price_data.index, price_data.values, 'k-', linewidth=0.8, alpha=0.7, label='BTC Price')
        
        # Mark trades with color coding by MDD level
        mdd_colors = {0: 'green', 1: 'yellow', 2: 'orange', 3: 'red', 4: 'darkred'}
        for _, trade in trades_df.iterrows():
            mdd_level = trade.get('mdd_level', 0)
            color = mdd_colors.get(mdd_level, 'blue')
            marker = '^' if trade['direction'] == 'long' else 'v'
            
            # Entry
            ax1.scatter(trade['entry_time'], trade['entry_price'], 
                       marker=marker, s=100, c=color, zorder=5, edgecolors='black')
            
            # Exit
            exit_color = 'green' if trade['net_pnl_pct'] > 0 else 'red'
            ax1.scatter(trade['exit_time'], trade['exit_price'], 
                       marker='o', s=80, c=exit_color, zorder=5)
        
        ax1.set_title(f'{period_name} - Price and Trades (Color = MDD Level)', fontsize=14, fontweight='bold')
        ax1.set_ylabel('Price (USDT)')
        ax1.grid(True, alpha=0.3)
        
        # 2. Equity curve (second)
        ax2 = plt.subplot(5, 1, 2)
        ax2.plot(equity_df['time'], equity_df['capital'], 'b-', linewidth=2, label='Capital')
        ax2.axhline(y=initial_capital, color='black', linestyle='--', alpha=0.5)
        
        # Mark MDD events
        for event in results.get('mdd_events', []):
            if event['type'] == 'mdd_restriction_start':
                ax2.axvline(x=event.get('time', equity_df['time'].iloc[0]), 
                          color='red', linestyle='--', alpha=0.7, label=f'MDD Level {event["level"]}')
            elif event['type'] == 'mdd_recovered':
                ax2.axvline(x=event.get('time', equity_df['time'].iloc[0]), 
                          color='green', linestyle='--', alpha=0.7, label='MDD Recovered')
        
        ax2.set_title('Equity Curve', fontsize=14, fontweight='bold')
        ax2.set_ylabel('Capital ($)')
        ax2.grid(True, alpha=0.3)
        ax2.legend()
        
        # 3. MDD chart with levels (third)
        ax3 = plt.subplot(5, 1, 3)
        
        # Fill areas for different MDD levels
        ax3.fill_between(mdd_df['time'], 0, mdd_df['mdd'], 
                        where=(mdd_df['mdd'] <= self.params['mdd_level_1']), 
                        color='lightgreen', alpha=0.5, label='Normal (100% size)')
        ax3.fill_between(mdd_df['time'], self.params['mdd_level_1'], mdd_df['mdd'], 
                        where=(mdd_df['mdd'] > self.params['mdd_level_1']) & (mdd_df['mdd'] <= self.params['mdd_level_2']), 
                        color='yellow', alpha=0.5, label='Level 1: 30-35% (70% size)')
        ax3.fill_between(mdd_df['time'], self.params['mdd_level_2'], mdd_df['mdd'], 
                        where=(mdd_df['mdd'] > self.params['mdd_level_2']) & (mdd_df['mdd'] <= self.params['mdd_level_3']), 
                        color='orange', alpha=0.5, label='Level 2: 35-40% (50% size)')
        ax3.fill_between(mdd_df['time'], self.params['mdd_level_3'], mdd_df['mdd'], 
                        where=(mdd_df['mdd'] > self.params['mdd_level_3']), 
                        color='red', alpha=0.5, label='Level 3: >40% (30% size)')
        
        ax3.plot(mdd_df['time'], mdd_df['mdd'], 'k-', linewidth=1.5)
        
        # Draw level lines
        ax3.axhline(y=self.params['mdd_level_1'], color='yellow', linestyle='--', linewidth=1)
        ax3.axhline(y=self.params['mdd_level_2'], color='orange', linestyle='--', linewidth=1)
        ax3.axhline(y=self.params['mdd_level_3'], color='red', linestyle='--', linewidth=2)
        
        ax3.set_title('Maximum Drawdown (MDD) with Position Size Levels', fontsize=14, fontweight='bold')
        ax3.set_ylabel('MDD (%)')
        ax3.set_ylim(0, max(mdd_df['mdd'].max() * 1.1, self.params['mdd_level_3'] * 1.2))
        ax3.grid(True, alpha=0.3)
        ax3.legend()
        
        # 4. Position size multiplier over time
        ax4 = plt.subplot(5, 1, 4)
        ax4.plot(equity_df['time'], equity_df['position_size_multiplier'] * 100, 'purple', linewidth=2)
        ax4.fill_between(equity_df['time'], 0, equity_df['position_size_multiplier'] * 100, 
                        alpha=0.3, color='purple')
        ax4.axhline(y=100, color='black', linestyle='--', alpha=0.5)
        ax4.set_title('Position Size Multiplier Over Time', fontsize=14, fontweight='bold')
        ax4.set_ylabel('Size (%)')
        ax4.set_ylim(0, 110)
        ax4.grid(True, alpha=0.3)
        
        # 5. Statistics panel (bottom)
        ax5 = plt.subplot(5, 1, 5)
        ax5.axis('off')
        
        # Create detailed statistics text
        mdd_level_stats = ""
        for level, stats in analysis['mdd_stats']['mdd_level_trades'].items():
            mdd_level_stats += f"    {level}: {stats['count']} trades, Win Rate: {stats['win_rate']:.1f}%, Avg Return: {stats['avg_return']:.2f}%\n"
        
        stats_text = f"""
Period: {period_name}
{'='*80}
Performance Metrics:
  Total Return: {results['total_return']:.2f}%
  Total Trades: {analysis['total_trades']}
  Win Rate: {analysis['win_rate']:.1f}%
  Profit Factor: {analysis['profit_factor']:.2f}
  Sharpe Ratio: {analysis['sharpe_ratio']:.2f}
  
MDD Management Statistics:
  Maximum MDD: {analysis['mdd_stats']['max_mdd']:.1f}%
  Average MDD: {analysis['mdd_stats']['avg_mdd']:.1f}%
  Time in MDD Level 1 (>30%): {analysis['mdd_stats']['time_in_mdd_level_1']:.1f}%
  Time in MDD Level 2 (>35%): {analysis['mdd_stats']['time_in_mdd_level_2']:.1f}%
  Time in MDD Level 3 (>40%): {analysis['mdd_stats']['time_in_mdd_level_3']:.1f}%
  Time without Position: {analysis['mdd_stats']['time_without_position']:.1f}%
  Trades with Reduced Size: {analysis['mdd_stats']['trades_with_reduced_size']}
  
Trade Analysis by MDD Level:
{mdd_level_stats}
  
Direction Analysis:
  Long Trades: {analysis['long_trades']} (Win Rate: {analysis['long_win_rate']:.1f}%)
  Short Trades: {analysis['short_trades']} (Win Rate: {analysis['short_win_rate']:.1f}%)
"""
        
        ax5.text(0.05, 0.95, stats_text, transform=ax5.transAxes, 
                fontsize=9, verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        plt.tight_layout()
        plt.show()
    
    def create_comparison_chart(self, all_results: List[Dict]):
        """개선된 MDD 관리 효과 비교"""
        fig, axes = plt.subplots(3, 3, figsize=(20, 12))
        fig.suptitle('Improved MDD Management Performance Analysis', fontsize=16)
        
        periods = [r['period_name'] for r in all_results]
        returns = [r['results']['total_return'] for r in all_results]
        max_mdds = [r['analysis']['mdd_stats']['max_mdd'] for r in all_results]
        win_rates = [r['analysis']['win_rate'] for r in all_results]
        trades_reduced = [r['analysis']['mdd_stats']['trades_with_reduced_size'] for r in all_results]
        time_mdd_40 = [r['analysis']['mdd_stats']['time_in_mdd_level_3'] for r in all_results]
        sharpe_ratios = [r['analysis']['sharpe_ratio'] for r in all_results]
        total_trades = [r['analysis']['total_trades'] for r in all_results]
        
        # 1. Returns comparison
        ax1 = axes[0, 0]
        x = np.arange(len(periods))
        ax1.bar(x, returns, color=['green' if r > 0 else 'red' for r in returns])
        ax1.set_title('Total Returns by Period')
        ax1.set_ylabel('Return (%)')
        ax1.set_xticks(x)
        ax1.set_xticklabels([p.split()[0] for p in periods], rotation=45)
        ax1.grid(True, alpha=0.3)
        
        # 2. Max MDD
        ax2 = axes[0, 1]
        ax2.bar(x, max_mdds, color='orange')
        ax2.axhline(y=40, color='red', linestyle='--', label='Level 3 (40%)')
        ax2.set_title('Maximum Drawdown by Period')
        ax2.set_ylabel('Max MDD (%)')
        ax2.set_xticks(x)
        ax2.set_xticklabels([p.split()[0] for p in periods], rotation=45)
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # 3. Win Rate
        ax3 = axes[0, 2]
        ax3.bar(x, win_rates, color='blue')
        ax3.axhline(y=50, color='black', linestyle='--', alpha=0.5)
        ax3.set_title('Win Rate by Period')
        ax3.set_ylabel('Win Rate (%)')
        ax3.set_xticks(x)
        ax3.set_xticklabels([p.split()[0] for p in periods], rotation=45)
        ax3.grid(True, alpha=0.3)
        
        # 4. Total Trades
        ax4 = axes[1, 0]
        ax4.bar(x, total_trades, color='darkgreen')
        ax4.set_title('Total Trades by Period')
        ax4.set_ylabel('Number of Trades')
        ax4.set_xticks(x)
        ax4.set_xticklabels([p.split()[0] for p in periods], rotation=45)
        ax4.grid(True, alpha=0.3)
        
        # 5. Trades with Reduced Size
        ax5 = axes[1, 1]
        width = 0.35
        ax5.bar(x - width/2, total_trades, width, label='Total', color='lightblue')
        ax5.bar(x + width/2, trades_reduced, width, label='Reduced Size', color='orange')
        ax5.set_title('Trades with Reduced Position Size')
        ax5.set_ylabel('Number of Trades')
        ax5.set_xticks(x)
        ax5.set_xticklabels([p.split()[0] for p in periods], rotation=45)
        ax5.legend()
        ax5.grid(True, alpha=0.3)
        
        # 6. Time in MDD > 40%
        ax6 = axes[1, 2]
        ax6.bar(x, time_mdd_40, color='red')
        ax6.set_title('Time in MDD Level 3 (>40%)')
        ax6.set_ylabel('Time (%)')
        ax6.set_xticks(x)
        ax6.set_xticklabels([p.split()[0] for p in periods], rotation=45)
        ax6.grid(True, alpha=0.3)
        
        # 7. Sharpe Ratio
        ax7 = axes[2, 0]
        ax7.bar(x, sharpe_ratios, color='darkgreen')
        ax7.set_title('Sharpe Ratio by Period')
        ax7.set_ylabel('Sharpe Ratio')
        ax7.set_xticks(x)
        ax7.set_xticklabels([p.split()[0] for p in periods], rotation=45)
        ax7.grid(True, alpha=0.3)
        
        # 8. MDD Level Distribution (for 2022)
        ax8 = axes[2, 1]
        if len(all_results) >= 3:  # 2022 is the 3rd period
            result_2022 = all_results[2]
            mdd_level_data = result_2022['analysis']['mdd_stats']['mdd_level_trades']
            levels = []
            counts = []
            for level, data in mdd_level_data.items():
                levels.append(level.replace('level_', 'Level '))
                counts.append(data['count'])
            
            ax8.bar(levels, counts, color=['green', 'yellow', 'orange', 'red', 'darkred'][:len(levels)])
            ax8.set_title('2022 - Trades by MDD Level')
            ax8.set_ylabel('Number of Trades')
            ax8.set_xlabel('MDD Level')
        ax8.grid(True, alpha=0.3)
        
        # 9. Recovery Performance
        ax9 = axes[2, 2]
        recovery_data = []
        for result in all_results:
            mdd_trades = result['analysis']['mdd_stats']['mdd_level_trades']
            if 'level_3' in mdd_trades:
                recovery_data.append(mdd_trades['level_3']['win_rate'])
            else:
                recovery_data.append(0)
        
        ax9.bar(x, recovery_data, color='purple')
        ax9.axhline(y=50, color='black', linestyle='--', alpha=0.5)
        ax9.set_title('Win Rate at MDD Level 3 (>40%)')
        ax9.set_ylabel('Win Rate (%)')
        ax9.set_xticks(x)
        ax9.set_xticklabels([p.split()[0] for p in periods], rotation=45)
        ax9.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.show()
