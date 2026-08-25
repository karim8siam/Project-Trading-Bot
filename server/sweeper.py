"""
MetaMask to Binance BEP-20 Fund Sweeper Module.
Supports:
1. 1-Click Automated On-Chain Transfer (Web3 with Private Key when BNB gas is available).
2. Manual Sweep Confirmation (When Admin manually transfers USDT via MetaMask App).
"""

from typing import Dict, Any, Optional
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from datetime import datetime
import json

from config import (
    MASTER_METAMASK_ADDRESS,
    METAMASK_PRIVATE_KEY,
    BINANCE_DEPOSIT_BEP20_ADDRESS,
    BSC_USDT_CONTRACT,
    BSC_RPC_URLS
)
from database import get_db

# Standard Minimal BEP-20 Token ABI
BEP20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
]


class WalletSweeper:
    """
    Manages fund sweeping from Master MetaMask to Binance BEP-20.
    """

    def __init__(self):
        try:
            self.master_address = Web3.to_checksum_address(MASTER_METAMASK_ADDRESS)
            self.binance_address = Web3.to_checksum_address(BINANCE_DEPOSIT_BEP20_ADDRESS)
            self.usdt_contract_address = Web3.to_checksum_address(BSC_USDT_CONTRACT)
        except Exception:
            self.master_address = MASTER_METAMASK_ADDRESS
            self.binance_address = BINANCE_DEPOSIT_BEP20_ADDRESS
            self.usdt_contract_address = BSC_USDT_CONTRACT
        self.private_key = METAMASK_PRIVATE_KEY
        self.w3 = None

    def _init_web3(self):
        for rpc in BSC_RPC_URLS:
            try:
                provider = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 6}))
                if provider.is_connected():
                    self.w3 = provider
                    self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                    return
            except Exception:
                continue
        self.w3 = Web3(Web3.HTTPProvider("https://bsc-dataseed.binance.org/"))
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    def _ensure_w3(self):
        if self.w3 is None:
            self._init_web3()

    def get_wallet_balances(self) -> Dict[str, Any]:
        """
        Fetches live BNB (gas) balance and BEP-20 USDT balance of Master MetaMask wallet.
        """
        self._ensure_w3()
        try:
            # 1. Native BNB balance
            bnb_wei = self.w3.eth.get_balance(self.master_address)
            bnb_balance = float(self.w3.from_wei(bnb_wei, "ether"))

            # 2. BEP-20 USDT balance
            contract = self.w3.eth.contract(address=self.usdt_contract_address, abi=BEP20_ABI)
            raw_usdt = contract.functions.balanceOf(self.master_address).call()
            usdt_balance = float(raw_usdt) / (10 ** 18)

            has_gas = bnb_balance >= 0.0005

            return {
                "success": True,
                "master_address": self.master_address,
                "binance_destination": self.binance_address,
                "bnb_balance": round(bnb_balance, 5),
                "usdt_balance": round(usdt_balance, 2),
                "has_gas": has_gas,
                "gas_status": "BNB Gas Ready ✅" if has_gas else "⚠️ Low/No BNB Gas (Need ~0.0005 BNB for Auto-Send)",
            }
        except Exception as e:
            return {
                "success": False,
                "master_address": self.master_address,
                "binance_destination": self.binance_address,
                "bnb_balance": 0.0,
                "usdt_balance": 0.0,
                "has_gas": False,
                "error": str(e)
            }

    def sweep_usdt_auto(self, amount_usdt: Optional[float] = None) -> Dict[str, Any]:
        """
        Executes automated on-chain BEP-20 USDT transfer from Master MetaMask to Binance.
        """
        bal_info = self.get_wallet_balances()
        if not bal_info["success"]:
            return {"success": False, "error": f"Failed to query wallet: {bal_info.get('error')}"}

        bnb_bal = bal_info["bnb_balance"]
        wallet_usdt = bal_info["usdt_balance"]

        if bnb_bal < 0.0004:
            return {
                "success": False,
                "error": f"⚠️ Insufficient BNB for network gas fee (Current BNB: {bnb_bal:.5f} BNB). Please deposit ~$0.30 of BNB into MetaMask ({self.master_address}), OR use the Manual Transfer option below."
            }

        target_amount = amount_usdt if (amount_usdt and amount_usdt > 0) else wallet_usdt
        if target_amount <= 0:
            return {"success": False, "error": "No USDT available to transfer (Balance is $0.00 USDT)."}

        if target_amount > wallet_usdt:
            return {"success": False, "error": f"Requested amount (${target_amount:.2f}) exceeds wallet balance (${wallet_usdt:.2f} USDT)."}

        try:
            contract = self.w3.eth.contract(address=self.usdt_contract_address, abi=BEP20_ABI)
            raw_value = int(target_amount * (10 ** 18))
            nonce = self.w3.eth.get_transaction_count(self.master_address)
            gas_price = self.w3.eth.gas_price

            # Build Transfer TX
            tx = contract.functions.transfer(
                self.binance_address,
                raw_value
            ).build_transaction({
                "from": self.master_address,
                "nonce": nonce,
                "gas": 60000,
                "gasPrice": gas_price,
                "chainId": 56
            })

            # Sign with private key
            signed_tx = self.w3.eth.account.sign_transaction(tx, private_key=self.private_key)
            tx_hash_bytes = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash = self.w3.to_hex(tx_hash_bytes)

            now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            # Log Sweep in DB
            now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            sweep_id = f"SWP-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            try:
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO sweeps (
                    sweep_id, amount_usdt, from_address, to_address, method, tx_hash, created_at
                ) VALUES (?, ?, ?, ?, 'AUTOMATED_ONCHAIN', ?, ?)
                """, (sweep_id, target_amount, self.master_address, self.binance_address, tx_hash, now_str))
                conn.commit()
                conn.close()
            except Exception as dbe:
                print(f"[Sweeper DB Error] {dbe}")

            return {
                "success": True,
                "sweep_id": sweep_id,
                "method": "AUTOMATED_ONCHAIN",
                "tx_hash": tx_hash,
                "amount_usdt": round(target_amount, 2),
                "from_address": self.master_address,
                "to_binance_address": self.binance_address,
                "bscscan_url": f"https://bscscan.com/tx/{tx_hash}",
                "timestamp": now_str,
                "message": f"Successfully swept ${target_amount:.2f} USDT directly to Binance! Tx: {tx_hash}"
            }

        except Exception as e:
            return {"success": False, "error": f"On-chain transfer failed: {str(e)}"}

    def confirm_manual_sweep(self, amount_usdt: float, tx_hash: Optional[str] = None) -> Dict[str, Any]:
        """
        Registers a manual transfer completed via MetaMask App to Binance.
        """
        if amount_usdt <= 0:
            return {"success": False, "error": "Amount must be greater than zero."}

        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        sweep_id = f"SWP-MAN-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO sweeps (
                sweep_id, amount_usdt, from_address, to_address, method, tx_hash, created_at
            ) VALUES (?, ?, ?, ?, 'MANUAL_METAMASK', ?, ?)
            """, (sweep_id, amount_usdt, self.master_address, self.binance_address, tx_hash or "MANUAL_TX", now_str))
            conn.commit()
            conn.close()
        except Exception as dbe:
            print(f"[Sweeper DB Error] {dbe}")

        return {
            "success": True,
            "sweep_id": sweep_id,
            "method": "MANUAL_METAMASK",
            "amount_usdt": round(amount_usdt, 2),
            "from_address": self.master_address,
            "to_binance_address": self.binance_address,
            "tx_hash": tx_hash or "MANUAL_TX",
            "timestamp": now_str,
            "message": f"Manual sweep of ${amount_usdt:.2f} USDT to Binance ({self.binance_address}) verified and recorded!"
        }

    def payout_withdrawal_auto(self, withdrawal_id: str) -> Dict[str, Any]:
        """
        Executes automated on-chain BEP-20 USDT transfer from Master MetaMask to user's registered BEP-20 address.
        """
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM withdrawals WHERE withdrawal_id = ?", (withdrawal_id,))
        w = cursor.fetchone()
        if not w:
            conn.close()
            return {"success": False, "error": "Withdrawal request not found."}

        if w["status"] != "PENDING":
            conn.close()
            return {"success": False, "error": f"Withdrawal is already {w['status']}."}

        recipient = w["bep20_recipient"]
        target_amount = float(w["amount_usdt"])

        bal_info = self.get_wallet_balances()
        if not bal_info["success"]:
            conn.close()
            return {"success": False, "error": f"Failed to query wallet: {bal_info.get('error')}"}

        bnb_bal = bal_info["bnb_balance"]
        wallet_usdt = bal_info["usdt_balance"]

        if bnb_bal < 0.0004:
            conn.close()
            return {
                "success": False,
                "error": f"⚠️ Insufficient BNB in MetaMask for gas fee (Current: {bnb_bal:.5f} BNB). Please deposit ~$0.30 BNB to {self.master_address}, OR use Manual Payout."
            }

        if wallet_usdt < target_amount:
            conn.close()
            return {
                "success": False,
                "error": f"⚠️ Insufficient USDT in MetaMask (Current: ${wallet_usdt:.2f} USDT). Please deposit or transfer USDT from Binance first, OR use Manual Payout."
            }

        try:
            contract = self.w3.eth.contract(address=self.usdt_contract_address, abi=BEP20_ABI)
            raw_value = int(target_amount * (10 ** 18))
            nonce = self.w3.eth.get_transaction_count(self.master_address)
            gas_price = self.w3.eth.gas_price

            # Build Transfer TX directly to user's BEP-20
            tx = contract.functions.transfer(
                self.w3.to_checksum_address(recipient),
                raw_value
            ).build_transaction({
                "from": self.master_address,
                "nonce": nonce,
                "gas": 60000,
                "gasPrice": gas_price,
                "chainId": 56
            })

            signed_tx = self.w3.eth.account.sign_transaction(tx, private_key=self.private_key)
            tx_hash_bytes = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash = self.w3.to_hex(tx_hash_bytes)

            now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("""
            UPDATE withdrawals SET
                status = 'COMPLETED',
                tx_hash = ?,
                completed_at = ?
            WHERE withdrawal_id = ?
            """, (tx_hash, now_str, withdrawal_id))
            conn.commit()
            conn.close()

            return {
                "success": True,
                "withdrawal_id": withdrawal_id,
                "amount_usdt": target_amount,
                "recipient": recipient,
                "tx_hash": tx_hash,
                "bscscan_url": f"https://bscscan.com/tx/{tx_hash}",
                "message": f"Successfully paid ${target_amount:.2f} USDT to {recipient}! Tx: {tx_hash}"
            }

        except Exception as e:
            conn.close()
            return {"success": False, "error": f"On-chain payout failed: {str(e)}"}

    def payout_withdrawal_manual(self, withdrawal_id: str, tx_hash: Optional[str] = None) -> Dict[str, Any]:
        """
        Confirms a manual payout sent via MetaMask App directly to user's address.
        """
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM withdrawals WHERE withdrawal_id = ?", (withdrawal_id,))
        w = cursor.fetchone()
        if not w:
            conn.close()
            return {"success": False, "error": "Withdrawal request not found."}

        if w["status"] != "PENDING":
            conn.close()
            return {"success": False, "error": f"Withdrawal is already {w['status']}."}

        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        final_tx = tx_hash or "MANUAL_PAYOUT_CONFIRMED"

        cursor.execute("""
        UPDATE withdrawals SET
            status = 'COMPLETED',
            tx_hash = ?,
            completed_at = ?
        WHERE withdrawal_id = ?
        """, (final_tx, now_str, withdrawal_id))
        conn.commit()
        conn.close()

        return {
            "success": True,
            "withdrawal_id": withdrawal_id,
            "amount_usdt": float(w["amount_usdt"]),
            "recipient": w["bep20_recipient"],
            "tx_hash": final_tx,
            "message": f"Manual payout of ${w['amount_usdt']:.2f} USDT to {w['bep20_recipient']} confirmed and marked completed!"
        }

    def reject_withdrawal(self, withdrawal_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        """
        Rejects a withdrawal request and refunds the USDT back to the user's withdrawable balance.
        """
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM withdrawals WHERE withdrawal_id = ?", (withdrawal_id,))
        w = cursor.fetchone()
        if not w:
            conn.close()
            return {"success": False, "error": "Withdrawal request not found."}

        if w["status"] != "PENDING":
            conn.close()
            return {"success": False, "error": f"Cannot reject withdrawal that is already {w['status']}."}

        amount = float(w["amount_usdt"])
        user_uuid = w["user_uuid"]
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        # Refund user balance
        cursor.execute("""
        UPDATE users SET
            balance_usdt = balance_usdt + ?,
            total_withdrawn = total_withdrawn - ?
        WHERE user_uuid = ?
        """, (amount, amount, user_uuid))

        cursor.execute("""
        UPDATE withdrawals SET
            status = 'REJECTED',
            completed_at = ?
        WHERE withdrawal_id = ?
        """, (now_str, withdrawal_id))
        conn.commit()
        conn.close()

        return {
            "success": True,
            "withdrawal_id": withdrawal_id,
            "refunded_amount": amount,
            "message": f"Withdrawal rejected. ${amount:.2f} USDT refunded back to user's balance."
        }


# Global Sweeper Instance
sweeper = WalletSweeper()
