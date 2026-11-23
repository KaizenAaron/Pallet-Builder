"""Pallet packing engine — the single source of truth for every pallet number.

Pure Python (stdlib only) so it can be copied verbatim into the Odoo addon in stage 2.

    result = pack(lines, PalletSpec(...), mode="layered")   # or "tightest"
    result = pack_auto(lines, [PalletSpec(...), ...], mode)  # choose the pallet type per pallet
"""

from __future__ import annotations

from .constraints import validate
from .expand import ShipmentLine, expand_lines
from .layered import GROUP_ORDERS, pack_layered
from .model import ENGINE_VERSION, MAX_STANDING_RATIO, BoxInstance, BoxSpec, PalletResult, PalletSpec, Placement, ShipmentResult
from .pallet_state import RULES
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
    "pack_auto",
    "validate",
]


def _pack_states(boxes: list[BoxInstance], pallet: PalletSpec, mode: str):
    """Best packing of `boxes` on one pallet type (the search behind both modes)."""
    if not boxes:
        return [], []
    # Layered = the same layer-building logic under each group order × placement rule; the best
    # wins (so it's never worse than any single rule). Tightest fit = the free-mixing extreme-point
    # runs (every ordering × every rule) *and* the layered results, so it never needs more pallets
    # than Layered.
    candidates = [pack_layered(boxes, pallet, rule, order) for order in GROUP_ORDERS for rule in RULES]
    if mode == "tightest":
        candidates.append(pack_tightest(boxes, pallet))
    return min(candidates, key=lambda c: score(*c))


def _warnings(boxes, unplaced, spec_for_box) -> list[str]:
    out: list[str] = []
    seen: set[tuple] = set()
    for b in unplaced:
        if b.spec.key in seen:
            continue
        seen.add(b.spec.key)
        n = sum(1 for u in unplaced if u.spec.key == b.spec.key)
        out.append(
            f"{b.spec.sku} box {b.spec.box_no} ({b.spec.name}): {n} box(es) cannot fit on a pallet "
            f"(too large or too heavy for the pallet type)"
        )
    stood: dict[tuple, object] = {}
    for b in boxes:
        spec = spec_for_box(b)
        if spec is not None and b.spec.key not in stood and b.spec.needs_standing(spec):
            stood[b.spec.key] = b.spec
    for s in stood.values():
        out.append(
            f"{s.sku} box {s.box_no} ({s.name}) is longer than the pallet, so it had to be "
            f"stood on its side or end. Allow some overhang on the pallet type to lay it flat."
        )
    return out


def pack(lines: list[ShipmentLine], pallet: PalletSpec, mode: str = "layered") -> ShipmentResult:
    """Pack every pallet on one pallet type."""
    if mode not in MODES:
        raise ValueError(f"unknown packing mode {mode!r}")
    boxes, warnings = expand_lines(lines)
    states, unplaced = _pack_states(boxes, pallet, mode)
    warnings += _warnings(boxes, unplaced, lambda b: pallet)
    pallets = [finalize_pallet(i + 1, st) for i, st in enumerate(states) if not st.is_empty()]
    return ShipmentResult(mode=mode, pallet=pallet, pallets=pallets, warnings=warnings, unplaced=unplaced)


def _footprint(state) -> float:
    """Overall floor area of one pallet: the deck, or the load where it overhangs."""
    s = state.spec
    ps = state.placements
    if not ps:
        return s.deck_area
    minx = min([0.0] + [p.x for p in ps])
    maxx = max([s.length] + [p.x + p.dx for p in ps])
    miny = min([0.0] + [p.y for p in ps])
    maxy = max([s.width] + [p.y + p.dy for p in ps])
    # the load is centered on the deck afterwards, so the overall size is the larger span
    return max(maxx - minx, s.length) * max(maxy - miny, s.width)


def _could_fit(boxes: list[BoxInstance], spec: PalletSpec) -> bool:
    """Cheap, exact *necessary* conditions for one pallet of `spec` to take all `boxes`."""
    if sum(b.spec.weight for b in boxes) > spec.max_load_weight + 1e-9:
        return False
    cap = (spec.length + 2 * spec.max_overhang) * (spec.width + 2 * spec.max_overhang) * spec.max_load_height
    if sum(b.spec.length * b.spec.width * b.spec.height for b in boxes) > cap + 1e-9:
        return False
    return all(any(spec.fits_footprint(*o) for o in b.spec.all_orientations()) for b in boxes)


def _quick_one_pallet(boxes: list[BoxInstance], spec: PalletSpec) -> bool:
    """A few fast packings; True as soon as one puts every box on a single pallet."""
    from .pallet_state import LOW_TOP
    from .tightest import ORDERINGS, pack_boxes_into

    for _name, order in ORDERINGS:
        states, left = pack_boxes_into([], sorted(boxes, key=order), spec, LOW_TOP)
        if len(states) == 1 and not left:
            return True
    states, left = pack_layered(boxes, spec, LOW_TOP)
    return len(states) == 1 and not left


def _right_size(state, pallets: list[PalletSpec], mode: str):
    """Move one packed pallet's boxes to the smallest candidate type that takes them all on a single
    pallet (full search for the final layout), or keep it as it is."""
    boxes = [p.box for p in state.placements]
    for other in sorted(pallets, key=lambda p: (p.deck_area, p.name)):  # smallest first
        if other.deck_area >= state.spec.deck_area - 1e-9 or other == state.spec:
            continue
        if not _could_fit(boxes, other) or not _quick_one_pallet(boxes, other):
            continue
        alone, left = _pack_states(boxes, other, mode)
        if len(alone) == 1 and not left and _footprint(alone[0]) < _footprint(state) - 1e-9:
            return alone[0]
    return state


def pack_auto(lines: list[ShipmentLine], pallets: list[PalletSpec], mode: str = "layered") -> ShipmentResult:
    """Choose the pallet type for each pallet. Best = fewest unplaced boxes, then fewest pallets,
    then least total floor space, then the usual heavy-at-the-bottom/height cost.

    1. The whole order is packed on each candidate type (one full search per type). Skipping types
       that a bigger one "covers" was tried: right-sizing alone then lost floor space on ~1 in 4
       random orders, so every type gets its own run.
    2. Right-sizing: every pallet of each run is re-packed *alone* on each candidate with a smaller
       deck; the smallest type that takes all its boxes on one pallet replaces it. The pallet count
       never changes, so a big pallet is only used where a box needs it.
    3. The best run wins; pallets are listed largest first.
    With a single candidate this is exactly pack().
    """
    if mode not in MODES:
        raise ValueError(f"unknown packing mode {mode!r}")
    if not pallets:
        raise ValueError("at least one pallet type is needed")
    if len(pallets) == 1:
        return pack(lines, pallets[0], mode)
    boxes, warnings = expand_lines(lines)

    def key(states, unplaced):
        return (
            len(unplaced),
            len(states),
            round(sum(_footprint(st) for st in states), 3),
            score(states, unplaced)[2:],
        )

    runs = [(spec, *_pack_states(boxes, spec, mode)) for spec in pallets]
    # Right-sizing can't change the pallet count or unplaced boxes, so only runs that already have
    # the best (unplaced, pallets) can win — the others are skipped (big time saver).
    floor = min((len(u), len(st)) for _, st, u in runs)
    best = None
    for spec, states, unplaced in runs:
        if (len(unplaced), len(states)) != floor:
            continue
        sized = [_right_size(st, pallets, mode) for st in states]
        k = key(sized, unplaced)
        if best is None or k < best[0]:
            best = (k, sized, unplaced)
    assert best is not None
    _, states, unplaced = best
    states = sorted(states, key=lambda st: -_footprint(st))  # stable: same-size pallets keep order
    box_spec = {p.box.uid: st.spec for st in states for p in st.placements}
    warnings += _warnings(boxes, unplaced, lambda b: box_spec.get(b.uid))
    results = [finalize_pallet(i + 1, st) for i, st in enumerate(states) if not st.is_empty()]
    return ShipmentResult(mode=mode, pallet=states[0].spec if states else pallets[0], pallets=results,
                          warnings=warnings, unplaced=unplaced)
