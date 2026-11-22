"""Shipments through the API. Golden numbers match tests/engine/test_engine.py exactly, proving the
API stores the engine's numbers unchanged."""

import pytest

from .conftest import invite_and_join, signup_verified

SMALL = {"box_no": 1, "length": 12, "width": 10, "height": 10, "weight": 10}


def product(s, sku, *boxes):
    r = s.post("/api/products", json={"sku": sku, "name": f"Product {sku}", "boxes": list(boxes)})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def shipment(s, lines, **kw):
    r = s.post("/api/shipments", json={"lines": [{"product_id": p, "quantity": q} for p, q in lines], **kw})
    assert r.status_code == 200, r.text
    return r.json()


def calc(s, sid):
    r = s.post(f"/api/shipments/{sid}/calculate")
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def acme():
    return signup_verified("alice@a.com", "Alpha Co")


def test_golden_single_sku(acme):
    pid = product(acme, "A", SMALL)
    sh = shipment(acme, [(pid, 100)], customer="Cust", reference="SO123", ship_date="2026-12-01", notes="Dock 4")
    assert sh["number"] == "SH-0001" and sh["status"] == "draft" and sh["results"] is None
    out = calc(acme, sh["id"])
    r = out["results"]
    assert out["status"] == "calculated" and out["stale"] is False
    assert r["pallet_count"] == 2 and r["total_gross_weight"] == 1090
    p1, p2 = r["pallets"]
    assert (p1["length"], p1["width"], p1["height"], p1["gross_weight"], p1["freight_class"]) == (48, 40, 65.5, 1005, "85")
    assert (p2["height"], p2["gross_weight"]) == (15.5, 85)
    assert len(p1["layout"]) == 96 and {"x", "y", "z", "dx", "dy", "dz", "sku"} <= set(p1["layout"][0])
    assert r["pallet_spec"]["name"] == "48 × 40 GMA"
    assert (out["customer"], out["reference"], out["ship_date"], out["notes"]) == ("Cust", "SO123", "2026-12-01", "Dock 4")


def test_golden_multi_box(acme):
    pid = product(acme, "FIX", {"box_no": 1, "length": 48, "width": 20, "height": 10, "weight": 50},
                  {"box_no": 2, "length": 24, "width": 20, "height": 8, "weight": 20})
    r = calc(acme, shipment(acme, [(pid, 4)])["id"])["results"]
    assert r["pallet_count"] == 1
    p = r["pallets"][0]
    assert (p["height"], p["gross_weight"]) == (33.5, 325)
    assert sorted((b["box_no"], b["count"]) for b in p["box_summary"]) == [(1, 4), (2, 4)]


def test_missing_boxes_warn_and_too_big_unplaced(acme):
    a = product(acme, "A", SMALL)
    nobox = product(acme, "NOBOX")
    huge = product(acme, "HUGE", {"box_no": 1, "length": 100, "width": 100, "height": 100, "weight": 5})
    out = calc(acme, shipment(acme, [(a, 2), (nobox, 3), (huge, 1)])["id"])
    lines = {ln["sku"]: ln for ln in out["lines"]}
    assert lines["NOBOX"]["box_count"] == 0 and lines["A"]["box_count"] == 1
    r = out["results"]
    assert r["pallet_count"] == 1
    assert any("NOBOX" in w for w in r["warnings"]) and any("HUGE" in w for w in r["warnings"])
    assert r["unplaced"] == [{"sku": "HUGE", "box_no": 1, "box_name": "Box 1"}]


def test_stale_after_any_input_change(acme):
    pid = product(acme, "A", SMALL)
    sh = shipment(acme, [(pid, 10)])
    calc(acme, sh["id"])
    get = lambda: acme.get(f"/api/shipments/{sh['id']}").json()  # noqa: E731
    assert get()["stale"] is False

    # box data edited
    acme.put(f"/api/products/{pid}", json={"sku": "A", "boxes": [{**SMALL, "weight": 11}]})
    assert get()["stale"] is True
    calc(acme, sh["id"])
    assert get()["stale"] is False

    # pallet type edited
    pt = acme.get("/api/pallet-types").json()[0]
    acme.put(f"/api/pallet-types/{pt['id']}", json={**{k: pt[k] for k in (
        "name", "length", "width", "deck_height", "tare_weight", "max_total_height", "max_gross_weight",
        "max_overhang")}, "tare_weight": 50})
    assert get()["stale"] is True
    calc(acme, sh["id"])

    # lines or mode edited (results are kept but flagged)
    body = {"lines": [{"product_id": pid, "quantity": 11}]}
    out = acme.put(f"/api/shipments/{sh['id']}", json=body).json()
    assert out["stale"] is True and out["results"]["pallet_count"] == 1
    calc(acme, sh["id"])
    out = acme.put(f"/api/shipments/{sh['id']}", json={**body, "packing_mode": "tightest"}).json()
    assert out["stale"] is True
    out = calc(acme, sh["id"])
    assert out["stale"] is False and out["calculated_mode"] == "tightest"
    # listing reflects staleness too
    acme.put(f"/api/products/{pid}", json={"sku": "A", "boxes": [{**SMALL, "weight": 12}]})
    assert acme.get("/api/shipments").json()[0]["stale"] is True


def test_deleting_product_or_pallet_type_keeps_old_shipments(acme):
    pid = product(acme, "A", SMALL)
    extra = acme.post("/api/pallet-types", json={
        "name": "Big", "length": 48, "width": 48, "deck_height": 6, "tare_weight": 50,
        "max_total_height": 80, "max_gross_weight": 3000}).json()
    sh = shipment(acme, [(pid, 10)], pallet_type_id=extra["id"])
    calc(acme, sh["id"])
    acme.delete(f"/api/pallet-types/{extra['id']}")
    out = acme.get(f"/api/shipments/{sh['id']}").json()
    assert out["pallet_type_id"] is None and out["stale"] is False
    assert out["results"]["pallet_spec"]["name"] == "Big"
    acme.delete(f"/api/products/{pid}")
    out = acme.get(f"/api/shipments/{sh['id']}").json()
    assert out["lines"][0]["sku"] == "A" and out["lines"][0]["product_deleted"] is True
    assert out["results"]["pallet_count"] == 1  # snapshot survives; now stale (product gone)
    assert out["stale"] is True


def test_validation(acme):
    other = signup_verified("bob@b.com", "Beta Co")
    foreign_product = product(other, "B", SMALL)
    foreign_pt = other.get("/api/pallet-types").json()[0]["id"]
    pid = product(acme, "A", SMALL)
    assert acme.post("/api/shipments", json={"lines": [{"product_id": foreign_product, "quantity": 1}]}).status_code == 422
    assert acme.post("/api/shipments", json={"pallet_type_id": foreign_pt, "lines": []}).status_code == 422
    assert acme.post("/api/shipments", json={"lines": [{"product_id": pid, "quantity": 0}]}).status_code == 422
    assert acme.post("/api/shipments", json={"packing_mode": "random"}).status_code == 422
    empty = shipment(acme, [])
    assert acme.post(f"/api/shipments/{empty['id']}/calculate").status_code == 422
    big = shipment(acme, [(pid, 20000)])
    r = acme.post(f"/api/shipments/{big['id']}/calculate")
    assert r.status_code == 422 and "too many" in r.json()["detail"]


def test_numbering_duplicate_delete_and_search(acme):
    other = signup_verified("bob@b.com", "Beta Co")
    pid = product(acme, "A", SMALL)
    s1 = shipment(acme, [(pid, 5)], customer="Acme Lighting")
    s2 = shipment(acme, [(pid, 7)], reference="SO-77")
    assert (s1["number"], s2["number"]) == ("SH-0001", "SH-0002")
    assert shipment(other, [])["number"] == "SH-0001"  # per company
    dup = acme.post(f"/api/shipments/{s1['id']}/duplicate").json()
    assert dup["number"] == "SH-0003" and dup["customer"] == "Acme Lighting" and dup["lines"][0]["quantity"] == 5
    assert dup["status"] == "draft"
    assert [s["number"] for s in acme.get("/api/shipments?q=lighting").json()] == ["SH-0003", "SH-0001"]
    assert [s["number"] for s in acme.get("/api/shipments?q=so-77").json()] == ["SH-0002"]
    assert [s["number"] for s in acme.get("/api/shipments?q=sh-0002").json()] == ["SH-0002"]
    assert acme.delete(f"/api/shipments/{s2['id']}").status_code == 200
    assert acme.get(f"/api/shipments/{s2['id']}").status_code == 404


def test_parse_lines(acme):
    product(acme, "FIX-1", SMALL)
    product(acme, "12345", SMALL)
    data = b"Internal Reference,Description,Quantity\nFIX-1,x,4\nfix-1,again,6\nNOPE,y,2\n12345,z,1\nFIX-1,bad,abc\n"
    r = acme.post("/api/shipments/parse-lines", files={"file": ("order.csv", data)})
    assert r.status_code == 200, r.text
    out = r.json()
    assert sorted((ln["sku"], ln["quantity"]) for ln in out["lines"]) == [("12345", 1), ("FIX-1", 10)]
    assert out["unknown_skus"] == ["NOPE"]
    assert [e["row"] for e in out["errors"]] == [6]
    assert acme.get("/api/shipments").json() == []  # nothing written
    bad = acme.post("/api/shipments/parse-lines", files={"file": ("x.csv", b"SKU,Name\nA,b\n")})
    assert bad.status_code == 400


def test_members_can_use_shipments(acme):
    m = invite_and_join(acme, "mel@a.com")
    pid = product(acme, "A", SMALL)
    sh = shipment(m, [(pid, 3)])
    assert calc(m, sh["id"])["results"]["pallet_count"] == 1
    assert m.delete(f"/api/shipments/{sh['id']}").status_code == 200


def test_tightest_never_more_pallets_than_layered_via_api(acme):
    a = product(acme, "A", {"box_no": 1, "length": 30, "width": 20, "height": 16, "weight": 40})
    b = product(acme, "B", {"box_no": 1, "length": 18, "width": 14, "height": 12, "weight": 15},
                {"box_no": 2, "length": 18, "width": 14, "height": 6, "weight": 6})
    c = product(acme, "C", {"box_no": 1, "length": 22, "width": 17, "height": 9, "weight": 12, "this_side_up": True})
    sh = shipment(acme, [(a, 14), (b, 11), (c, 9)])
    layered = calc(acme, sh["id"])["results"]["pallet_count"]
    acme.put(f"/api/shipments/{sh['id']}", json={"packing_mode": "tightest", "lines": [
        {"product_id": a, "quantity": 14}, {"product_id": b, "quantity": 11}, {"product_id": c, "quantity": 9}]})
    tightest = calc(acme, sh["id"])["results"]["pallet_count"]
    assert tightest <= layered
