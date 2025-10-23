# ============================================================
# Streamlit ZLEMA Bollinger Multi-Coin Dashboard (4H Overlay)
# On-demand incremental fetching + Bollinger Bands + Telegram Alerts
# ============================================================

import logging
import time
from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# Defensive internal imports (if they fail we show UI errors but app won't crash)
try:
    from binance_integration import fetch_klines, get_secret
except Exception as e:
    logging.exception("Failed to import binance_integration: %s", e)

    def fetch_klines(*args, **kwargs):
        return pd.DataFrame()

    def get_secret(k):
        return None

try:
    from candle_evaluator import evaluate_candles
except Exception:
    def evaluate_candles(df, phase, trend):
        return df

try:
    from zlema_bbands_trading import (
        compute_indicators,
        compute_adaptive_pct,
        compute_4h_overlay,
        apply_zones,
        validate_trend,
    )
except Exception:
    def compute_indicators(df): return df
    def compute_adaptive_pct(df): return df
    def compute_4h_overlay(df): return df
    def apply_zones(df, phase, trend): return df
    def validate_trend(df): return df

# --------------------------
# CONFIGURATION
# --------------------------
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT", "DOGEUSDT", "LTCUSDT",
    "ADAUSDT", "AVAXUSDT", "DOTUSDT", "TRXUSDT", "LINKUSDT", "MATICUSDT",
    "INJUSDT", "SUIUSDT", "PEPEUSDT", "SHIBUSDT", "WLDUSDT"
]
INTERVAL = "1h"
DAYS = 30

st.set_page_config(page_title="ZLEMA Bollinger Multi-Coin Dashboard", layout="wide")
st.title("ZLEMA Bollinger Multi-Coin Dashboard")
st.caption("On-demand incremental fetching with Bollinger Bands, 4H Overlay, and Telegram Alerts.")

# --------------------------
# SIDEBAR SETTINGS
# --------------------------
with st.sidebar:
    st.header("Control Panel")
    selected_coin = st.selectbox("Select Coin to Configure", SYMBOLS, index=0)

    st.subheader(f"Settings — {selected_coin}")
    phase = st.selectbox("Phase", ["Uptrend", "Downtrend", "Sideways"], index=2)
    trend = st.selectbox("Trend", ["Uptrend", "Downtrend", "Sideways"], index=2)
    monitor_active = st.checkbox("Monitor this coin (activate for scanning)")

    st.divider()
    if st.button("Analyze Active Coins Now"):
        st.session_state["analyze_now"] = True
    if st.button("Test Telegram Alert"):
        st.session_state["test_alert"] = True

# --------------------------
# SAFE FETCH WRAPPER
# --------------------------
def safe_fetch(symbol: str, interval: str = INTERVAL, days: int = DAYS):
    """
    Wraps fetch_klines with simple retries and returns a DataFrame (possibly empty).
    """
    attempts = 3
    for i in range(attempts):
        try:
            df = fetch_klines(symbol=symbol, interval=interval, days=days)
            if df is None:
                df = pd.DataFrame()
            # Quick validation
            if isinstance(df, pd.DataFrame) and not df.empty and {"open", "high", "low", "close"}.issubset(df.columns):
                return df.copy()
            # If df empty, try again after a small pause (endpoint fallback may be settling)
            time.sleep(1.0 + i * 0.5)
        except Exception as e:
            logging.exception("safe_fetch attempt failed: %s", e)
            time.sleep(1.0 + i * 0.5)
    # final try: return whatever we got (likely empty)
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()

# --------------------------
# MAIN UI & Fetch
# --------------------------
st.subheader(f"Detailed Chart — {selected_coin}")

if st.button(f"Refresh selected coin data ({selected_coin})"):
    # Clear Streamlit cache so fetch_klines will re-run (if using st.cache_data)
    try:
        st.cache_data.clear()
    except Exception:
        pass

with st.spinner(f"Fetching {selected_coin} data from Binance..."):
    df = safe_fetch(selected_coin, interval=INTERVAL, days=DAYS)

if df is None or df.empty:
    st.warning(f"No valid data found for {selected_coin}. Try refreshing again later.")
    st.stop()

# --------------------------
# COMPUTE INDICATORS (pass phase & trend where required)
# --------------------------
try:
    df = compute_indicators(df)
    df = compute_adaptive_pct(df)
    df = compute_4h_overlay(df)
    # apply_zones requires phase & trend in your codebase
    df = apply_zones(df, phase, trend)
    df = evaluate_candles(df, phase, trend)
    df = validate_trend(df)
except Exception as e:
    st.error(f"Indicator computation failed: {e}")
    st.stop()

# --------------------------
# VALIDATE DF BEFORE PLOTTING
# --------------------------
if df is None or df.empty or not {"open", "high", "low", "close"}.issubset(df.columns):
    # Helpful debug info for you
    st.error(f"Invalid or empty data returned for {selected_coin}. Columns: {list(df.columns)} Shape: {df.shape}")
    # Show last few lines if present
    if isinstance(df, pd.DataFrame) and not df.empty:
        st.write(df.tail())
    st.stop()

# --------------------------
# PLOTLY CHART
# --------------------------
fig = go.Figure()

fig.add_trace(
    go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name="Price",
    )
)

# Optional overlays
if "upper_band" in df.columns and "lower_band" in df.columns:
    fig.add_trace(go.Scatter(x=df.index, y=df["upper_band"], name="Upper Band", line=dict(width=1)))
    fig.add_trace(go.Scatter(x=df.index, y=df["lower_band"], name="Lower Band", line=dict(width=1)))

if "zlema" in df.columns:
    fig.add_trace(go.Scatter(x=df.index, y=df["zlema"], name="ZLEMA", line=dict(width=2)))

fig.update_layout(
    title=f"{selected_coin} — ZLEMA Bollinger Overlay",
    xaxis_title="Time",
    yaxis_title="Price (USDT)",
    xaxis_rangeslider_visible=False,
    template="plotly_dark",
    height=600,
)
st.plotly_chart(fig, use_container_width=True)

# --------------------------
# SUMMARY TABLE
# --------------------------
st.subheader("Summary Table (Active Coins)")
summary_data = [
    {"Coin": selected_coin, "Phase": phase, "Trend": trend, "Last Price": float(df['close'].iloc[-1])}
]
st.dataframe(pd.DataFrame(summary_data), use_container_width=True)

# --------------------------
# TELEGRAM ALERT TEST (optional)
# --------------------------
if st.session_state.get("test_alert", False):
    bot_token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_secret("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        st.warning("Telegram credentials not found in Streamlit secrets.")
    else:
        message = f"Test alert: Dashboard is running for {selected_coin}."
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                params={"chat_id": chat_id, "text": message},
                timeout=8,
            )
            r.raise_for_status()
            st.success("Test alert sent successfully.")
        except Exception as e:
            st.error(f"Failed to send Telegram alert: {e}")

# --------------------------
# ANALYZE ACTIVE COINS (light)
# --------------------------
if st.session_state.get("analyze_now", False):
    st.info("Running quick scan on a subset of symbols...")
    active_summary = []
    for sym in SYMBOLS[:8]:
        dfsym = safe_fetch(sym, interval=INTERVAL, days=7)
        if dfsym is None or dfsym.empty:
            active_summary.append({"Coin": sym, "Status": "No data"})
            continue
        last_price = float(dfsym["close"].iloc[-1]) if "close" in dfsym.columns else None
        active_summary.append({"Coin": sym, "Status": "OK", "Last Price": last_price})
    st.dataframe(pd.DataFrame(active_summary), use_container_width=True)
    st.session_state["analyze_now"] = False
