"""The bridge between stored shipments and the packing engine.

Every pallet number shown anywhere comes from `engine.pack()` via `calculate()`; nothing here
re-derives metrics. Results are stored as a snapshot together with `input_hash`, a fingerprint of
everything the engine saw (lines, each product's boxes at that moment, the pallet type, the mode).
`is_stale()` compares that fingerprint with the current inputs, so an estimate never changes
silently — it is flagged "out of date" until someone recalculates.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import engine
from ..engine.expand import expand_lines
from ..models import PalletType, Product, Shipment, ShipmentPallet

# Size guards, measured on the engine (see CLAUDE.md): `boxes × distinct box types` tracks how
# long the extreme-point search takes; layered is far cheaper because full layers skip it.
LIMITS = {
    "layered": {"boxes": 5000, "work": 1_000_000},
    "tightest": {"boxes": 1500, "work": 300_000},
}


class TooLarge(ValueError):
    pass


def pallet_spec_for(pt: PalletType | None, snapshot: dict | None = None) -> engine.PalletSpec:
    if pt is None:
        if snapshot:
            return engine.PalletSpec(**{k: snapshot[k] for k in engine.PalletSpec.__dataclass_fields__})
        return engine.PalletSpec()
    return engine.PalletSpec(
        length=pt.length,
        width=pt.width,
        deck_height=pt.deck_height,
        tare_weight=pt.tare_weight,
        max_total_height=pt.max_total_height,
        max_gross_weight=pt.max_gross_weight,
        max_overhang=pt.max_overhang,
    )


def engine_lines(db: Session, shipment: Shipment) -> list[engine.ShipmentLine]:
    ids = [ln.product_id for ln in shipment.lines if ln.product_id is not None]
    products = {
        p.id: p
        for p in db.scalars(
            select(Product)
            .where(Product.id.in_(ids), Product.company_id == shipment.company_id)
            .options(selectinload(Product.boxes))
        ).all()
    } if ids else {}
    out: list[engine.ShipmentLine] = []
    for ln in shipment.lines:
        p = products.get(ln.product_id) if ln.product_id is not None else None
        sku = p.sku if p else ln.sku
        name = p.name if p else ln.product_name
        boxes = [
            engine.BoxSpec(
                product_id=str(p.id), sku=sku, product_name=name, box_no=b.box_no, name=b.name,
                length=b.length, width=b.width, height=b.height, weight=b.weight,
                this_side_up=b.this_side_up, stackable=b.stackable, max_load_on_top=b.max_load_on_top,
                qty_per_unit=b.qty_per_unit, units_per_box=b.units_per_box,
            )
            for b in (p.boxes if p else [])
        ]
        out.append(engine.ShipmentLine(
            product_id=str(p.id) if p else f"deleted:{ln.sku}", sku=sku, product_name=name,
            quantity=ln.quantity, boxes=boxes,
        ))
    return out


def fingerprint(lines: list[engine.ShipmentLine], spec: engine.PalletSpec, mode: str) -> str:
    payload = {
        "mode": mode,
        "pallet": asdict(spec),
        "lines": [
            {"product": ln.product_id, "qty": ln.quantity, "boxes": [asdict(b) for b in ln.boxes]}
            for ln in lines
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def current_inputs(db: Session, shipment: Shipment) -> tuple[list[engine.ShipmentLine], engine.PalletSpec, str]:
    lines = engine_lines(db, shipment)
    spec = pallet_spec_for(shipment.pallet_type, None if shipment.pallet_type else shipment.pallet_spec)
    return lines, spec, fingerprint(lines, spec, shipment.packing_mode)


def is_stale(db: Session, shipment: Shipment) -> bool:
    if shipment.status != "calculated":
        return False
    return current_inputs(db, shipment)[2] != shipment.input_hash


def check_size(lines: list[engine.ShipmentLine], mode: str) -> int:
    boxes, _ = expand_lines(lines)
    kinds = len({b.spec for b in boxes})
    lim = LIMITS[mode]
    if len(boxes) > lim["boxes"] or len(boxes) * kinds > lim["work"]:
        hint = " Try Layered mode, or split the order into several shipments." if mode == "tightest" else (
            " Split the order into several shipments."
        )
        raise TooLarge(
            f"This shipment has {len(boxes):,} boxes of {kinds:,} different sizes — too many to calculate "
            f"in {'Tightest fit' if mode == 'tightest' else 'Layered'} mode.{hint}"
        )
    return len(boxes)


def calculate(db: Session, shipment: Shipment) -> Shipment:
    lines, spec, digest = current_inputs(db, shipment)
    check_size(lines, shipment.packing_mode)
    result = engine.pack(lines, spec, shipment.packing_mode)

    shipment.pallets.clear()
    db.flush()
    for p in result.pallets:
        shipment.pallets.append(ShipmentPallet(
            company_id=shipment.company_id, index=p.index, length=p.length, width=p.width, height=p.height,
            net_weight=p.net_weight, gross_weight=p.gross_weight, cubic_feet=p.cubic_feet, density=p.density,
            freight_class=p.freight_class, box_summary=p.box_summary,
            layout=[pl.to_dict() for pl in p.placements],
        ))
    d = result.to_dict()
    shipment.status = "calculated"
    shipment.calculated_at = datetime.now(timezone.utc)
    shipment.calculated_mode = shipment.packing_mode
    shipment.input_hash = digest
    shipment.pallet_count = result.pallet_count
    shipment.total_gross_weight = result.total_gross_weight
    shipment.total_cubic_feet = round(sum(p.cubic_feet for p in result.pallets), 2)
    shipment.warnings = d["warnings"]
    shipment.unplaced = d["unplaced"]
    shipment.pallet_spec = asdict(spec) | (
        {"name": shipment.pallet_type.name} if shipment.pallet_type else {"name": (shipment.pallet_spec or {}).get("name", "")}
    )
    return shipment
