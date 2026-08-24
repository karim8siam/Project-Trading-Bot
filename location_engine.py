"""
Location Engine & Institutional Order Block Detector.
Identifies:
1. Bullish & Bearish Order Blocks (Last opposing candle before institutional expansion move)
2. Multi-touch Support & Resistance (Grade A with 3+ touches vs Grade B 1-2 touches)
3. Trendline Detection (3+ swing points)
4. Location Grading: Grade S (Super), Grade A (Strong), Grade B (Decent), Grade C (Weak/Ignored)
"""

import math
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime
from indicators import compute_fibonacci_levels


def detect_order_blocks(
    df: pd.DataFrame,
    lookback: int = 50,
    expansion_threshold: float = 1.8
) -> Dict[str, List[Dict[str, float]]]:
    """
    Finds Institutional Order Blocks:
    - Bullish Order Block: The LAST bearish (red) candle before a massive bullish expansion move.
    - Bearish Order Block: The LAST bullish (green) candle before a massive bearish expansion move.
    """
    if len(df) < lookback:
        return {"bullish_obs": [], "bearish_obs": []}

    sub = df.iloc[-lookback:]
    bullish_obs = []
    bearish_obs = []

    for i in range(2, len(sub) - 2):
        c_prev = sub.iloc[i]
        c_next1 = sub.iloc[i + 1]
        c_next2 = sub.iloc[i + 2]

        o_p, cl_p = float(c_prev["open"]), float(c_prev["close"])
        h_p, l_p = float(c_prev["high"]), float(c_prev["low"])
        is_red_p = cl_p < o_p
        is_green_p = cl_p > o_p

        # 1. Bullish Order Block: Red candle followed by 2 strong green candles with large price jump
        if is_red_p:
            move_up = (float(c_next2["close"]) - o_p) / (o_p + 1e-9)
            atr_val = float(c_prev.get("atr_14", o_p * 0.005))
            if move_up > 0 and (float(c_next2["close"]) - o_p) >= expansion_threshold * atr_val:
                bullish_obs.append({
                    "top": max(o_p, cl_p),
                    "bottom": l_p,
                    "index": i,
                    "strength": move_up
                })

        # 2. Bearish Order Block: Green candle followed by 2 strong red candles with large price drop
        if is_green_p:
            move_down = (o_p - float(c_next2["close"])) / (o_p + 1e-9)
            atr_val = float(c_prev.get("atr_14", o_p * 0.005))
            if move_down > 0 and (o_p - float(c_next2["close"])) >= expansion_threshold * atr_val:
                bearish_obs.append({
                    "top": h_p,
                    "bottom": min(o_p, cl_p),
                    "index": i,
                    "strength": move_down
                })

    return {
        "bullish_obs": bullish_obs[-3:],  # keep 3 most recent active order blocks
        "bearish_obs": bearish_obs[-3:]
    }


def detect_support_resistance_touches(
    df: pd.DataFrame,
    current_price: float,
    lookback: int = 80,
    tolerance_pct: float = 0.005
) -> Tuple[int, str]:
    """
    Counts how many times previous candle highs/lows bounced at the current price level.
    3+ touches = Grade A Major Support/Resistance
    1-2 touches = Grade B Minor Support/Resistance
    """
    sub = df.tail(lookback)
    touches = 0

    for _, row in sub.iterrows():
        low_p = float(row["low"])
        high_p = float(row["high"])
        if abs(low_p - current_price) / current_price <= tolerance_pct:
            touches += 1
        elif abs(high_p - current_price) / current_price <= tolerance_pct:
            touches += 1

    if touches >= 3:
        return touches, "MAJOR"
    elif touches >= 1:
        return touches, "MINOR"
    return 0, "NONE"


def evaluate_master_location(
    df: pd.DataFrame,
    idx: int = -1,
    direction: str = "LONG"
) -> Dict[str, Any]:
    """
    Master Section 2 Location Evaluator (50 Base Points + Confluence Bonuses):
    - Grade S (Super - 45-50 pts): Order Block + (Fib 61.8% or EMA 200 or S/R)
    - Grade A (Strong - 30-40 pts): Order Block alone (40 pts) or Fib 61.8% alone (30 pts) or Major S/R (30 pts) or EMA 200 (30 pts)
    - Grade B (Decent - 20 pts): Fib 50%/38.2% or EMA 50 or Minor S/R
    - Grade C (Weak - 0 pts): Random area -> Bot ignores!
    """
    row = df.iloc[idx]
    close = float(row["close"])
    ema50 = float(row["ema_50"])
    ema200 = float(row["ema_200"])
    ema21 = float(row["ema_21"])

    tol = 0.004  # 0.4% proximity tolerance

    # 1. Order Blocks
    ob_data = detect_order_blocks(df, lookback=60)
    in_order_block = False
    ob_desc = ""

    if direction.upper() == "LONG":
        for ob in ob_data["bullish_obs"]:
            if ob["bottom"] * 0.997 <= close <= ob["top"] * 1.003:
                in_order_block = True
                ob_desc = f"Bullish Order Block Zone (${ob['bottom']:,.2f} - ${ob['top']:,.2f})"
                break
    else:  # SHORT
        for ob in ob_data["bearish_obs"]:
            if ob["bottom"] * 0.997 <= close <= ob["top"] * 1.003:
                in_order_block = True
                ob_desc = f"Bearish Order Block Zone (${ob['bottom']:,.2f} - ${ob['top']:,.2f})"
                break

    # 2. Fibonacci Retracements
    fibs = compute_fibonacci_levels(df, lookback=60)
    at_fib_618 = abs(close - fibs["fib_618"]) / close <= tol
    at_fib_500 = abs(close - fibs["fib_500"]) / close <= tol
    at_fib_382 = abs(close - fibs["fib_382"]) / close <= tol

    # 3. Moving Averages
    at_ema_200 = abs(close - ema200) / close <= tol
    at_ema_50 = abs(close - ema50) / close <= tol
    at_ema_21 = abs(close - ema21) / close <= tol

    # 4. Support / Resistance Touches
    touches, sr_type = detect_support_resistance_touches(df, current_price=close, lookback=80)
    is_major_sr = (sr_type == "MAJOR")
    is_minor_sr = (sr_type == "MINOR")

    # Determine Grade and Points
    confluences = []
    if in_order_block:
        confluences.append(ob_desc)
    if at_fib_618:
        confluences.append("Fibonacci 61.8% Golden Ratio")
    if at_ema_200:
        confluences.append("EMA 200 Institutional Level")
    if is_major_sr:
        confluences.append(f"Major S/R Level ({touches} prior touches)")
    if at_fib_500:
        confluences.append("Fibonacci 50.0% Level")
    if at_ema_50:
        confluences.append("EMA 50 Trend Level")

    location_grade = "GRADE C"
    base_location_score = 0
    confluence_bonus = 0

    # GRADE S EVALUATION (Order Block + Key Confluences)
    if in_order_block and is_major_sr and at_fib_618:
        location_grade = "GRADE S (HOLY GRAIL)"
        base_location_score = 50
        confluence_bonus = 20  # Holy Grail bonus
    elif in_order_block and (at_fib_618 or at_ema_200 or is_major_sr):
        location_grade = "GRADE S (SUPER)"
        base_location_score = 45
        confluence_bonus = 10
    elif in_order_block:
        location_grade = "GRADE A"
        base_location_score = 40

    # GRADE A EVALUATION (Major S/R or Fib 61.8% or EMA 200)
    elif is_major_sr and at_fib_618:
        location_grade = "GRADE A"
        base_location_score = 35
        confluence_bonus = 10
    elif is_major_sr or at_fib_618 or at_ema_200:
        location_grade = "GRADE A"
        base_location_score = 30

    # GRADE B EVALUATION (Minor S/R or Fib 50% or EMA 50)
    elif is_minor_sr or at_fib_500 or at_ema_50:
        location_grade = "GRADE B"
        base_location_score = 20
    elif at_fib_382 or at_ema_21:
        location_grade = "GRADE B"
        base_location_score = 10
    else:
        location_grade = "GRADE C"
        base_location_score = 0

    # Additional Confluence Bonus checks
    grade_a_elements = sum([1 for x in [in_order_block, at_fib_618, at_ema_200, is_major_sr] if x])
    if grade_a_elements >= 3 and confluence_bonus < 15:
        confluence_bonus = 15
    elif grade_a_elements >= 2 and confluence_bonus < 10:
        confluence_bonus = 10

    total_location_score = min(50, base_location_score + confluence_bonus)

    return {
        "location_grade": location_grade,
        "base_score": base_location_score,
        "confluence_bonus": confluence_bonus,
        "total_score": total_location_score,
        "in_order_block": in_order_block,
        "is_major_sr": is_major_sr,
        "at_fib_618": at_fib_618,
        "at_ema_200": at_ema_200,
        "confluences": confluences,
        "desc": f"{location_grade} ({', '.join(confluences) if confluences else 'No key level confluence'})"
    }


def is_active_trading_session(dt: Optional[datetime] = None) -> Tuple[bool, str]:
    """
    24/7 Crypto Futures Global Session Tracker:
    Crypto markets trade 24/7/365. This tracks global liquidity flows without blocking trades:
    - Asian Liquidity Window: 00:00 - 08:00 UTC (Tokyo / Singapore / Hong Kong)
    - European Liquidity Window: 08:00 - 14:00 UTC (London / Frankfurt)
    - US Liquidity Window: 14:00 - 21:00 UTC (New York / Chicago Peak)
    - Pacific / Global Handover: 21:00 - 00:00 UTC
    All sessions are active for crypto futures trading.
    """
    now = dt or datetime.utcnow()
    hour = now.hour

    if 13 <= hour < 17:
        return True, "US & European High-Volume Overlap (Peak Crypto Liquidity 🔥)"
    elif 8 <= hour < 14:
        return True, "European Session (High Crypto Volume ✅)"
    elif 14 <= hour < 22:
        return True, "US Session (High Crypto Volume ✅)"
    elif 0 <= hour < 8:
        return True, "Asian Session (Active Asia-Pacific Crypto Liquidity 🌏)"
    else:
        return True, "Global Handover Window (24/7 Crypto Market Active 🌐)"
