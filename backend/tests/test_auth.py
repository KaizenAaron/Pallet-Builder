from app.config import get_settings

from .conftest import PASSWORD, new_client, signup_verified, token_from


def _signup(c, email="a@example.com", password=PASSWORD):
    return c.post(
        "/api/auth/signup", json={"name": "A", "email": email, "password": password, "company_name": "Acme"}
    )


def test_signup_verify_login_me():
    c = new_client()
    r = _signup(c)
    assert r.status_code == 200
    link = r.json()["dev_link"]
    assert link.startswith("http://app.test/verify-email?token=")

    r = c.post("/api/auth/login", json={"email": "a@example.com", "password": PASSWORD})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "email_unverified"

    r = c.post("/api/auth/verify-email", json={"token": token_from(link)})
    assert r.status_code == 200
    assert r.json()["companies"][0]["role"] == "owner"

    c2 = new_client()
    r = c2.post("/api/auth/login", json={"email": "A@Example.com ", "password": PASSWORD})
    assert r.status_code == 200
    me = c2.get("/api/auth/me").json()
    assert me["email"] == "a@example.com" and me["companies"][0]["name"] == "Acme"


def test_verification_token_single_use():
    c = new_client()
    tok = token_from(_signup(c).json()["dev_link"])
    assert c.post("/api/auth/verify-email", json={"token": tok}).status_code == 200
    assert c.post("/api/auth/verify-email", json={"token": tok}).status_code == 400


def test_wrong_password_and_unknown_email_look_the_same():
    signup_verified("a@example.com")
    c = new_client()
    r1 = c.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong-password-x"})
    r2 = c.post("/api/auth/login", json={"email": "nobody@example.com", "password": "wrong-password-x"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()


def test_no_account_enumeration_without_link_fallback(monkeypatch):
    signup_verified("a@example.com")
    monkeypatch.setattr(get_settings(), "email_link_fallback", False)
    c = new_client()
    dup = _signup(c, "a@example.com").json()
    new = _signup(c, "fresh@example.com").json()
    assert dup == new
    f1 = c.post("/api/auth/forgot-password", json={"email": "a@example.com"}).json()
    f2 = c.post("/api/auth/forgot-password", json={"email": "nobody@example.com"}).json()
    assert f1 == f2 and f1["dev_link"] is None


def test_duplicate_signup_does_not_create_company():
    s = signup_verified("a@example.com")
    _signup(new_client(), "a@example.com")
    assert len(s.refresh()["companies"]) == 1


def test_password_reset_kills_old_sessions():
    s = signup_verified("a@example.com")
    assert s.client.get("/api/auth/me").status_code == 200
    c = new_client()
    link = c.post("/api/auth/forgot-password", json={"email": "a@example.com"}).json()["dev_link"]
    tok = token_from(link)
    r = c.post("/api/auth/reset-password", json={"token": tok, "password": "a-new-password-123"})
    assert r.status_code == 200
    assert s.client.get("/api/auth/me").status_code == 401  # old session revoked
    assert c.get("/api/auth/me").status_code == 200  # reset signs you in
    assert c.post("/api/auth/reset-password", json={"token": tok, "password": "another-pass-456"}).status_code == 400
    c3 = new_client()
    assert c3.post("/api/auth/login", json={"email": "a@example.com", "password": PASSWORD}).status_code == 401
    assert c3.post("/api/auth/login", json={"email": "a@example.com", "password": "a-new-password-123"}).status_code == 200


def test_logout_all_and_change_password():
    s = signup_verified("a@example.com")
    other = new_client()
    other.post("/api/auth/login", json={"email": "a@example.com", "password": PASSWORD})
    r = s.client.put("/api/auth/me/password", json={"current_password": PASSWORD, "new_password": "new-password-789"})
    assert r.status_code == 200
    assert s.client.get("/api/auth/me").status_code == 200  # this session got a fresh cookie
    assert other.get("/api/auth/me").status_code == 401
    s.client.post("/api/auth/logout-all")
    assert s.client.get("/api/auth/me").status_code == 401


def test_weak_password_rejected():
    r = _signup(new_client(), password="short")
    assert r.status_code == 422


def test_login_rate_limited():
    c = new_client()
    codes = [
        c.post("/api/auth/login", json={"email": "x@example.com", "password": "whatever-123"}).status_code
        for _ in range(11)
    ]
    assert codes[-1] == 429 and set(codes[:10]) == {401}


def test_unauthenticated_requests_rejected():
    c = new_client()
    assert c.get("/api/auth/me").status_code == 401
    assert c.get("/api/company", headers={"X-Company-Id": "1"}).status_code == 401
