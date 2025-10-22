# ============================================================
# Binance Integration (Streamlit Cloud Compatible)
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

from binance.client import Client

# ------------------------------------------------------------
# Load environment variables and Streamlit secrets
# ------------------------------------------------------------
load_dotenv()

def get_secret(key):
    """Get value from Streamlit secrets or .env file."""
    if st and "general" in st.secrets and key in st.secrets["general"]:
        return st.secrets["general"][key]
    return os.getenv(key)

api_key = get_secret("BINANCE_API_KEY")
api_secret = get_secret("BINANCE_API_SECRET")

# ------------------------------------------------------------
# Initialize Binance client (skip ping for restricted regions)
# ------------------------------------------------------------
try:
    if api_key and api_secret:
        client = Client(api_key=api_key, api_secret=api_secret)
        print("Binance client initialized with API keys.")
    else:
        client = Client()
        print("Binance client initialized without keys.")
except Exception as e:
    client = None
    print(f"Binance client initialization skipped: {e}")

# ------------------------------------------------------------
# Fetch Historical Klines (with public fallback)
# ------------------------------------------------------------
def fetch_klines(symbol="BTCUSDT", interval="1h", days=20, start_time=None, end_time=None):
    """
    Fetch historical candlestick (kline) data from Binance or fallback public API.

    Args:
        symbol (str): Trading pair, e.g., "BTCUSDT".
        interval (str): Timeframe, e.g., "1h".
        days (int): Number of days of data to fetch if no start/end specified.
        start_time (str or datetime): Optional start time string (UTC) or datetime.
        end_time (str or datetime): Optional end time string (UTC) or datetime.

    Returns:
        pd.DataFrame: OHLCV data with open_time as datetime.
    """
    try:
        # Try Binance client first
        if client:
            if start_time:
                if isinstance(start_time, datetime):
                    start_time = start_time.strftime("%d %b %Y %H:%M:%S")
                if end_time is None:
                    end_time = datetime.utcnow().strftime("%d %b %Y %H:%M:%S")
                klines = client.get_historical_klines(
                    symbol=symbol,
                    interval=interval,
                    start_str=start_time,
                    end_str=end_time,
                )
            else:
                start_time = (datetime.utcnow() - timedelta(days=days)).strftime("%d %b %Y %H:%M:%S")
                klines = client.get_historical_klines(
                    symbol=symbol,
                    interval=interval,
                    start_str=start_time,
                )

            if klines and len(klines) > 0:
                df = pd.DataFrame(
                    klines,
                    columns=[
                        "open_time", "open", "high", "low", "close", "volume",
                        "close_time", "quote_asset_volume", "num_trades",
                        "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore",
                    ],
                )
                df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
                numeric_cols = ["open", "high", "low", "close", "volume"]
                df[numeric_cols] = df[numeric_cols].astype(float)
                return df[["open_time", "open", "high", "low", "close", "volume"]]
    except Exception as e:
        print(f"Primary Binance API failed: {e}")

    # --------------------------------------------------------
    # Fallback: use Binance public REST API
    # --------------------------------------------------------
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={days*24}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data:
            print("No data returned from fallback API.")
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
        print("Data fetched using public fallback API.")
        return df[["open_time", "open", "high", "low", "close", "volume"]]

    except Exception as e:
        print(f"Fallback fetch error for {symbol}: {e}")
        time.sleep(2)
        return pd.DataFrame()
