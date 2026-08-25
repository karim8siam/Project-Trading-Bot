"""
Orbital Trading Platform Configuration.
Constants for Web3 On-Chain Verification, Master Vault, Admin Control, and 2-of-3 Auth.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
SERVER_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

if os.getenv("VERCEL"):
    DB_PATH = Path("/tmp/orbital_platform.db")
else:
    DATA_DIR = BASE_DIR / "data"
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    DB_PATH = DATA_DIR / "orbital_platform.db"

# Database Configuration (Neon Serverless PostgreSQL or local SQLite fallback)
raw_db_url = os.getenv("DATABASE_URL", "").strip()
if raw_db_url.startswith("postgres://"):
    DATABASE_URL = raw_db_url.replace("postgres://", "postgresql://", 1)
else:
    DATABASE_URL = raw_db_url
USE_POSTGRES = bool(DATABASE_URL)

# Trading Bot Database Integration Path
TRADING_BOT_DIR = Path("/Users/karimsiam/.gemini/antigravity/scratch/crypto_futures_trading_bot")
TRADING_BOT_DB = TRADING_BOT_DIR / "data" / "trading_journal.db"

# Master Deposit Wallet (BEP-20 / BNB Smart Chain)
MASTER_METAMASK_ADDRESS = os.getenv(
    "MASTER_METAMASK_ADDRESS",
    "0x66A06fA03BE98383fe4F73a5f1783332CAC0F5A0"
)

# Master MetaMask Private Key (for on-chain automated sweeping to Binance)
METAMASK_PRIVATE_KEY = os.getenv(
    "METAMASK_PRIVATE_KEY",
    "41650f50f404e962323dab6f1da94d8ddde3046568369b8554c3c35c06a069f3"
)

# Binance Official BEP-20 Deposit Destination
BINANCE_DEPOSIT_BEP20_ADDRESS = os.getenv(
    "BINANCE_DEPOSIT_BEP20_ADDRESS",
    "0xf13c3ce17b921ddff8d7057e2363fc79cac1fb2b"
)

# Master Admin Multi-Layer Security Verification Credentials
MASTER_ADMIN_PIN = os.getenv("MASTER_ADMIN_PIN", "499011")
MASTER_ADMIN_PASS_1 = os.getenv("MASTER_ADMIN_PASS_1", "Matrix8#MasterKey2026!")
MASTER_ADMIN_PASS_2 = os.getenv("MASTER_ADMIN_PASS_2", "AlphaOmega$Web3Vault_Secured99")
MASTER_ADMIN_SECURITY_WORD = os.getenv("MASTER_ADMIN_SECURITY_WORD", "satoshi_secret_bep20_2026")

# Binance Smart Chain (BSC) Mainnet Contracts & RPCs
BSC_CHAIN_ID = 56
BSC_USDT_CONTRACT = "0x55d398326f99059fF775485246999027B3197955"  # Official Binance-Peg BUSD-T / USDT
BSC_RPC_URLS = [
    "https://bsc-dataseed.binance.org/",
    "https://bsc-dataseed1.defibit.io/",
    "https://bsc-dataseed1.ninicoin.io/",
    "https://binance.llamarpc.com"
]

# Security & Authentication (2-of-3 MFA + 30-Day Device Persistence)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "orbital-trading-vault-ultra-secure-jwt-key-2026-master")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_DAYS = 30  # Device session persists for 30 days without repeated login

# 24-Hour Epoch & Profit-Sharing Parameters (60% User Share / 40% Admin Cut)
EPOCH_ROLLOVER_HOUR_UTC = 18  # Daily epoch cycles rollover at 18:00 UTC (12:00 AM Midnight Local Time UTC+6)
PLATFORM_PERFORMANCE_FEE_PCT = 40.0  # 40% Admin cut on profit days; 0% on loss days
USER_PROFIT_SHARE_PCT = 60.0  # 60% Net profit share added directly to user initial balance on profit days
MIN_DEPOSIT_USDT = 0.01  # No minimum limit (Any amount > 0 is accepted)
MIN_WITHDRAW_USDT = 0.01  # No minimum limit (Any amount > 0 is accepted)
