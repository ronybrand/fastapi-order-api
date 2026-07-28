"""initial schema: customers, orders, items

Revision ID: 0001
Revises:
Create Date: 2026-07-28

Escrita manualmente (sem `alembic revision --autogenerate`) porque este ambiente não tem um
Postgres de desenvolvimento acessível para gerar o diff contra os models. Revisada
manualmente contra `api/models/models.py` antes do commit, seguindo o checklist da skill
fastapi-feature — confira o diff real com `alembic check`/`--autogenerate` assim que houver
um banco de dev disponível.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto')

    order_status = postgresql.ENUM("OPEN", "CONFIRMED", "CANCELED", name="order_status")
    order_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("tax_id", sa.String(), nullable=False),
        sa.Column("passport_number", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.String(), nullable=True),
        sa.UniqueConstraint("tax_id", name="uq_customers_tax_id"),
        sa.UniqueConstraint("passport_number", name="uq_customers_passport_number"),
    )

    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", order_status, nullable=False, server_default="OPEN"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"])

    op.create_table(
        "items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_items_order_id", "items", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_items_order_id", table_name="items")
    op.drop_table("items")
    op.drop_index("ix_orders_customer_id", table_name="orders")
    op.drop_table("orders")
    op.drop_table("customers")
    postgresql.ENUM(name="order_status").drop(op.get_bind(), checkfirst=True)
    op.execute('DROP EXTENSION IF EXISTS pgcrypto')
