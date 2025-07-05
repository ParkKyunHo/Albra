"""
Natural Language Strategy Builder

This module provides natural language processing capabilities to convert
user-described trading strategies into executable strategy objects.

Key Features:
- Pattern recognition for common trading concepts
- Technical indicator parsing
- Entry/exit condition interpretation
- Risk management parameter extraction
- Strategy code generation
"""

import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
import json
import logging

from .base import BaseStrategy, StrategyParameters
from .indicators import Indicators

logger = logging.getLogger(__name__)


@dataclass
class StrategyBlueprint:
    """Container for parsed strategy components."""
    name: str
    description: str
    indicators: List[Dict[str, Any]]
    entry_conditions: Dict[str, List[Dict[str, Any]]]
    exit_conditions: Dict[str, List[Dict[str, Any]]]
    risk_parameters: Dict[str, Any]
    position_sizing: Dict[str, Any]
    metadata: Dict[str, Any]


class NLStrategyParser:
    """
    Natural language parser for trading strategies.
    
    This class analyzes natural language descriptions and extracts
    structured strategy components.
    """
    
    def __init__(self):
        """Initialize parser with pattern mappings."""
        self.indicator_patterns = self._build_indicator_patterns()
        self.condition_patterns = self._build_condition_patterns()
        self.risk_patterns = self._build_risk_patterns()
        
    def _build_indicator_patterns(self) -> Dict[str, Dict[str, Any]]:
        """Build pattern mappings for technical indicators."""
        return {
            # Moving Averages
            r'(\d+)[-\s]?(day|period|기간)?\s*(이동평균|moving average|ma|sma)': {
                'type': 'SMA',
                'params': ['period'],
                'extract': lambda m: {'period': int(m.group(1))}
            },
            r'(\d+)[-\s]?(day|period|기간)?\s*(지수이동평균|exponential moving average|ema)': {
                'type': 'EMA',
                'params': ['period'],
                'extract': lambda m: {'period': int(m.group(1))}
            },
            r'(\d+),?\s*(\d+)\s*(macd|맥디)': {
                'type': 'MACD',
                'params': ['fast', 'slow'],
                'extract': lambda m: {'fast': int(m.group(1)), 'slow': int(m.group(2))}
            },
            
            # RSI
            r'(\d+)[-\s]?(period|기간)?\s*(rsi|상대강도지수)': {
                'type': 'RSI',
                'params': ['period'],
                'extract': lambda m: {'period': int(m.group(1))}
            },
            
            # Bollinger Bands
            r'(\d+)[-\s]?(period|기간)?\s*(\d+\.?\d*)?\s*(표준편차|std|sigma)?\s*(볼린저|bollinger|bb)': {
                'type': 'BOLLINGER',
                'params': ['period', 'std_dev'],
                'extract': lambda m: {
                    'period': int(m.group(1)),
                    'std_dev': float(m.group(3)) if m.group(3) else 2.0
                }
            },
            
            # ATR
            r'(\d+)[-\s]?(period|기간)?\s*(atr|평균진폭)': {
                'type': 'ATR',
                'params': ['period'],
                'extract': lambda m: {'period': int(m.group(1))}
            },
            
            # Ichimoku
            r'(이치모쿠|ichimoku|일목균형표)': {
                'type': 'ICHIMOKU',
                'params': [],
                'extract': lambda m: {}
            }
        }
    
    def _build_condition_patterns(self) -> Dict[str, Dict[str, Any]]:
        """Build pattern mappings for entry/exit conditions."""
        return {
            # Crossover patterns
            r'(golden cross|골든크로스|골든 크로스)': {
                'type': 'GOLDEN_CROSS',
                'condition': 'fast_ma > slow_ma and prev_fast_ma <= prev_slow_ma'
            },
            r'(death cross|dead cross|데드크로스|데드 크로스)': {
                'type': 'DEATH_CROSS',
                'condition': 'fast_ma < slow_ma and prev_fast_ma >= prev_slow_ma'
            },
            
            # Price action
            r'(가격|price).*(위|above|over)\s*(.+)': {
                'type': 'PRICE_ABOVE',
                'extract': lambda m: {'target': m.group(3)}
            },
            r'(가격|price).*(아래|below|under)\s*(.+)': {
                'type': 'PRICE_BELOW',
                'extract': lambda m: {'target': m.group(3)}
            },
            
            # RSI conditions
            r'rsi.*(과매수|overbought|초과|above|over)\s*(\d+)': {
                'type': 'RSI_OVERBOUGHT',
                'extract': lambda m: {'level': int(m.group(2))}
            },
            r'rsi.*(과매도|oversold|미만|below|under)\s*(\d+)': {
                'type': 'RSI_OVERSOLD',
                'extract': lambda m: {'level': int(m.group(2))}
            },
            
            # Breakout patterns
            r'(돌파|breakout|break out|브레이크아웃)': {
                'type': 'BREAKOUT',
                'condition': 'price > resistance'
            },
            
            # Trend conditions
            r'(상승추세|uptrend|up trend|상승 추세)': {
                'type': 'UPTREND',
                'condition': 'ma_short > ma_medium > ma_long'
            },
            r'(하락추세|downtrend|down trend|하락 추세)': {
                'type': 'DOWNTREND',
                'condition': 'ma_short < ma_medium < ma_long'
            }
        }
    
    def _build_risk_patterns(self) -> Dict[str, Dict[str, Any]]:
        """Build pattern mappings for risk management."""
        return {
            # Stop loss
            r'(손절|stop loss|스톱로스|sl).*([\d.]+)\s*(%|퍼센트|percent)': {
                'type': 'STOP_LOSS_PERCENT',
                'extract': lambda m: {'value': float(m.group(2))}
            },
            r'(손절|stop loss|스톱로스|sl).*([\d.]+)\s*(atr)': {
                'type': 'STOP_LOSS_ATR',
                'extract': lambda m: {'multiplier': float(m.group(2))}
            },
            
            # Take profit
            r'(익절|take profit|테이크프로핏|tp).*([\d.]+)\s*(%|퍼센트|percent)': {
                'type': 'TAKE_PROFIT_PERCENT',
                'extract': lambda m: {'value': float(m.group(2))}
            },
            r'(익절|take profit|테이크프로핏|tp).*([\d.]+)\s*(atr)': {
                'type': 'TAKE_PROFIT_ATR',
                'extract': lambda m: {'multiplier': float(m.group(2))}
            },
            
            # Position sizing
            r'(포지션|position).*([\d.]+)\s*(%|퍼센트|percent)': {
                'type': 'POSITION_SIZE_PERCENT',
                'extract': lambda m: {'value': float(m.group(2))}
            },
            r'(kelly|켈리)': {
                'type': 'KELLY_CRITERION',
                'extract': lambda m: {}
            },
            
            # Risk per trade
            r'(리스크|risk).*([\d.]+)\s*(%|퍼센트|percent)': {
                'type': 'RISK_PER_TRADE',
                'extract': lambda m: {'value': float(m.group(2))}
            }
        }
    
    def parse(self, description: str) -> StrategyBlueprint:
        """
        Parse natural language strategy description.
        
        Args:
            description: Natural language strategy description
            
        Returns:
            StrategyBlueprint with parsed components
        """
        logger.info(f"Parsing strategy description: {description[:100]}...")
        
        # Extract components
        indicators = self._extract_indicators(description)
        entry_conditions = self._extract_entry_conditions(description)
        exit_conditions = self._extract_exit_conditions(description)
        risk_params = self._extract_risk_parameters(description)
        position_sizing = self._extract_position_sizing(description)
        
        # Generate strategy name
        name = self._generate_strategy_name(indicators, entry_conditions)
        
        blueprint = StrategyBlueprint(
            name=name,
            description=description,
            indicators=indicators,
            entry_conditions=entry_conditions,
            exit_conditions=exit_conditions,
            risk_parameters=risk_params,
            position_sizing=position_sizing,
            metadata={
                'source': 'natural_language',
                'original_description': description
            }
        )
        
        logger.info(f"Parsed strategy blueprint: {name}")
        return blueprint
    
    def _extract_indicators(self, text: str) -> List[Dict[str, Any]]:
        """Extract technical indicators from text."""
        indicators = []
        text_lower = text.lower()
        
        for pattern, config in self.indicator_patterns.items():
            matches = re.finditer(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                indicator = {
                    'type': config['type'],
                    'params': config['extract'](match) if 'extract' in config else {}
                }
                if indicator not in indicators:
                    indicators.append(indicator)
        
        return indicators
    
    def _extract_entry_conditions(self, text: str) -> Dict[str, List[Dict[str, Any]]]:
        """Extract entry conditions from text."""
        conditions = {'long': [], 'short': []}
        
        # Look for long entry keywords
        long_keywords = ['매수', 'buy', '롱', 'long', '진입', 'entry']
        short_keywords = ['매도', 'sell', '숏', 'short']
        
        # Split text into sentences
        sentences = re.split(r'[.!?;]', text)
        
        for sentence in sentences:
            sentence_lower = sentence.lower()
            
            # Determine if this is about long or short
            is_long = any(keyword in sentence_lower for keyword in long_keywords)
            is_short = any(keyword in sentence_lower for keyword in short_keywords)
            
            # Extract conditions from sentence
            for pattern, config in self.condition_patterns.items():
                if re.search(pattern, sentence_lower, re.IGNORECASE):
                    condition = {
                        'type': config['type'],
                        'params': config.get('extract', lambda m: {})(
                            re.search(pattern, sentence_lower, re.IGNORECASE)
                        ) if 'extract' in config else {}
                    }
                    
                    if is_long and condition not in conditions['long']:
                        conditions['long'].append(condition)
                    elif is_short and condition not in conditions['short']:
                        conditions['short'].append(condition)
        
        return conditions
    
    def _extract_exit_conditions(self, text: str) -> Dict[str, List[Dict[str, Any]]]:
        """Extract exit conditions from text."""
        conditions = {'stop_loss': [], 'take_profit': [], 'trailing_stop': [], 'signal_exit': []}
        
        # Look for exit keywords
        exit_keywords = ['청산', 'exit', '종료', 'close', '익절', '손절']
        
        sentences = re.split(r'[.!?;]', text)
        
        for sentence in sentences:
            sentence_lower = sentence.lower()
            
            if any(keyword in sentence_lower for keyword in exit_keywords):
                # Check for specific exit types
                if any(word in sentence_lower for word in ['손절', 'stop loss', '스톱']):
                    for pattern, config in self.risk_patterns.items():
                        if 'STOP_LOSS' in config.get('type', ''):
                            match = re.search(pattern, sentence_lower, re.IGNORECASE)
                            if match:
                                conditions['stop_loss'].append({
                                    'type': config['type'],
                                    'params': config['extract'](match)
                                })
                
                elif any(word in sentence_lower for word in ['익절', 'take profit', '목표']):
                    for pattern, config in self.risk_patterns.items():
                        if 'TAKE_PROFIT' in config.get('type', ''):
                            match = re.search(pattern, sentence_lower, re.IGNORECASE)
                            if match:
                                conditions['take_profit'].append({
                                    'type': config['type'],
                                    'params': config['extract'](match)
                                })
        
        return conditions
    
    def _extract_risk_parameters(self, text: str) -> Dict[str, Any]:
        """Extract risk management parameters from text."""
        risk_params = {
            'max_position_size': 0.1,  # Default 10%
            'max_risk_per_trade': 0.02,  # Default 2%
            'max_drawdown': 0.2,  # Default 20%
            'use_trailing_stop': False,
            'use_partial_exits': False
        }
        
        text_lower = text.lower()
        
        # Extract specific risk values
        for pattern, config in self.risk_patterns.items():
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                if config['type'] == 'RISK_PER_TRADE':
                    risk_params['max_risk_per_trade'] = config['extract'](match)['value'] / 100
                elif config['type'] == 'POSITION_SIZE_PERCENT':
                    risk_params['max_position_size'] = config['extract'](match)['value'] / 100
        
        # Check for trailing stop
        if any(word in text_lower for word in ['trailing stop', '트레일링', '추적손절']):
            risk_params['use_trailing_stop'] = True
        
        # Check for partial exits
        if any(word in text_lower for word in ['부분청산', 'partial', '분할청산']):
            risk_params['use_partial_exits'] = True
        
        return risk_params
    
    def _extract_position_sizing(self, text: str) -> Dict[str, Any]:
        """Extract position sizing method from text."""
        text_lower = text.lower()
        
        if any(word in text_lower for word in ['kelly', '켈리']):
            return {
                'method': 'kelly',
                'kelly_fraction': 0.25  # Conservative Kelly
            }
        elif any(word in text_lower for word in ['고정', 'fixed']):
            return {
                'method': 'fixed',
                'size': 0.1  # Default 10%
            }
        else:
            return {
                'method': 'risk_based',
                'risk_per_trade': 0.02  # Default 2%
            }
    
    def _generate_strategy_name(self, indicators: List[Dict], conditions: Dict) -> str:
        """Generate a descriptive strategy name."""
        parts = []
        
        # Add main indicators
        for ind in indicators[:2]:  # Use first 2 indicators
            parts.append(ind['type'])
        
        # Add main condition type
        if conditions.get('long'):
            if any(c['type'] == 'GOLDEN_CROSS' for c in conditions['long']):
                parts.append('CrossOver')
            elif any(c['type'] == 'BREAKOUT' for c in conditions['long']):
                parts.append('Breakout')
        
        if not parts:
            parts = ['Custom', 'Strategy']
        
        return '_'.join(parts)


class StrategyGenerator:
    """
    Generate executable strategy code from blueprint.
    
    This class converts parsed strategy blueprints into
    actual strategy implementations.
    """
    
    def __init__(self):
        """Initialize strategy generator."""
        self.template = self._load_template()
    
    def _load_template(self) -> str:
        """Load strategy code template."""
        return '''"""
Generated strategy from natural language description.
"""

from typing import Optional, Dict, Any, List
from backtest.strategies.base import BaseStrategy, StrategyParameters
from backtest.core.events import MarketEvent, SignalEvent


class {class_name}(BaseStrategy):
    """
    {description}
    
    Generated from natural language description.
    """
    
    def __init__(self):
        """Initialize strategy."""
        super().__init__(StrategyParameters(
            position_size={position_size},
            stop_loss={stop_loss},
            take_profit={take_profit},
            use_trailing_stop={use_trailing_stop}
        ))
        
        # Strategy-specific parameters
{parameters}
    
    @property
    def name(self) -> str:
        """Strategy name."""
        return "{strategy_name}"
    
    @property
    def required_indicators(self) -> List[str]:
        """Required indicators for this strategy."""
        return {required_indicators}
    
    def generate_signal(self, market_event: MarketEvent) -> Optional[SignalEvent]:
        """Generate trading signal."""
        # Calculate indicators
{indicator_calculations}
        
        # Check entry conditions
{entry_conditions}
        
        # Check exit conditions
{exit_conditions}
        
        return None
'''
    
    def generate(self, blueprint: StrategyBlueprint) -> str:
        """
        Generate strategy code from blueprint.
        
        Args:
            blueprint: Parsed strategy blueprint
            
        Returns:
            Generated Python code
        """
        class_name = blueprint.name.replace('_', '')
        
        # Generate parameter initialization
        parameters = self._generate_parameters(blueprint)
        
        # Generate indicator calculations
        indicator_calculations = self._generate_indicator_calculations(blueprint.indicators)
        
        # Generate entry conditions
        entry_conditions = self._generate_entry_conditions(blueprint.entry_conditions)
        
        # Generate exit conditions
        exit_conditions = self._generate_exit_conditions(blueprint.exit_conditions)
        
        # Extract risk parameters
        stop_loss = blueprint.risk_parameters.get('stop_loss', 0.02)
        take_profit = blueprint.risk_parameters.get('take_profit', 0.05)
        position_size = blueprint.position_sizing.get('size', 0.1)
        use_trailing_stop = blueprint.risk_parameters.get('use_trailing_stop', False)
        
        # Generate required indicators list
        required_indicators = self._generate_required_indicators(blueprint.indicators)
        
        # Fill template
        code = self.template.format(
            class_name=class_name,
            description=blueprint.description,
            strategy_name=blueprint.name,
            position_size=position_size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            use_trailing_stop=str(use_trailing_stop),
            parameters=parameters,
            required_indicators=required_indicators,
            indicator_calculations=indicator_calculations,
            entry_conditions=entry_conditions,
            exit_conditions=exit_conditions
        )
        
        return code
    
    def _generate_parameters(self, blueprint: StrategyBlueprint) -> str:
        """Generate parameter initialization code."""
        lines = []
        
        # Extract unique parameters from indicators
        for indicator in blueprint.indicators:
            for param_name, param_value in indicator.get('params', {}).items():
                lines.append(f"        self.{indicator['type'].lower()}_{param_name} = {param_value}")
        
        return '\n'.join(lines) if lines else "        pass"
    
    def _generate_required_indicators(self, indicators: List[Dict]) -> str:
        """Generate list of required indicators."""
        ind_list = []
        for indicator in indicators:
            ind_type = indicator['type'].lower()
            ind_list.append(f"'{ind_type}'")
        
        # Add basic indicators that might be needed
        if "'sma'" not in ind_list:
            ind_list.append("'sma'")
        if "'ema'" not in ind_list:
            ind_list.append("'ema'")
        
        return '[' + ', '.join(ind_list) + ']'
    
    def _generate_indicator_calculations(self, indicators: List[Dict]) -> str:
        """Generate indicator calculation code."""
        lines = ["        indicators = {}"]
        
        for indicator in indicators:
            ind_type = indicator['type']
            params = indicator.get('params', {})
            
            if ind_type == 'SMA':
                lines.append(f"        indicators['sma_{params['period']}'] = "
                           f"self.calculate_sma(market_event.close_history, {params['period']})")
            elif ind_type == 'EMA':
                lines.append(f"        indicators['ema_{params['period']}'] = "
                           f"self.calculate_ema(market_event.close_history, {params['period']})")
            elif ind_type == 'RSI':
                lines.append(f"        indicators['rsi'] = "
                           f"self.calculate_rsi(market_event.close_history, {params['period']})")
            elif ind_type == 'MACD':
                lines.append(f"        macd, signal, hist = "
                           f"self.calculate_macd(market_event.close_history, "
                           f"{params['fast']}, {params['slow']})")
                lines.append("        indicators['macd'] = macd")
                lines.append("        indicators['macd_signal'] = signal")
                lines.append("        indicators['macd_hist'] = hist")
        
        return '\n'.join(lines)
    
    def _generate_entry_conditions(self, conditions: Dict[str, List[Dict]]) -> str:
        """Generate entry condition code."""
        lines = []
        
        # Long conditions
        if conditions.get('long'):
            lines.append("        # Long entry conditions")
            long_checks = []
            
            for condition in conditions['long']:
                if condition['type'] == 'GOLDEN_CROSS':
                    long_checks.append("(fast_ma > slow_ma and prev_fast_ma <= prev_slow_ma)")
                elif condition['type'] == 'RSI_OVERSOLD':
                    long_checks.append(f"indicators['rsi'] < {condition['params']['level']}")
                elif condition['type'] == 'PRICE_ABOVE':
                    target = condition['params']['target']
                    long_checks.append(f"market_event.close > indicators['{target}']")
            
            if long_checks:
                lines.append(f"        if {' and '.join(long_checks)}:")
                lines.append("            return self.create_signal(")
                lines.append("                timestamp=market_event.timestamp,")
                lines.append("                symbol=market_event.symbol,")
                lines.append("                signal_type='BUY',")
                lines.append("                strength=1.0")
                lines.append("            )")
        
        # Short conditions
        if conditions.get('short'):
            lines.append("\n        # Short entry conditions")
            short_checks = []
            
            for condition in conditions['short']:
                if condition['type'] == 'DEATH_CROSS':
                    short_checks.append("(fast_ma < slow_ma and prev_fast_ma >= prev_slow_ma)")
                elif condition['type'] == 'RSI_OVERBOUGHT':
                    short_checks.append(f"indicators['rsi'] > {condition['params']['level']}")
                elif condition['type'] == 'PRICE_BELOW':
                    target = condition['params']['target']
                    short_checks.append(f"market_event.close < indicators['{target}']")
            
            if short_checks:
                lines.append(f"        if {' and '.join(short_checks)}:")
                lines.append("            return self.create_signal(")
                lines.append("                timestamp=market_event.timestamp,")
                lines.append("                symbol=market_event.symbol,")
                lines.append("                signal_type='SELL',")
                lines.append("                strength=1.0")
                lines.append("            )")
        
        return '\n'.join(lines) if lines else "        pass"
    
    def _generate_exit_conditions(self, conditions: Dict[str, List[Dict]]) -> str:
        """Generate exit condition code."""
        lines = ["        # Exit conditions are handled by position manager"]
        lines.append("        # (stop loss, take profit, trailing stop)")
        
        # Add custom exit conditions if any
        if conditions.get('signal_exit'):
            lines.append("\n        # Custom exit signals")
            lines.append("        # TODO: Implement custom exit logic")
        
        return '\n'.join(lines)


class NaturalLanguageStrategyBuilder:
    """
    Main interface for natural language strategy building.
    
    This class orchestrates the parsing and generation process.
    """
    
    def __init__(self):
        """Initialize builder components."""
        self.parser = NLStrategyParser()
        self.generator = StrategyGenerator()
        
        # Strategy examples for reference
        self.examples = self._load_examples()
    
    def _load_examples(self) -> List[Dict[str, str]]:
        """Load example strategy descriptions."""
        return [
            {
                'description': "20일 이동평균선과 50일 이동평균선의 골든크로스에서 매수, 데드크로스에서 매도. 손절은 2%, 익절은 5%로 설정.",
                'name': "MA_CrossOver"
            },
            {
                'description': "RSI가 30 이하로 과매도 상태일 때 매수, 70 이상으로 과매수 상태일 때 매도. ATR의 1.5배로 손절, 3배로 익절.",
                'name': "RSI_Reversal"
            },
            {
                'description': "MACD 히스토그램이 0선을 상향 돌파하면 매수, 하향 돌파하면 매도. 켈리 기준으로 포지션 사이징.",
                'name': "MACD_Momentum"
            },
            {
                'description': "볼린저 밴드 하단 터치 후 반등 시 매수, 상단 터치 후 하락 시 매도. 트레일링 스톱 사용.",
                'name': "Bollinger_Reversal"
            }
        ]
    
    def build_strategy(self, description: str) -> Tuple[str, StrategyBlueprint]:
        """
        Build strategy from natural language description.
        
        Args:
            description: Natural language strategy description
            
        Returns:
            Tuple of (generated_code, blueprint)
        """
        logger.info(f"Building strategy from description: {description[:100]}...")
        
        # Parse description
        blueprint = self.parser.parse(description)
        
        # Generate code
        code = self.generator.generate(blueprint)
        
        # Log success
        logger.info(f"Successfully generated strategy: {blueprint.name}")
        
        return code, blueprint
    
    def suggest_improvements(self, blueprint: StrategyBlueprint) -> List[str]:
        """
        Suggest improvements for the strategy.
        
        Args:
            blueprint: Strategy blueprint
            
        Returns:
            List of improvement suggestions
        """
        suggestions = []
        
        # Check for risk management
        if not blueprint.risk_parameters.get('stop_loss'):
            suggestions.append("손절 설정을 추가하는 것을 권장합니다 (예: 2% 또는 1.5 ATR)")
        
        if not blueprint.risk_parameters.get('take_profit'):
            suggestions.append("익절 목표를 설정하는 것을 권장합니다 (예: 5% 또는 3 ATR)")
        
        # Check for position sizing
        if blueprint.position_sizing.get('method') == 'fixed':
            suggestions.append("Kelly Criterion이나 리스크 기반 포지션 사이징을 고려해보세요")
        
        # Check for multiple confirmation
        if len(blueprint.indicators) < 2:
            suggestions.append("여러 지표를 조합하여 신호를 확인하는 것이 좋습니다")
        
        # Check for market regime filter
        has_trend_filter = any(ind['type'] in ['ADX', 'TREND'] for ind in blueprint.indicators)
        if not has_trend_filter:
            suggestions.append("시장 상태 필터 (예: ADX > 25)를 추가하여 횡보장을 피하세요")
        
        return suggestions
    
    def validate_strategy(self, code: str) -> Dict[str, Any]:
        """
        Validate generated strategy code.
        
        Args:
            code: Generated Python code
            
        Returns:
            Validation results
        """
        results = {
            'valid': True,
            'errors': [],
            'warnings': []
        }
        
        try:
            # Try to compile the code
            compile(code, '<string>', 'exec')
        except SyntaxError as e:
            results['valid'] = False
            results['errors'].append(f"Syntax error: {e}")
        
        # Check for required methods
        required_methods = ['generate_signal', 'name']
        for method in required_methods:
            if f"def {method}" not in code and f"def {method}" not in code:
                results['warnings'].append(f"Missing required method: {method}")
        
        # Check for basic structure
        if 'class' not in code:
            results['valid'] = False
            results['errors'].append("No class definition found")
        
        if 'BaseStrategy' not in code:
            results['warnings'].append("Strategy should inherit from BaseStrategy")
        
        return results
    
    def get_examples(self) -> List[Dict[str, str]]:
        """Get example strategy descriptions."""
        return self.examples
    
    def explain_strategy(self, blueprint: StrategyBlueprint) -> str:
        """
        Generate human-readable explanation of the strategy.
        
        Args:
            blueprint: Strategy blueprint
            
        Returns:
            Strategy explanation
        """
        explanation = []
        
        explanation.append(f"전략명: {blueprint.name}")
        explanation.append(f"설명: {blueprint.description}\n")
        
        explanation.append("사용 지표:")
        for ind in blueprint.indicators:
            params_str = ', '.join(f"{k}={v}" for k, v in ind.get('params', {}).items())
            explanation.append(f"  - {ind['type']}({params_str})")
        
        explanation.append("\n진입 조건:")
        if blueprint.entry_conditions.get('long'):
            explanation.append("  매수:")
            for cond in blueprint.entry_conditions['long']:
                explanation.append(f"    - {cond['type']}")
        
        if blueprint.entry_conditions.get('short'):
            explanation.append("  매도:")
            for cond in blueprint.entry_conditions['short']:
                explanation.append(f"    - {cond['type']}")
        
        explanation.append("\n리스크 관리:")
        for key, value in blueprint.risk_parameters.items():
            if value:
                explanation.append(f"  - {key}: {value}")
        
        explanation.append("\n포지션 사이징:")
        explanation.append(f"  - 방법: {blueprint.position_sizing.get('method', 'fixed')}")
        
        return '\n'.join(explanation)


# Example usage function
def create_strategy_from_description(description: str) -> str:
    """
    Create a strategy from natural language description.
    
    Args:
        description: Natural language strategy description
        
    Returns:
        Generated strategy code
    """
    builder = NaturalLanguageStrategyBuilder()
    
    # Build strategy
    code, blueprint = builder.build_strategy(description)
    
    # Validate
    validation = builder.validate_strategy(code)
    if not validation['valid']:
        raise ValueError(f"Invalid strategy code: {validation['errors']}")
    
    # Get suggestions
    suggestions = builder.suggest_improvements(blueprint)
    if suggestions:
        logger.info("Improvement suggestions:")
        for suggestion in suggestions:
            logger.info(f"  - {suggestion}")
    
    # Explain strategy
    explanation = builder.explain_strategy(blueprint)
    logger.info(f"\nStrategy explanation:\n{explanation}")
    
    return code