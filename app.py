# ============================================================
# Streamlit ZLEMA Bollinger Multi-Coin Dashboard (4H Overlay)
# On-demand incremental fetch + Telegram Alerts + Bollinger + 4H Bands
# ============================================================

import os
import time
import requests
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import timedelta

# Internal imports
from binance_integration import fetch_klines, fetch_klines_incremental, get_secret
from candle_evaluator import evaluate_candles
from zlema_bbands_trading import (
    compute_indicators,
    compute_adaptive_pct,
    compute_4h_overlay,
    apply_zones,
    validate_trend,
)

# --------------------------
# CONFIGURATION
# --------------------------
SYMBOLS = [
    "APTUSDT", "ARUSDT", "ARBUSDT", "ANKRUSDT", "ASTERUSDT", "BTCUSDT",
    "BCHUSDT", "BNBUSDT", "ETHUSDT", "ENSUSDT", "ENAUSDT", "INJUSDT",
    "JUPUSDT", "LTCUSDT", "LPTUSDT", "LDOUSDT", "LINEAUSDT", "PUMPUSDT",
    "PENDLEUSDT", "SAGAUSDT", "SEIUSDT", "STXUSDT", "TIAUSDT", "TONUSDT",
    "TAOUSDT", "WLDUSDT", "XRPUSDT", "ZETAUSDT", "AIUSDT", "JASMYUSDT",
    "GRTUSDT", "MINAUSDT", "FETUSDT", "ICPUSDT",
    "MELANIAUSDT", "TRUMPUSDT", "WIFUSDT", "BONKUSDT", "PEPEUSDT",
    "MYROUSDT", "FLOKIUSDT", "BOMEUSDT", "SHIBUSDT", "DOGEUSDT", "BRETTUSDT",
    "SNXUSDT", "ETHFIUSDT", "RUNEUSDT", "BAKEUSDT", "LDOUSDT", "CRVUSDT",
    "COMPUSDT", "ONDOUSDT", "DYDXUSDT", "UNIUSDT", "MKRUSDT", "HYPEUSDT",
    "PIXELUSDT", "GALAUSDT", "ILVUSDT", "IMXUSDT", "THETAUSDT",
    "APEUSDT", "VIRTUALUSDT", "WLFIUSDT",
    "VETUSDT", "PYTHUSDT", "JTOUSDT", "ROSEUSDT", "OPUSDT",
    "LINKUSDT", "COTIUSDT",
    "FILUSDT", "TRXUSDT", "DOTUSDT", "ADAUSDT", "SOLUSDT", "OMUSDT",
    "SUIUSDT", "NEARUSDT", "BEAMXUSDT", "ATOMUSDT", "CFXUSDT",
    "CHZUSDT", "ZILUSDT", "AVAXUSDT",
]

AUTO_REFRESH_SECONDS = 3600
BATCH_SIZE = 20
FETCH_DAYS = 30
SLEEP_BETWEEN_BATCHES = 3


# --------------------------
# TELEGRAM ALERTS
# --------------------------
def send_telegram_alert(message: str):
    """Sends a Telegram alert using Streamlit secrets or .env variables."""
    try:
        token = get_secret("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_TOKEN")
        chat_id = get_secret("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")

        if not token or not chat_id:
            print("Telegram credentials missing. Please add TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in Streamlit Secrets.")
            return False

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message}
        response = requests.post(url, json=payload, timeout=8)

        if response.status_code == 200:
            print(f"Telegram alert sent successfully to chat {chat_id}")
            return True
        else:
            print(f"Telegram alert failed with status {response.status_code}: {response.text}")
            return False

    except Exception as e:
        print(f"Telegram alert exception: {e}")
        return False


# --------------------------
# STREAMLIT SETUP
# --------------------------
st.set_page_config(page_title="ZLEMA Bollinger Multi-Coin Dashboard", layout="wide")
st.title("ZLEMA Bollinger Multi-Coin Dashboard")
st.caption("On-demand incremental fetching with Bollinger Bands, 4H Overlay, and Telegram Alerts.")


# --------------------------
# SESSION INITIALIZATION
# --------------------------
if "symbol_data" not in st.session_state:
    st.session_state["symbol_data"] = {}
if "last_signal" not in st.session_state:
    st.session_state["last_signal"] = {}
if "active_coins" not in st.session_state:
    st.session_state["active_coins"] = set()
if "trigger_analysis" not in st.session_state:
    st.session_state["trigger_analysis"] = False

for s in SYMBOLS:
    if f"{s}_phase" not in st.session_state:
        st.session_state[f"{s}_phase"] = "Sideways"
    if f"{s}_trend" not in st.session_state:
        st.session_state[f"{s}_trend"] = "Sideways"
    if f"{s}_active" not in st.session_state:
        st.session_state[f"{s}_active"] = False


# --------------------------
# AUTO REFRESH (Hourly)
# --------------------------
if "last_refresh" not in st.session_state:
    st.session_state["last_refresh"] = time.time()

if time.time() - st.session_state["last_refresh"] > AUTO_REFRESH_SECONDS:
    st.session_state["last_refresh"] = time.time()
    st.experimental_rerun()


# --------------------------
# DATA FETCH (Improved)
# --------------------------
def get_symbol_data(symbol: str):
    """Fetch 30 days initially, then 1 hour incrementally per coin."""
    cache = st.session_state["symbol_data"]
    now = pd.Timestamp.utcnow()

    # Initial 30-day fetch
    if symbol not in cache or cache[symbol] is None or cache[symbol].empty:
        if "data_cache" not in st.session_state:
            st.session_state["data_cache"] = {}

        df_old = st.session_state["data_cache"].get(symbol)

        if df_old is None or df_old.empty:
            df = fetch_klines(symbol, interval="1h", days=30)
        else:
            last_time = df_old["open_time"].max()
            new_df = fetch_klines_incremental(symbol, interval="1h", since=last_time)
            df = pd.concat([df_old, new_df]).drop_duplicates(subset=["open_time"]).reset_index(drop=True)

        # Store updated data
        st.session_state["data_cache"][symbol] = df

        if df is None or df.empty:
            print(f"[{symbol}] Initial fetch returned no data.")
            return pd.DataFrame(), False

        if "open_time" not in df.columns:
            df.columns = ["open_time", "open", "high", "low", "close", "volume"]

        df["open_time"] = pd.to_datetime(df["open_time"])
        cache[symbol] = df
        print(f"[{symbol}] Initial 30-day data loaded ({len(df)} rows).")
        return df, True

    # Incremental 1-hour fetch
    df_old = cache[symbol]
    try:
        last_time = pd.to_datetime(df_old["open_time"].max())
    except Exception:
        print(f"[{symbol}] Invalid cache, refetching 30 days.")
        df = fetch_klines(symbol, interval="1h", days=FETCH_DAYS)
        cache[symbol] = df
        return df, True

    start_time = last_time + timedelta(hours=1)
    df_new = fetch_klines(symbol, interval="1h", days=1)  # fallback to fetch recent candles

    if df_new is not None and not df_new.empty:
        if "open_time" not in df_new.columns:
            df_new.columns = ["open_time", "open", "high", "low", "close", "volume"]

        df_new["open_time"] = pd.to_datetime(df_new["open_time"])
        df = pd.concat([df_old, df_new]).drop_duplicates(subset=["open_time"]).sort_values("open_time")
        df = df[df["open_time"] >= (now - timedelta(days=FETCH_DAYS))]
        cache[symbol] = df
        print(f"[{symbol}] Added {len(df_new)} new rows. Total now: {len(df)} rows.")
        return df, True
    else:
        print(f"[{symbol}] No new candles yet. Using cached data.")
        return df_old, False
