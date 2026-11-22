from fastapi import FastAPI

from .db import Base, engine

app = FastAPI(title="Pallet Builder", docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.on_event("startup")
def _startup() -> None:
    # Creates *missing* tables only; schema changes ship as Alembic revisions.
    Base.metadata.create_all(bind=engine)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
