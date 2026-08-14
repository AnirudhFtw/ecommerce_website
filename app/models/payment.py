from sqlalchemy import Column, Integer, Float, String, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)

    order_id = Column(
        Integer,
        ForeignKey("orders.id"),
        nullable=False,
        unique=True
    )

    payment_mode = Column(
        String(20),
        nullable=False
    )

    payment_status = Column(
        String(20),
        nullable=False,
        default="PENDING"
    )

    amount = Column(
        Float,
        nullable=False
    )

    razorpay_order_id = Column(
        String(100),
        nullable=True
    )

    razorpay_payment_id = Column(
        String(100),
        nullable=True
    )

    order = relationship(
        "Order",
        back_populates="payment"
    )