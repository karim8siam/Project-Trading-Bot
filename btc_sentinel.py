"""
Bitcoin Master Sentinel & Multi-Timeframe Pump/Dump Engine.
Observes Bitcoin across 1M, 5M, 15M, 1H, and 4H timeframes to establish
the sovereign directional bias for the entire cryptocurrency futures portfolio.
"""

import time
from typing import Dict, Any, Tuple, Optional
import pandas as pd

from data_fetcher import data_fetcher
from indicators import add_all_indicators


class BTCSentinelEngine:
    def __init__(self):
        self.btc_symbol = "BTC/USDT"
        self.last_check_time = 0.0
        self.cache_ttl = 10.0  # 10-second fast cache
        self.cached_state: Dict[str, Any] = {}
        self.cached_dfs: Dict[str, Optional[pd.DataFrame]] = {}
        self.flash_lockout_until = 0.0

    def fetch_btc_data(self) -> Dict[str, Optional[pd.DataFrame]]:
        """Fetches multi-timeframe candle data for Bitcoin."""
        try:
            df_1m = data_fetcher.fetch_ohlcv(self.btc_symbol, timeframe="1m", limit=30)
            df_5m = data_fetcher.fetch_ohlcv(self.btc_symbol, timeframe="5m", limit=50)
            df_15m = data_fetcher.fetch_ohlcv(self.btc_symbol, timeframe="15m", limit=60)
            df_1h = data_fetcher.fetch_ohlcv(self.btc_symbol, timeframe="1h", limit=50)
            dfs = {
                "1m": df_1m,
                "5m": df_5m,
                "15m": df_15m,
                "1h": df_1h
            }
            self.cached_dfs = dfs
            return dfs
        except Exception as e:
            print(f"[BTC Sentinel] Error fetching BTC data: {e}")
            return {"1m": None, "5m": None, "15m": None, "1h": None}

    def get_btc_state(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Evaluates Bitcoin's Multi-Timeframe Sovereign State:
        - 1M Shockwave / Flash Pump & Dump Detector
        - 5M & 15M Intraday Momentum & VWAP
        - 1H Macro Directional Flow
        """
        now = time.time()
        if not force_refresh and self.cached_state and (now - self.last_check_time) < self.cache_ttl:
            return self.cached_state

        # Check ongoing flash lockout
        if now < self.flash_lockout_until:
            rem_secs = int(self.flash_lockout_until - now)
            state = {
                "state": "BTC_CASCADE_FREEZE",
                "bias": "NEUTRAL_LOCKED",
                "allow_long": False,
                "allow_short": False,
                "btc_price": self.cached_state.get("btc_price", 0.0),
                "roc_3m": self.cached_state.get("roc_3m", 0.0),
                "reason": f"Bitcoin Flash Shockwave Lockout Active ({rem_secs}s remaining)",
                "timestamp": now
            }
            self.cached_state = state
            return state

        data = self.fetch_btc_data()
        df_1m = data.get("1m")
        df_15m = data.get("15m")
        df_1h = data.get("1h")

        if df_15m is None or df_15m.empty or df_1h is None or df_1h.empty:
            # Fallback state if API rate limited
            return self.cached_state or {
                "state": "BTC_BALANCED_RANGE",
                "bias": "NEUTRAL",
                "allow_long": True,
                "allow_short": True,
                "btc_price": 0.0,
                "reason": "BTC Data Stream Buffering"
            }

        # 1. Flash Shockwave Check (1M micro-data)
        roc_3m = 0.0
        is_flash_spike = False
        if df_1m is not None and not df_1m.empty and len(df_1m) >= 5:
            last_p = float(df_1m.iloc[-1]["close"])
            prev_p = float(df_1m.iloc[-4]["close"])
            roc_3m = ((last_p - prev_p) / prev_p) * 100.0

            # Detect extreme rapid liquidation wicks (> 0.40% in 3 mins)
            if abs(roc_3m) >= 0.40:
                is_flash_spike = True
                self.flash_lockout_until = now + 120.0  # 2-minute cooling lockout

        # 2. 15-Minute Macro Analysis (Aligns with 1M/15M Architecture)
        df_15m = add_all_indicators(df_15m)
        m15_last = df_15m.iloc[-1]
        m15_close = float(m15_last["close"])
        m15_ema20 = float(m15_last.get("ema_20", m15_close))
        m15_ema50 = float(m15_last.get("ema_50", m15_close))
        m15_rsi = float(m15_last.get("rsi_14", 50.0))
        m15_adx = float(m15_last.get("adx_14", 20.0))

        macro_bull = m15_close > m15_ema50 and m15_ema20 >= m15_ema50
        macro_bear = m15_close < m15_ema50 and m15_ema20 <= m15_ema50

        # 3. 5-Minute Intermediate Momentum Analysis
        df_5m = data.get("5m")
        if df_5m is not None and not df_5m.empty:
            df_5m = add_all_indicators(df_5m)
            m5_last = df_5m.iloc[-1]
            m5_close = float(m5_last["close"])
            m5_ema9 = float(m5_last.get("ema_9", m5_close))
            m5_ema21 = float(m5_last.get("ema_21", m5_close))
            intra_bull = m5_close > m5_ema21 and m5_ema9 >= m5_ema21
            intra_bear = m5_close < m5_ema21 and m5_ema9 <= m5_ema21
        else:
            intra_bull = macro_bull
            intra_bear = macro_bear

        # 4. State Synthesis
        if is_flash_spike:
            state_name = "BTC_CASCADE_FREEZE"
            bias = "NEUTRAL_LOCKED"
            allow_long = False
            allow_short = False
            reason = f"BTC Flash Shockwave ({roc_3m:+.2f}% 3m Spike). Scalping paused for 2 mins."
        elif macro_bull and intra_bull:
            state_name = "BTC_EXPANSION_BULL"
            bias = "AGGRESSIVE_BULL"
            allow_long = True
            allow_short = False  # Strictly NO shorts when BTC is pumping
            reason = f"Bitcoin Pumping: 15M & 5M Bull Alignment (Price: ${m15_close:,.2f} > 15M EMA50 ${m15_ema50:,.2f})"
        elif macro_bear and intra_bear:
            state_name = "BTC_EXPANSION_BEAR"
            bias = "AGGRESSIVE_BEAR"
            allow_long = False  # Strictly NO longs when BTC is dumping
            allow_short = True
            reason = f"Bitcoin Dumping: 15M & 5M Bear Alignment (Price: ${m15_close:,.2f} < 15M EMA50 ${m15_ema50:,.2f})"
        elif macro_bull:
            state_name = "BTC_MODERATE_BULL"
            bias = "BULL_BIAS"
            allow_long = True
            allow_short = False
            reason = f"Bitcoin Macro Bullish (Price > 15M EMA50 ${m15_ema50:,.2f})"
        elif macro_bear:
            state_name = "BTC_MODERATE_BEAR"
            bias = "BEAR_BIAS"
            allow_long = False
            allow_short = True
            reason = f"Bitcoin Macro Bearish (Price < 15M EMA50 ${m15_ema50:,.2f})"
        else:
            state_name = "BTC_BALANCED_RANGE"
            bias = "NEUTRAL"
            allow_long = True
            allow_short = True
            reason = "Bitcoin Sideways Range (15M Neutral Chop)"

        res = {
            "state": state_name,
            "bias": bias,
            "allow_long": allow_long,
            "allow_short": allow_short,
            "btc_price": m15_close,
            "roc_3m": round(roc_3m, 2),
            "15m_rsi": round(m15_rsi, 1),
            "15m_adx": round(m15_adx, 1),
            "reason": reason,
            "timestamp": now
        }
        self.cached_state = res
        self.last_check_time = now
        return res

    def check_trade_alignment(self, symbol: str, direction: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Sovereign Gating Check: Validates if the proposed trade direction
        is compliant with Bitcoin's real-time state.
        """
        btc_info = self.get_btc_state()
        state = btc_info["state"]
        allow_long = btc_info["allow_long"]
        allow_short = btc_info["allow_short"]
        reason = btc_info["reason"]

        if state == "BTC_CASCADE_FREEZE":
            return False, f"[BTC Sentinel VETO]: {reason}", btc_info

        if direction == "LONG" and not allow_long:
            return False, f"[BTC Sentinel VETO]: Long rejected — {reason}. Altcoin Longs prohibited during Bitcoin Bearish flow.", btc_info

        if direction == "SHORT" and not allow_short:
            return False, f"[BTC Sentinel VETO]: Short rejected — {reason}. Altcoin Shorts prohibited during Bitcoin Bullish flow.", btc_info

        return True, f"[BTC Sentinel APPROVED]: Trade direction aligned with Bitcoin {btc_info['bias']}", btc_info

    def calculate_relative_strength(
        self,
        symbol: str,
        alt_df_15m: pd.DataFrame,
        alt_df_5m: Optional[pd.DataFrame] = None,
        direction: str = "LONG"
    ) -> Dict[str, Any]:
        """
        Calculates Altcoin Relative Strength (RS) vs. Bitcoin on 15M and 5M:
        - Awards +15 bonus points to Market Leaders outperforming BTC.
        - Awards +8 bonus points to Solid Aligned tokens.
        - Deducts -20 points from Laggards bleeding against BTC (auto-veto).
        - Enforces 5M Micro-Candle Flow Lock (blocks divergent red candles during bull flow).
        """
        if symbol == self.btc_symbol or "BTC" in symbol:
            return {
                "rs_pct": 0.0,
                "score_modifier": 0,
                "is_divergent": False,
                "status": "BTC_BENCHMARK",
                "desc": "Bitcoin Benchmark (Zero Drift)"
            }

        btc_15m = self.cached_dfs.get("15m")
        if btc_15m is None or btc_15m.empty:
            # Refresh if cache empty
            self.fetch_btc_data()
            btc_15m = self.cached_dfs.get("15m")

        if btc_15m is None or btc_15m.empty or alt_df_15m is None or len(alt_df_15m) < 4:
            return {
                "rs_pct": 0.0,
                "score_modifier": 0,
                "is_divergent": False,
                "status": "PARITY",
                "desc": "Parity Baseline (Data Buffering)"
            }

        try:
            # 1. 15M Return Calculation (Last 3 candles = 45 mins)
            lookback = min(4, len(alt_df_15m), len(btc_15m))
            alt_p_now = float(alt_df_15m.iloc[-1]["close"])
            alt_p_prev = float(alt_df_15m.iloc[-lookback]["close"])
            alt_ret_15m = ((alt_p_now - alt_p_prev) / max(1e-8, alt_p_prev)) * 100.0

            btc_p_now = float(btc_15m.iloc[-1]["close"])
            btc_p_prev = float(btc_15m.iloc[-lookback]["close"])
            btc_ret_15m = ((btc_p_now - btc_p_prev) / max(1e-8, btc_p_prev)) * 100.0

            # Net Relative Strength vs BTC in trade direction
            if direction == "LONG":
                net_rs = alt_ret_15m - btc_ret_15m
            else:
                net_rs = btc_ret_15m - alt_ret_15m

            # 2. 5M Micro-Candle Divergence Guard
            is_divergent = False
            div_reason = ""
            if alt_df_5m is not None and not alt_df_5m.empty and len(alt_df_5m) >= 2:
                last_candle = alt_df_5m.iloc[-1]
                c_open = float(last_candle["open"])
                c_close = float(last_candle["close"])
                btc_info = self.get_btc_state()
                btc_state = btc_info.get("state", "")

                if direction == "LONG" and "BULL" in btc_state:
                    # If BTC is Bullish, reject altcoins making red breakdown candles
                    if c_close < c_open * 0.998 and net_rs < -0.10:
                        is_divergent = True
                        div_reason = f"5M Bearish Divergence: {symbol} printing red candle while Bitcoin is pumping."
                elif direction == "SHORT" and "BEAR" in btc_state:
                    # If BTC is Bearish, reject altcoins making green pump candles
                    if c_close > c_open * 1.002 and net_rs < -0.10:
                        is_divergent = True
                        div_reason = f"5M Bullish Divergence: {symbol} printing green candle while Bitcoin is dumping."

            # 3. Score Modifier Tiering
            if net_rs >= 0.20:
                score_mod = 15
                status = "LEADER 🔥"
                desc = f"BTC Leader: Outperforming Bitcoin by {net_rs:+.2f}% (15M)"
            elif net_rs >= 0.05:
                score_mod = 8
                status = "STRONG ✅"
                desc = f"BTC Aligned: Beating Bitcoin by {net_rs:+.2f}% (15M)"
            elif net_rs >= -0.15:
                score_mod = 0
                status = "NEUTRAL ⚖️"
                desc = f"BTC Parity: Moving inline with Bitcoin ({net_rs:+.2f}%)"
            else:
                score_mod = -20  # Heavy penalty for lagging/bleeding tokens
                status = "LAGGARD ⚠️"
                desc = f"BTC Laggard: Bleeding against Bitcoin ({net_rs:+.2f}% underperformance)"

            return {
                "rs_pct": round(net_rs, 3),
                "alt_ret": round(alt_ret_15m, 2),
                "btc_ret": round(btc_ret_15m, 2),
                "score_modifier": score_mod,
                "is_divergent": is_divergent,
                "divergence_reason": div_reason,
                "status": status,
                "desc": desc
            }
        except Exception as e:
            return {
                "rs_pct": 0.0,
                "score_modifier": 0,
                "is_divergent": False,
                "status": "ERROR",
                "desc": f"RS Calculation Error: {e}"
            }


# Global Sentinel Instance
btc_sentinel = BTCSentinelEngine()
