"""Passwords, session tokens, single-use link tokens and the current-user dependency."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User

COOKIE_NAME = "pb_session"
MIN_PASSWORD_LENGTH = 10
_hasher = PasswordHasher()


# ---------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return _hasher.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False


# A fixed hash used to spend the same time on unknown emails as on wrong passwords.
_DUMMY_HASH = _hasher.hash("not-a-real-password-0000")


def burn_password_check(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def check_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
        )


# ---------------------------------------------------------------- link tokens
def new_link_token() -> tuple[str, str]:
    """Returns (raw token for the link, sha256 to store)."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_link_token(raw)


def hash_link_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------- sessions
def create_session_token(user: User) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "tv": user.token_version,
        "iat": now,
        "exp": now + timedelta(minutes=s.access_token_ttl_minutes),
    }
    return jwt.encode(payload, s.secret_key, algorithm="HS256")


def set_session_cookie(response: Response, user: User) -> str:
    s = get_settings()
    token = create_session_token(user)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=s.access_token_ttl_minutes * 60,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )
    return token


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def _token_from_request(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(COOKIE_NAME)


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = _token_from_request(request)
    if not token:
        return None
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
        user_id = int(payload["sub"])
        tv = int(payload.get("tv", -1))
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
    user = db.get(User, user_id)
    if user is None or user.token_version != tv or user.email_verified_at is None:
        return None
    now = datetime.now(timezone.utc)
    last = user.last_seen_at
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if last is None or now - last > timedelta(hours=1):
        user.last_seen_at = now
        db.commit()
    return user


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in.")
    return user


def platform_admin(user: User = Depends(current_user)) -> User:
    if not user.is_platform_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform admins only.")
    return user
