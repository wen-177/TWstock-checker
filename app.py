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
    
    /* 2. 讓主標題 (h1) 與副標題置中 */
    h1 {
        text-align: center;
    }
    .stCaptionContainer {
        text-align: center;
        display: flex;
        justify-content: center;
    }
    
    /* 3. 卡片等高與背景圓角 */
    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"] > div[data-testid="stBorderContainer"] {
        height: 100%;
        min-height: 160px;
        background-color: var(--background-secondary-color);
        border-radius: 12px;
        padding: 12px;
    }

    /* 4. 強制精準放大輸入框標題與文字（保留中） */
    div[data-testid="stTextInput"] label p {
        font-size: 20px !important;
        font-weight: bold !important;
        color: var(--text-color) !important;
    }
    
    div[data-testid="stTextInput"] input {
        font-size: 18px !important;
        height: 48px !important;
    }

    /* 5. 確保按鈕高度與輸入框對齊（保留中） */
    div[data-testid="stColumn"] button {
        height: 48px !important;
        margin-top: 2px !important;
    }

    /* 6. 響應式手機排版修正 */
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.8rem;
            padding-right: 0.8rem;
        }
        div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"] > div[data-testid="stBorderContainer"] {
            min-height: auto;
            margin-bottom: 10px;
        }
    /*7. 🌟 調整 st.metric 上方標題文字的大小與粗細 */
    div[data-testid="stMetricLabel"] p {
        font-size: 28px !important;    /* 這裡可以依喜好調整大小，例如 16px 或 20px */
        font-weight: bold !important;  /* 讓標題變粗體 */
    }
    }
</style>
""", unsafe_allow_html=True)


# --- 1. 從自建 CSV 總表快速讀取股票字典 ---
@st.cache_data(ttl=86400, show_spinner=False)
def load_all_taiwan_stocks():
    stock_dict = {}
    market_dict = {}
    
    try:
        # 直接讀取上傳的 stock_list.csv (需包含「代號」與「名稱」欄位)
        df_stocks = pd.read_csv("stock_list.csv", dtype=str)
        for _, row in df_stocks.iterrows():
            code = str(row['代號']).strip()
            name = str(row['名稱']).strip()
            if code and name:
                stock_dict[name] = code
                stock_dict[code] = code
                # 簡單市場別判斷：上櫃/興櫃或特定區段歸類為 TWO，其餘為 TW
                market_dict[code] = "TWO" if code.startswith(('3', '4', '5', '6', '8')) and len(code) == 4 else "TW"
    except Exception:
        # 讀取失敗時的基礎備援，確保系統不崩潰
        backup_stocks = {
            "台積電": "2330", "鴻海": "2317", "雷科": "6207", "聯發科": "2454", "元大台灣50": "0050"
        }
        for name, code in backup_stocks.items():
            stock_dict[name] = code
            stock_dict[code] = code
            market_dict[code] = "TWO" if code == "6207" else "TW"

    return stock_dict, market_dict


# --- 2. 智慧名稱與代碼對照 ---
def resolve_taiwan_stock(user_input, stock_dict):
    clean_input = user_input.strip()
    
    if clean_input.isdigit():
        name = next((k for k, v in stock_dict.items() if v == clean_input and not k.isdigit()), clean_input)
        return clean_input, name
    
    if clean_input in stock_dict:
        code = stock_dict[clean_input]
        return code, clean_input
    
    for name, code in stock_dict.items():
        if not name.isdigit() and (clean_input in name or name in clean_input):
            return code, name

    simplified_input = clean_input.replace("臺灣", "").replace("台灣", "").replace("台", "")
    for name, code in stock_dict.items():
        if not name.isdigit():
            simplified_name = name.replace("臺灣", "").replace("台灣", "").replace("台", "")
            if simplified_input and (simplified_input in simplified_name or simplified_name in simplified_input):
                return code, name

    return clean_input, clean_input


# --- 3. 股票歷史數據抓取 (FinMind + Yahoo Finance 雙源防護) ---
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_stock_data(stock_id, market_type="TW"):
    stock_id = str(stock_id).strip()
    df = pd.DataFrame()
    source = None

    # 嘗試 1: FinMind API Direct
    try:
        start_date = (pd.Timestamp.now() - pd.Timedelta(days=220)).strftime('%Y-%m-%d')
        url_fm = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice&data_id={stock_id}&start_date={start_date}"
        res = requests.get(url_fm, timeout=3)
        if res.status_code == 200:
            raw_data = res.json().get("data", [])
            if raw_data:
                raw_df = pd.DataFrame(raw_data)
                df = raw_df.rename(columns={
                    'open': 'Open', 'max': 'High', 'min': 'Low',
                    'close': 'Close', 'trading_turnover': 'Volume'
                })
                df['Date'] = pd.to_datetime(df['date'])
                source = "FinMind API"
    except Exception:
        pass

    # 嘗試 2: Yahoo Finance (帶 Header 避免雲端 IP 阻擋)
    if df.empty:
        suffixes = [".TW", ".TWO"] if market_type == "TW" else [".TWO", ".TW"]
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        for suffix in suffixes:
            try:
                ticker = f"{stock_id}{suffix}"
                session = requests.Session()
                session.headers.update(headers)
                yf_ticker = yf.Ticker(ticker, session=session)
                yf_df = yf_ticker.history(period="8m")
                
                if not yf_df.empty and len(yf_df) >= 5:
                    df = yf_df.reset_index()
                    if 'Date' in df.columns and hasattr(df['Date'].dt, 'tz_localize'):
                        df['Date'] = df['Date'].dt.tz_localize(None)
                    source = f"Yahoo Finance ({suffix})"
                    break
            except Exception:
                pass

    if not df.empty:
        for col in ['Open', 'High', 'Low', 'Close']:
            df[col] = df[col].astype(float)
        df = df.sort_values('Date').reset_index(drop=True)

    return df, source


# --- 4. 技術指標計算與健檢邏輯 ---
def calculate_indicators_and_health(df):
    close = df['Close']
    df['MA5'] = ta.trend.sma_indicator(close, window=5)
    df['MA10'] = ta.trend.sma_indicator(close, window=10)
    df['MA20'] = ta.trend.sma_indicator(close, window=20)
    df['MA60'] = ta.trend.sma_indicator(close, window=60)
    
    rsi_indicator = ta.momentum.RSIIndicator(close, window=14)
    df['RSI'] = rsi_indicator.rsi()
    
    stoch = ta.momentum.StochasticOscillator(
        high=df['High'], low=df['Low'], close=df['Close'], window=14, smooth_window=3
    )
    df['KD_K'] = stoch.stoch()
    df['KD_D'] = stoch.stoch_signal()

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    score = 0
    reasons = []

    # 1. 均線排列 (最大 40 分)
    if latest['Close'] > latest['MA5'] > latest['MA10'] > latest['MA20']:
        score += 40
        reasons.append("🟢 均線呈完美多頭排列，短中期趨勢強勁。")
    elif latest['Close'] > latest['MA20']:
        score += 25
        reasons.append("🟡 站穩月線 (MA20) 之上，中線趨勢偏多。")
    elif latest['Close'] > latest['MA60']:
        score += 15
        reasons.append("🟡 處於月線下方，但受季線 (MA60) 生命線支撐。")
    else:
        reasons.append("🔴 跌破短中期與季線均線，趨勢較弱，注意風險。")

    # 2. RSI 動能 (最大 30 分)
    if 50 <= latest['RSI'] <= 70:
        score += 30
        reasons.append(f"🟢 RSI 指標位居黃金動能區 ({latest['RSI']:.1f})，買盤熱絡。")
    elif latest['RSI'] > 70:
        score += 15
        reasons.append(f"⚠️ RSI 處於超買區 ({latest['RSI']:.1f})，短線留意獲利回吐壓力。")
    elif latest['RSI'] < 30:
        score += 10
        reasons.append(f"🟡 RSI 進入超賣區 ({latest['RSI']:.1f})，醞釀技術性反彈。")
    else:
        score += 20
        reasons.append(f"⚪ RSI 處於中性整理區 ({latest['RSI']:.1f})。")

    # 3. KD 交叉 (最大 30 分)
    if prev['KD_K'] < prev['KD_D'] and latest['KD_K'] >= latest['KD_D']:
        score += 30
        reasons.append(f"🟢 KD 指標低檔黃金交叉 (K: {latest['KD_K']:.1f}, D: {latest['KD_D']:.1f})，轉折向上。")
    elif latest['KD_K'] > latest['KD_D']:
        score += 20
        reasons.append(f"🟢 KD 指標多頭格局維持中 (K: {latest['KD_K']:.1f})。")
    else:
        score += 5
        reasons.append(f"🔴 KD 指標死亡交叉或向下修正中 (K: {latest['KD_K']:.1f})。")

    # 4. 交易價格建議邏輯
    if score >= 75:
        buy_price = latest['MA10']
        buy_strategy = "多頭強勢拉回 MA10"
    elif score >= 50:
        buy_price = latest['MA20']
        buy_strategy = "月線支撐 (MA20)"
    else:
        buy_price = latest['MA60'] if not pd.isna(latest['MA60']) else latest['MA20']
        buy_strategy = "季線大支撐 (MA60)"

    take_profit = latest['Close'] * 1.10
    stop_loss = buy_price * 0.93

    return df, score, reasons, round(buy_price, 2), round(take_profit, 2), round(stop_loss, 2), buy_strategy


# --- 5. 主應用程式介面 ---
def main():
    st.title("📈 台股單股快速健檢診斷室")
    st.caption("自動整合 MA / RSI / KD 多維度技術分析，提供最客觀的買賣防守參考價")

    stock_dict, market_dict = load_all_taiwan_stocks()

    col_input, col_btn = st.columns([4, 1])
    with col_input:
        stock_input = st.text_input("輸入股票名稱或代號：", value="2330", placeholder="例如：2330、台積電、雷科、0050")
    with col_btn:
        st.write(" ")
        st.write(" ")
        search_btn = st.button("🔍 開始健檢", use_container_width=True)

    if search_btn or stock_input:
        with st.spinner("🔍 正在從自建總表解析並取得最新數據..."):
            resolved_code, display_name = resolve_taiwan_stock(stock_input, stock_dict)
            market_type = market_dict.get(resolved_code, "TW")
            
            df, source = fetch_stock_data(resolved_code, market_type)

            if df.empty or len(df) < 10:
                st.error(f"❌ 查無台股 '{stock_input}' (代碼: {resolved_code}) 的歷史數據，請確認名稱或 4 位數代碼是否正確。")
                return

            df, score, reasons, buy_price, take_profit, stop_loss, buy_strategy = calculate_indicators_and_health(df)
            latest = df.iloc[-1]
            date_str = latest['Date'].strftime('%Y-%m-%d')

            # --- 頂部看板 ---
            st.subheader(f"📊 {display_name} ({resolved_code}) 健檢總覽 ({date_str})")
            
            card_col1, card_col2, card_col3, card_col4, card_col5 = st.columns(5, gap="small")
            
            with card_col1:
                with st.container(border=True):
                    st.metric(label="當前收盤價", value=f"${latest['Close']:.2f}")

            with card_col2:
                with st.container(border=True):
                    status_text = f"🟢 {score}分" if score >= 75 else (f"🟡 {score}分" if score >= 50 else f"🔴 {score}分")
                    st.metric(label="健康度評分", value=status_text)

            with card_col3:
                with st.container(border=True):
                    st.metric(label=f"適合買進價 💡 ({buy_strategy})", value=f"${buy_price}")

            with card_col4:
                with st.container(border=True):
                    st.metric(label="建議停利價 🎯", value=f"${take_profit}")

            with card_col5:
                with st.container(border=True):
                    st.metric(label="建議停損價 🛑", value=f"${stop_loss}")

            st.write("---")

            # --- 中間雙欄對齊看板 ---
            left_col, right_col = st.columns(2, gap="medium")

            with left_col:
                with st.container(border=True):
                    st.subheader("📋 技術面體檢診斷")
                    reasons_html = "".join([f'<p class="reason-text">{r}</p>' for r in reasons])
                    st.markdown(reasons_html, unsafe_allow_html=True)
                    st.caption(f"數據來源：{source} | 自動更新於市場每日收盤後")

            with right_col:
                with st.container(border=True):
                    st.subheader("📈 近期 K 線與均線走勢 (含 MA60 季線)")
                    chart_df = df.tail(60)
                    
                    fig = go.Figure()
                    fig.add_trace(go.Candlestick(
                        x=chart_df['Date'], open=chart_df['Open'], high=chart_df['High'],
                        low=chart_df['Low'], close=chart_df['Close'], name="K線"
                    ))
                    fig.add_trace(go.Scatter(x=chart_df['Date'], y=chart_df['MA5'], line=dict(color='orange', width=1.5), name="MA5"))
                    fig.add_trace(go.Scatter(x=chart_df['Date'], y=chart_df['MA10'], line=dict(color='cyan', width=1.5), name="MA10"))
                    fig.add_trace(go.Scatter(x=chart_df['Date'], y=chart_df['MA20'], line=dict(color='magenta', width=1.5), name="MA20"))
                    fig.add_trace(go.Scatter(x=chart_df['Date'], y=chart_df['MA60'], line=dict(color='green', width=2.0), name="MA60 季線"))
                    
                    fig.update_layout(
                        margin=dict(l=10, r=10, t=10, b=10),
                        xaxis_rangeslider_visible=False,
                        height=350,
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    st.plotly_chart(fig, use_container_width=True)

if __name__ == "__main__":
    main()
