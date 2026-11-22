from .conftest import invite_and_join, signup_verified

PT = {"name": "48 x 48", "length": 48, "width": 48, "deck_height": 6, "tare_weight": 50,
      "max_total_height": 80, "max_gross_weight": 3000, "max_overhang": 1}


def test_default_seeded_and_crud():
    a = signup_verified("alice@a.com")
    seeded = a.get("/api/pallet-types").json()
    assert len(seeded) == 1 and seeded[0]["is_default"] and (seeded[0]["length"], seeded[0]["width"]) == (48, 40)
    new = a.post("/api/pallet-types", json=PT).json()
    assert new["is_default"] is False
    lst = a.post(f"/api/pallet-types/{new['id']}/default").json()
    assert [p["is_default"] for p in lst if p["id"] == new["id"]] == [True]
    assert sum(p["is_default"] for p in lst) == 1
    upd = a.put(f"/api/pallet-types/{new['id']}", json={**PT, "name": "Square"}).json()
    assert upd["name"] == "Square"
    # deleting the default promotes another; the last one can't be deleted
    lst = a.delete(f"/api/pallet-types/{new['id']}").json()
    assert len(lst) == 1 and lst[0]["is_default"]
    assert a.delete(f"/api/pallet-types/{lst[0]['id']}").status_code == 400


def test_validation_rules():
    a = signup_verified("alice@a.com")
    assert a.post("/api/pallet-types", json={**PT, "max_total_height": 5}).status_code == 422
    assert a.post("/api/pallet-types", json={**PT, "max_gross_weight": 40}).status_code == 422
    assert a.post("/api/pallet-types", json={**PT, "max_overhang": 20}).status_code == 422


def test_members_read_only():
    a = signup_verified("alice@a.com")
    m = invite_and_join(a, "mel@a.com")
    pid = m.get("/api/pallet-types").json()[0]["id"]
    assert m.post("/api/pallet-types", json=PT).status_code == 403
    assert m.put(f"/api/pallet-types/{pid}", json=PT).status_code == 403
    assert m.delete(f"/api/pallet-types/{pid}").status_code == 403
