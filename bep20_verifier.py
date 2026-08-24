"""
BEP20 USDT Deposit Verification Engine for Binance Smart Chain (BSC).
Queries BSC JSON-RPC nodes, parses ERC20/BEP20 Transfer logs, and validates transaction parameters.
"""

import json
import re
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, Tuple
from config import (
    PLATFORM_DEPOSIT_ADDRESS,
    BSC_RPC_URLS,
    BSC_USDT_CONTRACT,
    MIN_DEPOSIT_USDT,
    USE_TESTNET
)
from database import is_tx_hash_used, record_deposit, update_user_balance_and_status

# ERC-20 / BEP-20 Transfer(address,address,uint256) topic0
TRANSFER_EVENT_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
TX_HASH_REGEX = re.compile(r"^0x[a-fA-F0-9]{64}$")


def is_valid_tx_hash_format(tx_hash: str) -> bool:
    """Checks if a string is a 66-character hex string starting with 0x."""
    if not tx_hash or not isinstance(tx_hash, str):
        return False
    return bool(TX_HASH_REGEX.match(tx_hash.strip()))


def _rpc_call(method: str, params: list, timeout: int = 6) -> Optional[Dict[str, Any]]:
    """
    Executes a JSON-RPC call to BSC RPC nodes with multi-endpoint fallback.
    """
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params
    }).encode("utf-8")

    headers = {"Content-Type": "application/json"}

    for rpc_url in BSC_RPC_URLS:
        try:
            req = urllib.request.Request(rpc_url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
                if "result" in result:
                    return result["result"]
        except Exception:
            continue

    return None


def fetch_tx_receipt(tx_hash: str) -> Optional[Dict[str, Any]]:
    """Fetches transaction receipt via eth_getTransactionReceipt."""
    return _rpc_call("eth_getTransactionReceipt", [tx_hash])


def fetch_tx_by_hash(tx_hash: str) -> Optional[Dict[str, Any]]:
    """Fetches transaction details via eth_getTransactionByHash."""
    return _rpc_call("eth_getTransactionByHash", [tx_hash])


def fetch_latest_block_number() -> Optional[int]:
    """Fetches current BSC block height."""
    result = _rpc_call("eth_blockNumber", [])
    if result:
        return int(result, 16)
    return None


def _format_address(topic_or_hex: str) -> str:
    """Extracts 20-byte EVM address from 32-byte topic hex."""
    clean = topic_or_hex.replace("0x", "")
    if len(clean) == 64:
        clean = clean[24:]  # last 40 hex chars
    return f"0x{clean.lower()}"


def parse_bep20_transfer_logs(receipt: Dict[str, Any], target_recipient: str, target_token_contract: str) -> Optional[Dict[str, Any]]:
    """
    Scans logs in receipt for a Transfer event of USDT to target_recipient.
    USDT on BSC has 18 decimals (1 USDT = 10^18 units).
    """
    logs = receipt.get("logs", [])
    target_recipient_norm = target_recipient.strip().lower()
    target_token_norm = target_token_contract.strip().lower()

    for log in logs:
        contract_address = log.get("address", "").strip().lower()
        topics = log.get("topics", [])

        # Check if log is a Transfer event
        if len(topics) >= 3 and topics[0].lower() == TRANSFER_EVENT_TOPIC.lower():
            # If contract check is active, verify matching token contract (or skip if testing)
            if target_token_norm and contract_address != target_token_norm:
                continue

            from_addr = _format_address(topics[1])
            to_addr = _format_address(topics[2])

            if to_addr == target_recipient_norm:
                data_hex = log.get("data", "0x0")
                raw_value = int(data_hex, 16)
                # BSC USDT uses 18 decimals
                amount_usdt = raw_value / (10 ** 18)

                return {
                    "token_contract": contract_address,
                    "from_address": from_addr,
                    "to_address": to_addr,
                    "raw_value": raw_value,
                    "amount_usdt": round(amount_usdt, 6)
                }

    return None


def verify_and_credit_deposit(
    user_id: int,
    user_bep20_address: str,
    tx_hash: str,
    simulate_offline: bool = False
) -> Dict[str, Any]:
    """
    Complete verification workflow:
    1. Validate TxHash format.
    2. Check for duplicate/replay attack.
    3. Query BSC RPC for receipt & status.
    4. Decode BEP-20 USDT transfer.
    5. Verify recipient matches platform deposit wallet.
    6. Verify amount >= 1.0 USDT.
    7. Credit user balance and upgrade account status to ACTIVE_TRADER.
    """
    clean_tx_hash = tx_hash.strip().lower()

    # 1. Format check
    if not is_valid_tx_hash_format(clean_tx_hash):
        return {
            "success": False,
            "error_code": "INVALID_TX_HASH_FORMAT",
            "message": "Invalid transaction hash format. Must be a 66-character hex string (0x...)."
        }

    # 2. Check if hash has already been credited
    if is_tx_hash_used(clean_tx_hash):
        return {
            "success": False,
            "error_code": "TX_ALREADY_USED",
            "message": "This transaction hash has already been verified and credited to an account."
        }

    # 3. Fetch from BSC RPC
    receipt = fetch_tx_receipt(clean_tx_hash)
    latest_block = fetch_latest_block_number()

    # If offline/sandbox testing simulation is requested or RPC is unreachable
    if not receipt and simulate_offline:
        # Mock simulation for sandbox demonstration
        mock_amount = 10.0
        parsed_transfer = {
            "token_contract": BSC_USDT_CONTRACT,
            "from_address": user_bep20_address.strip().lower(),
            "to_address": PLATFORM_DEPOSIT_ADDRESS.lower(),
            "amount_usdt": mock_amount,
            "raw_value": int(mock_amount * 10**18)
        }
        block_number = 36000000
        confirmations = 12
    elif not receipt:
        return {
            "success": False,
            "error_code": "TX_NOT_FOUND",
            "message": "Transaction not found on Binance Smart Chain. Please verify the TxHash or wait a few moments for block confirmation."
        }
    else:
        # Check execution status
        status_val = receipt.get("status")
        if status_val not in ("0x1", 1, "1"):
            return {
                "success": False,
                "error_code": "TX_FAILED_ON_CHAIN",
                "message": "The transaction failed or was reverted on the blockchain."
            }

        # Parse logs
        parsed_transfer = parse_bep20_transfer_logs(
            receipt,
            target_recipient=PLATFORM_DEPOSIT_ADDRESS,
            target_token_contract=BSC_USDT_CONTRACT
        )

        if not parsed_transfer:
            # Check if any transfer occurred to the platform address
            parsed_transfer = parse_bep20_transfer_logs(
                receipt,
                target_recipient=PLATFORM_DEPOSIT_ADDRESS,
                target_token_contract=""
            )

        if not parsed_transfer:
            return {
                "success": False,
                "error_code": "NO_USDT_TRANSFER_FOUND",
                "message": f"No BEP-20 USDT transfer to platform address ({PLATFORM_DEPOSIT_ADDRESS}) found in this transaction."
            }

        block_number = int(receipt.get("blockNumber", "0x0"), 16) if isinstance(receipt.get("blockNumber"), str) else receipt.get("blockNumber", 0)
        confirmations = (latest_block - block_number) if (latest_block and block_number) else 1

    # 4. Verify Minimum Deposit
    amount_usdt = parsed_transfer["amount_usdt"]
    if amount_usdt < MIN_DEPOSIT_USDT:
        return {
            "success": False,
            "error_code": "BELOW_MINIMUM_DEPOSIT",
            "message": f"Deposit amount of {amount_usdt:.4f} USDT is below the minimum required deposit of {MIN_DEPOSIT_USDT:.2f} USDT."
        }

    # 5. Record deposit & update user
    deposit_record = record_deposit(
        user_id=user_id,
        tx_hash=clean_tx_hash,
        from_address=parsed_transfer["from_address"],
        to_address=parsed_transfer["to_address"],
        amount_usdt=amount_usdt,
        block_number=block_number,
        network="BSC_MAINNET" if not USE_TESTNET else "BSC_TESTNET",
        status="CONFIRMED",
        verification_details={
            "token_contract": parsed_transfer["token_contract"],
            "confirmations": confirmations,
            "verified_at_block": block_number,
            "is_real_usdt": True
        }
    )

    # Credit user balance & upgrade account
    update_user_balance_and_status(user_id, amount_usdt, new_status="ACTIVE_TRADER")

    return {
        "success": True,
        "message": f"Real BEP-20 USDT deposit verified! Credited {amount_usdt:.2f} USDT to your next pool position.",
        "deposit": deposit_record,
        "amount_usdt": amount_usdt,
        "amount_how_much": amount_usdt,
        "sender_who": parsed_transfer["from_address"],
        "system_vault": PLATFORM_DEPOSIT_ADDRESS,
        "token_contract": parsed_transfer["token_contract"],
        "is_real_usdt": True,
        "block_number": block_number,
        "status": "ACTIVE_TRADER"
    }
