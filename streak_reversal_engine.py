"""
Directional Streak Reversal & Anti-Clustering Engine.
User Custom Rule:
When 4 back-to-back trades have been executed in the same direction (4 LONGs or 4 SHORTs):
- The bot triggers Reversal Priority Mode to seek the REVERSE direction.
- For 5 candles, same-direction trades are filtered while reverse setups are prioritized.
- After 5 candles (or upon executing a reverse trade), normal multi-regime trading automatically resumes.
"""

import time
from typing import Dict, Any, Tuple, Optional
from database import get_recent_executed_trades


class DirectionalStreakReversalEngine:
    def __init__(self, streak_threshold: int = 4, reversal_window_candles: int = 5):
        self.streak_threshold = streak_threshold
        self.reversal_window_candles = reversal_window_candles
        self.active_streak_dir: Optional[str] = None
        self.target_reverse_dir: Optional[str] = None
        self.streak_trigger_time: float = 0.0
        self.reversal_trades_taken: int = 0
        self.candle_duration_seconds: float = 60.0  # 1-minute primary execution timeframe
        self.last_handled_streak_id: Optional[str] = None

    def check_streak_status(self) -> Dict[str, Any]:
        """
        Evaluates recent trade executions from the journal.
        Returns the current reversal mode state.
        """
        now = time.time()
        
        # Check if active reversal window has expired or reverse trade was taken
        if self.active_streak_dir:
            elapsed_seconds = now - self.streak_trigger_time
            elapsed_candles = elapsed_seconds / self.candle_duration_seconds
            if elapsed_candles >= self.reversal_window_candles or self.reversal_trades_taken > 0:
                # 5 candles elapsed or reverse trade taken -> Reset to normal
                self.active_streak_dir = None
                self.target_reverse_dir = None
                self.streak_trigger_time = 0.0
                self.reversal_trades_taken = 0

        # If not currently in reversal mode, check if a new 4-trade streak formed
        if not self.active_streak_dir:
            try:
                recent_trades = get_recent_executed_trades(limit=self.streak_threshold)
                if len(recent_trades) >= self.streak_threshold:
                    streak_signature = "-".join([str(t.get("trade_id", t.get("id", ""))) for t in recent_trades])
                    if streak_signature != self.last_handled_streak_id:
                        dirs = [t.get("direction", "").upper() for t in recent_trades]
                        if all(d == "LONG" for d in dirs):
                            self.active_streak_dir = "LONG"
                            self.target_reverse_dir = "SHORT"
                            self.streak_trigger_time = now
                            self.reversal_trades_taken = 0
                            self.last_handled_streak_id = streak_signature
                        elif all(d == "SHORT" for d in dirs):
                            self.active_streak_dir = "SHORT"
                            self.target_reverse_dir = "LONG"
                            self.streak_trigger_time = now
                            self.reversal_trades_taken = 0
                            self.last_handled_streak_id = streak_signature
            except Exception:
                pass

        is_reversal_active = (self.active_streak_dir is not None)
        elapsed = (now - self.streak_trigger_time) if is_reversal_active else 0.0
        rem_candles = max(0.0, self.reversal_window_candles - (elapsed / self.candle_duration_seconds)) if is_reversal_active else 0.0

        return {
            "is_active": is_reversal_active,
            "streak_direction": self.active_streak_dir,
            "target_reverse_direction": self.target_reverse_dir,
            "remaining_candles": round(rem_candles, 1),
            "desc": (
                f"4 Back-to-Back {self.active_streak_dir} trades detected -> Seeking {self.target_reverse_dir} reversal setups ({round(rem_candles, 1)} candles remaining in window)"
                if is_reversal_active else "Normal Multi-Regime Operation"
            )
        }

    def evaluate_signal_filter(self, proposed_direction: str) -> Tuple[bool, str]:
        """
        Validates if a signal should be allowed or filtered based on the 4-trade streak rule.
        Returns: (allowed: bool, reason: str)
        """
        status = self.check_streak_status()
        if not status["is_active"]:
            return True, "Normal Strategy Rules Active"

        target_dir = status["target_reverse_direction"]
        streak_dir = status["streak_direction"]

        if proposed_direction == target_dir:
            return True, f"Reversal Engine Priority: Seeking {target_dir} reversal after 4 consecutive {streak_dir} trades 🔥"
        elif proposed_direction == streak_dir:
            return False, f"Streak Anti-Clustering Filter: 4 back-to-back {streak_dir} trades reached. Prioritizing {target_dir} reversals ({status['remaining_candles']} candles remaining)."

        return True, "Normal Strategy Rules Active"

    def record_trade_executed(self, direction: str):
        """Notifies the engine that a trade has been executed."""
        if self.active_streak_dir and direction == self.target_reverse_dir:
            self.reversal_trades_taken += 1
            # Reset immediately
            self.active_streak_dir = None
            self.target_reverse_dir = None
            self.streak_trigger_time = 0.0
            self.reversal_trades_taken = 0


streak_reversal_engine = DirectionalStreakReversalEngine(streak_threshold=4, reversal_window_candles=5)
