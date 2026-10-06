"""add shipping tracking, checkout settings and user timestamps

Revision ID: a4b8c12de730
Revises: f930a64c182b
Create Date: 2026-10-05
"""
from alembic import op
import sqlalchemy as sa


revision = "a4b8c12de730"
down_revision = "f930a64c182b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.add_column("orders", sa.Column("tax_amount", sa.Float(), nullable=False, server_default="0"))
    op.add_column("orders", sa.Column("shipping_amount", sa.Float(), nullable=False, server_default="0"))
    op.add_column("vendor_orders", sa.Column("tracking_number", sa.String(length=120), nullable=True))
    op.add_column("vendor_orders", sa.Column("shipping_provider", sa.String(length=120), nullable=True))
    op.create_table(
        "site_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.String(length=500), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("site_settings")
    op.drop_column("vendor_orders", "shipping_provider")
    op.drop_column("vendor_orders", "tracking_number")
    op.drop_column("orders", "shipping_amount")
    op.drop_column("orders", "tax_amount")
    op.drop_column("users", "created_at")
