from typing import Literal
import numpy as np
import math
import pandas as pd

Trend = Literal["bullish", "bearish", "sideways"]

# ============================================================
# Utility
# ============================================================

def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide two numbers."""
    try:
        if denominator == 0 or np.isnan(denominator):
            return default
        return numerator / denominator
    except Exception:
        return default


# ============================================================
# Candle Color Logic
# ============================================================

def get_candle_color(O: float, C: float, trend: Trend,
                     is_in_buy_zone: bool = False,
                     is_in_sell_zone: bool = False) -> str:
    """
    Determines candle color based on open/close/trend.
    """
    if C > O:
        return "green"
    if C < O:
        return "red"
    if trend == "bullish":
        return "green"
    if trend == "bearish":
        return "red"
    if trend == "sideways":
        if is_in_buy_zone:
            return "green"
        if is_in_sell_zone:
            return "red"
    return "neutral"


# ============================================================
# Wick Rejection Patterns (with 0.5% minimum range)
# ============================================================

def wick_rejection_buy(O: float, H: float, L: float, C: float) -> bool:
    """
    Strong BUY Wick Rejection:
      - Candle range ≥ 0.5% of close price
      - Long lower wick (≥ 33% of range)
      - Body ≥ 40% of range
      - Small upper wick (≤ 25% of range)
    """
    R = H - L
    if R <= 0 or any(np.isnan([O, H, L, C])):
        return False
    min_range = 0.005 * C
    if R < min_range:
        return False
    body = abs(C - O)
    lower_wick = min(O, C) - L
    upper_wick = H - max(O, C)
    return (
        (lower_wick / R >= 0.33) and
        (body / R >= 0.4) and
        (upper_wick / R <= 0.25) and
        (C > O)
    )


def wick_rejection_sell(O: float, H: float, L: float, C: float, U: float) -> bool:
    """
    Strong SELL Wick Rejection:
      - Candle range ≥ 0.5% of close price
      - Long upper wick (≥ 33% of range)
      - Body ≥ 40% of range
      - Small lower wick (≤ 25% of range)
    """
    R = H - L
    if R <= 0 or any(np.isnan([O, H, L, C, U])):
        return False
    min_range = 0.005 * C
    if R < min_range:
        return False
    body = abs(O - C)
    upper_wick = H - max(O, C)
    lower_wick = min(O, C) - L
    return (
        (upper_wick / R >= 0.33) and
        (body / R >= 0.4) and
        (lower_wick / R <= 0.25) and
        (C < O)
    )


# ============================================================
# Strong Candle Logic (based on 10-bar body average)
# ============================================================

def strong_buy(df: pd.DataFrame, idx: int) -> bool:
    if idx < 10:
        return False
    O, C = df["open"].iat[idx], df["close"].iat[idx]
    body_size = abs(C - O)
    body_avg = np.mean(np.abs(df["close"].iloc[idx - 10:idx] - df["open"].iloc[idx - 10:idx]))
    return (C > O) and (body_size >= 1.2 * body_avg)


def strong_sell(df: pd.DataFrame, idx: int) -> bool:
    if idx < 10:
        return False
    O, C = df["open"].iat[idx], df["close"].iat[idx]
    body_size = abs(C - O)
    body_avg = np.mean(np.abs(df["close"].iloc[idx - 10:idx] - df["open"].iloc[idx - 10:idx]))
    return (C < O) and (body_size >= 1.2 * body_avg)


# ============================================================
# Morning Star / Evening Star Patterns
# ============================================================

def is_morning_star(df: pd.DataFrame, idx: int) -> bool:
    if idx < 10:
        return False
    O1, H1, L1, C1 = df["open"].iat[idx - 2], df["high"].iat[idx - 2], df["low"].iat[idx - 2], df["close"].iat[idx - 2]
    O2, H2, L2, C2 = df["open"].iat[idx - 1], df["high"].iat[idx - 1], df["low"].iat[idx - 1], df["close"].iat[idx - 1]
    O3, H3, L3, C3 = df["open"].iat[idx], df["high"].iat[idx], df["low"].iat[idx], df["close"].iat[idx]
    body_avg = np.mean(np.abs(df["close"].iloc[idx - 10:idx] - df["open"].iloc[idx - 10:idx]))

    # Strong bearish first
    body1 = abs(O1 - C1)
    strong_sell_first = (C1 < O1) and (body1 >= 1.2 * body_avg) and ((C1 - L1) / (H1 - L1) <= 0.25)

    # Small indecision
    R2 = H2 - L2
    small_body = R2 > 0 and abs(C2 - O2) / R2 < 0.3

    # Bullish reversal
    bullish_third = (C3 > O3) and (C3 > (O1 + C1) / 2)

    return strong_sell_first and small_body and bullish_third


def is_evening_star(df: pd.DataFrame, idx: int) -> bool:
    if idx < 10:
        return False
    O1, H1, L1, C1 = df["open"].iat[idx - 2], df["high"].iat[idx - 2], df["low"].iat[idx - 2], df["close"].iat[idx - 2]
    O2, H2, L2, C2 = df["open"].iat[idx - 1], df["high"].iat[idx - 1], df["low"].iat[idx - 1], df["close"].iat[idx - 1]
    O3, H3, L3, C3 = df["open"].iat[idx], df["high"].iat[idx], df["low"].iat[idx], df["close"].iat[idx]
    body_avg = np.mean(np.abs(df["close"].iloc[idx - 10:idx] - df["open"].iloc[idx - 10:idx]))

    # Strong bullish first
    body1 = abs(O1 - C1)
    strong_buy_first = (C1 > O1) and (body1 >= 1.2 * body_avg) and ((H1 - C1) / (H1 - L1) <= 0.25)

    # Small indecision
    R2 = H2 - L2
    small_body = R2 > 0 and abs(C2 - O2) / R2 < 0.3

    # Bearish reversal
    bearish_third = (C3 < O3) and (C3 < (O1 + C1) / 2)

    return strong_buy_first and small_body and bearish_third


# ============================================================
# Lookback Helper
# ============================================================

def exists_color_in_lookback(df: pd.DataFrame, idx: int, lookback: int, color: str,
                             trend: Trend, use_zones: bool = True) -> bool:
    start = max(0, idx - lookback)
    for j in range(idx - 1, start - 1, -1):
        O, C = df["open"].iat[j], df["close"].iat[j]
        is_in_buy_zone = is_in_sell_zone = False
        if use_zones:
            if "buy_zone_low" in df.columns and "buy_zone_high" in df.columns:
                b_low, b_high = df["buy_zone_low"].iat[j], df["buy_zone_high"].iat[j]
                is_in_buy_zone = b_low <= C <= b_high
            if "sell_zone_low" in df.columns and "sell_zone_high" in df.columns:
                s_low, s_high = df["sell_zone_low"].iat[j], df["sell_zone_high"].iat[j]
                is_in_sell_zone = s_low <= C <= s_high
        col = get_candle_color(O, C, trend, is_in_buy_zone, is_in_sell_zone)
        if col == color:
            return True
    return False
