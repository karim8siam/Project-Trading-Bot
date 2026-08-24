"""
Range Mean-Reversion Strategy Engine for Crypto Futures.
Executes high-probability swing reversals during sideways/consolidating crypto markets:
- Bollinger Band Boundary Bounces (Lower/Upper band touches)
- RSI Extreme Reversals (< 35 Oversold / > 65 Overbought)
- Rejection Wick Confirmation
- Targets: Mean Reversion to 20 SMA (TP1) and Opposite Band (TP2)
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from candlestick_patterns import detect_candlestick_patterns


def evaluate_range_mean_reversion(df: pd.DataFrame, idx: int = -1) -> Dict[str, Any]:
    """
    Evaluates Range Mean-Reversion setup on a 0-100 point scale.
    """
    if len(df) < 50:
        return {"has_signal": False, "score": 0, "reason": "Insufficient candles"}

    row = df.iloc[idx]
    prev = df.iloc[idx - 1]

    close = float(row["close"])
    open_p = float(row["open"])
    high_p = float(row["high"])
    low_p = float(row["low"])
    volume = float(row["volume"])

    bb_upper = float(row.get("bb_upper", close * 1.02))
    bb_lower = float(row.get("bb_lower", close * 0.98))
    bb_mid = float(row.get("bb_middle", close))
    bb_width = float(row.get("bb_width", 0.04))

    rsi = float(row.get("rsi_14", 50.0))
    atr = float(row.get("atr_14", close * 0.01))
    pat = detect_candlestick_patterns(df, idx=idx).get("primary_pattern")

    # 1. Bullish Mean Reversion (Buy Lower Band / Oversold Bounce)
    bull_score = 0
    bull_breakdown = {}

    # Proximity to lower band (35 pts)
    dist_to_lower = (close - bb_lower) / (close + 1e-9)
    if low_p <= bb_lower or dist_to_lower <= 0.004:
        bull_score += 35
        bull_breakdown["band"] = f"Tested Lower Bollinger Band (${bb_lower:,.2f}) (+35)"
    elif dist_to_lower <= 0.008:
        bull_score += 22
        bull_breakdown["band"] = f"Near Lower Bollinger Band (+22)"

    # RSI Oversold Recovery (30 pts)
    if rsi <= 32.0:
        bull_score += 30
        bull_breakdown["rsi"] = f"Extreme Oversold RSI ({rsi:.1f}) (+30)"
    elif 32.0 < rsi <= 40.0:
        bull_score += 22
        bull_breakdown["rsi"] = f"Oversold Recovery RSI ({rsi:.1f}) (+22)"
    elif 40.0 < rsi <= 48.0:
        bull_score += 12
        bull_breakdown["rsi"] = f"Neutral-Low RSI ({rsi:.1f}) (+12)"

    # Reversal Wick / Candlestick (25 pts)
    is_green = close >= open_p
    lower_wick = min(open_p, close) - low_p
    body = abs(close - open_p)
    if pat and pat.get("direction") in ("LONG", "NEUTRAL"):
        bull_score += 25
        bull_breakdown["candle"] = f"Reversal Pattern: {pat.get('name')} (+25)"
    elif is_green and lower_wick > body * 0.7:
        bull_score += 20
        bull_breakdown["candle"] = "Strong Rejection Wick (+20)"
    elif is_green:
        bull_score += 12
        bull_breakdown["candle"] = "Bullish Close (+12)"

    # Bollinger Band Width Quality (10 pts)
    if bb_width <= 0.06:
        bull_score += 10
        bull_breakdown["range_quality"] = "Well-defined sideways range (+10)"

    # 2. Bearish Mean Reversion (Sell Upper Band / Overbought Rejection)
    bear_score = 0
    bear_breakdown = {}

    # Proximity to upper band (35 pts)
    dist_to_upper = (bb_upper - close) / (close + 1e-9)
    if high_p >= bb_upper or dist_to_upper <= 0.004:
        bear_score += 35
        bear_breakdown["band"] = f"Tested Upper Bollinger Band (${bb_upper:,.2f}) (+35)"
    elif dist_to_upper <= 0.008:
        bear_score += 22
        bear_breakdown["band"] = f"Near Upper Bollinger Band (+22)"

    # RSI Overbought Rejection (30 pts)
    if rsi >= 68.0:
        bear_score += 30
        bear_breakdown["rsi"] = f"Extreme Overbought RSI ({rsi:.1f}) (+30)"
    elif 60.0 <= rsi < 68.0:
        bear_score += 22
        bear_breakdown["rsi"] = f"Overbought Rejection RSI ({rsi:.1f}) (+22)"
    elif 52.0 <= rsi < 60.0:
        bear_score += 12
        bear_breakdown["rsi"] = f"Neutral-High RSI ({rsi:.1f}) (+12)"

    # Reversal Wick / Candlestick (25 pts)
    is_red = close <= open_p
    upper_wick = high_p - max(open_p, close)
    if pat and pat.get("direction") in ("SHORT", "NEUTRAL"):
        bear_score += 25
        bear_breakdown["candle"] = f"Reversal Pattern: {pat.get('name')} (+25)"
    elif is_red and upper_wick > body * 0.7:
        bear_score += 20
        bear_breakdown["candle"] = "Strong Upper Rejection Wick (+20)"
    elif is_red:
        bear_score += 12
        bear_breakdown["candle"] = "Bearish Close (+12)"

    if bb_width <= 0.06:
        bear_score += 10
        bear_breakdown["range_quality"] = "Well-defined sideways range (+10)"

    # Threshold: >= 55 points
    if bull_score >= 55 and bull_score > bear_score:
        sl = max(low_p - (atr * 1.0), close - (atr * 1.6))
        tp1 = bb_mid if bb_mid > close else close + (atr * 1.5)
        tp2 = bb_upper if bb_upper > tp1 else close + (atr * 2.8)
        return {
            "has_signal": True,
            "direction": "LONG",
            "strategy": "RANGE_MEAN_REVERSION",
            "score": min(100, bull_score),
            "entry_price": close,
            "stop_loss": round(sl, 4),
            "take_profit_1": round(tp1, 4),
            "take_profit_2": round(tp2, 4),
            "atr": atr,
            "breakdown": bull_breakdown,
            "desc": f"Range Mean-Reversion LONG ({bull_score}/100 pts) | {bull_breakdown.get('band')} | {bull_breakdown.get('rsi')}"
        }

    if bear_score >= 55 and bear_score > bull_score:
        sl = min(high_p + (atr * 1.0), close + (atr * 1.6))
        tp1 = bb_mid if bb_mid < close else close - (atr * 1.5)
        tp2 = bb_lower if bb_lower < tp1 else close - (atr * 2.8)
        return {
            "has_signal": True,
            "direction": "SHORT",
            "strategy": "RANGE_MEAN_REVERSION",
            "score": min(100, bear_score),
            "entry_price": close,
            "stop_loss": round(sl, 4),
            "take_profit_1": round(tp1, 4),
            "take_profit_2": round(tp2, 4),
            "atr": atr,
            "breakdown": bear_breakdown,
            "desc": f"Range Mean-Reversion SHORT ({bear_score}/100 pts) | {bear_breakdown.get('band')} | {bear_breakdown.get('rsi')}"
        }

    return {
        "has_signal": False,
        "strategy": "RANGE_MEAN_REVERSION",
        "score": max(bull_score, bear_score),
        "desc": f"Range Neutral (Bull: {bull_score}/100, Bear: {bear_score}/100)"
    }
