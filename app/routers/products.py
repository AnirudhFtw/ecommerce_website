from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.dependencies import get_current_admin
from app.database import get_db
from app.models.product import Product
from app.models.category import Category
from app.models.user import User
from app.schemas.product import ProductCreate, ProductResponse
from math import ceil
from fastapi import Query
from app.schemas.product import ProductListResponse
from app.models.customer import ProductReview
from app.schemas.customer import ReviewResponse
from sqlalchemy import func

from typing import Optional
from sqlalchemy import case

router = APIRouter(
    prefix="/products",
    tags=["Products"]
)


@router.get("/{product_id}/reviews")
def get_product_reviews(product_id: int, limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    if not db.query(Product.id).filter(Product.id == product_id, Product.is_active.is_(True), Product.is_approved.is_(True)).first():
        raise HTTPException(status_code=404, detail="Product not found")
    reviews = db.query(ProductReview).filter(ProductReview.product_id == product_id, ProductReview.is_approved.is_(True)).order_by(ProductReview.id.desc()).limit(limit).all()
    average = db.query(func.avg(ProductReview.rating)).filter(ProductReview.product_id == product_id, ProductReview.is_approved.is_(True)).scalar()
    return {"average_rating": float(average) if average is not None else None, "count": len(reviews), "reviews": [ReviewResponse.model_validate(review) for review in reviews]}


@router.get("/", response_model=ProductListResponse)
def get_products(
    search: str | None = None,
    category_id: int | None = None,
    min_price: float | None = Query(None, ge=0),
    max_price: float | None = Query(None, ge=0),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    sort: str = "newest",
    db: Session = Depends(get_db)
):
    if (
        min_price is not None
        and max_price is not None
        and min_price > max_price
    ):
        raise HTTPException(
            status_code=400,
            detail="min_price cannot be greater than max_price"
        )

    effective_price = Product.price * (100 - Product.discount_percent) / 100
    query = db.query(Product).filter(Product.is_active.is_(True), Product.is_approved.is_(True))

    # Search
    if search:
        query = query.filter(
            Product.name.ilike(f"%{search}%")
        )

    # Category
    if category_id is not None:
        query = query.filter(
            Product.category_id == category_id
        )

    # Minimum price
    if min_price is not None:
        query = query.filter(
            effective_price >= min_price
        )

    # Maximum price
    if max_price is not None:
        query = query.filter(
            effective_price <= max_price
        )

    # Sorting
    if sort == "price_asc":
        query = query.order_by(effective_price.asc())

    elif sort == "price_desc":
        query = query.order_by(effective_price.desc())

    elif sort == "newest":
        query = query.order_by(Product.id.desc())

    elif sort == "oldest":
        query = query.order_by(Product.id.asc())

    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid sort option"
        )

    # Total number of matching products
    total = query.count()

    # Pagination
    offset = (page - 1) * limit

    products = query.offset(offset).limit(limit).all()

    total_pages = ceil(total / limit) if total else 0

    return {
        "products": products,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages
    }

@router.post("/", response_model=ProductResponse)
def create_product(
    product: ProductCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    if not db.query(Category.id).filter(Category.id == product.category_id).first():
        raise HTTPException(status_code=404, detail="Category not found")

    new_product = Product(
        name=product.name,
        description=product.description,
        price=product.price,
        stock=product.stock,
        category_id=product.category_id,
        discount_percent=product.discount_percent,
        low_stock_threshold=product.low_stock_threshold,
        is_approved=True,
    )

    db.add(new_product)
    db.commit()
    db.refresh(new_product)

    return new_product





@router.get("/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: int,
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.is_active.is_(True),
        Product.is_approved.is_(True),
    ).first()

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    return product


@router.put("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    product_data: ProductCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    product = db.query(Product).filter(
        Product.id == product_id
    ).first()

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    product.name = product_data.name
    product.description = product_data.description
    product.price = product_data.price
    product.stock = product_data.stock
    product.category_id = product_data.category_id
    product.discount_percent = product_data.discount_percent
    product.low_stock_threshold = product_data.low_stock_threshold
    product.is_approved = True
    db.commit()
    db.refresh(product)

    return product


@router.delete("/{product_id}")
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    product = db.query(Product).filter(
        Product.id == product_id
    ).first()

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    product.is_active = False
    db.commit()

    return {"message": "Product deactivated successfully"}
