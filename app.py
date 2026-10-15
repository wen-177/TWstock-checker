import streamlit as st
import pandas as pd
import ta
import yfinance as yf
import plotly.graph_objects as go
import requests

# --- 頁面設定 ---
st.set_page_config(
    page_title="Taiwan Stock Health Checker",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- 全局 CSS 樣式 ---
st.markdown("""
<style>
    /* 1. 調整主容器邊距 */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        padding-left: 2rem;
        padding-right: 2rem;
    }
    
    /* 2. 卡片等高與背景圓角 */
    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"] > div[data-testid="stBorderContainer"] {
        height: 100%;
        min-height: 220px;
        background-color: var(--background-secondary-color);
        border-radius: 12px;
        padding: 16px;
    }

    /* 3. 頂部看板標題字體大小 (可在此統一修改像素值) */
    .card-label {
        font-size: 22px !important;
        font-weight: bold !important;
        margin-bottom: 4px !important;
        line-height: 1.3 !important;
        color: var(--text-color);
    }

    /* 4. 健檢診斷細節文字大小 (可在此統一修改像素值) */
    .reason-text {
        font-size: 20px !important;
        font-weight: 500 !important;
        margin-bottom: 12px !important;
        line-height: 1.6 !important;
        color: var(--text-color);
    }

    /* 5. 響應式手機排版修正 */
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.8rem;
            padding-right: 0.8rem;
        }
        div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"] > div[data-testid="stBorderContainer"] {
            min-height: auto;
            margin-bottom: 10px;
        }
    }
</style>
""", unsafe_allow_html=True)


# --- 1. 載入全台股與 ETF 清單 (超時控制 + 快取) ---
@st.cache_data(ttl=86400, show_spinner=False)
def load_all_taiwan_stocks():
    stock_dict = {}
    market_dict = {}
    
    # 內建常態備援字典 (確保離線或 API 異常時仍能查到雷科、台積電等重點股)
    backup_stocks = {
        "雷科": "6207", "台積電": "2330", "鴻海": "2317", "聯發科": "2454", 
        "廣達": "2382", "緯創": "3231", "技嘉": "2376", "長榮": "2603",
        "陽明": "2609", "萬海": "2615", "富邦金": "2881", "國泰金": "2882",
        "中信金": "2891", "玉山金": "2884", "兆豐金": "2886", "台新金": "2887",
        "元大台灣50": "0050", "國泰永續高股息": "
