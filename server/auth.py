"""
Authentication & 2-of-3 Multi-Factor Verifier for Orbital Trading.
Implements:
1. Registration with Email, Password, and BEP-20 Address.
2. Flexible 2-of-3 Login (Authenticate with ANY 2 of the 3 credentials):
   - Combo A: Email + Password
   - Combo B: Email + BEP-20 Wallet
   - Combo C: BEP-20 Wallet + Password
3. Persistent Device Token Management (30-Day Auto-Login).
"""

import uuid
import jwt
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
import os
import secrets
import hashlib
from web3 import Web3

from config import JWT_SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRY_DAYS
from database import get_db

def hash_password(password: str) -> str:
    """Hashes a password using PBKDF2-HMAC-SHA256 with random salt."""
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return f"{salt}${key.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against stored salt and PBKDF2 hash."""
    try:
        salt, key_hex = hashed_password.split('$')
        computed_key = hashlib.pbkdf2_hmac('sha256', plain_password.encode('utf-8'), salt.encode('utf-8'), 100000)
        return secrets.compare_digest(computed_key.hex(), key_hex)
    except Exception:
        return False


def normalize_address(address: str) -> str:
    """Normalizes an Ethereum / BSC BEP-20 address to standard checksum format."""
    cleaned = address.strip()
    if not cleaned.startswith("0x"):
        cleaned = "0x" + cleaned
    return Web3.to_checksum_address(cleaned)


def create_device_token(user_uuid: str, email: str, bep20_address: str) -> str:
    """Generates a long-lived 30-day JWT device token for persistent auto-login."""
    expire = datetime.utcnow() + timedelta(days=JWT_EXPIRY_DAYS)
    payload = {
        "sub": user_uuid,
        "email": email,
        "bep20": bep20_address,
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "device_session"
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def verify_device_token(token: str) -> Optional[Dict[str, Any]]:
    """Verifies and decodes a JWT device token."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except Exception:
        return None


def register_user(
    email: str,
    password: str,
    bep20_address: str,
    telegram_handle: Optional[str] = None
) -> Dict[str, Any]:
    """
    Registers a new user with Email, Password, and BEP-20 Wallet Address.
    """
    email_clean = email.strip().lower()
    if not email_clean or "@" not in email_clean:
        return {"success": False, "error": "Invalid email address."}

    if len(password) < 6:
        return {"success": False, "error": "Password must be at least 6 characters long."}

    try:
        bep20_clean = normalize_address(bep20_address)
    except Exception:
        return {"success": False, "error": "Invalid BEP-20 wallet address format."}

    conn = get_db()
    cursor = conn.cursor()

    # Check if Email or BEP20 already exists
    cursor.execute("SELECT id, email, bep20_address FROM users WHERE email = ? OR bep20_address = ?", (email_clean, bep20_clean))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        if existing["email"] == email_clean:
            return {"success": False, "error": "An account with this email already exists."}
        else:
            return {"success": False, "error": "This BEP-20 wallet address is already registered."}

    user_uuid = f"ORB-{uuid.uuid4().hex[:8].upper()}"
    pass_hash = hash_password(password)
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # Generate persistent device token
    device_token = create_device_token(user_uuid, email_clean, bep20_clean)

    cursor.execute("""
    INSERT INTO users (
        user_uuid, email, password_hash, bep20_address, telegram_handle,
        balance_usdt, active_vault_balance, total_deposited, total_withdrawn,
        total_profit_earned, device_token, is_admin, created_at, last_login_at
    ) VALUES (?, ?, ?, ?, ?, 0.0, 0.0, 0.0, 0.0, 0.0, ?, 0, ?, ?)
    """, (user_uuid, email_clean, pass_hash, bep20_clean, telegram_handle, device_token, now_str, now_str))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "user_uuid": user_uuid,
        "email": email_clean,
        "bep20_address": bep20_clean,
        "token": device_token,
        "message": "Account created successfully!"
    }


def login_user_2_of_3(
    email: Optional[str] = None,
    password: Optional[str] = None,
    bep20_address: Optional[str] = None
) -> Dict[str, Any]:
    """
    Authenticates a user if ANY 2 OF THE 3 credentials match:
    1. Email + Password
    2. Email + BEP-20 Wallet
    3. BEP-20 Wallet + Password
    """
    provided_count = sum(1 for x in [email, password, bep20_address] if x and str(x).strip())
    if provided_count < 2:
        return {
            "success": False,
            "error": "2-of-3 Multi-Factor Rule: Please provide at least TWO credentials (e.g. Email + Password, Email + BEP20, or BEP20 + Password)."
        }

    email_clean = email.strip().lower() if email else None
    pass_clean = password.strip() if password else None
    bep20_clean = None
    if bep20_address and bep20_address.strip():
        try:
            bep20_clean = normalize_address(bep20_address)
        except Exception:
            bep20_clean = None

    conn = get_db()
    cursor = conn.cursor()

    # Find user candidates
    user = None
    if email_clean:
        cursor.execute("SELECT * FROM users WHERE email = ?", (email_clean,))
        user = cursor.fetchone()

    if not user and bep20_clean:
        cursor.execute("SELECT * FROM users WHERE bep20_address = ?", (bep20_clean,))
        user = cursor.fetchone()

    if not user:
        conn.close()
        return {"success": False, "error": "No matching Orbital account found."}

    # Evaluate 2-of-3 Match Score
    matches = 0
    matched_factors = []

    # Factor 1: Email Match
    if email_clean and user["email"] == email_clean:
        matches += 1
        matched_factors.append("Email ✅")

    # Factor 2: Password Match
    if pass_clean and verify_password(pass_clean, user["password_hash"]):
        matches += 1
        matched_factors.append("Password ✅")

    # Factor 3: BEP-20 Address Match
    if bep20_clean and user["bep20_address"].lower() == bep20_clean.lower():
        matches += 1
        matched_factors.append("BEP-20 Address ✅")

    if matches < 2:
        conn.close()
        return {
            "success": False,
            "error": "Authentication failed. You must verify at least 2 matching factors.",
            "matched_factors": matched_factors
        }

    # Generate new device session token
    user_uuid = user["user_uuid"]
    token = create_device_token(user_uuid, user["email"], user["bep20_address"])
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("UPDATE users SET device_token = ?, last_login_at = ? WHERE user_uuid = ?", (token, now_str, user_uuid))
    conn.commit()
    conn.close()

    return {
        "success": True,
        "user_uuid": user_uuid,
        "email": user["email"],
        "bep20_address": user["bep20_address"],
        "token": token,
        "matched_factors": matched_factors,
        "message": f"Login successful via 2-of-3 verification ({', '.join(matched_factors)})!"
    }


def get_user_by_token(token: str) -> Optional[Dict[str, Any]]:
    """Retrieves full user record using valid device session token."""
    payload = verify_device_token(token)
    if not payload:
        return None

    user_uuid = payload.get("sub")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_uuid = ?", (user_uuid,))
    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None
