"""Company isolation: company A must never read or change company B's data.

Every tenant endpoint must be covered here. When you add one, add it to `TENANT_READS` (and a
write case if it writes).
"""

import pytest

from .conftest import invite_and_join, signup_verified

TENANT_READS = ["/api/company", "/api/pallet-types", "/api/company/members", "/api/company/invites"]


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
