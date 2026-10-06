from datetime import datetime
from sqlalchemy import Column, Integer, Float, String, ForeignKey
from sqlalchemy.orm import relationship
from enum import Enum
from sqlalchemy import DateTime, Text
from app.database import Base


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    PROCESSING = "PROCESSING"
    SHIPPED = "SHIPPED"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    PARTIALLY_REJECTED = "PARTIALLY_REJECTED"
    RETURNED = "RETURNED"
    REFUNDED = "REFUNDED"


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    total_amount = Column(
        Float,
        nullable=False
    )

    status = Column(
        String(30),
        nullable=False,
        default="PENDING"
    )

    user = relationship("User")

    payment = relationship(
        "Payment",
        back_populates="order",
        uselist=False,
        cascade="all, delete-orphan"
    )

    items = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan"
    )

    vendor_orders = relationship(
        "VendorOrder",
        back_populates="order",
        cascade="all, delete-orphan"
    )

    reserved_until = Column(
    DateTime,
    nullable=True
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    shipping_address = Column(Text, nullable=True)
    coupon_code = Column(String(40), nullable=True)
    discount_amount = Column(Float, nullable=False, default=0)
    tax_amount = Column(Float, nullable=False, default=0)
    shipping_amount = Column(Float, nullable=False, default=0)


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)

    order_id = Column(
        Integer,
        ForeignKey("orders.id"),
        nullable=False
    )

    product_id = Column(
        Integer,
        ForeignKey("products.id"),
        nullable=False
    )

    quantity = Column(
        Integer,
        nullable=False
    )

    vendor_order_id = Column(Integer, ForeignKey("vendor_orders.id"), nullable=True)

    price = Column(
        Float,
        nullable=False
    )

    order = relationship(
        "Order",
        back_populates="items"
    )

    product = relationship("Product")
    vendor_order = relationship("VendorOrder", back_populates="items")


class VendorOrder(Base):
    __tablename__ = "vendor_orders"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    vendor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(String(30), nullable=False, default="CONFIRMED")
    tracking_number = Column(String(120), nullable=True)
    shipping_provider = Column(String(120), nullable=True)

    order = relationship("Order", back_populates="vendor_orders")
    vendor = relationship("User")
    items = relationship("OrderItem", back_populates="vendor_order")
