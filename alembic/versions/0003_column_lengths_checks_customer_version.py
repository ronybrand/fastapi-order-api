"""customers/orders: bounded text columns, item check constraints, customers.version

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-14

* Text columns were unbounded `VARCHAR`: nothing at the database stopped a value the request schemas
  already refuse (name 200, e-mail 320, tax_id 20, passport 9, audit actor 200). Now the database agrees.
* `items.quantity > 0` and `items.unit_price > 0` are checked by the database too (defense in depth).
* `customers.version` (optimistic lock, like `orders.version`): existing rows start at 1.

upgrade() FAILS, leaving the schema untouched (Postgres DDL is transactional), if any existing value is
longer than the new limit or an item has a non-positive quantity/price - fix those rows first; that
failure is the safe outcome. downgrade() restores the unbounded columns and drops the constraints.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LENGTHS = {
    "customers": {
        "name": (200, False),
        "tax_id": (20, False),
        "passport_number": (9, True),
        "email": (320, False),
        "created_by": (200, False),
        "updated_by": (200, False),
        "deleted_by": (200, True),
    },
    "orders": {
        "created_by": (200, False),
        "updated_by": (200, False),
        "deleted_by": (200, True),
    },
}


def upgrade() -> None:
    for table, columns in _LENGTHS.items():
        for column, (length, nullable) in columns.items():
            op.alter_column(
                table,
                column,
                existing_type=sa.String(),
                type_=sa.String(length=length),
                existing_nullable=nullable,
            )

    op.add_column("customers", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))

    op.create_check_constraint("ck_items_quantity_positive", "items", "quantity > 0")
    op.create_check_constraint("ck_items_unit_price_positive", "items", "unit_price > 0")


def downgrade() -> None:
    op.drop_constraint("ck_items_unit_price_positive", "items", type_="check")
    op.drop_constraint("ck_items_quantity_positive", "items", type_="check")

    op.drop_column("customers", "version")

    for table, columns in _LENGTHS.items():
        for column, (length, nullable) in columns.items():
            op.alter_column(
                table,
                column,
                existing_type=sa.String(length=length),
                type_=sa.String(),
                existing_nullable=nullable,
            )
