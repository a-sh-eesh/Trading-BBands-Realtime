# ============================================================
# Binance Integration (Public REST API – Streamlit Compatible)
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

# Load keys (kept for compatibility, not required for public API)
BINANCE_API_KEY = get_secret("BINANCE_API_KEY")
BINANCE_API_SECRET = get_secret("BINANCE_API_SECRET")

# ------------------------------------------------------------
# Fetch Historical Klines (Public API only)
# ------------------------------------------------------------
def fetch_klines(symbol="BTCUSDT", interval="1h", days=30):
    """
    Fetch historical candlestick (kline) data using Binance's public REST API.
    Works globally without needing API keys or authentication.

    Args:
        symbol (str): Trading pair, e.g., "BTCUSDT"
        interval (str): Candle interval, e.g., "1h", "4h", "1d"
        days (int): Approx number of days to fetch (limited to 1000 candles)

    Returns:
        pd.DataFrame: DataFrame with columns ['open_time', 'open', 'high', 'low', 'close', 'volume']
    """
    try:
        # Binance allows up to 1000 candles per request
        limit = min(days * 24, 1000)
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"

        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data or len(data) == 0:
            print(f"No data returned for {symbol}.")
            return pd.DataFrame()

        # Convert API response into DataFrame
        df = pd.DataFrame(
            data,
            columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_asset_volume", "num_trades",
                "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore",
            ],
        )

        # Convert datatypes
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        numeric_cols = ["open", "high", "low", "close", "volume"]
        df[numeric_cols] = df[numeric_cols].astype(float)

        # Return the key columns expected by your trading system
        df = df[["open_time", "open", "high", "low", "close", "volume"]]

        print(f"Data fetched successfully for {symbol} ({len(df)} rows).")
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
