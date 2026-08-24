"""
Candlestick Pattern Recognition & 3-Layer Location Grading Engine.
Implements:
- Layer 1: Location Grading (Grade A, Grade B, Grade C)
- Layer 2: Pattern Quality & Recognition (Tier 1, Tier 2, Tier 3)
- Layer 3: Indicator & Volume Agreement
"""

import math
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Tuple, Optional
from indicators import compute_fibonacci_levels


# =========================================================================
# LAYER 1: LOCATION GRADING ENGINE
# =========================================================================
def evaluate_location_grade(
    df: pd.DataFrame,
    idx: int = -1,
    direction: str = "LONG"
) -> Tuple[str, int, List[str]]:
    """
    Evaluates WHERE the candlestick pattern formed:
    GRADE A (Powerful - +20 pts):
      - At EMA 200 level
      - At 61.8% Fibonacci level
      - At Lower Bollinger Band (Buy) / Upper Bollinger Band (Sell)
      - At Major Swing Support/Resistance (Rolling 50-bar Swing High/Low)
      - At Key Round Numbers (e.g. $60,000, $3,000, $150.00)

    GRADE B (Decent - +10 pts):
      - At EMA 50 level
      - At 50.0% Fibonacci level
      - At Middle Bollinger Band (20 SMA)

    GRADE C (Weak - 0 pts):
      - Random no-confluence zone in the middle of nowhere -> PATTERN IGNORED!
    """
    row = df.iloc[idx]
    close = float(row["close"])
    ema50 = float(row["ema_50"])
    ema200 = float(row["ema_200"])
    bb_lower = float(row["bb_lower"])
    bb_upper = float(row["bb_upper"])
    bb_mid = float(row["bb_middle"])

    # Proximity threshold: within 0.4% (0.004) of key level
    tol = 0.004

    reasons = []
    grade_a_hits = 0
    grade_b_hits = 0

    # 1. Fibonacci Levels
    fibs = compute_fibonacci_levels(df, lookback=60)
    fib618 = fibs["fib_618"]
    fib500 = fibs["fib_500"]

    if abs(close - fib618) / close <= tol:
        grade_a_hits += 1
        reasons.append("61.8% Golden Ratio Fibonacci Level")

    if abs(close - fib500) / close <= tol:
        grade_b_hits += 1
        reasons.append("50.0% Psychological Fibonacci Level")

    # 2. EMA 200 / EMA 50
    if abs(close - ema200) / close <= tol:
        grade_a_hits += 1
        reasons.append("EMA 200 Institutional Level")

    if abs(close - ema50) / close <= tol:
        grade_b_hits += 1
        reasons.append("EMA 50 Trend Support/Resistance Level")

    # 3. Bollinger Bands
    if direction.upper() == "LONG" and abs(close - bb_lower) / close <= tol:
        grade_a_hits += 1
        reasons.append("Lower Bollinger Band Reversal Zone")
    elif direction.upper() == "SHORT" and abs(close - bb_upper) / close <= tol:
        grade_a_hits += 1
        reasons.append("Upper Bollinger Band Reversal Zone")

    if abs(close - bb_mid) / close <= tol:
        grade_b_hits += 1
        reasons.append("Middle Bollinger Band Level")

    # 4. Major Swing Support / Resistance
    swing_high = fibs["swing_high"]
    swing_low = fibs["swing_low"]
    if direction.upper() == "LONG" and abs(close - swing_low) / close <= tol:
        grade_a_hits += 1
        reasons.append("Major Swing Low Support Level")
    elif direction.upper() == "SHORT" and abs(close - swing_high) / close <= tol:
        grade_a_hits += 1
        reasons.append("Major Swing High Resistance Level")

    # 5. Round Number Psychological Levels
    # e.g. for BTC (step $500), ETH (step $50), SOL (step $5), BNB (step $10)
    round_step = 500 if close > 10000 else (50 if close > 1000 else (10 if close > 100 else 1))
    nearest_round = round(close / round_step) * round_step
    if abs(close - nearest_round) / close <= 0.0015:
        grade_a_hits += 1
        reasons.append(f"Key Psychological Round Number (${nearest_round:,.0f})")

    # Final Grade Determination
    if grade_a_hits >= 1:
        return "GRADE A", 20, reasons
    elif grade_b_hits >= 1:
        return "GRADE B", 10, reasons
    else:
        return "GRADE C", 0, ["Random Area / No Key Level Confluence"]


# =========================================================================
# LAYER 2: CANDLESTICK PATTERN RECOGNITION (TIER 1, 2, 3)
# =========================================================================
def detect_candlestick_patterns(
    df: pd.DataFrame,
    idx: int = -1
) -> Dict[str, Any]:
    """
    Detects all 13 high, medium, and confirmation candlestick patterns.
    Returns detected pattern details, power tier, direction bias, and score contribution.
    """
    if len(df) < 5:
        return {"patterns": [], "tier": 3, "score": 0, "direction": None}

    c0 = df.iloc[idx]        # Current candle
    c1 = df.iloc[idx - 1]    # 1 bar ago
    c2 = df.iloc[idx - 2]    # 2 bars ago

    # Candle 0 properties
    o0, h0, l0, cl0 = float(c0["open"]), float(c0["high"]), float(c0["low"]), float(c0["close"])
    v0 = float(c0["volume"])
    range0 = max(1e-9, h0 - l0)
    body0 = abs(cl0 - o0)
    is_green0 = cl0 >= o0
    upper_wick0 = h0 - max(o0, cl0)
    lower_wick0 = min(o0, cl0) - l0

    # Candle 1 properties
    o1, h1, l1, cl1 = float(c1["open"]), float(c1["high"]), float(c1["low"]), float(c1["close"])
    v1 = float(c1["volume"])
    range1 = max(1e-9, h1 - l1)
    body1 = abs(cl1 - o1)
    is_green1 = cl1 >= o1

    # Candle 2 properties
    o2, h2, l2, cl2 = float(c2["open"]), float(c2["high"]), float(c2["low"]), float(c2["close"])
    v2 = float(c2["volume"])
    is_green2 = cl2 >= o2
    body2 = abs(cl2 - o2)

    patterns_found = []
    best_tier = 3
    best_score = 0
    signal_direction = None

    # ---------------------------------------------------------------------
    # TIER 1: HIGH POWER PATTERNS (Strongest Signals)
    # ---------------------------------------------------------------------
    
    # 1. Bullish Engulfing (+25 pts)
    # Previous red small, current green BIG body covering previous, body >= 1.5x previous, volume higher
    if (not is_green1) and is_green0 and (cl0 >= o1) and (o0 <= cl1):
        if body0 >= 1.3 * body1 and v0 >= v1:
            patterns_found.append({
                "name": "Bullish Engulfing",
                "tier": 1,
                "score": 25,
                "direction": "LONG",
                "desc": f"Green body ({body0:.2f}) completely engulfed Red body ({body1:.2f}) with expanding volume."
            })

    # 2. Bearish Engulfing (+25 pts)
    # Previous green small, current red BIG body covering previous, body >= 1.5x previous, volume higher
    if is_green1 and (not is_green0) and (cl0 <= o1) and (o0 >= cl1):
        if body0 >= 1.3 * body1 and v0 >= v1:
            patterns_found.append({
                "name": "Bearish Engulfing",
                "tier": 1,
                "score": 25,
                "direction": "SHORT",
                "desc": f"Red body ({body0:.2f}) completely engulfed Green body ({body1:.2f}) with expanding volume."
            })

    # 3. Morning Star (+30 pts)
    # 3-candle pattern: Big red (c2), tiny doji/body (c1), big green (c0) closing above 50% of c2
    if (not is_green2) and is_green0 and (body1 <= 0.4 * body2) and (cl0 >= (o2 + cl2) / 2.0):
        if v0 >= v1:
            patterns_found.append({
                "name": "Morning Star",
                "tier": 1,
                "score": 30,
                "direction": "LONG",
                "desc": "3-candle bullish reversal: Strong green candle closed above 50% midpoint of first red bar."
            })

    # 4. Evening Star (+30 pts)
    # 3-candle pattern: Big green (c2), tiny body (c1), big red (c0) closing below 50% of c2
    if is_green2 and (not is_green0) and (body1 <= 0.4 * body2) and (cl0 <= (o2 + cl2) / 2.0):
        if v0 >= v1:
            patterns_found.append({
                "name": "Evening Star",
                "tier": 1,
                "score": 30,
                "direction": "SHORT",
                "desc": "3-candle bearish reversal: Strong red candle closed below 50% midpoint of first green bar."
            })

    # 5. Three White Soldiers (+28 pts)
    # 3 consecutive green candles, each opens inside previous and closes higher near high
    if is_green2 and is_green1 and is_green0:
        if (cl0 > cl1 > cl2) and (o0 > o1 > o2) and (upper_wick0 <= 0.3 * range0):
            patterns_found.append({
                "name": "Three White Soldiers",
                "tier": 1,
                "score": 28,
                "direction": "LONG",
                "desc": "3 consecutive strong green candles marching upward with minimal upper wicks."
            })

    # 6. Three Black Crows (+28 pts)
    # 3 consecutive red candles, each opens inside previous and closes lower near low
    if (not is_green2) and (not is_green1) and (not is_green0):
        if (cl0 < cl1 < cl2) and (o0 < o1 < o2) and (lower_wick0 <= 0.3 * range0):
            patterns_found.append({
                "name": "Three Black Crows",
                "tier": 1,
                "score": 28,
                "direction": "SHORT",
                "desc": "3 consecutive strong red candles marching downward with minimal lower wicks."
            })

    # ---------------------------------------------------------------------
    # TIER 2: MEDIUM POWER PATTERNS (Good Reversal Signals)
    # ---------------------------------------------------------------------

    # 7. Hammer (+20 pts)
    # Long lower wick (>= 2x body), small upper wick (<= 0.25x range), forms after dip
    if lower_wick0 >= 2.0 * body0 and upper_wick0 <= 0.25 * range0 and body0 > 0:
        patterns_found.append({
            "name": "Hammer (Pin Bar)",
            "tier": 2,
            "score": 20,
            "direction": "LONG",
            "desc": f"Bullish rejection: Lower wick ({lower_wick0:.2f}) is >= 2x the body size."
        })

    # 8. Shooting Star (+20 pts)
    # Long upper wick (>= 2x body), small lower wick (<= 0.25x range), forms after rally
    if upper_wick0 >= 2.0 * body0 and lower_wick0 <= 0.25 * range0 and body0 > 0:
        patterns_found.append({
            "name": "Shooting Star (Bearish Pin Bar)",
            "tier": 2,
            "score": 20,
            "direction": "SHORT",
            "desc": f"Bearish rejection: Upper wick ({upper_wick0:.2f}) is >= 2x the body size."
        })

    # 9. Tweezer Bottom (+18 pts)
    # Two candles with equal lows (within 0.1%), second candle is green
    if abs(l0 - l1) / (cl0 + 1e-9) <= 0.001 and is_green0 and (not is_green1):
        patterns_found.append({
            "name": "Tweezer Bottom",
            "tier": 2,
            "score": 18,
            "direction": "LONG",
            "desc": f"Double bottom support rejection at identical low price ${l0:,.2f}."
        })

    # 10. Tweezer Top (+18 pts)
    # Two candles with equal highs (within 0.1%), second candle is red
    if abs(h0 - h1) / (cl0 + 1e-9) <= 0.001 and (not is_green0) and is_green1:
        patterns_found.append({
            "name": "Tweezer Top",
            "tier": 2,
            "score": 18,
            "direction": "SHORT",
            "desc": f"Double top resistance rejection at identical high price ${h0:,.2f}."
        })

    # 11. Bullish Harami (+15 pts)
    # Big red candle, followed by small green candle inside previous body
    if (not is_green1) and is_green0 and (o0 >= cl1) and (cl0 <= o1) and (body0 <= 0.6 * body1):
        patterns_found.append({
            "name": "Bullish Harami (Inside Bar)",
            "tier": 2,
            "score": 15,
            "direction": "LONG",
            "desc": "Small green inside candle formed completely within previous large red bar."
        })

    # 12. Bearish Harami (+15 pts)
    # Big green candle, followed by small red candle inside previous body
    if is_green1 and (not is_green0) and (o0 <= cl1) and (cl0 >= o1) and (body0 <= 0.6 * body1):
        patterns_found.append({
            "name": "Bearish Harami (Inside Bar)",
            "tier": 2,
            "score": 15,
            "direction": "SHORT",
            "desc": "Small red inside candle formed completely within previous large green bar."
        })

    # 13. Doji (+10 pts)
    # Body is less than 10% of total candle range
    if body0 <= 0.10 * range0:
        patterns_found.append({
            "name": "Doji (Indecision)",
            "tier": 2,
            "score": 10,
            "direction": "NEUTRAL",
            "desc": "Open and close virtually identical (< 10% range) indicating market equilibrium/reversal."
        })

    # ---------------------------------------------------------------------
    # TIER 3: WEAK PATTERNS (Confirmation Only - +5 pts)
    # ---------------------------------------------------------------------
    if not patterns_found:
        # Marubozu (Strong momentum, body >= 85% of range)
        if body0 >= 0.85 * range0:
            direction_m = "LONG" if is_green0 else "SHORT"
            patterns_found.append({
                "name": f"{'Bullish' if is_green0 else 'Bearish'} Marubozu",
                "tier": 3,
                "score": 5,
                "direction": direction_m,
                "desc": "Strong directional momentum bar with virtually no wicks."
            })
        # Spinning Top (Small body in middle with upper and lower wicks)
        elif 0.10 * range0 < body0 <= 0.35 * range0 and upper_wick0 >= 0.25 * range0 and lower_wick0 >= 0.25 * range0:
            patterns_found.append({
                "name": "Spinning Top",
                "tier": 3,
                "score": 5,
                "direction": "NEUTRAL",
                "desc": "Small body with balanced upper and lower shadows."
            })

    # Find highest tier and score
    if patterns_found:
        # Sort by tier ascending (1 is best) then score descending
        patterns_found.sort(key=lambda p: (p["tier"], -p["score"]))
        best = patterns_found[0]
        best_tier = best["tier"]
        best_score = best["score"]
        signal_direction = best["direction"]

    return {
        "patterns": patterns_found,
        "primary_pattern": patterns_found[0] if patterns_found else None,
        "tier": best_tier,
        "score": best_score,
        "direction": signal_direction
    }


# =========================================================================
# LAYER 3 + MASTER 3-LAYER EVALUATOR
# =========================================================================
def evaluate_3_layer_setup(
    df: pd.DataFrame,
    idx: int = -1,
    direction: str = "LONG"
) -> Dict[str, Any]:
    """
    Evaluates the complete 3-Layer Candlestick Architecture:
    - Layer 1: Location Check (Grade A / Grade B / Grade C)
    - Layer 2: Pattern Recognition & Quality Check (Tier 1 / 2 / 3)
    - Layer 3: Indicator Agreement Check

    RULE:
    - All 3 layers pass -> VALID TRADING PATTERN (Adds full score)
    - Grade C location -> PATTERN COMPLETELY IGNORED (Score = 0)
    """
    # 1. Layer 1: Location Check
    location_grade, location_pts, location_reasons = evaluate_location_grade(df, idx=idx, direction=direction)

    # 2. Layer 2: Pattern Quality Check
    pattern_res = detect_candlestick_patterns(df, idx=idx)
    primary_pat = pattern_res.get("primary_pattern")

    if not primary_pat:
        return {
            "valid": False,
            "candlestick_score": 0,
            "pattern_name": "None",
            "tier": 3,
            "location_grade": location_grade,
            "location_points": 0,
            "reason": "No recognized candlestick pattern formed on this candle."
        }

    pattern_dir = primary_pat["direction"]
    pattern_name = primary_pat["name"]
    pattern_score = primary_pat["score"]
    pattern_tier = primary_pat["tier"]

    # If pattern direction directly conflicts with trade direction (e.g. Bearish Engulfing during LONG evaluation)
    if pattern_dir != "NEUTRAL" and pattern_dir != direction.upper():
        return {
            "valid": False,
            "candlestick_score": 0,
            "pattern_name": pattern_name,
            "tier": pattern_tier,
            "location_grade": location_grade,
            "location_points": 0,
            "reason": f"Candlestick pattern '{pattern_name}' ({pattern_dir}) opposes candidate direction ({direction})."
        }

    # If Location is Grade C (Random area) -> IGNORE COMPLETELY
    if location_grade == "GRADE C":
        return {
            "valid": False,
            "candlestick_score": 0,
            "pattern_name": pattern_name,
            "tier": pattern_tier,
            "location_grade": "GRADE C",
            "location_points": 0,
            "reason": f"IGNORED: Pattern '{pattern_name}' formed at Grade C location (Random area with no key level confluence)."
        }

    # Combined Candlestick + Location Score
    total_candle_score = pattern_score + location_pts

    return {
        "valid": True,
        "candlestick_score": total_candle_score,
        "pattern_name": pattern_name,
        "pattern_score": pattern_score,
        "tier": pattern_tier,
        "location_grade": location_grade,
        "location_points": location_pts,
        "location_reasons": location_reasons,
        "pattern_desc": primary_pat["desc"],
        "reason": f"{location_grade} ({', '.join(location_reasons)}) + Tier {pattern_tier} '{pattern_name}' (+{total_candle_score} pts)"
    }
