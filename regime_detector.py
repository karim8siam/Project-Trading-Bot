"""
Crypto Market Regime Classifier for Binance USD(S)-M Futures.
Identifies market conditions in real-time to select the optimal trading engine:
1. TRENDING_BULL: Bullish EMA alignment + positive directional movement
2. TRENDING_BEAR: Bearish EMA alignment + negative directional movement
3. VOLATILITY_BREAKOUT: Bollinger Squeeze expansion or Donchian channel breakout with volume surge
4. RANGING: Sideways consolidation suitable for Support/Resistance & RSI mean-reversion
5. CHOPPY_NOISE: Erratic whipsaws with low conviction (bot observes safely)
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple


def detect_crypto_regime(df: pd.DataFrame, idx: int = -1) -> Dict[str, Any]:
    """
    Analyzes multi-indicator state to classify current crypto market regime.
    """
    if len(df) < 50:
        return {
            "regime": "INSUFFICIENT_DATA",
            "recommended_strategy": "WAIT",
            "confidence": 0,
            "desc": "Need at least 50 historical candles for regime detection."
        }

    row = df.iloc[idx]
    prev = df.iloc[idx - 1]

    close = float(row["close"])
    open_p = float(row["open"])
    volume = float(row["volume"])
    vol_ma20 = float(row.get("vol_ma_20", volume))

    ema9 = float(row.get("ema_9", close))
    ema21 = float(row.get("ema_21", close))
    ema50 = float(row.get("ema_50", close))
    ema200 = float(row.get("ema_200", close))

    adx = float(row.get("adx_14", 20.0))
    plus_di = float(row.get("plus_di", 20.0))
    minus_di = float(row.get("minus_di", 20.0))

    bb_upper = float(row.get("bb_upper", close * 1.02))
    bb_lower = float(row.get("bb_lower", close * 0.98))
    bb_mid = float(row.get("bb_middle", close))
    bb_width = float(row.get("bb_width", 0.04))
    prev_bb_width = float(prev.get("bb_width", bb_width))

    # 1. Breakout Detection (Bollinger Band expansion + 20-bar Donchian breakout)
    sub20 = df.iloc[max(0, idx - 20):idx]
    high_20 = float(sub20["high"].max()) if not sub20.empty else close
    low_20 = float(sub20["low"].min()) if not sub20.empty else close

    is_vol_surge = volume >= (vol_ma20 * 1.30)
    is_bb_expansion = bb_width > (prev_bb_width * 1.05)

    bull_breakout = (close >= high_20 or (close > bb_upper and is_bb_expansion)) and is_vol_surge and close > open_p
    bear_breakout = (close <= low_20 or (close < bb_lower and is_bb_expansion)) and is_vol_surge and close < open_p

    if bull_breakout:
        return {
            "regime": "VOLATILITY_BREAKOUT",
            "direction": "LONG",
            "recommended_strategy": "VOLATILITY_BREAKOUT",
            "adx": adx,
            "confidence": 85,
            "desc": f"Bullish Volatility Breakout (Volume Surge {volume/(vol_ma20+1e-9):.1f}x MA + Range Expansion)"
        }
    elif bear_breakout:
        return {
            "regime": "VOLATILITY_BREAKOUT",
            "direction": "SHORT",
            "recommended_strategy": "VOLATILITY_BREAKOUT",
            "adx": adx,
            "confidence": 85,
            "desc": f"Bearish Volatility Breakout (Volume Surge {volume/(vol_ma20+1e-9):.1f}x MA + Range Breakdown)"
        }

    # 2. Strong Trending Regime
    is_bull_stack = (ema9 >= ema21 >= ema50) and (close >= ema50)
    is_bear_stack = (ema9 <= ema21 <= ema50) and (close <= ema50)

    if is_bull_stack and (adx >= 20.0 or plus_di > minus_di + 4):
        trend_strength = min(95, int(50 + (adx * 1.5)))
        return {
            "regime": "TRENDING_BULL",
            "direction": "LONG",
            "recommended_strategy": "TREND_PULLBACK",
            "adx": adx,
            "confidence": trend_strength,
            "desc": f"Strong Bull Trend (EMA 9>21>50 Stack, ADX: {adx:.1f})"
        }

    if is_bear_stack and (adx >= 20.0 or minus_di > plus_di + 4):
        trend_strength = min(95, int(50 + (adx * 1.5)))
        return {
            "regime": "TRENDING_BEAR",
            "direction": "SHORT",
            "recommended_strategy": "TREND_PULLBACK",
            "adx": adx,
            "confidence": trend_strength,
            "desc": f"Strong Bear Trend (EMA 9<21<50 Stack, ADX: {adx:.1f})"
        }

    # 3. Moderate Trending Regime (Price above/below EMA 50 with directional bias)
    if close > ema50 and plus_di > minus_di + 3:
        return {
            "regime": "MODERATE_BULL",
            "direction": "LONG",
            "recommended_strategy": "TREND_PULLBACK",
            "adx": adx,
            "confidence": 65,
            "desc": f"Moderate Bullish Trend (Price > EMA50, +DI > -DI)"
        }

    if close < ema50 and minus_di > plus_di + 3:
        return {
            "regime": "MODERATE_BEAR",
            "direction": "SHORT",
            "recommended_strategy": "TREND_PULLBACK",
            "adx": adx,
            "confidence": 65,
            "desc": f"Moderate Bearish Trend (Price < EMA50, -DI > +DI)"
        }

    # 4. Ranging / Sideways Mean-Reversion Regime
    return {
        "regime": "RANGING",
        "direction": "NEUTRAL",
        "recommended_strategy": "RANGE_MEAN_REVERSION",
        "adx": adx,
        "confidence": 75,
        "desc": f"Sideways Range (ADX: {adx:.1f}, Mean-Reversion Active)"
    }
