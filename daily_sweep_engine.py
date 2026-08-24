"""
Daily Capital Accumulation & Automated Sweep Engine for ApexTrade AI.
Consolidates all un-swept user deposits received during the 24-hour cycle
and sweeps them daily at 00:00 UTC (12:00 AM UTC) to the Binance Trading Bot Hot Wallet.
"""

import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from config import (
    PLATFORM_DEPOSIT_ADDRESS,
    BINANCE_BOT_WALLET_ADDRESS,
    DAILY_SWEEP_HOUR_UTC,
    DAILY_SWEEP_MINUTE_UTC,
    AUTO_SWEEP_ENABLED
)
from database import (
    get_or_create_active_batch,
    get_current_batch_summary,
    execute_daily_sweep,
    get_batch_history
)


def get_next_sweep_datetime() -> datetime:
    """Calculates the next target datetime for the daily 00:00 UTC sweep."""
    now_utc = datetime.utcnow()
    target_today = now_utc.replace(
        hour=DAILY_SWEEP_HOUR_UTC,
        minute=DAILY_SWEEP_MINUTE_UTC,
        second=0,
        microsecond=0
    )
    if now_utc >= target_today:
        target_today += timedelta(days=1)
    return target_today


def get_seconds_until_next_sweep() -> int:
    """Returns number of seconds remaining until the next 00:00 UTC sweep cutoff."""
    target = get_next_sweep_datetime()
    now = datetime.utcnow()
    diff = int((target - now).total_seconds())
    return max(diff, 0)


def perform_sweep_now(batch_id: Optional[str] = None, sweep_tx_hash: Optional[str] = None) -> Dict[str, Any]:
    """
    Executes consolidation and sweeps the specified or current active batch
    from the System Deposit Address to the Binance Bot Hot Wallet.
    """
    summary = get_current_batch_summary()
    target_batch = batch_id or summary["batch_id"]

    print(f"\n[Daily Sweep Engine] 🔄 Triggering daily sweep for {target_batch}...")
    print(f"[Daily Sweep Engine] 💰 Total Pool Capital: {summary['total_amount_usdt']:.2f} USDT across {summary['unique_participants']} participants")
    print(f"[Daily Sweep Engine] 🎯 Destination Binance Hot Wallet: {BINANCE_BOT_WALLET_ADDRESS}")

    result = execute_daily_sweep(batch_id=target_batch, sweep_tx_hash=sweep_tx_hash)

    # Immediately ensure a fresh batch is opened for the new incoming deposits
    get_or_create_active_batch()

    return result


class DailySweepScheduler(threading.Thread):
    """Background daemon worker checking for the daily sweep trigger."""

    def __init__(self, check_interval_seconds: int = 30):
        super().__init__(daemon=True)
        self.check_interval = check_interval_seconds
        self.running = True
        self.last_swept_date = None

    def run(self):
        print(f"[Daily Sweep Scheduler] 🕒 Scheduler active. Automated daily sweep at {DAILY_SWEEP_HOUR_UTC:02d}:{DAILY_SWEEP_MINUTE_UTC:02d} UTC.")
        while self.running:
            try:
                now_utc = datetime.utcnow()
                today_str = now_utc.strftime("%Y-%m-%d")

                # Check if current time matches sweep cutoff window (within 1 minute)
                if (AUTO_SWEEP_ENABLED and
                    now_utc.hour == DAILY_SWEEP_HOUR_UTC and
                    now_utc.minute == DAILY_SWEEP_MINUTE_UTC and
                    self.last_swept_date != today_str):

                    print(f"[Daily Sweep Scheduler] ⚡ 00:00 UTC Cutoff reached! Initiating daily sweep for date {today_str}...")
                    perform_sweep_now()
                    self.last_swept_date = today_str

            except Exception as e:
                print(f"[Daily Sweep Scheduler] ⚠️ Error during sweep check: {e}")

            time.sleep(self.check_interval)

    def stop(self):
        self.running = False


_scheduler_instance: Optional[DailySweepScheduler] = None


def start_scheduler():
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = DailySweepScheduler()
        _scheduler_instance.start()
