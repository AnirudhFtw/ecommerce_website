"""add vendor orders and payment verification support

Revision ID: c62e8b7a19f4
Revises: b41a9c7d2e10
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa


revision = "c62e8b7a19f4"
down_revision = "b41a9c7d2e10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vendor_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("vendor_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["vendor_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_vendor_orders_id"), "vendor_orders", ["id"], unique=False)
    op.add_column("order_items", sa.Column("vendor_order_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_order_items_vendor_order_id_vendor_orders",
        "order_items",
        "vendor_orders",
        ["vendor_order_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_order_items_vendor_order_id_vendor_orders", "order_items", type_="foreignkey")
    op.drop_column("order_items", "vendor_order_id")
    op.drop_index(op.f("ix_vendor_orders_id"), table_name="vendor_orders")
    op.drop_table("vendor_orders")
