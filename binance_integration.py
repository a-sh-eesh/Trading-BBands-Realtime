# ============================================================
# Binance Integration (Streamlit Cloud Compatible)
# ============================================================

import os
import time
import pandas as pd
import requests
from datetime import datetime
from dotenv import load_dotenv

# Optional Streamlit import (for st.secrets)
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

# Load keys if needed later (for Telegram or other integrations)
BINANCE_API_KEY = get_secret("BINANCE_API_KEY")
BINANCE_API_SECRET = get_secret("BINANCE_API_SECRET")

# ------------------------------------------------------------
# Fetch Historical Klines (Public REST API)
# ------------------------------------------------------------
def fetch_klines(symbol="BTCUSDT", interval="1h", days=30):
    """
    Fetch historical candlestick (kline) data from Binance public REST API.

    Args:
        symbol (str): Trading pair, e.g., "BTCUSDT"
        interval (str): Candle interval, e.g., "1h", "4h", "1d"
        days (int): Number of days of data to fetch (approximate)

    Returns:
        pd.DataFrame: DataFrame with columns: open_time, open, high, low, close, volume
    """
    try:
        # Limit of 1000 candles per request (Binance restriction)
        limit = min(days * 24, 1000)

        # Public endpoint (no authentication needed)
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"

        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data or len(data) == 0:
            print(f"No data returned for {symbol}.")
            return pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame(
            data,
            columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_asset_volume", "num_trades",
                "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore",
            ],
        )

        # Clean up
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        numeric_cols = ["open", "high", "low", "close", "volume"]
        df[numeric_cols] = df[numeric_cols].astype(float)

        # Keep only required columns
        df = df[["open_time", "open", "high", "low", "close", "volume"]]
        print(f"Data fetched successfully for {symbol}.")
        return df

    except Exception as e:
        print(f"Public Binance API error for {symbol}: {e}")
        time.sleep(2)
        return pd.DataFrame()

# ------------------------------------------------------------
# Manual test (local debug)
# ------------------------------------------------------------
if __name__ == "__main__":
    df = fetch_klines("BTCUSDT", "1h", 10)
    print(df.tail())
