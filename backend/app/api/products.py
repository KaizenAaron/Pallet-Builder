from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..db import aware
from ..models import Product, ProductBox
from ..services import box_import
from ..tenancy import Tenant, get_tenant, require_role, scoped

router = APIRouter(prefix="/api/products", tags=["products"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class BoxIn(BaseModel):
    box_no: int = Field(ge=1, le=99)
    name: str = Field(default="", max_length=200)
    qty_per_unit: int = Field(default=1, ge=1, le=1000)
    units_per_box: int = Field(default=1, ge=1, le=100000)
    length: float = Field(gt=0, le=1000)
    width: float = Field(gt=0, le=1000)
    height: float = Field(gt=0, le=1000)
    weight: float = Field(ge=0, le=100000)
    this_side_up: bool = False
    stackable: bool = True
    max_load_on_top: float = Field(default=0, ge=0, le=1000000)


class ProductIn(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    name: str = Field(default="", max_length=300)
    boxes: list[BoxIn] | None = None

    @field_validator("sku")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("SKU can't be blank")
        return v

    @model_validator(mode="after")
    def _unique_box_numbers(self):
        if self.boxes is not None:
            nos = [b.box_no for b in self.boxes]
            if len(nos) != len(set(nos)):
                raise ValueError("Each box needs a different Box #")
        return self


def box_payload(b: ProductBox) -> dict:
    return {
        "id": b.id, "box_no": b.box_no, "name": b.name, "qty_per_unit": b.qty_per_unit,
        "units_per_box": b.units_per_box, "length": b.length, "width": b.width, "height": b.height,
        "weight": b.weight, "this_side_up": b.this_side_up, "stackable": b.stackable,
        "max_load_on_top": b.max_load_on_top,
    }


def product_payload(p: Product, with_boxes: bool = True) -> dict:
    d = {
        "id": p.id, "sku": p.sku, "name": p.name, "source": p.source,
        "box_count": len(p.boxes),
        # boxes one unit ships in (ignores units_per_box sharing); display only
        "unit_weight": round(sum(b.weight * b.qty_per_unit / b.units_per_box for b in p.boxes), 3),
        "updated_at": aware(p.updated_at).isoformat() if p.updated_at else None,
    }
    if with_boxes:
        d["boxes"] = [box_payload(b) for b in p.boxes]
    return d


def _get(tenant: Tenant, product_id: int) -> Product:
    p = tenant.db.scalar(
        scoped(select(Product), Product, tenant).where(Product.id == product_id).options(selectinload(Product.boxes))
    )
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found.")
    return p


def _sku_taken(tenant: Tenant, sku: str, exclude_id: int | None = None) -> bool:
    stmt = scoped(select(Product.id), Product, tenant).where(func.lower(Product.sku) == sku.lower())
    if exclude_id is not None:
        stmt = stmt.where(Product.id != exclude_id)
    return tenant.db.scalar(stmt) is not None


def _set_boxes(tenant: Tenant, p: Product, boxes: list[BoxIn]) -> None:
    by_no = {b.box_no: b for b in p.boxes}
    wanted = {b.box_no for b in boxes}
    for no, b in list(by_no.items()):
        if no not in wanted:
            p.boxes.remove(b)
    tenant.db.flush()
    for b in boxes:
        data = b.model_dump()
        data["name"] = data["name"].strip() or f"Box {b.box_no}"
        if b.box_no in by_no:
            for k, v in data.items():
                setattr(by_no[b.box_no], k, v)
        else:
            p.boxes.append(ProductBox(company_id=tenant.company_id, **data))


@router.get("")
def list_products(
    tenant: Tenant = Depends(get_tenant),
    q: str = Query(default="", max_length=100),
    missing_boxes: bool = False,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict:
    stmt = scoped(select(Product), Product, tenant)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(func.lower(Product.sku).like(like) | func.lower(Product.name).like(like))
    if missing_boxes:
        stmt = stmt.where(~Product.boxes.any())
    total = tenant.db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = tenant.db.scalars(
        stmt.options(selectinload(Product.boxes)).order_by(func.lower(Product.sku)).limit(limit).offset(offset)
    ).all()
    missing = tenant.db.scalar(
        select(func.count()).select_from(scoped(select(Product.id), Product, tenant).where(~Product.boxes.any()).subquery())
    )
    return {"total": total, "missing_boxes": missing, "items": [product_payload(p, with_boxes=False) for p in rows]}


@router.post("")
def create_product(body: ProductIn, tenant: Tenant = Depends(get_tenant)) -> dict:
    if _sku_taken(tenant, body.sku):
        raise HTTPException(status.HTTP_409_CONFLICT, f"A product with SKU {body.sku} already exists.")
    p = Product(company_id=tenant.company_id, sku=body.sku, name=body.name.strip() or body.sku, source="manual")
    tenant.db.add(p)
    tenant.db.flush()
    _set_boxes(tenant, p, body.boxes or [])
    tenant.db.commit()
    return product_payload(_get(tenant, p.id))


# Static paths must be declared before /{product_id}.
@router.get("/import-template.xlsx")
def import_template_xlsx(tenant: Tenant = Depends(get_tenant)) -> Response:
    return Response(
        box_import.template_xlsx(), media_type=XLSX,
        headers={"Content-Disposition": 'attachment; filename="pallet-builder-box-template.xlsx"'},
    )


@router.get("/import-template.csv")
def import_template_csv(tenant: Tenant = Depends(get_tenant)) -> Response:
    return Response(
        box_import.template_csv(), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="pallet-builder-box-template.csv"'},
    )


@router.get("/export.xlsx")
def export_products(tenant: Tenant = Depends(get_tenant)) -> Response:
    rows = tenant.db.scalars(scoped(select(Product), Product, tenant).options(selectinload(Product.boxes))).all()
    safe = "".join(ch for ch in tenant.company.name if ch.isalnum() or ch in " -_").strip().replace(" ", "-") or "company"
    return Response(
        box_import.export_xlsx(list(rows)), media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{safe}-box-index.xlsx"'},
    )


@router.post("/import")
async def import_products(
    file: UploadFile = File(...),
    dry_run: bool = Query(default=True),
    tenant: Tenant = Depends(require_role("admin")),
) -> dict:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File is larger than 10 MB.")
    try:
        parsed = box_import.parse_rows(box_import.read_table(file.filename or "", data))
    except box_import.ImportFileError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return box_import.apply_import(tenant.db, tenant.company_id, parsed, dry_run=dry_run)


@router.get("/{product_id}")
def get_product(product_id: int, tenant: Tenant = Depends(get_tenant)) -> dict:
    return product_payload(_get(tenant, product_id))


@router.put("/{product_id}")
def update_product(product_id: int, body: ProductIn, tenant: Tenant = Depends(get_tenant)) -> dict:
    p = _get(tenant, product_id)
    if _sku_taken(tenant, body.sku, exclude_id=p.id):
        raise HTTPException(status.HTTP_409_CONFLICT, f"A product with SKU {body.sku} already exists.")
    p.sku = body.sku
    p.name = body.name.strip() or body.sku
    if body.boxes is not None:
        _set_boxes(tenant, p, body.boxes)
    tenant.db.commit()
    return product_payload(_get(tenant, p.id))


@router.delete("/{product_id}")
def delete_product(product_id: int, tenant: Tenant = Depends(get_tenant)) -> dict:
    p = _get(tenant, product_id)
    tenant.db.delete(p)
    tenant.db.commit()
    return {"ok": True}
