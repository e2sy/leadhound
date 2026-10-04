"""Accounts + sessions — the login system.

Zero-dependency and honest about it:
  * passwords  -> hashlib.scrypt (memory-hard, stdlib), random 16-byte salt
  * sessions   -> 256-bit random tokens; only the SHA-256 of a token is stored,
                  so a leaked database can't be replayed as a login
  * transport  -> HttpOnly + SameSite=Lax cookie (blocks cross-site JS reads
                  and most cross-site POSTs), 30-day sliding expiry

Everything lives in your local SQLite file — local-first by design.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta

from . import db

COOKIE_NAME = "lh_session"
SESSION_TTL_DAYS = 30
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(ValueError):
    """Raised with a user-facing message for register/login problems."""


# ------------------------------------------------------------------ passwords
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32
    )
    return (
        f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}"
        f"${salt.hex()}${digest.hex()}"
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    try:
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(hash_hex)),
        )
    except (ValueError, TypeError):
        return False
    return secrets.compare_digest(digest.hex(), hash_hex)


# ------------------------------------------------------------------- accounts
def _validate(email: str, password: str) -> None:
    email = (email or "").strip()
    if not _EMAIL_RE.match(email):
        raise AuthError("enter a valid email address")
    if len(password or "") < 8:
        raise AuthError("password must be at least 8 characters")


def register(email: str, password: str) -> dict:
    """Create an account. Returns the user dict (no secrets)."""
    _validate(email, password)
    if db.user_by_email(email):
        raise AuthError("that email already has an account — log in instead")
    return db.create_user(email, hash_password(password))


def login(email: str, password: str) -> dict:
    """Verify credentials. Returns the user dict or raises AuthError."""
    user = db.user_by_email(email or "")
    if not user or not verify_password(password or "", user["password_hash"]):
        raise AuthError("wrong email or password")
    return {"id": user["id"], "email": user["email"]}


# ------------------------------------------------------------------- sessions
def _expiry() -> str:
    return (datetime.now(UTC) + timedelta(days=SESSION_TTL_DAYS)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def start_session(user_id: int) -> str:
    """Mint a session token; only its hash is persisted."""
    token = secrets.token_urlsafe(32)
    db.create_session(user_id, hashlib.sha256(token.encode()).hexdigest(), _expiry())
    return token


def user_for_token(token: str | None) -> dict | None:
    if not token:
        return None
    return db.session_user(hashlib.sha256(token.encode()).hexdigest())


def end_session(token: str | None) -> None:
    if token:
        db.delete_session(hashlib.sha256(token.encode()).hexdigest())
