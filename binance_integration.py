# ============================================================
# Binance Integration (Final Stable + Safe for Streamlit)
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
# Helper to load secrets safely
# ------------------------------------------------------------
def get_secret(key):
    """Fetch value from Streamlit secrets or .env file."""
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
# Binance endpoints (with fallback)
# ------------------------------------------------------------
BINANCE_ENDPOINTS = [
    "https://api.binance.com/api/v3/klines",
    "https://api1.binance.com/api/v3/klines",
    "https://data-api.binance.vision/api/v3/klines",
]

# ------------------------------------------------------------
# Core fetch logic (never breaks)
# ------------------------------------------------------------
def _safe_request(url, params, retries=3):
    """Make safe HTTP GET with retries and detect invalid data."""
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, timeout=10)
            if r.status_code in (451, 403):
                # Geo-block: skip to next endpoint
                continue
            r.raise_for_status()

            # Parse JSON safely
            try:
                data = r.json()
            except ValueError:
                # Not JSON (HTML/text) => skip
                continue

            # Must be list of lists for valid klines
            if not isinstance(data, list):
                continue
            if not all(isinstance(x, (list, tuple)) and len(x) >= 6 for x in data):
                continue

            return data  # Valid
        except Exception as e:
            time.sleep(1.5 * attempt)
            continue
    return []  # Empty if all failed


# ------------------------------------------------------------
# Fetch historical or incremental klines
# ------------------------------------------------------------
if st:
    @st.cache_data(show_spinner=False, ttl=1800)
    def fetch_klines(symbol="BTCUSDT", interval="1h", days=30, incremental=False, last_timestamp=None):
        return _fetch_klines_impl(symbol, interval, days, incremental, last_timestamp)
else:
    def fetch_klines(symbol="BTCUSDT", interval="1h", days=30, incremental=False, last_timestamp=None):
        return _fetch_klines_impl(symbol, interval, days, incremental, last_timestamp)


def _fetch_klines_impl(symbol, interval, days, incremental, last_timestamp):
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

    for base_url in BINANCE_ENDPOINTS:
        data = _safe_request(base_url, params)
        if not data:
            continue

        try:
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

        except Exception:
            continue  # try next endpoint if parsing fails

    # All endpoints failed
    if st:
        st.error(f"Failed to fetch Binance data for {symbol}. All endpoints returned invalid data.")
    return pd.DataFrame()
