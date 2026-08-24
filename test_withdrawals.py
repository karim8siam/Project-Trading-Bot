"""
Unit & Integration Tests for Withdrawal System with Admin Approval & System Vault Dispatch.
"""

import unittest
import time
from database import (
    init_db,
    create_user,
    get_user_by_id,
    update_user_balance_and_status,
    create_withdrawal_request,
    get_user_withdrawals,
    get_pending_withdrawals,
    approve_withdrawal_request,
    reject_withdrawal_request
)
from auth import hash_password


class TestWithdrawals(unittest.TestCase):

    def setUp(self):
        init_db()
        t = int(time.time() * 1000)
        self.user = create_user(f"trader_wd_{t}@apex.ai", hash_password("Pass123!"), "0x" + "a" * 40)
        update_user_balance_and_status(self.user["id"], added_balance=250.0, new_status="ACTIVE_TRADER")

    def test_01_withdrawal_request_and_balance_deduction(self):
        """Tests that requesting a withdrawal deducts from user balance and enters PENDING_ADMIN_CONFIRMATION status."""
        wd = create_withdrawal_request(self.user["id"], amount_usdt=100.0, destination_bep20=self.user["bep20_address"])
        self.assertEqual(wd["amount_usdt"], 100.0)
        self.assertEqual(wd["status"], "PENDING_ADMIN_CONFIRMATION")

        # Verify user balance was deducted (250 - 100 = 150)
        u = get_user_by_id(self.user["id"])
        self.assertEqual(u["balance_usdt"], 150.0)

    def test_02_insufficient_funds_rejected(self):
        """Tests that requesting more than available balance is blocked."""
        with self.assertRaises(ValueError):
            create_withdrawal_request(self.user["id"], amount_usdt=500.0, destination_bep20=self.user["bep20_address"])

    def test_03_admin_approval_and_system_vault_dispatch(self):
        """Tests that Admin approval confirms the withdrawal and generates payout dispatch details."""
        wd = create_withdrawal_request(self.user["id"], amount_usdt=50.0, destination_bep20=self.user["bep20_address"])
        pending_list = get_pending_withdrawals()
        self.assertTrue(any(p["id"] == wd["id"] for p in pending_list))

        # Admin approves
        approved = approve_withdrawal_request(wd["id"], payout_tx_hash="0x" + "b" * 64, admin_notes="Approved by Admin")
        self.assertIsNotNone(approved)
        self.assertEqual(approved["status"], "CONFIRMED_DISPATCHED")
        self.assertTrue(approved["payout_tx_hash"].startswith("0x"))

        # Check not in pending list anymore
        pending_after = get_pending_withdrawals()
        self.assertFalse(any(p["id"] == wd["id"] for p in pending_after))

    def test_04_admin_rejection_and_refund(self):
        """Tests that Admin rejection refunds the amount back to user's balance."""
        wd = create_withdrawal_request(self.user["id"], amount_usdt=80.0, destination_bep20=self.user["bep20_address"])
        u_before = get_user_by_id(self.user["id"])
        self.assertEqual(u_before["balance_usdt"], 170.0) # 250 - 80

        # Admin rejects
        rejected = reject_withdrawal_request(wd["id"], reason="Suspicious activity / KYC verification required")
        self.assertEqual(rejected["status"], "REJECTED")

        # Check balance is refunded
        u_after = get_user_by_id(self.user["id"])
        self.assertEqual(u_after["balance_usdt"], 250.0)


if __name__ == "__main__":
    unittest.main()
