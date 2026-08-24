"""
Unit & Integration Tests for User Earnings & P&L Dashboard and Last-Day Return Confirmation.
"""

import unittest
import time
from database import (
    init_db,
    create_user,
    get_user_by_id,
    update_user_balance_and_status,
    record_user_settlement,
    get_user_financial_analytics
)
from auth import hash_password


class TestUserDashboard(unittest.TestCase):

    def setUp(self):
        init_db()

    def test_01_user_financial_analytics_isolation(self):
        """Tests that two different users have completely unique, mathematically isolated dashboards."""
        t = int(time.time())
        u_alpha = create_user(f"alpha_{t}@apex.ai", hash_password("Pass123!"), "0x" + "a" * 40)
        u_beta = create_user(f"beta_{t}@apex.ai", hash_password("Pass123!"), "0x" + "b" * 40)

        # Alpha deposits $500, Beta deposits $100
        update_user_balance_and_status(u_alpha["id"], added_balance=500.0, new_status="ACTIVE_IN_BOT_CYCLE")
        update_user_balance_and_status(u_beta["id"], added_balance=100.0, new_status="ACTIVE_IN_BOT_CYCLE")

        # Cycle 1: +10% Win (60/40 Split -> +6% User Net)
        # Alpha ($500): User PnL = +$30.00, Fee = $20.00, End Bal = $530.00
        # Beta ($100): User PnL = +$6.00, Fee = $4.00, End Bal = $106.00
        record_user_settlement(
            batch_id="BATCH-DAY-1", settlement_date="2026-08-01", user_id=u_alpha["id"],
            starting_balance=500.0, daily_roi_pct=10.0, is_win=1, user_net_pct=6.0, system_cut_pct=4.0,
            user_pnl_usdt=30.0, system_fee_usdt=20.0, ending_balance=530.0
        )
        record_user_settlement(
            batch_id="BATCH-DAY-1", settlement_date="2026-08-01", user_id=u_beta["id"],
            starting_balance=100.0, daily_roi_pct=10.0, is_win=1, user_net_pct=6.0, system_cut_pct=4.0,
            user_pnl_usdt=6.0, system_fee_usdt=4.0, ending_balance=106.0
        )

        # Cycle 2: -5% Loss (100% Direct Loss -> -5% User Net, $0 Fee)
        # Alpha ($530): User PnL = -$26.50, Fee = $0.00, End Bal = $503.50
        # Beta ($106): User PnL = -$5.30, Fee = $0.00, End Bal = $100.70
        record_user_settlement(
            batch_id="BATCH-DAY-2", settlement_date="2026-08-02", user_id=u_alpha["id"],
            starting_balance=530.0, daily_roi_pct=-5.0, is_win=0, user_net_pct=-5.0, system_cut_pct=0.0,
            user_pnl_usdt=-26.5, system_fee_usdt=0.0, ending_balance=503.5
        )
        record_user_settlement(
            batch_id="BATCH-DAY-2", settlement_date="2026-08-02", user_id=u_beta["id"],
            starting_balance=106.0, daily_roi_pct=-5.0, is_win=0, user_net_pct=-5.0, system_cut_pct=0.0,
            user_pnl_usdt=-5.3, system_fee_usdt=0.0, ending_balance=100.7
        )

        # Fetch Analytics for Alpha
        alpha_dash = get_user_financial_analytics(u_alpha["id"])
        self.assertEqual(alpha_dash["total_profit_usdt"], 30.0)
        self.assertEqual(alpha_dash["total_loss_usdt"], 26.5)
        self.assertEqual(alpha_dash["net_pnl_usdt"], 3.5) # $30.0 - $26.5 = +$3.50
        self.assertEqual(alpha_dash["balance_usdt"], 503.5)
        self.assertEqual(alpha_dash["total_cycles_settled"], 2)

        # Fetch Analytics for Beta
        beta_dash = get_user_financial_analytics(u_beta["id"])
        self.assertEqual(beta_dash["total_profit_usdt"], 6.0)
        self.assertEqual(beta_dash["total_loss_usdt"], 5.3)
        self.assertEqual(beta_dash["net_pnl_usdt"], 0.7) # $6.0 - $5.3 = +$0.70
        self.assertEqual(beta_dash["balance_usdt"], 100.7)
        self.assertEqual(beta_dash["total_cycles_settled"], 2)

        # Ensure strict isolation
        self.assertNotEqual(alpha_dash["total_profit_usdt"], beta_dash["total_profit_usdt"])
        self.assertNotEqual(alpha_dash["balance_usdt"], beta_dash["balance_usdt"])

    def test_02_last_day_return_confirmation_details(self):
        """Tests that the last day return card provides accurate confirmation of payout or adjusted capital."""
        t = int(time.time()) + 1
        u = create_user(f"gamma_{t}@apex.ai", hash_password("Pass123!"), "0x" + "c" * 40)
        update_user_balance_and_status(u["id"], added_balance=250.0, new_status="ACTIVE_IN_BOT_CYCLE")

        # Settlement Day
        record_user_settlement(
            batch_id="BATCH-YESTERDAY", settlement_date="2026-08-15", user_id=u["id"],
            starting_balance=250.0, daily_roi_pct=8.0, is_win=1, user_net_pct=4.8, system_cut_pct=3.2,
            user_pnl_usdt=12.0, system_fee_usdt=8.0, ending_balance=262.0
        )

        dash = get_user_financial_analytics(u["id"])
        conf = dash["last_return_confirmation"]

        self.assertTrue(conf["has_settlement"])
        self.assertEqual(conf["status"], "CONFIRMED & RETURNED")
        self.assertEqual(conf["settlement_date"], "2026-08-15")
        self.assertEqual(conf["daily_roi_pct"], 8.0)
        self.assertEqual(conf["net_payout_usdt"], 12.0)
        self.assertEqual(conf["ending_balance_usdt"], 262.0)
        self.assertEqual(conf["destination_bep20"].lower(), ("0x" + "c" * 40).lower())


if __name__ == "__main__":
    unittest.main()
