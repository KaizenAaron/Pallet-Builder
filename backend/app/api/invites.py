from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import aware, get_db
from ..models import ROLE_RANK, Invite, Membership, User
from ..ratelimit import limit
from ..security import (
    check_password_strength,
    hash_link_token,
    hash_password,
    new_link_token,
    optional_user,
    set_session_cookie,
)
from ..services import mailer
from ..services.accounts import find_user, frontend_link, normalize_email
from ..tenancy import Tenant, require_role
from .auth import me_payload

router = APIRouter(prefix="/api", tags=["invites"])


class InviteIn(BaseModel):
    email: EmailStr
    role: Literal["owner", "admin", "member"] = "member"


class AcceptIn(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    password: str | None = None


def _status(inv: Invite) -> str:
    if inv.accepted_at:
        return "accepted"
    if inv.revoked_at:
        return "revoked"
    if aware(inv.expires_at) < datetime.now(timezone.utc):
        return "expired"
    return "pending"


def _payload(inv: Invite, link: str | None = None) -> dict:
    return {
        "id": inv.id,
        "email": inv.email,
        "role": inv.role,
        "status": _status(inv),
        "expires_at": aware(inv.expires_at).isoformat(),
        "invited_by": inv.invited_by.name if inv.invited_by else None,
        "link": link,
    }


def _issue(tenant: Tenant, inv: Invite) -> dict:
    raw, digest = new_link_token()
    inv.token_hash = digest
    inv.expires_at = datetime.now(timezone.utc) + timedelta(days=get_settings().invite_ttl_days)
    inv.revoked_at = None
    tenant.db.flush()
    link = frontend_link(f"/invite/{raw}")
    mailer.send(
        inv.email,
        f"You're invited to {tenant.company.name} on Pallet Builder",
        f"{tenant.user.name or tenant.user.email} invited you to join {tenant.company.name} on Pallet Builder.\n\n"
        f"Accept the invitation here:\n\n{link}\n",
    )
    tenant.db.commit()
    # The link is always returned to the inviter so they can copy it and send it themselves.
    return _payload(inv, link)


def _get_invite(tenant: Tenant, invite_id: int) -> Invite:
    inv = tenant.db.scalar(select(Invite).where(Invite.id == invite_id, Invite.company_id == tenant.company_id))
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite not found.")
    return inv


@router.get("/company/invites")
def list_invites(tenant: Tenant = Depends(require_role("admin"))) -> list[dict]:
    rows = tenant.db.scalars(
        select(Invite).where(Invite.company_id == tenant.company_id).order_by(Invite.created_at.desc())
    ).all()
    return [_payload(i) for i in rows if _status(i) in ("pending", "expired")]


@router.post("/company/invites")
def create_invite(body: InviteIn, tenant: Tenant = Depends(require_role("admin"))) -> dict:
    if ROLE_RANK[body.role] > ROLE_RANK[tenant.role]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't invite someone with a higher role than yours.")
    email = normalize_email(body.email)
    existing_user = find_user(tenant.db, email)
    if existing_user is not None and tenant.db.scalar(
        select(Membership).where(Membership.company_id == tenant.company_id, Membership.user_id == existing_user.id)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "That person is already a member.")
    inv = Invite(
        company_id=tenant.company_id,
        email=email,
        role=body.role,
        invited_by_id=tenant.user.id,
        token_hash="",
        expires_at=datetime.now(timezone.utc),
    )
    tenant.db.add(inv)
    return _issue(tenant, inv)


@router.post("/company/invites/{invite_id}/renew")
def renew_invite(invite_id: int, tenant: Tenant = Depends(require_role("admin"))) -> dict:
    inv = _get_invite(tenant, invite_id)
    if inv.accepted_at:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This invite was already accepted.")
    if ROLE_RANK[inv.role] > ROLE_RANK[tenant.role]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't renew an invite for a higher role than yours.")
    return _issue(tenant, inv)


@router.delete("/company/invites/{invite_id}")
def revoke_invite(invite_id: int, tenant: Tenant = Depends(require_role("admin"))) -> dict:
    inv = _get_invite(tenant, invite_id)
    if not inv.accepted_at:
        inv.revoked_at = datetime.now(timezone.utc)
        tenant.db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- public (by token)
def _invite_by_token(db: Session, token: str) -> Invite:
    inv = db.scalar(select(Invite).where(Invite.token_hash == hash_link_token(token)))
    if inv is None or _status(inv) != "pending" or inv.company.suspended_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This invitation is invalid, expired or was already used.")
    return inv


@router.get("/invites/{token}", dependencies=[Depends(limit("invite_view", 30, 900))])
def view_invite(token: str, db: Session = Depends(get_db), user: User | None = Depends(optional_user)) -> dict:
    inv = _invite_by_token(db, token)
    account_exists = find_user(db, inv.email) is not None
    return {
        "company_name": inv.company.name,
        "email": inv.email,
        "role": inv.role,
        "account_exists": account_exists,
        "signed_in_as": user.email if user else None,
    }


@router.post("/invites/{token}/accept", dependencies=[Depends(limit("invite_accept", 10, 900))])
def accept_invite(
    token: str,
    body: AcceptIn,
    response: Response,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict:
    inv = _invite_by_token(db, token)
    existing = find_user(db, inv.email)
    if user is not None:
        if user.email != inv.email:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"This invitation is for {inv.email}. Sign out and sign in with that email to accept it.",
            )
        target = user
    elif existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"code": "sign_in_required", "message": f"Sign in as {inv.email} to accept this invitation."},
        )
    else:
        if not body.name or not body.password:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Name and password are required.")
        check_password_strength(body.password)
        target = User(
            email=inv.email,
            name=body.name.strip(),
            password_hash=hash_password(body.password),
            email_verified_at=datetime.now(timezone.utc),  # the invite link proves the inbox
        )
        db.add(target)
        db.flush()
    already = db.scalar(
        select(Membership).where(Membership.company_id == inv.company_id, Membership.user_id == target.id)
    )
    if already is None:
        db.add(Membership(user_id=target.id, company_id=inv.company_id, role=inv.role))
    inv.accepted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(target)
    set_session_cookie(response, target)
    return {"company_id": inv.company_id, "me": me_payload(target)}
