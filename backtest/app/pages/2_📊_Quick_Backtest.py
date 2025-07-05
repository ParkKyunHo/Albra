"""
Quick Backtest Page
빠른 백테스트 실행을 위한 간편한 인터페이스
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add parent directories to path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

# Import our modules
from backtest.strategies.builder import NaturalLanguageStrategyBuilder

st.set_page_config(page_title="Quick Backtest - AlbraTrading", page_icon="📊", layout="wide")

st.title("📊 Quick Backtest")
st.markdown("빠르고 간편하게 백테스트를 실행하세요")

# Initialize session state
if 'backtest_running' not in st.session_state:
    st.session_state.backtest_running = False

# Sidebar - Settings
with st.sidebar:
    st.header("⚙️ 백테스트 설정")
    
    # Data source
    st.subheader("📁 데이터 소스")
    data_source = st.selectbox(
        "데이터 소스 선택",
        ["Demo Data", "Yahoo Finance", "CSV Upload", "Binance API"]
    )
    
    # Symbol selection
    st.subheader("💱 심볼 선택")
    if data_source == "Demo Data":
        symbol = st.selectbox(
            "심볼",
            ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT"]
        )
    else:
        symbol = st.text_input("심볼 입력", "BTC-USD")
    
    # Date range
    st.subheader("📅 기간 설정")
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "시작일",
            datetime.now() - timedelta(days=365),
            max_value=datetime.now()
        )
    with col2:
        end_date = st.date_input(
            "종료일",
            datetime.now(),
            max_value=datetime.now()
        )
    
    # Capital and costs
    st.subheader("💰 자본 및 비용")
    initial_capital = st.number_input(
        "초기 자본 ($)",
        min_value=1000,
        max_value=1000000,
        value=10000,
        step=1000
    )
    
    col1, col2 = st.columns(2)
    with col1:
        commission = st.number_input(
            "수수료 (%)",
            min_value=0.0,
            max_value=1.0,
            value=0.1,
            step=0.01,
            format="%.2f"
        )
    with col2:
        slippage = st.number_input(
            "슬리피지 (%)",
            min_value=0.0,
            max_value=1.0,
            value=0.1,
            step=0.01,
            format="%.2f"
        )

# Main content area
tab1, tab2, tab3 = st.tabs(["🎯 전략 선택", "📈 결과", "📊 상세 분석"])

with tab1:
    st.subheader("전략 선택")
    
    # Strategy selection method
    strategy_method = st.radio(
        "전략 선택 방법",
        ["📝 자연어로 설명", "📚 템플릿 선택", "📁 파일 업로드"],
        horizontal=True
    )
    
    if strategy_method == "📝 자연어로 설명":
        st.markdown("### 자연어로 전략 설명하기")
        
        # Example strategies
        example_col1, example_col2 = st.columns(2)
        with example_col1:
            if st.button("예시: 이동평균 크로스오버"):
                st.session_state.nl_strategy = """20일 이동평균선이 50일 이동평균선을 상향 돌파하면 매수,
하향 돌파하면 매도. 손절 2%, 익절 5%."""
        
        with example_col2:
            if st.button("예시: RSI 반전"):
                st.session_state.nl_strategy = """RSI가 30 이하면 매수, 70 이상이면 매도.
ATR의 1.5배로 손절, 3배로 익절."""
        
        # Natural language input
        nl_description = st.text_area(
            "전략을 자연어로 설명하세요",
            value=st.session_state.get('nl_strategy', ''),
            height=150,
            placeholder="""예시: 볼린저 밴드 하단을 터치한 후 반등하면 매수,
상단을 터치한 후 하락하면 매도.
손절은 2%, 익절은 5%로 설정."""
        )
        
        if nl_description:
            with st.expander("🔍 전략 분석 결과"):
                builder = NaturalLanguageStrategyBuilder()
                try:
                    code, blueprint = builder.build_strategy(nl_description)
                    explanation = builder.explain_strategy(blueprint)
                    st.text(explanation)
                    
                    # Show generated code
                    with st.expander("생성된 코드 보기"):
                        st.code(code, language='python')
                    
                    st.session_state.current_strategy = blueprint
                    st.success("✅ 전략이 성공적으로 생성되었습니다!")
                except Exception as e:
                    st.error(f"전략 생성 실패: {str(e)}")
    
    elif strategy_method == "📚 템플릿 선택":
        st.markdown("### 전략 템플릿")
        
        template = st.selectbox(
            "템플릿 선택",
            [
                "이동평균 크로스오버",
                "RSI 과매수/과매도",
                "볼린저 밴드 반전",
                "MACD 모멘텀",
                "이치모쿠 클라우드"
            ]
        )
        
        # Template parameters
        st.markdown("#### 파라미터 설정")
        if template == "이동평균 크로스오버":
            col1, col2 = st.columns(2)
            with col1:
                fast_period = st.number_input("빠른 이동평균 기간", 10, 50, 20)
            with col2:
                slow_period = st.number_input("느린 이동평균 기간", 50, 200, 50)
        
        elif template == "RSI 과매수/과매도":
            col1, col2, col3 = st.columns(3)
            with col1:
                rsi_period = st.number_input("RSI 기간", 5, 30, 14)
            with col2:
                oversold = st.number_input("과매도 레벨", 20, 40, 30)
            with col3:
                overbought = st.number_input("과매수 레벨", 60, 80, 70)
    
    elif strategy_method == "📁 파일 업로드":
        st.markdown("### 전략 파일 업로드")
        uploaded_file = st.file_uploader(
            "Python 전략 파일을 업로드하세요",
            type=['py']
        )
        
        if uploaded_file:
            st.success(f"✅ {uploaded_file.name} 업로드 완료")
    
    # Run backtest button
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button(
            "🚀 백테스트 실행",
            use_container_width=True,
            type="primary",
            disabled=st.session_state.backtest_running
        ):
            st.session_state.backtest_running = True
            st.rerun()

with tab2:
    st.subheader("백테스트 결과")
    
    if st.session_state.backtest_running:
        # Simulate backtest execution
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i in range(100):
            progress_bar.progress(i + 1)
            status_text.text(f'백테스트 진행중... {i+1}%')
            
        st.session_state.backtest_running = False
        
        # Generate demo results
        dates = pd.date_range(start=start_date, end=end_date, freq='D')
        returns = np.random.randn(len(dates)) * 0.02
        equity_curve = initial_capital * (1 + returns).cumprod()
        
        # Store results
        result_key = f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        st.session_state.backtest_results[result_key] = {
            'strategy_name': 'Demo Strategy',
            'total_return': (equity_curve.iloc[-1] / initial_capital - 1),
            'sharpe_ratio': np.sqrt(252) * returns.mean() / returns.std(),
            'max_drawdown': ((equity_curve / equity_curve.cummax() - 1).min()),
            'win_rate': (returns > 0).sum() / len(returns) * 100,
            'equity_curve': equity_curve,
            'dates': dates
        }
        
        st.success("✅ 백테스트 완료!")
        st.balloons()
    
    # Display results if available
    if len(st.session_state.backtest_results) > 0:
        # Get most recent result
        latest_result = list(st.session_state.backtest_results.values())[-1]
        
        # Performance metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "총 수익률",
                f"{latest_result['total_return']:.2%}",
                delta=f"{latest_result['total_return']:.2%}"
            )
        
        with col2:
            st.metric(
                "샤프 비율",
                f"{latest_result['sharpe_ratio']:.2f}"
            )
        
        with col3:
            st.metric(
                "최대 낙폭",
                f"{latest_result['max_drawdown']:.2%}"
            )
        
        with col4:
            st.metric(
                "승률",
                f"{latest_result['win_rate']:.1f}%"
            )
        
        # Equity curve chart
        st.markdown("---")
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=latest_result['dates'],
            y=latest_result['equity_curve'],
            mode='lines',
            name='Equity Curve',
            line=dict(color='blue', width=2)
        ))
        
        fig.add_hline(
            y=initial_capital,
            line_dash="dash",
            line_color="gray",
            annotation_text="Initial Capital"
        )
        
        fig.update_layout(
            title='포트폴리오 가치 변화',
            xaxis_title='날짜',
            yaxis_title='포트폴리오 가치 ($)',
            height=500,
            hovermode='x unified'
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Download results
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📥 결과 다운로드 (CSV)"):
                st.info("CSV 다운로드 기능은 준비 중입니다.")
        with col2:
            if st.button("📄 리포트 생성 (PDF)"):
                st.info("PDF 리포트 기능은 준비 중입니다.")
    
    else:
        st.info("백테스트를 실행하면 결과가 여기에 표시됩니다.")

with tab3:
    st.subheader("상세 분석")
    
    if len(st.session_state.backtest_results) > 0:
        # Get most recent result
        latest_result = list(st.session_state.backtest_results.values())[-1]
        
        # Additional analysis
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 📊 수익률 분포")
            # Placeholder for returns distribution
            st.info("수익률 분포 차트가 여기에 표시됩니다.")
        
        with col2:
            st.markdown("#### 📈 월별 수익률")
            # Placeholder for monthly returns
            st.info("월별 수익률 히트맵이 여기에 표시됩니다.")
        
        # Trade analysis
        st.markdown("---")
        st.markdown("#### 🔍 거래 분석")
        
        # Demo trade data
        trades_df = pd.DataFrame({
            'Entry Date': pd.date_range(start=start_date, periods=10, freq='10D'),
            'Exit Date': pd.date_range(start=start_date + timedelta(days=5), periods=10, freq='10D'),
            'Type': ['Long', 'Short'] * 5,
            'P&L': np.random.randn(10) * 100,
            'Return %': np.random.randn(10) * 5
        })
        
        st.dataframe(
            trades_df.style.format({
                'P&L': '${:.2f}',
                'Return %': '{:.2f}%'
            }).background_gradient(subset=['P&L', 'Return %'], cmap='RdYlGn'),
            use_container_width=True
        )
    else:
        st.info("백테스트를 실행하면 상세 분석이 여기에 표시됩니다.")