"""add vendor accounts and product ownership

Revision ID: b41a9c7d2e10
Revises: 9340f762f032
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa


revision = "b41a9c7d2e10"
down_revision = "9340f762f032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_vendor", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("vendor_application_status", sa.String(length=20), nullable=False, server_default="NONE"))
    op.add_column("users", sa.Column("shop_name", sa.String(length=150), nullable=True))
    op.add_column("users", sa.Column("vendor_application_note", sa.String(length=500), nullable=True))
    op.add_column("products", sa.Column("vendor_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_products_vendor_id_users", "products", "users", ["vendor_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_products_vendor_id_users", "products", type_="foreignkey")
    op.drop_column("products", "vendor_id")
    op.drop_column("users", "vendor_application_note")
    op.drop_column("users", "shop_name")
    op.drop_column("users", "vendor_application_status")
    op.drop_column("users", "is_vendor")
