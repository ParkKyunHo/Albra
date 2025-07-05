#!/usr/bin/env python3
"""
Simple test to compare 3 vs 4 conditions for ZLMACD Ichimoku
"""

import pandas as pd
import numpy as np
from datetime import datetime

def calculate_zlema(series: pd.Series, period: int) -> pd.Series:
    """Zero Lag EMA"""
    ema1 = series.ewm(span=period, adjust=False).mean()
    ema2 = ema1.ewm(span=period, adjust=False).mean()
    zlema = 2 * ema1 - ema2
    return zlema

def analyze_conditions():
    """Analyze the impact of requiring 4 conditions"""
    
    print("\n" + "="*70)
    print("ZLMACD Ichimoku Strategy - 3 vs 4 Conditions Analysis")
    print("="*70)
    
    # Simulated signals (based on typical market behavior)
    # Each row represents: [MACD_cross, Price_vs_cloud, TK_cross, Cloud_color]
    # 1 = bullish/long signal, 0 = bearish/short signal
    
    scenarios = [
        # Scenario 1: Perfect alignment (all 4 conditions)
        {"name": "Perfect Long Setup", "signals": [1, 1, 1, 1], "type": "LONG"},
        {"name": "Perfect Short Setup", "signals": [0, 0, 0, 0], "type": "SHORT"},
        
        # Scenario 2: 3 conditions met
        {"name": "Strong Long (no cloud color)", "signals": [1, 1, 1, 0], "type": "LONG"},
        {"name": "Strong Short (no cloud color)", "signals": [0, 0, 0, 1], "type": "SHORT"},
        {"name": "Long (no TK cross)", "signals": [1, 1, 0, 1], "type": "LONG"},
        {"name": "Short (no TK cross)", "signals": [0, 0, 1, 0], "type": "SHORT"},
        
        # Scenario 3: Only 2 conditions
        {"name": "Weak Long", "signals": [1, 1, 0, 0], "type": "LONG"},
        {"name": "Weak Short", "signals": [0, 0, 1, 1], "type": "SHORT"},
    ]
    
    conditions = ["MACD Cross", "Price vs Cloud", "TK Cross", "Cloud Color"]
    
    print("\n📊 Signal Analysis:")
    print("-" * 70)
    
    entries_3_conditions = 0
    entries_4_conditions = 0
    
    for scenario in scenarios:
        signals = scenario["signals"]
        signal_count = sum(signals) if scenario["type"] == "LONG" else 4 - sum(signals)
        
        # For 3 conditions (cloud color worth 0.5)
        if scenario["type"] == "LONG":
            strength_3 = signals[0] + signals[1] + signals[2] + (signals[3] * 0.5)
        else:
            strength_3 = (1-signals[0]) + (1-signals[1]) + (1-signals[2]) + ((1-signals[3]) * 0.5)
        
        can_enter_3 = strength_3 >= 3
        can_enter_4 = signal_count == 4
        
        if can_enter_3:
            entries_3_conditions += 1
        if can_enter_4:
            entries_4_conditions += 1
        
        print(f"\n{scenario['name']} ({scenario['type']}):")
        for i, condition in enumerate(conditions):
            status = "✅" if (signals[i] == 1 and scenario["type"] == "LONG") or \
                           (signals[i] == 0 and scenario["type"] == "SHORT") else "❌"
            print(f"  {condition}: {status}")
        
        print(f"  Strength (3-cond system): {strength_3:.1f}")
        print(f"  Entry allowed (3 conditions): {'YES ✅' if can_enter_3 else 'NO ❌'}")
        print(f"  Entry allowed (4 conditions): {'YES ✅' if can_enter_4 else 'NO ❌'}")
    
    print("\n" + "="*70)
    print("📈 Summary:")
    print(f"  Total scenarios tested: {len(scenarios)}")
    print(f"  Entries with 3+ conditions: {entries_3_conditions}")
    print(f"  Entries with 4 conditions: {entries_4_conditions}")
    print(f"  Signal reduction: {((entries_3_conditions - entries_4_conditions) / entries_3_conditions * 100):.1f}%")
    
    print("\n💡 Key Insights:")
    print("  - Requiring 4 conditions significantly reduces entry signals")
    print("  - Only perfect setups will trigger entries")
    print("  - Expected: Higher win rate but fewer trades")
    print("  - Risk: May miss profitable opportunities")

if __name__ == "__main__":
    analyze_conditions()