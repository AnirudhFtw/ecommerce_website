from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(
        String(100),
        nullable=False
    )

    email = Column(
        String(150),
        unique=True,
        nullable=False,
        index=True
    )

    password = Column(
        String(255),
        nullable=False
    )

    is_admin = Column(
        Boolean,
        default=False
    )

    is_vendor = Column(Boolean, nullable=False, default=False)
    vendor_application_status = Column(String(20), nullable=False, default="NONE")
    shop_name = Column(String(150), nullable=True)
    vendor_application_note = Column(String(500), nullable=True)
    email_verified = Column(Boolean, nullable=False, default=False)
    phone = Column(String(30), nullable=True)
    phone_verified = Column(Boolean, nullable=False, default=False)
    token_version = Column(Integer, nullable=False, default=0)
    bio = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    cart = relationship(
        "Cart",
        back_populates="user",
        uselist=False
    )
