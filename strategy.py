"""
Adaptive Multi-Regime Strategy Router for Binance USD(S)-M Crypto Futures.
Combines:
1. Dynamic Market Regime Detection (Trend vs Breakout vs Range)
2. 3 Specialized Crypto Strategy Engines:
   - Engine A: Trend Pullback Engine (EMA 21/50, Order Blocks, Fibs)
   - Engine B: Volatility Breakout Engine (Bollinger Squeeze & Donchian Breakouts)
   - Engine C: Range Mean-Reversion Engine (RSI Extremes & BB Reversals)
3. Calibrated Machine Learning Dual-Ensemble (Random Forest + Gradient Boosting)
4. Merge Engine & Composite Decision Reasoner
5. 24/7 Crypto Market Liquidity Tracking
"""

import math
import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple, Optional

from config import validate_symbol, SL_ATR_MULTIPLIER, TP_ATR_MULTIPLIER
from indicators import add_all_indicators
from regime_detector import detect_crypto_regime
from strategies.trend_pullback import evaluate_trend_pullback
from strategies.volatility_breakout import evaluate_volatility_breakout
from strategies.range_mean_reversion import evaluate_range_mean_reversion
from feature_extractor import extract_features_at_index
from risk_manager import calculate_sl_tp
from ml_brain import ml_brain
from merge_engine import combine_rule_and_ml_scores, evaluate_claude_ai_final_decision
from database import get_closed_trades
from location_engine import is_active_trading_session
def calculate_bullish_master_score(df: pd.DataFrame, idx: int = -1) -> Tuple[int, Dict[str, Any], Optional[str]]:
    """Backward compatible helper evaluating bullish setup score."""
    if len(df) < 50:
        return 0, {}, "Insufficient history"
    row = df.iloc[idx]
    if float(row.get("close", 0)) < float(row.get("ema_200", 0)):
        return 0, {}, "VETO 1: Price below EMA 200"
    res = evaluate_trend_pullback(df, idx=idx)
    score = res.get("score", 0) if res.get("direction") == "LONG" else 0
    return score, res.get("breakdown", {}), None


def calculate_bearish_master_score(df: pd.DataFrame, idx: int = -1) -> Tuple[int, Dict[str, Any], Optional[str]]:
    """Backward compatible helper evaluating bearish setup score."""
    if len(df) < 50:
        return 0, {}, "Insufficient history"
    row = df.iloc[idx]
    if float(row.get("close", 0)) > float(row.get("ema_200", 0)):
        return 0, {}, "VETO 1: Price above EMA 200"
    res = evaluate_trend_pullback(df, idx=idx)
    score = res.get("score", 0) if res.get("direction") == "SHORT" else 0
    return score, res.get("breakdown", {}), None


def evaluate_master_crypto_strategy(
    df: pd.DataFrame,
    idx: int = -1
) -> Tuple[Optional[str], int, str, Dict[str, Any], str]:
    """
    Evaluates the current market across all 3 specialized engines based on detected regime.
    Returns: (direction, score_0_to_100, strategy_name, breakdown, description)
    """
    if len(df) < 50:
        return None, 0, "NONE", {}, "Insufficient candle history (< 50 candles)."

    # 1. Detect Regime
    regime_info = detect_crypto_regime(df, idx=idx)
    regime = regime_info.get("regime", "RANGING")
    rec_strat = regime_info.get("recommended_strategy", "TREND_PULLBACK")

    candidates = []

    # 2. Evaluate Strategy Engines
    res_pullback = evaluate_trend_pullback(df, idx=idx)
    if res_pullback.get("has_signal"):
        candidates.append(res_pullback)

    res_breakout = evaluate_volatility_breakout(df, idx=idx)
    if res_breakout.get("has_signal"):
        candidates.append(res_breakout)

    res_range = evaluate_range_mean_reversion(df, idx=idx)
    if res_range.get("has_signal"):
        candidates.append(res_range)

    # If candidates found, select the highest-scoring candidate aligned with regime
    if candidates:
        # Sort by score descending
        candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
        best = candidates[0]
        score = int(best.get("score", 0))
        direction = best.get("direction")
        strat_name = best.get("strategy")
        desc = best.get("desc", f"{strat_name} {direction}")
        breakdown = best.get("breakdown", {})
        breakdown["regime"] = regime
        breakdown["regime_desc"] = regime_info.get("desc", "")
        return direction, score, strat_name, breakdown, desc

    # If no strategy triggered a signal
    max_score = max(
        res_pullback.get("score", 0),
        res_breakout.get("score", 0),
        res_range.get("score", 0)
    )
    neutral_desc = f"Market in {regime} state ({regime_info.get('desc')}). Best score: {max_score}/100 (Threshold: 55)"
    return None, int(max_score), "NONE", {"regime": regime}, neutral_desc


def analyze_market(
    symbol: str,
    df_tf: pd.DataFrame,
    df_htf: Optional[pd.DataFrame] = None,
    df_micro: Optional[pd.DataFrame] = None
) -> Dict[str, Any]:
    """
    Complete Multi-Regime Crypto Market Analysis Pipeline:
    1. Feature & Indicator Preparation
    2. 24/7 Crypto Session State
    3. Multi-Regime Strategy Evaluation (0-100 score)
    4. Dual-Timeframe 15M/5M Price Action Confirmation
    5. ML Dual-Model Ensemble Probability Gate
    6. Adaptive Merge & Executive Decision
    """
    validate_symbol(symbol)

    if "ema_50" not in df_tf.columns:
        df_tf = add_all_indicators(df_tf)

    if df_htf is not None and not df_htf.empty and "ema_50" not in df_htf.columns:
        df_htf = add_all_indicators(df_htf)

    if df_micro is not None and not df_micro.empty and "ema_50" not in df_micro.columns:
        df_micro = add_all_indicators(df_micro)

    session_active, session_desc = is_active_trading_session()
    direction, score, strat_name, breakdown, desc = evaluate_master_crypto_strategy(df_tf, idx=-1)

    latest_row = df_tf.iloc[-1]
    current_price = float(latest_row["close"])
    current_atr = float(latest_row.get("atr_14", current_price * 0.01))

    if not direction or score < 50:
        return {
            "has_signal": False,
            "symbol": symbol,
            "current_price": current_price,
            "direction": None,
            "strategy": strat_name,
            "score": score,
            "session": session_desc,
            "reason": desc
        }

    # 1. Price Action Confirmation Trigger (15M or 5M Micro-Trigger)
    from indicators import detect_price_action_confirmation
    pa_conf_15m = detect_price_action_confirmation(df_tf, idx=-1)
    
    pa_conf_5m = None
    if df_micro is not None and not df_micro.empty:
        pa_conf_5m = detect_price_action_confirmation(df_micro, idx=-1)

    is_15m_confirmed = (direction == "LONG" and pa_conf_15m["is_confirmed_bullish"]) or \
                        (direction == "SHORT" and pa_conf_15m["is_confirmed_bearish"])

    is_5m_confirmed = False
    if pa_conf_5m:
        is_5m_confirmed = (direction == "LONG" and pa_conf_5m["is_confirmed_bullish"]) or \
                          (direction == "SHORT" and pa_conf_5m["is_confirmed_bearish"])

    is_candle_confirmed = is_15m_confirmed or is_5m_confirmed
    active_pattern = pa_conf_15m["pattern"] if is_15m_confirmed else (pa_conf_5m["pattern"] + " (5M)" if is_5m_confirmed else "NONE")

    # 2. 1H Macro Higher-Timeframe Trend Filter (Strict Directional Veto)
    if df_htf is not None and not df_htf.empty and len(df_htf) >= 30:
        htf_last = df_htf.iloc[-1]
        htf_close = float(htf_last["close"])
        htf_ema50 = float(htf_last.get("ema_50", htf_close))
        if direction == "LONG" and htf_close < htf_ema50 * 0.995:
            v_reason = f"Macro Veto: 1H Bearish Trend (Price ${htf_close:,.2f} < 1H EMA 50 ${htf_ema50:,.2f})"
            return {
                "has_signal": False,
                "symbol": symbol,
                "current_price": current_price,
                "direction": direction,
                "strategy": strat_name,
                "score": score,
                "stop_loss": current_price,
                "take_profit": current_price,
                "ml_approved": False,
                "ml_confidence": 0.0,
                "ml_reason": v_reason,
                "session": session_desc,
                "reason": v_reason
            }
        elif direction == "SHORT" and htf_close > htf_ema50 * 1.005:
            v_reason = f"Macro Veto: 1H Bullish Trend (Price ${htf_close:,.2f} > 1H EMA 50 ${htf_ema50:,.2f})"
            return {
                "has_signal": False,
                "symbol": symbol,
                "current_price": current_price,
                "direction": direction,
                "strategy": strat_name,
                "score": score,
                "stop_loss": current_price,
                "take_profit": current_price,
                "ml_approved": False,
                "ml_confidence": 0.0,
                "ml_reason": v_reason,
                "session": session_desc,
                "reason": v_reason
            }

    # 3. Bitcoin Relative Strength (RS) & 5M Momentum Synchronization
    from btc_sentinel import btc_sentinel
    rs_data = btc_sentinel.calculate_relative_strength(
        symbol=symbol,
        alt_df_15m=df_tf,
        alt_df_5m=df_micro,
        direction=direction
    )

    # Reject altcoins exhibiting divergent weakness against Bitcoin (e.g. red candle while BTC is pumping)
    if rs_data.get("is_divergent"):
        v_reason = rs_data.get("divergence_reason", f"Altcoin 5M Divergence against Bitcoin momentum flow.")
        return {
            "has_signal": False,
            "symbol": symbol,
            "current_price": current_price,
            "direction": direction,
            "strategy": strat_name,
            "score": score,
            "stop_loss": current_price,
            "take_profit": current_price,
            "ml_approved": False,
            "ml_confidence": 0.0,
            "ml_reason": v_reason,
            "session": session_desc,
            "reason": v_reason
        }

    # Inject Bitcoin Relative Strength Modifier directly into Confluence Score
    rs_mod = rs_data.get("score_modifier", 0)
    score = max(0, min(100, score + rs_mod))
    breakdown["btc_relative_strength"] = rs_data.get("rs_pct", 0.0)
    breakdown["btc_rs_status"] = rs_data.get("status", "NEUTRAL")
    breakdown["btc_rs_modifier"] = rs_mod

    # Minimum baseline filter: Score must be at least 82/100 (PERFECT GRADE-S+++ 🔥)
    if score < 82:
        v_reason = f"Confluence score {score}/100 is below minimum threshold 82 ({rs_data.get('desc', '')})"
        return {
            "has_signal": False,
            "symbol": symbol,
            "current_price": current_price,
            "direction": direction,
            "strategy": strat_name,
            "score": score,
            "stop_loss": current_price,
            "take_profit": current_price,
            "ml_approved": False,
            "ml_confidence": 0.0,
            "ml_reason": v_reason,
            "session": session_desc,
            "reason": v_reason
        }

    # Extract market snapshot features for ML
    features = extract_features_at_index(
        df=df_tf,
        idx=-1,
        direction=direction,
        higher_tf_df=df_htf
    )
    features["confluence_score"] = float(score)
    features["btc_relative_strength"] = float(rs_data.get("rs_pct", 0.0))
    features["btc_rs_modifier"] = float(rs_mod)
    features["is_engulfing"] = 1.0 if "ENGULFING" in active_pattern else 0.0
    features["is_pinbar"] = 1.0 if "PINBAR" in active_pattern else 0.0
    features["is_sfp"] = 1.0 if "LIQUIDITY_SWEEP" in active_pattern else 0.0
    features["vol_surge"] = 1.0 if (pa_conf_15m.get("volume_surge") or (pa_conf_5m and pa_conf_5m.get("volume_surge"))) else 0.0

    # Structural Swing Stop-Loss & Two-Stage Take-Profit Calculation (5M + 15M Structural Anchors)
    stop_loss, tp1_partial, tp2_runner = calculate_sl_tp(
        entry_price=current_price,
        atr=current_atr,
        direction=direction,
        score=score,
        df=df_tf,
        df_htf=df_htf,
        df_5m=df_micro,
        symbol=symbol
    )

    # ML Dual-Model Ensemble Prediction with Tiered Threshold (73%, 80%, or 87%)
    from merge_engine import get_symbol_thresholds
    target_ml_thresh, target_gemini_thresh, tier_label = get_symbol_thresholds(symbol)
    ml_result = ml_brain.predict_dual_ensemble(features, threshold=target_ml_thresh)
    ml_win_prob = ml_result["ensemble_prob"]

    # Merge Engine: Combines Rule Score (0-100) + ML Probability
    closed_history = get_closed_trades()
    merge_result = combine_rule_and_ml_scores(
        rule_score=score,
        ml_win_prob=ml_win_prob,
        total_trades_history=len(closed_history),
        max_rule_score=100
    )

    # Executive Final Decision Review
    claude_decision = evaluate_claude_ai_final_decision(
        symbol=symbol,
        direction=direction,
        rule_score=score,
        breakdown=breakdown,
        ml_result=ml_result,
        merge_result=merge_result,
        current_price=current_price,
        stop_loss=stop_loss,
        take_profit=tp1_partial,
        session_desc=session_desc
    )

    is_final_approved = claude_decision["is_approved"] and ml_result["is_approved"]

    # 7. Sovereign Bitcoin Master Sentinel Check
    from btc_sentinel import btc_sentinel
    btc_aligned, btc_reason, btc_info = btc_sentinel.check_trade_alignment(symbol, direction)

    if is_final_approved and not btc_aligned:
        is_final_approved = False
        claude_decision["verdict"] = f"VETO 🚫 ({btc_reason})"
        claude_decision["thesis"] = btc_reason

    # 8. Open Interest (OI) & Funding Rate Sentiment Gate
    from oi_funding_sentinel import oi_funding_sentinel
    oi_ok, oi_reason, oi_metrics = oi_funding_sentinel.evaluate_sentiment_gate(symbol, direction)

    if is_final_approved and not oi_ok:
        is_final_approved = False
        claude_decision["verdict"] = f"VETO 🚫 ({oi_reason})"
        claude_decision["thesis"] = oi_reason

    final_reason = oi_reason if not oi_ok else (btc_reason if not btc_aligned else ml_result["reason"])

    return {
        "has_signal": is_final_approved,
        "symbol": symbol,
        "direction": direction,
        "strategy": strat_name,
        "score": score,
        "score_breakdown": breakdown,
        "current_price": current_price,
        "stop_loss": stop_loss,
        "take_profit": tp1_partial,
        "take_profit_2": tp2_runner,
        "pattern": active_pattern,
        "atr": current_atr,
        "session": session_desc,
        "technical_reason": desc,
        "ml_result": ml_result,
        "ml_approved": is_final_approved,
        "ml_confidence": ml_win_prob,
        "ml_reason": final_reason,
        "btc_state": btc_info.get("state", "N/A"),
        "btc_bias": btc_info.get("bias", "N/A"),
        "btc_reason": btc_reason,
        "funding_rate_pct": oi_metrics.get("funding_rate_pct", 0.0),
        "oi_delta_15m": oi_metrics.get("oi_delta_15m_pct", 0.0),
        "merge_result": merge_result,
        "claude_verdict": claude_decision["verdict"],
        "claude_thesis": claude_decision["thesis"],
        "risk_multiplier": claude_decision["risk_multiplier"],
        "features": features
    }
