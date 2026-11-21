"""Password hashing and opaque token helpers.

* Passwords: Argon2id (argon2-cffi defaults: m=64 MiB, t=3, p=4), rehashed on
  login when parameters change. Plaintext passwords are never stored or logged.
* Session and reset tokens: 256-bit random, URL-safe. Only their SHA-256 hash
  is stored, so a database leak does not yield usable tokens.
"""

from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_PASSWORD_LENGTH = 10
#: Upper bound protects the hasher from very large inputs (DoS).
MAX_PASSWORD_LENGTH = 128

_hasher = PasswordHasher()
# Used to spend the same time on unknown emails as on wrong passwords.
_DUMMY_HASH = _hasher.hash("via-timing-equalizer-not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Constant-effort verification; ``None`` hash still runs a verification."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def password_problems(password: str, email: str | None = None) -> list[str]:
    """Human-readable reasons a password is rejected (empty list = acceptable)."""
    problems = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"Use at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        problems.append(f"Use at most {MAX_PASSWORD_LENGTH} characters.")
    if password and not password.strip():
        problems.append("Password cannot be only whitespace.")
    if email and password.lower() == email.lower():
        problems.append("Password must not be your email address.")
    return problems


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
