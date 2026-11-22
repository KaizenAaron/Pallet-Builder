from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Company, Membership, User
from ..security import platform_admin

router = APIRouter(prefix="/api/admin", tags=["platform admin"])


@router.get("/companies")
def list_companies(_: User = Depends(platform_admin), db: Session = Depends(get_db)) -> list[dict]:
    counts = dict(
        db.execute(select(Membership.company_id, func.count()).group_by(Membership.company_id)).all()
    )
    rows = db.scalars(select(Company).order_by(Company.created_at.desc())).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "plan": c.plan,
            "members": counts.get(c.id, 0),
            "created_at": c.created_at.isoformat(),
            "suspended": c.suspended_at is not None,
        }
        for c in rows
    ]


def _company(db: Session, company_id: int) -> Company:
    c = db.get(Company, company_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found.")
    return c


@router.post("/companies/{company_id}/suspend")
def suspend(company_id: int, _: User = Depends(platform_admin), db: Session = Depends(get_db)) -> dict:
    c = _company(db, company_id)
    c.suspended_at = c.suspended_at or datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@router.post("/companies/{company_id}/unsuspend")
def unsuspend(company_id: int, _: User = Depends(platform_admin), db: Session = Depends(get_db)) -> dict:
    c = _company(db, company_id)
    c.suspended_at = None
    db.commit()
    return {"ok": True}
