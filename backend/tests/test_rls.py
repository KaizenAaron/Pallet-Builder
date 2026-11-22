"""Row-level security (Postgres only): an unfiltered query still can't see another company."""

import pytest
from sqlalchemy import text

from app.db import SessionLocal, engine, system_session
from app.rls import bind_company

from .conftest import signup_verified

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="RLS needs Postgres")


def test_unfiltered_query_only_sees_bound_company():
    a = signup_verified("alice@a.com", "Alpha Co")
    b = signup_verified("bob@b.com", "Beta Co")
    with SessionLocal() as db:
        bind_company(db, a.company_id)
        rows = db.execute(text("SELECT company_id FROM pallet_types")).scalars().all()
        assert rows == [a.company_id]
        db.commit()  # the binding survives into the next transaction
        rows = db.execute(text("SELECT company_id FROM pallet_types")).scalars().all()
        assert rows == [a.company_id]
    with SessionLocal() as db:
        assert db.execute(text("SELECT count(*) FROM pallet_types")).scalar() == 0
    with system_session() as db:
        assert db.execute(text("SELECT count(*) FROM pallet_types")).scalar() == 2
    assert b.company_id != a.company_id


def test_cannot_insert_rows_for_another_company():
    from sqlalchemy.exc import DBAPIError

    a = signup_verified("alice@a.com", "Alpha Co")
    b = signup_verified("bob@b.com", "Beta Co")
    with SessionLocal() as db:
        bind_company(db, a.company_id)
        with pytest.raises(DBAPIError):
            db.execute(
                text("INSERT INTO pallet_types (company_id, name, length, width, deck_height, tare_weight, "
                     "max_total_height, max_gross_weight, max_overhang, is_default, created_at) "
                     "VALUES (:c, 'evil', 1, 1, 1, 1, 1, 1, 0, false, now())"),
                {"c": b.company_id},
            )
