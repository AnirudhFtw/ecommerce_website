"""add catalog approval and order shipping fields

Revision ID: e507bc3d9a12
Revises: d1e7f462ba30
Create Date: 2026-10-05
"""
from alembic import op
import sqlalchemy as sa


revision = "e507bc3d9a12"
down_revision = "d1e7f462ba30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("categories", sa.Column("parent_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_categories_parent_id_categories", "categories", "categories", ["parent_id"], ["id"])
    op.add_column("products", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("products", sa.Column("is_approved", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("products", sa.Column("discount_percent", sa.Numeric(5, 2), nullable=False, server_default="0"))
    op.add_column("products", sa.Column("low_stock_threshold", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("orders", sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.add_column("orders", sa.Column("shipping_address", sa.Text(), nullable=True))
    op.create_table(
        "product_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=False),
        sa.Column("alt_text", sa.String(length=200), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_product_images_id"), "product_images", ["id"], unique=False)
    op.create_index(op.f("ix_product_images_product_id"), "product_images", ["product_id"], unique=False)
    op.create_table(
        "product_specifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_product_specifications_id"), "product_specifications", ["id"], unique=False)
    op.create_index(op.f("ix_product_specifications_product_id"), "product_specifications", ["product_id"], unique=False)


def downgrade() -> None:
    op.drop_table("product_specifications")
    op.drop_table("product_images")
    for table, column in (("orders", "shipping_address"), ("orders", "created_at"), ("products", "low_stock_threshold"), ("products", "discount_percent"), ("products", "is_approved"), ("products", "is_active")):
        op.drop_column(table, column)
    op.drop_constraint("fk_categories_parent_id_categories", "categories", type_="foreignkey")
    op.drop_column("categories", "parent_id")
