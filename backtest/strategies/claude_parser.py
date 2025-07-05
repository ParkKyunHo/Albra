"""
Claude API-based Natural Language Strategy Parser

This module uses Claude API for advanced natural language understanding
to convert complex trading strategy descriptions into executable code.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
import anthropic
from datetime import datetime

from .builder import StrategyBlueprint, NaturalLanguageStrategyBuilder

logger = logging.getLogger(__name__)


class ClaudeStrategyParser:
    """
    Advanced strategy parser using Claude API for natural language understanding.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Claude API client.
        
        Args:
            api_key: Anthropic API key. If not provided, will look for ANTHROPIC_API_KEY env var.
        """
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("Anthropic API key is required. Set ANTHROPIC_API_KEY environment variable.")
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model = "claude-3-opus-20240229"  # Use latest model
        
    def parse_strategy(self, description: str, language: str = "auto") -> StrategyBlueprint:
        """
        Parse strategy description using Claude API.
        
        Args:
            description: Natural language strategy description
            language: Language hint ("ko", "en", or "auto")
            
        Returns:
            StrategyBlueprint object with parsed components
        """
        # Detect language if auto
        if language == "auto":
            language = self._detect_language(description)
        
        # Create prompt for Claude
        prompt = self._create_parsing_prompt(description, language)
        
        try:
            # Call Claude API
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                temperature=0.1,  # Low temperature for consistent parsing
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            # Extract JSON from response
            content = response.content[0].text
            parsed_json = self._extract_json_from_response(content)
            
            # Validate and convert to StrategyBlueprint
            blueprint = self._json_to_blueprint(parsed_json, description)
            
            return blueprint
            
        except Exception as e:
            logger.error(f"Claude API error: {str(e)}")
            raise
    
    def _detect_language(self, text: str) -> str:
        """Simple language detection based on character patterns."""
        korean_chars = sum(1 for char in text if '가' <= char <= '힣')
        total_chars = len(text.replace(' ', ''))
        
        if korean_chars / total_chars > 0.3:
            return "ko"
        return "en"
    
    def _create_parsing_prompt(self, description: str, language: str) -> str:
        """Create a detailed prompt for Claude to parse the strategy."""
        
        system_context = """You are an expert trading strategy analyst. 
Parse the given trading strategy description and extract structured information.
Focus on identifying:
1. Technical indicators and their parameters
2. Entry conditions (when to buy/sell)
3. Exit conditions (when to close positions)
4. Risk management rules (stop loss, take profit)
5. Position sizing rules

Return the result as a valid JSON object."""

        if language == "ko":
            instructions = """다음 트레이딩 전략 설명을 분석하여 JSON 형식으로 변환하세요.
주의사항:
- 모든 지표의 파라미터를 정확히 추출
- 진입/청산 조건의 논리적 관계 파악
- 리스크 관리 규칙 명확히 구분
- 애매한 표현은 일반적인 트레이딩 관행으로 해석"""
        else:
            instructions = """Analyze the following trading strategy description and convert it to JSON format.
Guidelines:
- Extract all indicator parameters accurately
- Identify logical relationships in entry/exit conditions
- Clearly distinguish risk management rules
- Interpret ambiguous expressions using common trading practices"""

        json_template = """{
    "name": "Strategy name",
    "indicators": [
        {
            "type": "SMA/EMA/RSI/MACD/etc",
            "params": {"period": 20, ...},
            "variable_name": "sma_20"
        }
    ],
    "entry_conditions": {
        "long": [
            {
                "condition": "price > sma_20 AND rsi < 30",
                "description": "Buy when price above SMA and RSI oversold"
            }
        ],
        "short": [...]
    },
    "exit_conditions": {
        "stop_loss": {
            "type": "percent/atr/fixed",
            "value": 2.0,
            "description": "2% stop loss"
        },
        "take_profit": {...},
        "trailing_stop": {...},
        "signal_exit": [...]
    },
    "position_sizing": {
        "type": "fixed_percent/kelly/risk_based",
        "value": 10.0,
        "max_position": 100.0
    },
    "filters": [
        {
            "type": "trend/volatility/time",
            "condition": "...",
            "description": "..."
        }
    ]
}"""

        return f"""{system_context}

{instructions}

Expected JSON format:
{json_template}

Strategy description:
{description}

Please respond with only the JSON object, no additional explanation."""

    def _extract_json_from_response(self, response: str) -> Dict[str, Any]:
        """Extract JSON object from Claude's response."""
        # Try to find JSON in the response
        import re
        
        # Look for JSON between ```json and ``` or just {...}
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find JSON object directly
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                raise ValueError("No JSON found in Claude's response")
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {json_str}")
            raise ValueError(f"Invalid JSON in response: {e}")
    
    def _json_to_blueprint(self, parsed_json: Dict[str, Any], original_description: str) -> StrategyBlueprint:
        """Convert parsed JSON to StrategyBlueprint object."""
        # Extract components with defaults
        indicators = parsed_json.get('indicators', [])
        entry_conditions = parsed_json.get('entry_conditions', {'long': [], 'short': []})
        exit_conditions = parsed_json.get('exit_conditions', {})
        position_sizing = parsed_json.get('position_sizing', {'type': 'fixed_percent', 'value': 10.0})
        
        # Build risk parameters
        risk_params = {}
        if 'stop_loss' in exit_conditions:
            sl = exit_conditions['stop_loss']
            if sl['type'] == 'percent':
                risk_params['stop_loss_pct'] = sl['value'] / 100
            elif sl['type'] == 'atr':
                risk_params['stop_loss_atr'] = sl['value']
        
        if 'take_profit' in exit_conditions:
            tp = exit_conditions['take_profit']
            if tp['type'] == 'percent':
                risk_params['take_profit_pct'] = tp['value'] / 100
            elif tp['type'] == 'atr':
                risk_params['take_profit_atr'] = tp['value']
        
        if 'trailing_stop' in exit_conditions:
            risk_params['use_trailing_stop'] = True
            risk_params['trailing_stop_pct'] = exit_conditions['trailing_stop'].get('value', 1.0) / 100
        
        # Create blueprint
        blueprint = StrategyBlueprint(
            name=parsed_json.get('name', 'Claude_Parsed_Strategy'),
            description=original_description,
            indicators=indicators,
            entry_conditions=entry_conditions,
            exit_conditions=exit_conditions,
            risk_parameters=risk_params,
            position_sizing=position_sizing,
            metadata={
                'parsed_by': 'claude_api',
                'parse_date': datetime.now().isoformat(),
                'model': self.model
            }
        )
        
        return blueprint
    
    def improve_strategy(self, blueprint: StrategyBlueprint) -> List[str]:
        """
        Use Claude to suggest improvements to the strategy.
        
        Args:
            blueprint: Current strategy blueprint
            
        Returns:
            List of improvement suggestions
        """
        prompt = f"""As a trading strategy expert, analyze this strategy and suggest improvements:

Strategy: {blueprint.name}
Description: {blueprint.description}

Current components:
- Indicators: {json.dumps(blueprint.indicators, indent=2)}
- Entry conditions: {json.dumps(blueprint.entry_conditions, indent=2)}
- Exit conditions: {json.dumps(blueprint.exit_conditions, indent=2)}
- Risk parameters: {json.dumps(blueprint.risk_parameters, indent=2)}

Please suggest 3-5 specific improvements focusing on:
1. Risk management enhancements
2. Entry/exit timing optimization
3. Additional filters to reduce false signals
4. Position sizing improvements

Format your response as a JSON array of strings."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            
            suggestions = self._extract_json_from_response(response.content[0].text)
            
            if isinstance(suggestions, list):
                return suggestions
            elif isinstance(suggestions, dict) and 'suggestions' in suggestions:
                return suggestions['suggestions']
            else:
                return ["Unable to parse improvement suggestions"]
                
        except Exception as e:
            logger.error(f"Failed to get improvements: {e}")
            return ["Error getting improvement suggestions"]


class HybridStrategyBuilder(NaturalLanguageStrategyBuilder):
    """
    Hybrid strategy builder that combines regex patterns with Claude API.
    Falls back to Claude when regex patterns don't match.
    """
    
    def __init__(self, api_key: Optional[str] = None, use_claude: bool = True):
        """
        Initialize hybrid builder.
        
        Args:
            api_key: Anthropic API key
            use_claude: Whether to use Claude API for unmatched patterns
        """
        super().__init__()
        self.use_claude = use_claude
        
        if self.use_claude:
            try:
                self.claude_parser = ClaudeStrategyParser(api_key)
                logger.info("Claude API initialized successfully")
            except Exception as e:
                logger.warning(f"Claude API initialization failed: {e}")
                self.use_claude = False
                self.claude_parser = None
        else:
            self.claude_parser = None
    
    def build_strategy(self, description: str, strategy_name: Optional[str] = None) -> Tuple[str, StrategyBlueprint]:
        """
        Build strategy using hybrid approach.
        
        First tries regex patterns, then falls back to Claude API if needed.
        """
        # First try regex-based parsing
        try:
            code, blueprint = super().build_strategy(description, strategy_name)
            
            # Check if parsing was successful
            if self._is_blueprint_complete(blueprint):
                logger.info("Strategy successfully parsed with regex patterns")
                return code, blueprint
            else:
                logger.info("Regex parsing incomplete, trying Claude API")
                
        except Exception as e:
            logger.warning(f"Regex parsing failed: {e}")
        
        # Fall back to Claude API if available
        if self.use_claude and self.claude_parser:
            try:
                logger.info("Using Claude API for advanced parsing")
                blueprint = self.claude_parser.parse_strategy(description)
                
                # Generate code from Claude-parsed blueprint
                code = self._generate_code(blueprint)
                
                return code, blueprint
                
            except Exception as e:
                logger.error(f"Claude API parsing failed: {e}")
                # Fall back to basic parsing
                return super().build_strategy(description, strategy_name)
        else:
            # No Claude API, use basic parsing
            return super().build_strategy(description, strategy_name)
    
    def _is_blueprint_complete(self, blueprint: StrategyBlueprint) -> bool:
        """Check if blueprint has minimum required components."""
        has_indicators = len(blueprint.indicators) > 0
        has_entry = len(blueprint.entry_conditions.get('long', [])) > 0 or \
                   len(blueprint.entry_conditions.get('short', [])) > 0
        has_risk = bool(blueprint.risk_parameters)
        
        return has_indicators and has_entry and has_risk


# Example usage
if __name__ == "__main__":
    # Example with Claude API
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if api_key:
        parser = ClaudeStrategyParser(api_key)
        
        # Korean example
        korean_strategy = """
        20일 이동평균선과 50일 이동평균선을 사용합니다.
        RSI 14일 기준으로 과매도 구간(30 이하)에서
        단기 이동평균이 장기 이동평균을 상향 돌파하면 매수합니다.
        
        손절은 진입가 대비 2%, 익절은 5%로 설정하고,
        3% 수익 시 트레일링 스톱을 활성화합니다.
        
        포지션 크기는 계좌의 10%로 제한합니다.
        """
        
        try:
            blueprint = parser.parse_strategy(korean_strategy)
            print(f"Parsed strategy: {blueprint.name}")
            print(f"Indicators: {len(blueprint.indicators)}")
            print(f"Entry conditions: {blueprint.entry_conditions}")
            
            # Get improvement suggestions
            suggestions = parser.improve_strategy(blueprint)
            print("\nImprovement suggestions:")
            for i, suggestion in enumerate(suggestions, 1):
                print(f"{i}. {suggestion}")
                
        except Exception as e:
            print(f"Error: {e}")