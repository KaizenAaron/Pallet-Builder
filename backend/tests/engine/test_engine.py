"""Engine golden tests.

The expected numbers here are hand-checked (see each docstring). They are pinned the same way the
Crystal parity tests are in Sales-Rep-Activity: if a change breaks them, the change is wrong
unless the new numbers are explicitly signed off. Every result also goes through the independent
validator, for both packing modes.
"""

from __future__ import annotations

import time

import pytest

from app.engine import MODES, BoxSpec, PalletSpec, ShipmentLine, pack, validate

PALLET = PalletSpec()  # 48×40, 5.5" deck, 45 lb tare, 72" max height, 2,500 lb max, no overhang


def box(sku="A", no=1, l=12, w=10, h=10, wt=10.0, **kw) -> BoxSpec:
    return BoxSpec(
        product_id=sku, sku=sku, product_name=f"Product {sku}", box_no=no, name=f"{sku} box {no}",
        length=l, width=w, height=h, weight=wt, **kw,
    )


def line(spec_list, qty, sku=None) -> ShipmentLine:
    s = sku or spec_list[0].sku
    return ShipmentLine(product_id=s, sku=s, product_name=f"Product {s}", quantity=qty, boxes=spec_list)


def run(lines, mode="layered", pallet=PALLET):
    res = pack(lines, pallet, mode)
    for p in res.pallets:
        errors = validate(pallet, p.placements)
        assert errors == [], f"{mode} pallet {p.index}: {errors[:5]}"
    return res


def counts(res):
    return [len(p.placements) for p in res.pallets]


# ---------------------------------------------------------------- golden: layered


def test_single_sku_full_layers():
    """12×10×10 @10 lb: 16 per layer on 48×40, 6 layers fit 66.5" → 96 per pallet.
    100 boxes → 96 + 4. Pallet 1: 60" load + 5.5 deck = 65.5", 960 + 45 = 1005 lb."""
    res = run([line([box()], 100)])
    assert counts(res) == [96, 4]
    p1, p2 = res.pallets
    assert (p1.length, p1.width, p1.height, p1.gross_weight) == (48, 40, 65.5, 1005)
    assert (p2.height, p2.gross_weight) == (15.5, 85)


def test_multi_box_product():
    """One unit = box 1 (48×20×10, 50 lb) + box 2 (24×20×8, 20 lb). 4 units → 4 + 4 boxes.
    Heavier box 1 first: 2 per layer × 2 layers = 20"; box 2: 4 per layer, 1 layer = 8".
    Height 28 + 5.5 = 33.5"; gross 4×50 + 4×20 + 45 = 325 lb."""
    specs = [box("FIX", 1, 48, 20, 10, 50.0), box("FIX", 2, 24, 20, 8, 20.0)]
    res = run([line(specs, 4)])
    assert counts(res) == [8]
    p = res.pallets[0]
    assert (p.height, p.gross_weight) == (33.5, 325)
    assert {(r["box_no"], r["count"]) for r in p.box_summary} == {(1, 4), (2, 4)}


def test_weight_limit_starts_new_pallet():
    """20×20×10 @300 lb: (2500 − 45) / 300 = 8 boxes per pallet → 10 boxes = 8 + 2."""
    res = run([line([box(l=20, w=20, h=10, wt=300.0)], 10)])
    assert counts(res) == [8, 2]
    assert res.pallets[0].gross_weight == 8 * 300 + 45


def test_height_limit_starts_new_pallet():
    """24×20×20 @10 lb this-side-up: 4 per layer, 3 layers (60") fit 66.5". 16 boxes → 12 + 4."""
    res = run([line([box(l=24, w=20, h=20, this_side_up=True)], 16)])
    assert counts(res) == [12, 4]
    assert [p.height for p in res.pallets] == [65.5, 25.5]


def test_this_side_up_stays_upright():
    """10×10×30 this-side-up: 16 per layer standing, 2 layers = 60". 20 boxes → one pallet,
    the 4 leftovers on top of the first layer. Every box keeps dz = 30."""
    res = run([line([box(l=10, w=10, h=30, this_side_up=True)], 20)])
    assert counts(res) == [20]
    assert all(p.dz == 30 for p in res.pallets[0].placements)
    assert res.pallets[0].height == 65.5


def test_non_stackable_single_layer():
    """24×20×20 not stackable: one layer of 4 per pallet → 6 boxes = 4 + 2, 25.5" tall."""
    res = run([line([box(l=24, w=20, h=20, stackable=False, this_side_up=True)], 6)])
    assert counts(res) == [4, 2]
    assert all(p.height == 25.5 for p in res.pallets)


def test_max_load_on_top_limits_column_height():
    """24×20×10 @50 lb, max 100 lb on top: columns of 3 (bottom box carries 2×50 = 100).
    16 boxes → 3 layers (12) + 1 layer (4)."""
    res = run([line([box(l=24, w=20, h=10, wt=50.0, max_load_on_top=100.0, this_side_up=True)], 16)])
    assert counts(res) == [12, 4]


def test_overhang_allows_wider_layer():
    """26×21 boxes: no overhang → 1×1 per layer is all a 48×40 deck takes? No: 48/26 = 1, 40/21 = 1
    → 1 per layer (two-block can't fit either). With 2" overhang per side the area is 52×44 → 2×2."""
    spec = box(l=26, w=21, h=10, this_side_up=True)
    tight = run([line([spec], 4)])
    loose_pallet = PalletSpec(max_overhang=2.0)
    loose = run([line([spec], 4)], pallet=loose_pallet)
    assert loose.pallets[0].placements and max(p.z for p in loose.pallets[0].placements) == 0
    assert loose.pallets[0].length == 52 and loose.pallets[0].width == 42
    assert max(p.z for p in tight.pallets[0].placements) > 0  # had to stack without overhang


# ---------------------------------------------------------------- warnings / edge cases


def test_product_without_boxes_is_warned_not_fatal():
    res = run([line([box()], 2), ShipmentLine("B", "B", "Product B", 3, [])])
    assert counts(res) == [2]
    assert any("B: no box data" in w for w in res.warnings)


def test_box_too_big_is_reported_unplaced():
    res = run([line([box(l=100, w=100, h=100)], 1)])
    assert res.pallets == []
    assert len(res.unplaced) == 1
    assert any("cannot fit" in w for w in res.warnings)


def test_units_per_box_and_zero_qty():
    """12 units at 5 units/box → 3 boxes; zero-quantity lines are ignored."""
    res = run([line([box(units_per_box=5)], 12), line([box("Z")], 0)])
    assert counts(res) == [3]


@pytest.mark.parametrize("mode", MODES)
def test_deterministic(mode):
    lines = mixed_load()
    a = pack(lines, PALLET, mode).to_dict()
    b = pack(lines, PALLET, mode).to_dict()
    assert a == b


def test_freight_class_and_density():
    """Pallet 1 of the single-SKU case: 48×40×65.5 = 72.78 ft³, 1005 lb → 13.81 pcf → class 85."""
    p = run([line([box()], 100)]).pallets[0]
    assert p.cubic_feet == 72.78
    assert p.density == 13.81
    assert p.freight_class == "85"


# ---------------------------------------------------------------- tightest fit


def mixed_load():
    return [
        line([box("A", 1, 30, 20, 16, 40.0)], 14),
        line([box("B", 1, 18, 14, 12, 15.0), box("B", 2, 18, 14, 6, 6.0)], 11),
        line([box("C", 1, 22, 17, 9, 12.0, this_side_up=True)], 9),
        line([box("D", 1, 40, 12, 8, 25.0, stackable=False)], 3),
    ]


@pytest.mark.parametrize("mode", MODES)
def test_mixed_load_valid(mode):
    res = run(mixed_load(), mode)
    assert res.unplaced == []
    assert sum(counts(res)) == 14 + 22 + 9 + 3


def test_tightest_never_uses_more_pallets_than_layered_on_mixed_load():
    layered = run(mixed_load(), "layered")
    tightest = run(mixed_load(), "tightest")
    assert tightest.pallet_count <= layered.pallet_count


def test_tightest_single_sku_matches_layered():
    res = run([line([box()], 100)], "tightest")
    assert counts(res) == [96, 4]


def test_tightest_never_worse_than_layered_on_large_order():
    lines = [line([box(f"S{i}", 1, 12 + i, 10 + i % 3, 8 + i % 4, 8.0 + i)], 40) for i in range(8)]
    assert run(lines, "tightest").pallet_count <= run(lines, "layered").pallet_count


def test_large_order_is_fast():
    lines = [line([box(f"S{i}", 1, 12 + i, 10 + i % 3, 8 + i % 4, 8.0 + i)], 40) for i in range(8)]
    for mode in MODES:
        t = time.perf_counter()
        res = run(lines, mode)
        assert sum(counts(res)) == 320
        assert time.perf_counter() - t < 20, mode


# ---------------------------------------------------------------- stability rule


def _sample_order():
    """The sample box index's order: 40 fixtures (2 boxes), 30 panels, 200 clips, 60 drivers."""
    return [
        line([box("FIX-2400", 1, 50, 8, 6, 22.5), box("FIX-2400", 2, 26, 10, 4, 6, this_side_up=True)], 40),
        line([box("PANEL", 1, 50, 26, 6, 38, units_per_box=2)], 30),
        line([box("CLIP", 1, 12, 10, 8, 14, units_per_box=50)], 200),
        line([box("DRV", 1, 16, 12, 10, 24, units_per_box=20)], 60),
    ]


def test_orientations_respect_standing_ratio():
    """50×26×6 panel: may lie flat (6 high) only — on edge it would be 26 or 50 high on a 6 side.
    50×8×6 housing: flat (6 high) or on its side (8 high on a 6 side, 8 ≤ 12); never on end."""
    panel = box(l=50, w=26, h=6)
    assert {o[2] for o in panel.orientations()} == {6}
    housing = box(l=50, w=8, h=6)
    assert {o[2] for o in housing.orientations()} == {6, 8}
    cube = box(l=10, w=10, h=10)
    assert len(cube.orientations()) == 1
    # an explicit this-side-up box keeps its marked orientation, even if tall
    tall = box(l=10, w=10, h=30, this_side_up=True)
    assert {o[2] for o in tall.orientations()} == {30}


@pytest.mark.parametrize("mode", MODES)
def test_sample_order_lies_flat_with_one_inch_overhang(mode):
    """With 1" overhang per side the 50" housings and panels fit lying down, so nothing stands."""
    pallet = PalletSpec(max_overhang=1.0)
    res = run(_sample_order(), mode, pallet=pallet)  # run() also validates the stability rule
    assert res.unplaced == [] and not any("stood" in w for w in res.warnings)
    for p in res.pallets:
        for pl in p.placements:
            if not pl.spec.this_side_up:
                assert pl.dz <= 2 * min(pl.dx, pl.dy) + 1e-9, (pl.spec.sku, pl.dx, pl.dy, pl.dz)


@pytest.mark.parametrize("mode", MODES)
def test_too_long_boxes_may_stand_but_are_flagged(mode):
    """No overhang: a 50" box can't lie on a 48" deck, so standing is allowed (and warned about);
    every other box still obeys the stability rule."""
    res = run(_sample_order(), mode)
    assert res.unplaced == []
    flagged = [w for w in res.warnings if "stood on its side or end" in w]
    assert len(flagged) == 2 and any("FIX-2400 box 1" in w for w in flagged) and any("PANEL box 1" in w for w in flagged)
    for p in res.pallets:
        for pl in p.placements:
            if pl.spec.sku in ("CLIP", "DRV"):
                assert pl.dz <= 2 * min(pl.dx, pl.dy) + 1e-9


def test_validator_rejects_a_box_standing_on_end():
    from app.engine.model import BoxInstance, Placement

    b = BoxInstance(1, box(l=40, w=8, h=6))  # fits lying down, so standing on end isn't allowed
    errors = validate(PALLET, [Placement(b, 0, 0, 0, 8, 6, 40)])
    assert any("stands too tall" in e for e in errors)
    long_box = BoxInstance(2, box(l=50, w=8, h=6))  # can't lie on a 48" deck: standing is allowed
    assert validate(PALLET, [Placement(long_box, 0, 0, 0, 8, 6, 50)]) == []


# ---------------------------------------------------------------- real order: no sconce towers


def _sconce_order():
    """A real order (user-reported). The previous placement rule stacked the 21 flat sconces in
    three thin towers to 62.5" (and Layered needed 2 pallets); the user's existing program builds
    it ~49" tall. Weights are per box, from the user's screenshot."""
    return [
        line([box("CURVE", 1, 37, 9, 9, 7.0)], 2),
        line([box("PORTAL", 1, 15, 15, 4, 7.0)], 21),
        line([box("L19", 1, 15, 15, 27, 7.0), box("L19", 2, 13, 13, 16, 5.0)], 1),
        line([box("L28", 1, 21, 21, 33, 8.0), box("L28", 2, 13, 13, 16, 5.0)], 1),
    ]


@pytest.mark.parametrize("mode", MODES)
def test_sconce_order_builds_one_compact_pallet(mode):
    """Pinned: 1 pallet, 48.5" overall (43" of load on the 5.5" deck), 231 lb gross."""
    res = run(_sconce_order(), mode)
    assert res.pallet_count == 1 and res.unplaced == []
    p = res.pallets[0]
    assert (p.height, p.gross_weight) == (48.5, 231)


@pytest.mark.parametrize("mode", MODES)
def test_flat_boxes_spread_out_instead_of_towering(mode):
    """No column of the flat 15×15×4 sconces rises above the tallest other box on the pallet."""
    p = run(_sconce_order(), mode).pallets[0]
    others_top = max(pl.top for pl in p.placements if pl.spec.sku != "PORTAL")
    portal_top = max(pl.top for pl in p.placements if pl.spec.sku == "PORTAL")
    assert portal_top <= others_top + 1e-9


# ---------------------------------------------------------------- real order: heavy at the bottom


def _pendant_volo_order(**pendant):
    """A real order (user-reported): 2 Lex 28 pendants (21×21×33 box, 8 lb — mostly air — plus a
    13×13×16 light engine, 5 lb) and 8 Volo flushmounts (23×23×9, 7 lb). The old engine stood the
    light pendant boxes on the floor carrying four Volos (28 lb) each."""
    return [
        line([box("L28", 1, 21, 21, 33, 8.0, **pendant), box("L28", 2, 13, 13, 16, 5.0)], 2),
        line([box("VOLO", 1, 23, 23, 9, 7.0)], 8),
    ]


def _volos_on_pendants(p) -> int:
    pend = [q for q in p.placements if q.spec.sku == "L28" and q.spec.box_no == 1]
    return sum(
        1
        for pl in p.placements
        for q in pend
        if pl.spec.sku == "VOLO" and abs(pl.z - q.top) < 1e-6
        and pl.x < q.x + q.dx and q.x < pl.x + pl.dx and pl.y < q.y + q.dy and q.y < pl.y + pl.dy
    )


@pytest.mark.parametrize("pendant", [{}, {"max_load_on_top": 10.0}, {"stackable": False}])
def test_heavy_boxes_go_under_light_bulky_ones(pendant):
    """75" pallet (the user's): Volos 4 high on the floor (36"), pendants standing on top (33"),
    engines on the floor beside them = 74.5" on one pallet, nothing resting on a pendant — with or
    without a load limit on the pendant box (the old search needed 2 pallets with one)."""
    res = run(_pendant_volo_order(**pendant), "tightest", pallet=PalletSpec(max_total_height=75))
    assert res.pallet_count == 1
    p = res.pallets[0]
    assert p.height == 74.5
    assert not any(pl.z == 0 for pl in p.placements if pl.spec.sku == "L28" and pl.spec.box_no == 1)
    assert _volos_on_pendants(p) == 0


def test_heavy_low_never_costs_a_pallet():
    """On a 72" pallet the heavy-at-bottom layout doesn't fit one pallet (69" of load > 66.5"), so
    the estimate stays at 1 pallet with the pendants underneath — pallet count always comes first."""
    res = run(_pendant_volo_order(), "tightest")
    assert res.pallet_count == 1 and res.pallets[0].height == 62.5
