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
# Fetch Historical + Incremental Klines (Public API only)
# ------------------------------------------------------------
def fetch_klines(symbol="BTCUSDT", interval="1h", days=30, start_time=None, end_time=None):
    """
    Fetch candlestick (kline) data from Binance REST API.
    Supports both full (days-based) and incremental (start_time/end_time) fetching.

    Args:
        symbol (str): Trading pair, e.g., "BTCUSDT"
        interval (str): Candle interval, e.g., "1h", "4h", "1d"
        days (int): Number of days to fetch if no start/end time is given
        start_time (datetime, optional): UTC datetime to start fetching from
        end_time (datetime, optional): UTC datetime to end fetching at

    Returns:
        pd.DataFrame: Columns ['open_time', 'open', 'high', 'low', 'close', 'volume']
    """
    try:
        base_url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": symbol, "interval": interval, "limit": 1000}

        # If incremental fetch requested, convert times to ms timestamps
        if start_time:
            params["startTime"] = int(pd.Timestamp(start_time).timestamp() * 1000)
        if end_time:
            params["endTime"] = int(pd.Timestamp(end_time).timestamp() * 1000)

        # If no start_time, fallback to days-based limit
        if not start_time and days:
            limit = min(days * 24, 1000)
            params["limit"] = limit

        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data or len(data) == 0:
            print(f"[{symbol}] No klines returned.")
            return pd.DataFrame()

        df = pd.DataFrame(
            data,
            columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_asset_volume", "num_trades",
                "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore",
            ],
        )

        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        numeric_cols = ["open", "high", "low", "close", "volume"]
        df[numeric_cols] = df[numeric_cols].astype(float)
        df = df[["open_time", "open", "high", "low", "close", "volume"]]

        print(f"[{symbol}] Fetched {len(df)} candles ({interval}).")
        return df

    except Exception as e:
        print(f"Public Binance API error for {symbol}: {e}")
        time.sleep(2)
        return pd.DataFrame()

# ------------------------------------------------------------
# Optional: Local test (run this file alone to verify data)
# ------------------------------------------------------------
if __name__ == "__main__":
    symbol = "BTCUSDT"
    df = fetch_klines(symbol=symbol, interval="1h", days=10)
    print(df.tail())
