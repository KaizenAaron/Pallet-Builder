"""Postgres row-level security: the second, independent wall between companies.

Application code always filters by company (`tenancy.scoped`). RLS makes a missed filter return
nothing instead of another company's rows:

- every tenant table (models with `TenantMixin`) has ENABLE + FORCE ROW LEVEL SECURITY and a
  policy that only admits rows whose `company_id` equals the transaction's `app.company_id`
  setting, unless `app.bypass_rls` is 'on' (system contexts: CLI, platform-admin tooling);
- Postgres superusers ignore RLS, and the local Docker database user *is* a superuser, so ORM
  sessions also `SET LOCAL ROLE pallet_app` — a NOLOGIN role without BYPASSRLS — whenever the
  connecting user is allowed to.

`apply_rls()` is idempotent; Alembic revisions that add tenant tables call it again.
SQLite has no RLS: everything here is a no-op there.
"""

from __future__ import annotations

from sqlalchemy import event, inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

APP_ROLE = "pallet_app"
POLICY = "tenant_isolation"


def is_postgres(bind) -> bool:
    return bind.dialect.name == "postgresql"


def apply_rls(conn: Connection) -> None:
    if not is_postgres(conn):
        return
    from .models import tenant_tables

    cond = (
        "(company_id = NULLIF(current_setting('app.company_id', true), '')::integer "
        "OR current_setting('app.bypass_rls', true) = 'on')"
    )
    existing = set(inspect(conn).get_table_names())
    for table in tenant_tables():
        if table not in existing:  # created later; its own migration calls apply_rls() again
            continue
        conn.execute(text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
        conn.execute(text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
        conn.execute(text(f'DROP POLICY IF EXISTS {POLICY} ON "{table}"'))
        conn.execute(text(f'CREATE POLICY {POLICY} ON "{table}" USING {cond} WITH CHECK {cond}'))

    # The restricted role is best-effort: managed hosts may not allow CREATE ROLE, in which case
    # the (non-superuser) table owner is already subject to the FORCEd policies.
    steps = [
        f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') "
        f"THEN CREATE ROLE {APP_ROLE} NOLOGIN; END IF; END $$",
        f"GRANT {APP_ROLE} TO CURRENT_USER",
        f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}",
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}",
    ]
    for sql in steps:
        sp = conn.begin_nested()
        try:
            conn.execute(text(sql))
            sp.commit()
        except Exception:
            sp.rollback()


_role_usable: dict[str, bool] = {}


def _can_use_app_role(conn: Connection) -> bool:
    key = str(conn.engine.url)
    if key not in _role_usable:
        row = conn.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :r) "
                "AND pg_has_role(current_user, :r, 'MEMBER')"
            ),
            {"r": APP_ROLE},
        ).scalar()
        _role_usable[key] = bool(row)
    return _role_usable[key]


def reset_role_cache() -> None:
    _role_usable.clear()


def _apply_context(conn: Connection, info: dict) -> None:
    conn.execute(
        text("SELECT set_config('app.company_id', :c, true), set_config('app.bypass_rls', :b, true)"),
        {"c": str(info.get("company_id") or ""), "b": "on" if info.get("bypass_rls") else "off"},
    )


@event.listens_for(Session, "after_begin")
def _on_begin(session: Session, transaction, connection: Connection) -> None:
    if not is_postgres(connection):
        return
    if _can_use_app_role(connection):
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
    _apply_context(connection, session.info)


def bind_company(db: Session, company_id: int | None) -> None:
    """Scope this session to one company — now (if a transaction is open) and for every later
    transaction on the session."""
    db.info["company_id"] = company_id
    if db.in_transaction():
        conn = db.connection()
        if is_postgres(conn):
            _apply_context(conn, db.info)


def bypass(db: Session) -> Session:
    """Mark a session as a system context that may see every company's rows."""
    db.info["bypass_rls"] = True
    if db.in_transaction():
        conn = db.connection()
        if is_postgres(conn):
            _apply_context(conn, db.info)
    return db
