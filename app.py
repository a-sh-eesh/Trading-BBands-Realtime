# ============================================================
# Streamlit ZLEMA Bollinger Multi-Coin Dashboard (4H Overlay)
# ============================================================

import logging
import time
from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# -------------------------------------
# Internal imports (safe)
# -------------------------------------
try:
    from binance_integration import fetch_klines, get_secret
except Exception as e:
    st.error(f"Binance integration import failed: {e}")
    def fetch_klines(*args, **kwargs): return pd.DataFrame()
    def get_secret(k): return None

try:
    from candle_evaluator import evaluate_candles
except Exception:
    def evaluate_candles(df, phase, trend): return df

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
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "DOTUSDT", "TRXUSDT", "LINKUSDT", "MATICUSDT",
    "INJUSDT", "SUIUSDT", "PEPEUSDT", "SHIBUSDT", "WLDUSDT"
]
INTERVAL = "1h"
DAYS = 30

st.set_page_config(page_title="ZLEMA Bollinger Multi-Coin Dashboard", layout="wide")
st.title("ZLEMA Bollinger Multi-Coin Dashboard")
st.caption("Stable version with automatic endpoint fallback and data validation.")

# --------------------------
# SIDEBAR SETTINGS
# --------------------------
with st.sidebar:
    st.header("Control Panel")
    selected_coin = st.selectbox("Select Coin to Configure", SYMBOLS, index=0)
    phase = st.selectbox("Phase", ["Uptrend", "Downtrend", "Sideways"], index=2)
    trend = st.selectbox("Trend", ["Uptrend", "Downtrend", "Sideways"], index=2)
    if st.button("Test Telegram Alert"):
        st.session_state["test_alert"] = True
    st.divider()
    st.caption("Use Refresh button if data missing or outdated.")

# --------------------------
# FETCH & VALIDATE DATA
# --------------------------
def safe_fetch(symbol, interval, days):
    """Fetch klines safely, always return DataFrame."""
    try:
        df = fetch_klines(symbol=symbol, interval=interval, days=days)
        if not isinstance(df, pd.DataFrame):
            return pd.DataFrame()
        if df.empty:
            return pd.DataFrame()
        return df
    except Exception as e:
        st.error(f"Failed to fetch {symbol}: {e}")
        return pd.DataFrame()

if st.button(f"Refresh {selected_coin} data"):
    try:
        st.cache_data.clear()
    except Exception:
        pass

with st.spinner(f"Fetching {selected_coin} data..."):
    df = safe_fetch(selected_coin, INTERVAL, DAYS)

# Guarantee df is DataFrame even if failed
if not isinstance(df, pd.DataFrame):
    df = pd.DataFrame()

if df.empty or not {"open", "high", "low", "close"}.issubset(df.columns):
    st.error(f"No valid OHLC data for {selected_coin}. Check Binance API or try again.")
    st.stop()

# --------------------------
# COMPUTE INDICATORS
# --------------------------
try:
    df = compute_indicators(df)
    df = compute_adaptive_pct(df)
    df = compute_4h_overlay(df)
    df = apply_zones(df, phase, trend)
    df = evaluate_candles(df, phase, trend)
    df = validate_trend(df)
except Exception as e:
    st.error(f"Indicator computation failed: {e}")
    st.stop()

# --------------------------
# PLOTLY CHART
# --------------------------
try:
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name="Price",
    ))

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
except Exception as e:
    st.error(f"Chart rendering failed: {e}")
    st.stop()

# --------------------------
# SUMMARY TABLE
# --------------------------
try:
    st.subheader("Summary")
    last_price = float(df["close"].iloc[-1])
    st.dataframe(pd.DataFrame([{
        "Coin": selected_coin,
        "Phase": phase,
        "Trend": trend,
        "Last Price": last_price,
    }]), use_container_width=True)
except Exception as e:
    st.error(f"Summary section failed: {e}")

# --------------------------
# TELEGRAM ALERT TEST
# --------------------------
if st.session_state.get("test_alert", False):
    bot_token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_secret("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        st.warning("Telegram credentials missing.")
    else:
        try:
            message = f"Test alert: {selected_coin} data loaded successfully."
            r = requests.get(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                params={"chat_id": chat_id, "text": message},
                timeout=8,
            )
            r.raise_for_status()
            st.success("Telegram alert sent successfully.")
        except Exception as e:
            st.error(f"Telegram error: {e}")
