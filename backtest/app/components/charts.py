"""
Chart Components
재사용 가능한 차트 컴포넌트들
"""

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta


class ChartComponents:
    """재사용 가능한 차트 컴포넌트 클래스"""
    
    @staticmethod
    def create_candlestick_chart(
        data: pd.DataFrame,
        title: str = "Price Chart",
        indicators: Optional[List[str]] = None,
        height: int = 600
    ) -> go.Figure:
        """
        캔들스틱 차트 생성
        
        Args:
            data: OHLCV 데이터
            title: 차트 제목
            indicators: 표시할 지표 리스트
            height: 차트 높이
        """
        # Create figure with secondary y-axis
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            subplot_titles=('Price', 'Volume'),
            row_heights=[0.7, 0.3]
        )
        
        # Add candlestick
        fig.add_trace(
            go.Candlestick(
                x=data.index,
                open=data['open'],
                high=data['high'],
                low=data['low'],
                close=data['close'],
                name='Price'
            ),
            row=1, col=1
        )
        
        # Add volume bars
        colors = ['red' if row['close'] < row['open'] else 'green' 
                 for idx, row in data.iterrows()]
        
        fig.add_trace(
            go.Bar(
                x=data.index,
                y=data['volume'],
                marker_color=colors,
                name='Volume'
            ),
            row=2, col=1
        )
        
        # Add indicators if specified
        if indicators:
            for indicator in indicators:
                if indicator in data.columns:
                    fig.add_trace(
                        go.Scatter(
                            x=data.index,
                            y=data[indicator],
                            mode='lines',
                            name=indicator.upper(),
                            line=dict(width=2)
                        ),
                        row=1, col=1
                    )
        
        # Update layout
        fig.update_layout(
            title=title,
            height=height,
            xaxis_rangeslider_visible=False,
            showlegend=True,
            hovermode='x unified'
        )
        
        fig.update_xaxes(title_text="Date", row=2, col=1)
        fig.update_yaxes(title_text="Price", row=1, col=1)
        fig.update_yaxes(title_text="Volume", row=2, col=1)
        
        return fig
    
    @staticmethod
    def create_equity_curve(
        equity_data: pd.Series,
        benchmark_data: Optional[pd.Series] = None,
        drawdown_data: Optional[pd.Series] = None,
        title: str = "Portfolio Equity Curve",
        height: int = 500
    ) -> go.Figure:
        """
        수익 곡선 차트 생성
        
        Args:
            equity_data: 포트폴리오 가치 데이터
            benchmark_data: 벤치마크 데이터
            drawdown_data: 낙폭 데이터
            title: 차트 제목
            height: 차트 높이
        """
        # Create subplots if drawdown data is provided
        if drawdown_data is not None:
            fig = make_subplots(
                rows=2, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.03,
                subplot_titles=('Equity Curve', 'Drawdown'),
                row_heights=[0.7, 0.3]
            )
            
            # Add equity curve
            fig.add_trace(
                go.Scatter(
                    x=equity_data.index,
                    y=equity_data,
                    mode='lines',
                    name='Portfolio',
                    line=dict(color='blue', width=2)
                ),
                row=1, col=1
            )
            
            # Add benchmark if provided
            if benchmark_data is not None:
                fig.add_trace(
                    go.Scatter(
                        x=benchmark_data.index,
                        y=benchmark_data,
                        mode='lines',
                        name='Benchmark',
                        line=dict(color='gray', width=1, dash='dash')
                    ),
                    row=1, col=1
                )
            
            # Add drawdown
            fig.add_trace(
                go.Scatter(
                    x=drawdown_data.index,
                    y=drawdown_data * 100,  # Convert to percentage
                    mode='lines',
                    name='Drawdown',
                    fill='tozeroy',
                    line=dict(color='red', width=1)
                ),
                row=2, col=1
            )
            
            fig.update_yaxes(title_text="Portfolio Value", row=1, col=1)
            fig.update_yaxes(title_text="Drawdown (%)", row=2, col=1)
            fig.update_xaxes(title_text="Date", row=2, col=1)
        else:
            # Simple equity curve
            fig = go.Figure()
            
            fig.add_trace(
                go.Scatter(
                    x=equity_data.index,
                    y=equity_data,
                    mode='lines',
                    name='Portfolio',
                    line=dict(color='blue', width=2)
                )
            )
            
            if benchmark_data is not None:
                fig.add_trace(
                    go.Scatter(
                        x=benchmark_data.index,
                        y=benchmark_data,
                        mode='lines',
                        name='Benchmark',
                        line=dict(color='gray', width=1, dash='dash')
                    )
                )
            
            fig.update_yaxes(title_text="Portfolio Value")
            fig.update_xaxes(title_text="Date")
        
        fig.update_layout(
            title=title,
            height=height,
            hovermode='x unified',
            showlegend=True
        )
        
        return fig
    
    @staticmethod
    def create_returns_distribution(
        returns: pd.Series,
        title: str = "Returns Distribution",
        bins: int = 50,
        height: int = 400
    ) -> go.Figure:
        """
        수익률 분포 히스토그램 생성
        
        Args:
            returns: 수익률 데이터
            title: 차트 제목
            bins: 히스토그램 구간 수
            height: 차트 높이
        """
        fig = go.Figure()
        
        # Add histogram
        fig.add_trace(
            go.Histogram(
                x=returns,
                nbinsx=bins,
                name='Returns',
                marker_color='blue',
                opacity=0.7
            )
        )
        
        # Add normal distribution overlay
        mean = returns.mean()
        std = returns.std()
        x_range = np.linspace(returns.min(), returns.max(), 100)
        normal_dist = (1 / (std * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x_range - mean) / std) ** 2)
        normal_dist = normal_dist * len(returns) * (returns.max() - returns.min()) / bins
        
        fig.add_trace(
            go.Scatter(
                x=x_range,
                y=normal_dist,
                mode='lines',
                name='Normal Distribution',
                line=dict(color='red', width=2)
            )
        )
        
        # Add mean line
        fig.add_vline(
            x=mean,
            line_dash="dash",
            line_color="green",
            annotation_text=f"Mean: {mean:.4f}"
        )
        
        fig.update_layout(
            title=title,
            xaxis_title="Returns",
            yaxis_title="Frequency",
            height=height,
            showlegend=True
        )
        
        return fig
    
    @staticmethod
    def create_heatmap(
        data: pd.DataFrame,
        title: str = "Correlation Heatmap",
        color_scale: str = "RdBu_r",
        height: int = 500
    ) -> go.Figure:
        """
        히트맵 생성
        
        Args:
            data: 2D 데이터 (예: 상관관계 행렬)
            title: 차트 제목
            color_scale: 색상 스케일
            height: 차트 높이
        """
        fig = go.Figure(
            data=go.Heatmap(
                z=data.values,
                x=data.columns,
                y=data.index,
                colorscale=color_scale,
                zmid=0,
                text=data.values,
                texttemplate='%{text:.2f}',
                textfont={"size": 10},
                hoverongaps=False
            )
        )
        
        fig.update_layout(
            title=title,
            height=height,
            xaxis=dict(side="bottom"),
            yaxis=dict(side="left")
        )
        
        return fig
    
    @staticmethod
    def create_performance_metrics_table(
        metrics: Dict[str, float],
        title: str = "Performance Metrics"
    ) -> go.Figure:
        """
        성과 지표 테이블 생성
        
        Args:
            metrics: 성과 지표 딕셔너리
            title: 테이블 제목
        """
        # Format metrics
        formatted_metrics = []
        for key, value in metrics.items():
            if 'return' in key.lower() or 'drawdown' in key.lower():
                formatted_value = f"{value:.2%}"
            elif 'ratio' in key.lower():
                formatted_value = f"{value:.2f}"
            else:
                formatted_value = f"{value:,.2f}"
            
            formatted_metrics.append([key.replace('_', ' ').title(), formatted_value])
        
        fig = go.Figure(
            data=[go.Table(
                header=dict(
                    values=['Metric', 'Value'],
                    fill_color='lightgray',
                    align='left',
                    font=dict(size=12, color='black')
                ),
                cells=dict(
                    values=list(zip(*formatted_metrics)),
                    fill_color='white',
                    align='left',
                    font=dict(size=11)
                )
            )]
        )
        
        fig.update_layout(
            title=title,
            height=400
        )
        
        return fig
    
    @staticmethod
    def create_monthly_returns_heatmap(
        returns: pd.Series,
        title: str = "Monthly Returns Heatmap"
    ) -> go.Figure:
        """
        월별 수익률 히트맵 생성
        
        Args:
            returns: 일별 수익률 데이터
            title: 차트 제목
        """
        # Convert to monthly returns
        monthly_returns = returns.resample('M').apply(lambda x: (1 + x).prod() - 1)
        
        # Create pivot table
        pivot_data = pd.DataFrame({
            'Year': monthly_returns.index.year,
            'Month': monthly_returns.index.month,
            'Return': monthly_returns.values
        })
        
        pivot_table = pivot_data.pivot_table(
            values='Return',
            index='Year',
            columns='Month',
            aggfunc='mean'
        )
        
        # Month names
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        fig = go.Figure(
            data=go.Heatmap(
                z=pivot_table.values * 100,  # Convert to percentage
                x=month_names,
                y=pivot_table.index,
                colorscale='RdYlGn',
                zmid=0,
                text=pivot_table.values * 100,
                texttemplate='%{text:.1f}%',
                textfont={"size": 10},
                hoverongaps=False,
                colorbar=dict(title="Return (%)")
            )
        )
        
        fig.update_layout(
            title=title,
            xaxis_title="Month",
            yaxis_title="Year",
            height=400
        )
        
        return fig
    
    @staticmethod
    def create_radar_chart(
        metrics: Dict[str, float],
        title: str = "Strategy Performance Radar",
        max_values: Optional[Dict[str, float]] = None
    ) -> go.Figure:
        """
        레이더 차트 생성
        
        Args:
            metrics: 지표 딕셔너리
            title: 차트 제목
            max_values: 각 지표의 최대값 (정규화용)
        """
        categories = list(metrics.keys())
        values = list(metrics.values())
        
        # Normalize values if max_values provided
        if max_values:
            normalized_values = []
            for cat, val in zip(categories, values):
                max_val = max_values.get(cat, 1)
                normalized_values.append(val / max_val if max_val != 0 else 0)
            values = normalized_values
        
        fig = go.Figure()
        
        fig.add_trace(go.Scatterpolar(
            r=values,
            theta=categories,
            fill='toself',
            name='Performance'
        ))
        
        fig.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, 1] if max_values else [0, max(values) * 1.1]
                )
            ),
            showlegend=True,
            title=title
        )
        
        return fig
    
    @staticmethod
    def create_trade_scatter(
        trades: pd.DataFrame,
        x_col: str = 'duration',
        y_col: str = 'pnl',
        color_col: str = 'side',
        title: str = "Trade Analysis"
    ) -> go.Figure:
        """
        거래 분석 산점도 생성
        
        Args:
            trades: 거래 데이터프레임
            x_col: X축 컬럼명
            y_col: Y축 컬럼명
            color_col: 색상 구분 컬럼명
            title: 차트 제목
        """
        fig = px.scatter(
            trades,
            x=x_col,
            y=y_col,
            color=color_col,
            title=title,
            hover_data=trades.columns
        )
        
        # Add zero line
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        
        fig.update_layout(
            xaxis_title=x_col.replace('_', ' ').title(),
            yaxis_title=y_col.replace('_', ' ').title(),
            height=500
        )
        
        return fig


# Utility functions for common chart operations
def add_support_resistance_lines(
    fig: go.Figure,
    data: pd.DataFrame,
    lookback: int = 20,
    num_levels: int = 3
) -> go.Figure:
    """
    차트에 지지/저항선 추가
    
    Args:
        fig: Plotly figure
        data: OHLC 데이터
        lookback: 룩백 기간
        num_levels: 표시할 레벨 수
    """
    # Find local peaks and valleys
    highs = data['high'].rolling(window=lookback).max()
    lows = data['low'].rolling(window=lookback).min()
    
    # Get unique levels
    resistance_levels = highs.value_counts().nlargest(num_levels).index
    support_levels = lows.value_counts().nlargest(num_levels).index
    
    # Add resistance lines
    for level in resistance_levels:
        fig.add_hline(
            y=level,
            line_dash="dot",
            line_color="red",
            opacity=0.5,
            annotation_text=f"R: {level:.2f}"
        )
    
    # Add support lines
    for level in support_levels:
        fig.add_hline(
            y=level,
            line_dash="dot",
            line_color="green",
            opacity=0.5,
            annotation_text=f"S: {level:.2f}"
        )
    
    return fig


def add_trading_signals(
    fig: go.Figure,
    signals: pd.DataFrame,
    price_data: pd.Series,
    row: int = 1,
    col: int = 1
) -> go.Figure:
    """
    차트에 거래 신호 추가
    
    Args:
        fig: Plotly figure
        signals: 신호 데이터 (columns: ['date', 'side', 'price'])
        price_data: 가격 데이터
        row: subplot row
        col: subplot column
    """
    # Buy signals
    buy_signals = signals[signals['side'] == 'BUY']
    if not buy_signals.empty:
        fig.add_trace(
            go.Scatter(
                x=buy_signals['date'],
                y=buy_signals['price'],
                mode='markers',
                marker=dict(
                    symbol='triangle-up',
                    size=12,
                    color='green'
                ),
                name='Buy Signal'
            ),
            row=row, col=col
        )
    
    # Sell signals
    sell_signals = signals[signals['side'] == 'SELL']
    if not sell_signals.empty:
        fig.add_trace(
            go.Scatter(
                x=sell_signals['date'],
                y=sell_signals['price'],
                mode='markers',
                marker=dict(
                    symbol='triangle-down',
                    size=12,
                    color='red'
                ),
                name='Sell Signal'
            ),
            row=row, col=col
        )
    
    return fig