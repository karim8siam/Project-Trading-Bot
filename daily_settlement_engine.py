"""
Daily Profit/Loss Settlement Engine for ApexTrade AI.
Implements the core business logic:
- On WIN (ROI > 0%): 60% credited to User, 40% deducted as System Platform Fee.
- On LOSS (ROI <= 0%): No 60/40 rule. Full 100% loss deducted directly from User balance (0% System fee).
"""

from datetime import datetime
from typing import Dict, Any, List, Optional
from database import (
    get_active_trading_users,
    record_user_settlement,
    get_or_create_active_batch,
    get_user_settlements,
    get_all_settlements
)
from google_sheets_sync import GoogleSheetsSync


def calculate_settlement_breakdown(starting_balance: float, daily_roi_pct: float) -> Dict[str, Any]:
    """
    Computes exact settlement mathematical breakdown for a given balance and daily ROI.
    - Win (> 0): 60% to User, 40% to System.
    - Loss (<= 0): 100% direct loss to User, 0% to System.
    """
    starting_balance = float(starting_balance)
    daily_roi_pct = float(daily_roi_pct)

    if daily_roi_pct > 0:
        # WIN RULE: 60/40 Split
        is_win = 1
        user_net_pct = round(daily_roi_pct * 0.60, 4)
        system_cut_pct = round(daily_roi_pct * 0.40, 4)
        user_pnl_usdt = round(starting_balance * (user_net_pct / 100.0), 4)
        system_fee_usdt = round(starting_balance * (system_cut_pct / 100.0), 4)
        ending_balance = round(starting_balance + user_pnl_usdt, 4)
        rule_applied = "60_40_WIN_SPLIT"
    else:
        # LOSS RULE: 100% Direct Loss to User, 0% System Fee
        is_win = 0
        user_net_pct = round(daily_roi_pct, 4)
        system_cut_pct = 0.0
        user_pnl_usdt = round(starting_balance * (daily_roi_pct / 100.0), 4)
        system_fee_usdt = 0.0
        ending_balance = round(max(0.0, starting_balance + user_pnl_usdt), 4)
        rule_applied = "100_PERCENT_DIRECT_LOSS"

    return {
        "starting_balance": starting_balance,
        "daily_roi_pct": daily_roi_pct,
        "is_win": is_win,
        "user_net_pct": user_net_pct,
        "system_cut_pct": system_cut_pct,
        "user_pnl_usdt": user_pnl_usdt,
        "system_fee_usdt": system_fee_usdt,
        "ending_balance": ending_balance,
        "rule_applied": rule_applied
    }


def execute_daily_settlement(
    daily_roi_pct: float,
    batch_id: Optional[str] = None,
    settlement_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Processes daily P&L settlement across all active traders in the pool.
    Updates each user balance and syncs results to Google Sheets.
    """
    if not settlement_date:
        settlement_date = datetime.utcnow().strftime("%Y-%m-%d")

    if not batch_id:
        active_batch = get_or_create_active_batch()
        batch_id = active_batch["batch_id"]

    active_users = get_active_trading_users()
    if not active_users:
        return {
            "success": True,
            "message": "No active traders with balance >= 1.0 USDT found to settle.",
            "settled_count": 0,
            "total_user_pnl_usdt": 0.0,
            "total_system_fee_usdt": 0.0
        }

    settled_records = []
    total_starting_tvl = 0.0
    total_ending_tvl = 0.0
    total_user_pnl = 0.0
    total_system_fees = 0.0

    print(f"\n[Daily Settlement Engine] ⚖️ Executing settlement for {settlement_date} (Daily ROI: {daily_roi_pct:+.2f}%)...")

    for user in active_users:
        user_id = user["id"]
        start_bal = float(user["balance_usdt"])
        breakdown = calculate_settlement_breakdown(start_bal, daily_roi_pct)

        record = record_user_settlement(
            batch_id=batch_id,
            settlement_date=settlement_date,
            user_id=user_id,
            starting_balance=breakdown["starting_balance"],
            daily_roi_pct=breakdown["daily_roi_pct"],
            is_win=breakdown["is_win"],
            user_net_pct=breakdown["user_net_pct"],
            system_cut_pct=breakdown["system_cut_pct"],
            user_pnl_usdt=breakdown["user_pnl_usdt"],
            system_fee_usdt=breakdown["system_fee_usdt"],
            ending_balance=breakdown["ending_balance"]
        )
        record["email"] = user["email"]
        record["bep20_address"] = user["bep20_address"]
        settled_records.append(record)

        total_starting_tvl += breakdown["starting_balance"]
        total_ending_tvl += breakdown["ending_balance"]
        total_user_pnl += breakdown["user_pnl_usdt"]
        total_system_fees += breakdown["system_fee_usdt"]

    # Sync summary to Google Sheets
    try:
        sheets_sync = GoogleSheetsSync()
        sheets_sync.calculate_and_sync_daily_summary(target_date=settlement_date)
    except Exception as e:
        print(f"[Daily Settlement Engine] Google Sheets sync notice: {e}")

    summary = {
        "success": True,
        "settlement_date": settlement_date,
        "batch_id": batch_id,
        "daily_roi_pct": daily_roi_pct,
        "is_win": bool(daily_roi_pct > 0),
        "rule_applied": "60% User / 40% System" if daily_roi_pct > 0 else "100% Direct User Loss (0% System Fee)",
        "settled_count": len(settled_records),
        "total_starting_tvl": round(total_starting_tvl, 2),
        "total_ending_tvl": round(total_ending_tvl, 2),
        "total_user_pnl_usdt": round(total_user_pnl, 2),
        "total_system_fee_usdt": round(total_system_fees, 2),
        "records": settled_records
    }

    # Sync to Google Sheets
    try:
        sheets_sync = GoogleSheetsSync()
        sheets_sync.sync_settlement_to_google_sheets(summary)
    except Exception as e:
        print(f"[Daily Settlement Engine] Google Sheets sync notice: {e}")

    print(f"[Daily Settlement Engine] ✅ Completed settlement for {len(settled_records)} users.")
    print(f"💰 Total User PnL: {total_user_pnl:+.2f} USDT | 🏦 Total System Revenue: +{total_system_fees:.2f} USDT")

    return summary
