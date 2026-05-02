from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
import uuid
from typing import Any

import bcrypt
from fastapi import HTTPException, status

from app.core.config import settings


def hash_password(password: str) -> str:
    validate_password_strength(password)
    # bcrypt cost 12 is a production baseline that remains practical for SaaS login latency.
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def validate_password_strength(password: str) -> None:
    if (
        len(password) < 10
        or not re.search(r"[A-Z]", password)
        or not re.search(r"[a-z]", password)
        or not re.search(r"\d", password)
        or not re.search(r"[^A-Za-z0-9]", password)
    ):
        raise ValueError(
            "Password must be at least 10 characters and include uppercase, "
            "lowercase, number, and special character."
        )


def _legacy_hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 390_000)
    salt_b64 = base64.urlsafe_b64encode(salt).decode()
    digest_b64 = base64.urlsafe_b64encode(digest).decode()
    return f"pbkdf2_sha256${salt_b64}${digest_b64}"


def verify_password(password: str, password_hash: str) -> bool:
    if password_hash.startswith("$2"):
        return bcrypt.checkpw(password.encode(), password_hash.encode())

    # Legacy PBKDF2 hashes are accepted so existing users are not locked out.
    try:
        algorithm, salt_b64, digest_b64 = password_hash.split("$", 2)
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    salt = base64.urlsafe_b64decode(salt_b64.encode())
    expected_digest = base64.urlsafe_b64decode(digest_b64.encode())
    actual_digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 390_000)
    return secrets.compare_digest(actual_digest, expected_digest)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode())


def create_access_token(subject: str, expires_in_minutes: int | None = None) -> str:
    now = int(time.time())
    expires_at = now + 60 * (expires_in_minutes or settings.access_token_expire_minutes)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": subject,
        "iat": now,
        "exp": expires_at,
        "jti": uuid.uuid4().hex,
        "typ": "access",
    }
    return _encode_jwt(header, payload)


def create_refresh_token(subject: str, expires_in_days: int | None = None) -> str:
    now = int(time.time())
    expires_at = now + 24 * 60 * 60 * (expires_in_days or settings.refresh_token_expire_days)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": subject,
        "iat": now,
        "exp": expires_at,
        "jti": uuid.uuid4().hex,
        "typ": "refresh",
    }
    return _encode_jwt(header, payload)


def _encode_jwt(header: dict[str, Any], payload: dict[str, Any]) -> str:
    signing_input = ".".join(
        [
            _b64url_encode(json.dumps(header, separators=(",", ":")).encode()),
            _b64url_encode(json.dumps(payload, separators=(",", ":")).encode()),
        ]
    )
    signature = hmac.new(settings.secret_key.encode(), signing_input.encode(), hashlib.sha256)
    return f"{signing_input}.{_b64url_encode(signature.digest())}"


def decode_access_token(token: str) -> dict[str, Any]:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        header_b64, payload_b64, signature_b64 = token.split(".", 2)
    except ValueError as exc:
        raise credentials_error from exc

    signing_input = f"{header_b64}.{payload_b64}"
    expected_signature = hmac.new(
        settings.secret_key.encode(),
        signing_input.encode(),
        hashlib.sha256,
    ).digest()

    if not hmac.compare_digest(_b64url_encode(expected_signature), signature_b64):
        raise credentials_error

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except json.JSONDecodeError as exc:
        raise credentials_error from exc

    if int(payload.get("exp", 0)) <= int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")

    return payload
