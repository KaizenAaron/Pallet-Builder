"""Turn shipment lines (product + quantity) into individual box instances."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .model import BoxInstance, BoxSpec


@dataclass
class ShipmentLine:
    product_id: str
    sku: str
    product_name: str
    quantity: float
    boxes: list[BoxSpec] = field(default_factory=list)


def expand_lines(lines: list[ShipmentLine]) -> tuple[list[BoxInstance], list[str]]:
    """Each unit ships in all of its product's boxes (`qty_per_unit` of each box);
    `units_per_box` units share one box. Products with no box data are skipped with a warning
    rather than failing the whole estimate."""
    instances: list[BoxInstance] = []
    warnings: list[str] = []
    uid = 0
    for line in lines:
        if line.quantity <= 0:
            continue
        if not line.boxes:
            warnings.append(f"{line.sku or line.product_name}: no box data — left out of the estimate")
            continue
        for spec in sorted(line.boxes, key=lambda b: b.box_no):
            per_box = max(1, int(spec.units_per_box))
            count = math.ceil(line.quantity / per_box) * max(1, int(spec.qty_per_unit))
            for _ in range(count):
                uid += 1
                instances.append(BoxInstance(uid=uid, spec=spec))
    return instances, warnings
