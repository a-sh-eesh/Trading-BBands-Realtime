import numpy as np
import pandas as pd

"""
zlema_bbands_trading.py

Updated ZLEMA/Bollinger utility module:
- Keeps original indicators, adaptive PCT and zone logic
- Replaces the previous 6H overlay computation with a 4H overlay
- Provides compute_4h_overlay() (new) and compute_6h_overlay() wrapper for compatibility
"""

# === CONFIG CONSTANTS (kept from original file) ===
BASE_SCALE = 0.25
MIN_PCT = 0.002
MAX_PCT = 0.018
EMA_SPAN = 8
W_ATR = 0.25


# --------------------------
# 1. Compute 1H Indicators
# --------------------------
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute 1H ZLEMA, Bollinger Bands, and ATR (matches original logic)."""
    df = df.copy()
    span = 16
    lag = int((span - 1) / 2)

    # ZLEMA calculation (zero-lag EMA variant)
    df["ema"] = df["close"].ewm(span=span, adjust=False).mean()
    df["zlema"] = df["close"] + (df["close"] - df["close"].shift(lag))
    df["zlema"] = df["zlema"].ewm(span=span, adjust=False).mean()

    # Bollinger Bands on ZLEMA
    std = df["zlema"].rolling(window=span).std()
    df["upper_band"] = df["zlema"] + 2 * std
    df["lower_band"] = df["zlema"] - 2 * std

    # ATR (14)
    high_low = df["high"] - df["low"]
    high_close = np.abs(df["high"] - df["close"].shift(1))
    low_close = np.abs(df["low"] - df["close"].shift(1))
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = tr.rolling(window=14).mean()

    return df


# --------------------------
# 2. Adaptive PCT (original logic)
# --------------------------
def compute_adaptive_pct(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute adaptive percentage used to size zones.
    Mirrors original approach (raw_pct, scaled, smoothed, atr contribution,
    band-relative limiter) and writes pct_dynamic as in the original code.
    """
    df = df.copy()

    # raw band-relative percent
    df["raw_pct"] = (df["upper_band"] - df["lower_band"]) / df["zlema"]
    df["raw_pct_scaled"] = df["raw_pct"] * BASE_SCALE

    # smoothed pct
    df["smoothed_pct"] = df["raw_pct_scaled"].ewm(span=EMA_SPAN, adjust=False).mean()

    # atr component relative to price
    df["atr_component"] = (df["atr"] / df["zlema"]) * W_ATR

    # base dynamic PCT
    df["pct_dynamic"] = (
        0.6 * df["raw_pct_scaled"] +
        0.4 * df["smoothed_pct"] +
        df["atr_component"]
    )

    # clip to configured min/max
    df["pct_dynamic"] = df["pct_dynamic"].clip(lower=MIN_PCT, upper=MAX_PCT)

    # band-relative limiter (cap pct_dynamic to a fraction of band width)
    band_width_ratio = (df["upper_band"] - df["lower_band"]) / df["zlema"]
    df["pct_dynamic"] = np.minimum(df["pct_dynamic"], 0.6 * band_width_ratio)

    # cleanup & fill
    df["pct_dynamic"] = df["pct_dynamic"].clip(lower=MIN_PCT)
    df["pct_dynamic"] = df["pct_dynamic"].bfill().fillna(MIN_PCT)

    return df


# --------------------------
# 3. Compute 4H Overlay (NEW: replaces previous 6H overlay)
# --------------------------
def compute_4h_overlay(df: pd.DataFrame) -> pd.DataFrame:
    """
    Group 1H candles into 4-hour buckets and compute ZLEMA + Bollinger Bands on 4H.
    The resulting 4H columns are expanded back to the original 1H-indexed DataFrame.

    Output columns (appended to original df):
      - zlema_4h
      - upper_band_4h
      - lower_band_4h
    """
    # defensive copy
    df = df.copy().reset_index(drop=True)

    # ensure there's enough rows; if not, return original with NaNs
    if df.shape[0] == 0:
        df["zlema_4h"] = np.nan
        df["upper_band_4h"] = np.nan
        df["lower_band_4h"] = np.nan
        return df

    # assign group index: every 4 consecutive 1H rows form one 4H candle
    group_size = 4
    groups = np.floor(np.arange(len(df)) / group_size).astype(int)
    df["__group"] = groups

    # aggregate into 4H candles
    df_4h = df.groupby("__group").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum"
    })

    # compute ZLEMA on 4H close (use similar span to original; keep span=16)
    span = 16
    lag = int((span - 1) / 2)
    df_4h["ema"] = df_4h["close"].ewm(span=span, adjust=False).mean()
    df_4h["zlema_4h"] = df_4h["close"] + (df_4h["close"] - df_4h["close"].shift(lag))
    df_4h["zlema_4h"] = df_4h["zlema_4h"].ewm(span=span, adjust=False).mean()

    # 4H bollinger bands on zlema_4h
    std_4h = df_4h["zlema_4h"].rolling(window=span).std()
    df_4h["upper_band_4h"] = df_4h["zlema_4h"] + 2 * std_4h
    df_4h["lower_band_4h"] = df_4h["zlema_4h"] - 2 * std_4h

    # merge 4H columns back into original 1H dataframe by group index
    df = df.merge(
        df_4h[["zlema_4h", "upper_band_4h", "lower_band_4h"]],
        left_on="__group",
        right_index=True,
        how="left"
    )

    # drop helper column and return
    df.drop(columns=["__group"], inplace=True)
    return df


# --------------------------
# 6H compatibility wrapper (calls 4H implementation)
# --------------------------
def compute_6h_overlay(df: pd.DataFrame) -> pd.DataFrame:
    """
    Backwards-compatible wrapper. Historically users called compute_6h_overlay.
    This now redirects to compute_4h_overlay (the system was changed to 4H).
    """
    # call 4h implementation; keep the same returned columns but also optionally create 6h-named aliases
    df_out = compute_4h_overlay(df)
    # create 6h alias columns (in case other code expects these names)
    if "zlema_4h" in df_out.columns:
        df_out["zlema_6h"] = df_out["zlema_4h"]
    if "upper_band_4h" in df_out.columns:
        df_out["upper_band_6h"] = df_out["upper_band_4h"]
    if "lower_band_4h" in df_out.columns:
        df_out["lower_band_6h"] = df_out["lower_band_4h"]
    return df_out


# --------------------------
# 4. Apply Zones (original TTR behaviour kept)
# --------------------------
def apply_zones(df: pd.DataFrame, phase: str, trend: str) -> pd.DataFrame:
    """
    Define buy/sell zones.
      - TTR: no zones (pattern-based detection elsewhere)
      - BTR/Sideways: adaptive zones based on lower/upper bands and pct_dynamic
    Keeps original column names used for plotting: buy_zone_lower/upper, sell_zone_lower/upper
    """
    df = df.copy()
    phase_norm = str(phase).strip().upper()
    trend_norm = str(trend).strip().lower()

    # init columns
    df["buy_zone_low"] = np.nan
    df["buy_zone_high"] = np.nan
    df["sell_zone_low"] = np.nan
    df["sell_zone_high"] = np.nan

    if phase_norm == "TTR":
        # no zones for TTR (handled elsewhere)
        return df

    # For BTR or Sideways, compute zones relative to bands using pct_dynamic (as original)
    if phase_norm in ("BTR", "SIDEWAYS"):
        # ensure pct_dynamic exists (compute_adaptive_pct should be run before this)
        if "pct_dynamic" not in df.columns:
            # fallback to small constant if not present
            df["pct_dynamic"] = MIN_PCT

        df["buy_zone_low"] = df["lower_band"] * (1 - df["pct_dynamic"])
        df["buy_zone_high"] = df["lower_band"] * (1 + df["pct_dynamic"])
        df["sell_zone_low"] = df["upper_band"] * (1 - df["pct_dynamic"])
        df["sell_zone_high"] = df["upper_band"] * (1 + df["pct_dynamic"])

    # aliases kept for plotting compatibility
    df["buy_zone_lower"] = df["buy_zone_low"]
    df["buy_zone_upper"] = df["buy_zone_high"]
    df["sell_zone_lower"] = df["sell_zone_low"]
    df["sell_zone_upper"] = df["sell_zone_high"]

    return df


# --------------------------
# Validate Trend
# --------------------------
def validate_trend(trend: str) -> str:
    valid = {"bullish", "bearish", "sideways"}
    t = str(trend).strip().lower()
    if t not in valid:
        t = "sideways"
    return t


# --------------------------
# Optional: small CLI main (kept similar to original)
# --------------------------
def main():
    """Optional CLI entry used in original file. Left for backward compatibility."""
    print("\n=== ZLEMA Bollinger Trading System (Adaptive PCT + 4H Overlay) ===")
    phase = input("Enter market phase (TTR / BTR / Sideways): ").strip().upper()
    trend = validate_trend(input("Enter market trend (Bullish / Bearish / Sideways): "))
    symbols = []  # intentionally empty - original main fetched from global SYMBOLS
    # Use global SYMBOLS if not provided
    try:
        from __main__ import SYMBOLS as global_symbols
        symbols = global_symbols
    except Exception:
        # fallback to example list if not found
        symbols = ["BTCUSDT", "ETHUSDT"]

    for symbol in symbols:
        print(f"\nProcessing {symbol}...")
        # Note: original main used fetch_klines from outside; keep similar flow
        try:
            df = fetch_klines(symbol, interval="1h", days=30)
        except Exception as e:
            print(f"Fetch failed for {symbol}: {e}")
            continue
        if df is None or df.empty:
            print(f"No data for {symbol}, skipping.")
            continue

        df["open_time"] = pd.to_datetime(df["open_time"])
        df = compute_indicators(df)
        df = compute_adaptive_pct(df)
        df = compute_4h_overlay(df)
        df = apply_zones(df, phase, trend)
        df = evaluate_candles(df, phase, trend)

        out_file = f"{symbol}_signals.csv"
        df.to_csv(out_file, index=False)
        print(f"Saved: {out_file}")

    print("\nProcessing complete.")


if __name__ == "__main__":
    main()
