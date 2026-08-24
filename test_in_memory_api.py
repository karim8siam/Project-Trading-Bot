"""
In-Memory HTTP API & Integration Tests for ApexTrade AI with Daily Batch Accumulation and Sweep Engine.
"""

import io
import json
import time
import hashlib
from database import (
    init_db,
    get_user_by_email,
    get_user_by_id,
    get_or_create_active_batch,
    get_current_batch_summary,
    get_batch_history,
    get_user_batch_status,
    get_connection
)
from server import ApexTradeAPIHandler
from config import MIN_DEPOSIT_USDT, PLATFORM_DEPOSIT_ADDRESS, BINANCE_BOT_WALLET_ADDRESS


class FakeSocket:
    def __init__(self, raw_input: bytes):
        self.raw_input = raw_input
        self.rfile = io.BytesIO(raw_input)
        self.wfile = io.BytesIO()

    def makefile(self, mode, *args, **kwargs):
        if 'r' in mode:
            return self.rfile
        elif 'w' in mode or 'b' in mode:
            return self.wfile

    def sendall(self, b):
        self.wfile.write(b)


def simulate_http_request(method: str, path: str, body: dict = None, token: str = None):
    """Simulates an HTTP request against ApexTradeAPIHandler using in-memory streams."""
    body_bytes = json.dumps(body).encode('utf-8') if body is not None else b""
    headers = [
        f"{method} {path} HTTP/1.1",
        "Host: localhost",
        "Content-Type: application/json",
        f"Content-Length: {len(body_bytes)}"
    ]
    if token:
        headers.append(f"Authorization: Bearer {token}")
    headers.append("\r\n")

    raw_req = "\r\n".join(headers).encode('utf-8') + body_bytes
    fake_sock = FakeSocket(raw_req)

    # Instantiate handler
    handler = ApexTradeAPIHandler(fake_sock, ("127.0.0.1", 12345), None)
    
    # Parse output
    fake_sock.wfile.seek(0)
    raw_response = fake_sock.wfile.read().decode('utf-8', errors='replace')
    
    lines = raw_response.split("\r\n")
    status_line = lines[0]
    status_code = int(status_line.split(" ")[1])

    # Find body after empty line
    empty_idx = raw_response.find("\r\n\r\n")
    resp_body = raw_response[empty_idx + 4:] if empty_idx != -1 else ""

    try:
        json_data = json.loads(resp_body)
    except Exception:
        json_data = resp_body

    return status_code, json_data


def run_tests():
    print("🚀 Initializing ApexTrade API in-memory test suite with Daily Sweep Engine...")
    init_db()

    # 1. Test Deposit Config
    print("\n1. Testing GET /api/deposit/config...")
    status, data = simulate_http_request("GET", "/api/deposit/config")
    assert status == 200, f"Expected 200, got {status}"
    assert data["success"] is True
    assert data["platform_deposit_address"] == PLATFORM_DEPOSIT_ADDRESS
    assert data["min_deposit_usdt"] == MIN_DEPOSIT_USDT
    print(f"   ✅ Deposit Config Verified: {data['platform_deposit_address']}")

    # 2. Test Active Batch API
    print("\n2. Testing GET /api/batch/current...")
    status, data = simulate_http_request("GET", "/api/batch/current")
    assert status == 200 and data["success"] is True
    assert "batch" in data
    assert data["batch"]["destination_address"].lower() == BINANCE_BOT_WALLET_ADDRESS.lower()
    assert "seconds_until_sweep" in data
    print(f"   ✅ Active Batch Verified: {data['batch']['batch_id']}, Destination: {data['binance_bot_wallet']}")

    # 3. Test User Registration
    test_email = f"batch_trader_{int(time.time())}@apextrade.ai"
    test_bep20 = "0x71C8360f3e6962f3922339dE77b47e8Ea4D2833F"
    print(f"\n3. Testing POST /api/auth/register ({test_email})...")
    reg_body = {
        "email": test_email,
        "password": "StrongPassword123!",
        "bep20_address": test_bep20
    }
    status, data = simulate_http_request("POST", "/api/auth/register", body=reg_body)
    assert status == 201
    token = data["token"]
    user_id = data["user"]["id"]
    print(f"   ✅ User Registered (Status: {data['user']['account_status']})")

    # 4. Test User Profile Me (Initial state)
    print("\n4. Testing GET /api/auth/me (Unfunded)...")
    status, data = simulate_http_request("GET", "/api/auth/me", token=token)
    assert status == 200
    assert data["user"]["batch_status"]["queue_state"] == "NOT_DEPOSITED"
    print("   ✅ Unfunded User Queue State: NOT_DEPOSITED")

    # 5. Test Deposit Verification & Linking to Active Daily Batch
    sample_tx = "0x" + hashlib.sha256(f"test_batch_{time.time()}".encode()).hexdigest()
    print(f"\n5. Testing POST /api/deposit/verify with TxHash {sample_tx[:16]}...")
    status, data = simulate_http_request("POST", "/api/deposit/verify", body={
        "tx_hash": sample_tx,
        "simulate": True
    }, token=token)
    assert status == 200, f"Expected 200, got {status}: {data}"
    assert data["success"] is True
    assert data["amount_usdt"] >= 1.0
    batch_id = data["deposit"]["batch_id"]
    print(f"   ✅ Deposit Verified: +{data['amount_usdt']} USDT linked to {batch_id}")

    # 6. Test User Batch Queue Status
    print("\n6. Testing GET /api/auth/me (Queued in Batch)...")
    status, data = simulate_http_request("GET", "/api/auth/me", token=token)
    assert status == 200
    b_status = data["user"]["batch_status"]
    assert b_status["queue_state"] == "QUEUED_FOR_TODAY_BATCH"
    assert b_status["user_today_deposited_usdt"] >= 10.0
    print(f"   ✅ User Queue State Verified: {b_status['queue_state']} with {b_status['user_pool_share_pct']}% pool share")

    # 7. Test Batch Summary Update
    print("\n7. Testing GET /api/batch/current (After Deposit)...")
    status, data = simulate_http_request("GET", "/api/batch/current")
    assert status == 200
    assert data["batch"]["total_amount_usdt"] >= 10.0
    assert data["batch"]["unique_participants"] >= 1
    print(f"   ✅ Batch Pool Updated: {data['batch']['total_amount_usdt']} USDT across {data['batch']['unique_participants']} participants")

    # 8. Test Daily Sweep Trigger to Binance Hot Wallet
    print(f"\n8. Testing POST /api/admin/sweep-now (Sweeping to {BINANCE_BOT_WALLET_ADDRESS})...")
    status, data = simulate_http_request("POST", "/api/admin/sweep-now", body={})
    assert status == 200, f"Expected 200, got {status}: {data}"
    assert data["success"] is True
    assert data["status"] == "SWEPT_TO_BINANCE"
    assert data["destination_address"].lower() == BINANCE_BOT_WALLET_ADDRESS.lower()
    print(f"   ✅ Daily Sweep Executed: Swept {data['total_amount_usdt']} USDT to {data['destination_address']} (Tx: {data['sweep_tx_hash']})")

    # 9. Test User State After Sweep
    print("\n9. Testing GET /api/auth/me (Active in Bot Cycle)...")
    status, data = simulate_http_request("GET", "/api/auth/me", token=token)
    assert status == 200
    assert data["user"]["account_status"] == "ACTIVE_IN_BOT_CYCLE"
    assert data["user"]["bot_trading_enabled"] is True
    print("   ✅ User Account Status Promoted to: ACTIVE_IN_BOT_CYCLE with Bot Enabled!")

    # 11. Test Settlement Simulation API (Win vs Loss)
    print("\n11. Testing POST /api/settlements/simulate...")
    # Win test
    s_status, s_win = simulate_http_request("POST", "/api/settlements/simulate", body={"deposit": 100, "daily_roi_pct": 10.0})
    assert s_status == 200
    assert s_win["breakdown"]["user_net_pct"] == 6.0
    assert s_win["breakdown"]["system_cut_pct"] == 4.0
    assert s_win["breakdown"]["ending_balance"] == 106.0

    # Loss test
    s_status, s_loss = simulate_http_request("POST", "/api/settlements/simulate", body={"deposit": 100, "daily_roi_pct": -5.0})
    assert s_status == 200
    assert s_loss["breakdown"]["user_net_pct"] == -5.0
    assert s_loss["breakdown"]["system_cut_pct"] == 0.0
    assert s_loss["breakdown"]["ending_balance"] == 95.0
    print("   ✅ Settlement Simulator Rules Verified (60/40 Win & 100% Direct Loss)")

    # 12. Test Process Daily Settlement (+10% Win Payout)
    print("\n12. Testing POST /api/settlements/process-daily (+10% Win)...")
    s_status, s_proc = simulate_http_request("POST", "/api/settlements/process-daily", body={"daily_roi_pct": 10.0})
    assert s_status == 200, f"Expected 200, got {s_status}: {s_proc}"
    assert s_proc["success"] is True
    assert s_proc["is_win"] is True
    print(f"   ✅ Daily Settlement Processed for {s_proc['settled_count']} traders! User PnL: +{s_proc['total_user_pnl_usdt']} USDT | System Fee: +{s_proc['total_system_fee_usdt']} USDT")

    # 13. Test User Settlement Receipts
    print("\n13. Testing GET /api/settlements/me...")
    m_status, m_data = simulate_http_request("GET", "/api/settlements/me", token=token)
    assert m_status == 200
    assert len(m_data["settlements"]) >= 1
    assert m_data["settlements"][0]["is_win"] == 1
    print(f"   ✅ User Settlement Receipts Verified (Found {len(m_data['settlements'])} records)")

    # 14. Test Platform Settlement Ledger
    print("\n14. Testing GET /api/settlements/ledger...")
    l_status, l_data = simulate_http_request("GET", "/api/settlements/ledger")
    assert l_status == 200
    assert len(l_data["settlements"]) >= 1
    print(f"   ✅ Platform Settlement Ledger Verified: {len(l_data['settlements'])} records")

    print("\n=========================================================================")
    print("🎉 ALL 14 DAILY BATCH & 60/40 SETTLEMENT TESTS PASSED 100%! 🎉")
    print("=========================================================================\n")


if __name__ == "__main__":
    run_tests()

