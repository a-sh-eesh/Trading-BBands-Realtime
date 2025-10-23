# ============================================================
# Binance Integration (Stable + Streamlit Compatible)
# ============================================================

import os
import time
import pandas as pd
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Optional Streamlit support
try:
    import streamlit as st
except ImportError:
    st = None

load_dotenv()

# ------------------------------------------------------------
# Get secret from Streamlit or .env
# ------------------------------------------------------------
def get_secret(key):
    """Return Streamlit secret or .env variable (safe fallback)."""
    if st and hasattr(st, "secrets"):
        try:
            if key in st.secrets.get("general", {}):
                return st.secrets["general"][key]
        except Exception:
            pass
    return os.getenv(key)


# ------------------------------------------------------------
# Binance Endpoints & Constants
# ------------------------------------------------------------
BINANCE_ENDPOINTS = [
    "https://api.binance.com/api/v3/klines",
    "https://api1.binance.com/api/v3/klines",
    "https://data-api.binance.vision/api/v3/klines",
]


# ------------------------------------------------------------
# Fetch Historical Klines (with regional fallback)
# ------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=1800)
def fetch_klines(
    symbol="BTCUSDT",
    interval="1h",
    days=30,
    incremental=False,
    last_timestamp=None,
    max_retries=3,
):
    """
    Fetch historical candlestick (kline) data with geo-block fallback.

    Args:
        symbol (str): Trading pair, e.g., "BTCUSDT"
        interval (str): Candle interval, e.g., "1h"
        days (int): Number of days for full history
        incremental (bool): Fetch only candles after last_timestamp if True
        last_timestamp (int): Milliseconds timestamp of last candle
        max_retries (int): Retry count per endpoint

    Returns:
        pd.DataFrame: Cleaned dataframe with OHLCV + timestamps.
    """
    try:
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

        last_error = None

        for attempt in range(max_retries):
            for base_url in BINANCE_ENDPOINTS:
                try:
                    url = base_url
                    response = requests.get(url, params=params, timeout=10)

                    # Handle geo-block (HTTP 451) or forbidden
                    if response.status_code in (451, 403):
                        continue

                    response.raise_for_status()
                    data = response.json()

                    if not isinstance(data, list) or len(data) == 0:
                        continue

                    # Build dataframe
                    df = pd.DataFrame(
                        data,
                        columns=[
                            "open_time", "open", "high", "low", "close", "volume",
                            "close_time", "quote_asset_volume", "num_trades",
                            "taker_buy_base", "taker_buy_quote", "ignore",
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

                except requests.exceptions.RequestException as re:
                    last_error = re
                    time.sleep(1.5 * (attempt + 1))
                    continue
                except Exception as e:
                    last_error = e
                    time.sleep(1.5 * (attempt + 1))
                    continue

        if st:
            st.error(f"Binance API error for {symbol}: {last_error}")
        return pd.DataFrame()

    except Exception as e:
        if st:
            st.error(f"Unexpected error while fetching {symbol}: {e}")
        return pd.DataFrame()
