from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_admin, get_current_user, get_current_vendor
from app.models.category import Category
from app.models.product import Product
from app.models.order import OrderStatus, VendorOrder
from app.models.user import User
from app.schemas.order import OrderStatusUpdate, VendorOrderResponse
from app.schemas.product import ProductCreate, ProductResponse
from app.schemas.user import VendorApplicationCreate, VendorApplicationReview, UserResponse


router = APIRouter(prefix="/vendors", tags=["Vendors"])


@router.get("/me/orders", response_model=list[VendorOrderResponse])
def list_my_orders(
    db: Session = Depends(get_db),
    vendor: User = Depends(get_current_vendor),
):
    return db.query(VendorOrder).filter(
        VendorOrder.vendor_id == vendor.id
    ).order_by(VendorOrder.id.desc()).all()


@router.put("/me/orders/{vendor_order_id}/status", response_model=VendorOrderResponse)
def update_my_order_status(
    vendor_order_id: int,
    status_data: OrderStatusUpdate,
    db: Session = Depends(get_db),
    vendor: User = Depends(get_current_vendor),
):
    vendor_order = db.query(VendorOrder).filter(
        VendorOrder.id == vendor_order_id,
        VendorOrder.vendor_id == vendor.id,
    ).first()
    if not vendor_order:
        raise HTTPException(status_code=404, detail="Vendor order not found")

    transitions = {
        "CONFIRMED": {"PROCESSING", "REJECTED"},
        "PROCESSING": {"SHIPPED"},
        "SHIPPED": {"OUT_FOR_DELIVERY"},
        "OUT_FOR_DELIVERY": {"DELIVERED"},
    }
    new_status = status_data.status.value
    if new_status not in transitions.get(vendor_order.status, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot change vendor order from {vendor_order.status} to {new_status}",
        )

    if new_status == "REJECTED":
        for item in vendor_order.items:
            item.product.stock += item.quantity
        payment = vendor_order.order.payment
        if payment and payment.payment_status == "PAID":
            payment.payment_status = "REFUND_PENDING"

    vendor_order.status = new_status
    order = vendor_order.order
    statuses = [item.status for item in order.vendor_orders]
    active = [status for status in statuses if status not in {"REJECTED", "CANCELLED"}]
    if "REJECTED" in statuses:
        order.status = "PARTIALLY_REJECTED" if active else "REJECTED"
    elif active:
        progress = {
            "PENDING": 0,
            "CONFIRMED": 1,
            "PROCESSING": 2,
            "SHIPPED": 3,
            "OUT_FOR_DELIVERY": 4,
            "DELIVERED": 5,
        }
        order.status = min(active, key=lambda status: progress.get(status, 0))
    else:
        order.status = "CANCELLED"

    db.commit()
    db.refresh(vendor_order)
    return vendor_order


@router.post("/apply", response_model=UserResponse)
def apply_to_become_vendor(
    application: VendorApplicationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.is_vendor:
        raise HTTPException(status_code=400, detail="Account is already an approved vendor")
    if user.vendor_application_status == "PENDING":
        raise HTTPException(status_code=409, detail="A vendor application is already pending")
    shop_name = application.shop_name.strip()
    if not shop_name:
        raise HTTPException(status_code=422, detail="Shop name is required")

    user.shop_name = shop_name
    user.vendor_application_note = application.note
    user.vendor_application_status = "PENDING"
    db.commit()
    db.refresh(user)
    return user


@router.get("/applications", response_model=list[UserResponse])
def list_vendor_applications(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    return db.query(User).filter(User.vendor_application_status == "PENDING").order_by(User.id).all()


@router.put("/applications/{user_id}", response_model=UserResponse)
def review_vendor_application(
    user_id: int,
    review: VendorApplicationReview,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    applicant = db.query(User).filter(User.id == user_id).first()
    if not applicant or applicant.vendor_application_status != "PENDING":
        raise HTTPException(status_code=404, detail="Pending vendor application not found")
    applicant.is_vendor = review.approved
    applicant.vendor_application_status = "APPROVED" if review.approved else "REJECTED"
    if review.note is not None:
        applicant.vendor_application_note = review.note
    db.commit()
    db.refresh(applicant)
    return applicant


@router.get("/me/products", response_model=list[ProductResponse])
def list_my_products(
    db: Session = Depends(get_db),
    vendor: User = Depends(get_current_vendor),
):
    return db.query(Product).filter(Product.vendor_id == vendor.id).order_by(Product.id.desc()).all()


@router.post("/me/products", response_model=ProductResponse, status_code=201)
def create_my_product(
    data: ProductCreate,
    db: Session = Depends(get_db),
    vendor: User = Depends(get_current_vendor),
):
    if not db.query(Category.id).filter(Category.id == data.category_id).first():
        raise HTTPException(status_code=404, detail="Category not found")
    product = Product(**data.model_dump(), vendor_id=vendor.id)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.put("/me/products/{product_id}", response_model=ProductResponse)
def update_my_product(
    product_id: int,
    data: ProductCreate,
    db: Session = Depends(get_db),
    vendor: User = Depends(get_current_vendor),
):
    product = db.query(Product).filter(Product.id == product_id, Product.vendor_id == vendor.id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if not db.query(Category.id).filter(Category.id == data.category_id).first():
        raise HTTPException(status_code=404, detail="Category not found")
    for field, value in data.model_dump().items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/me/products/{product_id}", status_code=204)
def delete_my_product(
    product_id: int,
    db: Session = Depends(get_db),
    vendor: User = Depends(get_current_vendor),
):
    product = db.query(Product).filter(Product.id == product_id, Product.vendor_id == vendor.id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(product)
    db.commit()
