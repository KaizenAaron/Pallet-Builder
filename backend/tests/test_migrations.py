"""Alembic upgrades work on databases created by earlier versions of the app.

Regression: a database stamped 0001 back in phase 1 (when the create-all baseline had no
models to create) must still get every table and RLS policy from `alembic upgrade head`.
"""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.db import engine
from app.models import tenant_tables

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="needs a scratch Postgres database")

SCRATCH = "pb_migration_check"


@pytest.fixture
def scratch_url():
    admin = create_engine(engine.url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH}"))
        c.execute(text(f"CREATE DATABASE {SCRATCH}"))
    yield engine.url.set(database=SCRATCH)
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)"))
    admin.dispose()


def _upgrade(url, monkeypatch):
    import app.db as appdb

    eng = create_engine(url)
    monkeypatch.setattr(appdb, "engine", eng)  # alembic/env.py connects through app.db.engine
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    return eng


def test_upgrade_from_phase1_database(scratch_url, monkeypatch):
    eng = create_engine(scratch_url)
    with eng.begin() as c:  # what phase 1 left behind: an empty schema stamped 0001
        c.execute(text("CREATE TABLE alembic_version (version_num varchar(32) PRIMARY KEY)"))
        c.execute(text("INSERT INTO alembic_version VALUES ('0001')"))
    eng.dispose()
    eng = _upgrade(scratch_url, monkeypatch)
    tables = set(inspect(eng).get_table_names())
    assert {"users", "companies", "memberships", "invites", "auth_tokens", *tenant_tables()} <= tables
    with eng.connect() as c:
        forced = c.execute(text("SELECT relforcerowsecurity FROM pg_class WHERE relname = 'pallet_types'")).scalar()
        assert forced is True
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0002"
    eng.dispose()


def test_upgrade_fresh_database_twice(scratch_url, monkeypatch):
    _upgrade(scratch_url, monkeypatch).dispose()
    eng = _upgrade(scratch_url, monkeypatch)  # idempotent
    assert set(tenant_tables()) <= set(inspect(eng).get_table_names())
    eng.dispose()
