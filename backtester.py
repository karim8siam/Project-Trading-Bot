"""
Historical Backtester & Initial ML Bootstrapper for Binance Futures Bot.
Simulates:
- 200-Point Master Confluence Scoring Engine
- 3-Pillar Risk Management (1% risk sizing, Breakeven at 1R, Trailing Stops)
- Generates realistic trade history across the 4 whitelisted pairs
- Trains the Random Forest & XGBoost Dual-Model Ensemble
"""

import sys
import uuid
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional
from tabulate import tabulate

from config import (
    ALLOWED_SYMBOLS,
    DEFAULT_LEVERAGE,
    SL_ATR_MULTIPLIER,
    TP_ATR_MULTIPLIER,
    DEFAULT_TIMEFRAME
)
from indicators import add_all_indicators
from data_fetcher import BinanceFuturesFetcher
from strategy import check_candidate_signal
from feature_extractor import extract_features_at_index
from risk_manager import (
    calculate_position_size,
    calculate_logical_sl_tp,
    update_breakeven_and_trailing_stops
)
from database import (
    init_db,
    insert_trade,
    close_trade,
    get_training_dataset,
    get_performance_summary
)
from ml_brain import ml_brain


def run_backtest_on_dataframe(
    df: pd.DataFrame,
    symbol: str,
    initial_balance: float = 10000.0,
    record_to_db: bool = True,
    use_ml_filter: bool = False
) -> Dict[str, Any]:
    """
    Simulates trading across historical candle series using the 200-point confluence engine and 3-pillar risk rules.
    """
    if "ema_200" not in df.columns:
        df = add_all_indicators(df)

    balance = initial_balance
    trades = []
    open_position = None

    for i in range(200, len(df) - 1):
        curr_row = df.iloc[i]
        curr_price = float(curr_row["close"])
        curr_atr = float(curr_row["atr_14"])
        timestamp = str(curr_row.get("timestamp", f"Candle-{i}"))

        # 1. Manage existing open position (Breakeven & Trailing Stops)
        if open_position:
            pos = open_position
            dir_ = pos["direction"]
            sl = pos["stop_loss"]
            tp = pos["take_profit"]
            high_p = float(curr_row["high"])
            low_p = float(curr_row["low"])

            exit_price = None
            exit_reason = None

            if dir_ == "LONG":
                if high_p >= tp:
                    exit_price = tp
                    exit_reason = "TAKE_PROFIT"
                elif low_p <= sl:
                    exit_price = sl
                    exit_reason = "STOP_LOSS"
            else:  # SHORT
                if low_p <= tp:
                    exit_price = tp
                    exit_reason = "TAKE_PROFIT"
                elif high_p >= sl:
                    exit_price = sl
                    exit_reason = "STOP_LOSS"

            if exit_price and exit_reason:
                # Close Trade
                entry_p = pos["entry_price"]
                qty = pos["quantity"]
                lev = pos["leverage"]

                if dir_ == "LONG":
                    pnl_pct = ((exit_price - entry_p) / entry_p) * lev * 100.0
                    pnl_usd = (exit_price - entry_p) * qty
                else:
                    pnl_pct = ((entry_p - exit_price) / entry_p) * lev * 100.0
                    pnl_usd = (entry_p - exit_price) * qty

                is_win = 1 if pnl_usd > 0 else 0
                balance += pnl_usd

                closed_rec = {
                    "trade_id": pos["trade_id"],
                    "symbol": symbol,
                    "direction": dir_,
                    "entry_price": entry_p,
                    "exit_price": exit_price,
                    "exit_reason": exit_reason,
                    "pnl_usd": pnl_usd,
                    "pnl_percent": pnl_pct,
                    "is_win": is_win,
                    "balance_after": balance
                }
                trades.append(closed_rec)

                if record_to_db:
                    close_trade(pos["trade_id"], exit_price=exit_price, exit_reason=exit_reason)

                open_position = None
            else:
                # Check Breakeven & Trailing Stop (Rules 6 & 7)
                be_res = update_breakeven_and_trailing_stops(
                    trade={"entry_price": pos["entry_price"], "stop_loss": sl, "direction": dir_},
                    current_price=curr_price,
                    atr=curr_atr
                )
                open_position["stop_loss"] = be_res["updated_sl"]

        # 2. Check for new trade signals
        if not open_position:
            direction, score, breakdown, desc = check_candidate_signal(df, idx=i)

            if direction and score >= 140:
                features = extract_features_at_index(df, idx=i, direction=direction)
                features["confluence_score"] = float(score)

                # ML Meta-Filter check
                ml_approved = True
                ml_prob = 0.5
                if use_ml_filter and ml_brain.is_trained:
                    ml_approved, ml_prob, _ = ml_brain.evaluate_trade(features)

                if ml_approved:
                    stop_loss, tp1, tp2, _ = calculate_logical_sl_tp(
                        entry_price=curr_price,
                        atr=curr_atr,
                        direction=direction,
                        score=score
                    )

                    risk_plan = calculate_position_size(
                        account_balance_usdt=balance,
                        entry_price=curr_price,
                        stop_loss_price=stop_loss,
                        symbol=symbol,
                        score=score,
                        leverage=DEFAULT_LEVERAGE
                    )

                    if risk_plan["valid"]:
                        t_id = f"BT-{symbol[:3]}-{uuid.uuid4().hex[:6].upper()}"
                        open_position = {
                            "trade_id": t_id,
                            "symbol": symbol,
                            "direction": direction,
                            "entry_price": curr_price,
                            "quantity": risk_plan["quantity"],
                            "leverage": DEFAULT_LEVERAGE,
                            "stop_loss": stop_loss,
                            "take_profit": tp1,
                            "features": features
                        }

                        if record_to_db:
                            trade_db_record = {
                                "trade_id": t_id,
                                "symbol": symbol,
                                "direction": direction,
                                "entry_time": timestamp,
                                "entry_price": curr_price,
                                "quantity": risk_plan["quantity"],
                                "leverage": DEFAULT_LEVERAGE,
                                "stop_loss": stop_loss,
                                "take_profit": tp1,
                                "ml_predicted_prob": ml_prob,
                                "ml_approved": 1 if ml_approved else 0
                            }
                            insert_trade(trade_db_record, features=features)

    # Performance metrics
    total_trades = len(trades)
    wins = sum(1 for t in trades if t["is_win"] == 1)
    losses = total_trades - wins
    win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
    net_pnl = balance - initial_balance
    profit_pct = (net_pnl / initial_balance) * 100.0

    return {
        "symbol": symbol,
        "initial_balance": initial_balance,
        "final_balance": round(balance, 2),
        "net_pnl_usd": round(net_pnl, 2),
        "profit_pct": round(profit_pct, 2),
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(win_rate, 2),
        "trades": trades
    }


def bootstrap_and_train_ml(n_candles_per_pair: int = 1500) -> Dict[str, Any]:
    """
    Initializes clean SQLite database, simulates 1500 historical candles across all 4 whitelisted pairs,
    records all trades + 27-D features, and trains the Dual-Model ML Ensemble.
    """
    print("=" * 75)
    print("🚀 BOOTSTRAPPING 200-POINT CONFLUENCE & ML ENSEMBLE ACROSS 4 PAIRS")
    print(f"Pairs: {ALLOWED_SYMBOLS} | Candles per pair: {n_candles_per_pair}")
    print("=" * 75)

    init_db()
    fetcher = BinanceFuturesFetcher()
    all_results = []

    for symbol in ALLOWED_SYMBOLS:
        print(f"Backtesting & Generating Journal on {symbol}...")
        df = fetcher.generate_realistic_ohlcv(symbol, n_candles=n_candles_per_pair)
        res = run_backtest_on_dataframe(df, symbol=symbol, record_to_db=True, use_ml_filter=False)
        all_results.append(res)
        print(f"  -> {res['total_trades']} trades executed | Win Rate: {res['win_rate_pct']}% | PnL: ${res['net_pnl_usd']:,.2f}")

    # Retrain Machine Learning Dual Ensemble
    print("\nTraining Dual Ensemble (Random Forest + XGBoost) on simulated history...")
    X, y = get_training_dataset()
    print(f"Total Dataset Size: {len(X)} historical trades")

    train_result = ml_brain.train(X, y)
    print(f"  • Random Forest Test Accuracy : {train_result['rf_accuracy'] * 100:.1f}%")
    print(f"  • XGBoost / HistGBDT Accuracy : {train_result['xgb_accuracy'] * 100:.1f}%")
    print(f"  • Combined Ensemble Accuracy   : {train_result['ensemble_accuracy'] * 100:.1f}%")
    print(f"  • Validation ROC-AUC Score     : {train_result['val_roc_auc']:.3f}")

    print("\n🔍 Discovered Hidden Market Patterns:")
    for i, pat in enumerate(train_result.get("discovered_patterns", []), 1):
        print(f"  {i}. {pat}")

    print("=" * 75)
    return {"backtests": all_results, "ml_training": train_result}


if __name__ == "__main__":
    bootstrap_and_train_ml(n_candles_per_pair=1200)
