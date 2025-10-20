# ============================================================
# Binance Integration (Enhanced with .env Support)
# ============================================================

import os
import pandas as pd
import time
from datetime import datetime, timedelta
from binance.client import Client
from dotenv import load_dotenv

# ------------------------------------------------------------
# Load environment variables
# ------------------------------------------------------------
load_dotenv()
api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")

# ------------------------------------------------------------
# Initialize Binance client
# ------------------------------------------------------------
if api_key and api_secret:
    client = Client(api_key=api_key, api_secret=api_secret)
    print("Binance client initialized with API keys.")
else:
    client = Client()
    print("Binance client initialized in public mode (no keys found).")

# ------------------------------------------------------------
# Fetch Historical Klines
# ------------------------------------------------------------
def fetch_klines(symbol="BTCUSDT", interval="1h", days=20, start_time=None, end_time=None):
    """
    Fetch historical candlestick (kline) data from Binance.

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

        if not klines:
            return pd.DataFrame()

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
        print(f"Binance fetch error for {symbol}: {e}")
        time.sleep(2)
        return pd.DataFrame()
