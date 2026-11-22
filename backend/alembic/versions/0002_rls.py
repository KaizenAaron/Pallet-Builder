"""Create any missing tables, then row-level security on tenant tables (RLS is Postgres only).

Databases created in phase 1 were stamped 0001 before any models existed, so the 0001 baseline
created nothing there; this revision creates the phase 3 tables before securing them.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

from app import models  # noqa: F401
from app.db import Base
from app.rls import apply_rls

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)
    apply_rls(bind)


def downgrade() -> None:
    pass
