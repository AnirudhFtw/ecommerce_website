from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class ProductImage(Base):
    __tablename__ = "product_images"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    image_url = Column(String(500), nullable=False)
    alt_text = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    product = relationship("Product", back_populates="images")


class ProductSpecification(Base):
    __tablename__ = "product_specifications"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    value = Column(Text, nullable=False)
    product = relationship("Product", back_populates="specifications")
