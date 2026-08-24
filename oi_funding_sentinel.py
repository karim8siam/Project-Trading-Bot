"""
Open Interest (OI) & Funding Rate Sentiment Engine.
Monitors real-time Binance Futures Open Interest expansion and Funding Rate sentiment
to detect retail liquidation traps, long squeezes, and short squeezes before taking trades.
"""

import time
from typing import Dict, Any, Tuple, Optional
from data_fetcher import data_fetcher


class OIFundingSentinel:
    def __init__(self):
        self.cache_ttl = 30.0  # 30-second cache
        self.cached_metrics: Dict[str, Dict[str, Any]] = {}
        self.last_fetch_times: Dict[str, float] = {}

    def fetch_oi_and_funding(self, symbol: str) -> Dict[str, Any]:
        """
        Fetches live Funding Rate and Open Interest metrics from Binance Futures API.
        """
        now = time.time()
        if symbol in self.cached_metrics and (now - self.last_fetch_times.get(symbol, 0)) < self.cache_ttl:
            return self.cached_metrics[symbol]

        raw_sym = symbol.replace("/", "")
        base_url = data_fetcher.base_url
        headers = {"User-Agent": "Mozilla/5.0"}

        funding_rate = 0.0001  # Default baseline neutral 0.01%
        open_interest = 0.0
        oi_delta_pct = 0.0

        # 1. Fetch Real-Time Funding Rate
        try:
            r_fund = data_fetcher.session.get(
                f"{base_url}/fapi/v1/fundingRate?symbol={raw_sym}&limit=1",
                headers=headers,
                timeout=4
            )
            if r_fund.status_code == 200:
                fund_data = r_fund.json()
                if fund_data and len(fund_data) > 0:
                    funding_rate = float(fund_data[-1].get("fundingRate", 0.0001))
        except Exception:
            pass

        # 2. Fetch Real-Time Open Interest
        try:
            r_oi = data_fetcher.session.get(
                f"{base_url}/fapi/v1/openInterest?symbol={raw_sym}",
                headers=headers,
                timeout=4
            )
            if r_oi.status_code == 200:
                oi_data = r_oi.json()
                open_interest = float(oi_data.get("openInterest", 0.0))
        except Exception:
            pass

        # 3. Fetch 15-Minute Open Interest History for Delta Momentum
        try:
            r_hist = data_fetcher.session.get(
                f"{base_url}/futures/data/openInterestHist?symbol={raw_sym}&period=15m&limit=4",
                headers=headers,
                timeout=4
            )
            if r_hist.status_code == 200:
                hist_data = r_hist.json()
                if isinstance(hist_data, list) and len(hist_data) >= 2:
                    current_oi_hist = float(hist_data[-1].get("sumOpenInterest", open_interest))
                    prev_oi_hist = float(hist_data[0].get("sumOpenInterest", current_oi_hist))
                    if prev_oi_hist > 0:
                        oi_delta_pct = ((current_oi_hist - prev_oi_hist) / prev_oi_hist) * 100.0
        except Exception:
            pass

        metrics = {
            "symbol": symbol,
            "funding_rate": funding_rate,
            "funding_rate_pct": round(funding_rate * 100.0, 4),
            "open_interest": open_interest,
            "oi_delta_15m_pct": round(oi_delta_pct, 2),
            "timestamp": now
        }

        self.cached_metrics[symbol] = metrics
        self.last_fetch_times[symbol] = now
        return metrics

    def evaluate_sentiment_gate(self, symbol: str, direction: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Sovereign Sentiment Evaluation:
        - Detects over-leveraged Long Squeeze Traps (Funding > +0.035% with surging OI -> VETO Long)
        - Detects over-leveraged Short Squeeze Traps (Funding < -0.020% with surging OI -> VETO Short)
        - Identifies high-conviction Short/Long Squeeze alignments.
        """
        metrics = self.fetch_oi_and_funding(symbol)
        fund_pct = metrics["funding_rate_pct"]
        oi_delta = metrics["oi_delta_15m_pct"]

        # Trap Rule 1: Extreme Crowded Long Squeeze Danger
        # If funding is heavily positive (> +0.035%) and OI is expanding rapidly (> +3%),
        # retail is over-leveraged Long and market makers are likely to flush them.
        if direction == "LONG" and fund_pct >= 0.035 and oi_delta > 3.0:
            reason = (
                f"Long Squeeze Risk: Crowded Retail Longs (Funding: {fund_pct:+.4f}%, "
                f"15m OI Surge: {oi_delta:+.1f}%). High risk of liquidation flush."
            )
            return False, f"[OI/Funding VETO]: {reason}", metrics

        # Trap Rule 2: Extreme Crowded Short Squeeze Danger
        # If funding is deeply negative (< -0.020%) and OI is expanding rapidly (> +3%),
        # retail is aggressively panic-shorting and vulnerable to a massive upward short squeeze.
        if direction == "SHORT" and fund_pct <= -0.020 and oi_delta > 3.0:
            reason = (
                f"Short Squeeze Risk: Crowded Retail Shorts (Funding: {fund_pct:+.4f}%, "
                f"15m OI Surge: {oi_delta:+.1f}%). High risk of violent upward squeeze."
            )
            return False, f"[OI/Funding VETO]: {reason}", metrics

        # Clean Alignment: Natural flow
        squeeze_note = ""
        if direction == "LONG" and fund_pct < -0.01:
            squeeze_note = " (🔥 Fuel: Shorts Paying Longs — Short Squeeze Tailwinds Active)"
        elif direction == "SHORT" and fund_pct > 0.025:
            squeeze_note = " (🔥 Fuel: Longs Over-leveraged — Long Squeeze Tailwinds Active)"

        verdict = f"[OI/Funding APPROVED]: Funding {fund_pct:+.4f}% | 15m OI Delta {oi_delta:+.1f}%{squeeze_note}"
        return True, verdict, metrics


# Global Sentinel Instance
oi_funding_sentinel = OIFundingSentinel()
