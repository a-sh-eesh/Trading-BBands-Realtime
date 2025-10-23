# ============================================================
# Binance Integration (Stable & Streamlit-compatible)
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

# ------------------------------------------------------------
# Helper: Get secret values
# ------------------------------------------------------------
def get_secret(key):
    """Get value from Streamlit secrets or .env."""
    if st and hasattr(st, "secrets"):
        try:
            if key in st.secrets.get("general", {}):
                return st.secrets["general"][key]
        except Exception:
            pass
    return os.getenv(key)


# ------------------------------------------------------------
# Binance Data Fetcher
# ------------------------------------------------------------
BASE_URL = "https://api.binance.com/api/v3/klines"


@st.cache_data(show_spinner=False, ttl=1800)
def fetch_klines(symbol="BTCUSDT", interval="1h", days=30, incremental=False, last_timestamp=None):
    """
    Fetch historical or incremental kline data using Binance public REST API.

    Args:
        symbol (str): Trading pair.
        interval (str): Candle interval, e.g., '1h'.
        days (int): Number of days for full history.
        incremental (bool): Fetch only the last few candles if True.
        last_timestamp (int): Last fetched candle close time (ms).

    Returns:
        pd.DataFrame: Kline data with datetime index.
    """
    try:
        if incremental and last_timestamp:
            start_time = last_timestamp
        else:
            start_time = int((datetime.utcnow() - timedelta(days=days)).timestamp() * 1000)

        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "startTime": start_time,
            "limit": 1000,
        }

        response = requests.get(BASE_URL, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, list) or len(data) == 0:
            return pd.DataFrame()

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
            "open": "float", "high": "float", "low": "float", "close": "float", "volume": "float"
        })
        df.set_index("close_time", inplace=True)
        df.sort_index(inplace=True)

        return df

    except requests.exceptions.RequestException as e:
        if st:
            st.error(f"Binance API error: {e}")
        return pd.DataFrame()
    except Exception as e:
        if st:
            st.error(f"Unexpected error while fetching {symbol}: {e}")
        return pd.DataFrame()
