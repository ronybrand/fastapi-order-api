"""customers: tax_id/passport_number unique only among active (non soft-deleted) rows

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-14

A plain UNIQUE constraint also covers soft-deleted rows, so a deleted customer kept its tax_id
reserved and re-registering it failed on INSERT (unhandled IntegrityError). The service-level
uniqueness check only looks at active rows, so the database must agree: partial unique indexes
WHERE deleted_at IS NULL (the same name, so the IntegrityError handler can map the constraint).

downgrade() restores the full-table constraints and FAILS if an active and a deleted customer now
share a tax_id/passport_number - resolve those rows first; that failure is the safe outcome.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_customers_tax_id", "customers", type_="unique")
    op.drop_constraint("uq_customers_passport_number", "customers", type_="unique")
    op.create_index(
        "uq_customers_tax_id",
        "customers",
        ["tax_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_customers_passport_number",
        "customers",
        ["passport_number"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_customers_passport_number", table_name="customers")
    op.drop_index("uq_customers_tax_id", table_name="customers")
    op.create_unique_constraint("uq_customers_passport_number", "customers", ["passport_number"])
    op.create_unique_constraint("uq_customers_tax_id", "customers", ["tax_id"])
