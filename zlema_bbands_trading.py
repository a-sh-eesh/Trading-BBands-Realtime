"""
ZLEMA Bollinger Trading System (Adaptive PCT + 6H Overlay)
-----------------------------------------------------------
This version:
- Uses adaptive PCT with band-relative limiter
- Removes zone logic for TTR phase
- TTR now activates purely on ZLEMA touch + candlestick patterns
- BTR & Sideways continue using adaptive buy/sell zones
"""

import os
import pandas as pd
import numpy as np
from candle_evaluator import evaluate_candles
from binance_integration import fetch_klines

# === CONFIG ===
BASE_SCALE = 0.25         # scaling factor for adaptive PCT
LOOKBACK_DAYS = 20
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LTCUSDT"]

MIN_PCT = 0.002           # 0.2%
MAX_PCT = 0.018            # 1.8%
EMA_SPAN = 8              # smoothing for PCT
W_ATR = 0.25              # weight for ATR-based contribution


# === Compute 1H Indicators ===
def compute_indicators(df):
    """Compute 1H ZLEMA, Bollinger Bands, and ATR."""
    span = 16
    lag = (span - 1) / 2

    # --- ZLEMA Calculation ---
    df["ema"] = df["close"].ewm(span=span, adjust=False).mean()
    df["zlema"] = df["close"] + (df["close"] - df["close"].shift(int(lag)))
    df["zlema"] = df["zlema"].ewm(span=span, adjust=False).mean()

    # --- Bollinger Bands ---
    std = df["zlema"].rolling(window=span).std()
    df["upper_band"] = df["zlema"] + 2 * std
    df["lower_band"] = df["zlema"] - 2 * std

    # --- ATR (14) ---
    high_low = df["high"] - df["low"]
    high_close = np.abs(df["high"] - df["close"].shift())
    low_close = np.abs(df["low"] - df["close"].shift())
    tr = high_low.combine(high_close, max).combine(low_close, max)
    df["atr"] = tr.rolling(window=14).mean()

    return df


# === Adaptive PCT (with Band-Relative Limiter) ===
def compute_adaptive_pct(df):
    """Compute adaptive float percentage (Option A logic + band-relative limiter)."""
    df["raw_pct"] = (df["upper_band"] - df["lower_band"]) / df["zlema"]
    df["raw_pct_scaled"] = df["raw_pct"] * BASE_SCALE
    df["smoothed_pct"] = df["raw_pct_scaled"].ewm(span=EMA_SPAN, adjust=False).mean()
    df["atr_component"] = (df["atr"] / df["zlema"]) * W_ATR

    # --- Base adaptive PCT logic ---
    df["pct_dynamic"] = (
        0.6 * df["raw_pct_scaled"] +
        0.4 * df["smoothed_pct"] +
        df["atr_component"]
    ).clip(lower=MIN_PCT, upper=MAX_PCT)

    # --- Band-relative limiter ---
    band_width_ratio = (df["upper_band"] - df["lower_band"]) / df["zlema"]
    df["pct_dynamic"] = np.minimum(df["pct_dynamic"], 0.6 * band_width_ratio)

    # Cleanup
    df["pct_dynamic"] = df["pct_dynamic"].clip(lower=MIN_PCT)
    df["pct_dynamic"] = df["pct_dynamic"].bfill().fillna(MIN_PCT)
    return df


# === Compute 6H Bollinger Bands (from 1H candles) ===
def compute_6h_overlay(df):
    """
    Groups 1-hour candles into 6-hour segments and computes
    ZLEMA + Bollinger Bands (6H) for higher-timeframe context.
    Results are expanded back to 1H rows.
    """
    df = df.copy().reset_index(drop=True)
    df["group"] = np.floor(np.arange(len(df)) / 6)

    df_6h = df.groupby("group").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum"
    })

    span = 16
    lag = (span - 1) / 2
    df_6h["ema"] = df_6h["close"].ewm(span=span, adjust=False).mean()
    df_6h["zlema_6h"] = df_6h["close"] + (df_6h["close"] - df_6h["close"].shift(int(lag)))
    df_6h["zlema_6h"] = df_6h["zlema_6h"].ewm(span=span, adjust=False).mean()

    std_6h = df_6h["zlema_6h"].rolling(window=span).std()
    df_6h["upper_band_6h"] = df_6h["zlema_6h"] + 2 * std_6h
    df_6h["lower_band_6h"] = df_6h["zlema_6h"] - 2 * std_6h

    df = df.merge(
        df_6h[["zlema_6h", "upper_band_6h", "lower_band_6h"]],
        left_on="group",
        right_index=True,
        how="left"
    )

    df.drop(columns=["group"], inplace=True)
    return df


# === Apply Zones (Updated for TTR Logic) ===
def apply_zones(df, phase, trend):
    """
    Define buy/sell zones.
    - For TTR: removes zones entirely (pattern-based on ZLEMA only)
    - For BTR & Sideways: normal adaptive zones from Bollinger Bands
    """
    phase = phase.strip().upper()
    trend = trend.strip().lower()

    # Reset all zone columns
    df["buy_zone_low"] = np.nan
    df["buy_zone_high"] = np.nan
    df["sell_zone_low"] = np.nan
    df["sell_zone_high"] = np.nan

    # --- NEW TTR LOGIC ---
    if phase == "TTR":
        if trend not in ["bullish", "bearish"]:
            print("Skipping TTR logic for sideways trend.")
        # No zones for TTR, handled directly via ZLEMA in candle_evaluator
        return df

    # --- BTR or Sideways Zones ---
    elif phase in ["BTR", "SIDEWAYS"]:
        df["buy_zone_low"] = df["lower_band"] * (1 - df["pct_dynamic"])
        df["buy_zone_high"] = df["lower_band"] * (1 + df["pct_dynamic"])
        df["sell_zone_low"] = df["upper_band"] * (1 - df["pct_dynamic"])
        df["sell_zone_high"] = df["upper_band"] * (1 + df["pct_dynamic"])

    else:
        print(f"Warning: Unknown phase '{phase}' — skipping zone logic.")

    # Aliases for plotting compatibility
    df["buy_zone_lower"] = df["buy_zone_low"]
    df["buy_zone_upper"] = df["buy_zone_high"]
    df["sell_zone_lower"] = df["sell_zone_low"]
    df["sell_zone_upper"] = df["sell_zone_high"]

    return df


# === Validate Trend Input ===
def validate_trend(trend):
    valid = {"bullish", "bearish", "sideways"}
    trend = trend.strip().lower()
    if trend not in valid:
        print(f"Warning: Invalid trend '{trend}', defaulting to 'sideways'.")
        trend = "sideways"
    return trend


# === Main Execution ===
def main():
    print("\n=== ZLEMA Bollinger Trading System (Adaptive PCT + 6H Overlay) ===")

    phase = input("Enter market phase (TTR / BTR / Sideways): ").strip().upper()
    trend = validate_trend(input("Enter market trend (Bullish / Bearish / Sideways): "))

    for symbol in SYMBOLS:
        print(f"\nProcessing {symbol}...")
        df = fetch_klines(symbol, interval="1h", days=LOOKBACK_DAYS)
        if df is None or df.empty:
            print(f"Warning: No data for {symbol}, skipping.")
            continue

        df["open_time"] = pd.to_datetime(df["open_time"])

        # Step 1: Compute indicators
        df = compute_indicators(df)

        # Step 2: Adaptive PCT (band-relative)
        df = compute_adaptive_pct(df)

        # Step 3: Compute 6H overlay
        df = compute_6h_overlay(df)

        # Step 4: Apply zones (TTR removes them)
        df = apply_zones(df, phase, trend)

        # Step 5: Candle evaluation and signals
        df = evaluate_candles(df, phase, trend)

        # Step 6: Save output
        output_file = f"{symbol}_signals.csv"
        df.to_csv(output_file, index=False)
        print(f"Saved: {output_file}")

    print("\nAll symbols processed successfully.")


if __name__ == "__main__":
    main()
