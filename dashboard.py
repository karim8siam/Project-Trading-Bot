"""
Console Dashboard & 3-Pillar Institutional Risk Monitor for Binance Futures.
Visualizes:
- PILLAR 1: Per-Trade Risk & Active Positions (Breakeven & Trailing Stops)
- PILLAR 2: Daily Risk (3% Loss Limit, 3% Profit Target, 5 Trades/Day, Streaks)
- PILLAR 3: Account Risk (Drawdown Meter, Growth Tiers, 10%/20% Limits)
- ML DUAL-MODEL ENSEMBLE: Random Forest + XGBoost probabilities, Sunday retraining stats, and Discovered Hidden Patterns
"""

from typing import Dict, Any
from tabulate import tabulate
from config import ALLOWED_SYMBOLS, DEFAULT_LEVERAGE, USE_TESTNET
from database import get_open_trades, get_closed_trades, get_performance_summary
from risk_manager import (
    get_daily_performance,
    get_streak_status,
    check_account_drawdown,
    get_account_growth_tier
)
from data_fetcher import data_fetcher
from ml_brain import ml_brain
from location_engine import is_active_trading_session


def render_dashboard():
    """Renders comprehensive 3-pillar terminal dashboard."""
    balance = data_fetcher.fetch_balance_usdt()
    open_trades = get_open_trades()
    closed_trades = get_closed_trades(limit=10)
    perf = get_performance_summary()
    daily = get_daily_performance()
    streaks = get_streak_status()
    dd = check_account_drawdown(balance)
    tier_info = get_account_growth_tier(balance)
    feat_imp = ml_brain.get_feature_importances()
    session_active, session_desc = is_active_trading_session()
    rules_weight, ml_weight, weight_phase = ml_brain.get_adaptive_weight(perf["total_trades"])

    print("\n" + "=" * 94)
    print("      🛡️ BINANCE FUTURES 3-PILLAR RISK & DUAL-MODEL ML TRADING DASHBOARD")
    print("=" * 94)

    # 1. Account & Growth Phase
    print(f"\n[PILLAR 3: ACCOUNT RISK & GROWTH TIER]")
    account_table = [
        ["Account Balance", f"${balance:,.2f} USDT", "Account Phase", tier_info["tier_name"]],
        ["Peak Balance", f"${dd['peak_balance']:,.2f} USDT", "Peak Drawdown", f"{dd['drawdown_pct']:.2f}% (Limit: 10% / 20%)"],
        ["Drawdown Status", "🚨 20% HALT" if dd['is_emergency_halt'] else ("⚠️ 10% Protection Mode" if dd['is_protection_mode'] else "✅ Healthy (< 10%)"), "Trading Session", session_desc],
        ["Max Open Trades", f"{len(open_trades)} / 3 Max", "Leverage Mode", f"{DEFAULT_LEVERAGE}x Isolated Margin"]
    ]
    print(tabulate(account_table, tablefmt="fancy_grid"))

    # 2. Daily Risk Meter (Pillar 2)
    print(f"\n[PILLAR 2: DAILY RISK & STREAK CONTROLS]")
    daily_pnl_str = f"{'+' if daily['pnl_usd'] >= 0 else ''}${daily['pnl_usd']:,.2f}"
    daily_table = [
        ["Today's PnL", daily_pnl_str, "Daily Loss Limit", f"-{tier_info['daily_loss_limit_pct']}% (-${balance * tier_info['daily_loss_limit_pct']/100:,.2f})"],
        ["Today's Trades", f"{daily['trades_count']} / {tier_info['max_trades_per_day']} Max", "Daily Profit Target", f"+{tier_info['daily_profit_target_pct']}% (+${balance * tier_info['daily_profit_target_pct']/100:,.2f})"],
        ["Streak Status", f"{streaks['consecutive_wins']} Consecutive Wins" if streaks['consecutive_wins'] > 0 else (f"{streaks['consecutive_losses']} Consecutive Losses" if streaks['consecutive_losses'] > 0 else "Neutral Streak"), "Streak Guard", "🚨 50% Risk Cut" if streaks['consecutive_losses'] == 2 else ("🛑 Daily Halt (3 Losses)" if streaks['consecutive_losses'] >= 3 else "✅ Active")]
    ]
    print(tabulate(daily_table, tablefmt="fancy_grid"))

    # 3. Machine Learning Dual-Ensemble Brain
    print(f"\n[🤖 MACHINE LEARNING DUAL-MODEL ENSEMBLE BRAIN]")
    ml_status_table = [
        ["Random Forest Model", "Active (150 Trees)" if ml_brain.is_trained else "Building Data (<50)", "RF Test Accuracy", f"{ml_brain.rf_accuracy * 100:.1f}%" if ml_brain.is_trained else "N/A"],
        ["XGBoost / HistGBDT", "Active (150 Iterations)" if ml_brain.is_trained else "Building Data (<50)", "XGB Test Accuracy", f"{ml_brain.xgb_accuracy * 100:.1f}%" if ml_brain.is_trained else "N/A"],
        ["Dual Ensemble Accuracy", f"{ml_brain.ensemble_accuracy * 100:.1f}%" if ml_brain.is_trained else "N/A", "ML Decision Weight", f"{ml_weight * 100:.0f}% ({weight_phase})"],
        ["Sunday Retraining", "Automated (Weekly Midnight)", "Min Threshold", "P(Win) >= 58%"]
    ]
    print(tabulate(ml_status_table, tablefmt="fancy_grid"))

    # Discovered Patterns
    if ml_brain.discovered_patterns:
        print(f"\n[🔍 ML DISCOVERED HIDDEN MARKET PATTERNS]")
        for i, pat in enumerate(ml_brain.discovered_patterns, 1):
            print(f"  • Pattern {i}: {pat}")

    # 4. Overall Performance
    print(f"\n[HISTORICAL PERFORMANCE & METRICS]")
    perf_table = [
        ["Total Trades", perf["total_trades"], "Total Realized PnL", f"${perf['total_pnl_usd']:,.2f}"],
        ["Winning Trades", f"{perf['wins']} ✅", "Losing Trades", f"{perf['losses']} ❌"],
        ["Win Rate", f"{perf['win_rate_pct']}%", "Profit Factor", perf["profit_factor"]]
    ]
    print(tabulate(perf_table, tablefmt="fancy_grid"))

    # 5. Active Open Positions (Pillar 1)
    print(f"\n[PILLAR 1: ACTIVE POSITIONS & BREAKEVEN STATUS ({len(open_trades)}/3)]")
    if open_trades:
        open_rows = []
        for t in open_trades:
            sym = t["symbol"]
            curr_p = data_fetcher.fetch_current_price(sym)
            entry_p = float(t["entry_price"])
            sl_p = float(t["stop_loss"])
            dir_ = t["direction"]
            pnl_pct = ((curr_p - entry_p)/entry_p * 100 * t["leverage"]) if dir_ == "LONG" else ((entry_p - curr_p)/entry_p * 100 * t["leverage"])
            pnl_str = f"{'+' if pnl_pct >= 0 else ''}{pnl_pct:.2f}%"

            is_be = (sl_p >= entry_p) if dir_ == "LONG" else (sl_p <= entry_p)
            be_status = "🛡️ ZERO RISK (BE)" if is_be else "Active SL"

            open_rows.append([
                t["trade_id"],
                sym,
                dir_,
                f"${entry_p:,.2f}",
                f"${curr_p:,.2f}",
                f"${sl_p:,.2f}",
                f"${float(t['take_profit']):,.2f}",
                pnl_str,
                be_status,
                f"{float(t.get('ml_predicted_prob', 0.5))*100:.1f}%"
            ])
        headers = ["Trade ID", "Symbol", "Side", "Entry Price", "Mark Price", "Stop Loss", "Take Profit", "PnL (%)", "Protection", "ML Conf"]
        print(tabulate(open_rows, headers=headers, tablefmt="grid"))
    else:
        print("  (No active open positions currently)")

    # 6. Recent Closed Trades
    print(f"\n[RECENT CLOSED TRADES (Last {len(closed_trades)})]")
    if closed_trades:
        closed_rows = []
        for t in closed_trades:
            outcome = "WIN ✅" if t.get("is_win") == 1 else "LOSS ❌"
            pnl_u = float(t.get("pnl_usd") or 0.0)
            pnl_p = float(t.get("pnl_percent") or 0.0)
            closed_rows.append([
                t["trade_id"],
                t["symbol"],
                t["direction"],
                f"${float(t['entry_price']):,.2f}",
                f"${float(t.get('exit_price') or 0.0):,.2f}",
                t.get("exit_reason", "N/A"),
                f"{'+' if pnl_u >= 0 else ''}${pnl_u:.2f}",
                f"{'+' if pnl_p >= 0 else ''}{pnl_p:.2f}%",
                outcome
            ])
        headers = ["Trade ID", "Symbol", "Side", "Entry", "Exit", "Exit Reason", "PnL ($)", "PnL (%)", "Result"]
        print(tabulate(closed_rows, headers=headers, tablefmt="grid"))

    print("=" * 94 + "\n")


if __name__ == "__main__":
    render_dashboard()
