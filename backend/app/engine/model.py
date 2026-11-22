"""Engine data types.

This package is deliberately pure Python (stdlib only): no FastAPI, SQLAlchemy or Odoo imports.
It is ported verbatim into the Odoo addon in stage 2, and its golden tests are the parity
guarantee between the two codebases.

Units are whatever the caller uses consistently (the app uses inches and pounds).
Coordinates: x runs along the pallet length, y along its width, z up from the top of the deck.
The pallet deck occupies x in [0, length], y in [0, width].
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import permutations

EPS = 1e-6

# Bump whenever packing rules change, so saved estimates made under older rules show as
# "out of date" (it is part of the shipment input fingerprint).
ENGINE_VERSION = "2"

# Stability: a box that isn't marked this-side-up may not stand on a face whose height is more
# than this many times the narrower side of that face (no 50" boxes standing on end, no panels
# on edge). Boxes marked this-side-up keep their marked orientation regardless.
MAX_STANDING_RATIO = 2.0


def is_stable(dx: float, dy: float, dz: float) -> bool:
    return dz <= MAX_STANDING_RATIO * min(dx, dy) + EPS


@dataclass(frozen=True)
class BoxSpec:
    """One box of a product. A unit of the product ships in `qty_per_unit` of this box;
    `units_per_box` units of the product fit in one box (small items packed several to a carton)."""

    product_id: str
    sku: str
    product_name: str
    box_no: int
    name: str
    length: float
    width: float
    height: float
    weight: float
    this_side_up: bool = False
    stackable: bool = True
    max_load_on_top: float = 0.0  # 0 = no limit
    qty_per_unit: int = 1
    units_per_box: int = 1

    @property
    def key(self) -> tuple:
        return (self.product_id, self.box_no)

    def all_orientations(self) -> list[tuple[float, float, float]]:
        """Every (dx, dy, dz) the box could be placed in, deduplicated, in a deterministic order.
        A this-side-up box may only turn around the vertical axis."""
        if self.this_side_up:
            cands = [(self.length, self.width, self.height), (self.width, self.length, self.height)]
        else:
            cands = list(permutations((self.length, self.width, self.height)))
        seen: list[tuple[float, float, float]] = []
        for c in cands:
            if c not in seen:
                seen.append(c)
        return seen

    def orientations(self, pallet: "PalletSpec | None" = None) -> list[tuple[float, float, float]]:
        """Allowed orientations. Boxes not marked this-side-up must pass the stability rule —
        unless no stable orientation fits the pallet at all (e.g. a 50" box on a 48" deck with no
        overhang), in which case standing it up is the only option and `needs_standing` says so."""
        cands = self.all_orientations()
        if self.this_side_up:
            return cands
        stable = [c for c in cands if is_stable(*c)]
        if pallet is not None and not any(pallet.fits_footprint(*c) for c in stable):
            return cands
        return stable

    def needs_standing(self, pallet: "PalletSpec") -> bool:
        """True when the stability rule has to be waived for this box on this pallet."""
        if self.this_side_up:
            return False
        return not any(pallet.fits_footprint(*c) for c in self.all_orientations() if is_stable(*c))


@dataclass(frozen=True)
class BoxInstance:
    uid: int
    spec: BoxSpec


@dataclass(frozen=True)
class PalletSpec:
    length: float = 48.0
    width: float = 40.0
    deck_height: float = 5.5
    tare_weight: float = 45.0
    max_total_height: float = 72.0  # floor to top of load, deck included
    max_gross_weight: float = 2500.0  # load + tare
    max_overhang: float = 0.0  # per side

    def fits_footprint(self, dx: float, dy: float, dz: float) -> bool:
        o = self.max_overhang
        return (
            dx <= self.length + 2 * o + EPS
            and dy <= self.width + 2 * o + EPS
            and dz <= self.max_load_height + EPS
        )

    @property
    def max_load_height(self) -> float:
        return self.max_total_height - self.deck_height

    @property
    def max_load_weight(self) -> float:
        return self.max_gross_weight - self.tare_weight


@dataclass
class Placement:
    box: BoxInstance
    x: float
    y: float
    z: float
    dx: float
    dy: float
    dz: float

    @property
    def spec(self) -> BoxSpec:
        return self.box.spec

    @property
    def top(self) -> float:
        return self.z + self.dz

    def to_dict(self) -> dict:
        s = self.spec
        return {
            "uid": self.box.uid,
            "product_id": s.product_id,
            "sku": s.sku,
            "product_name": s.product_name,
            "box_no": s.box_no,
            "box_name": s.name,
            "x": round(self.x, 3),
            "y": round(self.y, 3),
            "z": round(self.z, 3),
            "dx": round(self.dx, 3),
            "dy": round(self.dy, 3),
            "dz": round(self.dz, 3),
            "weight": s.weight,
        }


@dataclass
class PalletResult:
    index: int
    placements: list[Placement]
    length: float
    width: float
    height: float
    net_weight: float
    gross_weight: float
    cubic_feet: float
    density: float
    freight_class: str
    box_summary: list[dict]

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "length": self.length,
            "width": self.width,
            "height": self.height,
            "net_weight": self.net_weight,
            "gross_weight": self.gross_weight,
            "cubic_feet": self.cubic_feet,
            "density": self.density,
            "freight_class": self.freight_class,
            "box_summary": self.box_summary,
            "placements": [p.to_dict() for p in self.placements],
        }


@dataclass
class ShipmentResult:
    mode: str
    pallet: PalletSpec
    pallets: list[PalletResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unplaced: list[BoxInstance] = field(default_factory=list)

    @property
    def pallet_count(self) -> int:
        return len(self.pallets)

    @property
    def total_gross_weight(self) -> float:
        return round(sum(p.gross_weight for p in self.pallets), 2)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "pallet_count": self.pallet_count,
            "total_gross_weight": self.total_gross_weight,
            "warnings": list(self.warnings),
            "unplaced": [
                {"sku": b.spec.sku, "box_no": b.spec.box_no, "box_name": b.spec.name}
                for b in self.unplaced
            ],
            "pallets": [p.to_dict() for p in self.pallets],
        }
