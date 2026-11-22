"""Company isolation: company A must never read or change company B's data.

Every tenant endpoint must be covered here. When you add one, add it to `TENANT_READS` (and a
write case if it writes).
"""

import pytest

from .conftest import invite_and_join, signup_verified

TENANT_READS = [
    "/api/company", "/api/pallet-types", "/api/company/members", "/api/company/invites",
    "/api/products", "/api/products/export.xlsx", "/api/products/import-template.xlsx",
    "/api/products/import-template.csv", "/api/shipments",
]


@pytest.fixture
def two_companies():
    a = signup_verified("alice@a.com", "Alpha Co")
    b = signup_verified("bob@b.com", "Beta Co")
    return a, b


@pytest.mark.parametrize("url", TENANT_READS)
def test_foreign_company_header_is_forbidden(two_companies, url):
    a, b = two_companies
    assert a.get(url).status_code == 200
    assert a.get(url, company_id=b.company_id).status_code == 403
    assert a.get(url, company_id=999999).status_code == 403


def test_missing_company_header():
    a = signup_verified("alice@a.com")
    assert a.client.get("/api/company").status_code == 400


def test_foreign_writes_are_forbidden(two_companies):
    a, b = two_companies
    bid = b.company_id
    bob_id = b.me["id"]
    assert a.put("/api/company", company_id=bid, json={"name": "Hacked"}).status_code == 403
    assert a.post("/api/company/invites", company_id=bid, json={"email": "x@x.com"}).status_code == 403
    assert a.put(f"/api/company/members/{bob_id}", company_id=bid, json={"role": "member"}).status_code == 403
    assert a.delete(f"/api/company/members/{bob_id}", company_id=bid).status_code == 403
    assert b.get("/api/company").json()["name"] == "Beta Co"


def test_guessing_ids_from_your_own_company_finds_nothing(two_companies):
    a, b = two_companies
    inv = b.post("/api/company/invites", json={"email": "carol@b.com"}).json()
    # Alice uses her own company header but targets Beta's member / invite ids.
    assert a.put(f"/api/company/members/{b.me['id']}", json={"role": "member"}).status_code == 404
    assert a.delete(f"/api/company/members/{b.me['id']}").status_code == 404
    assert a.delete(f"/api/company/invites/{inv['id']}").status_code == 404
    assert a.post(f"/api/company/invites/{inv['id']}/renew").status_code == 404
    assert [i["email"] for i in b.get("/api/company/invites").json()] == ["carol@b.com"]
    assert a.get("/api/company/invites").json() == []


def test_member_of_two_companies_sees_each_separately(two_companies):
    a, b = two_companies
    a2 = a.post("/api/companies", json={"name": "Alpha Two"}).json()
    a.refresh()
    assert {c["name"] for c in a.me["companies"]} == {"Alpha Co", "Alpha Two"}
    p1 = a.get("/api/pallet-types").json()
    p2 = a.get("/api/pallet-types", company_id=a2["id"]).json()
    assert len(p1) == len(p2) == 1 and p1[0]["id"] != p2[0]["id"]
    assert a.get("/api/company", company_id=a2["id"]).json()["name"] == "Alpha Two"


def test_member_role_cannot_administer():
    a = signup_verified("alice@a.com", "Alpha Co")
    m = invite_and_join(a, "mel@a.com", "member")
    assert m.get("/api/company").status_code == 200
    assert m.put("/api/company", json={"name": "Nope"}).status_code == 403
    assert m.post("/api/company/invites", json={"email": "z@a.com"}).status_code == 403
    assert m.get("/api/company/invites").status_code == 403
    assert m.delete(f"/api/company/members/{a.me['id']}").status_code == 403
    assert m.put(f"/api/company/members/{a.me['id']}", json={"role": "member"}).status_code == 403


def test_admin_limits_and_last_owner():
    a = signup_verified("alice@a.com", "Alpha Co")
    adm = invite_and_join(a, "ann@a.com", "admin")
    assert adm.post("/api/company/invites", json={"email": "o@a.com", "role": "owner"}).status_code == 403
    assert adm.put(f"/api/company/members/{a.me['id']}", json={"role": "member"}).status_code == 403
    assert adm.put("/api/company", json={"name": "Alpha Renamed"}).status_code == 200
    # the only owner can't demote or remove themselves
    assert a.put(f"/api/company/members/{a.me['id']}", json={"role": "admin"}).status_code == 400
    assert a.delete(f"/api/company/members/{a.me['id']}").status_code == 400
    # but a member can leave
    m = invite_and_join(a, "mel@a.com", "member")
    assert m.delete(f"/api/company/members/{m.me['id']}").status_code == 200
    assert m.get("/api/company").status_code == 403


def test_suspended_company_is_locked_out(two_companies):
    from cli import create_platform_admin

    from .conftest import PASSWORD, Session, new_client

    a, b = two_companies
    create_platform_admin("root@platform.com", PASSWORD, "Root")
    c = new_client()
    root = Session(c, c.post("/api/auth/login", json={"email": "root@platform.com", "password": PASSWORD}).json())
    companies = root.client.get("/api/admin/companies").json()
    assert {x["name"] for x in companies} == {"Alpha Co", "Beta Co"}
    assert root.client.post(f"/api/admin/companies/{a.company_id}/suspend").status_code == 200
    assert a.get("/api/company").status_code == 403
    assert b.get("/api/company").status_code == 200
    root.client.post(f"/api/admin/companies/{a.company_id}/unsuspend")
    assert a.get("/api/company").status_code == 200
    # ordinary users can't reach the platform admin API
    assert a.client.get("/api/admin/companies").status_code == 403


def test_products_and_pallet_types_are_isolated(two_companies):
    a, b = two_companies
    bp = b.post("/api/products", json={"sku": "SECRET", "boxes": [
        {"box_no": 1, "length": 1, "width": 1, "height": 1, "weight": 1}]}).json()
    bpt = b.get("/api/pallet-types").json()[0]
    # Alice in her own company can't see or touch Beta's rows by id
    assert a.get(f"/api/products/{bp['id']}").status_code == 404
    assert a.put(f"/api/products/{bp['id']}", json={"sku": "X"}).status_code == 404
    assert a.delete(f"/api/products/{bp['id']}").status_code == 404
    assert a.put(f"/api/pallet-types/{bpt['id']}", json={**{k: bpt[k] for k in (
        "name", "length", "width", "deck_height", "tare_weight", "max_total_height", "max_gross_weight",
        "max_overhang")}}).status_code == 404
    assert a.delete(f"/api/pallet-types/{bpt['id']}").status_code == 404
    assert a.post(f"/api/pallet-types/{bpt['id']}/default").status_code == 404
    assert a.get("/api/products").json()["total"] == 0
    # same SKU in Alice's company is fine and stays separate
    assert a.post("/api/products", json={"sku": "SECRET"}).status_code == 200
    assert b.get(f"/api/products/{bp['id']}").json()["box_count"] == 1
    # imports write only into the caller's company
    a.post("/api/products/import?dry_run=false", files={"file": ("x.csv", b"SKU,Product Name\nNEW,From A\n")})
    assert [p["sku"] for p in b.get("/api/products").json()["items"]] == ["SECRET"]


def test_shipments_are_isolated(two_companies):
    a, b = two_companies
    bp = b.post("/api/products", json={"sku": "SECRET", "boxes": [
        {"box_no": 1, "length": 10, "width": 10, "height": 10, "weight": 5}]}).json()
    bs = b.post("/api/shipments", json={"customer": "Beta's customer",
                                        "lines": [{"product_id": bp["id"], "quantity": 2}]}).json()
    b.post(f"/api/shipments/{bs['id']}/calculate")
    sid = bs["id"]
    assert a.get(f"/api/shipments/{sid}").status_code == 404
    assert a.put(f"/api/shipments/{sid}", json={"lines": []}).status_code == 404
    assert a.post(f"/api/shipments/{sid}/calculate").status_code == 404
    assert a.post(f"/api/shipments/{sid}/duplicate").status_code == 404
    assert a.delete(f"/api/shipments/{sid}").status_code == 404
    assert a.get(f"/api/shipments/{sid}", company_id=b.company_id).status_code == 403
    assert a.get("/api/shipments").json() == []
    # Alice can't put Beta's product on her own shipment
    r = a.post("/api/shipments", json={"lines": [{"product_id": bp["id"], "quantity": 1}]})
    assert r.status_code == 422
    # parse-lines only resolves Alice's own SKUs
    out = a.post("/api/shipments/parse-lines", files={"file": ("o.csv", b"SKU,Qty\nSECRET,1\n")}).json()
    assert out["lines"] == [] and out["unknown_skus"] == ["SECRET"]
    assert b.get(f"/api/shipments/{sid}").json()["results"]["pallet_count"] == 1
