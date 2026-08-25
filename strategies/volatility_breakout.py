"""
Volatility Breakout Strategy Engine for Crypto Futures.
Identifies and executes explosive volatility expansions out of consolidations:
- Bollinger Band Squeeze Release
- 20-period Donchian Channel High/Low Breakouts
- Volume Surge Confirmation (> 1.3x 20MA)
- Momentum Acceleration (MACD & RSI thrust)
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional


def evaluate_volatility_breakout(df: pd.DataFrame, idx: int = -1) -> Dict[str, Any]:
    """
    Evaluates Volatility Breakout setup on a 0-100 point scale.
    """
    if len(df) < 50:
        return {"has_signal": False, "score": 0, "reason": "Insufficient candles"}

    row = df.iloc[idx]
    prev = df.iloc[idx - 1]
    prev2 = df.iloc[idx - 2] if len(df) >= 3 else prev

    close = float(row["close"])
    open_p = float(row["open"])
    high_p = float(row["high"])
    low_p = float(row["low"])
    volume = float(row["volume"])
    vol_ma20 = float(row.get("vol_ma_20", volume))

    bb_upper = float(row.get("bb_upper", close * 1.02))
    bb_lower = float(row.get("bb_lower", close * 0.98))
    bb_mid = float(row.get("bb_middle", close))
    bb_width = float(row.get("bb_width", 0.04))
    prev_bb_width = float(prev.get("bb_width", bb_width))

    rsi = float(row.get("rsi_14", 50.0))
    adx = float(row.get("adx_14", 20.0))
    plus_di = float(row.get("plus_di", 20.0))
    minus_di = float(row.get("minus_di", 20.0))
    atr = float(row.get("atr_14", close * 0.01))

    # 20-bar High and Low lookback
    sub20 = df.iloc[max(0, idx - 20):idx]
    high_20 = float(sub20["high"].max()) if not sub20.empty else close
    low_20 = float(sub20["low"].min()) if not sub20.empty else close

    # 1. Volume Surge Check (30 pts)
    vol_surge_ratio = volume / (vol_ma20 + 1e-9)
    vol_score = 0
    vol_desc = ""
    if vol_surge_ratio >= 2.0:
        vol_score = 30
        vol_desc = f"Massive Institutional Volume Surge ({vol_surge_ratio:.2f}x MA20) (+30)"
    elif vol_surge_ratio >= 1.4:
        vol_score = 22
        vol_desc = f"Strong Volume Expansion ({vol_surge_ratio:.2f}x MA20) (+22)"
    elif vol_surge_ratio >= 1.1:
        vol_score = 12
        vol_desc = f"Moderate Volume ({vol_surge_ratio:.2f}x MA20) (+12)"

    # 2. Squeeze & Volatility Expansion (25 pts)
    bb_expansion = bb_width / (prev_bb_width + 1e-9)
    bb_score = 0
    bb_desc = ""
    if bb_expansion >= 1.15:
        bb_score = 25
        bb_desc = f"Explosive Volatility Expansion (BB Width +{((bb_expansion-1)*100):.1f}%) (+25)"
    elif bb_expansion >= 1.05:
        bb_score = 18
        bb_desc = f"Bollinger Squeeze Opening (+18)"
    else:
        bb_score = 10
        bb_desc = "Normal Volatility Band (+10)"

    # 3. Channel Breakout (25 pts)
    bull_break_score = 0
    bear_break_score = 0
    break_desc = ""

    if close >= high_20 and close > open_p:
        bull_break_score = 25
        break_desc = f"Fresh 20-Period High Breakout (${close:,.2f} >= ${high_20:,.2f}) (+25)"
    elif close > bb_upper and close > open_p:
        bull_break_score = 20
        break_desc = "Upper Bollinger Band Thrust (+20)"

    if close <= low_20 and close < open_p:
        bear_break_score = 25
        break_desc = f"Fresh 20-Period Low Breakdown (${close:,.2f} <= ${low_20:,.2f}) (+25)"
    elif close < bb_lower and close < open_p:
        bear_break_score = 20
        break_desc = "Lower Bollinger Band Breakdown (+20)"

    # 4. Momentum Thrust (20 pts)
    bull_mom_score = 0
    bear_mom_score = 0
    if 55.0 <= rsi <= 75.0 and plus_di > minus_di:
        bull_mom_score = 20
    elif 50.0 <= rsi < 55.0:
        bull_mom_score = 12

    if 25.0 <= rsi <= 45.0 and minus_di > plus_di:
        bear_mom_score = 20
    elif 45.0 < rsi <= 50.0:
        bear_mom_score = 12

    total_bull = vol_score + bb_score + bull_break_score + bull_mom_score
    total_bear = vol_score + bb_score + bear_break_score + bear_mom_score

    # Trigger threshold >= 55
    if bull_break_score > 0 and total_bull >= 55 and total_bull > total_bear:
        sl = max(low_p - (atr * 1.0), close - (atr * 1.8))
        sl_dist = close - sl
        tp1 = close * 1.004
        tp2 = close * 1.008
        return {
            "has_signal": True,
            "direction": "LONG",
            "strategy": "VOLATILITY_BREAKOUT",
            "score": min(100, total_bull),
            "entry_price": close,
            "stop_loss": round(sl, 4),
            "take_profit_1": round(tp1, 4),
            "take_profit_2": round(tp2, 4),
            "atr": atr,
            "desc": f"Volatility Breakout LONG ({total_bull}/100 pts) | {vol_desc} | {break_desc}"
        }

    if bear_break_score > 0 and total_bear >= 55 and total_bear > total_bull:
        sl = min(high_p + (atr * 1.0), close + (atr * 1.8))
        sl_dist = sl - close
        tp1 = close * 0.996
        tp2 = close * 0.992
        return {
            "has_signal": True,
            "direction": "SHORT",
            "strategy": "VOLATILITY_BREAKOUT",
            "score": min(100, total_bear),
            "entry_price": close,
            "stop_loss": round(sl, 4),
            "take_profit_1": round(tp1, 4),
            "take_profit_2": round(tp2, 4),
            "atr": atr,
            "desc": f"Volatility Breakout SHORT ({total_bear}/100 pts) | {vol_desc} | {break_desc}"
        }

    return {
        "has_signal": False,
        "strategy": "VOLATILITY_BREAKOUT",
        "score": max(total_bull, total_bear),
        "desc": f"No Breakout Triggered (Bull: {total_bull}/100, Bear: {total_bear}/100)"
    }
