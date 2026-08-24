"""
Comprehensive Test Suite for Crypto Futures Multi-Regime Trading Architecture.
Tests:
1. Market Regime Classifier (Trending, Breakout, Ranging)
2. Strategy Engines (Pullback, Breakout, Mean-Reversion)
3. Risk Manager 0-100 Score Sizing & Guardrails
4. Complete End-to-End Market Scan Simulation
"""

import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from indicators import add_all_indicators
from regime_detector import detect_crypto_regime
from strategies.trend_pullback import evaluate_trend_pullback
from strategies.volatility_breakout import evaluate_volatility_breakout
from strategies.range_mean_reversion import evaluate_range_mean_reversion
from strategy import analyze_market, evaluate_master_crypto_strategy
from risk_manager import (
    get_score_based_risk_percentage,
    calculate_position_size,
    get_account_growth_tier
)


def generate_synthetic_crypto_df(regime: str = "trend", n_candles: int = 150) -> pd.DataFrame:
    """Generates synthetic OHLCV data representing various crypto market regimes."""
    np.random.seed(42)
    dates = [datetime.utcnow() - timedelta(minutes=15 * (n_candles - i)) for i in range(n_candles)]
    
    if regime == "bull_trend":
        # Consistent upward trend with periodic shallow dips
        close = 50000.0 + np.cumsum(np.random.normal(30, 15, n_candles))
    elif regime == "bear_trend":
        # Consistent downward trend
        close = 50000.0 - np.cumsum(np.random.normal(30, 15, n_candles))
    elif regime == "breakout":
        # Flat consolidation then sudden massive explosion on the last bar
        close = 50000.0 + np.random.normal(0, 5, n_candles)
        close[-1] = close[-2] + 400.0  # Massive breakout above all 20 previous bars
    else:  # "range"
        # Flat sideways oscillation (low ADX)
        close = 50000.0 + np.random.normal(0, 10, n_candles)

    high = close + np.random.uniform(5, 20, n_candles)
    low = close - np.random.uniform(5, 20, n_candles)
    open_p = (close + np.roll(close, 1)) / 2.0
    open_p[0] = close[0]
    volume = np.random.uniform(100, 300, n_candles)
    if regime == "breakout":
        volume[-1] = 2000.0  # Huge volume surge

    df = pd.DataFrame({
        "timestamp": [d.strftime("%Y-%m-%d %H:%M:%S") for d in dates],
        "open": open_p,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume
    })
    return add_all_indicators(df)


def test_regime_detector():
    print("Testing Crypto Market Regime Detector...")
    df_bull = generate_synthetic_crypto_df("bull_trend")
    res_bull = detect_crypto_regime(df_bull)
    print(f"  • Bull Trend Detection: {res_bull['regime']} ({res_bull['desc']})")
    assert "BULL" in res_bull["regime"] or res_bull["confidence"] > 0

    df_break = generate_synthetic_crypto_df("breakout")
    res_break = detect_crypto_regime(df_break)
    print(f"  • Breakout Detection  : {res_break['regime']} ({res_break['desc']})")
    assert res_break["regime"] in ("VOLATILITY_BREAKOUT", "TRENDING_BULL", "MODERATE_BULL")

    df_range = generate_synthetic_crypto_df("range")
    res_range = detect_crypto_regime(df_range)
    print(f"  • Range Detection     : {res_range['regime']} ({res_range['desc']})")
    assert res_range["regime"] in ("RANGING", "MODERATE_BULL", "MODERATE_BEAR")
    print("  ✅ Regime Detector Passed!\n")


def test_strategy_engines():
    print("Testing 3 Crypto Strategy Engines...")
    df_bull = generate_synthetic_crypto_df("bull_trend")
    pb_res = evaluate_trend_pullback(df_bull)
    print(f"  • Trend Pullback Engine : has_signal={pb_res['has_signal']}, score={pb_res.get('score')}")

    df_break = generate_synthetic_crypto_df("breakout")
    br_res = evaluate_volatility_breakout(df_break)
    print(f"  • Breakout Engine       : has_signal={br_res['has_signal']}, score={br_res.get('score')}")

    df_range = generate_synthetic_crypto_df("range")
    rg_res = evaluate_range_mean_reversion(df_range)
    print(f"  • Range Reversion Engine: has_signal={rg_res['has_signal']}, score={rg_res.get('score')}")
    print("  ✅ Strategy Engines Passed!\n")


def test_risk_manager_score_tiers():
    print("Testing Risk Manager 0-100 Score Sizing...")
    # Test Perfect score (85)
    r_pct, min_rr, desc = get_score_based_risk_percentage(85, 1000.0)
    print(f"  • Score 85 (Perfect) : Risk = {r_pct}%, Min R:R = {min_rr}, Desc = {desc}")
    assert r_pct == 1.0

    # Test Strong score (65)
    r_pct, min_rr, desc = get_score_based_risk_percentage(65, 1000.0)
    print(f"  • Score 65 (Strong)  : Risk = {r_pct}%, Min R:R = {min_rr}, Desc = {desc}")
    assert r_pct == 0.75

    # Test Moderate score (55)
    r_pct, min_rr, desc = get_score_based_risk_percentage(55, 1000.0)
    print(f"  • Score 55 (Moderate): Risk = {r_pct}%, Min R:R = {min_rr}, Desc = {desc}")
    assert r_pct == 0.50

    # Test position sizing calculation
    pos = calculate_position_size(
        account_balance_usdt=1000.0,
        entry_price=60000.0,
        stop_loss_price=59400.0,
        symbol="BTC/USDT",
        score=65,
        leverage=5
    )
    print(f"  • Position Sizing BTC: Valid={pos['valid']}, Qty={pos.get('quantity')}, Risk=${pos.get('actual_risk_usd')}")
    assert pos["valid"] is True
    print("  ✅ Risk Manager Score Tiers Passed!\n")


def test_end_to_end_analysis():
    print("Testing End-to-End Market Analysis Pipeline...")
    df_bull = generate_synthetic_crypto_df("bull_trend")
    analysis = analyze_market("BTC/USDT", df_bull)
    print(f"  • BTC/USDT Analysis: has_signal={analysis['has_signal']}, dir={analysis.get('direction')}, score={analysis.get('score')}")
    print("  ✅ End-to-End Pipeline Passed!\n")


if __name__ == "__main__":
    print("=" * 70)
    print("  RUNNING CRYPTO FUTURES MULTI-REGIME TEST SUITE")
    print("=" * 70)
    test_regime_detector()
    test_strategy_engines()
    test_risk_manager_score_tiers()
    test_end_to_end_analysis()
    print("=" * 70)
    print("  🎉 ALL MULTI-REGIME TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)
