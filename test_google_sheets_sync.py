"""
Test script for Google Sheets Sync & Daily Basis Percentage Calculation.
"""

from google_sheets_sync import sheets_sync, LOCAL_TRADES_CSV, LOCAL_DAILY_CSV
import pandas as pd

def test_sync():
    print("=" * 80)
    print("📊 TESTING GOOGLE SHEETS LIVE SYNC & DAILY BASIS % PERFORMANCE")
    print("=" * 80)

    # 1. Simulate a winning trade sync
    test_trade = {
        "trade_id": "TEST-001-WIN",
        "entry_time": "2026-08-16 00:00:00",
        "exit_time": "2026-08-16 00:45:00",
        "symbol": "BTC/USDT",
        "direction": "LONG",
        "entry_price": 58200.0,
        "exit_price": 59900.0,
        "exit_reason": "TAKE_PROFIT",
        "pnl_usd": 85.50,
        "pnl_percent": 14.65,
        "is_win": 1,
        "ml_predicted_prob": 0.82,
        "score": 185,
        "balance": 5085.50
    }

    print("\n[1] Logging Test Trade to Google Sheets Sync Engine...")
    sheets_sync.log_trade(test_trade)
    print("✅ Trade successfully logged!")

    # 2. Test Daily Performance Calculation (PnL $ & Daily Basis %)
    print("\n[2] Calculating & Syncing Daily Basis Performance Summary...")
    daily_res = sheets_sync.calculate_and_sync_daily_summary()
    print("✅ Daily Summary calculated:")
    for k, v in daily_res.items():
        print(f"  • {k}: {v}")

    # 3. Read and Display Local CSV Output
    print("\n[3] Local CSV Mirror Content:")
    if LOCAL_DAILY_CSV.exists():
        df_daily = pd.read_csv(LOCAL_DAILY_CSV)
        print("\n--- DAILY PERFORMANCE TABLE ---")
        print(df_daily.tail(5).to_string(index=False))

    if LOCAL_TRADES_CSV.exists():
        df_trades = pd.read_csv(LOCAL_TRADES_CSV)
        print("\n--- TRADE JOURNAL TABLE (Last 3) ---")
        print(df_trades.tail(3).to_string(index=False))

if __name__ == "__main__":
    test_sync()
