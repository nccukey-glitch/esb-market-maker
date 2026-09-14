import os
import streamlit as st
import pandas as pd
from datetime import datetime, date

from data_processor import process_daily_market, process_date_range
from database.db_manager import db
from calculation.chip import calculate_broker_chips, get_net_buy_sell_rankings
from calculation.pnl import calculate_stock_estimated_mm_pnl
from calculation.allocation import allocate_estimated_mm_pnl
from data_fetcher.tpex import normalize_date
from data_fetcher.broker import get_broker_name

def check_password() -> bool:
    """
    Checks if password protection is enabled via Streamlit secrets or env var.
    If no password is set, allows direct access.
    """
    configured_pwd = None
    try:
        if "password" in st.secrets:
            configured_pwd = str(st.secrets["password"])
        elif "auth" in st.secrets and "password" in st.secrets["auth"]:
            configured_pwd = str(st.secrets["auth"]["password"])
    except Exception:
        pass

    if not configured_pwd:
        configured_pwd = os.environ.get("APP_PASSWORD", "")

    # No password protection configured -> access granted
    if not configured_pwd:
        return True

    if st.session_state.get("authenticated", False):
        return True

    st.markdown("### 🔒 興櫃市場籌碼與獲利設算系統")
    st.info("本系統已啟動安全保護，請輸入存取密碼以繼續。")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        pwd_input = st.text_input("請輸入系統密碼", type="password", key="login_password_key")
        if st.button("確認登入", use_container_width=True, type="primary"):
            if pwd_input == configured_pwd:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("密碼不正確，請重新輸入！")
    return False

def clean_num(val, max_decimals=2, prefix="", suffix="", use_comma=True):
    """
    Formats numbers cleanly:
    - Removes trailing zeros after the decimal point (e.g., 380.00 -> 380, 12.50 -> 12.5)
    - Adds thousand separators if use_comma=True
    - Handles negative numbers and prefix/suffix cleanly
    - Returns '-' for NaN, None, or empty values
    """
    if val is None or pd.isna(val) or val == "" or val == "-":
        return "-"
    try:
        f = float(val)
    except (ValueError, TypeError):
        return str(val)
    if abs(f) < 1e-9:
        return f"{prefix}0{suffix}"
    sign = "-" if f < 0 else ""
    abs_f = abs(f)
    fmt = f"{abs_f:,.{max_decimals}f}" if use_comma else f"{abs_f:.{max_decimals}f}"
    if "." in fmt:
        fmt = fmt.rstrip("0").rstrip(".")
    return f"{sign}{prefix}{fmt}{suffix}"

def set_1_based_index(df: pd.DataFrame, index_name: str = "排行") -> pd.DataFrame:
    """Sets a 1-based index starting from 1 instead of 0."""
    if df is not None and not df.empty:
        df.index = range(1, len(df) + 1)
        df.index.name = index_name
    return df

st.set_page_config(
    page_title="興櫃 Market Making Analytics",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="auto",
)

# Custom CSS for enhanced mobile & desktop viewing
st.markdown("""
<style>
    @media (max-width: 768px) {
        .block-container {
            padding-top: 1.5rem;
            padding-left: 0.8rem;
            padding-right: 0.8rem;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.35rem !important;
        }
    }
    div[data-testid="metric-container"] {
        background-color: rgba(240, 242, 246, 0.5);
        border: 1px solid rgba(0, 0, 0, 0.08);
        padding: 0.8rem;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

if not check_password():
    st.stop()

st.title("📈 興櫃市場籌碼與推薦券商價差獲利設算系統")
st.caption("Emerging Stock Board (ESB) Market Making & Chip Analytics Web App — 支援單日與區間雙軌試算")

# ----------------- Sidebar -----------------
st.sidebar.header("🔍 查詢與設定")

# 1. Date Range Selection
default_start = date(2026, 8, 28)
default_end = date(2026, 9, 9)

date_range_input = st.sidebar.date_input(
    "選擇查詢日期區間 (起 ~ 訖)",
    value=(default_start, default_end),
    max_value=date(2030, 12, 31)
)

if isinstance(date_range_input, (tuple, list)):
    if len(date_range_input) == 2:
        start_date_val, end_date_val = date_range_input
    elif len(date_range_input) == 1:
        start_date_val = end_date_val = date_range_input[0]
    else:
        start_date_val, end_date_val = default_start, default_end
else:
    start_date_val = end_date_val = date_range_input

if start_date_val > end_date_val:
    start_date_val, end_date_val = end_date_val, start_date_val

start_str = start_date_val.strftime("%Y-%m-%d")
end_str = end_date_val.strftime("%Y-%m-%d")
_, start_file_date = normalize_date(start_str)
_, end_file_date = normalize_date(end_str)

is_single_day = (start_file_date == end_file_date)

# 2. Calculation Mode Selection
calc_mode = st.sidebar.radio(
    "損益計算模式",
    [
        "📊 雙演算法並列比較 (推薦)",
        "1️⃣ 方式一：逐日累加法 (Daily Cumulative)",
        "2️⃣ 方式二：區間總額公式法 (Pooled Range Formula)",
    ],
    index=0
)

# 3. Units
unit_option = st.sidebar.radio("股數顯示單位", ["張 (1,000股)", "股"], index=0)
unit_scale = 1000 if "張" in unit_option else 1
unit_label = "張" if "張" in unit_option else "股"

st.sidebar.markdown("---")
force_download = st.sidebar.checkbox("強制重新下載 (覆寫快取)", value=False)
if st.sidebar.button("🔄 檢查並下載區間資料", use_container_width=True):
    with st.spinner(f"正在檢查/下載 {start_str} 至 {end_str} 市場資料..."):
        try:
            results = process_date_range(start_str, end_str, force_download=force_download)
            processed_days = [r for r in results if r["status"] == "ok"]
            cached_days = [r for r in results if r["status"] == "already_cached"]
            error_days = [r for r in results if r["status"] == "error"]
            if error_days:
                st.sidebar.warning(f"處理完成，但有 {len(error_days)} 日取得失敗。")
            else:
                st.sidebar.success(f"完成！新增下載 {len(processed_days)} 日，已快取 {len(cached_days)} 日。")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"資料取得失敗：{e}")

# Retrieve Market Range Analytics
stock_pnls = db.get_market_range_stock_pnls(start_file_date, end_file_date)
broker_pnls = db.get_market_range_broker_pnls(start_file_date, end_file_date)

# Determine distinct trading days count
available_dates = [d for d in db.get_available_dates() if start_file_date <= d <= end_file_date]
trading_days_count = len(available_dates)

if trading_days_count == 0:
    st.warning(f"⚠️ 資料庫中尚未有 {start_str} 至 {end_str} 的興櫃交易資料（或所選日期為非交易日）。")
    if st.button(f"📥 立即自櫃買中心連線下載 {start_str} ~ {end_str} 資料並設算", type="primary"):
        with st.spinner(f"正在連線櫃買中心下載並解析 {start_str} 至 {end_str} 交易資料..."):
            try:
                results = process_date_range(start_str, end_str, force_download=force_download)
                processed_days = [r for r in results if r["status"] == "ok"]
                if processed_days:
                    st.success(f"下載成功！已自動處理並計算 {len(processed_days)} 個交易日資料。")
                else:
                    st.info("所選日期在櫃買中心無交易資料（可能為週末或國定假日）。")
                st.rerun()
            except Exception as e:
                st.error(f"下載失敗：{e}")

# ----------------- Navigation Tabs -----------------
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 全市場自營商損益試算",
    "🏢 單股經紀據點籌碼排行",
    "🧮 單股造市價差損益與分配明細",
    "💼 指定券商據點個股進出明細"
])

# ----------------- Tab 1: 全市場自營商損益試算 -----------------
with tab1:
    range_title = f"{start_str} (單日)" if is_single_day else f"{start_str} 至 {end_str} (共涵蓋 {trading_days_count} 個交易日)"
    st.subheader(f"📅 全市場自營商損益試算 ({range_title})")

    total_m1_stock_pnl = sum(s["method1_pnl"] for s in stock_pnls)
    total_m2_stock_pnl = sum(s["method2_pnl"] for s in stock_pnls)
    total_m1_broker_pnl = sum(b["method1_pnl"] for b in broker_pnls)
    total_m2_broker_pnl = sum(b["method2_pnl"] for b in broker_pnls)
    diff_stock_pnl = total_m2_stock_pnl - total_m1_stock_pnl

    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    m_col1.metric("方式一 全自營商加總 (逐日累加)", clean_num(round(total_m1_broker_pnl), 0, prefix="$"))
    m_col2.metric("方式二 全自營商加總 (區間公式)", clean_num(round(total_m2_broker_pnl), 0, prefix="$"))
    m_col3.metric("兩演算法差額 (M2 - M1)", clean_num(round(diff_stock_pnl), 0, prefix="$"), delta=clean_num(round(diff_stock_pnl), 0) if not is_single_day else None)
    m_col4.metric("興櫃標的 / 造市商數", f"{len(stock_pnls)} 檔 / {len(broker_pnls)} 家")

    st.markdown("---")
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("### 📋 商品 - 全自營商損益排行")
        if stock_pnls:
            stock_df = pd.DataFrame(stock_pnls)
            stock_df["商品"] = stock_df["stock_id"] + " " + stock_df["stock_name"]
            stock_df["方式一配對量(" + unit_label + ")"] = stock_df["method1_matched_qty"] / unit_scale
            stock_df["方式二配對量(" + unit_label + ")"] = stock_df["method2_matched_qty"] / unit_scale
            stock_df["方式一損益"] = stock_df["method1_pnl"]
            stock_df["方式二損益"] = stock_df["method2_pnl"]
            stock_df["損益差額"] = stock_df["pnl_diff"]
            stock_df["交易天數"] = stock_df["trading_days"]
            stock_df = set_1_based_index(stock_df, "排行")

            if "雙演算法" in calc_mode:
                display_cols = ["商品", "方式一損益", "方式二損益", "損益差額", "方式一配對量(" + unit_label + ")", "方式二配對量(" + unit_label + ")", "交易天數"]
                fmt_dict = {
                    "方式一損益": lambda x: clean_num(round(x), 0),
                    "方式二損益": lambda x: clean_num(round(x), 0),
                    "損益差額": lambda x: clean_num(round(x), 0),
                    "方式一配對量(" + unit_label + ")": lambda x: clean_num(x, 2),
                    "方式二配對量(" + unit_label + ")": lambda x: clean_num(x, 2),
                    "交易天數": lambda x: clean_num(x, 0)
                }
            elif "方式一" in calc_mode:
                display_cols = ["商品", "方式一損益", "方式一配對量(" + unit_label + ")", "交易天數"]
                fmt_dict = {
                    "方式一損益": lambda x: clean_num(round(x), 0),
                    "方式一配對量(" + unit_label + ")": lambda x: clean_num(x, 2),
                    "交易天數": lambda x: clean_num(x, 0)
                }
            else:
                display_cols = ["商品", "方式二損益", "方式二配對量(" + unit_label + ")", "交易天數"]
                fmt_dict = {
                    "方式二損益": lambda x: clean_num(round(x), 0),
                    "方式二配對量(" + unit_label + ")": lambda x: clean_num(x, 2),
                    "交易天數": lambda x: clean_num(x, 0)
                }

            st.dataframe(
                stock_df[display_cols].style.format(fmt_dict),
                height=650,
                use_container_width=True
            )
            st.caption(f"**商品加總損益**：方式一 {clean_num(round(total_m1_stock_pnl), 0, prefix='$')} 元 | 方式二 {clean_num(round(total_m2_stock_pnl), 0, prefix='$')} 元")
        else:
            st.info("所選日期區間尚無個股損益資料")

    with col_right:
        st.markdown("### 🏦 自營商 - 全商品損益排行")
        if broker_pnls:
            broker_df = pd.DataFrame(broker_pnls)
            broker_df["自營商"] = broker_df["broker_code"] + " " + broker_df["broker_name"]
            broker_df["方式一損益"] = broker_df["method1_pnl"]
            broker_df["方式二損益"] = broker_df["method2_pnl"]
            broker_df["損益差額"] = broker_df["pnl_diff"]
            broker_df["總造市量(" + unit_label + ")"] = broker_df["total_volume"] / unit_scale
            broker_df = set_1_based_index(broker_df, "排行")

            if "雙演算法" in calc_mode:
                b_display_cols = ["自營商", "方式一損益", "方式二損益", "損益差額", "總造市量(" + unit_label + ")"]
                b_fmt_dict = {
                    "方式一損益": lambda x: clean_num(round(x), 0),
                    "方式二損益": lambda x: clean_num(round(x), 0),
                    "損益差額": lambda x: clean_num(round(x), 0),
                    "總造市量(" + unit_label + ")": lambda x: clean_num(x, 2),
                }
            elif "方式一" in calc_mode:
                b_display_cols = ["自營商", "方式一損益", "總造市量(" + unit_label + ")"]
                b_fmt_dict = {
                    "方式一損益": lambda x: clean_num(round(x), 0),
                    "總造市量(" + unit_label + ")": lambda x: clean_num(x, 2),
                }
            else:
                b_display_cols = ["自營商", "方式二損益", "總造市量(" + unit_label + ")"]
                b_fmt_dict = {
                    "方式二損益": lambda x: clean_num(round(x), 0),
                    "總造市量(" + unit_label + ")": lambda x: clean_num(x, 2),
                }

            st.dataframe(
                broker_df[b_display_cols].style.format(b_fmt_dict),
                height=650,
                use_container_width=True
            )
            st.caption(f"**全自營商加總**：方式一 {clean_num(round(total_m1_broker_pnl), 0, prefix='$')} 元 | 方式二 {clean_num(round(total_m2_broker_pnl), 0, prefix='$')} 元")
        else:
            st.info("所選日期區間尚無自營商損益資料")

# ----------------- Tab 2: 單股經紀據點籌碼排行 -----------------
with tab2:
    st.subheader(f"🏢 單一興櫃股票經紀據點籌碼統計 ({range_title})")
    stock_options = [f"{s['stock_id']} {s['stock_name']}" for s in stock_pnls] if stock_pnls else ["1260 富味鄉", "7932 昱鐳應材"]

    selected_stock = st.selectbox("選擇興櫃股票", stock_options, index=0)
    selected_sid = selected_stock.split()[0] if selected_stock else "1260"

    stock_chips = db.get_stock_range_chips(start_file_date, end_file_date, selected_sid)
    if stock_chips:
        net_rankings = get_net_buy_sell_rankings(stock_chips)
        col_buy, col_sell = st.columns(2)

        with col_buy:
            st.markdown(f"#### 🟢 區間買超據點排行 ({selected_stock})")
            buy_list = net_rankings["net_buyers"]
            if buy_list:
                b_df = pd.DataFrame(buy_list)
                b_df["券商據點"] = b_df["broker_code"] + " " + b_df["broker_name"]
                b_df["買進(" + unit_label + ")"] = b_df["buy_qty"] / unit_scale
                b_df["買均價"] = b_df["buy_avg_price"]
                buy_r = b_df["buy_ratio"] if "buy_ratio" in b_df.columns else pd.Series(0.0, index=b_df.index)
                b_df["買比重"] = buy_r * 100
                b_df["賣出(" + unit_label + ")"] = b_df["sell_qty"] / unit_scale
                b_df["賣均價"] = b_df["sell_avg_price"]
                sell_r = b_df["sell_ratio"] if "sell_ratio" in b_df.columns else pd.Series(0.0, index=b_df.index)
                b_df["賣比重"] = sell_r * 100
                b_df["買超(" + unit_label + ")"] = b_df["net_qty"] / unit_scale
                b_df = set_1_based_index(b_df, "排行")

                st.dataframe(
                    b_df[["券商據點", "買進(" + unit_label + ")", "買均價", "買比重", "賣出(" + unit_label + ")", "賣均價", "賣比重", "買超(" + unit_label + ")"]].style.format({
                        "買進(" + unit_label + ")": lambda x: clean_num(x, 2),
                        "買均價": lambda x: clean_num(x, 2),
                        "買比重": lambda x: clean_num(x, 2, suffix="%"),
                        "賣出(" + unit_label + ")": lambda x: clean_num(x, 2),
                        "賣均價": lambda x: clean_num(x, 2),
                        "賣比重": lambda x: clean_num(x, 2, suffix="%"),
                        "買超(" + unit_label + ")": lambda x: clean_num(x, 2),
                    }),
                    height=550,
                    use_container_width=True
                )
            else:
                st.info("此區間無買超據點")

        with col_sell:
            st.markdown(f"#### 🔴 區間賣超據點排行 ({selected_stock})")
            sell_list = net_rankings["net_sellers"]
            if sell_list:
                s_df = pd.DataFrame(sell_list)
                s_df["券商據點"] = s_df["broker_code"] + " " + s_df["broker_name"]
                s_df["買進(" + unit_label + ")"] = s_df["buy_qty"] / unit_scale
                s_df["買均價"] = s_df["buy_avg_price"]
                s_buy_r = s_df["buy_ratio"] if "buy_ratio" in s_df.columns else pd.Series(0.0, index=s_df.index)
                s_df["買比重"] = s_buy_r * 100
                s_df["賣出(" + unit_label + ")"] = s_df["sell_qty"] / unit_scale
                s_df["賣均價"] = s_df["sell_avg_price"]
                s_sell_r = s_df["sell_ratio"] if "sell_ratio" in s_df.columns else pd.Series(0.0, index=s_df.index)
                s_df["賣比重"] = s_sell_r * 100
                s_df["賣超(" + unit_label + ")"] = (-s_df["net_qty"]) / unit_scale
                s_df = set_1_based_index(s_df, "排行")

                st.dataframe(
                    s_df[["券商據點", "買進(" + unit_label + ")", "買均價", "買比重", "賣出(" + unit_label + ")", "賣均價", "賣比重", "賣超(" + unit_label + ")"]].style.format({
                        "買進(" + unit_label + ")": lambda x: clean_num(x, 2),
                        "買均價": lambda x: clean_num(x, 2),
                        "買比重": lambda x: clean_num(x, 2, suffix="%"),
                        "賣出(" + unit_label + ")": lambda x: clean_num(x, 2),
                        "賣均價": lambda x: clean_num(x, 2),
                        "賣比重": lambda x: clean_num(x, 2, suffix="%"),
                        "賣超(" + unit_label + ")": lambda x: clean_num(x, 2),
                    }),
                    height=550,
                    use_container_width=True
                )
            else:
                st.info("此區間無賣超據點")
    else:
        st.info("該股票在所選區間無經紀交易資料")

# ----------------- Tab 3: 單股造市價差損益與分配明細 -----------------
with tab3:
    st.subheader(f"🧮 {selected_stock} 造市價差損益設算與分配 ({range_title})")

    stock_detail = db.get_stock_range_detail(start_file_date, end_file_date, selected_sid)
    daily_rows = stock_detail.get("daily_rows", [])
    m1_data = stock_detail.get("method1", {})
    m2_data = stock_detail.get("method2", {})
    dealer_list = stock_detail.get("dealers", [])

    if daily_rows:
        # Comparison Metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("方式一 累加損益 (元)", clean_num(round(m1_data['total_estimated_mm_pnl']), 0, prefix="$"))
        c2.metric("方式二 公式損益 (元)", clean_num(round(m2_data['total_estimated_mm_pnl']), 0, prefix="$"))
        c3.metric("損益差額 (M2 - M1)", clean_num(round(stock_detail['pnl_diff']), 0, prefix="$"))
        c4.metric(f"配對量 (M1 / M2 {unit_label})", f"{clean_num(m1_data['matched_qty']/unit_scale, 2)} / {clean_num(m2_data['matched_qty']/unit_scale, 2)}")

        # Summary Table for both methods
        st.markdown("#### ⚖️ 兩種計算演算法數值對照表")
        method_comparison_df = pd.DataFrame([
            {
                "計算演算法": "方式一：逐日累加法 (Daily Cumulative)",
                "買進總量(" + unit_label + ")": clean_num(sum(r['buy_qty'] for r in daily_rows)/unit_scale, 2),
                "賣出總量(" + unit_label + ")": clean_num(sum(r['sell_qty'] for r in daily_rows)/unit_scale, 2),
                "配對成交量(" + unit_label + ")": clean_num(m1_data['matched_qty']/unit_scale, 2),
                "價差毛利(元)": clean_num(round(m1_data['gross_spread_pnl']), 0),
                "交易稅費成本(0.32%)": clean_num(round(m1_data['transaction_cost']), 0),
                "估算造市總損益(元)": clean_num(round(m1_data['total_estimated_mm_pnl']), 0),
            },
            {
                "計算演算法": "方式二：區間總額公式法 (Pooled Formula)",
                "買進總量(" + unit_label + ")": clean_num(m2_data['total_buy_qty']/unit_scale, 2),
                "賣出總量(" + unit_label + ")": clean_num(m2_data['total_sell_qty']/unit_scale, 2),
                "配對成交量(" + unit_label + ")": clean_num(m2_data['matched_qty']/unit_scale, 2),
                "價差毛利(元)": clean_num(round(m2_data['gross_spread_pnl']), 0),
                "交易稅費成本(0.32%)": clean_num(round(m2_data['transaction_cost']), 0),
                "估算造市總損益(元)": clean_num(round(m2_data['total_estimated_mm_pnl']), 0),
            }
        ])
        method_comparison_df = set_1_based_index(method_comparison_df, "序號")
        st.table(method_comparison_df)

        with st.expander("🔍 點擊查看方式二（區間總額公式法）參數與核心公式細節", expanded=False):
            st.markdown(f"""
            - **區間客戶買進加權均價 (Buy VWAP)**：`{clean_num(m2_data['total_buy_amount'], 2)} / {clean_num(m2_data['total_buy_qty'], 0)}` = **${clean_num(m2_data['buy_vwap'], 4)}**
            - **區間客戶賣出加權均價 (Sell VWAP)**：`{clean_num(m2_data['total_sell_amount'], 2)} / {clean_num(m2_data['total_sell_qty'], 0)}` = **${clean_num(m2_data['sell_vwap'], 4)}**
            - **區間可配對股數 (Matched Qty)**：`min({clean_num(m2_data['total_buy_qty'], 0)}, {clean_num(m2_data['total_sell_qty'], 0)})` = **{clean_num(m2_data['matched_qty'], 0)} 股**
            - **核心公式**：`(區間買進均價 * 0.9968 - 區間賣出均價) * 區間配對量`
            - **代入計算**：`({clean_num(m2_data['buy_vwap'], 4)} * 0.9968 - {clean_num(m2_data['sell_vwap'], 4)}) * {clean_num(m2_data['matched_qty'], 0)}` = **{clean_num(round(m2_data['total_estimated_mm_pnl']), 0, prefix='$')} 元**
            """)

        # Collapsible Daily Breakdown
        with st.expander(f"📅 逐日交易與損益歷程清單 (共 {len(daily_rows)} 交易日)", expanded=False):
            d_df = pd.DataFrame(daily_rows)
            d_df["交易日期"] = d_df["trade_date"]
            d_df["買進量(" + unit_label + ")"] = d_df["buy_qty"] / unit_scale
            d_df["買均價"] = d_df["buy_vwap"]
            d_df["賣出量(" + unit_label + ")"] = d_df["sell_qty"] / unit_scale
            d_df["賣均價"] = d_df["sell_vwap"]
            d_df["配對量(" + unit_label + ")"] = d_df["matched_qty"] / unit_scale
            d_df["價差毛利"] = d_df["gross_spread_pnl"]
            d_df["交易成本"] = d_df["transaction_cost"]
            d_df["當日估算損益"] = d_df["total_estimated_mm_pnl"]
            d_df = set_1_based_index(d_df, "序號")

            st.dataframe(
                d_df[["交易日期", "買進量(" + unit_label + ")", "買均價", "賣出量(" + unit_label + ")", "賣均價", "配對量(" + unit_label + ")", "價差毛利", "交易成本", "當日估算損益"]].style.format({
                    "買進量(" + unit_label + ")": lambda x: clean_num(x, 2),
                    "買均價": lambda x: clean_num(x, 2),
                    "賣出量(" + unit_label + ")": lambda x: clean_num(x, 2),
                    "賣均價": lambda x: clean_num(x, 2),
                    "配對量(" + unit_label + ")": lambda x: clean_num(x, 2),
                    "價差毛利": lambda x: clean_num(round(x), 0),
                    "交易成本": lambda x: clean_num(round(x), 0),
                    "當日估算損益": lambda x: clean_num(round(x), 0)
                }),
                use_container_width=True
            )

        # Dealer Allocations
        st.markdown("#### 🎯 推薦證券商 (***T) 成交量比重與區間損益分配表")
        if dealer_list:
            dealer_df = pd.DataFrame(dealer_list)
            dealer_df["自營商"] = dealer_df["broker_code"] + " " + dealer_df["broker_name"]
            dealer_df["買進量(" + unit_label + ")"] = dealer_df["buy_qty"] / unit_scale
            dealer_df["賣出量(" + unit_label + ")"] = dealer_df["sell_qty"] / unit_scale
            dealer_df["總造市量(" + unit_label + ")"] = dealer_df["total_volume"] / unit_scale
            dealer_df["成交量佔比"] = dealer_df["volume_share"] * 100
            dealer_df["方式一分配損益"] = dealer_df["method1_pnl"]
            dealer_df["方式二分配損益"] = dealer_df["method2_pnl"]
            dealer_df["損益差額"] = dealer_df["pnl_diff"]
            dealer_df = set_1_based_index(dealer_df, "排行")

            if "雙演算法" in calc_mode:
                deal_cols = ["自營商", "買進量(" + unit_label + ")", "賣出量(" + unit_label + ")", "總造市量(" + unit_label + ")", "成交量佔比", "方式一分配損益", "方式二分配損益", "損益差額"]
                deal_fmt = {
                    "買進量(" + unit_label + ")": lambda x: clean_num(x, 2),
                    "賣出量(" + unit_label + ")": lambda x: clean_num(x, 2),
                    "總造市量(" + unit_label + ")": lambda x: clean_num(x, 2),
                    "成交量佔比": lambda x: clean_num(x, 2, suffix="%"),
                    "方式一分配損益": lambda x: clean_num(round(x), 0),
                    "方式二分配損益": lambda x: clean_num(round(x), 0),
                    "損益差額": lambda x: clean_num(round(x), 0),
                }
            elif "方式一" in calc_mode:
                deal_cols = ["自營商", "買進量(" + unit_label + ")", "賣出量(" + unit_label + ")", "總造市量(" + unit_label + ")", "成交量佔比", "方式一分配損益"]
                deal_fmt = {
                    "買進量(" + unit_label + ")": lambda x: clean_num(x, 2),
                    "賣出量(" + unit_label + ")": lambda x: clean_num(x, 2),
                    "總造市量(" + unit_label + ")": lambda x: clean_num(x, 2),
                    "成交量佔比": lambda x: clean_num(x, 2, suffix="%"),
                    "方式一分配損益": lambda x: clean_num(round(x), 0)
                }
            else:
                deal_cols = ["自營商", "買進量(" + unit_label + ")", "賣出量(" + unit_label + ")", "總造市量(" + unit_label + ")", "成交量佔比", "方式二分配損益"]
                deal_fmt = {
                    "買進量(" + unit_label + ")": lambda x: clean_num(x, 2),
                    "賣出量(" + unit_label + ")": lambda x: clean_num(x, 2),
                    "總造市量(" + unit_label + ")": lambda x: clean_num(x, 2),
                    "成交量佔比": lambda x: clean_num(x, 2, suffix="%"),
                    "方式二分配損益": lambda x: clean_num(round(x), 0)
                }

            st.dataframe(
                dealer_df[deal_cols].style.format(deal_fmt),
                use_container_width=True
            )
        else:
            st.info("此區間無推薦證券商 (***T) 造市成交紀錄")
    else:
        st.info("該股票在所選區間無交易紀錄或未有配對成交")

# ----------------- Tab 4: 指定券商據點個股進出明細 -----------------
with tab4:
    st.subheader(f"💼 指定券商據點個股進出明細 ({range_title})")
    broker_input = st.text_input("輸入券商代號 (例如 980T、9A0T、9A95、8888、1260)", value="980T").strip()

    if broker_input:
        b_name = get_broker_name(broker_input)
        st.markdown(f"**券商代號**：`{broker_input}` | **券商機構名稱**：`{b_name}`")

        history_data = db.get_broker_range_history(start_file_date, end_file_date, broker_input)
        alloc_rows = history_data.get("allocations", [])
        chip_rows = history_data.get("chip_trades", [])

        # 1. MM Allocations if it's a T broker or has allocation records
        if broker_input.endswith('T') or alloc_rows:
            if alloc_rows:
                a_df = pd.DataFrame(alloc_rows)
                total_alloc_pnl = sum(a_df['allocated_pnl'])
                st.markdown(f"#### 🏆 自營商各股造市分配彙總 (區間累計分配損益: {clean_num(round(total_alloc_pnl), 0, prefix='$')} 元)")
                stock_summary = a_df.groupby(["stock_id", "stock_name"]).agg({
                    "buy_qty": "sum",
                    "sell_qty": "sum",
                    "total_volume": "sum",
                    "allocated_pnl": "sum",
                    "trade_date": "nunique"
                }).reset_index()

                stock_summary["股票"] = stock_summary["stock_id"] + " " + stock_summary["stock_name"].fillna("")
                stock_summary["買進量(" + unit_label + ")"] = stock_summary["buy_qty"] / unit_scale
                stock_summary["賣出量(" + unit_label + ")"] = stock_summary["sell_qty"] / unit_scale
                stock_summary["造市總量(" + unit_label + ")"] = stock_summary["total_volume"] / unit_scale
                stock_summary["累計分配損益(元)"] = stock_summary["allocated_pnl"]
                stock_summary["交易天數"] = stock_summary["trade_date"]
                stock_summary.sort_values(by="allocated_pnl", ascending=False, inplace=True)
                stock_summary = set_1_based_index(stock_summary, "排行")

                st.dataframe(
                    stock_summary[["股票", "買進量(" + unit_label + ")", "賣出量(" + unit_label + ")", "造市總量(" + unit_label + ")", "累計分配損益(元)", "交易天數"]].style.format({
                        "買進量(" + unit_label + ")": lambda x: clean_num(x, 2),
                        "賣出量(" + unit_label + ")": lambda x: clean_num(x, 2),
                        "造市總量(" + unit_label + ")": lambda x: clean_num(x, 2),
                        "累計分配損益(元)": lambda x: clean_num(round(x), 0),
                        "交易天數": lambda x: clean_num(x, 0)
                    }),
                    use_container_width=True
                )

                with st.expander(f"📋 點擊查看每日造市分配明細清單 (共 {len(alloc_rows)} 筆紀錄)", expanded=False):
                    d_alloc = a_df.copy()
                    d_alloc["交易日期"] = d_alloc["trade_date"]
                    d_alloc["股票"] = d_alloc["stock_id"] + " " + d_alloc["stock_name"].fillna("")
                    d_alloc["造市量(" + unit_label + ")"] = d_alloc["total_volume"] / unit_scale
                    d_alloc["佔比"] = d_alloc["volume_share"] * 100
                    d_alloc["當日分配損益"] = d_alloc["allocated_pnl"]
                    d_alloc = set_1_based_index(d_alloc, "序號")
                    st.dataframe(
                        d_alloc[["交易日期", "股票", "造市量(" + unit_label + ")", "佔比", "當日分配損益"]].style.format({
                            "造市量(" + unit_label + ")": lambda x: clean_num(x, 2),
                            "佔比": lambda x: clean_num(x, 2, suffix="%"),
                            "當日分配損益": lambda x: clean_num(round(x), 0)
                        }),
                        use_container_width=True
                    )
            else:
                st.info("所選區間內該自營商無造市交易分配紀錄")

        # 2. Broker Chip Trades
        if chip_rows:
            st.markdown("#### 📊 經紀買賣進出明細 (區間彙總)")
            c_df = pd.DataFrame(chip_rows)
            chip_summary = c_df.groupby(["stock_id", "stock_name"]).agg({
                "buy_qty": "sum",
                "sell_qty": "sum",
                "net_qty": "sum",
                "trade_date": "nunique"
            }).reset_index()

            chip_summary["股票"] = chip_summary["stock_id"] + " " + chip_summary["stock_name"].fillna("")
            chip_summary["買進(" + unit_label + ")"] = chip_summary["buy_qty"] / unit_scale
            chip_summary["賣出(" + unit_label + ")"] = chip_summary["sell_qty"] / unit_scale
            chip_summary["買賣超(" + unit_label + ")"] = chip_summary["net_qty"] / unit_scale
            chip_summary["進出天數"] = chip_summary["trade_date"]
            chip_summary.sort_values(by="buy_qty", ascending=False, inplace=True)
            chip_summary = set_1_based_index(chip_summary, "排行")

            st.dataframe(
                chip_summary[["股票", "買進(" + unit_label + ")", "賣出(" + unit_label + ")", "買賣超(" + unit_label + ")", "進出天數"]].style.format({
                    "買進(" + unit_label + ")": lambda x: clean_num(x, 2),
                    "賣出(" + unit_label + ")": lambda x: clean_num(x, 2),
                    "買賣超(" + unit_label + ")": lambda x: clean_num(x, 2),
                    "進出天數": lambda x: clean_num(x, 0),
                }),
                use_container_width=True
            )

            with st.expander(f"📋 點擊查看每日經紀進出紀錄 (共 {len(chip_rows)} 筆)", expanded=False):
                d_chip = c_df.copy()
                d_chip["交易日期"] = d_chip["trade_date"]
                d_chip["股票"] = d_chip["stock_id"] + " " + d_chip["stock_name"].fillna("")
                d_chip["買進(" + unit_label + ")"] = d_chip["buy_qty"] / unit_scale
                d_chip["買均價"] = d_chip["buy_avg_price"]
                d_chip["賣出(" + unit_label + ")"] = d_chip["sell_qty"] / unit_scale
                d_chip["賣均價"] = d_chip["sell_avg_price"]
                d_chip["買賣超(" + unit_label + ")"] = d_chip["net_qty"] / unit_scale
                d_chip = set_1_based_index(d_chip, "序號")
                st.dataframe(
                    d_chip[["交易日期", "股票", "買進(" + unit_label + ")", "買均價", "賣出(" + unit_label + ")", "賣均價", "買賣超(" + unit_label + ")"]].style.format({
                        "買進(" + unit_label + ")": lambda x: clean_num(x, 2),
                        "買均價": lambda x: clean_num(x, 2),
                        "賣出(" + unit_label + ")": lambda x: clean_num(x, 2),
                        "賣均價": lambda x: clean_num(x, 2),
                        "買賣超(" + unit_label + ")": lambda x: clean_num(x, 2),
                    }),
                    use_container_width=True
                )
        elif not broker_input.endswith('T'):
            st.info("所選區間內該券商據點無經紀買賣紀錄")
