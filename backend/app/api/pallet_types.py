from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from ..models import PalletType
from ..tenancy import Tenant, get_tenant, require_role, scoped

router = APIRouter(prefix="/api/pallet-types", tags=["pallet types"])

FIELDS = ("name", "length", "width", "deck_height", "tare_weight", "max_total_height", "max_gross_weight", "max_overhang")


class PalletTypeIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    length: float = Field(gt=0, le=200)
    width: float = Field(gt=0, le=200)
    deck_height: float = Field(ge=0, le=24)
    tare_weight: float = Field(ge=0, le=1000)
    max_total_height: float = Field(gt=0, le=200)
    max_gross_weight: float = Field(gt=0, le=20000)
    max_overhang: float = Field(default=0, ge=0, le=12)

    @model_validator(mode="after")
    def _limits(self):
        if self.max_total_height <= self.deck_height:
            raise ValueError("Max height must be taller than the deck")
        if self.max_gross_weight <= self.tare_weight:
            raise ValueError("Max gross weight must be more than the pallet's own (tare) weight")
        return self


def payload(p: PalletType) -> dict:
    return {"id": p.id, "is_default": p.is_default, **{f: getattr(p, f) for f in FIELDS}}


def _all(tenant: Tenant) -> list[PalletType]:
    return list(tenant.db.scalars(scoped(select(PalletType), PalletType, tenant).order_by(PalletType.name)).all())


def _get(tenant: Tenant, pallet_id: int) -> PalletType:
    p = tenant.db.scalar(scoped(select(PalletType), PalletType, tenant).where(PalletType.id == pallet_id))
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pallet type not found.")
    return p


@router.get("")
def list_pallet_types(tenant: Tenant = Depends(get_tenant)) -> list[dict]:
    return [payload(p) for p in _all(tenant)]


@router.post("")
def create_pallet_type(body: PalletTypeIn, tenant: Tenant = Depends(require_role("admin"))) -> dict:
    first = not _all(tenant)
    p = PalletType(company_id=tenant.company_id, is_default=first, **body.model_dump())
    p.name = p.name.strip()
    tenant.db.add(p)
    tenant.db.commit()
    return payload(p)


@router.put("/{pallet_id}")
def update_pallet_type(pallet_id: int, body: PalletTypeIn, tenant: Tenant = Depends(require_role("admin"))) -> dict:
    p = _get(tenant, pallet_id)
    for k, v in body.model_dump().items():
        setattr(p, k, v.strip() if isinstance(v, str) else v)
    tenant.db.commit()
    return payload(p)


@router.post("/{pallet_id}/default")
def make_default(pallet_id: int, tenant: Tenant = Depends(require_role("admin"))) -> list[dict]:
    target = _get(tenant, pallet_id)
    for p in _all(tenant):
        p.is_default = p.id == target.id
    tenant.db.commit()
    return [payload(p) for p in _all(tenant)]


@router.delete("/{pallet_id}")
def delete_pallet_type(pallet_id: int, tenant: Tenant = Depends(require_role("admin"))) -> list[dict]:
    p = _get(tenant, pallet_id)
    rest = [x for x in _all(tenant) if x.id != p.id]
    if not rest:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You need at least one pallet type.")
    if p.is_default:
        rest[0].is_default = True
    tenant.db.delete(p)
    tenant.db.commit()
    return [payload(x) for x in _all(tenant)]
