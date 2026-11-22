"""Density and suggested LTL freight class.

The table is the NMFC 13-subprovision density scale (lb/ft³ lower bound → class), in effect
since the July 2025 NMFC update. It is a *suggestion* for quoting only — the actual class depends
on the commodity's NMFC item. Callers may pass their own table (e.g. a company override).
"""

from __future__ import annotations

NMFC_DENSITY_TABLE: list[tuple[float, str]] = [
    (50.0, "50"),
    (35.0, "55"),
    (30.0, "60"),
    (22.5, "65"),
    (15.0, "70"),
    (12.0, "85"),
    (10.0, "92.5"),
    (8.0, "100"),
    (6.0, "125"),
    (4.0, "175"),
    (2.0, "250"),
    (1.0, "300"),
    (0.0, "400"),
]


def cubic_feet(length_in: float, width_in: float, height_in: float) -> float:
    return length_in * width_in * height_in / 1728.0


def density(weight_lb: float, cu_ft: float) -> float:
    return weight_lb / cu_ft if cu_ft > 0 else 0.0


def freight_class(density_pcf: float, table: list[tuple[float, str]] | None = None) -> str:
    for lower, cls in table or NMFC_DENSITY_TABLE:
        if density_pcf >= lower:
            return cls
    return (table or NMFC_DENSITY_TABLE)[-1][1]
