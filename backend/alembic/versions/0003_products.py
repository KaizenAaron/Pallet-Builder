"""Products and the box index (tenant tables with row-level security).

Revision ID: 0003
Revises: 0002
"""

from alembic import op

from app import models  # noqa: F401
from app.db import Base
from app.rls import apply_rls

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)
    apply_rls(bind)


def downgrade() -> None:
    pass
