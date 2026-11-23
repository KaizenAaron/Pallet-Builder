"""Automatic pallet selection: pallet_types.auto_select, shipments.pallet_selection,
shipment_pallets.pallet_spec.

Existing shipments become `fixed` (they were calculated on one chosen pallet type), so nothing
changes for them silently; new shipments default to `auto` (model default).

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

from app import models  # noqa: F401
from app.db import Base
from app.rls import apply_rls

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)  # never assume earlier tables exist
    if not _has_column(bind, "pallet_types", "auto_select"):
        op.add_column("pallet_types", sa.Column("auto_select", sa.Boolean(), nullable=False, server_default=sa.true()))
    if not _has_column(bind, "shipments", "pallet_selection"):
        op.add_column(
            "shipments", sa.Column("pallet_selection", sa.String(5), nullable=False, server_default="fixed")
        )
    if not _has_column(bind, "shipment_pallets", "pallet_spec"):
        op.add_column("shipment_pallets", sa.Column("pallet_spec", sa.JSON(), nullable=True))
    apply_rls(bind)


def downgrade() -> None:
    pass
