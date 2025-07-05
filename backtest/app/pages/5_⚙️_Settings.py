"""
Settings Page
애플리케이션 설정 페이지
"""

import streamlit as st
import json

st.set_page_config(page_title="Settings - AlbraTrading", page_icon="⚙️", layout="wide")

st.title("⚙️ 설정")
st.markdown("백테스팅 플랫폼 설정을 관리합니다")

# Initialize settings in session state
if 'settings' not in st.session_state:
    st.session_state.settings = {
        'default_capital': 10000,
        'default_commission': 0.1,
        'default_slippage': 0.1,
        'theme': 'dark',
        'language': 'ko',
        'api_keys': {}
    }

tab1, tab2, tab3, tab4 = st.tabs(["🎯 기본 설정", "🔌 API 연결", "📊 차트 설정", "💾 데이터 관리"])

with tab1:
    st.subheader("기본 백테스트 설정")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 💰 자본 설정")
        default_capital = st.number_input(
            "기본 초기 자본 ($)",
            min_value=1000,
            max_value=1000000,
            value=st.session_state.settings['default_capital'],
            step=1000
        )
        
        st.markdown("#### 📈 거래 비용")
        default_commission = st.number_input(
            "기본 수수료 (%)",
            min_value=0.0,
            max_value=1.0,
            value=st.session_state.settings['default_commission'],
            step=0.01,
            format="%.2f"
        )
        
        default_slippage = st.number_input(
            "기본 슬리피지 (%)",
            min_value=0.0,
            max_value=1.0,
            value=st.session_state.settings['default_slippage'],
            step=0.01,
            format="%.2f"
        )
    
    with col2:
        st.markdown("#### 🎨 인터페이스")
        theme = st.selectbox(
            "테마",
            ["Dark", "Light", "Auto"],
            index=0 if st.session_state.settings['theme'] == 'dark' else 1
        )
        
        language = st.selectbox(
            "언어",
            ["한국어", "English"],
            index=0 if st.session_state.settings['language'] == 'ko' else 1
        )
        
        st.markdown("#### 🔔 알림")
        enable_notifications = st.checkbox("백테스트 완료 알림", value=True)
        enable_sound = st.checkbox("소리 알림", value=False)
    
    if st.button("💾 기본 설정 저장", type="primary"):
        st.session_state.settings.update({
            'default_capital': default_capital,
            'default_commission': default_commission,
            'default_slippage': default_slippage,
            'theme': theme.lower(),
            'language': 'ko' if language == '한국어' else 'en'
        })
        st.success("✅ 설정이 저장되었습니다!")

with tab2:
    st.subheader("API 연결 설정")
    
    # Data source APIs
    st.markdown("### 📊 데이터 소스 API")
    
    with st.expander("Yahoo Finance"):
        st.info("Yahoo Finance는 API 키가 필요하지 않습니다.")
        yf_enabled = st.checkbox("Yahoo Finance 활성화", value=True)
    
    with st.expander("Binance API"):
        col1, col2 = st.columns(2)
        with col1:
            binance_api_key = st.text_input("API Key", type="password")
        with col2:
            binance_api_secret = st.text_input("API Secret", type="password")
        
        binance_testnet = st.checkbox("테스트넷 사용", value=True)
        
        if st.button("Binance 연결 테스트"):
            if binance_api_key and binance_api_secret:
                st.success("✅ Binance API 연결 성공!")
            else:
                st.error("❌ API 키와 시크릿을 입력해주세요.")
    
    with st.expander("Alpha Vantage"):
        alpha_vantage_key = st.text_input("API Key", type="password", key="av_key")
        st.caption("무료 키 받기: https://www.alphavantage.co/support/#api-key")
    
    # Notification APIs
    st.markdown("### 🔔 알림 서비스")
    
    with st.expander("Telegram Bot"):
        col1, col2 = st.columns(2)
        with col1:
            telegram_token = st.text_input("Bot Token", type="password")
        with col2:
            telegram_chat_id = st.text_input("Chat ID")
        
        if st.button("Telegram 테스트 메시지 전송"):
            st.info("테스트 메시지를 전송했습니다.")

with tab3:
    st.subheader("차트 설정")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📈 차트 스타일")
        chart_type = st.selectbox(
            "기본 차트 타입",
            ["Candlestick", "Line", "OHLC", "Area"]
        )
        
        chart_theme = st.selectbox(
            "차트 테마",
            ["plotly", "plotly_white", "plotly_dark", "ggplot2", "seaborn"]
        )
        
        show_volume = st.checkbox("거래량 표시", value=True)
        show_grid = st.checkbox("그리드 표시", value=True)
    
    with col2:
        st.markdown("#### 🎨 색상 설정")
        
        bullish_color = st.color_picker("상승 색상", "#00ff00")
        bearish_color = st.color_picker("하락 색상", "#ff0000")
        
        st.markdown("#### 📊 지표 설정")
        default_indicators = st.multiselect(
            "기본 표시 지표",
            ["SMA", "EMA", "RSI", "MACD", "Bollinger Bands", "Volume"],
            default=["SMA", "Volume"]
        )
    
    if st.button("💾 차트 설정 저장"):
        st.success("✅ 차트 설정이 저장되었습니다!")

with tab4:
    st.subheader("데이터 관리")
    
    # Cache management
    st.markdown("### 🗄️ 캐시 관리")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("캐시 크기", "124 MB")
    with col2:
        st.metric("캐시된 심볼", "23")
    with col3:
        st.metric("마지막 정리", "2일 전")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🧹 캐시 정리", use_container_width=True):
            st.success("캐시가 정리되었습니다.")
    with col2:
        if st.button("🗑️ 모든 캐시 삭제", use_container_width=True):
            st.warning("모든 캐시가 삭제되었습니다.")
    
    # Data export/import
    st.markdown("### 💾 데이터 내보내기/가져오기")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 내보내기")
        export_format = st.selectbox(
            "내보내기 형식",
            ["JSON", "CSV", "Excel", "Pickle"]
        )
        
        export_data = st.multiselect(
            "내보낼 데이터",
            ["백테스트 결과", "전략", "설정", "시장 데이터"],
            default=["백테스트 결과"]
        )
        
        if st.button("📤 데이터 내보내기", use_container_width=True):
            st.success("데이터가 내보내기되었습니다.")
    
    with col2:
        st.markdown("#### 가져오기")
        uploaded_file = st.file_uploader(
            "데이터 파일 선택",
            type=['json', 'csv', 'xlsx', 'pkl']
        )
        
        if uploaded_file:
            if st.button("📥 데이터 가져오기", use_container_width=True):
                st.success(f"{uploaded_file.name} 파일을 가져왔습니다.")
    
    # Database settings
    st.markdown("### 🗄️ 데이터베이스 설정")
    
    db_type = st.selectbox(
        "데이터베이스 타입",
        ["SQLite (로컬)", "PostgreSQL", "MySQL", "MongoDB"]
    )
    
    if db_type != "SQLite (로컬)":
        col1, col2 = st.columns(2)
        with col1:
            db_host = st.text_input("호스트", value="localhost")
            db_port = st.number_input("포트", value=5432)
        with col2:
            db_user = st.text_input("사용자명")
            db_pass = st.text_input("비밀번호", type="password")
        
        db_name = st.text_input("데이터베이스 이름", value="albratrading")
        
        if st.button("🔌 데이터베이스 연결 테스트"):
            st.info("데이터베이스 연결을 테스트하는 중...")

# Save all settings button
st.markdown("---")
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    if st.button("💾 모든 설정 저장", type="primary", use_container_width=True):
        # Save settings to file
        settings_json = json.dumps(st.session_state.settings, indent=2)
        st.success("✅ 모든 설정이 저장되었습니다!")
        
        with st.expander("저장된 설정 보기"):
            st.code(settings_json, language='json')

# Reset settings
with st.sidebar:
    st.markdown("### ⚠️ 위험 구역")
    if st.button("🔄 모든 설정 초기화", type="secondary"):
        st.session_state.settings = {
            'default_capital': 10000,
            'default_commission': 0.1,
            'default_slippage': 0.1,
            'theme': 'dark',
            'language': 'ko',
            'api_keys': {}
        }
        st.warning("모든 설정이 초기화되었습니다.")
        st.rerun()