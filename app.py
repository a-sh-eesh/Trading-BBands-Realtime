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
from binance_integration import fetch_klines, get_secret
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
# TELEGRAM ALERTS (Updated)
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
        # Try loading cached data from session
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
    df_new = fetch_klines(symbol, interval="1h", start_time=start_time, end_time=now)

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


# --------------------------
# SIDEBAR CONFIGURATION
# --------------------------
st.sidebar.header("Control Panel")

selected_symbol = st.sidebar.selectbox("Select Coin to Configure", SYMBOLS, index=0)
phase_key = f"{selected_symbol}_phase"
trend_key = f"{selected_symbol}_trend"
active_key = f"{selected_symbol}_active"

st.sidebar.subheader(f"Settings — {selected_symbol}")
st.sidebar.selectbox("Phase", ["TTR", "BTR", "Sideways"],
                     index=["TTR", "BTR", "Sideways"].index(st.session_state[phase_key]), key=phase_key)
st.sidebar.selectbox("Trend", ["Bullish", "Bearish", "Sideways"],
                     index=["Bullish", "Bearish", "Sideways"].index(st.session_state[trend_key]), key=trend_key)

monitor_toggle = st.sidebar.checkbox("Monitor this coin (activate for scanning)", value=st.session_state[active_key])
st.session_state[active_key] = monitor_toggle
if monitor_toggle:
    st.session_state["active_coins"].add(selected_symbol)
else:
    st.session_state["active_coins"].discard(selected_symbol)

st.sidebar.markdown("---")
if st.sidebar.button("Analyze Active Coins Now"):
    st.session_state["trigger_analysis"] = True

if st.sidebar.button("Test Telegram Alert"):
    success = send_telegram_alert("Test alert from your Streamlit ZLEMA system.")
    if success:
        st.sidebar.success("Test alert sent successfully.")
    else:
        st.sidebar.error("Failed to send Telegram alert. Check Streamlit Secrets configuration.")

st.sidebar.caption("Activate only coins you want monitored.")
st.sidebar.caption("Telegram credentials must be added in Streamlit Secrets.")


# --------------------------
# ANALYSIS FUNCTION
# --------------------------
def analyze_active_coins():
    active = sorted(list(st.session_state["active_coins"]))
    if not active:
        st.info("No active coins. Toggle 'Monitor this coin' for coins you want scanned.")
        return pd.DataFrame([])

    results = []
    total = len(active)
    progress = st.progress(0)
    i = 0

    for batch_start in range(0, total, BATCH_SIZE):
        batch = active[batch_start: batch_start + BATCH_SIZE]

        for symbol in batch:
            i += 1
            progress.progress(int(i / total * 100))
            df, updated = get_symbol_data(symbol)
            if df is None or df.empty:
                print(f"[{symbol}] Skipped: No data available.")
                continue

            df["open_time"] = pd.to_datetime(df["open_time"])
            phase = st.session_state.get(f"{symbol}_phase", "Sideways")
            trend = validate_trend(st.session_state.get(f"{symbol}_trend", "Sideways"))

            try:
                df = compute_indicators(df)
                df = compute_adaptive_pct(df)
                df = compute_4h_overlay(df)
                df = apply_zones(df, phase, trend)
                df = evaluate_candles(df, phase, trend)
            except Exception as e:
                results.append({
                    "symbol": symbol,
                    "signal": "ERROR",
                    "phase": phase,
                    "trend": trend,
                    "price": None,
                    "last_update": None,
                    "error": str(e),
                })
                continue

            latest = df.iloc[-1]
            signal = latest.get("entry_signal", "NONE")
            price = latest.get("close", 0.0)
            last_time = latest.get("open_time")

            last_signal = st.session_state["last_signal"].get(symbol)
            if signal in ("BUY", "SELL") and signal != last_signal:
                msg = (
                    f"{signal} Signal on {symbol}\n"
                    f"Phase: {phase} | Trend: {trend}\n"
                    f"Price: {price:.2f} USDT\n"
                    f"Time (UTC): {last_time}"
                )
                send_telegram_alert(msg)
                st.session_state["last_signal"][symbol] = signal

            results.append({
                "symbol": symbol,
                "signal": signal,
                "phase": phase,
                "trend": trend,
                "price": round(float(price), 2) if price is not None else None,
                "last_update": str(last_time),
            })

        time.sleep(SLEEP_BETWEEN_BATCHES)

    progress.progress(100)
    return pd.DataFrame(results)


# --------------------------
# RUN ANALYSIS
# --------------------------
if st.session_state.get("trigger_analysis", False) or "summary" not in st.session_state:
    st.session_state["summary"] = analyze_active_coins()
    st.session_state["trigger_analysis"] = False

summary_df = st.session_state.get("summary", pd.DataFrame([]))


# --------------------------
# DISPLAY SUMMARY
# --------------------------
st.subheader("Summary Table (Active Coins)")
if summary_df is not None and not summary_df.empty:
    st.dataframe(summary_df.sort_values("symbol"), use_container_width=True)
else:
    st.info("No active coin results to display.")


# --------------------------
# DETAILED VIEW (Selected Coin)
# --------------------------
st.markdown("---")
st.subheader(f"Detailed Chart — {selected_symbol}")

if st.button(f"Refresh selected coin data ({selected_symbol})"):
    st.session_state["symbol_data"].pop(selected_symbol, None)
    df, _ = get_symbol_data(selected_symbol)
else:
    df = st.session_state["symbol_data"].get(selected_symbol, pd.DataFrame())

# ✅ Guard before plotting
if df is None or df.empty or "open_time" not in df.columns:
    st.warning(f"No valid data found for {selected_symbol}. Try refreshing or wait for the next candle.")
    st.stop()

phase = st.session_state.get(f"{selected_symbol}_phase", "Sideways")
trend = validate_trend(st.session_state.get(f"{selected_symbol}_trend", "Sideways"))

df = compute_indicators(df)
df = compute_adaptive_pct(df)
df = compute_4h_overlay(df)
df = apply_zones(df, phase, trend)
df = evaluate_candles(df, phase, trend)

latest = df.iloc[-1]
st.write(f"Last Signal: {latest.get('entry_signal', 'NONE')} | Updated: {latest['open_time']}")
st.caption(f"Last Candle Time (UTC): {df['open_time'].iloc[-1]}")

# --- CHART ---
fig = go.Figure()

# 4H Overlay Bands
if all(col in df.columns for col in ["upper_band_4h", "lower_band_4h", "zlema_4h"]):
    df_4h = df.dropna(subset=["upper_band_4h", "lower_band_4h"])
    if not df_4h.empty:
        fig.add_trace(go.Scatter(
            x=df_4h["open_time"],
            y=df_4h["upper_band_4h"],
            mode="lines",
            line=dict(width=1, color="violet"),
            name="4H Upper Band"
        ))
        fig.add_trace(go.Scatter(
            x=df_4h["open_time"],
            y=df_4h["lower_band_4h"],
            mode="lines",
            line=dict(width=1, color="violet"),
            name="4H Lower Band",
            fill="tonexty",
            fillcolor="rgba(138,43,226,0.08)"
        ))
        fig.add_trace(go.Scatter(
            x=df_4h["open_time"],
            y=df_4h["zlema_4h"],
            mode="lines",
            line=dict(color="violet", width=1.2, dash="dot"),
            name="ZLEMA 4H"
        ))

# 1H Bollinger Bands (lines only)
if "upper_band" in df.columns and "lower_band" in df.columns:
    df_boll = df.dropna(subset=["upper_band", "lower_band"]).copy()
    if not df_boll.empty:
        fig.add_trace(go.Scatter(
            x=df_boll["open_time"],
            y=df_boll["upper_band"],
            mode="lines",
            line=dict(width=1, color="cornflowerblue"),
            name="1H Upper Band"
        ))
        fig.add_trace(go.Scatter(
            x=df_boll["open_time"],
            y=df_boll["lower_band"],
            mode="lines",
            line=dict(width=1, color="cornflowerblue"),
            name="1H Lower Band"
        ))

# ZLEMA
if "zlema" in df.columns:
    fig.add_trace(go.Scatter(
        x=df["open_time"], y=df["zlema"],
        mode="lines", name="ZLEMA (1H)",
        line=dict(color="orange", width=1.4)
    ))

# Candlesticks
fig.add_trace(go.Candlestick(
    x=df["open_time"],
    open=df["open"], high=df["high"], low=df["low"], close=df["close"],
    name="Candles"
))

# Zones
if phase != "TTR" and all(col in df.columns for col in ["buy_zone_lower", "buy_zone_upper"]):
    df_buy = df.dropna(subset=["buy_zone_lower", "buy_zone_upper"])
    if not df_buy.empty:
        fig.add_trace(go.Scatter(
            x=pd.concat([df_buy["open_time"], df_buy["open_time"][::-1]]),
            y=pd.concat([df_buy["buy_zone_lower"], df_buy["buy_zone_upper"][::-1]]),
            fill="toself", fillcolor="rgba(0,255,0,0.08)",
            line=dict(width=0), name="Buy Zone"
        ))

if phase != "TTR" and all(col in df.columns for col in ["sell_zone_lower", "sell_zone_upper"]):
    df_sell = df.dropna(subset=["sell_zone_lower", "sell_zone_upper"])
    if not df_sell.empty:
        fig.add_trace(go.Scatter(
            x=pd.concat([df_sell["open_time"], df_sell["open_time"][::-1]]),
            y=pd.concat([df_sell["sell_zone_lower"], df_sell["sell_zone_upper"][::-1]]),
            fill="toself", fillcolor="rgba(255,0,0,0.08)",
            line=dict(width=0), name="Sell Zone"
        ))

# Entry markers
if "entry_signal" in df.columns:
    buys = df[df["entry_signal"] == "BUY"]
    sells = df[df["entry_signal"] == "SELL"]

    if not buys.empty:
        fig.add_trace(go.Scatter(
            x=buys["open_time"], y=buys["low"] * 0.995,
            mode="markers", marker=dict(symbol="triangle-up", color="lime", size=9),
            name="BUY Signal"
        ))
    if not sells.empty:
        fig.add_trace(go.Scatter(
            x=sells["open_time"], y=sells["high"] * 1.005,
            mode="markers", marker=dict(symbol="triangle-down", color="red", size=9),
            name="SELL Signal"
        ))

fig.update_layout(
    template="plotly_dark",
    height=550,
    xaxis_rangeslider_visible=False,
    showlegend=True,
    legend=dict(
        orientation="h",
        yanchor="bottom", y=1.02,
        xanchor="right", x=1
    )
)

st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
st.caption("ZLEMA Bollinger System © 2025 — On-demand Fetch + Bollinger + 4H Overlay + Telegram Alerts")
