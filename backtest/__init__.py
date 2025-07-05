"""
AlbraTrading Modular Backtesting Framework

A professional-grade backtesting system designed with SOLID principles,
Domain-Driven Design, and Event-Driven Architecture.

Features:
- Event-driven backtesting engine
- Modular strategy framework
- Natural language strategy builder
- Comprehensive risk management
- Advanced performance analytics

Usage:
    from backtest import Backtest, StrategyBuilder
    
    # Code-based strategy
    backtest = Backtest(strategy=MyStrategy())
    results = backtest.run()
    
    # Natural language strategy
    strategy = StrategyBuilder.from_text("Buy when RSI < 30")
    backtest = Backtest(strategy=strategy)
    results = backtest.run()
"""

from .core.engine import BacktestEngine, Backtest
from .strategies.base import BaseStrategy
from .strategies.builder import StrategyBuilder

__version__ = "1.0.0"
__author__ = "AlbraTrading Team"

__all__ = [
    "BacktestEngine",
    "Backtest",
    "BaseStrategy", 
    "StrategyBuilder"
]