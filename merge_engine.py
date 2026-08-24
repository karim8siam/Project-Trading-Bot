"""
Merge Engine & Claude AI Brain Reasoner.
Combines:
1. Master Rule Confluence Score (Trend, Location/Order Block, Indicators, Candlesticks)
2. Machine Learning Dual-Model Ensemble (Random Forest + XGBoost)
3. 5-Stage Adaptive Timeline Weighting
4. Claude AI Brain Final Decision Review
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, Tuple, Optional

from database import get_closed_trades
from ml_brain import ml_brain


def combine_rule_and_ml_scores(
    rule_score: int,
    ml_win_prob: float,
    total_trades_history: int,
    max_rule_score: int = 100
) -> Dict[str, Any]:
    """
    Step 6 & 7: Merge Engine combining Rule Score (0-100) and ML Dual-Ensemble:
    - Normalizes rule score to [0.0, 1.0]
    - Fetches adaptive sample-size weights (W_rules, W_ml)
    - Computes Composite Confidence = (W_rules * S_norm) + (W_ml * P_ml)
    """
    rules_weight, ml_weight, phase_name = ml_brain.get_adaptive_weight(total_trades_history)

    # Normalize rule score to 0.0 - 1.0
    normalized_rule_score = min(1.0, max(0.0, rule_score / float(max_rule_score)))

    # Composite weighted probability
    composite_confidence = (rules_weight * normalized_rule_score) + (ml_weight * ml_win_prob)

    return {
        "rule_score": rule_score,
        "normalized_rule_score": round(normalized_rule_score, 4),
        "ml_win_prob": round(ml_win_prob, 4),
        "rules_weight": rules_weight,
        "ml_weight": ml_weight,
        "phase_name": phase_name,
        "composite_confidence": round(composite_confidence, 4),
        "composite_score_pct": round(composite_confidence * 100, 1)
    }


def generate_claude_ai_prompt(
    symbol: str,
    direction: str,
    rule_score: int,
    breakdown: Dict[str, Any],
    ml_result: Dict[str, Any],
    merge_result: Dict[str, Any],
    current_price: float,
    stop_loss: float,
    take_profit: float,
    session_desc: str
) -> str:
    """
    Constructs the structured market evaluation prompt for Claude AI Brain.
    """
    return f"""
================================================================================
🏛️ CLAUDE AI BRAIN - EXECUTIVE TRADE DECISION REVIEW (CRYPTO FUTURES)
================================================================================
ASSET: {symbol} | DIRECTION: {direction} | PRICE: ${current_price:,.2f}
MARKET SESSION: {session_desc}
REGIME: {breakdown.get('regime', 'N/A')} ({breakdown.get('regime_desc', 'N/A')})
STOP LOSS: ${stop_loss:,.2f} | TAKE PROFIT: ${take_profit:,.2f}

1. MULTI-REGIME CONFLUENCE EVALUATION ({rule_score}/100 Points):
   • Strategy: {breakdown.get('strategy', 'Adaptive Engine')}
   • Technical Breakdown: {json.dumps(breakdown, indent=2)}

2. MACHINE LEARNING DUAL-MODEL ENSEMBLE:
   • Random Forest Prediction : {ml_result.get('rf_prob', 0.5)*100:.1f}% Win Probability
   • XGBoost / HistGBDT       : {ml_result.get('xgb_prob', 0.5)*100:.1f}% Win Probability
   • Combined ML Ensemble     : {ml_result.get('ensemble_prob', 0.5)*100:.1f}% Win Probability
   • ML Status                : {ml_result.get('status', 'Active')}

3. MERGE ENGINE COMPOSITE CONFIDENCE:
   • Adaptive Phase           : {merge_result['phase_name']}
   • Rules Weight             : {merge_result['rules_weight']*100:.0f}%
   • ML Weight                : {merge_result['ml_weight']*100:.0f}%
   • Final Composite Score    : {merge_result['composite_score_pct']}%

TASK:
Review crypto technical layers and ML probabilities. Output approval with rationalized thesis.
================================================================================
"""


from gemini_reasoner import gemini_reasoner


from config import (
    HIGH_RISK_SYMBOLS_80_PCT,
    HIGH_RISK_ML_THRESHOLD,
    HIGH_RISK_GEMINI_THRESHOLD,
    STANDARD_ML_THRESHOLD,
    STANDARD_GEMINI_THRESHOLD,
    SNIPER_SYMBOLS_87_PCT,
    SNIPER_ML_THRESHOLD,
    SNIPER_GEMINI_THRESHOLD
)


def get_symbol_thresholds(symbol: str) -> Tuple[float, float, str]:
    """
    Returns custom risk thresholds for the symbol across all 3 tiers:
    - Tier 3: SNIPER Volatile Tokens (SUI, APT, PEPE, RENDER, TIA, INJ, ARB, OP, FET, SEI) -> Strict 87%+ ML & Gemini
    - Tier 2: High-Risk Alts (AVAX, DOGE, LINK) -> Strict 80%+ ML & Gemini
    - Tier 1: Core Majors (BTC, ETH, BNB, SOL, XRP, ADA, NEAR) -> Standard 73%+ ML & Gemini
    """
    if symbol in SNIPER_SYMBOLS_87_PCT:
        return SNIPER_ML_THRESHOLD, SNIPER_GEMINI_THRESHOLD, "Tier-3 Sniper Volatile Token (87%+ Gate 🔥)"
    elif symbol in HIGH_RISK_SYMBOLS_80_PCT:
        return HIGH_RISK_ML_THRESHOLD, HIGH_RISK_GEMINI_THRESHOLD, "Tier-2 High-Risk Volatility Pair (80%+ Gate 🛡️)"
    return STANDARD_ML_THRESHOLD, STANDARD_GEMINI_THRESHOLD, "Tier-1 Standard Major Pair (73%+ Gate 🌐)"


def evaluate_claude_ai_final_decision(
    symbol: str,
    direction: str,
    rule_score: int,
    breakdown: Dict[str, Any],
    ml_result: Dict[str, Any],
    merge_result: Dict[str, Any],
    current_price: float,
    stop_loss: float,
    take_profit: float,
    session_desc: str
) -> Dict[str, Any]:
    """
    Supreme Decision Engine with Custom Risk Tiering:
    - High-Risk Tier (AVAX, DOGE, LINK): Requires >= 80% ML Win Probability & >= 80% Gemini AI
    - Standard Tier-1 (BTC, ETH, BNB, SOL, XRP, ADA, NEAR): Requires >= 73% ML Win Probability & >= 73% Gemini AI
    """
    composite_score = merge_result["composite_score_pct"]
    ml_prob = ml_result.get("ensemble_prob", 0.5)

    target_ml_thresh, target_gemini_thresh, tier_label = get_symbol_thresholds(symbol)

    # 1. Supreme ML Threshold Check (ML is supreme mathematical authority)
    if ml_prob < target_ml_thresh:
        return {
            "verdict": f"VETO / PASS 🚫 (Supreme ML Gate: {ml_prob*100:.1f}% < {target_ml_thresh*100:.0f}% for {symbol})",
            "is_approved": False,
            "risk_multiplier": 0.0,
            "thesis": f"[Supreme ML VETO]: Probability {ml_prob*100:.1f}% is below required {target_ml_thresh*100:.0f}% for {tier_label}.",
            "gemini_confidence": 0.0,
            "gemini_reasoning": f"Skipped: Supreme ML probability below {target_ml_thresh*100:.0f}%",
            "gemini_risk_notes": f"{tier_label} Low Probability"
        }

    # 2. Call Google Gemini 3.6 Flash Reasoning Engine
    gemini_res = gemini_reasoner.analyze_trade_setup(
        symbol=symbol,
        direction=direction,
        rule_score=rule_score,
        breakdown=breakdown,
        ml_result=ml_result,
        current_price=current_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        session_desc=session_desc,
        target_confidence=target_gemini_thresh
    )

    is_gemini_approved = gemini_res.get("approved", False)
    gemini_conf = gemini_res.get("confidence", 0.0)
    gemini_reason = gemini_res.get("reasoning", "")
    gemini_risk = gemini_res.get("risk_notes", "")

    # 3. Final Supreme Consensus
    if is_gemini_approved and gemini_conf >= target_gemini_thresh and rule_score >= 76:
        verdict = f"APPROVED (SUPREME ML & GEMINI GRADE-S++ 🔥 | ML: {ml_prob*100:.1f}%, AI: {gemini_conf:.0f}%)"
        is_approved = True
        risk_multiplier = 1.0
        thesis = f"[Supreme ML ({ml_prob*100:.1f}%) + Gemini 3.6 Flash ({gemini_conf:.0f}%)]: {gemini_reason}"
        if gemini_risk:
            thesis += f" | Watch: {gemini_risk}"
    else:
        verdict = f"VETO / PASS 🚫 (Gemini Reasoning Filter: {gemini_conf:.0f}% < {target_gemini_thresh:.0f}%)"
        is_approved = False
        risk_multiplier = 0.0
        thesis = f"[Gemini VETO]: {gemini_reason} (Score: {rule_score}/100, ML: {ml_prob*100:.1f}%, AI Conf: {gemini_conf:.0f}%)"

    return {
        "verdict": verdict,
        "is_approved": is_approved,
        "risk_multiplier": risk_multiplier,
        "thesis": thesis,
        "gemini_confidence": gemini_conf,
        "gemini_reasoning": gemini_reason,
        "gemini_risk_notes": gemini_risk
    }
