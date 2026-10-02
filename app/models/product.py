from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False)
    stock = Column(Integer, nullable=False, default=0)

    category_id = Column(
        Integer,
        ForeignKey("categories.id"),
        nullable=False
    )

    vendor_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    category = relationship("Category", back_populates="products")
    vendor = relationship("User")
