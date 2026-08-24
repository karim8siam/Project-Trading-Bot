"""
Authentication & Security Module for ApexTrade AI Platform.
Provides PBKDF2-HMAC-SHA256 password hashing, token encoding/decoding, and BEP20 address validation.
"""

import os
import re
import hmac
import hashlib
import base64
import json
import time
from typing import Dict, Any, Optional, Tuple
from config import JWT_SECRET_KEY


# ==========================================
# 1. BEP20 WALLET ADDRESS VALIDATION
# ==========================================
BEP20_REGEX = re.compile(r"^0x[a-fA-F0-9]{40}$")

def is_valid_bep20_address(address: str) -> bool:
    """
    Validates whether a string is a syntactically valid Binance Smart Chain BEP20 address.
    """
    if not address or not isinstance(address, str):
        return False
    return bool(BEP20_REGEX.match(address.strip()))


def is_valid_email(email: str) -> bool:
    """Validates email format."""
    if not email or not isinstance(email, str):
        return False
    email_regex = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")
    return bool(email_regex.match(email.strip()))


# ==========================================
# 2. PASSWORD HASHING (PBKDF2-HMAC-SHA256)
# ==========================================
def hash_password(password: str) -> str:
    """
    Generates a secure PBKDF2-HMAC-SHA256 hash with a cryptographically secure random salt.
    Format: 'pbkdf2:sha256:iterations$salt$hash'
    """
    salt = os.urandom(16).hex()
    iterations = 100_000
    derived = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        iterations
    )
    return f"pbkdf2:sha256:{iterations}${salt}${derived.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plain text password against a stored PBKDF2 hash using constant-time comparison.
    """
    try:
        header, salt, original_hash = hashed_password.split('$')
        algo, subalgo, iterations = header.split(':')
        iterations = int(iterations)
        
        derived = hashlib.pbkdf2_hmac(
            'sha256',
            plain_password.encode('utf-8'),
            salt.encode('utf-8'),
            iterations
        )
        return hmac.compare_digest(derived.hex(), original_hash)
    except Exception:
        return False


# ==========================================
# 3. JWT TOKEN GENERATION & VERIFICATION
# ==========================================
def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')


def _base64url_decode(data_str: str) -> bytes:
    padding = '=' * (4 - len(data_str) % 4)
    return base64.urlsafe_b64decode((data_str + padding).encode('utf-8'))


def create_access_token(payload: Dict[str, Any], expires_in_seconds: int = 86400 * 7) -> str:
    """
    Creates a cryptographically signed JWT token valid for 7 days by default.
    """
    header = {"alg": "HS256", "typ": "JWT"}
    payload_copy = payload.copy()
    payload_copy["iat"] = int(time.time())
    payload_copy["exp"] = int(time.time()) + expires_in_seconds

    header_b64 = _base64url_encode(json.dumps(header, separators=(',', ':')).encode('utf-8'))
    payload_b64 = _base64url_encode(json.dumps(payload_copy, separators=(',', ':')).encode('utf-8'))
    
    signature_base = f"{header_b64}.{payload_b64}".encode('utf-8')
    signature = hmac.new(JWT_SECRET_KEY.encode('utf-8'), signature_base, hashlib.sha256).digest()
    signature_b64 = _base64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def verify_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verifies token signature and expiration. Returns payload dictionary if valid, None otherwise.
    """
    try:
        parts = token.strip().split('.')
        if len(parts) != 3:
            return None

        header_b64, payload_b64, signature_b64 = parts
        signature_base = f"{header_b64}.{payload_b64}".encode('utf-8')
        expected_sig = hmac.new(JWT_SECRET_KEY.encode('utf-8'), signature_base, hashlib.sha256).digest()
        actual_sig = _base64url_decode(signature_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload_bytes = _base64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode('utf-8'))

        # Expiration check
        if payload.get("exp") and payload["exp"] < time.time():
            return None

        return payload
    except Exception:
        return None
