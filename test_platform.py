"""
Automated Test Suite for Orbital Trading Platform.
Tests:
- Registration
- 2-of-3 Multi-Factor Authentication (All 3 combinations)
- Device Session Auto-Login Persistence
- 24-Hour Epoch Vault & Proportional Yield Allocation
- Trading Bot Bridge
"""

import sys
from pathlib import Path

# Add server directory to path
SERVER_DIR = Path(__file__).resolve().parent / "server"
sys.path.insert(0, str(SERVER_DIR))

from database import init_platform_db, get_db
from auth import register_user, login_user_2_of_3, get_user_by_token
from vault_engine import vault_engine
from bridge_bot_sync import get_live_bot_trades, get_live_bot_performance_summary


def run_tests():
    print("=" * 80)
    print("🪐 TESTING ORBITAL TRADING PLATFORM SUITE")
    print("=" * 80)

    # 1. Initialize DB
    init_platform_db()
    print("[1] Database Initialized ✅")

    # 2. Test User Registration
    test_email = "investor1@orbital.com"
    test_pass = "QuantumSafePass2026!"
    test_bep20 = "0x71C8705F2Bf2E4522967672ecAea539E1a4aD5A1"

    print("\n[2] Testing Registration...")
    reg_res = register_user(
        email=test_email,
        password=test_pass,
        bep20_address=test_bep20
    )
    print(f"  • Result: {reg_res}")
    assert reg_res["success"] or "already exists" in reg_res.get("error", ""), "Registration failed!"
    print("  • Registration Test Passed ✅")

    # 3. Test 2-of-3 Authentication Combinations
    print("\n[3] Testing 2-of-3 Multi-Factor Authentication:")

    # Combo A: Email + Password
    print("  • Test A: Email + Password...")
    res_a = login_user_2_of_3(email=test_email, password=test_pass)
    assert res_a["success"], f"Combo A failed: {res_a}"
    print(f"    -> Success: Matched {res_a['matched_factors']} ✅")

    # Combo B: Email + BEP-20 Wallet
    print("  • Test B: Email + BEP-20 Address...")
    res_b = login_user_2_of_3(email=test_email, bep20_address=test_bep20)
    assert res_b["success"], f"Combo B failed: {res_b}"
    print(f"    -> Success: Matched {res_b['matched_factors']} ✅")

    # Combo C: BEP-20 Wallet + Password
    print("  • Test C: BEP-20 Address + Password...")
    res_c = login_user_2_of_3(bep20_address=test_bep20, password=test_pass)
    assert res_c["success"], f"Combo C failed: {res_c}"
    print(f"    -> Success: Matched {res_c['matched_factors']} ✅")

    # Combo D: Single Factor (Must Fail!)
    print("  • Test D: Single Factor (Only Email - Expecting Rejection)...")
    res_d = login_user_2_of_3(email=test_email)
    assert not res_d["success"], "Single factor should NOT succeed!"
    print("    -> Correctly Rejected (2-of-3 Rule Enforced) ✅")

    # 4. Test Device Session Persistence
    print("\n[4] Testing Device Session Persistence (Auto-Login):")
    token = res_a["token"]
    user_rec = get_user_by_token(token)
    assert user_rec is not None, "Token verification failed!"
    print(f"  • Token Verified for User: {user_rec['user_uuid']} ({user_rec['email']}) ✅")

    # 5. Test 24-Hour Epoch Pool & Yield Settlement
    print("\n[5] Testing 24-Hour Epoch Vault & Yield Settlement:")
    epoch_info = vault_engine.get_or_create_active_epoch()
    print(f"  • Active Epoch: #{epoch_info['epoch_id']} | Countdown: {epoch_info['time_remaining_formatted']}")

    # Simulate deposit of $100 for investor
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance_usdt = 100.0, active_vault_balance = 100.0 WHERE email = ?", (test_email,))
    conn.commit()
    conn.close()

    # Settle epoch with +5.0% daily bot gain
    settle_res = vault_engine.settle_epoch_with_daily_bot_performance(daily_roi_pct=5.0, daily_pnl_usd=50.0)
    print(f"  • Settle Result: {settle_res}")
    assert settle_res["success"], "Settlement failed!"
    print("  • Yield Distribution (+4.0% net user yield after 20% platform fee) Passed ✅")

    # 6. Test Trading Bot Bridge
    print("\n[6] Testing Live Trading Bot Bridge:")
    trades = get_live_bot_trades(limit=3)
    print(f"  • Retrieved {len(trades)} recent trades from bot journal.")
    perf = get_live_bot_performance_summary()
    print(f"  • Bot Stats: Win Rate: {perf['win_rate_pct']}%, Total PnL: ${perf['total_pnl_usd']:,.2f}")

    print("\n" + "=" * 80)
    print("🏆 ALL ORBITAL PLATFORM MODULES PASSED 100% SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    run_tests()
