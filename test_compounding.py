"""
Unit & Integration Tests for Auto-Compounding Rollover Engine.
Tests continuous multi-day pool rollovers (Day 1 -> Day 2 -> Day 3) under Win (60/40) and Loss (100%) conditions.
"""

import unittest
import time
from database import (
    init_db,
    create_user,
    get_user_by_id,
    update_user_balance_and_status,
    update_user_auto_compound,
    record_user_settlement,
    get_user_financial_analytics
)
from auth import hash_password
from daily_settlement_engine import calculate_settlement_breakdown


class TestAutoCompounding(unittest.TestCase):

    def setUp(self):
        init_db()

    def test_01_compounding_toggle_persistence(self):
        """Tests that auto-compounding toggle persists accurately."""
        t = int(time.time())
        user = create_user(f"compound_trader_{t}@apex.ai", hash_password("Pass123!"), "0x" + "d" * 40)
        self.assertTrue(bool(user.get("auto_compound", 1)))

        # Turn OFF
        update_user_auto_compound(user["id"], False)
        u_off = get_user_by_id(user["id"])
        self.assertEqual(u_off["auto_compound"], 0)

        # Turn ON
        update_user_auto_compound(user["id"], True)
        u_on = get_user_by_id(user["id"])
        self.assertEqual(u_on["auto_compound"], 1)

    def test_02_three_day_compounding_math(self):
        """
        Tests exact multi-day compounding math:
        - Day 1: $100.00 deposit -> +10% Win (60/40: +6% User Net) -> Ending $106.00
        - Day 2: Starts with $106.00 -> +5% Win (60/40: +3% User Net) -> User PnL = $3.18 -> Ending $109.18
        - Day 3: Starts with $109.18 -> -4% Loss (100% Loss: -4% User Net) -> User Deduction = -$4.37 -> Ending $104.81
        """
        # Day 1: $100.00 with +10% Win
        d1 = calculate_settlement_breakdown(starting_balance=100.00, daily_roi_pct=10.0)
        self.assertEqual(d1["user_net_pct"], 6.0) # 60% of +10%
        self.assertEqual(d1["user_pnl_usdt"], 6.00)
        self.assertEqual(d1["ending_balance"], 106.00)

        # Day 2: Compounded $106.00 with +5% Win
        d2 = calculate_settlement_breakdown(starting_balance=d1["ending_balance"], daily_roi_pct=5.0)
        self.assertEqual(d2["user_net_pct"], 3.0) # 60% of +5%
        self.assertAlmostEqual(d2["user_pnl_usdt"], 3.18, places=2) # $106 * 3% = $3.18
        self.assertAlmostEqual(d2["ending_balance"], 109.18, places=2)

        # Day 3: Compounded $109.18 with -4% Loss
        d3 = calculate_settlement_breakdown(starting_balance=d2["ending_balance"], daily_roi_pct=-4.0)
        self.assertEqual(d3["user_net_pct"], -4.0) # 100% direct loss
        self.assertAlmostEqual(d3["user_pnl_usdt"], -4.3672, places=2) # $109.18 * -4% = -$4.37
        self.assertAlmostEqual(d3["ending_balance"], 104.81, places=2)

    def test_03_compounded_settlement_recording_and_kpis(self):
        """Tests that 3 compounded cycles are recorded and cumulative KPIs reflect the growth."""
        t = int(time.time()) + 2
        user = create_user(f"multi_day_trader_{t}@apex.ai", hash_password("Pass123!"), "0x" + "e" * 40)
        update_user_balance_and_status(user["id"], added_balance=100.0, new_status="ACTIVE_IN_BOT_CYCLE")

        # Record Day 1: +10% Win
        record_user_settlement(
            batch_id="BATCH-DAY-1", settlement_date="2026-08-01", user_id=user["id"],
            starting_balance=100.0, daily_roi_pct=10.0, is_win=1, user_net_pct=6.0, system_cut_pct=4.0,
            user_pnl_usdt=6.0, system_fee_usdt=4.0, ending_balance=106.0
        )

        # Record Day 2: +5% Win on compounded $106.00
        record_user_settlement(
            batch_id="BATCH-DAY-2", settlement_date="2026-08-02", user_id=user["id"],
            starting_balance=106.0, daily_roi_pct=5.0, is_win=1, user_net_pct=3.0, system_cut_pct=2.0,
            user_pnl_usdt=3.18, system_fee_usdt=2.12, ending_balance=109.18
        )

        # Record Day 3: -4% Loss on compounded $109.18
        record_user_settlement(
            batch_id="BATCH-DAY-3", settlement_date="2026-08-03", user_id=user["id"],
            starting_balance=109.18, daily_roi_pct=-4.0, is_win=0, user_net_pct=-4.0, system_cut_pct=0.0,
            user_pnl_usdt=-4.37, system_fee_usdt=0.0, ending_balance=104.81
        )

        analytics = get_user_financial_analytics(user["id"])
        self.assertEqual(analytics["balance_usdt"], 104.81)
        self.assertEqual(analytics["total_profit_usdt"], 9.18) # $6.00 + $3.18
        self.assertEqual(analytics["total_loss_usdt"], 4.37) # -$4.37
        self.assertAlmostEqual(analytics["net_pnl_usdt"], 4.81, places=2) # $9.18 - $4.37 = +$4.81
        self.assertEqual(analytics["total_cycles_settled"], 3)
        self.assertTrue(analytics["auto_compound"])


if __name__ == "__main__":
    unittest.main()
