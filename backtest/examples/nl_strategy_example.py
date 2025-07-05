"""
Natural Language Strategy Builder Example

This example demonstrates how to create trading strategies using natural language descriptions.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backtest.strategies.builder import NaturalLanguageStrategyBuilder
from backtest.core.engine import Backtest
from backtest.analysis.visualization import plot_backtest_results


def main():
    """Run natural language strategy builder examples."""
    
    # Initialize the builder
    builder = NaturalLanguageStrategyBuilder()
    
    print("=== Natural Language Strategy Builder Examples ===\n")
    
    # Example 1: Simple Moving Average Crossover
    print("Example 1: Moving Average Crossover Strategy")
    print("-" * 50)
    
    description1 = """
    20일 이동평균선과 50일 이동평균선의 골든크로스에서 매수하고,
    데드크로스에서 매도합니다. 손절은 2%, 익절은 5%로 설정하고,
    포지션 크기는 계좌의 10%로 고정합니다.
    """
    
    print(f"Description: {description1.strip()}\n")
    
    # Build strategy
    code1, blueprint1 = builder.build_strategy(description1)
    
    # Show parsed components
    explanation1 = builder.explain_strategy(blueprint1)
    print("Parsed Strategy:")
    print(explanation1)
    
    # Show improvement suggestions
    suggestions1 = builder.suggest_improvements(blueprint1)
    if suggestions1:
        print("\nImprovement Suggestions:")
        for suggestion in suggestions1:
            print(f"  - {suggestion}")
    
    print("\n" + "=" * 80 + "\n")
    
    # Example 2: RSI Reversal Strategy
    print("Example 2: RSI Reversal Strategy")
    print("-" * 50)
    
    description2 = """
    RSI가 30 이하로 과매도 상태일 때 매수하고, 70 이상으로 과매수 상태일 때 매도합니다.
    손절은 ATR의 1.5배, 익절은 ATR의 3배로 설정합니다.
    켈리 기준으로 포지션 사이징을 하고, 트레일링 스톱을 사용합니다.
    """
    
    print(f"Description: {description2.strip()}\n")
    
    code2, blueprint2 = builder.build_strategy(description2)
    explanation2 = builder.explain_strategy(blueprint2)
    print("Parsed Strategy:")
    print(explanation2)
    
    suggestions2 = builder.suggest_improvements(blueprint2)
    if suggestions2:
        print("\nImprovement Suggestions:")
        for suggestion in suggestions2:
            print(f"  - {suggestion}")
    
    print("\n" + "=" * 80 + "\n")
    
    # Example 3: Complex Multi-Indicator Strategy
    print("Example 3: Complex Multi-Indicator Strategy")
    print("-" * 50)
    
    description3 = """
    이치모쿠 구름 위에서 MACD 골든크로스가 발생하면 매수합니다.
    추가로 RSI가 50 이상이고 ADX가 25 이상일 때만 진입합니다.
    가격이 구름 아래로 떨어지거나 MACD 데드크로스 발생 시 청산합니다.
    손절은 2%, 익절은 10%로 설정하고, 3% 수익 시 트레일링 스톱을 활성화합니다.
    일일 손실 한도는 3%이며, 리스크 기반으로 포지션을 계산합니다.
    """
    
    print(f"Description: {description3.strip()}\n")
    
    code3, blueprint3 = builder.build_strategy(description3)
    explanation3 = builder.explain_strategy(blueprint3)
    print("Parsed Strategy:")
    print(explanation3)
    
    suggestions3 = builder.suggest_improvements(blueprint3)
    if suggestions3:
        print("\nImprovement Suggestions:")
        for suggestion in suggestions3:
            print(f"  - {suggestion}")
    
    # Save generated code
    print("\n" + "=" * 80 + "\n")
    print("Saving generated strategies...")
    
    # Create examples directory if not exists
    os.makedirs('backtest/examples/generated_strategies', exist_ok=True)
    
    # Save strategy 1
    with open('backtest/examples/generated_strategies/ma_crossover.py', 'w', encoding='utf-8') as f:
        f.write(code1)
    print("✓ Saved: ma_crossover.py")
    
    # Save strategy 2
    with open('backtest/examples/generated_strategies/rsi_reversal.py', 'w', encoding='utf-8') as f:
        f.write(code2)
    print("✓ Saved: rsi_reversal.py")
    
    # Save strategy 3
    with open('backtest/examples/generated_strategies/multi_indicator.py', 'w', encoding='utf-8') as f:
        f.write(code3)
    print("✓ Saved: multi_indicator.py")
    
    print("\n" + "=" * 80 + "\n")
    
    # Show available examples
    print("Available Example Strategies:")
    examples = builder.get_examples()
    for i, example in enumerate(examples, 1):
        print(f"\n{i}. {example['name']}")
        print(f"   Description: {example['description']}")
    
    print("\n" + "=" * 80 + "\n")
    
    # Interactive mode
    print("Interactive Mode - Create Your Own Strategy")
    print("-" * 50)
    print("Enter your strategy description (or 'quit' to exit):")
    print("\nExample format:")
    print("볼린저 밴드 하단 터치 시 매수, 상단 터치 시 매도. 손절 2%, 익절 5%.")
    print()
    
    while True:
        try:
            user_input = input("Your strategy description: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("Exiting interactive mode.")
                break
            
            if not user_input:
                print("Please enter a strategy description.")
                continue
            
            # Build strategy from user input
            try:
                user_code, user_blueprint = builder.build_strategy(user_input)
                
                # Show results
                print("\nGenerated Strategy:")
                print("=" * 50)
                user_explanation = builder.explain_strategy(user_blueprint)
                print(user_explanation)
                
                # Validate
                validation = builder.validate_strategy(user_code)
                if validation['valid']:
                    print("\n✓ Strategy code is valid!")
                else:
                    print("\n✗ Strategy code has errors:")
                    for error in validation['errors']:
                        print(f"  - {error}")
                
                # Suggestions
                user_suggestions = builder.suggest_improvements(user_blueprint)
                if user_suggestions:
                    print("\nSuggestions for improvement:")
                    for suggestion in user_suggestions:
                        print(f"  - {suggestion}")
                
                # Save option
                save_choice = input("\nSave this strategy? (y/n): ").strip().lower()
                if save_choice == 'y':
                    filename = input("Enter filename (without .py): ").strip()
                    if filename:
                        filepath = f'backtest/examples/generated_strategies/{filename}.py'
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(user_code)
                        print(f"✓ Saved to: {filepath}")
                
            except Exception as e:
                print(f"\nError generating strategy: {e}")
                print("Please try rephrasing your description.")
            
            print("\n" + "-" * 50 + "\n")
            
        except KeyboardInterrupt:
            print("\n\nExiting interactive mode.")
            break
    
    print("\nExample completed!")


if __name__ == "__main__":
    main()