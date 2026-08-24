"""
End-to-End HTTP API & Frontend Integration Tests for ApexTrade AI.
"""

import threading
import time
import urllib.request
import json
from http.server import HTTPServer
from server import ApexTradeAPIHandler
from config import MIN_DEPOSIT_USDT

TEST_PORT = 8899
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"


def start_test_server():
    server = HTTPServer(("127.0.0.1", TEST_PORT), ApexTradeAPIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def http_req(path, method="GET", data=None, token=None):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            status = response.status
            content = response.read().decode("utf-8")
            try:
                return status, json.loads(content)
            except Exception:
                return status, content
    except urllib.error.HTTPError as e:
        err_content = e.read().decode("utf-8")
        try:
            return e.code, json.loads(err_content)
        except Exception:
            return e.code, err_content


def run_e2e_tests():
    print("🚀 Starting Test Server on port", TEST_PORT)
    server = start_test_server()
    time.sleep(0.5)

    # 1. Test Static Index.html
    print("Testing GET / (Static Index)...")
    status, content = http_req("/")
    assert status == 200, f"Expected 200 for index, got {status}"
    assert "ApexTrade" in content, "Brand not found in HTML"
    print("✅ Static Frontend OK")

    # 2. Test Deposit Config
    print("Testing GET /api/deposit/config...")
    status, data = http_req("/api/deposit/config")
    assert status == 200 and data["success"] is True
    assert "platform_deposit_address" in data
    assert data["min_deposit_usdt"] == MIN_DEPOSIT_USDT
    print("✅ Deposit Config OK:", data["platform_deposit_address"])

    # 3. Test Registration
    test_email = f"e2e_trader_{int(time.time())}@apextrade.ai"
    test_bep20 = "0x71C8360f3e6962f3922339dE77b47e8Ea4D2833F"
    print(f"Testing POST /api/auth/register for {test_email}...")

    reg_payload = {
        "email": test_email,
        "password": "PasswordSecret123!",
        "bep20_address": test_bep20
    }
    status, data = http_req("/api/auth/register", method="POST", data=reg_payload)
    assert status == 201 and data["success"] is True
    token = data["token"]
    assert data["user"]["account_status"] == "PENDING_DEPOSIT"
    assert data["user"]["balance_usdt"] == 0.0
    print("✅ User Registration OK")

    # 4. Test Login
    print("Testing POST /api/auth/login...")
    status, data = http_req("/api/auth/login", method="POST", data={
        "email": test_email,
        "password": "PasswordSecret123!"
    })
    assert status == 200 and data["success"] is True
    assert "token" in data
    print("✅ User Login OK")

    # 5. Test Auth Profile (Me)
    print("Testing GET /api/auth/me...")
    status, data = http_req("/api/auth/me", token=token)
    assert status == 200 and data["success"] is True
    assert data["user"]["email"] == test_email
    print("✅ Auth Profile OK")

    # 6. Test Bot Toggle Before Deposit (Should be Blocked)
    print("Testing Bot Activation with 0 Deposit (Should fail)...")
    status, data = http_req("/api/bot/toggle", method="POST", data={"enabled": True}, token=token)
    assert status == 403, f"Expected 403, got {status}"
    print("✅ Zero-deposit Bot Guard Protection Verified")

    # 7. Test Deposit Verification (Simulated On-Chain Tx)
    sample_tx = "0x" + "b" * 64
    print(f"Testing POST /api/deposit/verify with TxHash {sample_tx[:12]}...")
    status, data = http_req("/api/deposit/verify", method="POST", data={
        "tx_hash": sample_tx,
        "simulate": True
    }, token=token)
    assert status == 200 and data["success"] is True
    assert data["amount_usdt"] >= 1.0
    assert data["user"]["account_status"] == "ACTIVE_TRADER"
    print(f"✅ On-Chain BEP20 Payment Verified & Credited (+{data['amount_usdt']} USDT)")

    # 8. Test Double Spend Prevention (Replay same TxHash)
    print("Testing Duplicate TxHash Replay Prevention...")
    status, data = http_req("/api/deposit/verify", method="POST", data={
        "tx_hash": sample_tx,
        "simulate": True
    }, token=token)
    assert status == 400 and data["error_code"] == "TX_ALREADY_USED"
    print("✅ Anti-Replay / Double-Spend Protection Verified")

    # 9. Test Deposit History
    print("Testing GET /api/deposit/history...")
    status, data = http_req("/api/deposit/history", token=token)
    assert status == 200 and len(data["deposits"]) == 1
    assert data["deposits"][0]["tx_hash"] == sample_tx.lower()
    print("✅ Deposit Ledger OK")

    # 10. Test Bot Activation After Deposit
    print("Testing Bot Activation after Verified Deposit...")
    status, data = http_req("/api/bot/toggle", method="POST", data={"enabled": True}, token=token)
    assert status == 200 and data["success"] is True
    assert data["bot_trading_enabled"] is True
    print("✅ AI Trading Bot Activated Successfully!")

    server.shutdown()
    print("\n🎉 ALL END-TO-END PLATFORM TESTS PASSED 100% SUCCESSFULLY! 🎉")


if __name__ == "__main__":
    run_e2e_tests()
