"""Tightest-fit packer: extreme-point heuristic, best of several box orderings and both
placement rules.

Boxes are mixed freely. For each ordering, boxes are placed first-fit across open pallets at the
lowest/back-most/left-most feasible extreme point. The best run wins: fewest unplaced boxes, then
fewest pallets, then the lowest tallest pallet, then the lowest total height.
"""

from __future__ import annotations

from typing import Callable

from .model import BoxInstance, PalletSpec
from .pallet_state import LOW_TOP, RULES, PalletState

SortKey = Callable[[BoxInstance], tuple]


def _vol(b: BoxInstance) -> float:
    s = b.spec
    return s.length * s.width * s.height


def _density(b: BoxInstance) -> float:
    s = b.spec
    return s.weight / (s.length * s.width * s.height)


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
    # densest first: dense boxes build the base, bulky light boxes (mostly air) go on top
    ("density", lambda b: (not b.spec.stackable, -_density(b), -b.spec.weight, b.spec.sku, b.spec.box_no, b.uid)),
]


def pack_boxes_into(
    states: list[PalletState], boxes: list[BoxInstance], spec: PalletSpec, rule: str = LOW_TOP
) -> tuple[list[PalletState], list[BoxInstance]]:
    """First-fit `boxes` into `states` (mutated), opening new pallets as needed."""
    unplaced: list[BoxInstance] = []
    for box in boxes:
        if any(st.place_at_best_point(box) for st in states):
            continue
        fresh = PalletState(spec, rule=rule)
        if fresh.place_at_best_point(box):
            states.append(fresh)
        else:
            unplaced.append(box)
    return states, unplaced


# How much height (inches) a fully inverted load is worth: each 10% of the shipment's weight that
# rests on lighter-for-their-size boxes of another product counts like 3.6" of extra height.
# Big inversions (a light pendant carton carrying a stack of dense fixtures) beat a few inches of
# height; small ones don't justify a much taller pallet. Calibrated on two real orders (any value
# from ~18 to ~700 picks the right layout for both); see CLAUDE.md.
HEAVY_LOW_INCHES = 36.0


def score(states: list[PalletState], unplaced: list[BoxInstance]) -> tuple:
    """Lower is better: unplaced boxes, then pallets, then a cost that adds the tallest pallet's
    height to a penalty for weight resting on lighter-for-their-size boxes (heavy at the bottom,
    even at the price of some height — signed off by the user), then total height."""
    tops = [st.top for st in states]
    net = sum(st.net_weight for st in states)
    on_lighter = sum(st.weight_on_lighter() for st in states)
    share = on_lighter / net if net > 0 else 0.0
    cost = max(tops, default=0.0) + HEAVY_LOW_INCHES * share
    return (len(unplaced), len(states), round(cost, 6), round(sum(tops), 6))


def pack_tightest(boxes: list[BoxInstance], spec: PalletSpec) -> tuple[list[PalletState], list[BoxInstance]]:
    """Every ordering × both placement rules; the best-scoring run wins (ties → the earlier, i.e.
    LOW_TOP). Trying BOTTOM_LEFT too means tightest never does worse than the original rule."""
    best = None
    for rule in RULES:
        for _name, key in ORDERINGS:
            states, unplaced = pack_boxes_into([], sorted(boxes, key=key), spec, rule)
            s = score(states, unplaced)
            if best is None or s < best[0]:
                best = (s, states, unplaced)
    assert best is not None
    return best[1], best[2]
