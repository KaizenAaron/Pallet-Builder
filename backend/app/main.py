from fastapi import FastAPI

from . import models  # noqa: F401  (register tables)
from . import rls  # noqa: F401  (register session hooks)
from .api import admin, auth, companies, invites, members
from .db import Base, engine

app = FastAPI(title="Pallet Builder", docs_url="/api/docs", openapi_url="/api/openapi.json")

for r in (auth.router, companies.router, members.router, invites.router, admin.router):
    app.include_router(r)


@app.on_event("startup")
def _startup() -> None:
    # Creates *missing* tables only; schema changes (and RLS policies) ship as Alembic revisions.
    Base.metadata.create_all(bind=engine)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
