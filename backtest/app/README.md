# AlbraTrading Backtesting Platform

A comprehensive Streamlit-based backtesting platform with natural language strategy generation.

## 🚀 Features

### 1. **Natural Language Strategy Builder**
- Write trading strategies in Korean or English
- Automatic code generation from descriptions
- Support for multiple indicators and conditions

### 2. **Quick Backtest**
- Fast and easy backtesting interface
- Multiple data sources (Demo, Yahoo Finance, CSV, Binance)
- Real-time results visualization

### 3. **Advanced Analysis**
- Strategy comparison
- Walk-forward analysis
- Parameter optimization
- Portfolio backtesting
- Monte Carlo simulations

### 4. **Comprehensive Settings**
- API connections management
- Chart customization
- Data management
- Export/Import functionality

## 📁 Project Structure

```
backtest/app/
├── streamlit_app.py          # Main application entry
├── pages/                    # Application pages
│   ├── 1_🏠_Home.py         # Dashboard
│   ├── 2_📊_Quick_Backtest.py # Quick backtest interface
│   ├── 3_🔨_Strategy_Builder.py # Natural language builder
│   ├── 4_📈_Advanced_Analysis.py # Advanced analytics
│   └── 5_⚙️_Settings.py      # Settings management
├── core/                     # Core functionality
│   └── data_manager.py       # Data source management
└── components/               # Reusable components
    └── charts.py            # Chart components
```

## 🛠️ Installation

1. Install required packages:
```bash
pip install streamlit plotly pandas numpy yfinance
```

2. Run the application:
```bash
streamlit run backtest/app/streamlit_app.py
```

## 📊 Usage

### Quick Start
1. Navigate to "Quick Backtest"
2. Select a data source
3. Choose or describe your strategy
4. Click "백테스트 실행"

### Natural Language Strategy Example
```
20일 이동평균선이 50일 이동평균선을 상향 돌파하면 매수,
하향 돌파하면 매도. 손절 2%, 익절 5%.
```

### Advanced Analysis
- **Strategy Comparison**: Compare multiple strategies side-by-side
- **Walk-Forward**: Test strategy robustness over time
- **Optimization**: Find optimal parameters
- **Portfolio**: Combine strategies for better performance
- **Monte Carlo**: Analyze uncertainty and risk

## 🔧 Configuration

### Data Sources
- **Demo Data**: Built-in synthetic data for testing
- **Yahoo Finance**: Real market data
- **CSV Upload**: Your own data files
- **Binance API**: Cryptocurrency data (requires API key)

### Settings
- Default capital and costs
- Chart preferences
- API connections
- Data caching options

## 📈 Key Features

### 1. Performance Metrics
- Total Return
- Sharpe Ratio
- Maximum Drawdown
- Win Rate
- Calmar Ratio
- Profit Factor

### 2. Visualizations
- Equity curves
- Candlestick charts
- Performance radar charts
- Correlation heatmaps
- Monte Carlo paths
- Monthly returns heatmap

### 3. Risk Analysis
- Value at Risk (VaR)
- Conditional VaR
- Drawdown analysis
- Risk contribution
- Correlation analysis

## 🤝 Contributing

To add new features:
1. Add new pages in `pages/` directory
2. Create reusable components in `components/`
3. Extend data sources in `core/data_manager.py`

## 📝 Notes

- All timestamps are in KST (UTC+9)
- Demo data is for testing only
- Real trading requires proper API configuration
- Backtest results are stored in session state

## 🚨 Disclaimer

This is a backtesting platform for educational and research purposes. Past performance does not guarantee future results. Always conduct thorough research before real trading.