import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ["EMAIL_LINK_FALLBACK"] = "true"
os.environ["SMTP_HOST"] = ""  # never send real email from tests
os.environ["FRONTEND_BASE_URL"] = "http://app.test"

from urllib.parse import parse_qs, urlparse  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import ratelimit  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.rls import apply_rls, reset_role_cache  # noqa: E402

PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        apply_rls(conn)
    reset_role_cache()
    ratelimit.reset()
    yield


def new_client() -> TestClient:
    return TestClient(app)


def token_from(link: str) -> str:
    u = urlparse(link)
    q = parse_qs(u.query)
    return q["token"][0] if "token" in q else u.path.rsplit("/", 1)[-1]


class Session:
    """A signed-in browser: its own cookie jar plus an active company."""

    def __init__(self, client: TestClient, me: dict):
        self.client = client
        self.me = me
        self.company_id = me["companies"][0]["id"] if me["companies"] else None

    def h(self, company_id=None):
        cid = company_id if company_id is not None else self.company_id
        return {"X-Company-Id": str(cid)} if cid is not None else {}

    def get(self, url, company_id=None, **kw):
        return self.client.get(url, headers=self.h(company_id), **kw)

    def post(self, url, company_id=None, **kw):
        return self.client.post(url, headers=self.h(company_id), **kw)

    def put(self, url, company_id=None, **kw):
        return self.client.put(url, headers=self.h(company_id), **kw)

    def delete(self, url, company_id=None, **kw):
        return self.client.delete(url, headers=self.h(company_id), **kw)

    def refresh(self):
        self.me = self.client.get("/api/auth/me").json()
        return self.me


def signup_verified(email: str, company: str = "Acme", name: str = "Test User") -> Session:
    c = new_client()
    r = c.post(
        "/api/auth/signup", json={"name": name, "email": email, "password": PASSWORD, "company_name": company}
    )
    assert r.status_code == 200, r.text
    r = c.post("/api/auth/verify-email", json={"token": token_from(r.json()["dev_link"])})
    assert r.status_code == 200, r.text
    return Session(c, r.json())


def invite_and_join(admin: Session, email: str, role: str = "member", name: str = "Invitee") -> Session:
    r = admin.post("/api/company/invites", json={"email": email, "role": role})
    assert r.status_code == 200, r.text
    c = new_client()
    r = c.post(f"/api/invites/{token_from(r.json()['link'])}/accept", json={"name": name, "password": PASSWORD})
    assert r.status_code == 200, r.text
    s = Session(c, r.json()["me"])
    s.company_id = r.json()["company_id"]
    return s
