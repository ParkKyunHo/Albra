"""
Multi-Symbol Test for ZL MACD + Ichimoku Strategy
"""
import os
import sys
import time
import json
from datetime import datetime
import pandas as pd

# 현재 디렉토리를 스크립트 위치로 변경
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)
sys.path.append(script_dir)

# turtle_trading_strategy 모듈 임포트
from turtle_trading_strategy import ZLMACDIchimokuWalkForward

def run_symbol_test(symbol, timeframe='1h'):
    """단일 심볼에 대한 백테스트 실행"""
    print(f"\n{'='*80}")
    print(f"Testing {symbol} on {timeframe} timeframe")
    print(f"{'='*80}")
    
    try:
        # 분석기 초기화
        analyzer = ZLMACDIchimokuWalkForward(
            initial_capital=10000,
            timeframe=timeframe,
            symbol=symbol
        )
        
        # 분석 실행
        results = analyzer.run_analysis()
        
        # 결과 저장
        if results:
            # 요약 통계 계산
            total_return = sum(r['return'] for r in results)
            avg_return = sum(r['return'] for r in results) / len(results)
            avg_win_rate = sum(r['win_rate'] for r in results) / len(results)
            total_trades = sum(r['trades'] for r in results)
            avg_sharpe = sum(r['sharpe'] for r in results) / len(results)
            max_dd = max(r['max_dd'] for r in results)
            positive_quarters = sum(1 for r in results if r['return'] > 0)
            
            summary = {
                'symbol': symbol,
                'timeframe': timeframe,
                'total_return': total_return,
                'avg_quarterly_return': avg_return,
                'avg_win_rate': avg_win_rate,
                'total_trades': total_trades,
                'avg_sharpe': avg_sharpe,
                'max_drawdown': max_dd,
                'positive_quarters': positive_quarters,
                'total_quarters': len(results),
                'quarterly_win_rate': (positive_quarters / len(results) * 100) if len(results) > 0 else 0
            }
            
            # 결과 출력
            print(f"\n📊 Summary for {symbol}:")
            print(f"  • Total Return: {total_return:.2f}%")
            print(f"  • Avg Quarterly Return: {avg_return:.2f}%")
            print(f"  • Avg Win Rate: {avg_win_rate:.1f}%")
            print(f"  • Total Trades: {total_trades}")
            print(f"  • Avg Sharpe Ratio: {avg_sharpe:.2f}")
            print(f"  • Max Drawdown: {max_dd:.1f}%")
            print(f"  • Positive Quarters: {positive_quarters}/{len(results)} ({positive_quarters/len(results)*100:.1f}%)")
            
            return summary
        else:
            print(f"❌ No results for {symbol}")
            return None
            
    except Exception as e:
        print(f"❌ Error testing {symbol}: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """메인 실행 함수"""
    print("\n" + "="*80)
    print("ZL MACD + Ichimoku Strategy - Multi-Symbol Comparison Test")
    print("="*80)
    
    # 테스트할 심볼 목록
    symbols = ['BTC/USDT', 'ETH/USDT', 'XRP/USDT']
    timeframe = '1h'  # 1시간 봉으로 테스트
    
    print(f"\nTesting {len(symbols)} symbols on {timeframe} timeframe:")
    for i, symbol in enumerate(symbols, 1):
        print(f"{i}. {symbol}")
    
    # 각 심볼별 결과 저장
    all_results = []
    
    # 각 심볼에 대해 백테스트 실행
    for symbol in symbols:
        result = run_symbol_test(symbol, timeframe)
        if result:
            all_results.append(result)
        
        # API 제한 방지를 위한 대기
        time.sleep(2)
    
    # 전체 결과 비교
    if all_results:
        print("\n" + "="*80)
        print("📊 MULTI-SYMBOL COMPARISON RESULTS")
        print("="*80)
        
        # DataFrame으로 변환하여 보기 좋게 출력
        df = pd.DataFrame(all_results)
        
        print("\n1. Return Performance:")
        print(f"{'Symbol':<10} {'Total Return':<15} {'Avg Quarterly':<15} {'Positive Qtrs':<15}")
        print("-" * 55)
        for _, row in df.iterrows():
            print(f"{row['symbol']:<10} {row['total_return']:>12.1f}% "
                  f"{row['avg_quarterly_return']:>13.1f}% "
                  f"{row['positive_quarters']:>6}/{row['total_quarters']:<3} "
                  f"({row['quarterly_win_rate']:>5.1f}%)")
        
        print("\n2. Trading Statistics:")
        print(f"{'Symbol':<10} {'Win Rate':<12} {'Total Trades':<15} {'Avg Sharpe':<12}")
        print("-" * 49)
        for _, row in df.iterrows():
            print(f"{row['symbol']:<10} {row['avg_win_rate']:>9.1f}% "
                  f"{row['total_trades']:>13} "
                  f"{row['avg_sharpe']:>11.2f}")
        
        print("\n3. Risk Metrics:")
        print(f"{'Symbol':<10} {'Max Drawdown':<15}")
        print("-" * 25)
        for _, row in df.iterrows():
            print(f"{row['symbol']:<10} {row['max_drawdown']:>12.1f}%")
        
        # 최고 성과 찾기
        best_return = df.loc[df['total_return'].idxmax()]
        best_sharpe = df.loc[df['avg_sharpe'].idxmax()]
        best_winrate = df.loc[df['avg_win_rate'].idxmax()]
        lowest_dd = df.loc[df['max_drawdown'].idxmin()]
        
        print("\n🏆 Best Performers:")
        print(f"  • Highest Total Return: {best_return['symbol']} ({best_return['total_return']:.1f}%)")
        print(f"  • Best Risk-Adjusted (Sharpe): {best_sharpe['symbol']} ({best_sharpe['avg_sharpe']:.2f})")
        print(f"  • Highest Win Rate: {best_winrate['symbol']} ({best_winrate['avg_win_rate']:.1f}%)")
        print(f"  • Lowest Max Drawdown: {lowest_dd['symbol']} ({lowest_dd['max_drawdown']:.1f}%)")
        
        # 결과를 JSON 파일로 저장
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'multi_symbol_comparison_{timeframe}_{timestamp}.json'
        
        with open(filename, 'w') as f:
            json.dump({
                'test_date': datetime.now().isoformat(),
                'timeframe': timeframe,
                'symbols': symbols,
                'results': all_results,
                'best_performers': {
                    'highest_return': {
                        'symbol': best_return['symbol'],
                        'value': best_return['total_return']
                    },
                    'best_sharpe': {
                        'symbol': best_sharpe['symbol'],
                        'value': best_sharpe['avg_sharpe']
                    },
                    'highest_winrate': {
                        'symbol': best_winrate['symbol'],
                        'value': best_winrate['avg_win_rate']
                    },
                    'lowest_drawdown': {
                        'symbol': lowest_dd['symbol'],
                        'value': lowest_dd['max_drawdown']
                    }
                }
            }, f, indent=2)
        
        print(f"\n✅ Results saved to: {filename}")
        
        # 심볼별 특성 분석
        print("\n💡 Symbol-Specific Insights:")
        
        for _, row in df.iterrows():
            symbol = row['symbol']
            print(f"\n{symbol}:")
            
            # 수익률 특성
            if row['total_return'] > 0:
                print(f"  ✓ Profitable overall ({row['total_return']:.1f}% total return)")
            else:
                print(f"  ✗ Loss overall ({row['total_return']:.1f}% total return)")
            
            # 일관성 분석
            consistency = row['quarterly_win_rate']
            if consistency >= 70:
                print(f"  ✓ Very consistent ({consistency:.1f}% positive quarters)")
            elif consistency >= 50:
                print(f"  ✓ Moderately consistent ({consistency:.1f}% positive quarters)")
            else:
                print(f"  ✗ Inconsistent ({consistency:.1f}% positive quarters)")
            
            # 리스크 특성
            if row['max_drawdown'] <= 30:
                print(f"  ✓ Low risk (Max DD: {row['max_drawdown']:.1f}%)")
            elif row['max_drawdown'] <= 50:
                print(f"  ⚠ Moderate risk (Max DD: {row['max_drawdown']:.1f}%)")
            else:
                print(f"  ✗ High risk (Max DD: {row['max_drawdown']:.1f}%)")
            
            # 거래 빈도
            avg_trades_per_quarter = row['total_trades'] / row['total_quarters']
            if avg_trades_per_quarter < 10:
                print(f"  • Low trading frequency ({avg_trades_per_quarter:.1f} trades/quarter)")
            elif avg_trades_per_quarter < 20:
                print(f"  • Moderate trading frequency ({avg_trades_per_quarter:.1f} trades/quarter)")
            else:
                print(f"  • High trading frequency ({avg_trades_per_quarter:.1f} trades/quarter)")
        
    else:
        print("\n❌ No results to compare")

if __name__ == "__main__":
    main()
