"""
Core Backtesting Engine

This module implements the event-driven backtesting engine that coordinates
all components of the backtesting system.
"""

import queue
import logging
from datetime import datetime
from typing import Dict, List, Optional, Type, Any
import pandas as pd
import numpy as np
from tqdm import tqdm

from .events import Event, MarketEvent, SignalEvent, OrderEvent, FillEvent, RiskEvent
from .portfolio import Portfolio
from .data_feed import DataFeed
from ..strategies.base import BaseStrategy
from ..execution.broker import SimulatedBroker
from ..risk.manager import RiskManager
from ..analysis.performance import PerformanceAnalyzer


logger = logging.getLogger(__name__)


class BacktestEngine:
    """
    Event-driven backtesting engine.
    
    This class orchestrates the entire backtesting process by:
    1. Managing the event queue
    2. Distributing events to appropriate handlers
    3. Coordinating between strategy, portfolio, broker, and risk manager
    4. Collecting and analyzing results
    """
    
    def __init__(
        self,
        data_feed: DataFeed,
        strategy: BaseStrategy,
        portfolio: Portfolio,
        broker: SimulatedBroker,
        risk_manager: Optional[RiskManager] = None
    ):
        """
        Initialize the backtesting engine.
        
        Args:
            data_feed: Data source for market data
            strategy: Trading strategy to test
            portfolio: Portfolio manager
            broker: Simulated broker for order execution
            risk_manager: Optional risk management component
        """
        self.data_feed = data_feed
        self.strategy = strategy
        self.portfolio = portfolio
        self.broker = broker
        self.risk_manager = risk_manager or RiskManager()
        
        # Event queue for event-driven architecture
        self.events_queue = queue.Queue()
        
        # Performance tracking
        self.market_events_count = 0
        self.signal_events_count = 0
        self.order_events_count = 0
        self.fill_events_count = 0
        
        # Results storage
        self.all_events: List[Event] = []
        self.equity_curve: List[Dict[str, Any]] = []
        
        logger.info(f"BacktestEngine initialized with strategy: {strategy.__class__.__name__}")
    
    def run(self, start_date: datetime, end_date: datetime, show_progress: bool = True) -> Dict[str, Any]:
        """
        Run the backtest for the specified period.
        
        Args:
            start_date: Start date for the backtest
            end_date: End date for the backtest
            show_progress: Whether to show progress bar
            
        Returns:
            Dictionary containing backtest results
        """
        logger.info(f"Starting backtest from {start_date} to {end_date}")
        
        # Reset components
        self._reset()
        
        # Get data iterator
        data_iterator = self.data_feed.get_data_iterator(start_date, end_date)
        total_bars = self.data_feed.get_total_bars(start_date, end_date)
        
        # Create progress bar if requested
        if show_progress:
            pbar = tqdm(total=total_bars, desc="Backtesting", unit="bars")
        
        # Main event loop
        try:
            for market_data in data_iterator:
                # Create and queue market event
                market_event = self._create_market_event(market_data)
                self.events_queue.put(market_event)
                
                # Process all events in queue
                while not self.events_queue.empty():
                    try:
                        event = self.events_queue.get(block=False)
                        self._process_event(event)
                    except queue.Empty:
                        break
                
                # Update equity curve
                self._update_equity_curve(market_event.timestamp, market_event.close)
                
                if show_progress:
                    pbar.update(1)
        
        finally:
            if show_progress:
                pbar.close()
        
        # Generate final results
        results = self._generate_results()
        logger.info("Backtest completed successfully")
        
        return results
    
    def _reset(self):
        """Reset all components for a new backtest run."""
        self.events_queue = queue.Queue()
        self.all_events = []
        self.equity_curve = []
        self.market_events_count = 0
        self.signal_events_count = 0
        self.order_events_count = 0
        self.fill_events_count = 0
        
        # Reset components
        self.portfolio.reset()
        self.strategy.reset()
        self.broker.reset()
        self.risk_manager.reset()
    
    def _create_market_event(self, market_data: pd.Series) -> MarketEvent:
        """Create a MarketEvent from market data."""
        # Calculate indicators
        indicators = self.strategy.calculate_indicators(market_data)
        
        return MarketEvent(
            timestamp=market_data.name,  # Assuming index is datetime
            symbol=self.data_feed.symbol,
            open=market_data['open'],
            high=market_data['high'],
            low=market_data['low'],
            close=market_data['close'],
            volume=market_data['volume'],
            indicators=indicators
        )
    
    def _process_event(self, event: Event):
        """Process a single event by routing it to the appropriate handler."""
        self.all_events.append(event)
        
        if isinstance(event, MarketEvent):
            self._handle_market_event(event)
        elif isinstance(event, SignalEvent):
            self._handle_signal_event(event)
        elif isinstance(event, OrderEvent):
            self._handle_order_event(event)
        elif isinstance(event, FillEvent):
            self._handle_fill_event(event)
        elif isinstance(event, RiskEvent):
            self._handle_risk_event(event)
        else:
            logger.warning(f"Unknown event type: {type(event)}")
    
    def _handle_market_event(self, event: MarketEvent):
        """Handle market data event."""
        self.market_events_count += 1
        
        # Update portfolio with latest prices
        self.portfolio.update_market_prices({event.symbol: event.close})
        
        # Check risk limits
        risk_events = self.risk_manager.check_risk_limits(self.portfolio, event)
        for risk_event in risk_events:
            self.events_queue.put(risk_event)
        
        # Generate trading signals
        signal = self.strategy.generate_signal(event)
        if signal and signal.signal_type != 'HOLD':
            self.events_queue.put(signal)
            self.signal_events_count += 1
    
    def _handle_signal_event(self, event: SignalEvent):
        """Handle trading signal event."""
        # Risk manager can veto signals
        if not self.risk_manager.approve_signal(event, self.portfolio):
            logger.info(f"Signal vetoed by risk manager: {event}")
            return
        
        # Convert signal to order
        order = self.portfolio.generate_order(event)
        if order:
            self.events_queue.put(order)
            self.order_events_count += 1
    
    def _handle_order_event(self, event: OrderEvent):
        """Handle order event."""
        # Execute order through broker
        fill = self.broker.execute_order(event)
        if fill:
            self.events_queue.put(fill)
            self.fill_events_count += 1
    
    def _handle_fill_event(self, event: FillEvent):
        """Handle order fill event."""
        # Update portfolio with fill
        self.portfolio.update_fill(event)
        
        # Notify strategy of fill
        self.strategy.on_fill(event)
    
    def _handle_risk_event(self, event: RiskEvent):
        """Handle risk management event."""
        logger.warning(f"Risk event: {event}")
        
        # Take action based on severity
        if event.severity == 'CRITICAL':
            # Force close all positions
            close_orders = self.portfolio.close_all_positions()
            for order in close_orders:
                self.events_queue.put(order)
    
    def _update_equity_curve(self, timestamp: datetime, current_price: float):
        """Update the equity curve with current portfolio value."""
        equity = self.portfolio.get_total_equity()
        positions = self.portfolio.get_positions_summary()
        
        self.equity_curve.append({
            'timestamp': timestamp,
            'equity': equity,
            'cash': self.portfolio.cash,
            'positions_value': equity - self.portfolio.cash,
            'positions_count': len(positions),
            'price': current_price
        })
    
    def _generate_results(self) -> Dict[str, Any]:
        """Generate comprehensive backtest results."""
        # Create equity curve DataFrame
        equity_df = pd.DataFrame(self.equity_curve)
        equity_df.set_index('timestamp', inplace=True)
        
        # Get trades from portfolio
        trades = self.portfolio.get_closed_trades()
        
        # Calculate performance metrics
        analyzer = PerformanceAnalyzer()
        metrics = analyzer.calculate_metrics(
            equity_curve=equity_df,
            trades=trades,
            initial_capital=self.portfolio.initial_capital
        )
        
        return {
            'metrics': metrics,
            'equity_curve': equity_df,
            'trades': trades,
            'events_summary': {
                'market_events': self.market_events_count,
                'signal_events': self.signal_events_count,
                'order_events': self.order_events_count,
                'fill_events': self.fill_events_count
            },
            'final_equity': self.portfolio.get_total_equity(),
            'initial_capital': self.portfolio.initial_capital
        }


class Backtest:
    """
    High-level backtesting interface for ease of use.
    
    This class provides a simple API for running backtests without
    needing to manually configure all components.
    """
    
    def __init__(
        self,
        strategy: BaseStrategy,
        symbol: str = 'BTC/USDT',
        timeframe: str = '1h',
        initial_capital: float = 10000,
        commission: float = 0.001,
        slippage: float = 0.001,
        data_source: str = 'binance'
    ):
        """
        Initialize a backtest with simplified parameters.
        
        Args:
            strategy: Trading strategy to test
            symbol: Trading symbol
            timeframe: Data timeframe (1m, 5m, 15m, 1h, 4h, 1d)
            initial_capital: Starting capital
            commission: Trading commission (as decimal)
            slippage: Expected slippage (as decimal)
            data_source: Data source ('binance', 'csv', etc.)
        """
        self.strategy = strategy
        self.symbol = symbol
        self.timeframe = timeframe
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.data_source = data_source
        
        # Components will be initialized in run()
        self.engine = None
        self.results = None
    
    def run(
        self,
        start_date: str,
        end_date: str,
        show_progress: bool = True
    ) -> Dict[str, Any]:
        """
        Run the backtest.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            show_progress: Whether to show progress bar
            
        Returns:
            Backtest results dictionary
        """
        # Convert string dates to datetime
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        
        # Initialize components
        from .data_feed import BinanceDataFeed
        from .portfolio import Portfolio
        from ..execution.broker import SimulatedBroker
        from ..risk.manager import RiskManager
        
        # Create data feed
        data_feed = BinanceDataFeed(
            symbol=self.symbol,
            timeframe=self.timeframe
        )
        
        # Create portfolio
        portfolio = Portfolio(
            initial_capital=self.initial_capital,
            commission=self.commission
        )
        
        # Create broker
        broker = SimulatedBroker(
            slippage=self.slippage,
            commission=self.commission
        )
        
        # Create risk manager
        risk_manager = RiskManager()
        
        # Create engine
        self.engine = BacktestEngine(
            data_feed=data_feed,
            strategy=self.strategy,
            portfolio=portfolio,
            broker=broker,
            risk_manager=risk_manager
        )
        
        # Run backtest
        self.results = self.engine.run(start_dt, end_dt, show_progress)
        
        return self.results
    
    def plot_results(self):
        """Plot backtest results."""
        if not self.results:
            raise ValueError("No results to plot. Run backtest first.")
        
        from ..analysis.visualization import plot_backtest_results
        plot_backtest_results(self.results)
    
    def get_metrics(self) -> Dict[str, float]:
        """Get performance metrics."""
        if not self.results:
            raise ValueError("No results available. Run backtest first.")
        
        return self.results['metrics']