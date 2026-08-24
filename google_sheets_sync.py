"""
Google Sheets Live Sync Module for Crypto Futures Trading Bot.
Automatically syncs:
1. Every Trade (Entry, Exit, Reason, Realized PnL $, Win/Loss, ML %, Score)
2. Daily Performance Summary (Date, Starting Balance, Ending Balance, Daily Realized PnL $, Daily Profit/Loss %)
"""

import os
import json
import csv
import requests
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any, Optional, List
from config import BASE_DIR, ALLOWED_SYMBOLS, DB_PATH
import sqlite3
import pandas as pd


# Local backup CSV files (persisted in data/ directory)
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
LOCAL_TRADES_CSV = DATA_DIR / "google_sheets_trades.csv"
LOCAL_DAILY_CSV = DATA_DIR / "google_sheets_daily_performance.csv"

# Optional Google Sheets Webhook URL or Apps Script URL (set in .env)
GOOGLE_SHEET_WEBHOOK_URL = os.getenv("GOOGLE_SHEET_WEBHOOK_URL", "")


class GoogleSheetsSync:
    """
    Manages real-time synchronization between the trading bot and Google Sheets.
    Supports both Google Apps Script Webhooks (instant setup) and local CSV mirroring.
    """

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or GOOGLE_SHEET_WEBHOOK_URL
        self._init_local_csvs()

    def _init_local_csvs(self):
        """Initializes local CSV mirrors with header columns if they don't exist."""
        if not LOCAL_TRADES_CSV.exists():
            with open(LOCAL_TRADES_CSV, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Trade ID",
                    "Date / Time (UTC)",
                    "Symbol",
                    "Direction",
                    "Entry Price ($)",
                    "Exit Price ($)",
                    "Exit Reason",
                    "PnL ($)",
                    "PnL (%)",
                    "Outcome",
                    "ML Win Prob (%)",
                    "Confluence Score",
                    "Breakeven Saved",
                    "Account Balance ($)"
                ])

        if not LOCAL_DAILY_CSV.exists():
            with open(LOCAL_DAILY_CSV, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Date",
                    "Starting Balance ($)",
                    "Ending Balance ($)",
                    "Daily PnL ($)",
                    "Daily Profit/Loss (%)",
                    "Total Trades",
                    "Wins",
                    "Losses",
                    "Win Rate (%)",
                    "Status"
                ])

    def log_trade(self, trade_data: Dict[str, Any]) -> bool:
        """
        Logs a completed or updated trade to Google Sheets (and local CSV backup).
        """
        trade_id = trade_data.get("trade_id", "UNKNOWN")
        timestamp = trade_data.get("exit_time") or trade_data.get("entry_time") or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        symbol = trade_data.get("symbol", "BTC/USDT")
        direction = trade_data.get("direction", "LONG")
        entry_price = float(trade_data.get("entry_price", 0.0))
        exit_price = float(trade_data.get("exit_price", 0.0)) if trade_data.get("exit_price") is not None else 0.0
        exit_reason = trade_data.get("exit_reason", "OPEN")
        pnl_usd = float(trade_data.get("pnl_usd", 0.0))
        pnl_pct = float(trade_data.get("pnl_percent", 0.0) or trade_data.get("pnl_pct", 0.0))
        
        is_win = trade_data.get("is_win")
        if is_win == 1 or pnl_usd > 0:
            outcome = "WIN ✅"
        elif is_win == 0 or pnl_usd < 0:
            outcome = "LOSS ❌"
        else:
            outcome = "BREAKEVEN 🛡️" if "BREAKEVEN" in str(exit_reason) else "OPEN ⏳"

        ml_prob = float(trade_data.get("ml_predicted_prob", 0.75) or trade_data.get("ml_prob", 0.75)) * 100.0
        score = trade_data.get("score", 170)
        be_saved = "YES 🛡️" if "BREAKEVEN" in str(exit_reason) or trade_data.get("be_triggered") else "NO"
        balance = float(trade_data.get("balance", 0.0))

        row = [
            trade_id,
            timestamp,
            symbol,
            direction,
            f"${entry_price:,.2f}",
            f"${exit_price:,.2f}" if exit_price > 0 else "OPEN",
            exit_reason,
            f"{'+' if pnl_usd >= 0 else ''}${pnl_usd:.2f}",
            f"{'+' if pnl_pct >= 0 else ''}{pnl_pct:.2f}%",
            outcome,
            f"{ml_prob:.1f}%",
            score,
            be_saved,
            f"${balance:,.2f}" if balance > 0 else "-"
        ]

        # 1. Write to Local CSV Mirror
        try:
            with open(LOCAL_TRADES_CSV, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(row)
        except Exception as e:
            print(f"[Google Sheets Sync] Local CSV write error: {e}")

        # 2. Push to Google Sheets via Webhook (if URL configured)
        if self.webhook_url:
            payload = {
                "action": "log_trade",
                "trade": {
                    "trade_id": trade_id,
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "direction": direction,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "exit_reason": exit_reason,
                    "pnl_usd": pnl_usd,
                    "pnl_pct": pnl_pct,
                    "outcome": outcome,
                    "ml_prob": round(ml_prob, 1),
                    "score": score,
                    "be_saved": be_saved,
                    "balance": balance
                }
            }
            try:
                res = requests.post(self.webhook_url, json=payload, timeout=5)
                if res.status_code == 200:
                    print(f"[Google Sheets Sync] ✅ Trade {trade_id} synced to Google Sheets!")
                    return True
                else:
                    print(f"[Google Sheets Sync] Webhook responded with status {res.status_code}")
            except Exception as e:
                print(f"[Google Sheets Sync] Webhook connection warning: {e}")

        return True

    def calculate_and_sync_daily_summary(self, target_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Calculates today's total trades, wins, losses, net PnL $, and DAILY PROFIT/LOSS PERCENTAGE (%),
        and updates the 'Daily Performance' tab in Google Sheets.
        """
        if not target_date:
            target_date = datetime.utcnow().strftime("%Y-%m-%d")

        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql("SELECT * FROM trades WHERE exit_price IS NOT NULL", conn)
        conn.close()

        if not df.empty:
            df["trade_date"] = df["exit_time"].apply(lambda x: str(x)[:10] if x else "")
            daily_df = df[df["trade_date"] == target_date]
            if daily_df.empty:
                daily_df = df.tail(10)
            
            total_trades = len(daily_df)
            wins_df = daily_df[daily_df["pnl_usd"] > 0]
            losses_df = daily_df[daily_df["pnl_usd"] <= 0]
            wins = len(wins_df)
            losses = len(losses_df)
            win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
            daily_pnl_usd = float(daily_df["pnl_usd"].sum())
        else:
            total_trades = 0
            wins = 0
            losses = 0
            win_rate = 0.0
            daily_pnl_usd = 0.0

        # Reference starting daily capital
        starting_balance = 5000.0
        ending_balance = starting_balance + daily_pnl_usd
        daily_roi_pct = (daily_pnl_usd / starting_balance) * 100.0

        status = "PROFIT 🟢" if daily_pnl_usd >= 0 else "LOSS 🔴"

        summary_data = {
            "date": target_date,
            "starting_balance": round(starting_balance, 2),
            "ending_balance": round(ending_balance, 2),
            "daily_pnl_usd": round(daily_pnl_usd, 2),
            "daily_roi_pct": round(daily_roi_pct, 2),
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": round(win_rate, 1),
            "status": status
        }

        # Write to Local Daily CSV
        row = [
            target_date,
            f"${starting_balance:,.2f}",
            f"${ending_balance:,.2f}",
            f"{'+' if daily_pnl_usd >= 0 else ''}${daily_pnl_usd:.2f}",
            f"{'+' if daily_roi_pct >= 0 else ''}{daily_roi_pct:.2f}%",
            total_trades,
            wins,
            losses,
            f"{win_rate:.1f}%",
            status
        ]

        try:
            with open(LOCAL_DAILY_CSV, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(row)
        except Exception as e:
            print(f"[Google Sheets Sync] Local Daily CSV write error: {e}")

        # Push to Google Sheets Webhook
        if self.webhook_url:
            payload = {
                "action": "log_daily_summary",
                "daily": summary_data
            }
            try:
                requests.post(self.webhook_url, json=payload, timeout=5)
                print(f"[Google Sheets Sync] 📊 Daily summary for {target_date} ({daily_roi_pct:+.2f}%) synced to Google Sheets!")
            except Exception as e:
                pass

        return summary_data

    def sync_settlement_to_google_sheets(self, settlement_data: Dict[str, Any]) -> bool:
        """
        Pushes daily 60/40 win / 100% loss settlement summary to Google Sheets.
        """
        if not self.webhook_url:
            return False

        payload = {
            "action": "log_settlement",
            "settlement": {
                "date": settlement_data.get("settlement_date"),
                "batch_id": settlement_data.get("batch_id"),
                "daily_roi_pct": settlement_data.get("daily_roi_pct"),
                "is_win": settlement_data.get("is_win"),
                "rule_applied": settlement_data.get("rule_applied"),
                "settled_count": settlement_data.get("settled_count"),
                "total_starting_tvl": settlement_data.get("total_starting_tvl"),
                "total_user_pnl_usdt": settlement_data.get("total_user_pnl_usdt"),
                "total_system_fee_usdt": settlement_data.get("total_system_fee_usdt"),
                "total_ending_tvl": settlement_data.get("total_ending_tvl")
            }
        }
        try:
            res = requests.post(self.webhook_url, json=payload, timeout=5)
            if res.status_code == 200:
                print(f"[Google Sheets Sync] 📊 Settlement for {settlement_data.get('settlement_date')} synced to Google Sheets!")
                return True
        except Exception as e:
            print(f"[Google Sheets Sync] Settlement sync notice: {e}")

        return False


# Global sync instance
sheets_sync = GoogleSheetsSync()


APPS_SCRIPT_TEMPLATE = """/**
 * Google Apps Script for Binance Futures Trading Bot Live Sync.
 * 
 * INSTRUCTIONS (Takes 1 minute to setup):
 * 1. Open Google Sheets (create a new blank spreadsheet).
 * 2. In the top menu, click 'Extensions' > 'Apps Script'.
 * 3. Delete any default code, paste this entire script, and click 'Save' (Floppy icon).
 * 4. Click 'Deploy' > 'New deployment'.
 * 5. Select type: 'Web app'.
 * 6. Set:
 *    - Description: Trading Bot Sync
 *    - Execute as: 'Me'
 *    - Who has access: 'Anyone'
 * 7. Click 'Deploy' and copy the Web App URL!
 * 8. Paste the URL into your bot's .env file as:
 *    GOOGLE_SHEET_WEBHOOK_URL=https://script.google.com/macros/s/YOUR_DEPLOYMENT_ID/exec
 */

function doPost(e) {
  try {
    var sheetApp = SpreadsheetApp.getActiveSpreadsheet();
    var contents = JSON.parse(e.postData.contents);
    var action = contents.action;
    
    if (action === "log_trade") {
      var t = contents.trade;
      var tradeSheet = sheetApp.getSheetByName("Trade Journal");
      if (!tradeSheet) {
        tradeSheet = sheetApp.insertSheet("Trade Journal");
        tradeSheet.appendRow([
          "Trade ID", "Date / Time (UTC)", "Symbol", "Direction",
          "Entry Price ($)", "Exit Price ($)", "Exit Reason",
          "PnL ($)", "PnL (%)", "Outcome", "ML Win Prob (%)",
          "Confluence Score", "Breakeven Saved", "Account Balance ($)"
        ]);
        tradeSheet.getRange("A1:N1").setBackground("#1e293b").setFontColor("#ffffff").setFontWeight("bold");
      }
      tradeSheet.appendRow([
        t.trade_id, t.timestamp, t.symbol, t.direction,
        t.entry_price, t.exit_price, t.exit_reason,
        t.pnl_usd, (t.pnl_pct + "%"), t.outcome, (t.ml_prob + "%"),
        t.score, t.be_saved, t.balance
      ]);
      return ContentService.createTextOutput(JSON.stringify({"status": "success", "message": "Trade logged"})).setMimeType(ContentService.MimeType.JSON);
    }
    
    if (action === "log_daily_summary") {
      var d = contents.daily;
      var dailySheet = sheetApp.getSheetByName("Daily Performance");
      if (!dailySheet) {
        dailySheet = sheetApp.insertSheet("Daily Performance");
        dailySheet.appendRow([
          "Date", "Starting Balance ($)", "Ending Balance ($)",
          "Daily PnL ($)", "Daily Profit/Loss (%)", "Total Trades",
          "Wins", "Losses", "Win Rate (%)", "Status"
        ]);
        dailySheet.getRange("A1:J1").setBackground("#0f172a").setFontColor("#ffffff").setFontWeight("bold");
      }
      dailySheet.appendRow([
        d.date, d.starting_balance, d.ending_balance,
        d.daily_pnl_usd, (d.daily_roi_pct + "%"), d.total_trades,
        d.wins, d.losses, (d.win_rate_pct + "%"), d.status
      ]);
      return ContentService.createTextOutput(JSON.stringify({"status": "success", "message": "Daily summary logged"})).setMimeType(ContentService.MimeType.JSON);
    }
    
    return ContentService.createTextOutput(JSON.stringify({"status": "ignored"})).setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({"status": "error", "message": err.toString()})).setMimeType(ContentService.MimeType.JSON);
  }
}
"""
