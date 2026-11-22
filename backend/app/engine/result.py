"""Turn packed pallet states into report-ready results."""

from __future__ import annotations

from .freight import cubic_feet, density, freight_class
from .model import PalletResult, PalletSpec
from .pallet_state import PalletState


def _r(v: float, nd: int = 2) -> float:
    return round(v + 0.0, nd)


def finalize_pallet(index: int, state: PalletState) -> PalletResult:
    spec: PalletSpec = state.spec
    placements = state.centered_placements()
    minx = min([0.0] + [p.x for p in placements])
    maxx = max([spec.length] + [p.x + p.dx for p in placements])
    miny = min([0.0] + [p.y for p in placements])
    maxy = max([spec.width] + [p.y + p.dy for p in placements])
    length = maxx - minx
    width = maxy - miny
    height = spec.deck_height + max((p.top for p in placements), default=0.0)
    net = sum(p.spec.weight for p in placements)
    gross = net + spec.tare_weight
    cf = cubic_feet(length, width, height)
    dens = density(gross, cf)

    summary: dict[tuple, dict] = {}
    for p in placements:
        s = p.spec
        row = summary.setdefault(
            s.key,
            {
                "product_id": s.product_id,
                "sku": s.sku,
                "product_name": s.product_name,
                "box_no": s.box_no,
                "box_name": s.name,
                "dims": [s.length, s.width, s.height],
                "unit_weight": s.weight,
                "count": 0,
                "weight": 0.0,
            },
        )
        row["count"] += 1
        row["weight"] = _r(row["weight"] + s.weight)
    box_summary = sorted(summary.values(), key=lambda r: (r["sku"], r["box_no"]))

    return PalletResult(
        index=index,
        placements=sorted(placements, key=lambda p: (p.z, p.y, p.x)),
        length=_r(length),
        width=_r(width),
        height=_r(height),
        net_weight=_r(net),
        gross_weight=_r(gross),
        cubic_feet=_r(cf),
        density=_r(dens),
        freight_class=freight_class(dens),
        box_summary=box_summary,
    )
