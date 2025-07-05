"""
Transaction Cost Models

This module provides various transaction cost models for realistic
backtesting including spread costs, market impact, and funding rates.
"""

import numpy as np
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class CostModel:
    """Base class for cost models."""
    name: str
    
    def calculate_cost(self, order_size: float, price: float, **kwargs) -> float:
        """Calculate transaction cost."""
        raise NotImplementedError


class SpreadCostModel(CostModel):
    """
    Bid-ask spread cost model.
    
    This model calculates the cost of crossing the spread when
    executing market orders.
    """
    
    def __init__(self, spread_bps: float = 5.0, min_spread: float = 0.01):
        """
        Initialize spread cost model.
        
        Args:
            spread_bps: Spread in basis points (5.0 = 0.05%)
            min_spread: Minimum absolute spread
        """
        super().__init__(name="SpreadCost")
        self.spread_bps = spread_bps
        self.min_spread = min_spread
    
    def calculate_cost(self, order_size: float, price: float, **kwargs) -> float:
        """
        Calculate spread cost.
        
        Args:
            order_size: Size of the order
            price: Current market price
            
        Returns:
            Spread cost
        """
        # Calculate spread as percentage of price
        spread = max(price * self.spread_bps / 10000, self.min_spread)
        
        # Cost is half-spread times order size
        return 0.5 * spread * order_size


class MarketImpactModel(CostModel):
    """
    Market impact cost model.
    
    This model estimates the price impact of large orders using
    various impact functions.
    """
    
    def __init__(self, impact_coefficient: float = 0.1, impact_exponent: float = 0.5):
        """
        Initialize market impact model.
        
        Args:
            impact_coefficient: Impact scaling factor
            impact_exponent: Impact exponent (0.5 for square root)
        """
        super().__init__(name="MarketImpact")
        self.impact_coefficient = impact_coefficient
        self.impact_exponent = impact_exponent
    
    def calculate_cost(self, order_size: float, price: float, **kwargs) -> float:
        """
        Calculate market impact cost using power law model.
        
        Args:
            order_size: Size of the order
            price: Current market price
            adv: Average daily volume (optional)
            
        Returns:
            Market impact cost
        """
        # Get average daily volume
        adv = kwargs.get('adv', 1000000)  # Default ADV
        
        # Calculate participation rate
        participation_rate = order_size / adv
        
        # Power law impact model
        impact_pct = self.impact_coefficient * (participation_rate ** self.impact_exponent)
        
        # Convert to cost
        return price * order_size * impact_pct


class LinearImpactModel(MarketImpactModel):
    """Linear market impact model."""
    
    def __init__(self, impact_coefficient: float = 0.01):
        super().__init__(impact_coefficient=impact_coefficient, impact_exponent=1.0)
        self.name = "LinearImpact"


class SquareRootImpactModel(MarketImpactModel):
    """Square root market impact model (most common)."""
    
    def __init__(self, impact_coefficient: float = 0.1):
        super().__init__(impact_coefficient=impact_coefficient, impact_exponent=0.5)
        self.name = "SquareRootImpact"


class FundingCostModel(CostModel):
    """
    Funding cost model for leveraged positions.
    
    This model calculates the funding costs for holding leveraged
    positions in perpetual futures.
    """
    
    def __init__(self, funding_rate: float = 0.0001):
        """
        Initialize funding cost model.
        
        Args:
            funding_rate: Funding rate per 8 hours (0.01%)
        """
        super().__init__(name="FundingCost")
        self.funding_rate = funding_rate
        self.funding_interval_hours = 8
    
    def calculate_cost(self, position_value: float, holding_hours: float, **kwargs) -> float:
        """
        Calculate funding cost.
        
        Args:
            position_value: Value of the position
            holding_hours: Hours position is held
            
        Returns:
            Funding cost
        """
        # Number of funding intervals
        num_intervals = holding_hours / self.funding_interval_hours
        
        # Total funding cost
        return position_value * self.funding_rate * num_intervals


class BorrowCostModel(CostModel):
    """
    Borrow cost model for short positions.
    
    This model calculates the cost of borrowing assets for short selling.
    """
    
    def __init__(self, borrow_rate: float = 0.05):
        """
        Initialize borrow cost model.
        
        Args:
            borrow_rate: Annual borrow rate (5% = 0.05)
        """
        super().__init__(name="BorrowCost")
        self.borrow_rate = borrow_rate
    
    def calculate_cost(self, position_value: float, holding_days: float, **kwargs) -> float:
        """
        Calculate borrow cost.
        
        Args:
            position_value: Value of the short position
            holding_days: Days position is held
            
        Returns:
            Borrow cost
        """
        # Daily borrow cost
        daily_rate = self.borrow_rate / 365
        
        return position_value * daily_rate * holding_days


class CompositeCostModel(CostModel):
    """
    Composite cost model combining multiple cost components.
    
    This model allows combining different cost models to create
    a comprehensive transaction cost estimate.
    """
    
    def __init__(self, models: Dict[str, CostModel], weights: Optional[Dict[str, float]] = None):
        """
        Initialize composite cost model.
        
        Args:
            models: Dictionary of cost models
            weights: Optional weights for each model
        """
        super().__init__(name="CompositeCost")
        self.models = models
        self.weights = weights or {name: 1.0 for name in models}
    
    def calculate_cost(self, **kwargs) -> float:
        """
        Calculate total cost from all models.
        
        Returns:
            Total transaction cost
        """
        total_cost = 0.0
        
        for name, model in self.models.items():
            weight = self.weights.get(name, 1.0)
            cost = model.calculate_cost(**kwargs)
            total_cost += weight * cost
        
        return total_cost
    
    def get_cost_breakdown(self, **kwargs) -> Dict[str, float]:
        """
        Get breakdown of costs by component.
        
        Returns:
            Dictionary of cost components
        """
        breakdown = {}
        
        for name, model in self.models.items():
            weight = self.weights.get(name, 1.0)
            cost = model.calculate_cost(**kwargs)
            breakdown[name] = weight * cost
        
        breakdown['total'] = sum(breakdown.values())
        return breakdown


class CryptoTransactionCosts:
    """
    Comprehensive transaction cost calculator for cryptocurrency trading.
    
    This class provides realistic cost estimates for crypto trading
    including exchange fees, spread costs, and market impact.
    """
    
    def __init__(
        self,
        maker_fee: float = 0.0006,
        taker_fee: float = 0.001,
        spread_bps: float = 5.0,
        impact_coefficient: float = 0.1,
        funding_rate: float = 0.0001
    ):
        """
        Initialize crypto transaction cost calculator.
        
        Args:
            maker_fee: Maker fee rate
            taker_fee: Taker fee rate
            spread_bps: Typical spread in basis points
            impact_coefficient: Market impact coefficient
            funding_rate: Funding rate for perpetuals
        """
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        
        # Initialize cost models
        self.spread_model = SpreadCostModel(spread_bps)
        self.impact_model = SquareRootImpactModel(impact_coefficient)
        self.funding_model = FundingCostModel(funding_rate)
    
    def calculate_trade_cost(
        self,
        order_size: float,
        price: float,
        order_type: str = 'MARKET',
        adv: float = 1000000,
        include_impact: bool = True
    ) -> Dict[str, float]:
        """
        Calculate total trading cost.
        
        Args:
            order_size: Size of the order
            price: Current market price
            order_type: MARKET or LIMIT
            adv: Average daily volume
            include_impact: Whether to include market impact
            
        Returns:
            Dictionary with cost breakdown
        """
        costs = {}
        
        # Exchange fees
        if order_type == 'MARKET':
            costs['exchange_fee'] = self.taker_fee * order_size * price
            costs['spread_cost'] = self.spread_model.calculate_cost(order_size, price)
        else:  # LIMIT
            costs['exchange_fee'] = self.maker_fee * order_size * price
            costs['spread_cost'] = 0  # Limit orders don't pay spread
        
        # Market impact (for large orders)
        if include_impact:
            costs['market_impact'] = self.impact_model.calculate_cost(
                order_size, price, adv=adv
            )
        else:
            costs['market_impact'] = 0
        
        costs['total'] = sum(costs.values())
        
        return costs
    
    def calculate_holding_cost(
        self,
        position_value: float,
        holding_hours: float,
        is_short: bool = False
    ) -> Dict[str, float]:
        """
        Calculate cost of holding a position.
        
        Args:
            position_value: Value of the position
            holding_hours: Hours position is held
            is_short: Whether position is short
            
        Returns:
            Dictionary with holding costs
        """
        costs = {}
        
        # Funding costs (for perpetuals)
        costs['funding'] = self.funding_model.calculate_cost(
            position_value, holding_hours
        )
        
        # Additional costs for shorts
        if is_short:
            holding_days = holding_hours / 24
            borrow_model = BorrowCostModel()
            costs['borrow'] = borrow_model.calculate_cost(
                position_value, holding_days
            )
        
        costs['total'] = sum(costs.values())
        
        return costs