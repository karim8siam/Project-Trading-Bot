"""
Trend Pullback Strategy Engine for Crypto Futures.
Enters high-probability continuation moves when price pulls back into key dynamic support/resistance (EMA 21/50, Order Blocks, Fibonacci levels) during strong trends.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, Tuple
from candlestick_patterns import detect_candlestick_patterns


def evaluate_trend_pullback(df: pd.DataFrame, idx: int = -1) -> Dict[str, Any]:
    """
    Evaluates Trend Pullback setup on a 0-100 point scale.
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
    vol_ma20 = float(row.get("vol_ma_20", volume))

    ema9 = float(row.get("ema_9", close))
    ema21 = float(row.get("ema_21", close))
    ema50 = float(row.get("ema_50", close))
    ema200 = float(row.get("ema_200", close))

    rsi = float(row.get("rsi_14", 50.0))
    macd = float(row.get("macd", 0.0))
    macd_sig = float(row.get("macd_signal", 0.0))
    macd_hist = float(row.get("macd_hist", 0.0))
    prev_macd_hist = float(prev.get("macd_hist", 0.0))
    atr = float(row.get("atr_14", close * 0.01))

    # Check Bullish Trend Pullback
    bull_score = 0
    bull_breakdown = {}

    # 1. Trend Alignment (30 pts)
    if close > ema50 and ema9 > ema21 > ema50:
        bull_score += 30
        bull_breakdown["trend"] = "Perfect EMA 9>21>50 Stack (+30)"
    elif close > ema50 and ema21 > ema50:
        bull_score += 22
        bull_breakdown["trend"] = "EMA 21>50 Bullish Alignment (+22)"
    elif close > ema50:
        bull_score += 15
        bull_breakdown["trend"] = "Price above EMA 50 (+15)"

    # 2. Pullback Quality to Dynamic EMA (25 pts)
    dist_to_ema21 = abs(close - ema21) / close
    dist_to_ema50 = abs(close - ema50) / close
    if dist_to_ema21 <= 0.008:
        bull_score += 25
        bull_breakdown["pullback"] = f"Clean Pullback to EMA 21 ({dist_to_ema21*100:.2f}% dist) (+25)"
    elif dist_to_ema50 <= 0.012:
        bull_score += 20
        bull_breakdown["pullback"] = f"Deep Pullback to EMA 50 ({dist_to_ema50*100:.2f}% dist) (+20)"
    elif close > ema21:
        bull_score += 12
        bull_breakdown["pullback"] = "Riding above EMA 21 (+12)"

    # 3. Momentum & RSI (25 pts)
    if 38.0 <= rsi <= 55.0:
        bull_score += 15
        bull_breakdown["rsi"] = f"RSI Sweet Spot for Dip Buying ({rsi:.1f}) (+15)"
    elif 30.0 <= rsi < 38.0:
        bull_score += 12
        bull_breakdown["rsi"] = f"Oversold Bounce Zone ({rsi:.1f}) (+12)"
    elif 55.0 < rsi <= 65.0:
        bull_score += 8
        bull_breakdown["rsi"] = f"Moderate Momentum ({rsi:.1f}) (+8)"

    if macd_hist > prev_macd_hist or macd > macd_sig:
        bull_score += 10
        bull_breakdown["macd"] = "MACD Momentum Rising (+10)"

    # 4. Candlestick Reversal Confirmation (20 pts)
    is_green = close > open_p
    lower_wick = min(open_p, close) - low_p
    body = abs(close - open_p)
    pat = detect_candlestick_patterns(df, idx=idx).get("primary_pattern")

    if pat and pat.get("direction") in ("LONG", "NEUTRAL"):
        bull_score += 20
        bull_breakdown["candle"] = f"Pattern: {pat.get('name')} (+20)"
    elif is_green and lower_wick > body * 0.8:
        bull_score += 15
        bull_breakdown["candle"] = "Hammer / Long Lower Wick Rejection (+15)"
    elif is_green:
        bull_score += 10
        bull_breakdown["candle"] = "Bullish Green Close (+10)"

    # Check Bearish Trend Pullback
    bear_score = 0
    bear_breakdown = {}

    # 1. Trend Alignment (30 pts)
    if close < ema50 and ema9 < ema21 < ema50:
        bear_score += 30
        bear_breakdown["trend"] = "Perfect Bearish EMA 9<21<50 Stack (+30)"
    elif close < ema50 and ema21 < ema50:
        bear_score += 22
        bear_breakdown["trend"] = "EMA 21<50 Bearish Alignment (+22)"
    elif close < ema50:
        bear_score += 15
        bear_breakdown["trend"] = "Price below EMA 50 (+15)"

    # 2. Pullback Quality to Dynamic EMA (25 pts)
    if dist_to_ema21 <= 0.008:
        bear_score += 25
        bear_breakdown["pullback"] = f"Clean Pullback to EMA 21 ({dist_to_ema21*100:.2f}% dist) (+25)"
    elif dist_to_ema50 <= 0.012:
        bear_score += 20
        bear_breakdown["pullback"] = f"Deep Pullback to EMA 50 ({dist_to_ema50*100:.2f}% dist) (+20)"
    elif close < ema21:
        bear_score += 12
        bear_breakdown["pullback"] = "Riding below EMA 21 (+12)"

    # 3. Momentum & RSI (25 pts)
    if 45.0 <= rsi <= 62.0:
        bear_score += 15
        bear_breakdown["rsi"] = f"RSI Sweet Spot for Bearish Pullback ({rsi:.1f}) (+15)"
    elif 62.0 < rsi <= 70.0:
        bear_score += 12
        bear_breakdown["rsi"] = f"Overbought Rejection Zone ({rsi:.1f}) (+12)"
    elif 35.0 <= rsi < 45.0:
        bear_score += 8
        bear_breakdown["rsi"] = f"Bearish Drift ({rsi:.1f}) (+8)"

    if macd_hist < prev_macd_hist or macd < macd_sig:
        bear_score += 10
        bear_breakdown["macd"] = "MACD Momentum Dropping (+10)"

    # 4. Candlestick Reversal Confirmation (20 pts)
    is_red = close < open_p
    upper_wick = high_p - max(open_p, close)
    if pat and pat.get("direction") in ("SHORT", "NEUTRAL"):
        bear_score += 20
        bear_breakdown["candle"] = f"Pattern: {pat.get('name')} (+20)"
    elif is_red and upper_wick > body * 0.8:
        bear_score += 15
        bear_breakdown["candle"] = "Shooting Star / Upper Wick Rejection (+15)"
    elif is_red:
        bear_score += 10
        bear_breakdown["candle"] = "Bearish Red Close (+10)"

    # Output decision (Threshold: >= 55 points)
    if bull_score >= 55 and bull_score > bear_score:
        sl = max(low_p - (atr * 1.2), close - (atr * 2.0))
        sl_dist = close - sl
        tp1 = close + (sl_dist * 1.5)
        tp2 = close + (sl_dist * 3.0)
        return {
            "has_signal": True,
            "direction": "LONG",
            "strategy": "TREND_PULLBACK",
            "score": min(100, bull_score),
            "entry_price": close,
            "stop_loss": round(sl, 4),
            "take_profit_1": round(tp1, 4),
            "take_profit_2": round(tp2, 4),
            "atr": atr,
            "breakdown": bull_breakdown,
            "desc": f"Trend Pullback LONG (Score: {bull_score}/100) | {bull_breakdown.get('trend')} & {bull_breakdown.get('pullback')}"
        }

    if bear_score >= 55 and bear_score > bull_score:
        sl = min(high_p + (atr * 1.2), close + (atr * 2.0))
        sl_dist = sl - close
        tp1 = close - (sl_dist * 1.5)
        tp2 = close - (sl_dist * 3.0)
        return {
            "has_signal": True,
            "direction": "SHORT",
            "strategy": "TREND_PULLBACK",
            "score": min(100, bear_score),
            "entry_price": close,
            "stop_loss": round(sl, 4),
            "take_profit_1": round(tp1, 4),
            "take_profit_2": round(tp2, 4),
            "atr": atr,
            "breakdown": bear_breakdown,
            "desc": f"Trend Pullback SHORT (Score: {bear_score}/100) | {bear_breakdown.get('trend')} & {bear_breakdown.get('pullback')}"
        }

    return {
        "has_signal": False,
        "strategy": "TREND_PULLBACK",
        "score": max(bull_score, bear_score),
        "desc": f"Neutral Trend (Bull: {bull_score}/100, Bear: {bear_score}/100, Threshold: 55)"
    }
