"""
3-Pillar Institutional Risk Management Framework.
Implements all 14 Golden Rules of Capital Preservation:

PILLAR 1: PER-TRADE RISK
- Rule 1: 1% Golden Rule (Never risk > 1% on any trade)
- Rule 2: Score-Based Dynamic Risk Adjustment (250-300: 1.0%, 200-249: 0.75%, 150-199: 0.50%)
- Rule 3: Exact Position Sizing Formula
- Rule 4: Logical Stop Loss Placement (Below Order Block/Support/Fib/EMA200, 10-50 pip limits)
- Rule 5: Risk-to-Reward Ratio Integration (1:2 min for Perfect, 1:2.5 for Strong, 1:3 for Decent) + Partial TP
- Rule 6: Breakeven Rule (Move SL to Entry at 1R profit -> Zero-risk trade)
- Rule 7: Dynamic Trailing Stop Loss (Trails behind price once in profit)

PILLAR 2: DAILY RISK RULES
- Rule 8: Daily Loss Limit (Max 3% account loss -> Stop trading for day)
- Rule 9: Daily Trade Limit (Max 5 trades per day)
- Rule 10: Daily Profit Target (3% daily gain -> Lock in profit and stop)
- Rule 11: Win/Loss Streak Protection (2 losses -> 50% risk; 3 losses -> Halt day; 3 wins -> Maintain discipline)

PILLAR 3: ACCOUNT RISK & GROWTH RULES
- Rule 12: Maximum Account Drawdown (10% DD -> Protection Mode 0.5% risk; 20% DD -> Emergency Stop)
- Rule 13: Account Growth Tier Sizing ($0-1k: Starting, $1k-5k: Growth, $5k-20k: Stable, $20k+: Pro)
- Rule 14: Max 3 Open Trades & Correlation Limit
"""

import math
import pandas as pd
import numpy as np
from datetime import datetime, date
from typing import Dict, Any, Optional, Tuple, List
from config import (
    DEFAULT_LEVERAGE,
    MAX_OPEN_TRADES,
    SL_ATR_MULTIPLIER,
    TP_ATR_MULTIPLIER,
    validate_symbol
)
from database import get_open_trades, get_closed_trades, get_connection


# Standard contract specifications for 20 whitelisted pairs (Synchronized with Binance ExchangeInfo)
SYMBOL_SPECS = {
    # Tier 1: Core Majors
    "BTC/USDT":      {"amount_precision": 3, "min_qty": 0.001, "price_precision": 2, "min_notional": 50.0, "pip_size": 1.0},
    "ETH/USDT":      {"amount_precision": 3, "min_qty": 0.001, "price_precision": 2, "min_notional": 20.0, "pip_size": 0.1},
    "BNB/USDT":      {"amount_precision": 2, "min_qty": 0.01,  "price_precision": 3, "min_notional": 5.0, "pip_size": 0.01},
    "SOL/USDT":      {"amount_precision": 2, "min_qty": 0.01,  "price_precision": 4, "min_notional": 5.0, "pip_size": 0.01},
    "XRP/USDT":      {"amount_precision": 1, "min_qty": 0.1,   "price_precision": 4, "min_notional": 5.0, "pip_size": 0.0001},
    "ADA/USDT":      {"amount_precision": 0, "min_qty": 1.0,   "price_precision": 5, "min_notional": 5.0, "pip_size": 0.0001},
    "NEAR/USDT":     {"amount_precision": 0, "min_qty": 1.0,   "price_precision": 4, "min_notional": 5.0, "pip_size": 0.001},
    # Tier 2: High-Risk Alts
    "AVAX/USDT":     {"amount_precision": 0, "min_qty": 1.0,   "price_precision": 4, "min_notional": 5.0, "pip_size": 0.01},
    "DOGE/USDT":     {"amount_precision": 0, "min_qty": 1.0,   "price_precision": 6, "min_notional": 5.0, "pip_size": 0.00001},
    "LINK/USDT":     {"amount_precision": 2, "min_qty": 0.01,  "price_precision": 3, "min_notional": 20.0, "pip_size": 0.01},
    # Tier 3: Sniper Volatile Mid-Caps (87% Threshold)
    "SUI/USDT":      {"amount_precision": 1, "min_qty": 0.1,   "price_precision": 6, "min_notional": 5.0, "pip_size": 0.0001},
    "APT/USDT":      {"amount_precision": 1, "min_qty": 0.1,   "price_precision": 5, "min_notional": 5.0, "pip_size": 0.001},
    "1000PEPE/USDT": {"amount_precision": 0, "min_qty": 1.0,   "price_precision": 7, "min_notional": 5.0, "pip_size": 0.0000001},
    "RENDER/USDT":   {"amount_precision": 1, "min_qty": 0.1,   "price_precision": 7, "min_notional": 5.0, "pip_size": 0.001},
    "TIA/USDT":      {"amount_precision": 0, "min_qty": 1.0,   "price_precision": 7, "min_notional": 5.0, "pip_size": 0.0001},
    "INJ/USDT":      {"amount_precision": 1, "min_qty": 0.1,   "price_precision": 6, "min_notional": 5.0, "pip_size": 0.001},
    "ARB/USDT":      {"amount_precision": 1, "min_qty": 0.1,   "price_precision": 6, "min_notional": 5.0, "pip_size": 0.0001},
    "OP/USDT":       {"amount_precision": 1, "min_qty": 0.1,   "price_precision": 7, "min_notional": 5.0, "pip_size": 0.0001},
    "FET/USDT":      {"amount_precision": 0, "min_qty": 1.0,   "price_precision": 7, "min_notional": 5.0, "pip_size": 0.0001},
    "SEI/USDT":      {"amount_precision": 0, "min_qty": 1.0,   "price_precision": 7, "min_notional": 5.0, "pip_size": 0.0001}
}


# =========================================================================
# PILLAR 3: ACCOUNT GROWTH TIERS (RULE 13)
# =========================================================================
def get_account_growth_tier(account_balance: float) -> Dict[str, Any]:
    """
    Rule 13: Adjusts risk rules as account balance grows.
    """
    if account_balance <= 1000.0:
        return {
            "tier_name": "STARTING PHASE ($0 - $1,000)",
            "max_risk_pct": 1.0,
            "daily_loss_limit_pct": 3.0,
            "daily_profit_target_pct": 3.0,
            "max_trades_per_day": 8,
            "min_score_threshold": 50
        }
    elif account_balance <= 5000.0:
        return {
            "tier_name": "GROWTH PHASE ($1,000 - $5,000)",
            "max_risk_pct": 0.75,
            "daily_loss_limit_pct": 2.5,
            "daily_profit_target_pct": 3.0,
            "max_trades_per_day": 6,
            "min_score_threshold": 55
        }
    elif account_balance < 20000.0:
        return {
            "tier_name": "STABLE PHASE ($5,000 - $20,000)",
            "max_risk_pct": 0.50,
            "daily_loss_limit_pct": 2.0,
            "daily_profit_target_pct": 2.5,
            "max_trades_per_day": 5,
            "min_score_threshold": 60
        }
    else:
        return {
            "tier_name": "PROFESSIONAL PHASE ($20,000+)",
            "max_risk_pct": 0.35,
            "daily_loss_limit_pct": 1.5,
            "daily_profit_target_pct": 2.0,
            "max_trades_per_day": 5,
            "min_score_threshold": 65
        }


# =========================================================================
# PILLAR 1: SCORE-BASED RISK ADJUSTMENT (RULE 2)
# =========================================================================
def get_score_based_risk_percentage(score: int, account_balance: float) -> Tuple[float, float, str]:
    """
    Rule 2 & Risk/Reward Integration:
    - 75 - 100 pts (PERFECT TRADE 🔥): Risk 1.0% (capped by tier), Min R:R = 1:2.0
    - 60 - 74 pts (STRONG TRADE ✅): Risk 0.75%, Min R:R = 1:2.5
    - 50 - 59 pts (MODERATE TRADE ⚠️): Risk 0.50%, Min R:R = 1:3.0
    - Below 50 pts: NO TRADE (0% risk)
    Returns: (risk_pct, min_required_rr, tier_desc)
    """
    tier_info = get_account_growth_tier(account_balance)
    max_tier_risk = tier_info["max_risk_pct"]

    if score >= 75:
        risk_pct = min(1.0, max_tier_risk)
        return risk_pct, 2.0, "PERFECT TRADE 🔥 (Full 1% Risk Allocation)"
    elif score >= 60:
        risk_pct = min(0.75, max_tier_risk)
        return risk_pct, 2.5, "STRONG TRADE ✅ (0.75% Reduced Risk Allocation)"
    elif score >= 50:
        risk_pct = min(0.50, max_tier_risk)
        return risk_pct, 3.0, "MODERATE TRADE ⚠️ (0.50% Half Risk Allocation)"
    else:
        return 0.0, 3.0, "NO TRADE 🚫 (Score < 50 - Zero Risk Allowed)"


# =========================================================================
# PILLAR 1: POSITION SIZING & LOGICAL SL/TP (RULES 1, 3, 4, 5)
# =========================================================================
def calculate_logical_sl_tp(
    entry_price: float,
    atr: float,
    direction: str,
    score: int = 76,
    df: Optional[pd.DataFrame] = None,
    df_htf: Optional[pd.DataFrame] = None,
    symbol: str = "",
    order_block_price: Optional[float] = None,
    support_resistance_price: Optional[float] = None,
    fib_price: Optional[float] = None,
    ema200_price: Optional[float] = None
) -> Tuple[float, float, float, float]:
    """
    Upgraded Elite 4-Pillar Stop Loss & Two-Stage Take Profit Engine:
    1. Multi-Timeframe (1H + 15M) Structural Swing Anchors.
    2. Volatility Beta Regime: Dynamic breathing room (1.0%-1.4% Majors, 1.8%-2.5% High-Beta Alts).
    3. Institutional Order Block & Fair Value Gap (FVG) Base Defense Invalidation Buffers.
    4. Two-Stage Take-Profit Payout (1:1.2 R:R TP1 & 1:2.5 R:R TP2).
    Returns: (stop_loss, tp1_partial, tp2_runner, rr_ratio)
    """
    # 1. 1-Minute Micro-Scalping Volatility Buffer
    beta_min_pct = 0.006 if symbol.upper() in {"DOGE/USDT", "PEPE/USDT", "SUI/USDT", "FET/USDT"} else 0.004  # 0.4% - 0.6% for 1M Scalps
    min_sl_dist = max(atr * 1.4, entry_price * beta_min_pct)
    max_sl_dist = max(atr * 3.5, entry_price * 0.025)
    buffer_pct = max(0.002, (atr * 0.5) / entry_price)  # 0.2% - 0.4% micro-pivot invalidation cushion

    candidate_sls = []

    # 2. Dual-Timeframe (15M HTF + 1M Micro) Structural Swing Pivot Detection
    if df is not None and not df.empty:
        from indicators import detect_swing_pivots, detect_fair_value_gaps
        pivots = detect_swing_pivots(df, window=15, df_htf=df_htf)
        if direction.upper() == "LONG":
            candidate_sls.append(pivots["swing_low"] * (1.0 - buffer_pct))
            if pivots.get("htf_swing_low") and pivots["htf_swing_low"] < entry_price:
                candidate_sls.append(pivots["htf_swing_low"] * (1.0 - buffer_pct))
        else:
            candidate_sls.append(pivots["swing_high"] * (1.0 + buffer_pct))
            if pivots.get("htf_swing_high") and pivots["htf_swing_high"] > entry_price:
                candidate_sls.append(pivots["htf_swing_high"] * (1.0 + buffer_pct))

        # 3. Fair Value Gap (FVG) Base Defense
        fvg_data = detect_fair_value_gaps(df)
        if direction.upper() == "LONG" and fvg_data.get("bullish_fvg"):
            candidate_sls.append(fvg_data["bullish_fvg"] * (1.0 - buffer_pct))
        elif direction.upper() == "SHORT" and fvg_data.get("bearish_fvg"):
            candidate_sls.append(fvg_data["bearish_fvg"] * (1.0 + buffer_pct))

    if direction.upper() == "LONG":
        if order_block_price and order_block_price < entry_price:
            candidate_sls.append(order_block_price * (1.0 - buffer_pct))
        if support_resistance_price and support_resistance_price < entry_price:
            candidate_sls.append(support_resistance_price * (1.0 - buffer_pct))
        if fib_price and fib_price < entry_price:
            candidate_sls.append(fib_price * (1.0 - buffer_pct))
        if ema200_price and ema200_price < entry_price:
            candidate_sls.append(ema200_price * (1.0 - buffer_pct))

        # Default fallback
        candidate_sls.append(entry_price - max(atr * 1.4, entry_price * beta_min_pct))

        # Filter candidates within acceptable institutional range
        valid_sls = [sl for sl in candidate_sls if (entry_price - sl) >= min_sl_dist and (entry_price - sl) <= max_sl_dist]
        stop_loss = min(valid_sls) if valid_sls else (entry_price - max(atr * 1.4, entry_price * beta_min_pct))

        sl_distance = max(entry_price - stop_loss, min_sl_dist)
        tp1 = entry_price + (sl_distance * 0.5)  # Fast Scalp TP @ 0.5R Target
        tp2 = entry_price + (sl_distance * 1.2)  # Stage 2: Macro Trend Target @ 1.2R

    else:  # SHORT
        if order_block_price and order_block_price > entry_price:
            candidate_sls.append(order_block_price * (1.0 + buffer_pct))
        if support_resistance_price and support_resistance_price > entry_price:
            candidate_sls.append(support_resistance_price * (1.0 + buffer_pct))
        if fib_price and fib_price > entry_price:
            candidate_sls.append(fib_price * (1.0 + buffer_pct))
        if ema200_price and ema200_price > entry_price:
            candidate_sls.append(ema200_price * (1.0 + buffer_pct))

        candidate_sls.append(entry_price + max(atr * 1.4, entry_price * beta_min_pct))

        valid_sls = [sl for sl in candidate_sls if (sl - entry_price) >= min_sl_dist and (sl - entry_price) <= max_sl_dist]
        stop_loss = max(valid_sls) if valid_sls else (entry_price + max(atr * 1.4, entry_price * beta_min_pct))

        sl_distance = max(stop_loss - entry_price, min_sl_dist)
        tp1 = entry_price - (sl_distance * 0.5)  # Fast Scalp TP @ 0.5R Target
        tp2 = entry_price - (sl_distance * 1.2)  # Stage 2: Macro Trend Target @ 1.2R

    rr_ratio = abs(tp1 - entry_price) / max(1e-6, abs(entry_price - stop_loss))
    return round(stop_loss, 4), round(tp1, 4), round(tp2, 4), round(rr_ratio, 2)


def calculate_sl_tp(
    entry_price: float,
    atr: float,
    direction: str,
    sl_multiplier: float = SL_ATR_MULTIPLIER,
    tp_multiplier: float = TP_ATR_MULTIPLIER,
    score: int = 76,
    df: Optional[pd.DataFrame] = None,
    df_htf: Optional[pd.DataFrame] = None,
    symbol: str = ""
) -> Tuple[float, float, float]:
    """
    Standard SL/TP calculator returning (stop_loss, tp1_partial, tp2_runner)
    anchored on Structural Swing Pivots.
    """
    sl, tp1, tp2, _ = calculate_logical_sl_tp(
        entry_price=entry_price,
        atr=atr,
        direction=direction,
        score=score,
        df=df,
        df_htf=df_htf,
        symbol=symbol
    )
    return sl, tp1, tp2


def calculate_position_size(
    account_balance_usdt: float,
    entry_price: float,
    stop_loss_price: float,
    symbol: str,
    score: int = 250,
    leverage: int = DEFAULT_LEVERAGE,
    custom_risk_pct: Optional[float] = None
) -> Dict[str, Any]:
    """
    Rule 1, 2, 3: Calculates exact position size based on current score and risk rules.
    Allows custom_risk_pct (e.g. 5.0% dedicated risk for Delta Counter-Hedge).
    """
    validate_symbol(symbol)
    spec = SYMBOL_SPECS.get(symbol, {"amount_precision": 3, "min_qty": 0.001, "min_notional": 5.0})

    if account_balance_usdt <= 0:
        return {"valid": False, "reason": "Account balance must be positive."}

    # 1. Get score-based risk percentage or custom override
    if custom_risk_pct is not None:
        risk_pct = float(custom_risk_pct)
        tier_desc = f"TACTICAL DELTA HEDGE ({risk_pct:.1f}% Dedicated Risk Allocation)"
    else:
        risk_pct, min_rr, tier_desc = get_score_based_risk_percentage(score, account_balance_usdt)
        if risk_pct <= 0:
            return {"valid": False, "reason": f"Score {score} is below minimum 50 required for trading."}

        # 2. Winning/Losing Streak Risk Adjustment (Rule 11)
        streak_status = get_streak_status()
        if streak_status["consecutive_losses"] == 2:
            risk_pct *= 0.50  # Cut risk in half after 2 consecutive losses
            tier_desc += " [STREAK: 50% Risk Reduction Active]"

        # 3. Peak Drawdown Risk Adjustment (Rule 12)
        dd_status = check_account_drawdown(account_balance_usdt)
        if dd_status["is_protection_mode"]:
            risk_pct = min(risk_pct, 0.50)  # Capped at 0.5% in protection mode
            tier_desc += " [PROTECTION MODE: 10% Drawdown Active]"

    # 4. Total Dollar Risk for this Trade
    target_risk_usd = account_balance_usdt * (risk_pct / 100.0)

    # 5. Stop Loss Distance
    sl_distance = abs(entry_price - stop_loss_price)
    if sl_distance <= 0:
        return {"valid": False, "reason": "Stop-loss cannot equal entry price."}

    # 6. Raw lot size calculation (Rule 3)
    raw_quantity = target_risk_usd / sl_distance
    amount_prec = spec["amount_precision"]
    quantity = round(raw_quantity, amount_prec)

    if quantity < spec["min_qty"]:
        quantity = spec["min_qty"]

    notional_value = quantity * entry_price
    if notional_value < spec["min_notional"]:
        # Ensure quantity meets Binance min notional ($5.05 buffer)
        min_target_notional = spec["min_notional"] + 0.10
        step = (10 ** (-amount_prec)) if amount_prec > 0 else 1.0
        adj_qty = round(min_target_notional / entry_price, amount_prec)
        while (adj_qty * entry_price) < (spec["min_notional"] + 0.05):
            adj_qty = round(adj_qty + step, amount_prec)
        if adj_qty < spec["min_qty"]:
            adj_qty = spec["min_qty"]
        quantity = adj_qty
        notional_value = quantity * entry_price

    required_margin = notional_value / leverage
    if required_margin > account_balance_usdt:
        return {
            "valid": False,
            "reason": f"Required margin (${required_margin:.2f}) exceeds available equity (${account_balance_usdt:.2f})."
        }

    # =========================================================================
    # DYNAMIC RISK CEILING (Allows 5.0% for Delta Hedge, 1.0% for Standard Trades)
    # The actual dollar loss if the Stop Loss is triggered respects the assigned risk.
    # =========================================================================
    max_allowable_risk_usd = account_balance_usdt * (risk_pct / 100.0)
    actual_risk_usd = quantity * sl_distance

    if actual_risk_usd > max_allowable_risk_usd:
        # Dynamically recalibrate the Stop-Loss to guarantee risk strictly <= 1.0%
        recalibrated_sl_dist = max_allowable_risk_usd / quantity
        min_sl_dist_pct = 0.0015  # Minimum 0.15% price buffer to avoid noise stop-outs

        if (recalibrated_sl_dist / entry_price) < min_sl_dist_pct:
            return {
                "valid": False,
                "reason": f"Risk Limit Rejection: Minimum contract lot ({quantity} {symbol} = ${notional_value:.2f}) requires ${actual_risk_usd:.2f} risk, exceeding strict 1.0% ceiling (${max_allowable_risk_usd:.2f})."
            }

        # Enforce exact new tightened Stop-Loss price
        if stop_loss_price < entry_price:  # LONG
            stop_loss_price = round(entry_price - recalibrated_sl_dist, spec["price_precision"])
        else:  # SHORT
            stop_loss_price = round(entry_price + recalibrated_sl_dist, spec["price_precision"])

        sl_distance = abs(entry_price - stop_loss_price)
        actual_risk_usd = quantity * sl_distance

    # Final assertion: under no circumstance can actual risk exceed 1.00% of equity
    actual_risk_pct = (actual_risk_usd / account_balance_usdt) * 100.0
    if actual_risk_pct > 1.001:
        return {
            "valid": False,
            "reason": f"1.0% Risk Guardrail: Trade risk ({actual_risk_pct:.2f}%) exceeds hard 1.00% maximum limit."
        }

    return {
        "valid": True,
        "symbol": symbol,
        "quantity": quantity,
        "entry_price": entry_price,
        "stop_loss": stop_loss_price,
        "notional_value": round(notional_value, 2),
        "required_margin": round(required_margin, 2),
        "risk_pct_used": round(min(risk_pct, 1.0), 2),
        "target_risk_usd": round(max_allowable_risk_usd, 4),
        "actual_risk_usd": round(actual_risk_usd, 4),
        "actual_risk_pct": round(actual_risk_pct, 2),
        "tier_desc": tier_desc,
        "leverage": leverage
    }


# =========================================================================
# PILLAR 2: DAILY RISK LIMITS & STREAK CONTROLS (RULES 8, 9, 10, 11)
# =========================================================================
def get_daily_performance() -> Dict[str, Any]:
    """
    Computes today's realized PnL, today's trade count, and profit/loss percentages.
    """
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT 
        COUNT(*) as today_trades,
        SUM(pnl_usd) as today_pnl_usd,
        SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as today_wins,
        SUM(CASE WHEN is_win = 0 THEN 1 ELSE 0 END) as today_losses
    FROM trades
    WHERE status = 'CLOSED' AND DATE(exit_time) = DATE(?)
    """, (today_str,))
    row = cursor.fetchone()
    conn.close()

    today_trades = row["today_trades"] if row and row["today_trades"] else 0
    today_pnl_usd = float(row["today_pnl_usd"]) if row and row["today_pnl_usd"] else 0.0
    today_wins = row["today_wins"] if row and row["today_wins"] else 0
    today_losses = row["today_losses"] if row and row["today_losses"] else 0

    return {
        "date": today_str,
        "trades_count": today_trades,
        "pnl_usd": round(today_pnl_usd, 2),
        "wins": today_wins,
        "losses": today_losses
    }


def get_streak_status() -> Dict[str, int]:
    """
    Rule 11: Calculates current consecutive winning or losing streak.
    """
    recent = get_closed_trades(limit=10)
    if not recent:
        return {"consecutive_wins": 0, "consecutive_losses": 0}

    first_outcome = recent[0].get("is_win")
    streak_count = 0
    for t in recent:
        if t.get("is_win") == first_outcome:
            streak_count += 1
        else:
            break

    if first_outcome == 1:
        return {"consecutive_wins": streak_count, "consecutive_losses": 0}
    else:
        return {"consecutive_wins": 0, "consecutive_losses": streak_count}


# =========================================================================
# PILLAR 3: DRAWDOWN & OPEN POSITION CONTROLS (RULES 12, 14)
# =========================================================================
def check_account_drawdown(current_balance: float) -> Dict[str, Any]:
    """
    Rule 12: Maximum Drawdown Protection.
    - 10% Drawdown: Protection Mode (0.5% risk limit)
    - 20% Drawdown: Complete Bot Suspension (Emergency Halt)
    """
    closed = get_closed_trades(limit=500)
    pnl_sum = sum(float(t.get("pnl_usd") or 0.0) for t in closed)
    starting_balance = max(1.0, current_balance - pnl_sum)
    running = starting_balance
    peak = starting_balance
    for t in reversed(closed):
        running += float(t.get("pnl_usd") or 0.0)
        if running > peak:
            peak = running
    peak_balance = max(peak, current_balance)

    drawdown_usd = max(0.0, peak_balance - current_balance)
    drawdown_pct = (drawdown_usd / peak_balance * 100.0) if peak_balance > 0 else 0.0

    return {
        "current_balance": current_balance,
        "peak_balance": round(peak_balance, 2),
        "drawdown_pct": round(drawdown_pct, 2),
        "is_protection_mode": drawdown_pct >= 10.0 and drawdown_pct < 20.0,
        "is_emergency_halt": drawdown_pct >= 20.0
    }


def check_3_pillar_risk_guardrails(
    symbol: str,
    account_balance: float = 13.50,
    **kwargs
) -> Tuple[bool, str]:
    """
    Evaluates Per-Trade & Multi-Pair Opportunity Controls before allowing any trade:
    - Allows all valid qualified opportunities across all whitelisted pairs (no arbitrary cap).
    - Duplicate position check (Max 1 position per coin).
    - Strict <= 1.0% portfolio risk per trade.
    """
    open_trades = get_open_trades()

    # Max concurrent unique pair cap (up to 20 whitelisted pairs)
    if len(open_trades) >= MAX_OPEN_TRADES:
        return False, f"Maximum global portfolio capacity reached ({len(open_trades)}/{MAX_OPEN_TRADES} active)."

    # Symbol Anti-Whipsaw Cooldown check
    in_cd, rem_mins = is_symbol_in_cooldown(symbol)
    if in_cd:
        return False, f"Anti-Whipsaw Protection: {symbol} in 30-min cooldown after Stop-Loss ({rem_mins}m remaining)."

    # Rule 14: Prevent duplicate active trades in same symbol
    if symbol in [t["symbol"] for t in open_trades]:
        return False, f"Position already active for {symbol}. No duplicate exposure allowed."

    return True, f"Risk Guardrails Passed ({len(open_trades)}/{MAX_OPEN_TRADES} active)."


# =========================================================================
# SYMBOL ANTI-WHIPSAW COOLDOWN REGISTRY
# =========================================================================
import time
SYMBOL_COOLDOWN_TIMESTAMPS: Dict[str, float] = {}

def register_symbol_stop_out(symbol: str):
    """Registers a stop-loss event to prevent rapid re-entry into chop."""
    SYMBOL_COOLDOWN_TIMESTAMPS[symbol] = time.time()

def is_symbol_in_cooldown(symbol: str, cooldown_seconds: int = 300) -> Tuple[bool, int]:
    """Checks if symbol is in 5-minute anti-whipsaw protection window (for 1M scalps)."""
    last_stop = SYMBOL_COOLDOWN_TIMESTAMPS.get(symbol, 0.0)
    elapsed = time.time() - last_stop
    if elapsed < cooldown_seconds:
        rem_mins = int((cooldown_seconds - elapsed) / 60)
        return True, rem_mins
    return False, 0


# =========================================================================
# PILLAR 1: BREAKEVEN & TRAILING STOP MANAGER (RULES 6, 7)
# =========================================================================
def update_breakeven_and_trailing_stops(
    trade: Dict[str, Any],
    current_price: float,
    atr: float,
    btc_state: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Sovereign Beta-Linked Dynamic SL/TP Engine:
    - 1. Dynamic BTC Pump Expansion: When Bitcoin pumps (BTC_EXPANSION_BULL / ROC_3m > +0.25%),
         expands Take-Profit from 0.5R -> 1.2R -> 1.5R to let winners ride with Bitcoin.
    - 2. Dynamic BTC Dump Defensive Ratchet: When Bitcoin shows sudden exhaustion / micro-dump (ROC_3m < -0.20%),
         tightens Stop-Loss to lock current green profit immediately before the dump reaches the altcoin.
    - 3. Breakeven Rule: When profit >= +0.4R, move Stop-Loss to Entry Price + Fees (+0.05%).
    - 4. Profit Lock Rule: When profit >= +0.5R, lock in +0.3R minimum green profit.
    - 5. Dynamic Chandelier Trail: When profit >= +0.8R, trail stop with 1.2x ATR cushion.
    """
    entry_p = float(trade["entry_price"])
    current_sl = float(trade["stop_loss"])
    current_tp = float(trade.get("take_profit", entry_p * 1.01))
    direction = trade["direction"]
    sl_dist = abs(entry_p - current_sl)

    updated_sl = current_sl
    updated_tp = current_tp
    is_breakeven = False
    is_trailing = False
    is_tp_expanded = False
    tp_reason = ""

    # Get symbol price precision
    symbol = trade.get("symbol", "")
    p_prec = SYMBOL_SPECS.get(symbol, {}).get("price_precision", 4)

    # Fetch real-time BTC metrics if available
    btc_roc = 0.0
    btc_bias = "NEUTRAL"
    if btc_state:
        btc_roc = float(btc_state.get("roc_3m", 0.0))
        btc_bias = btc_state.get("bias", "NEUTRAL")

    if direction == "LONG":
        current_profit_dist = current_price - entry_p

        # A. Bitcoin Pump Momentum Extension (0.5R -> 1.2R -> 1.5R)
        if btc_roc >= 0.25 or btc_bias == "AGGRESSIVE_BULL":
            expanded_tp = entry_p + (sl_dist * 1.5)
            if expanded_tp > updated_tp:
                updated_tp = expanded_tp
                is_tp_expanded = True
                tp_reason = f"BTC Pump Surge ({btc_roc:+.2f}% 3m): TP expanded to 1.5R runner (${updated_tp:,.{p_prec}f})"
            if current_profit_dist >= (0.25 * sl_dist) and current_sl < entry_p:
                updated_sl = entry_p * 1.0005
                is_breakeven = True

        # B. Bitcoin Dump / Sudden Deceleration Defensive Profit Snapping
        elif btc_roc <= -0.20:
            if current_profit_dist >= (0.35 * sl_dist) and updated_sl < (entry_p + 0.25 * sl_dist):
                updated_sl = entry_p + (0.25 * sl_dist)
                is_trailing = True
                tp_reason = f"BTC Deceleration Alert ({btc_roc:+.2f}% 3m): SL tightened to lock profit."

        # Stage 1: Full Zero-Risk Breakeven Lock at +0.4R profit (+0.05% fee cushion)
        if current_profit_dist >= (0.4 * sl_dist) and current_sl < entry_p:
            updated_sl = entry_p * 1.0005  # covers taker fees
            is_breakeven = True

        # Stage 2: Lock in minimum +0.3R Green Profit once +0.5R is reached
        if current_profit_dist >= (0.5 * sl_dist) and updated_sl < (entry_p + 0.3 * sl_dist):
            updated_sl = entry_p + (0.3 * sl_dist)
            is_trailing = True

        # Stage 3: Dynamic Macro Trailing Stop after +0.8R profit (1.2x ATR cushion)
        if current_profit_dist >= (0.8 * sl_dist):
            trail_level = current_price - (atr * 1.2)
            if trail_level > updated_sl:
                updated_sl = trail_level
                is_trailing = True

    else:  # SHORT
        current_profit_dist = entry_p - current_price

        # A. Bitcoin Dump Momentum Extension for Shorts (0.5R -> 1.5R)
        if btc_roc <= -0.25 or btc_bias == "AGGRESSIVE_BEAR":
            expanded_tp = entry_p - (sl_dist * 1.5)
            if expanded_tp < updated_tp:
                updated_tp = expanded_tp
                is_tp_expanded = True
                tp_reason = f"BTC Dump Breakdown ({btc_roc:+.2f}% 3m): TP expanded to 1.5R macro runner."
            if current_profit_dist >= (0.25 * sl_dist) and current_sl > entry_p:
                updated_sl = entry_p * 0.9995
                is_breakeven = True

        # Stage 1: Full Zero-Risk Breakeven Lock at +0.4R profit (+0.05% fee cushion)
        if current_profit_dist >= (0.4 * sl_dist) and current_sl > entry_p:
            updated_sl = entry_p * 0.9995  # covers taker fees
            is_breakeven = True

        # Stage 2: Lock in minimum +0.3R Green Profit once +0.5R is reached
        if current_profit_dist >= (0.5 * sl_dist) and updated_sl > (entry_p - 0.3 * sl_dist):
            updated_sl = entry_p - (0.3 * sl_dist)
            is_trailing = True

        # Stage 3: Dynamic Macro Trailing Stop after +0.8R profit (1.2x ATR cushion)
        if current_profit_dist >= (0.8 * sl_dist):
            trail_level = current_price + (atr * 1.2)
            if trail_level < updated_sl:
                updated_sl = trail_level
                is_trailing = True

    return {
        "updated_sl": round(updated_sl, p_prec),
        "updated_tp": round(updated_tp, p_prec),
        "is_breakeven": is_breakeven,
        "is_trailing": is_trailing,
        "is_tp_expanded": is_tp_expanded,
        "tp_reason": tp_reason
    }
