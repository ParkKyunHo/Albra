"""
Home/Dashboard Page
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(page_title="Home - AlbraTrading", page_icon="🏠", layout="wide")

st.title("🏠 홈 / 대시보드")

# Check if user has any backtest results
if 'backtest_results' not in st.session_state:
    st.session_state.backtest_results = {}

# Quick action buttons
col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("🚀 빠른 백테스트", use_container_width=True, type="primary"):
        st.switch_page("pages/2_📊_Quick_Backtest.py")

with col2:
    if st.button("🔨 전략 생성", use_container_width=True):
        st.switch_page("pages/3_🔨_Strategy_Builder.py")

with col3:
    if st.button("📈 고급 분석", use_container_width=True):
        st.switch_page("pages/4_📈_Advanced_Analysis.py")

with col4:
    if st.button("⚙️ 설정", use_container_width=True):
        st.switch_page("pages/5_⚙️_Settings.py")

# Market Overview Section
st.markdown("---")
st.subheader("📈 시장 개요")

# Simulated market data (in real app, this would come from API)
market_data = {
    'BTC/USDT': {'price': 45000, 'change': 2.5, 'volume': '1.2B'},
    'ETH/USDT': {'price': 2500, 'change': -1.2, 'volume': '800M'},
    'BNB/USDT': {'price': 320, 'change': 0.8, 'volume': '200M'},
    'SOL/USDT': {'price': 100, 'change': 5.2, 'volume': '150M'},
}

cols = st.columns(4)
for idx, (symbol, data) in enumerate(market_data.items()):
    with cols[idx]:
        delta_color = "normal" if data['change'] >= 0 else "inverse"
        st.metric(
            label=symbol,
            value=f"${data['price']:,.0f}",
            delta=f"{data['change']:+.2f}%",
            delta_color=delta_color
        )
        st.caption(f"Vol: ${data['volume']}")

# Performance Summary
st.markdown("---")
st.subheader("📊 성과 요약")

if len(st.session_state.backtest_results) > 0:
    # Create performance summary
    results_df = pd.DataFrame([
        {
            'Strategy': result.get('strategy_name', 'Unknown'),
            'Return': result.get('total_return', 0) * 100,
            'Sharpe': result.get('sharpe_ratio', 0),
            'Max DD': result.get('max_drawdown', 0) * 100,
            'Win Rate': result.get('win_rate', 0)
        }
        for result in st.session_state.backtest_results.values()
    ])
    
    # Performance chart
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=results_df['Strategy'],
        y=results_df['Return'],
        name='수익률 (%)',
        marker_color='lightblue'
    ))
    
    fig.update_layout(
        title='전략별 수익률 비교',
        xaxis_title='전략',
        yaxis_title='수익률 (%)',
        height=400
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Summary table
    st.dataframe(
        results_df.style.format({
            'Return': '{:.2f}%',
            'Sharpe': '{:.2f}',
            'Max DD': '{:.2f}%',
            'Win Rate': '{:.1f}%'
        }).background_gradient(subset=['Return', 'Sharpe'], cmap='RdYlGn'),
        use_container_width=True
    )
else:
    # No results yet - show demo chart
    st.info("백테스트를 실행하면 여기에 성과 요약이 표시됩니다.")
    
    # Demo chart
    demo_dates = pd.date_range(start='2024-01-01', end='2024-12-31', freq='D')
    demo_returns = pd.Series(
        index=demo_dates,
        data=100 * (1 + 0.0005 + 0.001 * pd.Series(range(len(demo_dates))).apply(
            lambda x: np.random.randn()
        )).cumprod()
    )
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=demo_dates,
        y=demo_returns,
        mode='lines',
        name='예시 수익 곡선',
        line=dict(color='blue', width=2)
    ))
    
    fig.update_layout(
        title='백테스트 수익 곡선 예시',
        xaxis_title='날짜',
        yaxis_title='포트폴리오 가치',
        height=400,
        hovermode='x unified'
    )
    
    st.plotly_chart(fig, use_container_width=True)

# Educational content
st.markdown("---")
st.subheader("📚 시작하기")

col1, col2 = st.columns(2)

with col1:
    with st.expander("🎯 첫 번째 백테스트 실행하기"):
        st.markdown("""
        1. **Quick Backtest** 페이지로 이동
        2. 심볼 선택 (예: BTC/USDT)
        3. 전략 선택 또는 자연어로 입력
        4. 백테스트 실행
        
        **예시 전략:**
        ```
        20일 이동평균선과 50일 이동평균선의 골든크로스에서 매수,
        데드크로스에서 매도. 손절 2%, 익절 5%.
        ```
        """)

with col2:
    with st.expander("🔨 나만의 전략 만들기"):
        st.markdown("""
        **Strategy Builder**에서 자연어로 전략을 설명하면
        자동으로 실행 가능한 코드가 생성됩니다.
        
        **지원하는 지표:**
        - 이동평균선 (SMA, EMA)
        - RSI, MACD, 볼린저 밴드
        - 이치모쿠, ATR
        - 그 외 다수
        """)

# System status
with st.sidebar:
    st.markdown("### 🔔 시스템 상태")
    st.success("✅ 모든 시스템 정상")
    
    st.markdown("### 📊 세션 통계")
    st.write(f"백테스트 실행: {len(st.session_state.backtest_results)}")
    st.write(f"활성 전략: {1 if st.session_state.get('current_strategy') else 0}")
    
    if st.button("🗑️ 세션 초기화"):
        st.session_state.clear()
        st.rerun()