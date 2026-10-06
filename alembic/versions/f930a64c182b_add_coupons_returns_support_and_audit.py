"""add coupons, returns, support and audit tables

Revision ID: f930a64c182b
Revises: e507bc3d9a12
Create Date: 2026-10-05
"""
from alembic import op
import sqlalchemy as sa


revision = "f930a64c182b"
down_revision = "e507bc3d9a12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("coupon_code", sa.String(length=40), nullable=True))
    op.add_column("orders", sa.Column("discount_amount", sa.Float(), nullable=False, server_default="0"))
    op.add_column("payments", sa.Column("refund_id", sa.String(length=100), nullable=True))
    op.add_column("payments", sa.Column("refund_amount", sa.Numeric(12, 2), nullable=True))
    op.create_table(
        "coupons",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("discount_type", sa.String(length=20), nullable=False), sa.Column("discount_value", sa.Numeric(10, 2), nullable=False),
        sa.Column("minimum_order_amount", sa.Numeric(12, 2), nullable=False), sa.Column("starts_at", sa.DateTime(), nullable=True),
        sa.Column("ends_at", sa.DateTime(), nullable=True), sa.Column("max_redemptions", sa.Integer(), nullable=True),
        sa.Column("redemption_count", sa.Integer(), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_coupons_id"), "coupons", ["id"], unique=False)
    op.create_index(op.f("ix_coupons_code"), "coupons", ["code"], unique=True)
    op.create_table(
        "return_requests",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False), sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False), sa.Column("refund_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=True), sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False), sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_return_order"),
    )
    op.create_index(op.f("ix_return_requests_id"), "return_requests", ["id"], unique=False)
    op.create_index(op.f("ix_return_requests_order_id"), "return_requests", ["order_id"], unique=False)
    op.create_index(op.f("ix_return_requests_user_id"), "return_requests", ["user_id"], unique=False)
    op.create_table(
        "vendor_payouts",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("vendor_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False), sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reference", sa.String(length=120), nullable=True), sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("paid_at", sa.DateTime(), nullable=True), sa.ForeignKeyConstraint(["vendor_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_vendor_payouts_id"), "vendor_payouts", ["id"], unique=False)
    op.create_index(op.f("ix_vendor_payouts_vendor_id"), "vendor_payouts", ["vendor_id"], unique=False)
    op.create_table("commission_settings",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False), sa.PrimaryKeyConstraint("id"))
    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=160), nullable=False), sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False), sa.Column("admin_reply", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]), sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_support_tickets_id"), "support_tickets", ["id"], unique=False)
    op.create_index(op.f("ix_support_tickets_user_id"), "support_tickets", ["user_id"], unique=False)
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False), sa.Column("entity_type", sa.String(length=60), nullable=False),
        sa.Column("entity_id", sa.String(length=80), nullable=True), sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_logs_id"), "audit_logs", ["id"], unique=False)
    op.create_index(op.f("ix_audit_logs_actor_id"), "audit_logs", ["actor_id"], unique=False)


def downgrade() -> None:
    for table in ("audit_logs", "support_tickets", "commission_settings", "vendor_payouts", "return_requests", "coupons"):
        op.drop_table(table)
    op.drop_column("payments", "refund_amount")
    op.drop_column("payments", "refund_id")
    op.drop_column("orders", "discount_amount")
    op.drop_column("orders", "coupon_code")
