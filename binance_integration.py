# ============================================================
# Binance Integration (Stable + Region Safe + Streamlit Compatible)
# ============================================================

import os
import time
import pandas as pd
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Optional Streamlit import
try:
    import streamlit as st
except ImportError:
    st = None

load_dotenv()

# ------------------------------------------------------------
# Secrets helper
# ------------------------------------------------------------
def get_secret(key):
    """Fetch secret value from Streamlit or .env."""
    if st and hasattr(st, "secrets"):
        try:
            if key in st.secrets:
                return st.secrets[key]
            if "general" in st.secrets and key in st.secrets["general"]:
                return st.secrets["general"][key]
        except Exception:
            pass
    return os.getenv(key)


# ------------------------------------------------------------
# Binance endpoints and fallback
# ------------------------------------------------------------
BINANCE_ENDPOINTS = [
    "https://api.binance.com/api/v3/klines",
    "https://api1.binance.com/api/v3/klines",
    "https://data-api.binance.vision/api/v3/klines",
]

# Public backup CSV (from Binance Vision)
CSV_FALLBACK_URL = (
    "https://data.binance.vision/data/spot/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-2025-09.csv"
)

# ------------------------------------------------------------
# Core safe request
# ------------------------------------------------------------
def _safe_request(url, params, retries=3):
    """Make safe HTTP GET and validate structure."""
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, timeout=10)
            if r.status_code in (451, 403):
                continue  # geo-block, skip
            r.raise_for_status()

            data = r.json()
            if not isinstance(data, list):
                continue
            if not all(isinstance(x, (list, tuple)) and len(x) >= 6 for x in data):
                continue
            return data  # valid structure
        except Exception:
            time.sleep(1.5 * attempt)
            continue
    return []


# ------------------------------------------------------------
# Convert raw kline data into DataFrame
# ------------------------------------------------------------
def _parse_klines(data):
    df = pd.DataFrame(
        data,
        columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "num_trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ],
    )
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")
    df = df.astype({
        "open": "float",
        "high": "float",
        "low": "float",
        "close": "float",
        "volume": "float",
    })
    df.set_index("close_time", inplace=True)
    df.sort_index(inplace=True)
    return df


# ------------------------------------------------------------
# Fallback data loader (CSV)
# ------------------------------------------------------------
def _fallback_csv(symbol, interval):
    """Load fallback CSV from Binance Vision (for blocked regions)."""
    try:
        url = CSV_FALLBACK_URL.format(symbol=symbol.upper(), interval=interval)
        df = pd.read_csv(url, header=None)
        df.columns = [
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "num_trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ]
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")
        df = df.astype({
            "open": "float",
            "high": "float",
            "low": "float",
            "close": "float",
            "volume": "float",
        })
        df.set_index("close_time", inplace=True)
        if st:
            st.warning(f"Using fallback CSV data for {symbol}. Live API blocked.")
        return df
    except Exception as e:
        if st:
            st.error(f"Fallback CSV fetch failed for {symbol}: {e}")
        return pd.DataFrame()


# ------------------------------------------------------------
# Fetch historical klines
# ------------------------------------------------------------
def _fetch_impl(symbol="BTCUSDT", interval="1h", days=30, incremental=False, last_timestamp=None):
    start_time = (
        last_timestamp
        if incremental and last_timestamp
        else int((datetime.utcnow() - timedelta(days=days)).timestamp() * 1000)
    )
    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "startTime": start_time,
        "limit": 1000,
    }

    # Try each endpoint
    for base_url in BINANCE_ENDPOINTS:
        data = _safe_request(base_url, params)
        if data:
            try:
                return _parse_klines(data)
            except Exception:
                continue

    # Fallback if all endpoints failed
    return _fallback_csv(symbol, interval)


# ------------------------------------------------------------
# Cached fetch wrapper (Streamlit-aware)
# ------------------------------------------------------------
if st:
    @st.cache_data(show_spinner=False, ttl=1800)
    def fetch_klines(symbol="BTCUSDT", interval="1h", days=30, incremental=False, last_timestamp=None):
        return _fetch_impl(symbol, interval, days, incremental, last_timestamp)
else:
    def fetch_klines(symbol="BTCUSDT", interval="1h", days=30, incremental=False, last_timestamp=None):
        return _fetch_impl(symbol, interval, days, incremental, last_timestamp)


# ------------------------------------------------------------
# Local test mode
# ------------------------------------------------------------
if __name__ == "__main__":
    print("Testing Binance integration...")
    df = fetch_klines("BTCUSDT", "1h", 2)
    print("Rows:", len(df))
    print(df.tail())
