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
# Re-timed for engine v4 (every group order × placement rule is tried): worst allowed ≈ 11–12 s.
LIMITS = {
    "layered": {"boxes": 5000, "work": 200_000},
    "tightest": {"boxes": 1500, "work": 50_000},
}


class TooLarge(ValueError):
    pass


def pallet_spec_for(pt: PalletType | None, snapshot: dict | None = None) -> engine.PalletSpec:
    if pt is None:
        if snapshot and "length" in snapshot:
            return engine.PalletSpec(
                **{k: snapshot[k] for k in engine.PalletSpec.__dataclass_fields__ if k in snapshot}
            )
        return engine.PalletSpec()
    return engine.PalletSpec(
        length=pt.length,
        width=pt.width,
        deck_height=pt.deck_height,
        tare_weight=pt.tare_weight,
        max_total_height=pt.max_total_height,
        max_gross_weight=pt.max_gross_weight,
        max_overhang=pt.max_overhang,
        name=pt.name,
    )


def candidate_specs(db: Session, shipment: Shipment) -> list[engine.PalletSpec]:
    """The pallet types the engine may use. Fixed: the shipment's type (or its snapshot if the type
    was deleted). Automatic: every type ticked "Use in automatic selection", falling back to the
    company default, then to any type."""
    if shipment.pallet_selection != "auto":
        return [pallet_spec_for(shipment.pallet_type, None if shipment.pallet_type else shipment.pallet_spec)]
    types = db.scalars(
        select(PalletType).where(PalletType.company_id == shipment.company_id).order_by(PalletType.id)
    ).all()
    chosen = [t for t in types if t.auto_select] or [t for t in types if t.is_default] or list(types[:1])
    return [pallet_spec_for(t) for t in chosen] or [engine.PalletSpec()]


def summary_label(pallets: list) -> str:
    """'2 × 48 × 40 GMA, 1 × 48 × 48' — pallet type counts in the order they first appear."""
    counts: dict[str, int] = {}
    for p in pallets:
        name = (p.pallet.name if p.pallet else "") or "Pallet"
        counts[name] = counts.get(name, 0) + 1
    return ", ".join(f"{n} × {name}" for name, n in counts.items())


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


def fingerprint(lines: list[engine.ShipmentLine], specs: list[engine.PalletSpec], mode: str) -> str:
    payload = {
        "engine": engine.ENGINE_VERSION,  # rule changes make old estimates "out of date"
        "mode": mode,
        "pallets": [asdict(s) for s in specs],  # every candidate type (automatic) or the fixed one
        "lines": [
            {"product": ln.product_id, "qty": ln.quantity, "boxes": [asdict(b) for b in ln.boxes]}
            for ln in lines
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def current_inputs(
    db: Session, shipment: Shipment
) -> tuple[list[engine.ShipmentLine], list[engine.PalletSpec], str]:
    lines = engine_lines(db, shipment)
    specs = candidate_specs(db, shipment)
    return lines, specs, fingerprint(lines, specs, shipment.packing_mode)


def is_stale(db: Session, shipment: Shipment) -> bool:
    if shipment.status != "calculated":
        return False
    return current_inputs(db, shipment)[2] != shipment.input_hash


def check_size(lines: list[engine.ShipmentLine], mode: str, n_types: int = 1) -> int:
    """Each candidate pallet type is one full search, so the budget is shared between them."""
    boxes, _ = expand_lines(lines)
    kinds = len({b.spec for b in boxes})
    lim = LIMITS[mode]
    n = max(1, n_types)
    if len(boxes) > lim["boxes"] / n or len(boxes) * kinds > lim["work"] / n:
        hint = " Try Layered mode, or split the order into several shipments." if mode == "tightest" else (
            " Split the order into several shipments."
        )
        raise TooLarge(
            f"This shipment has {len(boxes):,} boxes of {kinds:,} different sizes — too many to calculate "
            f"in {'Tightest fit' if mode == 'tightest' else 'Layered'} mode"
            f"{f' with {n} pallet types to choose from' if n > 1 else ''}.{hint}"
        )
    return len(boxes)


def calculate(db: Session, shipment: Shipment) -> Shipment:
    lines, specs, digest = current_inputs(db, shipment)
    check_size(lines, shipment.packing_mode, len(specs))
    result = engine.pack_auto(lines, specs, shipment.packing_mode)  # one type = plain pack()

    shipment.pallets.clear()
    db.flush()
    for p in result.pallets:
        shipment.pallets.append(ShipmentPallet(
            company_id=shipment.company_id, index=p.index, length=p.length, width=p.width, height=p.height,
            net_weight=p.net_weight, gross_weight=p.gross_weight, cubic_feet=p.cubic_feet, density=p.density,
            freight_class=p.freight_class, box_summary=p.box_summary,
            layout=[pl.to_dict() for pl in p.placements],
            pallet_spec=asdict(p.pallet) if p.pallet else None,
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
    if shipment.pallet_selection == "auto":
        # a summary; each pallet carries its own spec
        shipment.pallet_spec = {"selection": "auto", "name": summary_label(result.pallets)}
    else:
        spec = specs[0]
        shipment.pallet_spec = asdict(spec) | {"name": spec.name or (shipment.pallet_spec or {}).get("name", "")}
    return shipment
