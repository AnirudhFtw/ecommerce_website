from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pathlib import Path
from uuid import uuid4
from datetime import date, datetime, time, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session
from decimal import Decimal

from app.database import get_db
from app.dependencies import get_current_admin, get_current_user, get_current_vendor
from app.models.category import Category
from app.models.product import Product
from app.models.order import Order, OrderStatus, OrderItem, VendorOrder
from app.models.catalog import ProductImage, ProductSpecification
from app.models.extras import CommissionSetting, VendorPayout
from app.models.customer import ProductReview
from app.models.user import User
from app.schemas.order import OrderStatusUpdate, VendorOrderResponse, VendorOrderStatusUpdate
from app.schemas.product import ProductCreate, ProductResponse, ProductSpecificationsUpdate
from app.schemas.customer import VendorProfileUpdate
from app.schemas.user import VendorApplicationCreate, VendorApplicationReview, UserResponse
from app.schemas.marketplace import PayoutRequest
from app.services.notifications import create_notification, notify_admins


router = APIRouter(prefix="/vendors", tags=["Vendors"])


def net_vendor_order_sales(vendor_order: VendorOrder) -> float:
    vendor_subtotal = sum(line.price * line.quantity for line in vendor_order.items)
    order_subtotal = sum(line.price * line.quantity for line in vendor_order.order.items)
    coupon_discount = float(vendor_order.order.discount_amount or 0)
    allocated_discount = coupon_discount * vendor_subtotal / order_subtotal if order_subtotal else 0
    return max(0.0, vendor_subtotal - allocated_discount)


@router.put("/me/profile")
def update_vendor_profile(data: VendorProfileUpdate, db: Session = Depends(get_db), vendor: User = Depends(get_current_vendor)):
    vendor.shop_name = data.shop_name.strip()
    vendor.vendor_application_note = data.vendor_application_note
    db.commit()
    db.refresh(vendor)
    return {"id": vendor.id, "shop_name": vendor.shop_name, "vendor_application_status": vendor.vendor_application_status}


@router.get("/me/reviews")
def list_vendor_reviews(db: Session = Depends(get_db), vendor: User = Depends(get_current_vendor)):
    rows = db.query(ProductReview).join(Product).filter(Product.vendor_id == vendor.id, ProductReview.is_approved.is_(True)).order_by(ProductReview.id.desc()).all()
    return [{"id": row.id, "product_id": row.product_id, "rating": row.rating, "body": row.body, "created_at": row.created_at} for row in rows]


@router.get("/me/dashboard")
def vendor_dashboard(db: Session = Depends(get_db), vendor: User = Depends(get_current_vendor)):
    delivered_orders = db.query(VendorOrder).filter(VendorOrder.vendor_id == vendor.id, VendorOrder.status == "DELIVERED").all()
    gross_sales = sum(net_vendor_order_sales(order) for order in delivered_orders)
    product_count = db.query(Product).filter(Product.vendor_id == vendor.id, Product.is_active.is_(True)).count()
    low_stock = db.query(Product).filter(Product.vendor_id == vendor.id, Product.is_active.is_(True), Product.stock <= Product.low_stock_threshold).count()
    commission = db.query(CommissionSetting).order_by(CommissionSetting.id.desc()).first()
    commission_percent = Decimal(str(commission.percent if commission else 10))
    gross_amount = Decimal(str(round(gross_sales, 2)))
    already_reserved = db.query(func.coalesce(func.sum(VendorPayout.amount), 0)).filter(
        VendorPayout.vendor_id == vendor.id,
        VendorPayout.status.in_(["REQUESTED", "APPROVED", "PAID"]),
    ).scalar()
    available = gross_amount * (Decimal("1") - commission_percent / Decimal("100")) - Decimal(str(already_reserved or 0))
    return {
        "shop_name": vendor.shop_name,
        "products": product_count,
        "low_stock_products": low_stock,
        "orders": db.query(VendorOrder).filter(VendorOrder.vendor_id == vendor.id).count(),
        "delivered_orders": len(delivered_orders),
        "gross_sales": round(gross_sales, 2),
        "commission_percent": float(commission_percent),
        "available_earnings": float(max(available, Decimal("0"))),
    }


@router.get("/me/sales")
def vendor_sales(start_date: date | None = None, end_date: date | None = None, db: Session = Depends(get_db), vendor: User = Depends(get_current_vendor)):
    query = db.query(VendorOrder).filter(VendorOrder.vendor_id == vendor.id, VendorOrder.status == "DELIVERED")
    if start_date:
        query = query.filter(VendorOrder.order.has(Order.created_at >= datetime.combine(start_date, time.min)))
    if end_date:
        query = query.filter(VendorOrder.order.has(Order.created_at < datetime.combine(end_date + timedelta(days=1), time.min)))
    orders = query.all()
    product_sales = {}
    total = 0.0
    for vendor_order in orders:
        vendor_subtotal = sum(line.price * line.quantity for line in vendor_order.items)
        order_subtotal = sum(line.price * line.quantity for line in vendor_order.order.items)
        discount_share = float(vendor_order.order.discount_amount or 0) * vendor_subtotal / order_subtotal if order_subtotal else 0
        for item in vendor_order.items:
            line_subtotal = item.price * item.quantity
            line_total = line_subtotal - (discount_share * line_subtotal / vendor_subtotal if vendor_subtotal else 0)
            total += line_total
            entry = product_sales.setdefault(item.product_id, {"product_id": item.product_id, "units_sold": 0, "sales": 0.0})
            entry["units_sold"] += item.quantity
            entry["sales"] += line_total
    return {"orders": len(orders), "gross_sales": round(total, 2), "products": list(product_sales.values())}


@router.get("/me/market-insights")
def market_insights(db: Session = Depends(get_db), vendor: User = Depends(get_current_vendor)):
    since = datetime.utcnow() - timedelta(days=30)
    market = db.query(Product.category_id, func.sum(OrderItem.quantity).label("units")).join(OrderItem, OrderItem.product_id == Product.id).join(VendorOrder, VendorOrder.id == OrderItem.vendor_order_id).filter(VendorOrder.status == "DELIVERED", VendorOrder.order.has(Order.created_at >= since)).group_by(Product.category_id).all()
    own = db.query(Product.category_id, func.sum(OrderItem.quantity).label("units")).join(OrderItem, OrderItem.product_id == Product.id).join(VendorOrder, VendorOrder.id == OrderItem.vendor_order_id).filter(Product.vendor_id == vendor.id, VendorOrder.status == "DELIVERED", VendorOrder.order.has(Order.created_at >= since)).group_by(Product.category_id).all()
    own_units = {category_id: int(units or 0) for category_id, units in own}
    return [{"category_id": category_id, "market_units_sold_30d": int(units or 0), "vendor_units_sold_30d": own_units.get(category_id, 0)} for category_id, units in market]


@router.get("/me/payouts")
def list_my_payouts(db: Session = Depends(get_db), vendor: User = Depends(get_current_vendor)):
    rows = db.query(VendorPayout).filter(VendorPayout.vendor_id == vendor.id).order_by(VendorPayout.id.desc()).all()
    return [{"id": row.id, "amount": float(row.amount), "status": row.status, "reference": row.reference, "created_at": row.created_at, "paid_at": row.paid_at} for row in rows]


@router.post("/me/payouts", status_code=201)
def request_payout(request: PayoutRequest, db: Session = Depends(get_db), vendor: User = Depends(get_current_vendor)):
    delivered = db.query(VendorOrder).filter(VendorOrder.vendor_id == vendor.id, VendorOrder.status == "DELIVERED").all()
    gross = Decimal(str(round(sum(net_vendor_order_sales(vo) for vo in delivered), 2)))
    commission = db.query(CommissionSetting).order_by(CommissionSetting.id.desc()).first()
    rate = Decimal(str(commission.percent if commission else 10))
    reserved = Decimal(str(db.query(func.coalesce(func.sum(VendorPayout.amount), 0)).filter(VendorPayout.vendor_id == vendor.id, VendorPayout.status.in_(["REQUESTED", "APPROVED", "PAID"])).scalar() or 0))
    available = gross * (Decimal("1") - rate / Decimal("100")) - reserved
    amount = request.amount.quantize(Decimal("0.01"))
    if amount > available:
        raise HTTPException(status_code=400, detail="Payout amount exceeds available earnings")
    payout = VendorPayout(vendor_id=vendor.id, amount=amount)
    db.add(payout)
    notify_admins(db, "PAYOUT", "Vendor payout requested", f"{vendor.shop_name or vendor.name} requested a payout of {amount}.")
    db.commit()
    db.refresh(payout)
    return {"id": payout.id, "amount": float(payout.amount), "status": payout.status}


@router.post("/me/products/{product_id}/images", status_code=201)
async def upload_product_image(
    product_id: int,
    file: UploadFile = File(...),
    alt_text: str | None = Form(default=None, max_length=200),
    db: Session = Depends(get_db),
    vendor: User = Depends(get_current_vendor),
):
    product = db.query(Product).filter(Product.id == product_id, Product.vendor_id == vendor.id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    ext_by_type = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    extension = ext_by_type.get(file.content_type or "")
    if not extension:
        raise HTTPException(status_code=415, detail="Only JPEG, PNG, and WebP images are allowed")
    content = await file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image must be 5 MB or smaller")
    valid_magic = (
        extension == ".jpg" and content.startswith(b"\xff\xd8\xff")
        or extension == ".png" and content.startswith(b"\x89PNG\r\n\x1a\n")
        or extension == ".webp" and content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    )
    if not valid_magic:
        raise HTTPException(status_code=415, detail="File contents do not match the image type")
    image_dir = Path(__file__).resolve().parents[1] / "static" / "products"
    image_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{extension}"
    (image_dir / filename).write_bytes(content)
    image = ProductImage(product_id=product.id, image_url=f"/media/products/{filename}", alt_text=alt_text, sort_order=len(product.images))
    db.add(image)
    product.is_approved = False
    db.commit()
    db.refresh(image)
    return {"id": image.id, "image_url": image.image_url, "alt_text": image.alt_text, "sort_order": image.sort_order}


@router.put("/me/products/{product_id}/specifications", response_model=ProductResponse)
def update_product_specifications(
    product_id: int,
    data: ProductSpecificationsUpdate,
    db: Session = Depends(get_db),
    vendor: User = Depends(get_current_vendor),
):
    product = db.query(Product).filter(Product.id == product_id, Product.vendor_id == vendor.id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.specifications.clear()
    product.specifications.extend(ProductSpecification(name=item.name, value=item.value) for item in data.items)
    product.is_approved = False
    db.commit()
    db.refresh(product)
    return product


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
    status_data: VendorOrderStatusUpdate,
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

    if new_status == "SHIPPED":
        vendor_order.tracking_number = status_data.tracking_number
        vendor_order.shipping_provider = status_data.shipping_provider

    create_notification(
        db,
        vendor_order.order.user_id,
        "ORDER",
        "Order status updated",
        f"Vendor order #{vendor_order.id} is now {new_status.lower().replace('_', ' ')}.",
    )

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
    notify_admins(db, "VENDOR_APPLICATION", "Vendor application received", f"{user.name} applied to become a vendor.")
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
    create_notification(
        db,
        applicant.id,
        "VENDOR_APPLICATION",
        "Vendor application reviewed",
        "Your vendor application was approved." if review.approved else "Your vendor application was rejected.",
    )
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
    product = Product(**data.model_dump(), vendor_id=vendor.id, is_approved=False)
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
    product.is_approved = False
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
    product.is_active = False
    db.commit()
