"""Pallet packing engine — the single source of truth for every pallet number.

Pure Python (stdlib only) so it can be copied verbatim into the Odoo addon in stage 2.

    result = pack(lines, PalletSpec(...), mode="layered")   # or "tightest"
"""

from __future__ import annotations

from .constraints import validate
from .expand import ShipmentLine, expand_lines
from .layered import pack_layered
from .model import ENGINE_VERSION, MAX_STANDING_RATIO, BoxInstance, BoxSpec, PalletResult, PalletSpec, Placement, ShipmentResult
from .result import finalize_pallet
from .tightest import pack_tightest, score

MODES = ("layered", "tightest")

__all__ = [
    "ENGINE_VERSION",
    "MAX_STANDING_RATIO",
    "BoxInstance",
    "BoxSpec",
    "MODES",
    "PalletResult",
    "PalletSpec",
    "Placement",
    "ShipmentLine",
    "ShipmentResult",
    "pack",
    "validate",
]


def pack(lines: list[ShipmentLine], pallet: PalletSpec, mode: str = "layered") -> ShipmentResult:
    if mode not in MODES:
        raise ValueError(f"unknown packing mode {mode!r}")
    boxes, warnings = expand_lines(lines)
    if not boxes:
        states, unplaced = [], []
    elif mode == "layered":
        states, unplaced = pack_layered(boxes, pallet)
    else:
        # Tightest fit = best of the free-mixing extreme-point runs *and* the layer-first result,
        # so it never needs more pallets than Layered.
        candidates = [pack_tightest(boxes, pallet), pack_layered(boxes, pallet)]
        states, unplaced = min(candidates, key=lambda c: score(*c))

    seen: set[tuple] = set()
    for b in unplaced:
        if b.spec.key in seen:
            continue
        seen.add(b.spec.key)
        n = sum(1 for u in unplaced if u.spec.key == b.spec.key)
        warnings.append(
            f"{b.spec.sku} box {b.spec.box_no} ({b.spec.name}): {n} box(es) cannot fit on a pallet "
            f"(too large or too heavy for the pallet type)"
        )

    stood: dict[tuple, object] = {}
    for b in boxes:
        if b.spec.key not in stood and b.spec.needs_standing(pallet):
            stood[b.spec.key] = b.spec
    for spec in stood.values():
        warnings.append(
            f"{spec.sku} box {spec.box_no} ({spec.name}) is longer than the pallet, so it had to be "
            f"stood on its side or end. Allow some overhang on the pallet type to lay it flat."
        )

    pallets = [finalize_pallet(i + 1, st) for i, st in enumerate(states) if not st.is_empty()]
    return ShipmentResult(mode=mode, pallet=pallet, pallets=pallets, warnings=warnings, unplaced=unplaced)
