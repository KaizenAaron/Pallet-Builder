"""Row-level security on tenant tables (Postgres only; no-op on SQLite).

Revision ID: 0002
Revises: 0001
"""

from alembic import op

from app.rls import apply_rls

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    apply_rls(op.get_bind())


def downgrade() -> None:
    pass
