"""Incremental pallet builder shared by both packing modes.

`PalletState.try_place` is the only way a box gets onto a pallet, so every packer obeys the same
rules. `constraints.validate` re-checks finished pallets independently.

Rules enforced on every placement:
- inside the deck footprint plus `max_overhang` on each side, and under the max load height
- no overlap with boxes already placed
- resting on the deck, or at least `support_ratio` of its base on top faces of stackable boxes
- never touching the underside of a box already placed (no filling gaps under a box, which keeps
  the support graph fixed once a box is placed)
- load on every box below stays within its `max_load_on_top` (0 = unlimited); a box's own weight
  plus everything on it is shared among its supports in proportion to contact area
- pallet gross weight within the limit
"""

from __future__ import annotations

from .model import EPS, BoxInstance, PalletSpec, Placement

DEFAULT_SUPPORT_RATIO = 0.75
DECK = -1


def overlap_1d(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def footprint_overlap(ax, ay, adx, ady, bx, by, bdx, bdy) -> float:
    return overlap_1d(ax, ax + adx, bx, bx + bdx) * overlap_1d(ay, ay + ady, by, by + bdy)


class PalletState:
    def __init__(self, spec: PalletSpec, support_ratio: float = DEFAULT_SUPPORT_RATIO):
        self.spec = spec
        self.support_ratio = support_ratio
        self.placements: list[Placement] = []
        self.supports: list[list[tuple[int, float]]] = []  # per placement: (support index | DECK, contact area)
        self.loads: list[float] = []  # weight resting on each placement
        self.net_weight = 0.0
        self.points: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)]
        # Box specs that found no position since the last placement. Identical boxes can't fit
        # either until something changes, so first-fit skips this pallet for them (exact, just
        # faster — results are identical to trying every point again).
        self._no_fit: set = set()
        self.used_volume = 0.0

    # ------------------------------------------------------------------ queries
    @property
    def top(self) -> float:
        return max((p.top for p in self.placements), default=0.0)

    def is_empty(self) -> bool:
        return not self.placements

    # ------------------------------------------------------------------ placement
    def check(self, box: BoxInstance, x: float, y: float, z: float, dx: float, dy: float, dz: float):
        """Return (supports, load_increments) if the box can go here, else None."""
        s = self.spec
        o = s.max_overhang
        spec = box.spec
        if x < -o - EPS or y < -o - EPS or z < -EPS:
            return None
        if x + dx > s.length + o + EPS or y + dy > s.width + o + EPS:
            return None
        if z + dz > s.max_load_height + EPS:
            return None
        if self.net_weight + spec.weight > s.max_load_weight + EPS:
            return None

        supports: list[tuple[int, float]] = []
        base = dx * dy
        for i, p in enumerate(self.placements):
            ox = overlap_1d(x, x + dx, p.x, p.x + p.dx)
            if ox <= EPS:
                continue
            oy = overlap_1d(y, y + dy, p.y, p.y + p.dy)
            if oy <= EPS:
                continue
            oz = overlap_1d(z, z + dz, p.z, p.top)
            if oz > EPS:
                return None  # collision
            if abs(p.top - z) <= EPS:
                if not p.spec.stackable:
                    return None
                supports.append((i, ox * oy))
            elif abs(p.z - (z + dz)) <= EPS:
                return None  # would sit under an existing box
        if z <= EPS:
            supports = [(DECK, base)]
        else:
            area = sum(a for _, a in supports)
            if area + EPS < self.support_ratio * base:
                return None

        increments = self._propagate(supports, spec.weight)
        for i, inc in increments.items():
            limit = self.placements[i].spec.max_load_on_top
            if limit > 0 and self.loads[i] + inc > limit + EPS:
                return None
        return supports, increments

    def _propagate(self, supports: list[tuple[int, float]], weight: float) -> dict[int, float]:
        """Distribute `weight` down the support graph; returns extra load per placement index."""
        inc: dict[int, float] = {}
        stack: list[tuple[list[tuple[int, float]], float]] = [(supports, weight)]
        while stack:
            sups, amount = stack.pop()
            total = sum(a for _, a in sups)
            if total <= 0:
                continue
            for idx, a in sups:
                if idx == DECK:
                    continue
                share = amount * a / total
                inc[idx] = inc.get(idx, 0.0) + share
                stack.append((self.supports[idx], share))
        return inc

    def try_place(self, box: BoxInstance, x, y, z, dx, dy, dz) -> bool:
        res = self.check(box, x, y, z, dx, dy, dz)
        if res is None:
            return False
        supports, increments = res
        p = Placement(box=box, x=x, y=y, z=z, dx=dx, dy=dy, dz=dz)
        self.placements.append(p)
        self.supports.append(supports)
        self.loads.append(0.0)
        for i, inc in increments.items():
            self.loads[i] += inc
        self.net_weight += box.spec.weight
        self.used_volume += dx * dy * dz
        self._no_fit.clear()
        self._update_points(p)
        return True

    def snapshot(self):
        return (len(self.placements), list(self.loads), self.net_weight, list(self.points), self.used_volume)

    def restore(self, snap) -> None:
        n, loads, weight, points, used = snap
        self.used_volume = used
        self._no_fit.clear()
        del self.placements[n:]
        del self.supports[n:]
        self.loads = loads
        self.net_weight = weight
        self.points = points

    # ------------------------------------------------------------------ extreme points
    def _update_points(self, p: Placement) -> None:
        new = [
            (p.x + p.dx, p.y, p.z),
            (p.x, p.y + p.dy, p.z),
            (p.x, p.y, p.top),
        ]
        projected = []
        for (px, py, pz) in new:
            if pz > EPS:
                projected.append((px, py, self._project_down(px, py, pz)))
        projected.append((p.x + p.dx, self._project_y(p.x + p.dx, p.y, p.z), p.z))
        projected.append((self._project_x(p.x, p.y + p.dy, p.z), p.y + p.dy, p.z))
        pts = [q for q in self.points if not self._inside(q, p)]
        for q in new + projected:
            q = (round(q[0], 6), round(q[1], 6), round(q[2], 6))
            if q not in pts and not any(self._inside(q, r) for r in self.placements):
                pts.append(q)
        pts.sort(key=lambda q: (q[2], q[1], q[0]))
        self.points = pts

    @staticmethod
    def _inside(q, p: Placement) -> bool:
        x, y, z = q
        return (
            p.x - EPS <= x < p.x + p.dx - EPS
            and p.y - EPS <= y < p.y + p.dy - EPS
            and p.z - EPS <= z < p.top - EPS
        )

    def _project_down(self, x, y, z) -> float:
        best = 0.0
        for p in self.placements:
            if p.x - EPS <= x < p.x + p.dx - EPS and p.y - EPS <= y < p.y + p.dy - EPS and p.top <= z + EPS:
                best = max(best, p.top)
        return best

    def _project_y(self, x, y, z) -> float:
        best = min(0.0, y)
        for p in self.placements:
            if p.x - EPS <= x < p.x + p.dx - EPS and p.z - EPS <= z < p.top - EPS and p.y + p.dy <= y + EPS:
                best = max(best, p.y + p.dy)
        return best

    def _project_x(self, x, y, z) -> float:
        best = min(0.0, x)
        for p in self.placements:
            if p.y - EPS <= y < p.y + p.dy - EPS and p.z - EPS <= z < p.top - EPS and p.x + p.dx <= x + EPS:
                best = max(best, p.x + p.dx)
        return best

    def place_at_best_point(self, box: BoxInstance) -> bool:
        """Extreme-point placement: lowest, then back-most, then left-most point that accepts the
        box; at each point prefer the lowest orientation, then the largest footprint."""
        if box.spec in self._no_fit:
            return False
        sp = box.spec
        s = self.spec
        # Exact quick rejections: too heavy for what's left, or more volume than is left.
        if self.net_weight + sp.weight > s.max_load_weight + EPS:
            return False
        capacity = (s.length + 2 * s.max_overhang) * (s.width + 2 * s.max_overhang) * s.max_load_height
        if self.used_volume + sp.length * sp.width * sp.height > capacity + EPS:
            return False
        orients = sorted(box.spec.orientations(self.spec), key=lambda d: (d[2], -(d[0] * d[1]), -d[0]))
        for (x, y, z) in self.points:
            for (dx, dy, dz) in orients:
                if self.try_place(box, x, y, z, dx, dy, dz):
                    return True
        self._no_fit.add(box.spec)
        return False

    # ------------------------------------------------------------------ finishing
    def centered_placements(self) -> list[Placement]:
        """Shift the whole load so it sits centered on the deck (a rigid shift keeps every rule)."""
        if not self.placements:
            return []
        s = self.spec
        minx = min(p.x for p in self.placements)
        maxx = max(p.x + p.dx for p in self.placements)
        miny = min(p.y for p in self.placements)
        maxy = max(p.y + p.dy for p in self.placements)
        sx = s.length / 2 - (minx + maxx) / 2
        sy = s.width / 2 - (miny + maxy) / 2
        return [
            Placement(box=p.box, x=round(p.x + sx, 6), y=round(p.y + sy, 6), z=p.z, dx=p.dx, dy=p.dy, dz=p.dz)
            for p in self.placements
        ]
