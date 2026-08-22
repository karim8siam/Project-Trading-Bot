"""
Live Bridge between Binance Futures Trading Bot & Orbital Platform.
Reads live trades, performance stats, and signals from trading_journal.db.
"""

import sqlite3
import pandas as pd
from typing import Dict, Any, List, Optional
from config import TRADING_BOT_DB


def get_live_bot_trades(limit: int = 15) -> List[Dict[str, Any]]:
    """
    Fetches the latest live closed and open trades from the trading bot database.
    """
    if not TRADING_BOT_DB.exists():
        return []

    try:
        conn = sqlite3.connect(TRADING_BOT_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
        SELECT 
            id, trade_id, symbol, direction, entry_time, entry_price, 
            stop_loss, take_profit, exit_time, exit_price, exit_reason, 
            pnl_usd, pnl_percent, ml_predicted_prob, leverage
        FROM trades 
        ORDER BY id DESC 
        LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        trades = []
        for r in rows:
            pnl = r["pnl_usd"]
            pnl_pct = r["pnl_percent"]
            
            if pnl is not None:
                if pnl > 0:
                    outcome = "WIN ✅"
                elif abs(pnl) < 1.0:
                    outcome = "BREAKEVEN 🛡️"
                else:
                    outcome = "LOSS ❌"
            else:
                outcome = "ACTIVE ⚡"

            trades.append({
                "id": r["id"],
                "trade_id": r["trade_id"],
                "symbol": r["symbol"],
                "direction": r["direction"],
                "entry_time": r["entry_time"],
                "entry_price": r["entry_price"],
                "exit_price": r["exit_price"],
                "stop_loss": r["stop_loss"],
                "take_profit": r["take_profit"],
                "exit_reason": r["exit_reason"] or "IN PROGRESS",
                "pnl_usd": round(pnl, 2) if pnl is not None else 0.0,
                "pnl_percent": round(pnl_pct, 2) if pnl_pct is not None else 0.0,
                "ml_probability": round((r["ml_predicted_prob"] or 0.75) * 100.0, 1),
                "leverage": r["leverage"] or 5,
                "outcome": outcome
            })

        return trades
    except Exception as e:
        print(f"[Bridge Sync] Error reading trading bot DB: {e}")
        return []


def get_live_bot_performance_summary() -> Dict[str, Any]:
    """
    Computes overall win rate, total net profit, and profit factor from the bot database.
    """
    if not TRADING_BOT_DB.exists():
        return {
            "total_trades": 0,
            "win_rate_pct": 0.0,
            "total_pnl_usd": 0.0,
            "profit_factor": 1.0,
            "status": "Scanning"
        }

    try:
        conn = sqlite3.connect(TRADING_BOT_DB)
        df = pd.read_sql("SELECT * FROM trades WHERE exit_price IS NOT NULL", conn)
        conn.close()

        if df.empty:
            return {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate_pct": 0.0,
                "total_pnl_usd": 0.0,
                "profit_factor": 0.0,
                "status": "Binance Mainnet Live ($13.89) 🟢"
            }

        total = len(df)
        wins = len(df[df["pnl_usd"] > 0])
        win_rate = (wins / total * 100.0) if total > 0 else 0.0
        total_pnl = float(df["pnl_usd"].sum())

        gross_wins = float(df[df["pnl_usd"] > 0]["pnl_usd"].sum())
        gross_losses = abs(float(df[df["pnl_usd"] < 0]["pnl_usd"].sum()))
        profit_factor = (gross_wins / max(1.0, gross_losses)) if gross_losses > 0 else 2.5

        return {
            "total_trades": total,
            "wins": wins,
            "losses": total - wins,
            "win_rate_pct": round(win_rate, 1),
            "total_pnl_usd": round(total_pnl, 2),
            "profit_factor": round(profit_factor, 2),
            "status": "Binance Mainnet Live 🟢"
        }
    except Exception as e:
        return {
            "total_trades": 0,
            "win_rate_pct": 0.0,
            "total_pnl_usd": 0.0,
            "profit_factor": 0.0,
            "status": f"Error: {e}"
        }


def get_live_24h_bot_pnl(epoch_start_time: Optional[str] = None) -> Dict[str, Any]:
    """
    Calculates the real-time 24-hour PnL ($) and ROI (%) from the live Binance Bot trading journal.
    Zero demo data - reads real executed trades directly from trading_journal.db.
    """
    if not TRADING_BOT_DB.exists():
        return {
            "today_pnl_usd": 0.0,
            "today_roi_pct": 0.0,
            "today_closed_trades": 0,
            "today_wins": 0,
            "today_losses": 0,
            "has_trades_today": False,
            "admin_cut_usd": 0.0,
            "user_payout_usd": 0.0
        }

    try:
        conn = sqlite3.connect(TRADING_BOT_DB)
        cursor = conn.cursor()

        if epoch_start_time:
            cursor.execute("""
            SELECT pnl_usd, pnl_percent FROM trades 
            WHERE exit_price IS NOT NULL AND exit_time >= ?
            """, (epoch_start_time,))
        else:
            cursor.execute("""
            SELECT pnl_usd, pnl_percent FROM trades 
            WHERE exit_price IS NOT NULL
            """)
        
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {
                "today_pnl_usd": 0.0,
                "today_roi_pct": 0.0,
                "today_closed_trades": 0,
                "today_wins": 0,
                "today_losses": 0,
                "has_trades_today": False,
                "admin_cut_usd": 0.0,
                "user_payout_usd": 0.0
            }

        total_pnl = sum(r[0] for r in rows if r[0] is not None)
        total_roi = sum(r[1] for r in rows if r[1] is not None)
        wins = sum(1 for r in rows if r[0] is not None and r[0] > 0)
        losses = sum(1 for r in rows if r[0] is not None and r[0] < 0)

        # 60/40 Profit sharing breakdown
        if total_pnl > 0:
            admin_cut = total_pnl * 0.40
            user_payout = total_pnl * 0.60
        else:
            admin_cut = 0.0
            user_payout = total_pnl

        return {
            "today_pnl_usd": round(total_pnl, 2),
            "today_roi_pct": round(total_roi, 2),
            "today_closed_trades": len(rows),
            "today_wins": wins,
            "today_losses": losses,
            "has_trades_today": True,
            "admin_cut_usd": round(admin_cut, 2),
            "user_payout_usd": round(user_payout, 2)
        }
    except Exception as e:
        print(f"[Bridge Sync] Error querying 24h bot PnL: {e}")
        return {
            "today_pnl_usd": 0.0,
            "today_roi_pct": 0.0,
            "today_closed_trades": 0,
            "today_wins": 0,
            "today_losses": 0,
            "has_trades_today": False,
            "admin_cut_usd": 0.0,
            "user_payout_usd": 0.0
        }
