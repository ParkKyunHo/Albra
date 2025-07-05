"""
AlbraTrading Backtesting Platform
Main Streamlit Application

A comprehensive backtesting platform with natural language strategy builder.
"""

import streamlit as st
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

# Page configuration
st.set_page_config(
    page_title="AlbraTrading Backtest Platform",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    /* Main content area */
    .main > div {
        padding-top: 2rem;
    }
    
    /* Metric cards */
    div[data-testid="metric-container"] {
        background-color: #1a1a1a;
        border: 1px solid #333;
        padding: 1rem;
        border-radius: 0.5rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    /* Success/Error boxes */
    .stSuccess, .stError, .stWarning, .stInfo {
        padding: 1rem;
        border-radius: 0.5rem;
    }
    
    /* Buttons */
    .stButton > button {
        width: 100%;
        border-radius: 0.5rem;
        font-weight: 600;
    }
    
    /* Sidebar */
    .css-1d391kg {
        padding-top: 3rem;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'initialized' not in st.session_state:
    st.session_state.initialized = True
    st.session_state.backtest_results = {}
    st.session_state.current_strategy = None
    st.session_state.market_data = None

# Main page content
st.title("🚀 AlbraTrading Backtesting Platform")
st.markdown("### 전문가급 백테스팅 및 전략 개발 플랫폼")

# Welcome message
col1, col2, col3 = st.columns(3)

with col1:
    st.info("""
    **🎯 Quick Start**
    
    1. 좌측 메뉴에서 원하는 기능 선택
    2. Quick Backtest로 빠른 테스트
    3. Strategy Builder로 전략 생성
    """)

with col2:
    st.success("""
    **✨ 주요 기능**
    
    - 자연어 전략 생성
    - 실시간 차트 분석
    - 다중 전략 비교
    - Walk-Forward 분석
    """)

with col3:
    st.warning("""
    **📚 도움말**
    
    - [사용 가이드](/)
    - [전략 예시](/)
    - [API 문서](/)
    """)

# Statistics dashboard
st.markdown("---")
st.subheader("📊 플랫폼 통계")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="총 백테스트 실행",
        value=len(st.session_state.backtest_results),
        delta="오늘 +0"
    )

with col2:
    st.metric(
        label="저장된 전략",
        value="0",
        delta=None
    )

with col3:
    st.metric(
        label="평균 샤프 비율",
        value="0.00",
        delta=None
    )

with col4:
    st.metric(
        label="최고 수익률",
        value="0.00%",
        delta=None
    )

# Recent activity
st.markdown("---")
st.subheader("📝 최근 활동")

if len(st.session_state.backtest_results) == 0:
    st.info("아직 실행한 백테스트가 없습니다. Quick Backtest에서 시작해보세요!")
else:
    # Display recent backtest results
    for key, result in list(st.session_state.backtest_results.items())[-5:]:
        with st.expander(f"백테스트: {key}"):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"**전략**: {result.get('strategy_name', 'Unknown')}")
            with col2:
                st.write(f"**수익률**: {result.get('total_return', 0):.2%}")
            with col3:
                st.write(f"**샤프 비율**: {result.get('sharpe_ratio', 0):.2f}")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
    <p>AlbraTrading Backtesting Platform v1.0.0 | Built with Streamlit</p>
</div>
""", unsafe_allow_html=True)

# Sidebar info
with st.sidebar:
    st.markdown("### 💡 Tips")
    st.markdown("""
    - **Ctrl+Enter**: 코드 실행
    - **Shift+Enter**: 새 줄
    - **?**: 도움말 표시
    """)
    
    st.markdown("---")
    st.markdown("### 🔗 Quick Links")
    st.markdown("""
    - [GitHub Repository](https://github.com/yourusername/albratrading)
    - [Documentation](/)
    - [Report Issue](/)
    """)