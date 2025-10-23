# ============================================================
# Binance Integration (Stable + Streamlit Compatible)
# ============================================================

import os
import time
from datetime import datetime, timedelta

import pandas as pd
import requests
from dotenv import load_dotenv

# Optional Streamlit support (kept optional so module can be imported in non-streamlit contexts)
try:
    import streamlit as st
except Exception:
    st = None

load_dotenv()

# ------------------------------------------------------------
# Get secret from Streamlit or .env
# ------------------------------------------------------------
def get_secret(key):
    """Return Streamlit secret or .env variable (safe fallback)."""
    if st and hasattr(st, "secrets"):
        try:
            # support both flat and [general] style
            if key in st.secrets:
                return st.secrets[key]
            if "general" in st.secrets and key in st.secrets.get("general", {}):
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
# Use a safe cache if Streamlit present; otherwise, behave as plain function.
if st:
    @st.cache_data(show_spinner=False, ttl=1800)
    def fetch_klines(
        symbol="BTCUSDT",
        interval="1h",
        days=30,
        incremental=False,
        last_timestamp=None,
        max_retries=3,
    ):
        return _fetch_klines_impl(symbol, interval, days, incremental, last_timestamp, max_retries)
else:
    def fetch_klines(
        symbol="BTCUSDT",
        interval="1h",
        days=30,
        incremental=False,
        last_timestamp=None,
        max_retries=3,
    ):
        return _fetch_klines_impl(symbol, interval, days, incremental, last_timestamp, max_retries)


def _fetch_klines_impl(symbol, interval, days, incremental, last_timestamp, max_retries):
    """
    Internal implementation to fetch klines with endpoint fallback.
    Always returns a pandas.DataFrame (possibly empty) and never raises RequestExceptions outward.
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
                    resp = requests.get(base_url, params=params, timeout=10)

                    # If geo-block / unavailable for legal reasons or forbidden, try next endpoint
                    if resp.status_code in (451, 403):
                        last_error = requests.HTTPError(f"{resp.status_code} for url: {resp.url}")
                        continue

                    resp.raise_for_status()
                    data = resp.json()

                    if not isinstance(data, list) or len(data) == 0:
                        last_error = None  # empty but valid
                        continue

                    df = pd.DataFrame(
                        data,
                        columns=[
                            "open_time", "open", "high", "low", "close", "volume",
                            "close_time", "quote_asset_volume", "num_trades",
                            "taker_buy_base", "taker_buy_quote", "ignore",
                        ],
                    )

                    # Convert timestamps and numeric columns
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
                    # backoff
                    time.sleep(1.5 * (attempt + 1))
                    continue
                except Exception as e:
                    last_error = e
                    time.sleep(1.5 * (attempt + 1))
                    continue

        # If we reach here, either we had errors or no endpoint returned data
        if st:
            if last_error:
                st.error(f"Public Binance API error for {symbol}: {last_error}")
            else:
                st.warning(f"{symbol} initial fetch returned no data from public endpoints.")
        return pd.DataFrame()

    except Exception as e:
        if st:
            st.error(f"Unexpected error while fetching {symbol}: {e}")
        return pd.DataFrame()


# ------------------------------------------------------------
# (Optional) local test entrypoint
# ------------------------------------------------------------
if __name__ == "__main__":
    # quick local smoke test when running this file directly
    symbol = "BTCUSDT"
    print(f"Testing fetch_klines for {symbol} ...")
    df_test = fetch_klines(symbol=symbol, interval="1h", days=3)
    print("Rows:", len(df_test))
    if not df_test.empty:
        print(df_test.tail())
