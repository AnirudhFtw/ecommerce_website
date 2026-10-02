from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import relationship

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

    cart = relationship(
        "Cart",
        back_populates="user",
        uselist=False
    )
