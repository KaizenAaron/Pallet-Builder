from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..db import aware
from ..models import PalletType, Product, ProductBox, Shipment, ShipmentLine
from ..services import box_import
from ..services import shipments as svc
from ..tenancy import Tenant, get_tenant, scoped

router = APIRouter(prefix="/api/shipments", tags=["shipments"])

MAX_LINES = 500
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


class LineIn(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=1_000_000)


class ShipmentIn(BaseModel):
    customer: str = Field(default="", max_length=200)
    reference: str = Field(default="", max_length=100)
    ship_date: date | None = None
    notes: str = Field(default="", max_length=5000)
    pallet_selection: str = Field(default="auto", pattern="^(auto|fixed)$")
    pallet_type_id: int | None = None  # used when pallet_selection is "fixed"
    packing_mode: str = Field(default="layered", pattern="^(layered|tightest)$")
    lines: list[LineIn] = Field(default_factory=list, max_length=MAX_LINES)


def _iso(dt) -> str | None:
    return aware(dt).isoformat() if dt else None


def summary_payload(s: Shipment, stale: bool) -> dict:
    return {
        "id": s.id,
        "number": s.label,
        "customer": s.customer,
        "reference": s.reference,
        "ship_date": s.ship_date.isoformat() if s.ship_date else None,
        "packing_mode": s.packing_mode,
        "pallet_selection": s.pallet_selection,
        "status": s.status,
        "stale": stale,
        "pallet_count": s.pallet_count,
        "total_gross_weight": s.total_gross_weight,
        "line_count": len(s.lines),
        "updated_at": _iso(s.updated_at),
    }


def detail_payload(tenant: Tenant, s: Shipment) -> dict:
    stale = svc.is_stale(tenant.db, s)
    ids = [ln.product_id for ln in s.lines if ln.product_id]
    box_counts = dict(
        tenant.db.execute(
            select(ProductBox.product_id, func.count())
            .where(ProductBox.product_id.in_(ids), ProductBox.company_id == tenant.company_id)
            .group_by(ProductBox.product_id)
        ).all()
    ) if ids else {}
    return {
        **summary_payload(s, stale),
        "notes": s.notes,
        "pallet_type_id": s.pallet_type_id,
        "calculated_at": _iso(s.calculated_at),
        "calculated_mode": s.calculated_mode,
        "created_by": s.created_by.name if s.created_by else None,
        "lines": [
            {
                "id": ln.id,
                "product_id": ln.product_id,
                "sku": ln.product.sku if ln.product else ln.sku,
                "product_name": ln.product.name if ln.product else ln.product_name,
                "quantity": ln.quantity,
                "product_deleted": ln.product_id is None,
                "box_count": box_counts.get(ln.product_id, 0) if ln.product_id else 0,
            }
            for ln in s.lines
        ],
        "results": None if s.status != "calculated" else {
            "pallet_count": s.pallet_count,
            "total_gross_weight": s.total_gross_weight,
            "total_cubic_feet": s.total_cubic_feet,
            "warnings": s.warnings or [],
            "unplaced": s.unplaced or [],
            "pallet_spec": s.pallet_spec,
            "pallets": [
                {
                    "index": p.index, "length": p.length, "width": p.width, "height": p.height,
                    "net_weight": p.net_weight, "gross_weight": p.gross_weight, "cubic_feet": p.cubic_feet,
                    "density": p.density, "freight_class": p.freight_class, "box_summary": p.box_summary,
                    "layout": p.layout,
                    "pallet_spec": p.pallet_spec or s.pallet_spec,
                }
                for p in s.pallets
            ],
        },
    }


def _load(tenant: Tenant, shipment_id: int) -> Shipment:
    s = tenant.db.scalar(
        scoped(select(Shipment), Shipment, tenant)
        .where(Shipment.id == shipment_id)
        .options(selectinload(Shipment.lines).selectinload(ShipmentLine.product), selectinload(Shipment.pallets))
    )
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shipment not found.")
    return s


def _pallet_type(tenant: Tenant, pallet_type_id: int | None) -> PalletType | None:
    if pallet_type_id is None:
        return tenant.db.scalar(
            scoped(select(PalletType), PalletType, tenant).order_by(PalletType.is_default.desc(), PalletType.id)
        )
    pt = tenant.db.scalar(scoped(select(PalletType), PalletType, tenant).where(PalletType.id == pallet_type_id))
    if pt is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That pallet type doesn't exist.")
    return pt


def _apply(tenant: Tenant, s: Shipment, body: ShipmentIn) -> None:
    ids = {ln.product_id for ln in body.lines}
    products = {
        p.id: p for p in tenant.db.scalars(scoped(select(Product), Product, tenant).where(Product.id.in_(ids))).all()
    } if ids else {}
    missing = ids - set(products)
    if missing:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "One or more products don't exist.")
    s.customer = body.customer.strip()
    s.reference = body.reference.strip()
    s.ship_date = body.ship_date
    s.notes = body.notes.strip()
    s.packing_mode = body.packing_mode
    s.pallet_selection = body.pallet_selection
    if body.pallet_selection == "fixed":
        pt = _pallet_type(tenant, body.pallet_type_id)
    elif body.pallet_type_id is not None:
        pt = _pallet_type(tenant, body.pallet_type_id)  # validated, remembered for switching back
    else:
        pt = None
    s.pallet_type_id = pt.id if pt else None
    s.pallet_type = pt
    s.lines.clear()
    tenant.db.flush()
    for i, ln in enumerate(body.lines):
        p = products[ln.product_id]
        s.lines.append(ShipmentLine(
            company_id=tenant.company_id, position=i, product_id=p.id, product=p, sku=p.sku,
            product_name=p.name, quantity=ln.quantity,
        ))


def _next_number(tenant: Tenant) -> int:
    return (tenant.db.scalar(scoped(select(func.max(Shipment.number)), Shipment, tenant)) or 0) + 1


@router.get("")
def list_shipments(
    tenant: Tenant = Depends(get_tenant),
    q: str = Query(default="", max_length=100),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    stmt = scoped(select(Shipment), Shipment, tenant).options(
        selectinload(Shipment.lines).selectinload(ShipmentLine.product), selectinload(Shipment.pallet_type)
    )
    term = q.strip().lower()
    if term:
        like = f"%{term}%"
        num = term.removeprefix("sh-").lstrip("0")
        conds = func.lower(Shipment.customer).like(like) | func.lower(Shipment.reference).like(like)
        if num.isdigit():
            conds = conds | (Shipment.number == int(num))
        stmt = stmt.where(conds)
    rows = tenant.db.scalars(stmt.order_by(Shipment.updated_at.desc(), Shipment.id.desc()).limit(limit)).all()
    return [summary_payload(s, svc.is_stale(tenant.db, s)) for s in rows]


@router.post("")
def create_shipment(body: ShipmentIn, tenant: Tenant = Depends(get_tenant)) -> dict:
    s = Shipment(company_id=tenant.company_id, number=_next_number(tenant), created_by_id=tenant.user.id)
    tenant.db.add(s)
    _apply(tenant, s, body)
    tenant.db.commit()
    return detail_payload(tenant, _load(tenant, s.id))


@router.post("/parse-lines")
async def parse_lines(file: UploadFile = File(...), tenant: Tenant = Depends(get_tenant)) -> dict:
    """Read SKU + quantity rows from a file and resolve them to products. Writes nothing."""
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File is larger than 5 MB.")
    try:
        table = box_import.read_table(file.filename or "", data)
    except box_import.ImportFileError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    qty_aliases = {"qty", "quantity", "units", "orderqty", "orderedqty", "productuomqty", "count", "qtyordered"}
    header_idx = sku_col = qty_col = None
    for i, row in enumerate(table[:20]):
        norm = [box_import._norm(c) for c in row]
        s_idx = next((j for j, n in enumerate(norm) if box_import.ALIASES.get(n) == "sku"), None)
        q_idx = next((j for j, n in enumerate(norm) if n in qty_aliases), None)
        if s_idx is not None and q_idx is not None:
            header_idx, sku_col, qty_col = i, s_idx, q_idx
            break
    if header_idx is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file needs an SKU column and a Qty column.")
    products = {p.sku.lower(): p for p in tenant.db.scalars(scoped(select(Product), Product, tenant)).all()}
    totals: dict[int, int] = {}
    unknown: list[str] = []
    errors: list[dict] = []
    for off, row in enumerate(table[header_idx + 1:]):
        rownum = header_idx + off + 2
        raw_sku = row[sku_col] if sku_col < len(row) else None
        raw_qty = row[qty_col] if qty_col < len(row) else None
        if raw_sku in (None, "") and raw_qty in (None, ""):
            continue
        sku = str(int(raw_sku)) if isinstance(raw_sku, float) and raw_sku.is_integer() else str(raw_sku or "").strip()
        try:
            qty = float(str(raw_qty).replace(",", "").strip())
            if qty <= 0 or qty != int(qty):
                raise ValueError
        except (TypeError, ValueError):
            errors.append({"row": rownum, "sku": sku, "message": f"Qty must be a whole number above 0 (got {raw_qty!r})"})
            continue
        p = products.get(sku.lower())
        if p is None:
            if sku and sku not in unknown:
                unknown.append(sku)
            continue
        totals[p.id] = totals.get(p.id, 0) + int(qty)
    by_id = {p.id: p for p in products.values()}
    return {
        "lines": [
            {"product_id": pid, "sku": by_id[pid].sku, "product_name": by_id[pid].name, "quantity": q}
            for pid, q in totals.items()
        ],
        "unknown_skus": unknown,
        "errors": errors,
    }


@router.get("/{shipment_id}")
def get_shipment(shipment_id: int, tenant: Tenant = Depends(get_tenant)) -> dict:
    return detail_payload(tenant, _load(tenant, shipment_id))


@router.put("/{shipment_id}")
def update_shipment(shipment_id: int, body: ShipmentIn, tenant: Tenant = Depends(get_tenant)) -> dict:
    s = _load(tenant, shipment_id)
    _apply(tenant, s, body)
    tenant.db.commit()
    return detail_payload(tenant, _load(tenant, s.id))


@router.post("/{shipment_id}/calculate")
def calculate_shipment(shipment_id: int, tenant: Tenant = Depends(get_tenant)) -> dict:
    s = _load(tenant, shipment_id)
    if not s.lines:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Add at least one product before calculating.")
    try:
        svc.calculate(tenant.db, s)
    except svc.TooLarge as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    tenant.db.commit()
    return detail_payload(tenant, _load(tenant, s.id))


@router.post("/{shipment_id}/duplicate")
def duplicate_shipment(shipment_id: int, tenant: Tenant = Depends(get_tenant)) -> dict:
    src = _load(tenant, shipment_id)
    s = Shipment(
        company_id=tenant.company_id, number=_next_number(tenant), created_by_id=tenant.user.id,
        customer=src.customer, reference=src.reference, ship_date=src.ship_date, notes=src.notes,
        pallet_type_id=src.pallet_type_id, packing_mode=src.packing_mode, pallet_selection=src.pallet_selection,
    )
    for ln in src.lines:
        s.lines.append(ShipmentLine(
            company_id=tenant.company_id, position=ln.position, product_id=ln.product_id, sku=ln.sku,
            product_name=ln.product_name, quantity=ln.quantity,
        ))
    tenant.db.add(s)
    tenant.db.commit()
    return detail_payload(tenant, _load(tenant, s.id))


@router.delete("/{shipment_id}")
def delete_shipment(shipment_id: int, tenant: Tenant = Depends(get_tenant)) -> dict:
    s = _load(tenant, shipment_id)
    tenant.db.delete(s)
    tenant.db.commit()
    return {"ok": True}
