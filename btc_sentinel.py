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
        self.flash_lockout_until = 0.0

    def fetch_btc_data(self) -> Dict[str, Optional[pd.DataFrame]]:
        """Fetches multi-timeframe candle data for Bitcoin."""
        try:
            df_1m = data_fetcher.fetch_ohlcv(self.btc_symbol, timeframe="1m", limit=30)
            df_5m = data_fetcher.fetch_ohlcv(self.btc_symbol, timeframe="5m", limit=50)
            df_15m = data_fetcher.fetch_ohlcv(self.btc_symbol, timeframe="15m", limit=60)
            df_1h = data_fetcher.fetch_ohlcv(self.btc_symbol, timeframe="1h", limit=50)
            return {
                "1m": df_1m,
                "5m": df_5m,
                "15m": df_15m,
                "1h": df_1h
            }
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

        # 1. Flash Shockwave Check (1M data)
        roc_3m = 0.0
        is_flash_spike = False
        if df_1m is not None and not df_1m.empty and len(df_1m) >= 5:
            last_p = float(df_1m.iloc[-1]["close"])
            prev_p = float(df_1m.iloc[-4]["close"])
            roc_3m = ((last_p - prev_p) / prev_p) * 100.0

            # Detect extreme rapid liquidation wicks (> 0.45% in 3 mins)
            if abs(roc_3m) >= 0.45:
                is_flash_spike = True
                self.flash_lockout_until = now + 180.0  # 3-minute cooling lockout

        # 2. 1-Hour Macro Analysis
        df_1h = add_all_indicators(df_1h)
        h_last = df_1h.iloc[-1]
        h_close = float(h_last["close"])
        h_ema20 = float(h_last.get("ema_20", h_close))
        h_ema50 = float(h_last.get("ema_50", h_close))
        h_rsi = float(h_last.get("rsi_14", 50.0))
        h_adx = float(h_last.get("adx_14", 20.0))

        macro_bull = h_close > h_ema50 and h_ema20 >= h_ema50
        macro_bear = h_close < h_ema50 and h_ema20 <= h_ema50

        # 3. 15-Minute Intraday Momentum Analysis
        df_15m = add_all_indicators(df_15m)
        m_last = df_15m.iloc[-1]
        m_close = float(m_last["close"])
        m_ema9 = float(m_last.get("ema_9", m_close))
        m_ema21 = float(m_last.get("ema_21", m_close))
        m_rsi = float(m_last.get("rsi_14", 50.0))

        intra_bull = m_close > m_ema21 and m_ema9 >= m_ema21
        intra_bear = m_close < m_ema21 and m_ema9 <= m_ema21

        # 4. State Synthesis
        if is_flash_spike:
            state_name = "BTC_CASCADE_FREEZE"
            bias = "NEUTRAL_LOCKED"
            allow_long = False
            allow_short = False
            reason = f"BTC Flash Shockwave ({roc_3m:+.2f}% 3m Spike). Trading paused for 3 mins."
        elif macro_bull and intra_bull:
            state_name = "BTC_EXPANSION_BULL"
            bias = "AGGRESSIVE_BULL"
            allow_long = True
            allow_short = False  # Strictly NO shorts when BTC is pumping
            reason = f"Bitcoin Pumping: 1H & 15M Bull Alignment (Price: ${h_close:,.2f} > EMA50 ${h_ema50:,.2f})"
        elif macro_bear and intra_bear:
            state_name = "BTC_EXPANSION_BEAR"
            bias = "AGGRESSIVE_BEAR"
            allow_long = False  # Strictly NO longs when BTC is dumping
            allow_short = True
            reason = f"Bitcoin Dumping: 1H & 15M Bear Alignment (Price: ${h_close:,.2f} < EMA50 ${h_ema50:,.2f})"
        elif macro_bull:
            state_name = "BTC_MODERATE_BULL"
            bias = "BULL_BIAS"
            allow_long = True
            allow_short = False
            reason = f"Bitcoin Macro Bullish (Price > 1H EMA50 ${h_ema50:,.2f})"
        elif macro_bear:
            state_name = "BTC_MODERATE_BEAR"
            bias = "BEAR_BIAS"
            allow_long = False
            allow_short = True
            reason = f"Bitcoin Macro Bearish (Price < 1H EMA50 ${h_ema50:,.2f})"
        else:
            state_name = "BTC_BALANCED_RANGE"
            bias = "NEUTRAL"
            allow_long = True
            allow_short = True
            reason = f"Bitcoin Consolidating in Neutral Range (${h_close:,.2f})"

        res = {
            "state": state_name,
            "bias": bias,
            "allow_long": allow_long,
            "allow_short": allow_short,
            "btc_price": h_close,
            "roc_3m": round(roc_3m, 2),
            "1h_rsi": round(h_rsi, 1),
            "1h_adx": round(h_adx, 1),
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


# Global Sentinel Instance
btc_sentinel = BTCSentinelEngine()
