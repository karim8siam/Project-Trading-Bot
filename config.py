"""
Configuration Module for Binance Futures ML Trading Bot.
Enforces strict security checks, whitelisted pairs, and risk rules.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env if present
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# ==========================================
# 1. EXCHANGE & CREDENTIALS
# ==========================================
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
# Default to Testnet / Sandbox mode for safety
USE_TESTNET = os.getenv("USE_TESTNET", "true").lower() in ("true", "1", "yes")

# ==========================================
# 2. 3-TIER ADAPTIVE MASTER PORTFOLIO (21 WHITELISTED PAIRS)
# ==========================================
# Tier 1: Core Majors (56%+ ML Threshold - Active Momentum)
CORE_MAJOR_SYMBOLS = [
    "BTC/USDT",
    "ETH/USDT",
    "BNB/USDT",
    "SOL/USDT",
    "XRP/USDT",
    "ADA/USDT",
    "NEAR/USDT",
    "TRX/USDT"  # Tron
]

# Tier 2: High-Risk Altcoins (58%+ ML Threshold - High Security Filter)
HIGH_RISK_SYMBOLS_80_PCT = [
    "AVAX/USDT",
    "DOGE/USDT",
    "LINK/USDT",
    "DOT/USDT"
]

# Tier 3: Sniper Volatile Mid-Cap Tokens (60%+ ML Threshold - Ultra-Elite Grade-S+++)
SNIPER_SYMBOLS_87_PCT = [
    "SUI/USDT",
    "APT/USDT",
    "RENDER/USDT",
    "TIA/USDT",
    "INJ/USDT",
    "ARB/USDT",
    "OP/USDT",
    "FET/USDT",
    "SEI/USDT"
]

ALLOWED_SYMBOLS = CORE_MAJOR_SYMBOLS + HIGH_RISK_SYMBOLS_80_PCT + SNIPER_SYMBOLS_87_PCT

# Supported timeframes (1m execution with 15m macro filter)
DEFAULT_TIMEFRAME = os.getenv("DEFAULT_TIMEFRAME", "1m")
HIGHER_TIMEFRAME = os.getenv("HIGHER_TIMEFRAME", "15m")  # For macro trend confirmation

# ==========================================
# 3. RISK MANAGEMENT RULES (STRICT 1% RISK & UNCAPPED OPPORTUNITIES)
# ==========================================
RISK_PER_TRADE_PERCENT = float(os.getenv("RISK_PER_TRADE_PERCENT", "1.0"))  # 1.0% of total balance
DEFAULT_LEVERAGE = int(os.getenv("DEFAULT_LEVERAGE", "5"))  # 5x isolated
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", "21"))  # Uncapped: Takes every qualified opportunity across all 21 pairs
MAX_DAILY_LOSS_PERCENT = float(os.getenv("MAX_DAILY_LOSS_PERCENT", "3.0"))  # Kill switch at 3% daily drawdown

# Take-Profit & Stop-Loss Multipliers (ATR-based)
SL_ATR_MULTIPLIER = float(os.getenv("SL_ATR_MULTIPLIER", "1.5"))  # 1.5x ATR for tight Stop Loss
TP_ATR_MULTIPLIER = float(os.getenv("TP_ATR_MULTIPLIER", "3.0"))  # 3.0x ATR for Take Profit (1:2.5 to 1:3 Asymmetric R:R)

# ==========================================
# 4. MACHINE LEARNING & GEMINI PARAMETERS (CALIBRATED TIERS +1%)
# ==========================================
# Tier 1: Core Majors: BTC, ETH, BNB, SOL, XRP, ADA, NEAR -> Calibrated to 56.0%+
STANDARD_ML_THRESHOLD = float(os.getenv("STANDARD_ML_THRESHOLD", "0.56"))
STANDARD_GEMINI_THRESHOLD = float(os.getenv("STANDARD_GEMINI_THRESHOLD", "56.0"))

# Tier 2: High-Risk Alts: AVAX, DOGE, LINK -> Calibrated to 58.0%+
HIGH_RISK_ML_THRESHOLD = float(os.getenv("HIGH_RISK_ML_THRESHOLD", "0.58"))
HIGH_RISK_GEMINI_THRESHOLD = float(os.getenv("HIGH_RISK_GEMINI_THRESHOLD", "58.0"))

# Tier 3: Sniper Tokens: SUI, APT, RENDER, TIA, INJ, ARB, OP, FET, SEI -> Calibrated to 60.0%+
SNIPER_ML_THRESHOLD = float(os.getenv("SNIPER_ML_THRESHOLD", "0.60"))
SNIPER_GEMINI_THRESHOLD = float(os.getenv("SNIPER_GEMINI_THRESHOLD", "60.0"))

ML_CONFIDENCE_THRESHOLD = STANDARD_ML_THRESHOLD
GEMINI_CONFIDENCE_THRESHOLD = STANDARD_GEMINI_THRESHOLD
RETRAIN_TRADE_INTERVAL = int(os.getenv("RETRAIN_TRADE_INTERVAL", "5"))   # Continuous learning: Auto-retrains every 5 completed trades
MIN_SAMPLES_FOR_TRAIN = int(os.getenv("MIN_SAMPLES_FOR_TRAIN", "10"))    # Active immediately

# ==========================================
# 5. DATABASE & MODEL PATHS
# ==========================================
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "trading_journal.db"
MODEL_PATH = DATA_DIR / "meta_classifier.joblib"
SCALER_PATH = DATA_DIR / "feature_scaler.joblib"


# ==========================================
# 6. WEB PLATFORM & BEP20 DEPOSIT SETTINGS
# ==========================================
# Master Platform BEP20 Address (where users send >= 1.0 USDT deposits)
PLATFORM_DEPOSIT_ADDRESS = os.getenv(
    "PLATFORM_DEPOSIT_ADDRESS", 
    "0x66A06fA03BE98383fe4F73a5f1783332CAC0F5A0"
)

# Binance Hot Wallet Address (where accumulated daily funds sweep for bot trading)
BINANCE_BOT_WALLET_ADDRESS = os.getenv(
    "BINANCE_BOT_WALLET_ADDRESS",
    "0xf13c3ce17b921ddff8d7057e2363fc79cac1fb2b"
)

# Daily Sweep Schedule (Default: 00:00 UTC / 12:00 AM UTC)
DAILY_SWEEP_HOUR_UTC = int(os.getenv("DAILY_SWEEP_HOUR_UTC", "0"))
DAILY_SWEEP_MINUTE_UTC = int(os.getenv("DAILY_SWEEP_MINUTE_UTC", "0"))
AUTO_SWEEP_ENABLED = os.getenv("AUTO_SWEEP_ENABLED", "true").lower() in ("true", "1", "yes")

# Binance Smart Chain (BSC) Settings
BSC_RPC_URLS = [
    os.getenv("BSC_RPC_URL", "https://bsc-dataseed.binance.org/"),
    "https://bsc-dataseed1.defibit.io/",
    "https://bsc-dataseed2.ninicoin.io/",
    "https://rpc.ankr.com/bsc"
]

# Official BSC BEP20 USDT Contract
# Mainnet USDT: 0x55d398326f99059fF775485246999027B3197955 (18 decimals)
# Testnet USDT: 0x337610d27c682E347C9cD60BD4b3b107C9d34dDd
BSC_USDT_CONTRACT = os.getenv(
    "BSC_USDT_CONTRACT", 
    "0x55d398326f99059fF775485246999027B3197955"
).lower()

# Minimum Deposit Rule (Equal or more than 1 USDT)
MIN_DEPOSIT_USDT = float(os.getenv("MIN_DEPOSIT_USDT", "1.0"))

# Security & Web Server
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "apextrade_ai_super_secret_jwt_key_bsc_prod_2026")
SERVER_PORT = int(os.getenv("PORT", "8000"))
SERVER_HOST = os.getenv("HOST", "0.0.0.0")



ALL_SUPPORTED_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT", "NEAR/USDT", "TRX/USDT",
    "AVAX/USDT", "DOGE/USDT", "LINK/USDT", "DOT/USDT",
    "SUI/USDT", "APT/USDT", "RENDER/USDT", "TIA/USDT", "INJ/USDT", "ARB/USDT", "OP/USDT", "FET/USDT", "SEI/USDT"
]


def validate_symbol(symbol: str) -> str:
    """
    Guarantees that only valid Binance USD(S)-M Futures symbols can ever be processed.
    """
    normalized = symbol.upper().replace(":", "").replace("-", "/")
    if "/" not in normalized and normalized.endswith("USDT"):
        normalized = normalized[:-4] + "/USDT"
    if normalized not in ALLOWED_SYMBOLS and normalized not in ALL_SUPPORTED_SYMBOLS:
        raise ValueError(
            f"SECURITY VIOLATION: Symbol '{symbol}' is not a recognized supported futures pair."
        )
    return normalized

