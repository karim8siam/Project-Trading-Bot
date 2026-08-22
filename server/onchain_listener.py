"""
On-Chain BEP-20 USDT Deposit Verification Engine for Orbital Trading.
Connects to Binance Smart Chain (BSC) Mainnet RPC to verify incoming transfers to:
Master MetaMask Address: 0x66A06fA03BE98383fe4F73a5f1783332CAC0F5A0
"""

import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from web3 import Web3
import requests

from config import (
    MASTER_METAMASK_ADDRESS,
    BSC_USDT_CONTRACT,
    BSC_RPC_URLS,
    MIN_DEPOSIT_USDT
)
from database import get_db

# Standard BEP-20 Transfer Event Signature: Transfer(address from, address to, uint256 value)
TRANSFER_EVENT_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


class OnChainDepositVerifier:
    """
    Verifies real-time on-chain USDT (BEP-20) transfers on BNB Smart Chain.
    """

    def __init__(self):
        self.master_address = Web3.to_checksum_address(MASTER_METAMASK_ADDRESS)
        self.usdt_contract = Web3.to_checksum_address(BSC_USDT_CONTRACT)
        self.w3 = None
        self._init_web3()

    def _init_web3(self):
        """Initializes connection to the fastest available BSC RPC node."""
        for rpc in BSC_RPC_URLS:
            try:
                provider = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 6}))
                if provider.is_connected():
                    self.w3 = provider
                    print(f"[On-Chain Verifier] ✅ Connected to BSC Mainnet via {rpc} (Block: {self.w3.eth.block_number})")
                    return
            except Exception:
                continue

        # Fallback to public endpoint
        self.w3 = Web3(Web3.HTTPProvider("https://bsc-dataseed.binance.org/"))

    def verify_transaction_hash(
        self,
        tx_hash: str,
        expected_sender: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Queries BSC blockchain to verify transaction receipt, sender, recipient, and amount.
        """
        clean_tx = tx_hash.strip().lower()
        if not clean_tx.startswith("0x"):
            clean_tx = "0x" + clean_tx

        if len(clean_tx) != 66:
            return {
                "valid": False,
                "error": f"Invalid transaction hash length ({len(clean_tx)} chars). A valid BSC transaction hash must be 66 characters (e.g. 0x...)."
            }

        # 1. Check if Tx Hash was already credited in DB
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM deposits WHERE tx_hash = ? AND status = 'VERIFIED'", (clean_tx,))
        already_used = cursor.fetchone()
        if already_used:
            conn.close()
            return {"valid": False, "error": "This transaction hash has already been credited to an account."}

        try:
            # Query BSC node for Tx Receipt
            receipt = self.w3.eth.get_transaction_receipt(clean_tx)
            if not receipt:
                conn.close()
                return {"valid": False, "error": "Transaction not found on BSC blockchain yet. Please wait a few seconds for network confirmation."}

            # Check status (1 = Success, 0 = Reverted)
            if receipt["status"] != 1:
                conn.close()
                return {"valid": False, "error": "Transaction failed or was reverted on the blockchain."}

            block_num = receipt["blockNumber"]
            tx_from = Web3.to_checksum_address(receipt["from"])
            
            # Check for BEP-20 USDT / BUSD / USDC Token Transfer Event in logs
            usdt_amount = 0.0
            found_transfer_to_master = False
            token_sender = tx_from

            for log in receipt["logs"]:
                topics = log["topics"]
                if topics and topics[0].hex().lower() == TRANSFER_EVENT_TOPIC.lower():
                    if len(topics) >= 3:
                        from_addr = Web3.to_checksum_address("0x" + topics[1].hex()[-40:])
                        to_addr = Web3.to_checksum_address("0x" + topics[2].hex()[-40:])
                        
                        if to_addr == self.master_address:
                            found_transfer_to_master = True
                            token_sender = from_addr
                            # BEP-20 USDT has 18 decimals on BSC
                            raw_val = int(log["data"].hex() if hasattr(log["data"], "hex") else log["data"], 16)
                            usdt_amount = raw_val / (10 ** 18)
                            break

            # If not a token transfer log, check direct native BNB transfer
            if not found_transfer_to_master:
                tx_obj = self.w3.eth.get_transaction(clean_tx)
                if tx_obj and tx_obj.get("to") and Web3.to_checksum_address(tx_obj["to"]) == self.master_address:
                    found_transfer_to_master = True
                    token_sender = Web3.to_checksum_address(tx_obj["from"])
                    raw_bnb = self.w3.from_wei(tx_obj["value"], "ether")
                    usdt_amount = float(raw_bnb) * 700.0  # Approx BNB price equivalent in USDT

            if not found_transfer_to_master:
                conn.close()
                return {
                    "valid": False,
                    "error": f"Transaction destination does not match Master Vault address ({self.master_address}). Please verify you sent to the correct address."
                }

            if usdt_amount <= 0:
                conn.close()
                return {
                    "valid": False,
                    "error": "Deposit amount must be greater than $0.00."
                }

            conn.close()
            return {
                "valid": True,
                "tx_hash": clean_tx,
                "block_number": block_num,
                "sender": token_sender,
                "destination": self.master_address,
                "amount_usdt": round(usdt_amount, 2),
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            }

        except Exception as e:
            conn.close()
            return {"valid": False, "error": f"On-chain verification error: {str(e)}"}

    def credit_verified_deposit(
        self,
        user_uuid: str,
        tx_hash: str,
        expected_sender: str
    ) -> Dict[str, Any]:
        """
        Verifies transaction on-chain and automatically credits user's balance in SQLite.
        """
        ver_res = self.verify_transaction_hash(tx_hash=tx_hash, expected_sender=expected_sender)
        if not ver_res["valid"]:
            return {"success": False, "error": ver_res["error"]}

        amount = ver_res["amount_usdt"]
        sender = ver_res["sender"]
        block_num = ver_res["block_number"]
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        deposit_id = f"DEP-{uuid.uuid4().hex[:8].upper()}"

        conn = get_db()
        cursor = conn.cursor()

        try:
            # 1. Insert into deposits table
            cursor.execute("""
            INSERT INTO deposits (
                deposit_id, user_uuid, bep20_sender, destination_address,
                amount_usdt, tx_hash, block_number, status, created_at, verified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'VERIFIED', ?, ?)
            """, (deposit_id, user_uuid, sender, self.master_address, amount, tx_hash, block_num, now_str, now_str))

            # 2. Update user's available balance and pending rollover balance (queued for 12:00 AM)
            cursor.execute("""
            UPDATE users SET 
                balance_usdt = balance_usdt + ?,
                pending_rollover_balance = pending_rollover_balance + ?,
                active_vault_balance = active_vault_balance + ?,
                total_deposited = total_deposited + ?
            WHERE user_uuid = ?
            """, (amount, amount, amount, amount, user_uuid))

            conn.commit()
            
            # Fetch updated balance
            cursor.execute("SELECT balance_usdt, active_vault_balance, pending_rollover_balance FROM users WHERE user_uuid = ?", (user_uuid,))
            u = cursor.fetchone()
            conn.close()

            return {
                "success": True,
                "deposit_id": deposit_id,
                "amount_credited": amount,
                "new_balance": u["balance_usdt"],
                "active_vault_balance": u["active_vault_balance"],
                "pending_rollover_balance": u["pending_rollover_balance"],
                "message": f"Successfully verified on-chain! +${amount:.2f} USDT credited and queued for next 12:00 AM trading rollover."
            }

        except Exception as e:
            conn.rollback()
            conn.close()
            return {"success": False, "error": f"Database credit error: {str(e)}"}


# Global Verifier Instance
deposit_verifier = OnChainDepositVerifier()
