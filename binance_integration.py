# ============================================================
# Binance Integration (Public REST API – Streamlit Compatible)
# Incremental and Full Fetch Support
# ============================================================

import os
import time
import pandas as pd
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Optional Streamlit import for reading secrets
try:
    import streamlit as st
except ImportError:
    st = None

# ------------------------------------------------------------
# Load environment variables and Streamlit secrets
# ------------------------------------------------------------
load_dotenv()

def get_secret(key):
    """Get value from Streamlit secrets or .env file."""
    if st and "general" in st.secrets and key in st.secrets["general"]:
        return st.secrets["general"][key]
    return os.getenv(key)

# ------------------------------------------------------------
# Fetch Historical + Incremental Klines (Public API)
# ------------------------------------------------------------
def fetch_klines(symbol="BTCUSDT", interval="1h", days=30, start_time=None, end_time=None):
    """
    Fetch candlestick (kline) data from Binance REST API.
    Supports both full (days-based) and incremental (start_time/end_time) fetching.
    Returns guaranteed columns ['open_time', 'open', 'high', 'low', 'close', 'volume'].
    """
    try:
        base_url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": symbol.upper(), "interval": interval, "limit": 1000}

        # If incremental fetch requested, convert times to ms timestamps
        if start_time:
            params["startTime"] = int(pd.Timestamp(start_time).timestamp() * 1000)
        if end_time:
            params["endTime"] = int(pd.Timestamp(end_time).timestamp() * 1000)

        # Default days fetch (if no incremental range given)
        if not start_time and days:
            limit = min(days * 24, 1000)
            params["limit"] = limit

        response = requests.get(base_url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        # Handle empty or invalid response
        if not data or len(data) == 0:
            print(f"[{symbol}] No data returned from Binance API.")
            return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume"])

        # Convert to DataFrame
        df = pd.DataFrame(data)
        if df.shape[1] < 6:
            print(f"[{symbol}] Unexpected Binance data structure: {df.shape}")
            return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume"])

        # Explicitly assign columns
        df.columns = [
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "num_trades",
            "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
        ]

        # Convert datatypes
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        numeric_cols = ["open", "high", "low", "close", "volume"]
        df[numeric_cols] = df[numeric_cols].astype(float)

        # Keep only the needed columns
        df = df[["open_time", "open", "high", "low", "close", "volume"]]

        print(f"[{symbol}] Data fetched successfully: {len(df)} candles.")
        return df

    except Exception as e:
        print(f"❌ Binance fetch failed for {symbol}: {e}")
        time.sleep(2)
        return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume"])

# ------------------------------------------------------------
# Optional: Local test (run this file alone to verify data)
# ------------------------------------------------------------
if __name__ == "__main__":
    symbol = "BTCUSDT"
    df = fetch_klines(symbol=symbol, interval="1h", days=10)
    print(df.tail())
