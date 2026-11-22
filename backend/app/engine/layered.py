"""Layered (warehouse-friendly) packer.

1. Identical boxes are grouped. For each group, the best single-box layer pattern is chosen:
   a plain grid in either rotation, or a two-block pattern (some rows/columns turned 90°).
   Boxes that are not this-side-up may also stand on another face if that packs better.
2. Full layers are stacked heaviest group first, non-stackable groups last, each layer centered
   on the deck. A layer goes on the first pallet that accepts every box in it; otherwise a new
   pallet is started.
3. Leftover boxes (partial layers) are packed on top with the extreme-point packer, first-fit
   across the pallets already built, so they end up as a mixed top layer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .model import EPS, BoxInstance, BoxSpec, PalletSpec
from .pallet_state import PalletState
from .tightest import ORDERINGS, pack_boxes_into

Rect = tuple[float, float, float, float]  # x, y, dx, dy


def _grid(a: float, b: float, X: float, Y: float, x0: float = 0.0, y0: float = 0.0) -> list[Rect]:
    nx = int((X + EPS) // a) if a > 0 else 0
    ny = int((Y + EPS) // b) if b > 0 else 0
    return [(x0 + i * a, y0 + j * b, a, b) for j in range(ny) for i in range(nx)]


def layer_pattern(a: float, b: float, X: float, Y: float) -> list[Rect]:
    """Best pattern of an a×b footprint in an X×Y area. Ties go to the simplest pattern."""
    candidates: list[list[Rect]] = [_grid(a, b, X, Y), _grid(b, a, X, Y)]
    for (p, q) in ((a, b), (b, a)):
        # k columns of p-wide boxes, the rest of the length turned 90°
        for k in range(1, int((X + EPS) // p)):
            left = _grid(p, q, k * p, Y)
            right = _grid(q, p, X - k * p, Y, x0=k * p)
            candidates.append(left + right)
        # k rows of q-deep boxes, the rest of the width turned 90°
        for k in range(1, int((Y + EPS) // q)):
            front = _grid(p, q, X, k * q)
            back = _grid(q, p, X, Y - k * q, y0=k * q)
            candidates.append(front + back)
    best: list[Rect] = []
    for c in candidates:  # strict '>' keeps the earliest (simplest) on ties
        if len(c) > len(best):
            best = c
    return best


@dataclass
class GroupPlan:
    spec: BoxSpec
    boxes: list[BoxInstance]
    height: float
    rects: list[Rect]  # centered on the deck

    @property
    def per_layer(self) -> int:
        return len(self.rects)


def _layers_per_pallet(spec: BoxSpec, pallet: PalletSpec, per_layer: int, h: float) -> int:
    if per_layer == 0:
        return 0
    n = int((pallet.max_load_height + EPS) // h)
    n = min(n, int((pallet.max_load_weight + EPS) // (per_layer * spec.weight)) if spec.weight > 0 else n)
    if not spec.stackable:
        n = min(n, 1)
    if spec.max_load_on_top > 0 and spec.weight > 0:
        n = min(n, 1 + int((spec.max_load_on_top + EPS) // spec.weight))
    return max(n, 0)


def plan_group(spec: BoxSpec, boxes: list[BoxInstance], pallet: PalletSpec) -> GroupPlan:
    X = pallet.length + 2 * pallet.max_overhang
    Y = pallet.width + 2 * pallet.max_overhang
    n = len(boxes)
    best = None
    for (fa, fb, h) in spec.orientations(pallet):
        if fa > fb + EPS:
            continue  # (a, b) and (b, a) give the same patterns
        rects = layer_pattern(fa, fb, X, Y)
        per = len(rects)
        lpp = _layers_per_pallet(spec, pallet, per, h)
        if per == 0 or lpp == 0:
            continue
        score = (math.ceil(n / (per * lpp)), math.ceil(n / per) * h, -per, h)
        if best is None or score < best[0]:
            best = (score, h, rects)
    if best is None:
        return GroupPlan(spec=spec, boxes=boxes, height=0.0, rects=[])
    _, h, rects = best
    px = max(r[0] + r[2] for r in rects)
    py = max(r[1] + r[3] for r in rects)
    ox = (pallet.length - px) / 2
    oy = (pallet.width - py) / 2
    centered = [(round(x + ox, 6), round(y + oy, 6), dx, dy) for (x, y, dx, dy) in rects]
    return GroupPlan(spec=spec, boxes=boxes, height=h, rects=centered)


def _try_layer(state: PalletState, boxes: list[BoxInstance], plan: GroupPlan) -> bool:
    z = state.top
    snap = state.snapshot()
    for box, (x, y, dx, dy) in zip(boxes, plan.rects):
        if not state.try_place(box, x, y, z, dx, dy, plan.height):
            state.restore(snap)
            return False
    return True


def pack_layered(boxes: list[BoxInstance], pallet: PalletSpec) -> tuple[list[PalletState], list[BoxInstance]]:
    groups: dict[tuple, list[BoxInstance]] = {}
    for b in boxes:
        groups.setdefault(b.spec.key, []).append(b)
    plans = [plan_group(bs[0].spec, bs, pallet) for bs in groups.values()]
    plans.sort(
        key=lambda g: (
            not g.spec.stackable,
            -g.spec.weight,
            -(g.spec.length * g.spec.width * g.spec.height),
            g.spec.sku,
            g.spec.box_no,
        )
    )

    states: list[PalletState] = []
    layered_ok: list[bool] = []  # pallet still has a flat top made only of full layers
    remainder: list[BoxInstance] = []
    for plan in plans:
        per = plan.per_layer
        if per == 0:
            remainder.extend(plan.boxes)
            continue
        full = len(plan.boxes) // per
        queue = list(plan.boxes)
        for _ in range(full):
            layer, queue = queue[:per], queue[per:]
            placed = False
            for i, st in enumerate(states):
                if layered_ok[i] and _try_layer(st, layer, plan):
                    placed = True
                    break
            if not placed:
                st = PalletState(pallet)
                if _try_layer(st, layer, plan):
                    states.append(st)
                    layered_ok.append(True)
                else:  # a whole layer can never fit (e.g. too heavy); pack box by box instead
                    remainder.extend(layer)
        remainder.extend(queue)

    order = ORDERINGS[0][1]
    states, unplaced = pack_boxes_into(states, sorted(remainder, key=order), pallet)
    return states, unplaced
