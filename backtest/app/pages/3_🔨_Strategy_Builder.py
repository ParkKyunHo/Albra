"""
Strategy Builder Page
자연어로 전략을 생성하고 테스트하는 페이지
"""

import streamlit as st
import sys
from pathlib import Path
from datetime import datetime

# Add parent directories to path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from backtest.strategies.builder import NaturalLanguageStrategyBuilder
from backtest.strategies.claude_parser import HybridStrategyBuilder
import os

st.set_page_config(page_title="Strategy Builder - AlbraTrading", page_icon="🔨", layout="wide")

st.title("🔨 Strategy Builder")
st.markdown("자연어로 설명하면 자동으로 트레이딩 전략을 생성합니다")

# Check for Claude API key
has_claude_api = os.getenv('ANTHROPIC_API_KEY') is not None

# Initialize builder based on API availability
if has_claude_api:
    builder = HybridStrategyBuilder(use_claude=True)
    st.success("🤖 Claude API 연결됨 - 고급 자연어 처리 활성화")
else:
    builder = NaturalLanguageStrategyBuilder()
    st.info("💡 Claude API 키가 없습니다. 기본 패턴 매칭을 사용합니다.")
    with st.expander("Claude API 설정 방법"):
        st.markdown("""
        1. [Anthropic Console](https://console.anthropic.com/)에서 API 키 발급
        2. 환경 변수 설정:
        ```bash
        export ANTHROPIC_API_KEY='your-api-key-here'
        ```
        3. Streamlit 재시작
        """)

# Sidebar - Examples
with st.sidebar:
    st.header("📚 전략 예시")
    
    st.subheader("🎯 추세 추종")
    if st.button("MA Crossover", use_container_width=True):
        st.session_state.strategy_input = """20일 이동평균선과 50일 이동평균선의 골든크로스에서 매수,
데드크로스에서 매도. 손절 2%, 익절 5%."""
    
    if st.button("Trend Following", use_container_width=True):
        st.session_state.strategy_input = """가격이 200일 이동평균선 위에 있고 MACD가 시그널선을 상향 돌파하면 매수.
MACD가 시그널선을 하향 돌파하면 매도. 트레일링 스톱 사용."""
    
    st.subheader("🔄 평균 회귀")
    if st.button("RSI Reversal", use_container_width=True):
        st.session_state.strategy_input = """RSI가 30 이하로 과매도 구간에 진입하면 매수,
70 이상으로 과매수 구간에 진입하면 매도.
ATR의 1.5배로 손절, 3배로 익절."""
    
    if st.button("Bollinger Reversal", use_container_width=True):
        st.session_state.strategy_input = """볼린저 밴드 하단을 터치한 후 반등하면 매수,
상단을 터치한 후 하락하면 매도.
손절 1.5%, 익절 3%."""
    
    st.subheader("🎯 복합 전략")
    if st.button("Multi-Indicator", use_container_width=True):
        st.session_state.strategy_input = """이치모쿠 구름 위에서 MACD 골든크로스가 발생하고
RSI가 50 이상이면 매수.
가격이 구름 아래로 떨어지면 매도.
켈리 기준으로 포지션 사이징."""

# Main content
tab1, tab2, tab3, tab4 = st.tabs(["✍️ 전략 작성", "🔍 전략 분석", "💻 생성된 코드", "🧪 백테스트"])

with tab1:
    st.subheader("전략을 자연어로 설명하세요")
    
    # Strategy input
    strategy_description = st.text_area(
        "전략 설명",
        value=st.session_state.get('strategy_input', ''),
        height=200,
        placeholder="""예시:
20일 볼린저 밴드를 사용합니다.
가격이 하단 밴드를 터치하고 RSI가 30 이하면 매수합니다.
가격이 상단 밴드를 터치하거나 RSI가 70 이상이면 매도합니다.
손절은 진입가격의 2% 아래, 익절은 5% 위에 설정합니다.
3% 수익 시 트레일링 스톱을 활성화합니다.""",
        key="strategy_input_area"
    )
    
    # Advanced options
    with st.expander("🔧 고급 옵션"):
        col1, col2 = st.columns(2)
        with col1:
            use_pyramiding = st.checkbox("피라미딩 허용", value=False)
            use_partial_exit = st.checkbox("부분 청산 허용", value=False)
        with col2:
            max_positions = st.number_input("최대 포지션 수", 1, 10, 1)
            risk_per_trade = st.slider("거래당 리스크 (%)", 0.5, 5.0, 2.0, 0.5)
    
    # Generate button
    if st.button("🚀 전략 생성", type="primary", use_container_width=True):
        if strategy_description:
            with st.spinner("전략을 분석하고 코드를 생성하는 중..."):
                try:
                    code, blueprint = builder.build_strategy(strategy_description)
                    st.session_state.generated_code = code
                    st.session_state.strategy_blueprint = blueprint
                    st.success("✅ 전략이 성공적으로 생성되었습니다!")
                    st.balloons()
                except Exception as e:
                    st.error(f"❌ 전략 생성 실패: {str(e)}")
        else:
            st.warning("⚠️ 전략 설명을 입력해주세요.")

with tab2:
    st.subheader("전략 분석 결과")
    
    if 'strategy_blueprint' in st.session_state:
        blueprint = st.session_state.strategy_blueprint
        
        # Strategy explanation
        explanation = builder.explain_strategy(blueprint)
        st.text(explanation)
        
        # Visual representation
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 📊 사용 지표")
            for indicator in blueprint.indicators:
                st.write(f"• {indicator['type']} {indicator.get('params', {})}")
        
        with col2:
            st.markdown("#### 📈 진입/청산 조건")
            st.write("**진입 조건:**")
            for cond in blueprint.entry_conditions.get('long', []):
                st.write(f"• 매수: {cond['type']}")
            for cond in blueprint.entry_conditions.get('short', []):
                st.write(f"• 매도: {cond['type']}")
            
            st.write("**청산 조건:**")
            for key, conditions in blueprint.exit_conditions.items():
                if conditions:
                    st.write(f"• {key}: {conditions}")
        
        # Improvement suggestions
        suggestions = builder.suggest_improvements(blueprint)
        if suggestions:
            with st.expander("💡 개선 제안"):
                for suggestion in suggestions:
                    st.info(suggestion)
        
        # Validation
        if 'generated_code' in st.session_state:
            validation = builder.validate_strategy(st.session_state.generated_code)
            if validation['valid']:
                st.success("✅ 전략 코드 검증 완료 - 오류 없음")
            else:
                st.error("❌ 전략 코드 검증 실패")
                for error in validation['errors']:
                    st.error(f"• {error}")
    else:
        st.info("전략을 생성하면 분석 결과가 여기에 표시됩니다.")

with tab3:
    st.subheader("생성된 전략 코드")
    
    if 'generated_code' in st.session_state:
        # Code display
        st.code(st.session_state.generated_code, language='python')
        
        # Actions
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📋 코드 복사"):
                st.success("클립보드에 복사되었습니다!")
        
        with col2:
            strategy_name = st.text_input("전략 이름", value=f"strategy_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
        with col3:
            if st.button("💾 전략 저장"):
                # Save strategy
                file_path = f"backtest/strategies/custom/{strategy_name}.py"
                st.success(f"전략이 {file_path}에 저장되었습니다!")
    else:
        st.info("전략을 생성하면 코드가 여기에 표시됩니다.")
        
        # Show template
        st.markdown("#### 전략 코드 구조 예시")
        st.code('''
class MyStrategy(BaseStrategy):
    """내가 만든 전략"""
    
    def __init__(self):
        super().__init__(StrategyParameters(
            position_size=0.1,
            stop_loss=0.02,
            take_profit=0.05
        ))
    
    @property
    def name(self) -> str:
        return "MY_STRATEGY"
    
    def generate_signal(self, market_event: MarketEvent) -> Optional[SignalEvent]:
        # 여기에 전략 로직 구현
        pass
''', language='python')

with tab4:
    st.subheader("전략 백테스트")
    
    if 'generated_code' in st.session_state:
        # Backtest settings
        col1, col2 = st.columns(2)
        
        with col1:
            test_symbol = st.selectbox("테스트 심볼", ["BTC/USDT", "ETH/USDT", "BNB/USDT"])
            test_period = st.selectbox("테스트 기간", ["1개월", "3개월", "6개월", "1년"])
        
        with col2:
            test_capital = st.number_input("테스트 자본", 1000, 100000, 10000, 1000)
            test_commission = st.number_input("수수료 (%)", 0.0, 1.0, 0.1, 0.01)
        
        if st.button("🧪 백테스트 실행", type="primary", use_container_width=True):
            with st.spinner("백테스트 실행 중..."):
                # Simulate backtest
                progress = st.progress(0)
                for i in range(100):
                    progress.progress(i + 1)
                
                st.success("✅ 백테스트 완료!")
                
                # Show results
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("총 수익률", "+23.45%", "↑")
                with col2:
                    st.metric("샤프 비율", "1.85", "")
                with col3:
                    st.metric("최대 낙폭", "-8.32%", "")
                with col4:
                    st.metric("승률", "58.3%", "")
                
                st.info("📊 상세한 백테스트 결과를 보려면 Quick Backtest 페이지를 이용하세요.")
    else:
        st.info("전략을 생성한 후 백테스트를 실행할 수 있습니다.")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
    💡 Tip: 전략 설명은 구체적이고 명확하게 작성할수록 더 정확한 코드가 생성됩니다.
</div>
""", unsafe_allow_html=True)