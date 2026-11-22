"""The one place a request becomes scoped to a company.

Every endpoint that touches company data depends on `get_tenant` (or `require_role`). The
company comes from the `X-Company-Id` header and is checked against the caller's memberships;
`company_id` is never read from a request body. After this check the session is bound to the
company, which also drives Postgres row-level security (`app/rls.py`).
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import ROLE_RANK, Company, Membership, User
from .rls import bind_company
from .security import current_user


@dataclass
class Tenant:
    user: User
    company: Company
    role: str
    db: Session

    @property
    def company_id(self) -> int:
        return self.company.id

    def at_least(self, role: str) -> bool:
        return ROLE_RANK[self.role] >= ROLE_RANK[role]


def get_tenant(
    x_company_id: str | None = Header(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Tenant:
    if not x_company_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No company selected.")
    try:
        company_id = int(x_company_id)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid company id.")
    membership = db.scalar(
        select(Membership).where(Membership.user_id == user.id, Membership.company_id == company_id)
    )
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not a member of this company.")
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not a member of this company.")
    if company.suspended_at is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This company's account is suspended.")
    bind_company(db, company.id)
    return Tenant(user=user, company=company, role=membership.role, db=db)


def require_role(role: str):
    def dep(tenant: Tenant = Depends(get_tenant)) -> Tenant:
        if not tenant.at_least(role):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires the {role} role.")
        return tenant

    return dep


def scoped(stmt, model, tenant: Tenant):
    """Add the company filter to a select over a tenant model."""
    return stmt.where(model.company_id == tenant.company_id)
