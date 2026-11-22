from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models import Invite

from .conftest import PASSWORD, Session, new_client, signup_verified, token_from


def _invite(admin, email, role="member"):
    r = admin.post("/api/company/invites", json={"email": email, "role": role})
    assert r.status_code == 200, r.text
    return r.json()


def test_new_user_accepts_and_is_verified():
    a = signup_verified("alice@a.com", "Alpha Co")
    inv = _invite(a, "New@A.com")
    tok = token_from(inv["link"])
    c = new_client()
    view = c.get(f"/api/invites/{tok}").json()
    assert view == {
        "company_name": "Alpha Co", "email": "new@a.com", "role": "member",
        "account_exists": False, "signed_in_as": None,
    }
    r = c.post(f"/api/invites/{tok}/accept", json={"name": "Newbie", "password": PASSWORD})
    assert r.status_code == 200
    assert r.json()["me"]["companies"][0]["role"] == "member"
    # verified: can sign in elsewhere
    assert new_client().post("/api/auth/login", json={"email": "new@a.com", "password": PASSWORD}).status_code == 200
    # single use
    assert new_client().get(f"/api/invites/{tok}").status_code == 404


def test_existing_user_must_sign_in_then_joins():
    a = signup_verified("alice@a.com", "Alpha Co")
    b = signup_verified("bob@b.com", "Beta Co")
    tok = token_from(_invite(a, "bob@b.com", "admin")["link"])
    anon = new_client()
    r = anon.post(f"/api/invites/{tok}/accept", json={})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "sign_in_required"
    r = b.client.post(f"/api/invites/{tok}/accept", json={})
    assert r.status_code == 200
    roles = {c["name"]: c["role"] for c in b.refresh()["companies"]}
    assert roles == {"Alpha Co": "admin", "Beta Co": "owner"}


def test_signed_in_as_someone_else_is_rejected():
    a = signup_verified("alice@a.com", "Alpha Co")
    b = signup_verified("bob@b.com", "Beta Co")
    tok = token_from(_invite(a, "carol@c.com")["link"])
    assert b.client.post(f"/api/invites/{tok}/accept", json={}).status_code == 403


def test_revoked_and_expired_invites_fail():
    a = signup_verified("alice@a.com", "Alpha Co")
    inv = _invite(a, "x@a.com")
    a.delete(f"/api/company/invites/{inv['id']}")
    assert new_client().get(f"/api/invites/{token_from(inv['link'])}").status_code == 404

    inv2 = _invite(a, "y@a.com")
    with SessionLocal() as db:
        row = db.get(Invite, inv2["id"])
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    tok2 = token_from(inv2["link"])
    assert new_client().post(f"/api/invites/{tok2}/accept", json={"name": "Y", "password": PASSWORD}).status_code == 404
    listed = {i["email"]: i["status"] for i in a.get("/api/company/invites").json()}
    assert listed == {"y@a.com": "expired"}
    # renewing issues a fresh working link (the old one stays dead)
    renewed = a.post(f"/api/company/invites/{inv2['id']}/renew").json()
    assert renewed["status"] == "pending"
    assert new_client().get(f"/api/invites/{tok2}").status_code == 404
    assert new_client().get(f"/api/invites/{token_from(renewed['link'])}").status_code == 200


def test_cannot_invite_existing_member_or_higher_role():
    a = signup_verified("alice@a.com", "Alpha Co")
    assert a.post("/api/company/invites", json={"email": "alice@a.com"}).status_code == 409
    c = new_client()
    tok = token_from(_invite(a, "ann@a.com", "admin")["link"])
    adm_me = c.post(f"/api/invites/{tok}/accept", json={"name": "Ann", "password": PASSWORD}).json()
    adm = Session(c, adm_me["me"])
    assert adm.post("/api/company/invites", json={"email": "o@a.com", "role": "owner"}).status_code == 403
