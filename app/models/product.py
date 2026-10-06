from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, Boolean, Numeric
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
    is_active = Column(Boolean, nullable=False, default=True)
    is_approved = Column(Boolean, nullable=False, default=True)
    discount_percent = Column(Numeric(5, 2), nullable=False, default=0)
    low_stock_threshold = Column(Integer, nullable=False, default=5)

    category = relationship("Category", back_populates="products")
    vendor = relationship("User")
    images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan", order_by="ProductImage.sort_order")
    specifications = relationship("ProductSpecification", back_populates="product", cascade="all, delete-orphan")
