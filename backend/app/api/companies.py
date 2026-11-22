from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Company, PalletType, User
from ..security import current_user
from ..services.accounts import create_company
from ..tenancy import Tenant, get_tenant, require_role, scoped

router = APIRouter(prefix="/api", tags=["companies"])

PROFILE_FIELDS = (
    "name", "address_line1", "address_line2", "city", "state", "postal_code", "country", "phone", "units",
)


class CompanyIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class CompanyUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    address_line1: str = Field(default="", max_length=200)
    address_line2: str = Field(default="", max_length=200)
    city: str = Field(default="", max_length=100)
    state: str = Field(default="", max_length=100)
    postal_code: str = Field(default="", max_length=20)
    country: str = Field(default="", max_length=100)
    phone: str = Field(default="", max_length=50)
    units: Literal["imperial", "metric"] = "imperial"


def company_payload(c: Company, role: str | None = None) -> dict:
    d = {f: getattr(c, f) for f in PROFILE_FIELDS}
    d.update({"id": c.id, "plan": c.plan})
    if role is not None:
        d["role"] = role
    return d


@router.post("/companies")
def new_company(body: CompanyIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    company = create_company(db, user, body.name)
    db.commit()
    return company_payload(company, "owner")


@router.get("/company")
def get_company(tenant: Tenant = Depends(get_tenant)) -> dict:
    return company_payload(tenant.company, tenant.role)


@router.put("/company")
def update_company(body: CompanyUpdate, tenant: Tenant = Depends(require_role("admin"))) -> dict:
    for f in PROFILE_FIELDS:
        setattr(tenant.company, f, getattr(body, f).strip() if isinstance(getattr(body, f), str) else getattr(body, f))
    tenant.db.commit()
    return company_payload(tenant.company, tenant.role)


@router.get("/pallet-types")
def list_pallet_types(tenant: Tenant = Depends(get_tenant)) -> list[dict]:
    rows = tenant.db.scalars(scoped(select(PalletType), PalletType, tenant).order_by(PalletType.name)).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "length": p.length,
            "width": p.width,
            "deck_height": p.deck_height,
            "tare_weight": p.tare_weight,
            "max_total_height": p.max_total_height,
            "max_gross_weight": p.max_gross_weight,
            "max_overhang": p.max_overhang,
            "is_default": p.is_default,
        }
        for p in rows
    ]
