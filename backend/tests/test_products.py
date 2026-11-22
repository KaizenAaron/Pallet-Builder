from .conftest import invite_and_join, signup_verified

BOX = {"box_no": 1, "name": "Housing", "length": 50, "width": 8, "height": 6, "weight": 22.5}


def test_create_with_boxes_and_read_back():
    a = signup_verified("alice@a.com", "Alpha Co")
    r = a.post("/api/products", json={
        "sku": " FIX-2400 ", "name": "24 in Fixture",
        "boxes": [BOX, {"box_no": 2, "length": 26, "width": 10, "height": 4, "weight": 6, "this_side_up": True}],
    })
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["sku"] == "FIX-2400" and p["box_count"] == 2 and p["unit_weight"] == 28.5
    assert p["boxes"][1]["name"] == "Box 2" and p["boxes"][1]["this_side_up"] is True
    assert a.get(f"/api/products/{p['id']}").json() == p


def test_sku_unique_per_company_case_insensitive_but_not_across_companies():
    a = signup_verified("alice@a.com", "Alpha Co")
    b = signup_verified("bob@b.com", "Beta Co")
    assert a.post("/api/products", json={"sku": "ABC"}).status_code == 200
    assert a.post("/api/products", json={"sku": "abc"}).status_code == 409
    assert b.post("/api/products", json={"sku": "ABC"}).status_code == 200


def test_update_replaces_boxes_and_renames():
    a = signup_verified("alice@a.com")
    p = a.post("/api/products", json={"sku": "A", "boxes": [BOX, {**BOX, "box_no": 2}]}).json()
    r = a.put(f"/api/products/{p['id']}", json={"sku": "A2", "name": "Renamed", "boxes": [{**BOX, "box_no": 2, "weight": 10}]})
    assert r.status_code == 200
    out = r.json()
    assert out["sku"] == "A2" and [b["box_no"] for b in out["boxes"]] == [2] and out["boxes"][0]["weight"] == 10
    # omitting boxes leaves them alone
    out = a.put(f"/api/products/{p['id']}", json={"sku": "A2", "name": "Again"}).json()
    assert out["box_count"] == 1


def test_validation():
    a = signup_verified("alice@a.com")
    assert a.post("/api/products", json={"sku": "  "}).status_code == 422
    assert a.post("/api/products", json={"sku": "A", "boxes": [{**BOX, "length": 0}]}).status_code == 422
    assert a.post("/api/products", json={"sku": "A", "boxes": [BOX, BOX]}).status_code == 422


def test_list_search_and_missing_filter():
    a = signup_verified("alice@a.com")
    a.post("/api/products", json={"sku": "FIX-1", "name": "Fixture", "boxes": [BOX]})
    a.post("/api/products", json={"sku": "CLIP-1", "name": "Clip"})
    all_ = a.get("/api/products").json()
    assert all_["total"] == 2 and all_["missing_boxes"] == 1
    assert [p["sku"] for p in a.get("/api/products?q=fix").json()["items"]] == ["FIX-1"]
    assert [p["sku"] for p in a.get("/api/products?missing_boxes=true").json()["items"]] == ["CLIP-1"]


def test_members_can_edit_products_but_not_import():
    a = signup_verified("alice@a.com")
    m = invite_and_join(a, "mel@a.com", "member")
    p = m.post("/api/products", json={"sku": "M1", "boxes": [BOX]})
    assert p.status_code == 200
    assert m.delete(f"/api/products/{p.json()['id']}").status_code == 200
    r = m.post("/api/products/import", files={"file": ("x.csv", b"SKU\nA\n", "text/csv")})
    assert r.status_code == 403
