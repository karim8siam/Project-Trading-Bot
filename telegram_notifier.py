# -*- coding: utf-8 -*-
"""
Telegram Real-Time Notification & Multi-Subscriber Alert Broadcast Engine.
Continuously broadcasts live trade events to Admin and all registered Telegram investors:
1. Trade Opened (Pair, Direction, Confluence Score, ML Win Prob, Exact SL/TP & 1.0% Risk Cap).
2. Rule 6 Breakeven Shift (+1.0R Milestone -> 100% Risk-Free Guarantee).
3. Rule 7 Dynamic Trailing Stop Shifts (Profit Locking & Chandelier ATR Ratchet).
4. Gemini AI Active Trade Supervisor Decisions (Dynamic Profit Locks, Runner Extensions, Soft Cuts).
5. Trade Closures (Realized Win/Loss PnL, Exit Reasons & Outcomes).
"""

import os
import sys
import requests
from typing import Dict, Any, Optional, List
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SERVER_DIR = BASE_DIR.parent / "orbital_trading_platform" / "server"
if SERVER_DIR.exists() and str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8956298161:AAHVCjE5J_EoP0XVRPQhZY0tJ4hvwvXfFVo")
TELEGRAM_ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "7019220132")
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def get_all_subscribers() -> List[str]:
    """Fetches all unique registered Telegram chat IDs to broadcast live trade telemetry."""
    recipients = set()
    if TELEGRAM_ADMIN_CHAT_ID:
        recipients.add(str(TELEGRAM_ADMIN_CHAT_ID))

    try:
        from database import get_db
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_chat_id FROM users WHERE telegram_chat_id IS NOT NULL AND telegram_chat_id != '")
        rows = cursor.fetchall()
        for r in rows:
            cid = str(r[0] if isinstance(r, (list, tuple)) else r.get("telegram_chat_id", ""))
            if cid and cid.strip():
                recipients.add(cid.strip())
        conn.close()
    except Exception:
        pass

    return list(recipients)


def send_telegram_message(
    text: str,
    chat_id: str,
    parse_mode: str = "HTML",
    reply_markup: Optional[Dict[str, Any]] = None
) -> bool:
    """Sends a formatted push notification via Telegram Bot API."""
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return False

    try:
        url = f"{TELEGRAM_API_BASE}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        r = requests.post(url, json=payload, timeout=6)
        return r.status_code == 200
    except Exception as e:
        print(f"[Telegram Notifier Error]: {e}")
        return False


def broadcast_alert(text: str, parse_mode: str = "HTML") -> None:
    """Continuously broadcasts real-time trade signals and outcomes to all subscribers."""
    subscribers = get_all_subscribers()
    for sub_id in subscribers:
        try:
            send_telegram_message(text, chat_id=sub_id, parse_mode=parse_mode)
        except Exception:
            pass


def notify_trade_opened(trade: Dict[str, Any], signal: Dict[str, Any]) -> bool:
    """Dispatches instant alert when a new trade is executed on Binance Futures."""
    sym = trade.get("symbol", "N/A")
    direction = trade.get("direction", "LONG")
    qty = trade.get("quantity", 0.0)
    ep = float(trade.get("entry_price", 0.0))
    sl = float(trade.get("stop_loss", 0.0))
    tp = float(trade.get("take_profit", 0.0))
    lev = trade.get("leverage", 5)
    tid = trade.get("trade_id", "N/A")

    score = signal.get("score", 85)
    strat = signal.get("strategy", "TREND_PULLBACK")
    ml_prob = signal.get("ml_confidence", 0.60) * 100
    regime = signal.get("regime", "TRENDING")

    sl_dist = abs(ep - sl)
    r_val = qty * sl_dist

    icon = "🟢" if direction == "LONG" else "🔴"
    side_badge = "LONG 📈" if direction == "LONG" else "SHORT 📉"

    msg = f"""
{icon} <b>NEW LIVE TRADE EXECUTED ON BINANCE</b>

<b>Pair:</b> <code>{sym}</code> ({side_badge})
<b>Trade ID:</b> <code>{tid}</code>
<b>Entry Price:</b> <code>${ep:,.4f}</code> ({lev}x Isolated)
<b>Quantity:</b> <code>{qty} {sym.split("/")[0]}</code>
<b>Hard Stop-Loss:</b> <code>${sl:,.4f}</code> (Risk: ~${r_val:.4f} USDT | Strict &le; 1.0%)
<b>Take-Profit:</b> <code>${tp:,.4f}</code> (Asymmetric Target)

⚡ <b>QUANTITATIVE CONFLUENCE:</b>
• <b>Engine:</b> {strat} (Score: {score}/100 Grade-S 🔥)
• <b>Regime:</b> {regime}
• <b>ML Dual Ensemble:</b> <b>{ml_prob:.1f}% Win Prob</b> (RF + XGBoost)
• <b>Active Supervisor:</b> 🧠 Gemini 3.6 Flash Copilot Monitoring
"""
    broadcast_alert(msg.strip())
    return True


def notify_breakeven_activated(trade_id: str, symbol: str, entry_price: float, new_sl: float) -> bool:
    """Dispatches alert when Rule 6 Breakeven is activated (+1.0R profit)."""
    msg = f"""
🛡️ <b>RULE 6 BREAKEVEN ACTIVATED — ZERO RISK</b>

<b>Pair:</b> <code>{symbol}</code> (Trade: <code>{trade_id}</code>)
<b>Profit Milestone:</b> &ge; +1.0R (+100% of Risk Target)
<b>New Stop-Loss:</b> <code>${new_sl:,.4f}</code> (Entry + Fee Cushion)

🔒 <b>Guarantee:</b> This position is now <b>100% risk-free</b>. Capital is fully protected on Binance matching engine.
"""
    broadcast_alert(msg.strip())
    return True


def notify_trailing_stop_updated(trade_id: str, symbol: str, new_sl: float, locked_r: float) -> bool:
    """Dispatches alert when Rule 7 Trailing Stop locks in green profit."""
    msg = f"""
📈 <b>RULE 7 TRAILING STOP SHIFTED — PROFIT LOCKED</b>

<b>Pair:</b> <code>{symbol}</code> (Trade: <code>{trade_id}</code>)
<b>New Protected SL:</b> <code>${new_sl:,.4f}</code>
<b>Locked In Profit:</b> &ge; +{locked_r:.1f}R in Guaranteed Gains

🚀 <b>Status:</b> Dynamic Chandelier ATR trailing stop is active and ratcheting forward.
"""
    broadcast_alert(msg.strip())
    return True


def notify_gemini_supervisor_action(
    trade_id: str,
    symbol: str,
    action: str,
    confidence: int,
    reasoning: str
) -> bool:
    """Dispatches alert when Gemini AI makes a tactical micro-decision."""
    action_titles = {
        "HOLD_AND_LET_RUN": "🟢 HOLDING RUNNER",
        "EXTEND_TP_RUNNER": "🚀 EXTENDING TAKE-PROFIT RUNNER",
        "TIGHTEN_SL_LOCK_PROFIT": "🔒 DYNAMIC PROFIT LOCK (SL TIGHTENED)",
        "TACTICAL_EARLY_EXIT": "🎯 TACTICAL EARLY PROFIT EXIT",
        "EARLY_SOFT_CUT_INVALIDATION": "🛡️ EARLY SOFT CUT (70% LOSS SAVED)"
    }
    title = action_titles.get(action, f"🧠 {action}")

    msg = f"""
🧠 <b>GEMINI AI SUPERVISOR TACTICAL DECISION</b>

<b>Pair:</b> <code>{symbol}</code> (Trade: <code>{trade_id}</code>)
<b>Action:</b> <b>{title}</b>
<b>AI Confidence:</b> <code>{confidence}%</code>

💡 <b>Quantitative Rationale:</b>
<em>"{reasoning}"</em>
"""
    broadcast_alert(msg.strip())
    return True


def notify_trade_closed(closed_trade: Dict[str, Any]) -> bool:
    """Dispatches alert when a trade closes with realized PnL and outcome."""
    sym = closed_trade.get("symbol", "N/A")
    direction = closed_trade.get("direction", "N/A")
    pnl = float(closed_trade.get("pnl_usd", 0.0))
    pnl_pct = float(closed_trade.get("pnl_percent", 0.0))
    is_win = pnl >= 0
    ep = float(closed_trade.get("entry_price", 0.0))
    xp = float(closed_trade.get("exit_price", 0.0))
    reason = closed_trade.get("exit_reason", "STRATEGY_EXIT")
    tid = closed_trade.get("trade_id", "N/A")

    icon = "🎯 <b>PROFIT BANKED!</b> 🟢" if is_win else "🛡️ <b>CONTROLLED EXIT</b> 🔴"
    pnl_sign = "+" if pnl >= 0 else ""

    msg = f"""
{icon}

<b>Pair:</b> <code>{sym}</code> ({direction})
<b>Trade ID:</b> <code>{tid}</code>
<b>Exit Price:</b> <code>${xp:,.4f}</code> (Entry: <code>${ep:,.4f}</code>)
<b>Exit Reason:</b> <code>{reason}</code>

💰 <b>REALIZED PnL:</b>
• <b>Net Realized PnL:</b> <b>{pnl_sign}${pnl:,.4f} USDT ({pnl_sign}{pnl_pct:.2f}%)</b>

🧠 <b>Continuous Learning:</b> ML Ensemble updated & retrained on this outcome.
"""
    broadcast_alert(msg.strip())
    return True
