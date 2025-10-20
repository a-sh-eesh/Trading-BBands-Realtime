from typing import Dict
import numpy as np
import pandas as pd
from candle_helpers import (
    wick_rejection_buy, wick_rejection_sell,
    strong_buy, strong_sell,
    exists_color_in_lookback,
    is_morning_star, is_evening_star
)

PCT = 0.013
LOOKBACK_CANDLES_COLOR = 4
MIN_RANGE_PCT = 0.005  # 0.5% minimum total range


def evaluate_signal(phase: str, trend: str, idx: int, df: pd.DataFrame, symbol: str = "COIN") -> Dict:
    out = {"entry_signal": "None", "reason": ""}
    if idx < 0 or idx >= len(df):
        out["reason"] = "index_out_of_range"
        return out

    row = df.iloc[idx]
    O, H, L, C = row["open"], row["high"], row["low"], row["close"]
    Z = float(row.get("zlema", np.nan))
    U, Lo = row.get("upper_band", np.nan), row.get("lower_band", np.nan)

    # --- 0.5% minimum total range filter ---
    R = H - L
    if R < (MIN_RANGE_PCT * C):
        out["reason"] = "ignored_small_range_0.5%"
        return out

    # ------------------------------------------------------
    # === NEW TTR LOGIC ===
    # ------------------------------------------------------
    if phase.upper() == "TTR":
        # skip TTR for sideways
        if trend not in ("bullish", "bearish"):
            out["reason"] = "ttr_skipped_for_sideways"
            return out

        # --- BULLISH TREND ---
        if trend == "bullish":
            touch_zlema = (L <= Z <= H)
            if touch_zlema:
                wick_ok = wick_rejection_buy(O, H, L, C)
                strong_ok = strong_buy(df, idx)
                morning_ok = is_morning_star(df, idx)

                if wick_ok or strong_ok or morning_ok:
                    reasons = []
                    if morning_ok: reasons.append("morning_star")
                    if wick_ok: reasons.append("wick_rejection")
                    if strong_ok: reasons.append("strong_buy")
                    out["entry_signal"] = "BUY"
                    out["reason"] = "zlema_touch+" + "+".join(reasons)
                    return out

        # --- BEARISH TREND ---
        if trend == "bearish":
            touch_zlema = (L <= Z <= H)
            if touch_zlema:
                wick_ok = wick_rejection_sell(O, H, L, C, U)
                strong_ok = strong_sell(df, idx)
                evening_ok = is_evening_star(df, idx)

                if wick_ok or strong_ok or evening_ok:
                    reasons = []
                    if evening_ok: reasons.append("evening_star")
                    if wick_ok: reasons.append("wick_rejection")
                    if strong_ok: reasons.append("strong_sell")
                    out["entry_signal"] = "SELL"
                    out["reason"] = "zlema_touch+" + "+".join(reasons)
                    return out

        # No valid pattern found
        out["reason"] = "zlema_touched_no_pattern"
        return out

    # ------------------------------------------------------
    # === EXISTING LOGIC FOR BTR / SIDEWAYS ===
    # ------------------------------------------------------
    B_low, B_high = row.get("buy_zone_low", Lo), row.get("buy_zone_high", Lo)
    S_low, S_high = row.get("sell_zone_low", U), row.get("sell_zone_high", U)

    # === BUY LOGIC ===
    if trend in ("bullish", "sideways"):
        zone_touch = (H >= B_low) and (L <= B_high)
        cond_prev_green = exists_color_in_lookback(df, idx, LOOKBACK_CANDLES_COLOR, "green", trend)
        wick_ok = wick_rejection_buy(O, H, L, C)
        strong_ok = strong_buy(df, idx)
        morning_ok = is_morning_star(df, idx)

        if zone_touch and cond_prev_green and (wick_ok or strong_ok or morning_ok):
            reasons = []
            if morning_ok: reasons.append("morning_star")
            if wick_ok: reasons.append("wick_rejection")
            if strong_ok: reasons.append("strong_buy")
            out["entry_signal"] = "BUY"
            out["reason"] = "buy_zone_touch+" + "+".join(reasons)
            return out

    # === SELL LOGIC ===
    if trend in ("bearish", "sideways"):
        zone_touch = (H >= S_low) and (L <= S_high)
        cond_prev_red = exists_color_in_lookback(df, idx, LOOKBACK_CANDLES_COLOR, "red", trend)
        wick_ok = wick_rejection_sell(O, H, L, C, U)
        strong_ok = strong_sell(df, idx)
        evening_ok = is_evening_star(df, idx)

        if zone_touch and cond_prev_red and (wick_ok or strong_ok or evening_ok):
            reasons = []
            if evening_ok: reasons.append("evening_star")
            if wick_ok: reasons.append("wick_rejection")
            if strong_ok: reasons.append("strong_sell")
            out["entry_signal"] = "SELL"
            out["reason"] = "sell_zone_touch+" + "+".join(reasons)
            return out

    out["reason"] = "no_conditions_met"
    return out


def evaluate_candles(df: pd.DataFrame, phase: str, trend: str, symbol: str = "COIN") -> pd.DataFrame:
    required_cols = ["open", "high", "low", "close", "zlema", "upper_band", "lower_band"]
    for c in required_cols:
        if c not in df.columns:
            raise ValueError(f"Missing column: {c}")

    signals, reasons = [], []
    for i in range(len(df)):
        res = evaluate_signal(phase=phase, trend=trend, idx=i, df=df, symbol=symbol)
        signals.append(res["entry_signal"])
        reasons.append(res["reason"])

    df_out = df.copy()
    df_out["entry_signal"] = signals
    df_out["reason"] = reasons
    return df_out
