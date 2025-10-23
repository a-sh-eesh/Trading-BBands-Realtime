# ============================================================
# Binance Integration (Region-Safe + Streamlit-Compatible)
# ============================================================

import os
import time
import pandas as pd
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

try:
    import streamlit as st
except ImportError:
    st = None

load_dotenv()


# -----------------------
# Secrets helper
# -----------------------
def get_secret(key):
    if st and hasattr(st, "secrets"):
        try:
            if key in st.secrets:
                return st.secrets[key]
            if "general" in st.secrets and key in st.secrets["general"]:
                return st.secrets["general"][key]
        except Exception:
            pass
    return os.getenv(key)


# -----------------------
# Binance endpoints
# -----------------------
BINANCE_ENDPOINTS = [
    "https://api.binance.com/api/v3/klines",
    "https://data-api.binance.vision/api/v3/klines",
]

# Public backup CSV when region blocked
CSV_FALLBACK_URL = (
    "https://data.binance.vision/data/spot/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-2025-09.csv"
)


def _safe_request(url, params, retries=3):
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, timeout=10)
            if r.status_code == 451 or r.status_code == 403:
                continue
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list) and all(isinstance(x, list) for x in data):
                return data
        except Exception:
            time.sleep(1.2 * attempt)
    return []


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


def _fallback_csv(symbol, interval):
    """Download fallback CSV from Binance Vision."""
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
        return df
    except Exception:
        return pd.DataFrame()


if st:
    @st.cache_data(show_spinner=False, ttl=1800)
    def fetch_klines(symbol="BTCUSDT", interval="1h", days=30):
        return _fetch(symbol, interval, days)
else:
    def fetch_klines(symbol="BTCUSDT", interval="1h", days=30):
        return _fetch(symbol, interval, days)


def _fetch(symbol, interval, days):
    start_time = int((datetime.utcnow() - timedelta(days=days)).timestamp() * 1000)
    params = {"symbol": symbol.upper(), "interval": interval, "startTime": start_time, "limit": 1000}

    for base in BINANCE_ENDPOINTS:
        data = _safe_request(base, params)
        if data:
            try:
                return _parse_klines(data)
            except Exception:
                continue

    # fallback CSV
    df = _fallback_csv(symbol, interval)
    if not df.empty:
        if st:
            st.warning(f"Using fallback CSV data for {symbol}. Live Binance API unavailable.")
        return df

    if st:
        st.error(f"Failed to fetch any data for {symbol}. Region might be blocked.")
    return pd.DataFrame()


# -----------------------
# Local test
# -----------------------
if __name__ == "__main__":
    df = fetch_klines("BTCUSDT", "1h", 2)
    print(df.tail())
