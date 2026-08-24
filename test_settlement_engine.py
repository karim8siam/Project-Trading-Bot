"""
Unit & Integration Tests for ApexTrade AI Daily Settlement Engine (60/40 Win & 100% Direct Loss).
"""

import unittest
import time
from database import (
    init_db,
    create_user,
    get_user_by_id,
    update_user_balance_and_status,
    get_user_settlements,
    get_connection
)
from auth import hash_password
from daily_settlement_engine import (
    calculate_settlement_breakdown,
    execute_daily_settlement
)


class TestDailySettlementEngine(unittest.TestCase):

    def setUp(self):
        init_db()

    def test_01_win_day_breakdown_mathematics(self):
        """Tests that on a WIN day, user gets 60% of ROI and system gets 40% fee."""
        deposit = 100.0
        daily_roi = 10.0  # +10%

        res = calculate_settlement_breakdown(deposit, daily_roi)

        self.assertEqual(res["is_win"], 1)
        self.assertEqual(res["rule_applied"], "60_40_WIN_SPLIT")
        self.assertEqual(res["user_net_pct"], 6.0)     # 10% * 0.60 = 6.0%
        self.assertEqual(res["system_cut_pct"], 4.0)   # 10% * 0.40 = 4.0%
        self.assertEqual(res["user_pnl_usdt"], 6.0)    # $100 * 6% = $6.00
        self.assertEqual(res["system_fee_usdt"], 4.0)  # $100 * 4% = $4.00
        self.assertEqual(res["ending_balance"], 106.0) # $100 + $6 = $106.00

    def test_02_loss_day_breakdown_mathematics(self):
        """Tests that on a LOSS day, no 60/40 rule applies (100% direct loss to user, 0% system fee)."""
        deposit = 100.0
        daily_roi = -5.0  # -5%

        res = calculate_settlement_breakdown(deposit, daily_roi)

        self.assertEqual(res["is_win"], 0)
        self.assertEqual(res["rule_applied"], "100_PERCENT_DIRECT_LOSS")
        self.assertEqual(res["user_net_pct"], -5.0)    # Direct 100% loss (-5%)
        self.assertEqual(res["system_cut_pct"], 0.0)   # 0% system fee on loss
        self.assertEqual(res["user_pnl_usdt"], -5.0)   # -$5.00 deduction
        self.assertEqual(res["system_fee_usdt"], 0.0)  # $0.00
        self.assertEqual(res["ending_balance"], 95.0)  # $100 - $5 = $95.00

    def test_03_multi_user_win_settlement_execution(self):
        """Tests executing a live +8% settlement across multiple users in the database."""
        t = int(time.time())
        u1 = create_user(f"trader1_{t}@apex.ai", hash_password("Pass123!"), "0x" + "1" * 40)
        u2 = create_user(f"trader2_{t}@apex.ai", hash_password("Pass123!"), "0x" + "2" * 40)

        # Fund users
        update_user_balance_and_status(u1["id"], added_balance=500.0, new_status="ACTIVE_IN_BOT_CYCLE")
        update_user_balance_and_status(u2["id"], added_balance=100.0, new_status="ACTIVE_IN_BOT_CYCLE")

        # Execute +8% daily win settlement
        summary = execute_daily_settlement(daily_roi_pct=8.0, settlement_date=f"2026-TEST-{t}")
        self.assertTrue(summary["success"])
        self.assertEqual(summary["is_win"], True)

        # Check User 1: 500 USDT * (+8% * 0.60 = +4.8%) = +24.0 USDT -> New balance: 524.00 USDT
        fresh_u1 = get_user_by_id(u1["id"])
        self.assertEqual(fresh_u1["balance_usdt"], 524.0)

        # Check User 2: 100 USDT * (+8% * 0.60 = +4.8%) = +4.80 USDT -> New balance: 104.80 USDT
        fresh_u2 = get_user_by_id(u2["id"])
        self.assertEqual(fresh_u2["balance_usdt"], 104.8)

        # Check user settlement receipts in DB
        u1_settlements = get_user_settlements(u1["id"])
        self.assertEqual(len(u1_settlements), 1)
        self.assertEqual(u1_settlements[0]["user_pnl_usdt"], 24.0)
        self.assertEqual(u1_settlements[0]["system_fee_usdt"], 16.0)

    def test_04_multi_user_loss_settlement_execution(self):
        """Tests executing a live -4% loss settlement (direct deduction, 0 system fee)."""
        t = int(time.time()) + 1
        u3 = create_user(f"trader3_{t}@apex.ai", hash_password("Pass123!"), "0x" + "3" * 40)
        update_user_balance_and_status(u3["id"], added_balance=200.0, new_status="ACTIVE_IN_BOT_CYCLE")

        # Execute -4% daily loss settlement
        summary = execute_daily_settlement(daily_roi_pct=-4.0, settlement_date=f"2026-TEST-LOSS-{t}")
        self.assertTrue(summary["success"])
        self.assertEqual(summary["is_win"], False)

        # Check User 3: 200 USDT * (-4%) = -8.00 USDT -> New balance: 192.00 USDT
        fresh_u3 = get_user_by_id(u3["id"])
        self.assertEqual(fresh_u3["balance_usdt"], 192.0)

        # Verify 0 system fee recorded
        u3_settlements = get_user_settlements(u3["id"])
        self.assertEqual(len(u3_settlements), 1)
        self.assertEqual(u3_settlements[0]["system_fee_usdt"], 0.0)
        self.assertEqual(u3_settlements[0]["user_pnl_usdt"], -8.0)


if __name__ == "__main__":
    unittest.main()
