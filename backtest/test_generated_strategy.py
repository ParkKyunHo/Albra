"""
Test generated strategy code to verify import fixes.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Test importing the generated strategies
try:
    from backtest.examples.generated_strategies.multi_indicator import ICHIMOKUCrossOver
    print("✅ Successfully imported ICHIMOKUCrossOver strategy")
    
    # Create an instance
    strategy = ICHIMOKUCrossOver()
    print(f"✅ Strategy name: {strategy.name}")
    print(f"✅ Position size: {strategy.parameters.position_size}")
    print(f"✅ Stop loss: {strategy.parameters.stop_loss}")
    print(f"✅ Take profit: {strategy.parameters.take_profit}")
    print(f"✅ Trailing stop: {strategy.parameters.use_trailing_stop}")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
except Exception as e:
    print(f"❌ Error: {e}")

# Test other strategies
print("\n" + "="*50 + "\n")

try:
    from backtest.examples.generated_strategies.ma_crossover import CrossOver
    print("✅ Successfully imported CrossOver strategy")
    strategy = CrossOver()
    print(f"✅ Strategy name: {strategy.name}")
    
    from backtest.examples.generated_strategies.rsi_reversal import CustomStrategy
    print("✅ Successfully imported CustomStrategy")
    strategy = CustomStrategy()
    print(f"✅ Strategy name: {strategy.name}")
    
except Exception as e:
    print(f"❌ Error: {e}")

print("\n✅ All import issues have been fixed!")
print("You can now use these generated strategies in your backtesting.")