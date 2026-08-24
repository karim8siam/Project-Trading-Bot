"""
Portfolio Delta Hedge & Counter-Trend Sniper Engine.
Monitors portfolio directional correlation and executes relative-weakness counter-hedges
to neutralize systemic beta pullbacks and protect account capital.
"""

import time
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
from config import ALLOWED_SYMBOLS
from indicators import add_all_indicators
from data_fetcher import data_fetcher


class PortfolioHedger:
    def __init__(self):
        self.max_hedges = 1  # Maximum 1 active hedge at a time
        self.min_skew_positions = 4  # Trigger when >= 4 positions in same direction
        self.drawdown_threshold_pct = 0.80  # Dynamic trigger: 0.80% portfolio drawdown
        self.max_allowed_drawdown_pct = 5.00  # Hard ceiling: strictly <= 5.0%
        self.last_scan_time = 0.0

    def evaluate_portfolio_state(self, open_trades: List[Dict[str, Any]], total_balance: float = 13.0) -> Dict[str, Any]:
        """
        Evaluates portfolio skew and dynamic percentage-based unrealized drawdown
        relative to the live total wallet balance.
        """
        long_count = sum(1 for t in open_trades if t.get("direction") == "LONG")
        short_count = sum(1 for t in open_trades if t.get("direction") == "SHORT")
        hedge_count = sum(1 for t in open_trades if t.get("is_hedge", 0) == 1 or "HEDGE" in str(t.get("strategy", "")))

        # Calculate live unrealized PnL in USD and in Percentage (%)
        total_unrealized_pnl = 0.0
        active_symbols = set()

        for t in open_trades:
            sym = t.get("symbol", "")
            active_symbols.add(sym)
            try:
                ep = float(t.get("entry_price", 0.0))
                qty = float(t.get("quantity", 0.0))
                d = t.get("direction", "LONG")
                curr_p = data_fetcher.fetch_current_price(sym)
                if curr_p and ep > 0:
                    if d == "LONG":
                        pnl = (curr_p - ep) * qty
                    else:
                        pnl = (ep - curr_p) * qty
                    total_unrealized_pnl += pnl
            except Exception:
                pass

        # Dynamic Drawdown Percentage of Live Account Balance
        safe_bal = max(total_balance, 1.0)
        drawdown_pct = (total_unrealized_pnl / safe_bal) * 100.0

        # Determine if Delta Hedge is needed
        hedge_needed = False
        hedge_direction = "SHORT"
        reason = ""

        # Condition 1: Heavy Long Skew (>= 3 Longs and 0 Shorts)
        if long_count >= 3 and short_count == 0:
            hedge_needed = True
            hedge_direction = "SHORT"
            reason = f"Directional Long Skew ({long_count} Longs / 0 Shorts). Short Counter-Hedge needed."

        # Condition 2: Heavy Short Skew (>= 3 Shorts and 0 Longs)
        elif short_count >= 3 and long_count == 0:
            hedge_needed = True
            hedge_direction = "LONG"
            reason = f"Directional Short Skew ({short_count} Shorts / 0 Longs). Long Counter-Hedge needed."

        return {
            "long_count": long_count,
            "short_count": short_count,
            "hedge_count": short_count if hedge_direction == "SHORT" else long_count,
            "total_unrealized_pnl": round(total_unrealized_pnl, 4),
            "drawdown_pct": round(drawdown_pct, 2),
            "active_symbols": list(active_symbols),
            "hedge_needed": hedge_needed,
            "hedge_direction": hedge_direction,
            "reason": reason
        }

    def scan_for_hedge_candidate(self, active_symbols: List[str], target_direction: str = "SHORT") -> Optional[Dict[str, Any]]:
        """
        Scans all whitelist pairs (excluding currently held symbols) to find the
        single best candidate based on Relative Weakness Index (RWI).
        """
        candidates = []

        # Exclude currently held symbols to avoid self-cannibalization
        held_set = set(active_symbols)

        for symbol in ALLOWED_SYMBOLS:
            if symbol in held_set:
                continue

            try:
                df_1h = data_fetcher.fetch_ohlcv(symbol, timeframe="1h", limit=50)
                df_15m = data_fetcher.fetch_ohlcv(symbol, timeframe="15m", limit=50)

                if df_1h is None or df_1h.empty or df_15m is None or df_15m.empty:
                    continue

                df_1h = add_all_indicators(df_1h)
                df_15m = add_all_indicators(df_15m)

                row_1h = df_1h.iloc[-1]
                row_15m = df_15m.iloc[-1]

                close_1h = float(row_1h["close"])
                ema50_1h = float(row_1h.get("ema_50", close_1h))
                ema200_1h = float(row_1h.get("ema_200", close_1h))

                close_15m = float(row_15m["close"])
                atr_15m = float(row_15m.get("atr", close_15m * 0.015))

                if target_direction == "SHORT":
                    # Relative Weakness Score:
                    # 1. Distance below 1H EMA 50 & EMA 200
                    # 2. Bearish momentum (RSI < 50, ADX strength)
                    ema_dist_pct = ((ema50_1h - close_1h) / ema50_1h) * 100.0
                    rsi_15m = float(row_15m.get("rsi", 50))
                    adx_15m = float(row_15m.get("adx", 20))

                    # Calculate 1H Return
                    ret_1h = ((close_1h - float(df_1h.iloc[0]["close"])) / float(df_1h.iloc[0]["close"])) * 100.0

                    weakness_score = 0.0
                    if close_1h < ema50_1h:
                        weakness_score += 35.0
                    if close_1h < ema200_1h:
                        weakness_score += 25.0
                    if rsi_15m < 45.0:
                        weakness_score += 20.0
                    if ret_1h < 0:
                        weakness_score += abs(ret_1h) * 5.0

                    # Swing high for tight stop loss
                    swing_high = float(df_15m["high"].iloc[-8:].max())
                    tight_sl = max(swing_high * 1.002, close_15m + (atr_15m * 1.2))
                    sl_dist = abs(tight_sl - close_15m)
                    fast_tp = close_15m - (sl_dist * 1.2)

                    candidates.append({
                        "symbol": symbol,
                        "direction": "SHORT",
                        "score": round(weakness_score, 1),
                        "current_price": close_15m,
                        "stop_loss": round(tight_sl, 4),
                        "take_profit": round(fast_tp, 4),
                        "atr": atr_15m,
                        "strategy": "DELTA_HEDGE_SNIPER",
                        "reason": f"Relative Weakness Leader (Score: {weakness_score:.1f} | Price < 1H EMA50)"
                    })

            except Exception:
                continue

        if not candidates:
            return None

        # Sort by highest relative weakness score
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[0]


# Global Portfolio Hedger Instance
portfolio_hedger = PortfolioHedger()
