"""
ZL MACD + Ichimoku Strategy - Multi-Symbol Portfolio Comparison
BTC 단일 운용 vs 3종목 분산 포트폴리오 비교 분석
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import os
import sys
import json
import time
from typing import Dict, List, Tuple
import seaborn as sns

# 현재 디렉토리 설정
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)
sys.path.append(script_dir)

# turtle_trading_strategy 모듈 임포트
from turtle_trading_strategy import ZLMACDIchimokuWalkForward, ZLMACDIchimokuStrategy

# 한글 폰트 설정
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False

class MultiSymbolPortfolioAnalyzer:
    """멀티 심볼 포트폴리오 분석기"""
    
    def __init__(self, initial_capital: float = 10000, timeframe: str = '1h'):
        self.initial_capital = initial_capital
        self.timeframe = timeframe
        self.symbols = ['BTC/USDT', 'ETH/USDT', 'XRP/USDT']
        
        # 각 심볼별 자본 배분 (균등 배분)
        self.capital_per_symbol = initial_capital / len(self.symbols)
        
        # 결과 저장
        self.individual_results = {}
        self.portfolio_results = None
        
        print(f"Multi-Symbol Portfolio Analyzer initialized")
        print(f"  • Initial Capital: ${initial_capital:,.0f}")
        print(f"  • Symbols: {', '.join(self.symbols)}")
        print(f"  • Capital per Symbol: ${self.capital_per_symbol:,.0f}")
        print(f"  • Timeframe: {timeframe}")
    
    def run_individual_backtests(self):
        """각 심볼별로 개별 백테스트 실행"""
        print("\n" + "="*80)
        print("PHASE 1: Running Individual Symbol Backtests")
        print("="*80)
        
        for symbol in self.symbols:
            print(f"\nAnalyzing {symbol}...")
            
            try:
                # Walk-Forward 분석기 초기화
                analyzer = ZLMACDIchimokuWalkForward(
                    initial_capital=self.capital_per_symbol,  # 분산된 자본으로 실행
                    timeframe=self.timeframe,
                    symbol=symbol
                )
                
                # 분석 실행
                results = analyzer.run_analysis()
                
                if results:
                    # 결과 저장
                    self.individual_results[symbol] = {
                        'quarterly_results': results,
                        'analyzer': analyzer,
                        'equity_curves': self._extract_equity_curves(results),
                        'trades': self._extract_all_trades(results),
                        'summary': self._calculate_summary(results)
                    }
                    
                    print(f"  ✓ {symbol} analysis complete")
                    print(f"    • Total Return: {self.individual_results[symbol]['summary']['total_return']:.1f}%")
                    print(f"    • Win Rate: {self.individual_results[symbol]['summary']['avg_win_rate']:.1f}%")
                    print(f"    • Total Trades: {self.individual_results[symbol]['summary']['total_trades']}")
                else:
                    print(f"  ✗ No results for {symbol}")
                    
            except Exception as e:
                print(f"  ✗ Error analyzing {symbol}: {e}")
                
            # API 제한 방지
            time.sleep(2)
    
    def run_btc_only_backtest(self):
        """BTC 단일 종목 백테스트 (전체 자본 투입)"""
        print("\n" + "="*80)
        print("PHASE 2: Running BTC-Only Backtest (Full Capital)")
        print("="*80)
        
        try:
            # BTC만으로 전체 자본 투입
            analyzer = ZLMACDIchimokuWalkForward(
                initial_capital=self.initial_capital,  # 전체 자본 투입
                timeframe=self.timeframe,
                symbol='BTC/USDT'
            )
            
            # 분석 실행
            results = analyzer.run_analysis()
            
            if results:
                self.btc_only_results = {
                    'quarterly_results': results,
                    'analyzer': analyzer,
                    'equity_curves': self._extract_equity_curves(results),
                    'trades': self._extract_all_trades(results),
                    'summary': self._calculate_summary(results)
                }
                
                print(f"  ✓ BTC-only analysis complete")
                print(f"    • Total Return: {self.btc_only_results['summary']['total_return']:.1f}%")
                print(f"    • Win Rate: {self.btc_only_results['summary']['avg_win_rate']:.1f}%")
                print(f"    • Total Trades: {self.btc_only_results['summary']['total_trades']}")
            else:
                print(f"  ✗ No results for BTC-only")
                
        except Exception as e:
            print(f"  ✗ Error in BTC-only analysis: {e}")
    
    def _extract_equity_curves(self, quarterly_results: List[Dict]) -> pd.DataFrame:
        """분기별 결과에서 전체 자산 곡선 추출"""
        all_equity = []
        
        for quarter in quarterly_results:
            if 'equity_df' in quarter and not quarter['equity_df'].empty:
                equity_df = quarter['equity_df'].copy()
                all_equity.append(equity_df)
        
        if all_equity:
            combined = pd.concat(all_equity, ignore_index=True)
            combined = combined.sort_values('time').reset_index(drop=True)
            return combined
        else:
            return pd.DataFrame()
    
    def _extract_all_trades(self, quarterly_results: List[Dict]) -> pd.DataFrame:
        """분기별 결과에서 모든 거래 추출"""
        all_trades = []
        
        for quarter in quarterly_results:
            if 'trades_df' in quarter and not quarter['trades_df'].empty:
                trades_df = quarter['trades_df'].copy()
                trades_df['quarter'] = quarter['period']
                all_trades.append(trades_df)
        
        if all_trades:
            return pd.concat(all_trades, ignore_index=True)
        else:
            return pd.DataFrame()
    
    def _calculate_summary(self, quarterly_results: List[Dict]) -> Dict:
        """전체 기간 요약 통계 계산"""
        if not quarterly_results:
            return {}
        
        total_return = sum(r['return'] for r in quarterly_results)
        avg_return = np.mean([r['return'] for r in quarterly_results])
        avg_win_rate = np.mean([r['win_rate'] for r in quarterly_results])
        total_trades = sum(r['trades'] for r in quarterly_results)
        avg_sharpe = np.mean([r['sharpe'] for r in quarterly_results])
        max_dd = max([r['max_dd'] for r in quarterly_results])
        
        # 복리 수익률 계산
        compound_return = 1.0
        for r in quarterly_results:
            compound_return *= (1 + r['return'] / 100)
        compound_return = (compound_return - 1) * 100
        
        return {
            'total_return': total_return,
            'compound_return': compound_return,
            'avg_quarterly_return': avg_return,
            'avg_win_rate': avg_win_rate,
            'total_trades': total_trades,
            'avg_sharpe': avg_sharpe,
            'max_drawdown': max_dd,
            'num_quarters': len(quarterly_results)
        }
    
    def calculate_portfolio_performance(self):
        """포트폴리오 전체 성과 계산"""
        print("\n" + "="*80)
        print("PHASE 3: Calculating Portfolio Performance")
        print("="*80)
        
        # 각 심볼의 equity curve를 시간별로 정렬
        portfolio_equity = {}
        
        for symbol, data in self.individual_results.items():
            if 'equity_curves' in data and not data['equity_curves'].empty:
                equity_df = data['equity_curves'].copy()
                equity_df['symbol'] = symbol
                
                # 시간을 key로 사용
                for _, row in equity_df.iterrows():
                    time_key = row['time']
                    if time_key not in portfolio_equity:
                        portfolio_equity[time_key] = {
                            'time': time_key,
                            'capitals': {},
                            'prices': {}
                        }
                    portfolio_equity[time_key]['capitals'][symbol] = row['capital']
                    portfolio_equity[time_key]['prices'][symbol] = row.get('price', 0)
        
        # DataFrame으로 변환하고 포트폴리오 가치 계산
        portfolio_list = []
        for time_key, data in sorted(portfolio_equity.items()):
            total_capital = sum(data['capitals'].values())
            portfolio_list.append({
                'time': data['time'],
                'portfolio_capital': total_capital,
                'btc_price': data['prices'].get('BTC/USDT', 0),
                'eth_price': data['prices'].get('ETH/USDT', 0),
                'xrp_price': data['prices'].get('XRP/USDT', 0),
                **{f'{symbol}_capital': capital for symbol, capital in data['capitals'].items()}
            })
        
        self.portfolio_results = pd.DataFrame(portfolio_list)
        
        # 포트폴리오 수익률 계산
        if not self.portfolio_results.empty:
            initial_value = self.initial_capital
            final_value = self.portfolio_results['portfolio_capital'].iloc[-1]
            total_return = (final_value / initial_value - 1) * 100
            
            print(f"  ✓ Portfolio analysis complete")
            print(f"    • Initial Capital: ${initial_value:,.0f}")
            print(f"    • Final Capital: ${final_value:,.0f}")
            print(f"    • Total Return: {total_return:.1f}%")
            
            # 최대 손실 계산
            portfolio_values = self.portfolio_results['portfolio_capital'].values
            peak = np.maximum.accumulate(portfolio_values)
            drawdown = (portfolio_values - peak) / peak * 100
            max_drawdown = abs(drawdown.min())
            print(f"    • Max Drawdown: {max_drawdown:.1f}%")
    
    def plot_comparison_charts(self):
        """비교 차트 생성"""
        print("\n" + "="*80)
        print("PHASE 4: Creating Comparison Charts")
        print("="*80)
        
        # 차트 스타일 설정
        plt.style.use('seaborn-v0_8-darkgrid')
        
        # 1. 메인 비교 차트 (4개 서브플롯)
        fig = plt.figure(figsize=(20, 16))
        
        # 1-1. 개별 심볼 수익 곡선
        ax1 = plt.subplot(2, 2, 1)
        
        for symbol, data in self.individual_results.items():
            if 'equity_curves' in data and not data['equity_curves'].empty:
                equity_df = data['equity_curves']
                returns = (equity_df['capital'] / self.capital_per_symbol - 1) * 100
                ax1.plot(equity_df['time'], returns, label=symbol, linewidth=2)
        
        ax1.axhline(y=0, color='black', linestyle='--', alpha=0.5)
        ax1.set_title('Individual Symbol Returns (Equal Capital Allocation)', fontsize=14, fontweight='bold')
        ax1.set_xlabel('Date')
        ax1.set_ylabel('Return (%)')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 1-2. BTC Only vs Portfolio 비교
        ax2 = plt.subplot(2, 2, 2)
        
        # BTC only (전체 자본)
        if hasattr(self, 'btc_only_results') and 'equity_curves' in self.btc_only_results:
            btc_equity = self.btc_only_results['equity_curves']
            btc_returns = (btc_equity['capital'] / self.initial_capital - 1) * 100
            ax2.plot(btc_equity['time'], btc_returns, 'b-', linewidth=3, label='BTC Only (100% Capital)')
        
        # 포트폴리오 (3종목 분산)
        if self.portfolio_results is not None and not self.portfolio_results.empty:
            portfolio_returns = (self.portfolio_results['portfolio_capital'] / self.initial_capital - 1) * 100
            ax2.plot(self.portfolio_results['time'], portfolio_returns, 'r-', linewidth=3, label='3-Symbol Portfolio')
        
        ax2.axhline(y=0, color='black', linestyle='--', alpha=0.5)
        ax2.set_title('BTC Only vs 3-Symbol Portfolio Comparison', fontsize=14, fontweight='bold')
        ax2.set_xlabel('Date')
        ax2.set_ylabel('Return (%)')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # 1-3. 포트폴리오 구성 변화
        ax3 = plt.subplot(2, 2, 3)
        
        if self.portfolio_results is not None and not self.portfolio_results.empty:
            # 각 심볼의 비중 계산
            for symbol in self.symbols:
                symbol_col = f'{symbol}_capital'
                if symbol_col in self.portfolio_results.columns:
                    weights = self.portfolio_results[symbol_col] / self.portfolio_results['portfolio_capital'] * 100
                    ax3.plot(self.portfolio_results['time'], weights, label=symbol, linewidth=2)
        
        ax3.axhline(y=33.33, color='black', linestyle='--', alpha=0.3, label='Equal Weight')
        ax3.set_title('Portfolio Composition Over Time', fontsize=14, fontweight='bold')
        ax3.set_xlabel('Date')
        ax3.set_ylabel('Weight (%)')
        ax3.set_ylim(0, 100)
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        
        # 1-4. 드로우다운 비교
        ax4 = plt.subplot(2, 2, 4)
        
        # BTC only 드로우다운
        if hasattr(self, 'btc_only_results') and 'equity_curves' in self.btc_only_results:
            btc_equity_values = self.btc_only_results['equity_curves']['capital'].values
            btc_peak = np.maximum.accumulate(btc_equity_values)
            btc_dd = (btc_equity_values - btc_peak) / btc_peak * 100
            ax4.fill_between(self.btc_only_results['equity_curves']['time'], 
                           0, btc_dd, color='blue', alpha=0.3, label='BTC Only')
            ax4.plot(self.btc_only_results['equity_curves']['time'], 
                   btc_dd, 'b-', linewidth=2)
        
        # Portfolio 드로우다운
        if self.portfolio_results is not None and not self.portfolio_results.empty:
            portfolio_values = self.portfolio_results['portfolio_capital'].values
            portfolio_peak = np.maximum.accumulate(portfolio_values)
            portfolio_dd = (portfolio_values - portfolio_peak) / portfolio_peak * 100
            ax4.fill_between(self.portfolio_results['time'], 
                           0, portfolio_dd, color='red', alpha=0.3, label='3-Symbol Portfolio')
            ax4.plot(self.portfolio_results['time'], 
                   portfolio_dd, 'r-', linewidth=2)
        
        ax4.set_title('Drawdown Comparison', fontsize=14, fontweight='bold')
        ax4.set_xlabel('Date')
        ax4.set_ylabel('Drawdown (%)')
        ax4.legend()
        ax4.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # 저장
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename1 = f'portfolio_comparison_main_{self.timeframe}_{timestamp}.png'
        plt.savefig(filename1, dpi=300, bbox_inches='tight')
        print(f"  ✓ Main comparison chart saved: {filename1}")
        
        # 2. 성과 요약 차트
        fig2, ((ax5, ax6), (ax7, ax8)) = plt.subplots(2, 2, figsize=(16, 12))
        
        # 2-1. 수익률 비교 막대 차트
        labels = []
        returns = []
        colors = []
        
        # 개별 심볼 수익률
        for symbol in self.symbols:
            if symbol in self.individual_results:
                labels.append(symbol)
                returns.append(self.individual_results[symbol]['summary']['total_return'])
                colors.append('lightblue')
        
        # BTC only
        if hasattr(self, 'btc_only_results'):
            labels.append('BTC Only\n(Full Capital)')
            returns.append(self.btc_only_results['summary']['total_return'])
            colors.append('darkblue')
        
        # Portfolio
        if self.portfolio_results is not None and not self.portfolio_results.empty:
            portfolio_return = (self.portfolio_results['portfolio_capital'].iloc[-1] / self.initial_capital - 1) * 100
            labels.append('3-Symbol\nPortfolio')
            returns.append(portfolio_return)
            colors.append('darkred')
        
        bars = ax5.bar(labels, returns, color=colors, alpha=0.7, edgecolor='black')
        
        # 값 표시
        for bar, ret in zip(bars, returns):
            height = bar.get_height()
            ax5.text(bar.get_x() + bar.get_width()/2., height,
                    f'{ret:.1f}%', ha='center', va='bottom' if height >= 0 else 'top')
        
        ax5.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax5.set_title('Total Return Comparison', fontsize=14, fontweight='bold')
        ax5.set_ylabel('Return (%)')
        ax5.grid(True, alpha=0.3)
        
        # 2-2. 리스크 지표 비교
        categories = ['BTC Only', '3-Symbol Portfolio']
        
        if hasattr(self, 'btc_only_results') and self.portfolio_results is not None:
            # 최대 손실
            btc_values = self.btc_only_results['equity_curves']['capital'].values
            btc_peak = np.maximum.accumulate(btc_values)
            btc_dd = (btc_values - btc_peak) / btc_peak * 100
            btc_max_dd = abs(btc_dd.min())
            
            portfolio_values = self.portfolio_results['portfolio_capital'].values
            portfolio_peak = np.maximum.accumulate(portfolio_values)
            portfolio_dd = (portfolio_values - portfolio_peak) / portfolio_peak * 100
            portfolio_max_dd = abs(portfolio_dd.min())
            
            # 변동성 (일간 수익률 표준편차)
            btc_returns = pd.Series(btc_values).pct_change().dropna()
            portfolio_returns = pd.Series(portfolio_values).pct_change().dropna()
            
            btc_volatility = btc_returns.std() * np.sqrt(252) * 100  # 연율화
            portfolio_volatility = portfolio_returns.std() * np.sqrt(252) * 100
            
            # 샤프 비율
            btc_sharpe = (btc_returns.mean() / btc_returns.std()) * np.sqrt(252) if btc_returns.std() > 0 else 0
            portfolio_sharpe = (portfolio_returns.mean() / portfolio_returns.std()) * np.sqrt(252) if portfolio_returns.std() > 0 else 0
            
            # 막대 그래프
            x = np.arange(len(categories))
            width = 0.25
            
            ax6.bar(x - width, [btc_max_dd, portfolio_max_dd], width, label='Max Drawdown (%)', color='red', alpha=0.7)
            ax6.bar(x, [btc_volatility, portfolio_volatility], width, label='Volatility (%)', color='orange', alpha=0.7)
            ax6.bar(x + width, [btc_sharpe, portfolio_sharpe], width, label='Sharpe Ratio', color='green', alpha=0.7)
            
            ax6.set_xlabel('Strategy')
            ax6.set_title('Risk Metrics Comparison', fontsize=14, fontweight='bold')
            ax6.set_xticks(x)
            ax6.set_xticklabels(categories)
            ax6.legend()
            ax6.grid(True, alpha=0.3)
        
        # 2-3. 월별 수익률 히트맵 (포트폴리오)
        if self.portfolio_results is not None and not self.portfolio_results.empty:
            # 월별 수익률 계산
            portfolio_df = self.portfolio_results.copy()
            portfolio_df['time'] = pd.to_datetime(portfolio_df['time'])
            portfolio_df.set_index('time', inplace=True)
            
            # 월별 리샘플링
            monthly_returns = portfolio_df['portfolio_capital'].resample('M').last().pct_change() * 100
            monthly_returns = monthly_returns.dropna()
            
            # 피벗 테이블 생성
            monthly_df = pd.DataFrame({
                'Year': monthly_returns.index.year,
                'Month': monthly_returns.index.month,
                'Return': monthly_returns.values
            })
            
            pivot_table = monthly_df.pivot(index='Year', columns='Month', values='Return')
            
            # 히트맵
            sns.heatmap(pivot_table, annot=True, fmt='.1f', cmap='RdYlGn', center=0,
                       cbar_kws={'label': 'Return (%)'}, ax=ax7)
            ax7.set_title('Portfolio Monthly Returns Heatmap', fontsize=14, fontweight='bold')
            ax7.set_xlabel('Month')
            ax7.set_ylabel('Year')
        
        # 2-4. 통계 요약 테이블
        summary_data = []
        
        # BTC Only
        if hasattr(self, 'btc_only_results'):
            summary_data.append({
                'Strategy': 'BTC Only',
                'Total Return': f"{self.btc_only_results['summary']['total_return']:.1f}%",
                'Win Rate': f"{self.btc_only_results['summary']['avg_win_rate']:.1f}%",
                'Total Trades': self.btc_only_results['summary']['total_trades'],
                'Avg Sharpe': f"{self.btc_only_results['summary']['avg_sharpe']:.2f}",
                'Max DD': f"{btc_max_dd:.1f}%" if 'btc_max_dd' in locals() else "N/A"
            })
        
        # Portfolio
        if self.portfolio_results is not None:
            # 전체 거래 수 계산
            total_portfolio_trades = sum(
                data['summary']['total_trades'] 
                for data in self.individual_results.values()
            )
            
            # 평균 승률 계산
            avg_portfolio_winrate = np.mean([
                data['summary']['avg_win_rate'] 
                for data in self.individual_results.values()
            ])
            
            summary_data.append({
                'Strategy': '3-Symbol Portfolio',
                'Total Return': f"{portfolio_return:.1f}%" if 'portfolio_return' in locals() else "N/A",
                'Win Rate': f"{avg_portfolio_winrate:.1f}%",
                'Total Trades': total_portfolio_trades,
                'Avg Sharpe': f"{portfolio_sharpe:.2f}" if 'portfolio_sharpe' in locals() else "N/A",
                'Max DD': f"{portfolio_max_dd:.1f}%" if 'portfolio_max_dd' in locals() else "N/A"
            })
        
        # 테이블 그리기
        ax8.axis('off')
        if summary_data:
            table_data = []
            headers = list(summary_data[0].keys())
            for row in summary_data:
                table_data.append(list(row.values()))
            
            table = ax8.table(cellText=table_data, colLabels=headers,
                            cellLoc='center', loc='center')
            table.auto_set_font_size(False)
            table.set_fontsize(10)
            table.scale(1.2, 1.5)
            
            # 헤더 스타일
            for i in range(len(headers)):
                table[(0, i)].set_facecolor('#40466e')
                table[(0, i)].set_text_props(weight='bold', color='white')
            
            # 행 색상
            for i in range(1, len(table_data) + 1):
                for j in range(len(headers)):
                    if i % 2 == 0:
                        table[(i, j)].set_facecolor('#f0f0f0')
        
        ax8.set_title('Performance Summary', fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        
        # 저장
        filename2 = f'portfolio_comparison_summary_{self.timeframe}_{timestamp}.png'
        plt.savefig(filename2, dpi=300, bbox_inches='tight')
        print(f"  ✓ Summary chart saved: {filename2}")
        
        # 차트 표시
        plt.show()
        
        # 3. 최종 분석 결과 출력
        self.print_final_analysis()
    
    def print_final_analysis(self):
        """최종 분석 결과 출력"""
        print("\n" + "="*80)
        print("FINAL ANALYSIS RESULTS")
        print("="*80)
        
        print("\n📊 1. Individual Symbol Performance (Equal Capital Allocation):")
        print(f"{'Symbol':<12} {'Total Return':<15} {'Win Rate':<12} {'Trades':<10} {'Max DD':<10}")
        print("-" * 60)
        
        for symbol in self.symbols:
            if symbol in self.individual_results:
                data = self.individual_results[symbol]['summary']
                print(f"{symbol:<12} {data['total_return']:>12.1f}% "
                      f"{data['avg_win_rate']:>10.1f}% "
                      f"{data['total_trades']:>8} "
                      f"{data['max_drawdown']:>8.1f}%")
        
        print("\n📊 2. Portfolio Comparison:")
        print(f"{'Strategy':<20} {'Total Return':<15} {'Risk-Adjusted':<15}")
        print("-" * 50)
        
        # BTC Only
        if hasattr(self, 'btc_only_results'):
            btc_return = self.btc_only_results['summary']['total_return']
            btc_sharpe = self.btc_only_results['summary']['avg_sharpe']
            print(f"{'BTC Only (100%)':<20} {btc_return:>12.1f}% {btc_sharpe:>13.2f}")
        
        # Portfolio
        if self.portfolio_results is not None and not self.portfolio_results.empty:
            portfolio_return = (self.portfolio_results['portfolio_capital'].iloc[-1] / self.initial_capital - 1) * 100
            
            # 포트폴리오 샤프 계산
            portfolio_values = self.portfolio_results['portfolio_capital'].values
            portfolio_returns = pd.Series(portfolio_values).pct_change().dropna()
            portfolio_sharpe = (portfolio_returns.mean() / portfolio_returns.std()) * np.sqrt(252) if portfolio_returns.std() > 0 else 0
            
            print(f"{'3-Symbol Portfolio':<20} {portfolio_return:>12.1f}% {portfolio_sharpe:>13.2f}")
        
        print("\n💡 Key Insights:")
        
        # 비교 분석
        if hasattr(self, 'btc_only_results') and self.portfolio_results is not None:
            btc_return = self.btc_only_results['summary']['total_return']
            portfolio_return = (self.portfolio_results['portfolio_capital'].iloc[-1] / self.initial_capital - 1) * 100
            
            if portfolio_return > btc_return:
                diff = portfolio_return - btc_return
                print(f"  ✓ Portfolio outperformed BTC-only by {diff:.1f}%")
            else:
                diff = btc_return - portfolio_return
                print(f"  ✗ BTC-only outperformed portfolio by {diff:.1f}%")
            
            # 리스크 비교
            btc_values = self.btc_only_results['equity_curves']['capital'].values
            portfolio_values = self.portfolio_results['portfolio_capital'].values
            
            btc_volatility = pd.Series(btc_values).pct_change().std() * np.sqrt(252) * 100
            portfolio_volatility = pd.Series(portfolio_values).pct_change().std() * np.sqrt(252) * 100
            
            if portfolio_volatility < btc_volatility:
                vol_reduction = (1 - portfolio_volatility / btc_volatility) * 100
                print(f"  ✓ Portfolio reduced volatility by {vol_reduction:.1f}%")
            else:
                vol_increase = (portfolio_volatility / btc_volatility - 1) * 100
                print(f"  ✗ Portfolio increased volatility by {vol_increase:.1f}%")
            
            # 다각화 효과
            print(f"\n  📌 Diversification Analysis:")
            
            # 상관관계 계산 (간단히 각 심볼의 수익률 상관관계)
            if all(symbol in self.individual_results for symbol in self.symbols):
                returns_data = {}
                for symbol in self.symbols:
                    equity = self.individual_results[symbol]['equity_curves']
                    if not equity.empty:
                        returns = equity['capital'].pct_change().dropna()
                        returns_data[symbol] = returns
                
                if len(returns_data) == 3:
                    # 최소 길이로 맞추기
                    min_len = min(len(returns) for returns in returns_data.values())
                    for symbol in returns_data:
                        returns_data[symbol] = returns_data[symbol][:min_len]
                    
                    corr_df = pd.DataFrame(returns_data).corr()
                    avg_corr = (corr_df.sum().sum() - len(corr_df)) / (len(corr_df) * (len(corr_df) - 1))
                    
                    print(f"    • Average correlation between symbols: {avg_corr:.3f}")
                    if avg_corr < 0.7:
                        print(f"    • Good diversification benefit (low correlation)")
                    else:
                        print(f"    • Limited diversification benefit (high correlation)")
    
    def save_results(self):
        """결과를 JSON 파일로 저장"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        results = {
            'timestamp': timestamp,
            'timeframe': self.timeframe,
            'initial_capital': self.initial_capital,
            'symbols': self.symbols,
            'individual_results': {},
            'portfolio_performance': {},
            'btc_only_performance': {}
        }
        
        # 개별 심볼 결과
        for symbol, data in self.individual_results.items():
            results['individual_results'][symbol] = {
                'summary': data['summary'],
                'num_trades': len(data['trades']) if 'trades' in data else 0
            }
        
        # 포트폴리오 성과
        if self.portfolio_results is not None and not self.portfolio_results.empty:
            final_value = self.portfolio_results['portfolio_capital'].iloc[-1]
            results['portfolio_performance'] = {
                'final_value': float(final_value),
                'total_return': float((final_value / self.initial_capital - 1) * 100),
                'data_points': len(self.portfolio_results)
            }
        
        # BTC only 성과
        if hasattr(self, 'btc_only_results'):
            results['btc_only_performance'] = self.btc_only_results['summary']
        
        # JSON 저장
        filename = f'portfolio_comparison_results_{self.timeframe}_{timestamp}.json'
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n✅ Results saved to: {filename}")
    
    def run_complete_analysis(self):
        """전체 분석 실행"""
        # 1. 개별 심볼 백테스트
        self.run_individual_backtests()
        
        # 2. BTC 단일 백테스트
        self.run_btc_only_backtest()
        
        # 3. 포트폴리오 성과 계산
        self.calculate_portfolio_performance()
        
        # 4. 차트 생성
        self.plot_comparison_charts()
        
        # 5. 결과 저장
        self.save_results()


def main():
    """메인 실행 함수"""
    print("\n" + "="*80)
    print("ZL MACD + Ichimoku Strategy - Portfolio Comparison Analysis")
    print("BTC Single vs Multi-Symbol Portfolio (BTC + ETH + XRP)")
    print("="*80)
    
    # 분석기 초기화
    analyzer = MultiSymbolPortfolioAnalyzer(
        initial_capital=10000,
        timeframe='1h'
    )
    
    # 전체 분석 실행
    analyzer.run_complete_analysis()
    
    print("\n✅ Analysis complete!")


if __name__ == "__main__":
    main()
