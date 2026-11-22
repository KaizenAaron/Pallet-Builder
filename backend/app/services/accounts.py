"""Account helpers shared by signup, invites, the company endpoints and the CLI."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import aware
from ..models import AuthToken, Company, Membership, PalletType, User
from ..rls import bind_company
from ..security import hash_link_token, new_link_token


def normalize_email(email: str) -> str:
    return email.strip().lower()


def find_user(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def create_company(db: Session, owner: User, name: str) -> Company:
    """New company with the owner's membership and a default 48×40 pallet type."""
    company = Company(name=name.strip())
    db.add(company)
    db.flush()
    db.add(Membership(user_id=owner.id, company_id=company.id, role="owner"))
    bind_company(db, company.id)  # pallet_types is RLS-protected
    db.add(PalletType(company_id=company.id, name="48 × 40 GMA", is_default=True))
    db.flush()
    return company


def issue_token(db: Session, user: User, purpose: str) -> str:
    s = get_settings()
    ttl = (
        timedelta(hours=s.verify_email_ttl_hours)
        if purpose == "verify_email"
        else timedelta(minutes=s.password_reset_ttl_minutes)
    )
    raw, digest = new_link_token()
    db.add(
        AuthToken(
            user_id=user.id, purpose=purpose, token_hash=digest, expires_at=datetime.now(timezone.utc) + ttl
        )
    )
    db.flush()
    return raw


def consume_token(db: Session, raw: str, purpose: str) -> User | None:
    tok = db.scalar(
        select(AuthToken).where(AuthToken.token_hash == hash_link_token(raw), AuthToken.purpose == purpose)
    )
    now = datetime.now(timezone.utc)
    if tok is None or tok.used_at is not None or aware(tok.expires_at) < now:
        return None
    tok.used_at = now
    return tok.user


def frontend_link(path: str) -> str:
    return get_settings().frontend_base_url.rstrip("/") + path
