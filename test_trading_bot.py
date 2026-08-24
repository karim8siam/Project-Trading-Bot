"""
Comprehensive Test Suite for Binance Futures ML Dual Ensemble, Merge Engine, & Claude AI Brain.
Tests:
1. Whitelist Security
2. 3-Pillar Risk Guardrails
3. Order Block Detection & Location Grading
4. Trading Session Filters
5. Master Scoring & Hard Veto Rules
6. ML Dual Ensemble, 5-Stage Timeline, Merge Engine, & Claude AI Brain
"""

import os
import unittest
import pandas as pd
import numpy as np
from datetime import datetime

from config import ALLOWED_SYMBOLS, validate_symbol
from database import (
    init_db,
    clear_db,
    insert_trade,
    close_trade,
    get_training_dataset,
    get_performance_summary
)
from indicators import add_all_indicators
from location_engine import detect_order_blocks, evaluate_master_location, is_active_trading_session
from risk_manager import (
    calculate_position_size,
    calculate_logical_sl_tp,
    get_score_based_risk_percentage,
    get_account_growth_tier,
    update_breakeven_and_trailing_stops
)
from feature_extractor import extract_features_at_index
from ml_brain import MLDualEnsembleBrain
from merge_engine import combine_rule_and_ml_scores, evaluate_claude_ai_final_decision
from data_fetcher import BinanceFuturesFetcher
from strategy import calculate_bullish_master_score, calculate_bearish_master_score, analyze_market


class TestTradingBot(unittest.TestCase):

    def setUp(self):
        """Set up clean database for each test."""
        init_db()
        clear_db()

    def test_01_whitelist_security(self):
        """Verify strict 10-pair whitelist enforcement."""
        for sym in ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT", "AVAX/USDT", "LINK/USDT", "ADA/USDT", "NEAR/USDT"]:
            self.assertEqual(validate_symbol(sym), sym)

        invalid_symbols = ["PEPE/USDT", "SHIB/USDT", "EUR/USD", "AAPL", "UNKNOWN/USDT"]
        for sym in invalid_symbols:
            with self.assertRaises(ValueError):
                validate_symbol(sym)

    def test_02_three_pillar_risk_rules(self):
        """Verify 3-Pillar Risk Rules."""
        balance = 10000.0
        risk_80, _, _ = get_score_based_risk_percentage(score=80, account_balance=balance)
        self.assertEqual(risk_80, 0.50)

        sl, tp1, tp2, rr = calculate_logical_sl_tp(
            entry_price=60000.0,
            atr=500.0,
            direction="LONG",
            score=85,
            order_block_price=59200.0
        )
        self.assertTrue(sl < 60000.0)
        self.assertTrue(tp1 > 60000.0)
        self.assertTrue(rr >= 2.0)

        mock_trade = {"entry_price": 60000.0, "stop_loss": 59000.0, "direction": "LONG"}
        be_res = update_breakeven_and_trailing_stops(mock_trade, current_price=61100.0, atr=500.0)
        self.assertTrue(be_res["is_breakeven"])

    def test_03_order_block_and_location_grading(self):
        """Verify Order Block detection and Grade S/A/B/C classification."""
        fetcher = BinanceFuturesFetcher()
        df = add_all_indicators(fetcher.generate_realistic_ohlcv("BTC/USDT", n_candles=300))

        obs = detect_order_blocks(df, lookback=60)
        self.assertIn("bullish_obs", obs)
        self.assertIn("bearish_obs", obs)

        loc = evaluate_master_location(df, idx=-1, direction="LONG")
        self.assertIn("location_grade", loc)
        self.assertIn("total_score", loc)

    def test_04_session_filter(self):
        """Verify 24/7 crypto session tracking."""
        dt_overlap = datetime(2026, 8, 18, 14, 0, 0)
        active, _ = is_active_trading_session(dt_overlap)
        self.assertTrue(active)

        dt_asia = datetime(2026, 8, 18, 3, 0, 0)
        active_asia, _ = is_active_trading_session(dt_asia)
        self.assertTrue(active_asia)

    def test_05_master_scoring_and_vetoes(self):
        """Verify master scoring engine and hard veto cancellations."""
        fetcher = BinanceFuturesFetcher()
        df = add_all_indicators(fetcher.generate_realistic_ohlcv("ETH/USDT", n_candles=300))

        score, breakdown, veto = calculate_bullish_master_score(df, idx=-1)
        self.assertIsInstance(score, (int, float))

        # Test VETO 1
        df_below_ema = df.copy()
        df_below_ema.loc[df_below_ema.index[-1], "close"] = 100.0
        df_below_ema.loc[df_below_ema.index[-1], "ema_200"] = 500.0
        score_be, _, veto_be = calculate_bullish_master_score(df_below_ema, idx=-1)
        self.assertEqual(score_be, 0)
        self.assertIn("VETO 1", veto_be)

    def test_06_ml_timeline_merge_engine_and_claude_ai(self):
        """Verify 5-Stage ML timeline weights, Merge Engine composite scoring, and Claude AI brain."""
        brain = MLDualEnsembleBrain()

        # Test 5-Stage Timeline Weights
        w_rules, w_ml, p1 = brain.get_adaptive_weight(total_samples=30)
        self.assertEqual((w_rules, w_ml), (1.00, 0.00))

        w_rules, w_ml, p2 = brain.get_adaptive_weight(total_samples=100)
        self.assertEqual((w_rules, w_ml), (0.70, 0.30))

        w_rules, w_ml, p3 = brain.get_adaptive_weight(total_samples=350)
        self.assertEqual((w_rules, w_ml), (0.60, 0.40))

        w_rules, w_ml, p4 = brain.get_adaptive_weight(total_samples=750)
        self.assertEqual((w_rules, w_ml), (0.50, 0.50))

        w_rules, w_ml, p5 = brain.get_adaptive_weight(total_samples=1200)
        self.assertEqual((w_rules, w_ml), (0.40, 0.60))

        # Test Merge Engine
        merged = combine_rule_and_ml_scores(
            rule_score=180,
            ml_win_prob=0.78,
            total_trades_history=100,
            max_rule_score=200
        )
        self.assertIn("composite_score_pct", merged)
        self.assertTrue(0.0 <= merged["composite_confidence"] <= 1.0)

        # Test Claude AI Decision Layer
        claude_res = evaluate_claude_ai_final_decision(
            symbol="BTC/USDT",
            direction="LONG",
            rule_score=185,
            breakdown={"sec1_trend_score": 50, "sec2_location_score": 45, "sec3_indicator_score": 60, "sec4_candlestick_score": 30, "location_grade": "GRADE S"},
            ml_result={"rf_prob": 0.81, "xgb_prob": 0.75, "ensemble_prob": 0.78, "status": "Active"},
            merge_result=merged,
            current_price=65000.0,
            stop_loss=64000.0,
            take_profit=68000.0,
            session_desc="London / NY Overlap"
        )

        self.assertTrue(claude_res["is_approved"])
        self.assertIn("APPROVED", claude_res["verdict"])
        self.assertIn("CLAUDE AI BRAIN", claude_res["prompt"])


if __name__ == "__main__":
    unittest.main()
