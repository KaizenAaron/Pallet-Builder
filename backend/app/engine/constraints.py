"""Independent validator for a finished pallet.

Recomputes every rule from the final placements alone (no packer state), so a packer bug can
never produce an impossible pallet unnoticed. Every engine test runs every result through this.
"""

from __future__ import annotations

from .model import EPS, PalletSpec, Placement
from .pallet_state import DEFAULT_SUPPORT_RATIO, overlap_1d


def _dims_ok(p: Placement) -> bool:
    s = p.spec
    return sorted((round(p.dx, 6), round(p.dy, 6), round(p.dz, 6))) == sorted(
        (round(s.length, 6), round(s.width, 6), round(s.height, 6))
    )


def validate(
    spec: PalletSpec, placements: list[Placement], support_ratio: float = DEFAULT_SUPPORT_RATIO
) -> list[str]:
    errors: list[str] = []
    o = spec.max_overhang
    n = len(placements)

    for i, p in enumerate(placements):
        tag = f"box {p.box.uid} ({p.spec.sku} #{p.spec.box_no})"
        if not _dims_ok(p):
            errors.append(f"{tag}: placed dims are not the box's dims")
        if p.spec.this_side_up and abs(p.dz - p.spec.height) > EPS:
            errors.append(f"{tag}: this-side-up box is tipped over")
        if p.x < -o - EPS or p.y < -o - EPS or p.x + p.dx > spec.length + o + EPS or p.y + p.dy > spec.width + o + EPS:
            errors.append(f"{tag}: outside the pallet footprint plus overhang")
        if p.z < -EPS or p.top > spec.max_load_height + EPS:
            errors.append(f"{tag}: above the max pallet height")

    # pairwise overlap + support graph
    supporters: list[list[tuple[int, float]]] = [[] for _ in range(n)]
    for i in range(n):
        a = placements[i]
        for j in range(i + 1, n):
            b = placements[j]
            ox = overlap_1d(a.x, a.x + a.dx, b.x, b.x + b.dx)
            oy = overlap_1d(a.y, a.y + a.dy, b.y, b.y + b.dy)
            if ox <= EPS or oy <= EPS:
                continue
            if overlap_1d(a.z, a.top, b.z, b.top) > EPS:
                errors.append(f"boxes {a.box.uid} and {b.box.uid} overlap")
            elif abs(a.top - b.z) <= EPS:
                supporters[j].append((i, ox * oy))
            elif abs(b.top - a.z) <= EPS:
                supporters[i].append((j, ox * oy))

    for i, p in enumerate(placements):
        if p.z <= EPS:
            continue
        area = sum(a for _, a in supporters[i])
        if area + EPS < support_ratio * p.dx * p.dy:
            errors.append(f"box {p.box.uid}: only {area / (p.dx * p.dy):.0%} of its base is supported")
        for j, _ in supporters[i]:
            if not placements[j].spec.stackable:
                errors.append(f"box {p.box.uid} rests on non-stackable box {placements[j].box.uid}")

    # load on top: process from the highest box down; each box passes its weight plus its load
    # to its supporters in proportion to contact area
    loads = [0.0] * n
    for i in sorted(range(n), key=lambda k: -placements[k].z):
        total = sum(a for _, a in supporters[i])
        if total <= 0:
            continue
        carried = placements[i].spec.weight + loads[i]
        for j, a in supporters[i]:
            loads[j] += carried * a / total
    for i, p in enumerate(placements):
        lim = p.spec.max_load_on_top
        if lim > 0 and loads[i] > lim + EPS:
            errors.append(f"box {p.box.uid}: carries {loads[i]:.1f} lb, limit {lim:g} lb")

    net = sum(p.spec.weight for p in placements)
    if net + spec.tare_weight > spec.max_gross_weight + EPS:
        errors.append(f"gross weight {net + spec.tare_weight:.1f} exceeds {spec.max_gross_weight:g}")
    return errors
