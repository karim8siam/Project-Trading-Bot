"""
24-Hour Epoch Vault & Yield Distribution Engine for Orbital Trading.
Manages:
- Daily 24-hour trading pool aggregation
- Proportional user pool share calculations
- Daily ROI % distribution from trading bot results
- 20% Platform Performance Fee deduction on profit days (0% on loss days)
"""

import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from config import (
    EPOCH_ROLLOVER_HOUR_UTC,
    PLATFORM_PERFORMANCE_FEE_PCT,
    USER_PROFIT_SHARE_PCT
)
from database import get_db


class VaultEpochEngine:
    """
    Manages daily 24-hour pooled trading vaults and proportional profit allocations.
    """

    def get_or_create_active_epoch(self) -> Dict[str, Any]:
        """
        Retrieves the currently active 24-hour trading epoch or initializes a new one.
        """
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM vault_epochs WHERE status IN ('OPEN', 'TRADING') ORDER BY epoch_id DESC LIMIT 1")
        epoch = cursor.fetchone()

        now = datetime.utcnow()

        if not epoch:
            # Create first initial epoch
            epoch_id = int(now.strftime("%Y%m%d"))
            start_time = now.strftime("%Y-%m-%d %H:%M:%S")

            # Calculate total pooled vault balance across all users
            cursor.execute("SELECT SUM(active_vault_balance) FROM users")
            total_pool = cursor.fetchone()[0] or 0.0

            cursor.execute("""
            INSERT INTO vault_epochs (
                epoch_id, start_time, starting_pool_usdt, status
            ) VALUES (?, ?, ?, 'OPEN')
            """, (epoch_id, start_time, total_pool))
            conn.commit()

            cursor.execute("SELECT * FROM vault_epochs WHERE epoch_id = ?", (epoch_id,))
            epoch = cursor.fetchone()

        # Calculate time remaining until next 12:00 UTC rollover
        rollover_today = now.replace(hour=EPOCH_ROLLOVER_HOUR_UTC, minute=0, second=0, microsecond=0)
        if now >= rollover_today:
            next_rollover = rollover_today + timedelta(days=1)
        else:
            next_rollover = rollover_today

        seconds_remaining = max(0, int((next_rollover - now).total_seconds()))
        hours = seconds_remaining // 3600
        minutes = (seconds_remaining % 3600) // 60
        seconds = seconds_remaining % 60

        cursor.execute("SELECT SUM(active_vault_balance) FROM users")
        current_pool = cursor.fetchone()[0] or 0.0

        cursor.execute("SELECT COUNT(*) FROM users WHERE active_vault_balance > 0")
        active_investors = cursor.fetchone()[0] or 0

        conn.close()

        return {
            "epoch_id": epoch["epoch_id"],
            "status": epoch["status"],
            "start_time": epoch["start_time"],
            "starting_pool_usdt": epoch["starting_pool_usdt"],
            "current_pool_usdt": round(current_pool, 2),
            "active_investors": active_investors,
            "next_rollover_utc": next_rollover.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "seconds_remaining": seconds_remaining,
            "time_remaining_formatted": f"{hours:02d}h {minutes:02d}m {seconds:02d}s"
        }

    def get_user_vault_summary(self, user_uuid: str) -> Dict[str, Any]:
        """
        Calculates user's personal vault balance, pool percentage share, and projected earnings.
        """
        epoch_info = self.get_or_create_active_epoch()
        total_pool = epoch_info["current_pool_usdt"]

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_uuid = ?", (user_uuid,))
        user = cursor.fetchone()
        conn.close()

        if not user:
            return {}

        user_vault_bal = float(user["active_vault_balance"] or 0.0)
        pool_share_pct = (user_vault_bal / total_pool * 100.0) if total_pool > 0 else 0.0

        return {
            "user_uuid": user_uuid,
            "balance_usdt": round(user["balance_usdt"], 2),
            "active_vault_balance": round(user_vault_bal, 2),
            "pending_rollover_balance": round(user["pending_rollover_balance"] or 0.0, 2),
            "is_compounding": int(user["is_compounding"] if user["is_compounding"] is not None else 1),
            "compounding_status": user["compounding_status"] or "ACTIVE",
            "total_deposited": round(user["total_deposited"], 2),
            "total_withdrawn": round(user["total_withdrawn"], 2),
            "total_profit_earned": round(user["total_profit_earned"], 2),
            "pool_share_pct": round(pool_share_pct, 4),
            "epoch_info": epoch_info
        }

    def toggle_compounding(self, user_uuid: str, enable: bool) -> Dict[str, Any]:
        """
        Toggles auto-compounding on or off for a user.
        When turned OFF, funds complete the current 24-hour epoch and release to withdrawable balance at 12:00 AM midnight.
        """
        conn = get_db()
        cursor = conn.cursor()
        new_val = 1 if enable else 0
        new_status = 'ACTIVE' if enable else 'STOPPING_AT_NEXT_ROLLOVER'

        cursor.execute("""
        UPDATE users SET is_compounding = ?, compounding_status = ? WHERE user_uuid = ?
        """, (new_val, new_status, user_uuid))
        conn.commit()
        conn.close()

        if enable:
            msg = "✅ Auto-Compounding Activated! Your full balance and daily profits will automatically roll over every day at 12:00 AM midnight."
        else:
            msg = "⏳ Auto-Compounding Stopping: Your funds will finish today's 24-hour trading round until the 12:00 AM midnight rollover, then release to your withdrawable wallet."

        return {
            "success": True,
            "is_compounding": new_val,
            "compounding_status": new_status,
            "message": msg
        }

    def get_admin_collection_stats(self) -> Dict[str, Any]:
        """
        Computes total USDT deposits collected in current 24-hour epoch for next rollover.
        """
        epoch = self.get_or_create_active_epoch()
        start_time = epoch["start_time"]

        conn = get_db()
        cursor = conn.cursor()

        # Sum of verified deposits in current epoch
        cursor.execute("""
        SELECT 
            COALESCE(SUM(amount_usdt), 0.0) as today_total,
            COUNT(*) as deposit_count,
            COUNT(DISTINCT user_uuid) as unique_depositors
        FROM deposits 
        WHERE status = 'VERIFIED' AND created_at >= ?
        """, (start_time,))
        res = cursor.fetchone()

        # Total all-time vault pool across all users
        cursor.execute("SELECT COALESCE(SUM(active_vault_balance), 0.0) FROM users")
        active_pool = cursor.fetchone()[0] or 0.0

        cursor.execute("SELECT COUNT(*) FROM users WHERE active_vault_balance > 0")
        total_active_investors = cursor.fetchone()[0] or 0

        conn.close()

        return {
            "epoch_id": epoch["epoch_id"],
            "epoch_start_time": start_time,
            "today_collection_usdt": round(float(res["today_total"]), 2),
            "today_deposit_count": int(res["deposit_count"]),
            "today_unique_depositors": int(res["unique_depositors"]),
            "total_active_pool_usdt": round(float(active_pool), 2),
            "total_active_investors": int(total_active_investors),
            "next_rollover_utc": epoch["next_rollover_utc"],
            "time_remaining_formatted": epoch["time_remaining_formatted"]
        }

    def get_previous_day_reconciliation(self) -> Dict[str, Any]:
        """
        Computes Previous Day Collection, Outgoing to Binance, and Outgoing Withdrawals.
        """
        conn = get_db()
        cursor = conn.cursor()

        # Get last settled epoch
        cursor.execute("SELECT * FROM vault_epochs WHERE status = 'SETTLED' ORDER BY epoch_id DESC LIMIT 1")
        prev_epoch = cursor.fetchone()

        # Get all historical epochs for table
        cursor.execute("SELECT * FROM vault_epochs ORDER BY epoch_id DESC LIMIT 10")
        all_epochs_raw = cursor.fetchall()

        epochs_history = []
        for ep in all_epochs_raw:
            ep_id = ep["epoch_id"]
            # Deposits in this epoch
            cursor.execute("""
            SELECT COALESCE(SUM(amount_usdt), 0.0) FROM deposits 
            WHERE status = 'VERIFIED' AND created_at >= ? AND created_at <= ?
            """, (ep["start_time"], ep["settled_at"] or "9999-12-31"))
            dep_sum = cursor.fetchone()[0] or 0.0

            # Sweeps to binance
            cursor.execute("""
            SELECT COALESCE(SUM(amount_usdt), 0.0) FROM sweeps 
            WHERE epoch_id = ? OR (created_at >= ? AND created_at <= ?)
            """, (ep_id, ep["start_time"], ep["settled_at"] or "9999-12-31"))
            sweep_sum = cursor.fetchone()[0] or 0.0

            # Withdrawals
            cursor.execute("""
            SELECT COALESCE(SUM(amount_usdt), 0.0) FROM withdrawals 
            WHERE status = 'COMPLETED' AND created_at >= ? AND created_at <= ?
            """, (ep["start_time"], ep["settled_at"] or "9999-12-31"))
            wth_sum = cursor.fetchone()[0] or 0.0

            epochs_history.append({
                "epoch_id": ep_id,
                "start_time": ep["start_time"],
                "settled_at": ep["settled_at"] or "IN PROGRESS",
                "starting_pool": round(float(ep["starting_pool_usdt"]), 2),
                "collection_usdt": round(float(dep_sum), 2),
                "outgoing_to_binance": round(float(sweep_sum), 2),
                "outgoing_withdrawals": round(float(wth_sum), 2),
                "daily_roi_pct": round(float(ep["daily_roi_pct"] or 0.0), 2),
                "status": ep["status"]
            })

        # Previous day stats summary
        if prev_epoch:
            ep_id = prev_epoch["epoch_id"]
            cursor.execute("""
            SELECT COALESCE(SUM(amount_usdt), 0.0) FROM deposits 
            WHERE status = 'VERIFIED' AND created_at >= ? AND created_at <= ?
            """, (prev_epoch["start_time"], prev_epoch["settled_at"] or "9999-12-31"))
            prev_dep = cursor.fetchone()[0] or 0.0

            cursor.execute("""
            SELECT COALESCE(SUM(amount_usdt), 0.0) FROM sweeps 
            WHERE epoch_id = ? OR (created_at >= ? AND created_at <= ?)
            """, (ep_id, prev_epoch["start_time"], prev_epoch["settled_at"] or "9999-12-31"))
            prev_sweep = cursor.fetchone()[0] or 0.0

            cursor.execute("""
            SELECT COALESCE(SUM(amount_usdt), 0.0) FROM withdrawals 
            WHERE status = 'COMPLETED' AND created_at >= ? AND created_at <= ?
            """, (prev_epoch["start_time"], prev_epoch["settled_at"] or "9999-12-31"))
            prev_wth = cursor.fetchone()[0] or 0.0

            prev_stats = {
                "has_prev_day": True,
                "epoch_id": ep_id,
                "settled_at": prev_epoch["settled_at"],
                "prev_collection_usdt": round(float(prev_dep), 2),
                "prev_outgoing_to_binance": round(float(prev_sweep), 2),
                "prev_outgoing_withdrawals": round(float(prev_wth), 2),
                "prev_daily_roi_pct": round(float(prev_epoch["daily_roi_pct"] or 0.0), 2)
            }
        else:
            prev_stats = {
                "has_prev_day": False,
                "epoch_id": "None (First Day)",
                "settled_at": "---",
                "prev_collection_usdt": 0.0,
                "prev_outgoing_to_binance": 0.0,
                "prev_outgoing_withdrawals": 0.0,
                "prev_daily_roi_pct": 0.0
            }

        conn.close()

        return {
            "previous_day": prev_stats,
            "epochs_history": epochs_history
        }

    def settle_epoch_with_daily_bot_performance(
        self,
        daily_roi_pct: float,
        daily_pnl_usd: float
    ) -> Dict[str, Any]:
        """
        Settles active 24-hour epoch by distributing daily bot profit/loss to all depositors.
        - On Profit Days: 20% platform commission fee deducted; 80% distributed to users.
        - On Loss Days: 0% platform fee; exact loss % applied.
        """
        conn = get_db()
        cursor = conn.cursor()

        # Get active epoch
        cursor.execute("SELECT * FROM vault_epochs WHERE status IN ('OPEN', 'TRADING') ORDER BY epoch_id DESC LIMIT 1")
        epoch = cursor.fetchone()
        if not epoch:
            conn.close()
            return {"success": False, "error": "No active epoch found to settle."}

        epoch_id = epoch["epoch_id"]
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        # Get all users with positive active vault balance
        cursor.execute("SELECT user_uuid, active_vault_balance, is_compounding FROM users WHERE active_vault_balance > 0")
        active_users = cursor.fetchall()

        total_pool = sum(float(u["active_vault_balance"]) for u in active_users)
        if total_pool <= 0:
            cursor.execute("UPDATE vault_epochs SET status = 'SETTLED', settled_at = ? WHERE epoch_id = ?", (now_str, epoch_id))
            conn.commit()
            conn.close()
            return {"success": True, "message": "Epoch settled with zero active depositors."}

        # Calculate Net User ROI % and Admin Cut
        if daily_roi_pct > 0:
            # On Profit Days: 40% Admin Cut, 60% Net Yield to Depositor
            platform_cut = (daily_roi_pct * (PLATFORM_PERFORMANCE_FEE_PCT / 100.0))
            net_user_roi_pct = (daily_roi_pct * (USER_PROFIT_SHARE_PCT / 100.0))
            platform_fee_collected = total_pool * (platform_cut / 100.0)
        else:
            # On Loss Days: 0% Admin Cut, 100% Exact Loss Applied to Depositors
            platform_cut = 0.0
            net_user_roi_pct = daily_roi_pct
            platform_fee_collected = 0.0

        # Distribute proportional earnings to each user
        settled_count = 0
        for u in active_users:
            u_uuid = u["user_uuid"]
            u_bal = float(u["active_vault_balance"])
            share_pct = (u_bal / total_pool) * 100.0 if total_pool > 0 else 0.0
            
            user_profit_loss = u_bal * (net_user_roi_pct / 100.0)
            new_vault_bal = max(0.0, u_bal + user_profit_loss)

            # Auto-compounding handling
            is_comp = int(u["is_compounding"] if u["is_compounding"] is not None else 1)
            if is_comp == 1:
                next_active_vault = new_vault_bal
                next_status = 'ACTIVE'
            else:
                # User stopped compounding: Release capital to withdrawable balance!
                next_active_vault = 0.0
                next_status = 'STOPPED'

            # Record share allocation
            cursor.execute("""
            INSERT INTO epoch_shares (
                epoch_id, user_uuid, deposited_amount, pool_share_pct, profit_loss_earned, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """, (epoch_id, u_uuid, u_bal, round(share_pct, 4), round(user_profit_loss, 2), now_str))

            # Update user balances: Add net profit (or subtract loss)
            profit_delta = max(0.0, user_profit_loss)
            cursor.execute("""
            UPDATE users SET
                balance_usdt = balance_usdt + ?,
                active_vault_balance = ?,
                pending_rollover_balance = 0.0,
                compounding_status = ?,
                total_profit_earned = total_profit_earned + ?
            WHERE user_uuid = ?
            """, (round(user_profit_loss, 2), round(next_active_vault, 2), next_status, round(profit_delta, 2), u_uuid))
            settled_count += 1

        # Settle active epoch
        ending_pool = total_pool + (total_pool * (net_user_roi_pct / 100.0))
        cursor.execute("""
        UPDATE vault_epochs SET
            ending_pool_usdt = ?,
            daily_pnl_usd = ?,
            daily_roi_pct = ?,
            platform_fee_collected = ?,
            status = 'SETTLED',
            settled_at = ?
        WHERE epoch_id = ?
        """, (round(ending_pool, 2), round(daily_pnl_usd, 2), round(daily_roi_pct, 2), round(platform_fee_collected, 2), now_str, epoch_id))

        # Initialize the next 24-hour epoch and merge all active balances
        cursor.execute("SELECT MAX(epoch_id) FROM vault_epochs")
        max_ep_row = cursor.fetchone()
        max_ep = (max_ep_row[0] if max_ep_row and max_ep_row[0] else None) or int(datetime.utcnow().strftime("%Y%m%d"))
        next_epoch_id = max_ep + 1

        cursor.execute("SELECT SUM(active_vault_balance) FROM users")
        new_starting_pool = cursor.fetchone()[0] or 0.0

        cursor.execute("SELECT epoch_id FROM vault_epochs WHERE epoch_id = ?", (next_epoch_id,))
        existing_next = cursor.fetchone()
        if not existing_next:
            cursor.execute("""
            INSERT INTO vault_epochs (
                epoch_id, start_time, starting_pool_usdt, status
            ) VALUES (?, ?, ?, 'OPEN')
            """, (next_epoch_id, now_str, round(new_starting_pool, 2)))
        else:
            cursor.execute("""
            UPDATE vault_epochs SET starting_pool_usdt = ?, status = 'OPEN' WHERE epoch_id = ?
            """, (round(new_starting_pool, 2), next_epoch_id))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "epoch_id": epoch_id,
            "settled_investors": settled_count,
            "gross_daily_roi_pct": round(daily_roi_pct, 2),
            "net_user_roi_pct": round(net_user_roi_pct, 2),
            "platform_fee_collected": round(platform_fee_collected, 2),
            "ending_pool_usdt": round(ending_pool, 2),
            "next_epoch_id": next_epoch_id,
            "message": f"Epoch {epoch_id} settled successfully! Net user yield: {net_user_roi_pct:+.2f}%."
        }


# Global Vault Engine Instance
vault_engine = VaultEpochEngine()
