from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class Coupon(Base):
    __tablename__ = "coupons"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(40), nullable=False, unique=True, index=True)
    discount_type = Column(String(20), nullable=False)
    discount_value = Column(Numeric(10, 2), nullable=False)
    minimum_order_amount = Column(Numeric(12, 2), nullable=False, default=0)
    starts_at = Column(DateTime, nullable=True)
    ends_at = Column(DateTime, nullable=True)
    max_redemptions = Column(Integer, nullable=True)
    redemption_count = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)


class ReturnRequest(Base):
    __tablename__ = "return_requests"
    __table_args__ = (UniqueConstraint("order_id", name="uq_return_order"),)
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reason = Column(Text, nullable=False)
    status = Column(String(30), nullable=False, default="REQUESTED")
    refund_amount = Column(Numeric(12, 2), nullable=True)
    admin_note = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    order = relationship("Order")
    user = relationship("User")


class VendorPayout(Base):
    __tablename__ = "vendor_payouts"
    id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    status = Column(String(20), nullable=False, default="REQUESTED")
    reference = Column(String(120), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)


class CommissionSetting(Base):
    __tablename__ = "commission_settings"
    id = Column(Integer, primary_key=True)
    percent = Column(Numeric(5, 2), nullable=False, default=10)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class SiteSetting(Base):
    __tablename__ = "site_settings"
    id = Column(Integer, primary_key=True)
    key = Column(String(80), nullable=False, unique=True)
    value = Column(String(500), nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    subject = Column(String(160), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="OPEN")
    admin_reply = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(60), nullable=False)
    entity_id = Column(String(80), nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
