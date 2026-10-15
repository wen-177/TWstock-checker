import streamlit as st
import pandas as pd
import ta
import yfinance as yf
import plotly.graph_objects as go
import requests
from FinMind.data import DataLoader

# 頁面基本設定
st.set_page_config(page_title="台股單股快速健檢", page_icon="📊", layout="wide")

# ==================== 1. 全站 CSS 樣式控制 ====================
st.markdown("""
    <style>
    /* 1. 全站基礎字體 */
    html, body, [class*="css"] { 
        font-size: 18px; 
    }

    /* 2. 主標題置中樣式 */
    .custom-title {
        text-align: center;
        font-size: 40px !important;
        font-weight: bold;
        margin-bottom: 8px;
        color: var(--text-color);
    }

    /* 3. 搜尋輸入框內部輸入字體 */
    .stTextInput input {
        font-size: 22px !important;       
        font-weight: bold !important;     
        padding: 12px 16px !important;    
        border-radius: 8px !important;
    }

    /* 4. 輸入框上方標題字體 */
    div[data-testid="stWidgetLabel"] p {
        font-size: 24px !important;
        font-weight: 800 !important;
        line-height: 1.5 !important;
    }

    /* 5. 按鈕視覺與高度 */
    .stButton button {
        font-size: 20px !important;
        font-weight: bold !important;
        padding: 12px 0px !important;     
        border-radius: 8px !important;
    }

    /* 6. 響應式微調 (手機螢幕 < 768px) */
    @media (max-width: 768px) {
        .custom-title { font-size: 28px !important; }
        div[data-testid="stWidgetLabel"] p { font-size: 20px !important; }
        .stTextInput input { font-size: 18px !important; padding: 10px 12px !important; }
        .stButton button { font-size: 18px !important; }
        [data-testid="stMetricValue"] { font-size: 22px !important; }
    }

    /* 7. 頂部看板小標題字體大小 (可在這裡統一修改像素值) */
    .card-label {
        font-size: 24px !important;    /* 👈 統一調整這個數字 (例如 20px, 22px, 24px) */
        font-weight: bold !important;
        margin-bottom: 2px !important;
        line-height: 1.3 !important;
        color: var(--text-color);
    }

    /* 8. 健檢診斷細節文字大小 */
    .reason-text {
        font-size: 22px !important;     /* 👈 修改這裡控制字體大小 */
        font-weight: 500 !important;    /* 👈 修改這裡控制字體粗細 */
        margin-bottom: 12px !important;
        line-height: 1.6 !important;
        color: var(--text-color);
    }
    </style>
""", unsafe_allow_html=True)


# ==================== 2. 高速快取與資料載入 ====================

@st.cache_data(ttl=86400)
def load_all_taiwan_stocks():
    stock_dict = {}  # 名稱 -> 代碼
    market_dict = {} # 代碼 -> 市場別
    
    # 0. 內建常備熱門與上櫃個股對照表 (確保離線或 Open API 異常時仍能查到雷科、台積電等)
    backup_stocks = {
        "雷科": "6207", "台積電": "2330", "鴻海": "2317", "聯發科": "2454", 
        "廣達": "2382", "緯創": "3231", "技嘉": "2376", "長榮": "2603",
        "陽明": "2609", "萬海": "2615", "富邦金": "2881", "國泰金": "2882",
        "中信金": "2891", "玉山金": "2884", "兆豐金": "2886", "台新金": "2887",
        "元大台灣50": "0050", "國泰永續高股息": "00878", "群益台灣精選高息": "00919",
        "復華台灣科技優息": "00929", "元大高股息": "0056"
    }
    for name, code in backup_stocks.items():
        stock_dict[name] = code
        stock_dict[code] = code

    # 1. 使用 FinMind 官方股票清單 API (最穩定，包含上市/上櫃/ETF 所有台股)
    try:
        url_finmind = "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInfo"
        res = requests.get(url_finmind, timeout=6)
        if res.status_code == 200:
            data = res.json().get("data", [])
            for item in data:
                code = item.get("stock_id", "").strip()
                name = item.get("stock_name", "").strip()
                industry = item.get("industry_category", "")
                if code and name:
                    stock_dict[name] = code
                    stock_dict[code] = code
                    # 判斷市場類型
                    if "上櫃" in industry or "TPEx" in industry:
                        market_dict[code] = "TWO"
                    else:
                        market_dict[code] = "TW"
            return stock_dict, market_dict
    except Exception:
        pass

    # 2. 備援：證交所 (TWSE) OpenAPI
    try:
        url_twse = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
        res = requests.get(url_twse, timeout=4)
        if res.status_code == 200:
            for item in res.json():
                code = item.get('Code', '').strip()
                name = item.get('Name', '').strip()
                if code and name:
                    stock_dict[name] = code
                    stock_dict[code] = code
                    market_dict[code] = "TW"
    except Exception:
        pass

    # 3. 備援：櫃買中心 (TPEx) OpenAPI
    try:
        url_tpex = "https://www.tpex.org.tw/openapi/v1/mops_after_market_information"
        res = requests.get(url_tpex, timeout=4)
        if res.status_code == 200:
            for item in res.json():
                code = item.get('SecuritiesCompanyCode', item.get('Code', '')).strip()
                name = item.get('CompanyName', item.get('Name', '')).strip()
                if code and name:
                    stock_dict[name] = code
                    stock_dict[code] = code
                    market_dict[code] = "TWO"
    except Exception:
        pass

    return stock_dict, market_dict


def resolve_taiwan_stock(user_input, stock_dict):
    clean_input = user_input.strip()
    
    # 情況 A：輸入純數字代號 (如: 6207, 2330, 00878)
    if clean_input.isdigit():
        # 嘗試找出對應中文名
        name = next((k for k, v in stock_dict.items() if v == clean_input and not k.isdigit()), clean_input)
        return clean_input, name
    
    # 情況 B：精準名稱比對 (如: 雷科)
    if clean_input in stock_dict:
        code = stock_dict[clean_input]
        return code, clean_input
    
    # 情況 C：模糊比對 (包含子字串)
    for name, code in stock_dict.items():
        if not name.isdigit() and (clean_input in name or name in clean_input):
            return code, name

    # 情況 D：去除「台/臺灣」等異體字比對
    simplified_input = clean_input.replace("臺灣", "").replace("台灣", "").replace("台", "")
    for name, code in stock_dict.items():
        if not name.isdigit():
            simplified_name = name.replace("臺灣", "").replace("台灣", "").replace("台", "")
            if simplified_input and (simplified_input in simplified_name or simplified_name in simplified_input):
                return code, name

    # 無法解析代碼時，返回原始輸入
    return clean_input, clean_input


def fetch_stock_data(stock_id, market_type="TW"):
    stock_id = stock_id.strip()
    df = pd.DataFrame()
    source = None

    # 嘗試 1: FinMind
    try:
        dl = DataLoader()
        start_date = (pd.Timestamp.now() - pd.Timedelta(days=180)).strftime('%Y-%m-%d')
        raw_df = dl.taiwan_stock_daily(stock_id=stock_id, start_date=start_date)
        if not raw_df.empty:
            df = raw_df.rename(columns={
                'open': 'Open', 'max': 'High', 'min': 'Low',
                'close': 'Close', 'trading_turnover': 'Volume'
            })
            df['Date'] = pd.to_datetime(df['date'])
            source = "FinMind"
    except Exception:
        pass

    # 嘗試 2: Yahoo Finance
    if df.empty:
        suffix_list = [".TW", ".TWO"] if market_type == "TW" else [".TWO", ".TW"]
        for suffix in suffix_list:
            try:
                ticker = f"{stock_id}{suffix}"
                yf_df = yf.Ticker(ticker).history(period="6m")
                if not yf_df.empty:
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


def evaluate_health(df):
    latest = df.iloc[-1]
    close = float(latest['Close'])
    ma5 = float(latest['MA5'])
    ma10 = float(latest['MA10'])
    ma20 = float(latest['MA20'])
    ma60 = float(latest['MA60']) if 'MA60' in df.columns and not pd.isna(latest['MA60']) else ma20
    rsi = float(latest['RSI'])
    k_val = float(latest['K'])
    d_val = float(latest['D'])

    score = 0
    reasons = []

    # 1. 均線趨勢 (40分)
    if close > ma5 > ma10 > ma20:
        score += 40
        reasons.append("🟢 均線完美多頭排列：短中長期趨勢皆強勁偏多 (+40分)")
    elif close > ma10 > ma20:
        score += 30
        reasons.append("🟢 站上十日線與月線：中短期多頭格局穩健 (+30分)")
    elif close > ma20:
        score += 20
        reasons.append("🟡 站上月線：股價尚維持在月線支撐之上 (+20分)")
    elif close > ma5:
        score += 10
        reasons.append("🟠 僅站上五日線：短線有反彈，但中長期壓力未過 (+10分)")
    else:
        reasons.append("🔴 跌破短中期均線：股價低於 MA5、MA10 與 MA20，趨勢偏弱 (+0分)")

    # 2. RSI 動能 (30分)
    if 50 <= rsi <= 70:
        score += 30
        reasons.append("🟢 RSI 強勢區 (50~70)：買盤動能充沛 (+30分)")
    elif 30 <= rsi < 50:
        score += 20
        reasons.append("🟡 RSI 中立區 (30~50)：動能平淡，盤整觀望 (+20分)")
    elif rsi > 70:
        score += 15
        reasons.append("🟠 RSI 過熱 (>70)：短線買氣旺盛但有拉回過熱風險 (+15分)")
    else:
        score += 10
        reasons.append("🔴 RSI 過冷 (<30)：短線超賣，隨時可能反彈但目前極弱 (+10分)")

    # 3. KD 交叉 (30分)
    if k_val > d_val:
        score += 30
        reasons.append("🟢 KD 黃金交叉/多頭控盤：K值大於D值，短線偏多 (+30分)")
    else:
        reasons.append("🔴 KD 死亡交叉/空頭修正：K值小於D值，短線面臨修正 (+10分)")
        score += 10

    # 4. 🎯 自動動態判斷「適合買進價」
    if close >= ma10:
        buy_price = round((ma5 + ma10) / 2, 2)
        buy_strategy = "強勢拉回 (MA5~MA10)"
    elif close >= ma20:
        buy_price = round(ma20, 2)
        buy_strategy = "月線支撐 (MA20)"
    else:
        buy_price = round(ma60, 2)
        buy_strategy = "季線大支撐 (MA60)"

    # 風控點位計算
    recent_20_low = float(df['Low'].tail(20).min())
    stop_loss = round(min(ma20, recent_20_low), 2)
    if close < ma20:
        stop_loss = round(min(ma60, recent_20_low), 2)
        
    risk = close - stop_loss
    if risk <= 0:
        stop_loss = round(close * 0.95, 2)
        risk = close * 0.05

    take_profit = round(close + (risk * 1.5), 2)

    return score, reasons, buy_price, buy_strategy, stop_loss, take_profit


# ==================== 3. 前端 UI 排版 ====================

# 載入股票字典
stock_dict, market_dict = load_all_taiwan_stocks()

left_pad, form_col, right_pad = st.columns([1, 3, 1])

with form_col:
    st.markdown('<div class="custom-title">🔍 台股單股快速健檢診斷室</div>', unsafe_allow_html=True)
    st.markdown(
        '<p style="text-align: center; font-size: 20px; font-weight: 500; opacity: 0.85; margin-bottom: 24px; color: var(--text-color);">'
        '支援全台股（上市、上櫃、ETF）名稱或代碼，秒級分析健康度評分與風控點位。'
        '</p>', 
        unsafe_allow_html=True
    )

    with st.form(key="search_form"):
        search_col1, search_col2 = st.columns([3, 1], vertical_alignment="bottom")
        with search_col1:
            stock_input = st.text_input("輸入股票名稱或代號", value="台積電", placeholder="例如：台積電、2330、鈊象、00878")
        with search_col2:
            submit_btn = st.form_submit_button("🚀 立即分析", use_container_width=True)

if stock_input:
    resolved_code, display_name = resolve_taiwan_stock(stock_input, stock_dict)
    market_type = market_dict.get(resolved_code, "TW")

    with st.spinner(f"正在分析 {display_name} ({resolved_code}) 中..."):
        df, source = fetch_stock_data(resolved_code, market_type)

        if df.empty:
            st.error(f"❌ 查無台股 '{stock_input}' (代碼: {resolved_code}) 的歷史數據，請確認名稱或代碼是否正確。")
        else:
            # 計算指標 (增加 MA60 季線)
            df['MA5'] = ta.trend.sma_indicator(df['Close'], window=5)
            df['MA10'] = ta.trend.sma_indicator(df['Close'], window=10)
            df['MA20'] = ta.trend.sma_indicator(df['Close'], window=20)
            df['MA60'] = ta.trend.sma_indicator(df['Close'], window=60)
            df['RSI'] = ta.momentum.rsi(df['Close'], window=14)
            df['K'] = ta.momentum.stoch_signal(df['High'], df['Low'], df['Close'], window=9, smooth_window=3)
            df['D'] = ta.momentum.stoch(df['High'], df['Low'], df['Close'], window=9, smooth_window=3)

            latest = df.iloc[-1]
            date_str = latest['Date'].strftime('%Y-%m-%d')
            score, reasons, buy_price, buy_strategy, stop_loss, take_profit = evaluate_health(df)

            st.divider()

            # --- 頂部看板 ---
            st.subheader(f"📊 {display_name} ({resolved_code}) 健檢總覽 ({date_str})")
            
            card_col1, card_col2, card_col3, card_col4, card_col5 = st.columns(5, gap="small")
            
            with card_col1:
                with st.container(border=True):
                    st.markdown('<p class="card-label">當前收盤價</p>', unsafe_allow_html=True)
                    st.title(f"${latest['Close']:.2f}")

            with card_col2:
                with st.container(border=True):
                    st.markdown('<p class="card-label">健康度評分</p>', unsafe_allow_html=True)
                    if score >= 75:
                        st.title(f"🟢 {score}分")
                    elif score >= 50:
                        st.title(f"🟡 {score}分")
                    else:
                        st.title(f"🔴 {score}分")

            with card_col3:
                with st.container(border=True):
                    st.markdown(
                        f'<div style="display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap;">'
                        f'  <p class="card-label" style="margin: 0;">適合買進價 💡</p>'
                        f'  <span style="font-size: 16px; font-weight: 600; color: #3b82f6; opacity: 0.9;">({buy_strategy})</span>'
                        f'</div>', 
                        unsafe_allow_html=True
                    )
                    st.title(f"${buy_price}")

            with card_col4:
                with st.container(border=True):
                    st.markdown('<p class="card-label">建議停利價 🎯</p>', unsafe_allow_html=True)
                    st.title(f"${take_profit}")

            with card_col5:
                with st.container(border=True):
                    st.markdown('<p class="card-label">建議停損價 🛑</p>', unsafe_allow_html=True)
                    st.title(f"${stop_loss}")

            # --- 中間雙欄對齊看板 (CSS Grid 絕對等高) ---
            reasons_html = "".join([
                f'<p class="reason-text">{r}</p>'
                for r in reasons
            ])

            st.markdown(f"""
                <style>
                .equal-height-grid {{
                    display: grid;
                    grid-template-columns: 3fr 2fr;
                    gap: 16px;
                    margin-bottom: 24px;
                }}
                @media (max-width: 768px) {{
                    .equal-height-grid {{
                        grid-template-columns: 1fr;
                    }}
                }}
                .equal-card {{
                    border: 1px solid rgba(250, 250, 250, 0.2);
                    border-radius: 8px;
                    padding: 20px;
                    height: 100%;
                    box-sizing: border-box;
                    background-color: rgba(255, 255, 255, 0.02);
                }}
                .metric-box {{
                    background: rgba(255, 255, 255, 0.04);
                    padding: 16px 12px;
                    border-radius: 8px;
                    text-align: center;
                }}
                .metric-label {{ 
                    font-size: 24px !important; 
                    font-weight: 600; 
                    opacity: 0.9; 
                    margin-bottom: 6px; 
                }}
                .metric-val {{ 
                    font-size: 28px !important; 
                    font-weight: bold; 
                }}
                </style>

                <div class="equal-height-grid">
                    <!-- 左框：健檢評分細節診斷 -->
                    <div class="equal-card">
                        <h3 style="margin-top:0; font-size: 28px;">📝 健檢評分細節診斷</h3>
                        {reasons_html}
                    </div>
                    <!-- 右框：技術指標即時數據 -->
                    <div class="equal-card" style="display: flex; flex-direction: column; justify-content: space-between;">
                        <h3 style="margin-top:0; font-size: 28px;">📈 技術指標即時數據</h3>
                        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin-bottom: 12px;">
                            <div class="metric-box">
                                <div class="metric-label">MA5 🟠</div>
                                <div class="metric-val">${latest['MA5']:.2f}</div>
                            </div>
                            <div class="metric-box">
                                <div class="metric-label">MA10 🟣</div>
                                <div class="metric-val">${latest['MA10']:.2f}</div>
                            </div>
                            <div class="metric-box">
                                <div class="metric-label">MA20 🔵</div>
                                <div class="metric-val">${latest['MA20']:.2f}</div>
                            </div>
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                            <div class="metric-box">
                                <div class="metric-label">MA60 (季線) 🔴</div>
                                <div class="metric-val">${latest['MA60']:.2f}</div>
                            </div>
                            <div class="metric-box">
                                <div class="metric-label">RSI / KD</div>
                                <div class="metric-val">{latest['RSI']:.1f} / {latest['K']:.0f}</div>
                            </div>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

            st.divider()

            # --- 下方 K 線圖 (包含 MA60 季線) ---
            st.subheader("📉 歷史走勢與均線疊加圖")
            
            date_x = df['Date'].dt.strftime('%Y-%m-%d')

            fig = go.Figure()
            fig.add_trace(go.Candlestick(
                x=date_x,
                open=df['Open'], high=df['High'],
                low=df['Low'], close=df['Close'],
                name="K線"
            ))
            fig.add_trace(go.Scatter(x=date_x, y=df['MA5'], line=dict(color='orange', width=1.5), name="MA5 🟠"))
            fig.add_trace(go.Scatter(x=date_x, y=df['MA10'], line=dict(color='mediumpurple', width=1.5), name="MA10 🟣"))
            fig.add_trace(go.Scatter(x=date_x, y=df['MA20'], line=dict(color='deepskyblue', width=1.5), name="MA20 🔵"))
            fig.add_trace(go.Scatter(x=date_x, y=df['MA60'], line=dict(color='crimson', width=1.5), name="MA60 🔴"))
            
            fig.update_layout(
                xaxis_rangeslider_visible=False,
                xaxis=dict(type='category', nticks=10),
                height=480,
                margin=dict(l=10, r=10, t=10, b=10)
            )
            
            st.plotly_chart(fig, use_container_width=True)

            st.markdown(
                f'<p style="font-size: 18px; font-weight: 500; opacity: 0.8; margin-top: 12px; color: var(--text-color);">'
                f'數據來源：{source} ｜ 本站結果僅供參考，不構成任何投資買賣建議。'
                f'</p>', 
                unsafe_allow_html=True
            )