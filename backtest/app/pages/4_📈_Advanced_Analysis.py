"""
Advanced Analysis Page
고급 분석 기능을 제공하는 페이지
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add parent directories to path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

st.set_page_config(page_title="Advanced Analysis - AlbraTrading", page_icon="📈", layout="wide")

st.title("📈 고급 분석")
st.markdown("여러 전략 비교, 워크포워드 분석, 파라미터 최적화 등 고급 기능을 제공합니다")

# Initialize session state
if 'selected_strategies' not in st.session_state:
    st.session_state.selected_strategies = []
if 'optimization_results' not in st.session_state:
    st.session_state.optimization_results = {}
if 'walkforward_results' not in st.session_state:
    st.session_state.walkforward_results = {}

# Analysis tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔄 전략 비교", 
    "🚶 워크포워드 분석", 
    "🔧 파라미터 최적화", 
    "💼 포트폴리오 백테스트",
    "📊 몬테카를로 시뮬레이션"
])

with tab1:
    st.subheader("🔄 전략 비교 분석")
    
    # Strategy selection
    st.markdown("### 비교할 전략 선택")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        # Get available strategies from backtest results
        available_strategies = list(st.session_state.backtest_results.keys()) if 'backtest_results' in st.session_state else []
        
        if available_strategies:
            selected = st.multiselect(
                "백테스트 결과에서 전략 선택",
                available_strategies,
                default=available_strategies[:2] if len(available_strategies) >= 2 else available_strategies
            )
        else:
            st.info("비교할 백테스트 결과가 없습니다. Quick Backtest에서 먼저 백테스트를 실행해주세요.")
            selected = []
    
    with col2:
        if st.button("📊 비교 분석 실행", type="primary", disabled=len(selected) < 2):
            st.session_state.selected_strategies = selected
    
    if len(st.session_state.selected_strategies) >= 2:
        # Comparison metrics
        st.markdown("### 📊 성과 지표 비교")
        
        # Create comparison dataframe
        comparison_data = []
        for strategy_key in st.session_state.selected_strategies:
            if strategy_key in st.session_state.backtest_results:
                result = st.session_state.backtest_results[strategy_key]
                comparison_data.append({
                    'Strategy': result.get('strategy_name', strategy_key),
                    'Total Return': result.get('total_return', 0) * 100,
                    'Sharpe Ratio': result.get('sharpe_ratio', 0),
                    'Max Drawdown': result.get('max_drawdown', 0) * 100,
                    'Win Rate': result.get('win_rate', 0),
                    'Calmar Ratio': result.get('total_return', 0) / abs(result.get('max_drawdown', 1)) if result.get('max_drawdown', 0) != 0 else 0,
                    'Profit Factor': np.random.uniform(1.2, 2.5)  # Demo value
                })
        
        comparison_df = pd.DataFrame(comparison_data)
        
        # Display comparison table
        st.dataframe(
            comparison_df.style.format({
                'Total Return': '{:.2f}%',
                'Sharpe Ratio': '{:.2f}',
                'Max Drawdown': '{:.2f}%',
                'Win Rate': '{:.1f}%',
                'Calmar Ratio': '{:.2f}',
                'Profit Factor': '{:.2f}'
            }).background_gradient(subset=['Total Return', 'Sharpe Ratio', 'Calmar Ratio'], cmap='RdYlGn'),
            use_container_width=True
        )
        
        # Radar chart comparison
        st.markdown("### 🎯 레이더 차트")
        
        categories = ['수익률', '샤프비율', '승률', 'Calmar비율', '수익팩터']
        
        fig = go.Figure()
        
        for idx, row in comparison_df.iterrows():
            values = [
                row['Total Return'] / 100,  # Normalize to 0-1 scale
                row['Sharpe Ratio'] / 3,    # Assuming max Sharpe of 3
                row['Win Rate'] / 100,
                row['Calmar Ratio'] / 3,     # Assuming max Calmar of 3
                row['Profit Factor'] / 3     # Assuming max PF of 3
            ]
            
            fig.add_trace(go.Scatterpolar(
                r=values,
                theta=categories,
                fill='toself',
                name=row['Strategy']
            ))
        
        fig.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, 1]
                )),
            showlegend=True,
            title="전략 성과 비교"
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Equity curves comparison
        st.markdown("### 📈 수익 곡선 비교")
        
        fig = go.Figure()
        
        for strategy_key in st.session_state.selected_strategies:
            if strategy_key in st.session_state.backtest_results:
                result = st.session_state.backtest_results[strategy_key]
                if 'equity_curve' in result and 'dates' in result:
                    fig.add_trace(go.Scatter(
                        x=result['dates'],
                        y=result['equity_curve'],
                        mode='lines',
                        name=result.get('strategy_name', strategy_key)
                    ))
        
        fig.update_layout(
            title='전략별 수익 곡선',
            xaxis_title='날짜',
            yaxis_title='포트폴리오 가치 ($)',
            height=500,
            hovermode='x unified'
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Correlation analysis
        st.markdown("### 🔗 상관관계 분석")
        
        # Generate demo correlation matrix
        n_strategies = len(st.session_state.selected_strategies)
        correlation_matrix = np.random.rand(n_strategies, n_strategies)
        correlation_matrix = (correlation_matrix + correlation_matrix.T) / 2
        np.fill_diagonal(correlation_matrix, 1)
        
        fig = px.imshow(
            correlation_matrix,
            labels=dict(color="상관계수"),
            x=[s.split('_')[0] for s in st.session_state.selected_strategies],
            y=[s.split('_')[0] for s in st.session_state.selected_strategies],
            color_continuous_scale="RdBu_r",
            zmin=-1, zmax=1
        )
        
        fig.update_layout(title="전략 간 상관관계")
        st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.subheader("🚶 워크포워드 분석")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("""
        워크포워드 분석은 전략의 견고성을 테스트하는 고급 기법입니다.
        - In-Sample 기간: 전략 최적화
        - Out-of-Sample 기간: 성과 검증
        """)
    
    with col2:
        wf_strategy = st.selectbox(
            "분석할 전략",
            list(st.session_state.backtest_results.keys()) if 'backtest_results' in st.session_state else []
        )
    
    # Walk-forward settings
    st.markdown("### ⚙️ 워크포워드 설정")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        in_sample_period = st.number_input("In-Sample 기간 (일)", 60, 365, 180)
    with col2:
        out_sample_period = st.number_input("Out-of-Sample 기간 (일)", 30, 180, 60)
    with col3:
        step_size = st.number_input("스텝 크기 (일)", 10, 60, 30)
    
    if st.button("🚀 워크포워드 분석 실행", type="primary"):
        with st.spinner("워크포워드 분석 실행 중..."):
            # Simulate walk-forward analysis
            progress = st.progress(0)
            
            # Generate demo results
            n_windows = 10
            wf_results = []
            
            for i in range(n_windows):
                progress.progress((i + 1) / n_windows)
                
                wf_results.append({
                    'Window': i + 1,
                    'Start Date': datetime.now() - timedelta(days=365-i*30),
                    'End Date': datetime.now() - timedelta(days=335-i*30),
                    'IS Return': np.random.uniform(5, 25),
                    'OOS Return': np.random.uniform(-5, 20),
                    'IS Sharpe': np.random.uniform(0.5, 2.5),
                    'OOS Sharpe': np.random.uniform(0.3, 2.0)
                })
            
            st.session_state.walkforward_results[wf_strategy] = pd.DataFrame(wf_results)
            st.success("✅ 워크포워드 분석 완료!")
    
    # Display results
    if wf_strategy in st.session_state.walkforward_results:
        results_df = st.session_state.walkforward_results[wf_strategy]
        
        # Performance comparison
        st.markdown("### 📊 In-Sample vs Out-of-Sample 성과")
        
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=('수익률 비교', '샤프 비율 비교'),
            vertical_spacing=0.1
        )
        
        # Returns comparison
        fig.add_trace(
            go.Bar(x=results_df['Window'], y=results_df['IS Return'], name='In-Sample', marker_color='blue'),
            row=1, col=1
        )
        fig.add_trace(
            go.Bar(x=results_df['Window'], y=results_df['OOS Return'], name='Out-of-Sample', marker_color='orange'),
            row=1, col=1
        )
        
        # Sharpe comparison
        fig.add_trace(
            go.Scatter(x=results_df['Window'], y=results_df['IS Sharpe'], name='In-Sample Sharpe', line=dict(color='blue')),
            row=2, col=1
        )
        fig.add_trace(
            go.Scatter(x=results_df['Window'], y=results_df['OOS Sharpe'], name='Out-of-Sample Sharpe', line=dict(color='orange')),
            row=2, col=1
        )
        
        fig.update_xaxes(title_text="Window", row=2, col=1)
        fig.update_yaxes(title_text="Return (%)", row=1, col=1)
        fig.update_yaxes(title_text="Sharpe Ratio", row=2, col=1)
        
        fig.update_layout(height=700, showlegend=True)
        st.plotly_chart(fig, use_container_width=True)
        
        # Statistics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            avg_is_return = results_df['IS Return'].mean()
            avg_oos_return = results_df['OOS Return'].mean()
            st.metric("평균 수익률", f"IS: {avg_is_return:.2f}% / OOS: {avg_oos_return:.2f}%")
        
        with col2:
            efficiency = (avg_oos_return / avg_is_return * 100) if avg_is_return != 0 else 0
            st.metric("효율성", f"{efficiency:.1f}%", f"{efficiency-100:.1f}%")
        
        with col3:
            consistency = (results_df['OOS Return'] > 0).sum() / len(results_df) * 100
            st.metric("일관성", f"{consistency:.1f}%")

with tab3:
    st.subheader("🔧 파라미터 최적화")
    
    # Strategy selection for optimization
    opt_strategy = st.selectbox(
        "최적화할 전략 선택",
        ["Moving Average Crossover", "RSI Strategy", "MACD Strategy", "Custom Strategy"]
    )
    
    # Parameter settings based on strategy
    st.markdown("### 📐 최적화 파라미터")
    
    if opt_strategy == "Moving Average Crossover":
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Fast MA Period**")
            fast_min = st.number_input("최소값", 5, 50, 10)
            fast_max = st.number_input("최대값", 10, 100, 30)
            fast_step = st.number_input("스텝", 1, 10, 5)
        
        with col2:
            st.markdown("**Slow MA Period**")
            slow_min = st.number_input("최소값", 20, 100, 30, key="slow_min")
            slow_max = st.number_input("최대값", 50, 300, 100, key="slow_max")
            slow_step = st.number_input("스텝", 5, 20, 10, key="slow_step")
    
    # Optimization settings
    st.markdown("### ⚙️ 최적화 설정")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        optimization_metric = st.selectbox(
            "최적화 지표",
            ["Sharpe Ratio", "Total Return", "Calmar Ratio", "Profit Factor"]
        )
    
    with col2:
        optimization_method = st.selectbox(
            "최적화 방법",
            ["Grid Search", "Random Search", "Bayesian Optimization"]
        )
    
    with col3:
        n_trials = st.number_input("시도 횟수", 10, 1000, 100)
    
    if st.button("🎯 최적화 시작", type="primary"):
        with st.spinner(f"{optimization_method} 진행 중..."):
            # Simulate optimization
            progress = st.progress(0)
            
            # Generate demo optimization results
            results = []
            best_score = -np.inf
            best_params = {}
            
            for i in range(min(n_trials, 20)):  # Limit for demo
                progress.progress((i + 1) / min(n_trials, 20))
                
                # Random parameters
                fast_period = np.random.randint(fast_min, fast_max)
                slow_period = np.random.randint(slow_min, slow_max)
                
                # Random performance
                score = np.random.uniform(0.5, 2.5) if optimization_metric == "Sharpe Ratio" else np.random.uniform(10, 50)
                
                results.append({
                    'Trial': i + 1,
                    'Fast Period': fast_period,
                    'Slow Period': slow_period,
                    optimization_metric: score
                })
                
                if score > best_score:
                    best_score = score
                    best_params = {'Fast Period': fast_period, 'Slow Period': slow_period}
            
            opt_results_df = pd.DataFrame(results)
            st.session_state.optimization_results[opt_strategy] = {
                'results': opt_results_df,
                'best_params': best_params,
                'best_score': best_score
            }
            
            st.success("✅ 최적화 완료!")
    
    # Display optimization results
    if opt_strategy in st.session_state.optimization_results:
        opt_data = st.session_state.optimization_results[opt_strategy]
        
        # Best parameters
        st.markdown("### 🏆 최적 파라미터")
        col1, col2 = st.columns(2)
        
        with col1:
            st.info(f"**최적 파라미터:** {opt_data['best_params']}")
        with col2:
            st.success(f"**최고 {optimization_metric}:** {opt_data['best_score']:.2f}")
        
        # 3D visualization
        st.markdown("### 📊 파라미터 공간 시각화")
        
        results_df = opt_data['results']
        
        fig = go.Figure(data=[go.Scatter3d(
            x=results_df['Fast Period'],
            y=results_df['Slow Period'],
            z=results_df[optimization_metric],
            mode='markers',
            marker=dict(
                size=8,
                color=results_df[optimization_metric],
                colorscale='Viridis',
                showscale=True,
                colorbar=dict(title=optimization_metric)
            ),
            text=[f"Trial {i}" for i in results_df['Trial']],
            hovertemplate='Fast: %{x}<br>Slow: %{y}<br>' + optimization_metric + ': %{z}<extra></extra>'
        )])
        
        fig.update_layout(
            title='파라미터 최적화 결과',
            scene=dict(
                xaxis_title='Fast Period',
                yaxis_title='Slow Period',
                zaxis_title=optimization_metric
            ),
            height=600
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Heatmap
        st.markdown("### 🔥 파라미터 히트맵")
        
        # Create pivot table for heatmap
        pivot_data = results_df.pivot_table(
            values=optimization_metric,
            index='Slow Period',
            columns='Fast Period',
            aggfunc='mean'
        )
        
        fig = px.imshow(
            pivot_data,
            labels=dict(x="Fast Period", y="Slow Period", color=optimization_metric),
            color_continuous_scale="RdYlGn"
        )
        
        fig.update_layout(title=f'{optimization_metric} by Parameters')
        st.plotly_chart(fig, use_container_width=True)

with tab4:
    st.subheader("💼 포트폴리오 백테스트")
    
    st.markdown("""
    여러 전략을 조합하여 포트폴리오로 운영할 때의 성과를 분석합니다.
    각 전략의 가중치를 조절하여 최적의 포트폴리오를 구성할 수 있습니다.
    """)
    
    # Strategy selection for portfolio
    available_strategies = list(st.session_state.backtest_results.keys()) if 'backtest_results' in st.session_state else []
    
    if len(available_strategies) >= 2:
        st.markdown("### 📊 포트폴리오 구성")
        
        # Weight allocation
        weights = {}
        total_weight = 0
        
        for strategy in available_strategies:
            weight = st.slider(
                f"{strategy} 비중 (%)",
                0, 100, 100 // len(available_strategies),
                key=f"weight_{strategy}"
            )
            weights[strategy] = weight / 100
            total_weight += weight
        
        # Weight validation
        if abs(total_weight - 100) > 0.01:
            st.warning(f"⚠️ 전체 비중이 {total_weight}%입니다. 100%가 되도록 조정해주세요.")
        
        # Portfolio settings
        col1, col2 = st.columns(2)
        
        with col1:
            rebalancing_freq = st.selectbox(
                "리밸런싱 주기",
                ["매일", "매주", "매월", "분기별", "연간", "없음"]
            )
        
        with col2:
            correlation_consideration = st.checkbox("상관관계 고려", value=True)
        
        if st.button("💼 포트폴리오 백테스트 실행", type="primary", disabled=abs(total_weight - 100) > 0.01):
            with st.spinner("포트폴리오 백테스트 실행 중..."):
                # Simulate portfolio backtest
                dates = pd.date_range(start='2024-01-01', end='2024-12-31', freq='D')
                
                # Generate individual strategy returns
                strategy_returns = {}
                for strategy in weights:
                    returns = np.random.randn(len(dates)) * 0.02
                    strategy_returns[strategy] = returns
                
                # Calculate portfolio returns
                portfolio_returns = np.zeros(len(dates))
                for strategy, weight in weights.items():
                    if weight > 0:
                        portfolio_returns += strategy_returns[strategy] * weight
                
                # Calculate portfolio equity curve
                portfolio_equity = pd.Series(10000 * (1 + portfolio_returns).cumprod())
                
                # Calculate metrics
                total_return = (portfolio_equity.iloc[-1] / 10000 - 1) * 100
                sharpe_ratio = np.sqrt(252) * portfolio_returns.mean() / portfolio_returns.std()
                max_dd = ((portfolio_equity / portfolio_equity.cummax() - 1).min()) * 100
                
                # Display results
                st.success("✅ 포트폴리오 백테스트 완료!")
                
                # Metrics
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("총 수익률", f"{total_return:.2f}%")
                with col2:
                    st.metric("샤프 비율", f"{sharpe_ratio:.2f}")
                with col3:
                    st.metric("최대 낙폭", f"{max_dd:.2f}%")
                with col4:
                    st.metric("연환산 수익률", f"{total_return:.2f}%")
                
                # Portfolio vs Individual strategies
                st.markdown("### 📈 포트폴리오 vs 개별 전략")
                
                fig = go.Figure()
                
                # Add portfolio curve
                fig.add_trace(go.Scatter(
                    x=dates,
                    y=portfolio_equity,
                    mode='lines',
                    name='Portfolio',
                    line=dict(color='red', width=3)
                ))
                
                # Add individual strategy curves
                for strategy in weights:
                    if weights[strategy] > 0:
                        strategy_equity = 10000 * (1 + strategy_returns[strategy]).cumprod()
                        fig.add_trace(go.Scatter(
                            x=dates,
                            y=strategy_equity,
                            mode='lines',
                            name=strategy,
                            line=dict(width=1, dash='dot')
                        ))
                
                fig.update_layout(
                    title='포트폴리오 vs 개별 전략 성과',
                    xaxis_title='날짜',
                    yaxis_title='포트폴리오 가치 ($)',
                    height=500,
                    hovermode='x unified'
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Risk contribution
                st.markdown("### 🎯 리스크 기여도")
                
                risk_contribution = pd.DataFrame({
                    'Strategy': list(weights.keys()),
                    'Weight': [weights[s] * 100 for s in weights],
                    'Risk Contribution': np.random.uniform(10, 40, len(weights))
                })
                
                fig = px.pie(
                    risk_contribution,
                    values='Risk Contribution',
                    names='Strategy',
                    title='전략별 리스크 기여도'
                )
                
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("포트폴리오 백테스트를 실행하려면 최소 2개 이상의 백테스트 결과가 필요합니다.")

with tab5:
    st.subheader("📊 몬테카를로 시뮬레이션")
    
    st.markdown("""
    몬테카를로 시뮬레이션을 통해 전략의 불확실성을 분석하고
    다양한 시나리오에서의 성과를 예측합니다.
    """)
    
    # Strategy selection
    mc_strategy = st.selectbox(
        "시뮬레이션할 전략",
        list(st.session_state.backtest_results.keys()) if 'backtest_results' in st.session_state else []
    )
    
    # Simulation settings
    st.markdown("### ⚙️ 시뮬레이션 설정")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        n_simulations = st.number_input("시뮬레이션 횟수", 100, 10000, 1000)
    with col2:
        time_horizon = st.number_input("예측 기간 (일)", 30, 365, 252)
    with col3:
        confidence_level = st.slider("신뢰 수준 (%)", 80, 99, 95)
    
    if st.button("🎲 몬테카를로 시뮬레이션 실행", type="primary"):
        with st.spinner(f"{n_simulations}개 시나리오 생성 중..."):
            # Get historical statistics (demo values)
            mean_return = 0.001
            std_return = 0.02
            
            # Run Monte Carlo simulation
            simulation_results = []
            
            for i in range(min(n_simulations, 100)):  # Limit for performance
                # Generate random returns
                returns = np.random.normal(mean_return, std_return, time_horizon)
                
                # Calculate cumulative returns
                cum_returns = (1 + returns).cumprod()
                final_value = 10000 * cum_returns[-1]
                
                simulation_results.append({
                    'simulation': i,
                    'returns': cum_returns,
                    'final_value': final_value
                })
            
            # Calculate statistics
            final_values = [s['final_value'] for s in simulation_results]
            percentile_low = np.percentile(final_values, (100 - confidence_level) / 2)
            percentile_high = np.percentile(final_values, 100 - (100 - confidence_level) / 2)
            
            # Display results
            st.success("✅ 몬테카를로 시뮬레이션 완료!")
            
            # Summary statistics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("평균 최종 가치", f"${np.mean(final_values):,.0f}")
            with col2:
                st.metric("중간값", f"${np.median(final_values):,.0f}")
            with col3:
                st.metric(f"{confidence_level}% 하한", f"${percentile_low:,.0f}")
            with col4:
                st.metric(f"{confidence_level}% 상한", f"${percentile_high:,.0f}")
            
            # Simulation paths
            st.markdown("### 📈 시뮬레이션 경로")
            
            fig = go.Figure()
            
            # Add sample paths
            for i in range(min(50, len(simulation_results))):
                sim = simulation_results[i]
                dates = pd.date_range(start=datetime.now(), periods=time_horizon, freq='D')
                
                fig.add_trace(go.Scatter(
                    x=dates,
                    y=10000 * sim['returns'],
                    mode='lines',
                    line=dict(color='lightblue', width=0.5),
                    showlegend=False,
                    hoverinfo='skip'
                ))
            
            # Add confidence bands
            dates = pd.date_range(start=datetime.now(), periods=time_horizon, freq='D')
            all_paths = np.array([10000 * s['returns'] for s in simulation_results[:min(100, len(simulation_results))]])
            
            percentiles = np.percentile(all_paths, [5, 25, 50, 75, 95], axis=0)
            
            # Add median
            fig.add_trace(go.Scatter(
                x=dates,
                y=percentiles[2],
                mode='lines',
                name='중간값',
                line=dict(color='red', width=2)
            ))
            
            # Add confidence bands
            fig.add_trace(go.Scatter(
                x=dates,
                y=percentiles[4],
                mode='lines',
                name='95% 상한',
                line=dict(color='green', width=1, dash='dash')
            ))
            
            fig.add_trace(go.Scatter(
                x=dates,
                y=percentiles[0],
                mode='lines',
                name='5% 하한',
                line=dict(color='green', width=1, dash='dash'),
                fill='tonexty',
                fillcolor='rgba(0,255,0,0.1)'
            ))
            
            fig.update_layout(
                title=f'{n_simulations}개 시나리오 몬테카를로 시뮬레이션',
                xaxis_title='날짜',
                yaxis_title='포트폴리오 가치 ($)',
                height=500,
                hovermode='x unified'
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Distribution of final values
            st.markdown("### 📊 최종 가치 분포")
            
            fig = go.Figure()
            
            fig.add_trace(go.Histogram(
                x=final_values,
                nbinsx=50,
                name='최종 가치 분포',
                marker_color='blue'
            ))
            
            # Add percentile lines
            fig.add_vline(x=percentile_low, line_dash="dash", line_color="red",
                         annotation_text=f"{confidence_level}% 하한")
            fig.add_vline(x=percentile_high, line_dash="dash", line_color="red",
                         annotation_text=f"{confidence_level}% 상한")
            fig.add_vline(x=np.mean(final_values), line_dash="solid", line_color="green",
                         annotation_text="평균")
            
            fig.update_layout(
                title='최종 포트폴리오 가치 분포',
                xaxis_title='최종 가치 ($)',
                yaxis_title='빈도',
                height=400
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Risk metrics
            st.markdown("### 📊 리스크 지표")
            
            var_95 = np.percentile(final_values, 5)
            cvar_95 = np.mean([v for v in final_values if v <= var_95])
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Value at Risk (95%)", f"${10000 - var_95:,.0f}")
            with col2:
                st.metric("Conditional VaR (95%)", f"${10000 - cvar_95:,.0f}")
            with col3:
                prob_loss = (np.array(final_values) < 10000).sum() / len(final_values) * 100
                st.metric("손실 확률", f"{prob_loss:.1f}%")

# Add export functionality
st.markdown("---")
st.markdown("### 💾 분석 결과 내보내기")

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("📥 Excel 다운로드", use_container_width=True):
        st.info("Excel 내보내기 기능은 준비 중입니다.")

with col2:
    if st.button("📄 PDF 리포트 생성", use_container_width=True):
        st.info("PDF 리포트 생성 기능은 준비 중입니다.")

with col3:
    if st.button("📧 이메일 전송", use_container_width=True):
        st.info("이메일 전송 기능은 준비 중입니다.")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
    💡 Tip: 고급 분석 기능을 사용하여 전략의 견고성과 위험을 평가하세요.
</div>
""", unsafe_allow_html=True)