from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select

from ..models import ROLE_RANK, Membership
from ..tenancy import Tenant, get_tenant, require_role

router = APIRouter(prefix="/api/company/members", tags=["members"])


class RoleIn(BaseModel):
    role: Literal["owner", "admin", "member"]


def _get_membership(tenant: Tenant, user_id: int) -> Membership:
    m = tenant.db.scalar(
        select(Membership).where(Membership.company_id == tenant.company_id, Membership.user_id == user_id)
    )
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found.")
    return m


def _owner_count(tenant: Tenant) -> int:
    return tenant.db.scalar(
        select(func.count()).select_from(Membership).where(
            Membership.company_id == tenant.company_id, Membership.role == "owner"
        )
    )


@router.get("")
def list_members(tenant: Tenant = Depends(get_tenant)) -> list[dict]:
    rows = tenant.db.scalars(select(Membership).where(Membership.company_id == tenant.company_id)).all()
    return sorted(
        (
            {
                "user_id": m.user_id,
                "name": m.user.name,
                "email": m.user.email,
                "role": m.role,
                "joined_at": m.created_at.isoformat(),
                "is_you": m.user_id == tenant.user.id,
            }
            for m in rows
        ),
        key=lambda r: (-ROLE_RANK[r["role"]], r["name"].lower(), r["email"]),
    )


@router.put("/{user_id}")
def change_role(user_id: int, body: RoleIn, tenant: Tenant = Depends(require_role("admin"))) -> dict:
    m = _get_membership(tenant, user_id)
    touches_owner = m.role == "owner" or body.role == "owner"
    if touches_owner and tenant.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owners can add or remove owners.")
    if m.role == "owner" and body.role != "owner" and _owner_count(tenant) <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A company needs at least one owner.")
    m.role = body.role
    tenant.db.commit()
    return {"user_id": user_id, "role": m.role}


@router.delete("/{user_id}")
def remove_member(user_id: int, tenant: Tenant = Depends(get_tenant)) -> dict:
    m = _get_membership(tenant, user_id)
    leaving = user_id == tenant.user.id
    if not leaving:
        if not tenant.at_least("admin"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Requires the admin role.")
        if ROLE_RANK[m.role] >= ROLE_RANK["admin"] and tenant.role != "owner":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owners can remove admins or owners.")
    if m.role == "owner" and _owner_count(tenant) <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A company needs at least one owner.")
    tenant.db.delete(m)
    tenant.db.commit()
    return {"ok": True}
