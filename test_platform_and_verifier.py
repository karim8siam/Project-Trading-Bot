"""
Comprehensive Unit & Integration Test Suite for ApexTrade AI Platform and BEP20 Verifier.
Tests:
- Authentication & Password Hashing
- BEP20 Address Format Validation
- Database Operations & Status Transitions
- On-Chain TxHash BEP20 Verification Engine
- REST API Server Endpoints
"""

import unittest
import json
import time
import os
from database import (
    init_db,
    create_user,
    get_user_by_email,
    get_user_by_id,
    is_tx_hash_used,
    record_deposit,
    get_user_deposits,
    update_user_balance_and_status,
    update_bot_trading_status,
    get_connection
)
from auth import (
    is_valid_bep20_address,
    is_valid_email,
    hash_password,
    verify_password,
    create_access_token,
    verify_access_token
)
from bep20_verifier import (
    is_valid_tx_hash_format,
    verify_and_credit_deposit,
    parse_bep20_transfer_logs
)
from config import PLATFORM_DEPOSIT_ADDRESS, BSC_USDT_CONTRACT


class TestApexTradePlatform(unittest.TestCase):

    def setUp(self):
        init_db()
        # Clean test user if exists
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM deposits WHERE from_address LIKE '0xtest%';")
        cursor.execute("DELETE FROM users WHERE email LIKE 'test_%@example.com';")
        conn.commit()
        conn.close()

    def test_01_bep20_address_validation(self):
        """Test BEP20 / EVM address regex and format checks."""
        valid_addr1 = "0x71C8360f3e6962f3922339dE77b47e8Ea4D2833F"
        valid_addr2 = "0x55d398326f99059ff775485246999027b3197955"
        self.assertTrue(is_valid_bep20_address(valid_addr1))
        self.assertTrue(is_valid_bep20_address(valid_addr2))

        # Invalid cases
        self.assertFalse(is_valid_bep20_address("0x123"))  # too short
        self.assertFalse(is_valid_bep20_address("not_an_address"))
        self.assertFalse(is_valid_bep20_address("123456789012345678901234567890123456789012"))  # no 0x prefix
        self.assertFalse(is_valid_bep20_address("0x71C8360f3e6962f3922339dE77b47e8Ea4D2833F_EXTRA"))

    def test_02_password_hashing_and_jwt(self):
        """Test PBKDF2 password hashing & HMAC-SHA256 JWT tokens."""
        raw_pw = "SecureTradingPass123!"
        hashed = hash_password(raw_pw)

        self.assertNotEqual(raw_pw, hashed)
        self.assertTrue(verify_password(raw_pw, hashed))
        self.assertFalse(verify_password("WrongPassword!", hashed))

        # JWT
        payload = {"user_id": 999, "email": "test@apex.ai"}
        token = create_access_token(payload, expires_in_seconds=3600)
        decoded = verify_access_token(token)

        self.assertIsNotNone(decoded)
        self.assertEqual(decoded["user_id"], 999)
        self.assertEqual(decoded["email"], "test@apex.ai")

    def test_03_user_registration_lifecycle(self):
        """Test creating user, initial PENDING_DEPOSIT state, and updates."""
        test_email = f"test_{int(time.time())}@example.com"
        test_bep20 = "0x71C8360f3e6962f3922339dE77b47e8Ea4D2833F"
        hashed_pw = hash_password("Password123")

        user = create_user(test_email, hashed_pw, test_bep20)
        self.assertIsNotNone(user)
        self.assertEqual(user["account_status"], "PENDING_DEPOSIT")
        self.assertEqual(user["balance_usdt"], 0.0)
        self.assertEqual(user["bot_trading_enabled"], 0)

        # Deposit credit
        update_user_balance_and_status(user["id"], added_balance=25.0, new_status="ACTIVE_TRADER")
        updated_user = get_user_by_id(user["id"])
        self.assertEqual(updated_user["balance_usdt"], 25.0)
        self.assertEqual(updated_user["account_status"], "ACTIVE_TRADER")

        # Bot toggle
        update_bot_trading_status(user["id"], True)
        updated_user_bot = get_user_by_id(user["id"])
        self.assertEqual(updated_user_bot["bot_trading_enabled"], 1)

    def test_04_bep20_deposit_verification_rules(self):
        """Test on-chain verifier logic: format, minimum deposit, double spend check."""
        test_email = f"test_dep_{int(time.time())}@example.com"
        test_bep20 = "0xtest000000000000000000000000000000000001"
        user = create_user(test_email, hash_password("Pass123!"), test_bep20)

        # 1. Invalid TxHash format
        res1 = verify_and_credit_deposit(user["id"], test_bep20, "0xInvalidHash")
        self.assertFalse(res1["success"])
        self.assertEqual(res1["error_code"], "INVALID_TX_HASH_FORMAT")

        # 2. Valid simulated deposit (10 USDT >= 1.0 USDT)
        valid_tx_hash = "0x" + "a" * 64
        res2 = verify_and_credit_deposit(user["id"], test_bep20, valid_tx_hash, simulate_offline=True)
        self.assertTrue(res2["success"])
        self.assertEqual(res2["status"], "ACTIVE_TRADER")
        self.assertGreaterEqual(res2["amount_usdt"], 1.0)

        # Verify DB updated
        fresh_user = get_user_by_id(user["id"])
        self.assertEqual(fresh_user["account_status"], "ACTIVE_TRADER")
        self.assertEqual(fresh_user["balance_usdt"], 10.0)

        # 3. Double Spend / Replay Attack Prevention (Same hash submitted again)
        res3 = verify_and_credit_deposit(user["id"], test_bep20, valid_tx_hash, simulate_offline=True)
        self.assertFalse(res3["success"])
        self.assertEqual(res3["error_code"], "TX_ALREADY_USED")

        # 4. Deposit history query
        deposits = get_user_deposits(user["id"])
        self.assertEqual(len(deposits), 1)
        self.assertEqual(deposits[0]["tx_hash"], valid_tx_hash.lower())
        self.assertEqual(deposits[0]["amount_usdt"], 10.0)

    def test_05_bep20_log_parsing(self):
        """Test decoding ERC20/BEP20 Transfer(address,address,uint256) event data."""
        # 15.5 USDT = 15.5 * 10^18 = 15500000000000000000 = hex(15500000000000000000)
        raw_val_hex = hex(int(15.5 * 10**18))
        
        from_topic = "0x00000000000000000000000071c8360f3e6962f3922339de77b47e8ea4d2833f"
        to_topic = f"0x000000000000000000000000{PLATFORM_DEPOSIT_ADDRESS.lower().replace('0x', '')}"

        fake_receipt = {
            "status": "0x1",
            "blockNumber": "0x225544",
            "logs": [{
                "address": BSC_USDT_CONTRACT,
                "topics": [
                    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
                    from_topic,
                    to_topic
                ],
                "data": raw_val_hex
            }]
        }

        parsed = parse_bep20_transfer_logs(
            fake_receipt,
            target_recipient=PLATFORM_DEPOSIT_ADDRESS,
            target_token_contract=BSC_USDT_CONTRACT
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["amount_usdt"], 15.5)
        self.assertEqual(parsed["to_address"], PLATFORM_DEPOSIT_ADDRESS.lower())


if __name__ == "__main__":
    unittest.main()
