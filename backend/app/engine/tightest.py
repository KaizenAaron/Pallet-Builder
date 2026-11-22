"""Tightest-fit packer: extreme-point heuristic, best of several box orderings.

Boxes are mixed freely. For each ordering, boxes are placed first-fit across open pallets at the
lowest/back-most/left-most feasible extreme point. The best run wins: fewest unplaced boxes, then
fewest pallets, then the lowest tallest pallet, then the lowest total height.
"""

from __future__ import annotations

from typing import Callable

from .model import BoxInstance, PalletSpec
from .pallet_state import PalletState

SortKey = Callable[[BoxInstance], tuple]


def _vol(b: BoxInstance) -> float:
    s = b.spec
    return s.length * s.width * s.height


def _base(b: BoxInstance) -> float:
    s = b.spec
    dims = sorted((s.length, s.width, s.height))
    return dims[1] * dims[2]


# Non-stackable boxes go last in every ordering so they end up on top.
ORDERINGS: list[tuple[str, SortKey]] = [
    ("volume", lambda b: (not b.spec.stackable, -_vol(b), -b.spec.weight, b.spec.sku, b.spec.box_no, b.uid)),
    ("weight", lambda b: (not b.spec.stackable, -b.spec.weight, -_vol(b), b.spec.sku, b.spec.box_no, b.uid)),
    ("footprint", lambda b: (not b.spec.stackable, -_base(b), -_vol(b), b.spec.sku, b.spec.box_no, b.uid)),
    ("height", lambda b: (not b.spec.stackable, -max(b.spec.length, b.spec.width, b.spec.height), -_vol(b), b.spec.sku, b.spec.box_no, b.uid)),
]


def pack_boxes_into(
    states: list[PalletState], boxes: list[BoxInstance], spec: PalletSpec
) -> tuple[list[PalletState], list[BoxInstance]]:
    """First-fit `boxes` into `states` (mutated), opening new pallets as needed."""
    unplaced: list[BoxInstance] = []
    for box in boxes:
        if any(st.place_at_best_point(box) for st in states):
            continue
        fresh = PalletState(spec)
        if fresh.place_at_best_point(box):
            states.append(fresh)
        else:
            unplaced.append(box)
    return states, unplaced


def score(states: list[PalletState], unplaced: list[BoxInstance]) -> tuple:
    tops = [st.top for st in states]
    return (len(unplaced), len(states), round(max(tops, default=0.0), 6), round(sum(tops), 6))


def pack_tightest(boxes: list[BoxInstance], spec: PalletSpec) -> tuple[list[PalletState], list[BoxInstance]]:
    best = None
    for _name, key in ORDERINGS:
        states, unplaced = pack_boxes_into([], sorted(boxes, key=key), spec)
        s = score(states, unplaced)
        if best is None or s < best[0]:
            best = (s, states, unplaced)
    assert best is not None
    return best[1], best[2]
