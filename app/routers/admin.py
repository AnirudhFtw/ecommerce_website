from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import StringIO
import csv

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_admin
from app.models.customer import ProductReview, Wallet, WalletTransaction
from app.models.extras import AuditLog, CommissionSetting, Coupon, ReturnRequest, SupportTicket, VendorPayout, SiteSetting
from app.models.order import Order
from app.models.payment import Payment
from app.models.product import Product
from app.models.category import Category
from app.models.user import User
from app.schemas.admin import ProductApprovalUpdate, ReviewModerationUpdate, WalletAdjustment, AdminRoleUpdate, AdminNotificationCreate
from app.schemas.marketplace import CouponCreate, CouponResponse, RefundProcessRequest, ReturnRequestResponse, ReturnRequestReview, SupportTicketReply
from app.schemas.user import UserResponse
from app.services.notifications import create_notification
from app.services.payment import refund_razorpay_payment, razorpay_is_configured


router = APIRouter(prefix="/admin", tags=["Admin"])


def log_admin_action(db: Session, admin: User, action: str, entity_type: str, entity_id: int | str, details: str = "") -> None:
    db.add(AuditLog(actor_id=admin.id, action=action, entity_type=entity_type, entity_id=str(entity_id), details=details))


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    captured = db.query(func.coalesce(func.sum(Payment.amount - func.coalesce(Payment.refund_amount, 0)), 0)).filter(Payment.payment_status.in_(["PAID", "PARTIALLY_REFUNDED"])).scalar()
    return {
        "customers": db.query(User).filter(User.is_admin.is_(False), User.is_vendor.is_(False)).count(),
        "approved_vendors": db.query(User).filter(User.is_vendor.is_(True)).count(),
        "pending_vendor_applications": db.query(User).filter(User.vendor_application_status == "PENDING").count(),
        "pending_products": db.query(Product).filter(Product.is_approved.is_(False), Product.is_active.is_(True)).count(),
        "orders": db.query(Order).count(),
        "captured_revenue": float(captured or 0),
        "low_stock_products": db.query(Product).filter(Product.is_active.is_(True), Product.stock <= Product.low_stock_threshold).count(),
    }


@router.get("/users", response_model=list[UserResponse])
def list_users(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    return db.query(User).order_by(User.id.desc()).offset(offset).limit(limit).all()


@router.get("/vendors", response_model=list[UserResponse])
def list_vendors(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    return db.query(User).filter(User.is_vendor.is_(True)).order_by(User.id.desc()).all()


@router.put("/users/{user_id}/admin-role", response_model=UserResponse)
def update_admin_role(user_id: int, data: AdminRoleUpdate, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id and not data.is_admin:
        raise HTTPException(status_code=409, detail="You cannot remove your own admin role")
    user.is_admin = data.is_admin
    log_admin_action(db, admin, "ADMIN_ROLE_CHANGED", "user", user.id, f"is_admin={data.is_admin}")
    db.commit()
    db.refresh(user)
    return user


@router.post("/notifications", status_code=201)
def send_admin_notification(data: AdminNotificationCreate, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    if data.user_id is not None:
        if not db.query(User.id).filter(User.id == data.user_id).first():
            raise HTTPException(status_code=404, detail="User not found")
        create_notification(db, data.user_id, data.kind, data.title, data.message)
        recipient_count = 1
    else:
        users = db.query(User.id).all()
        for (user_id,) in users:
            create_notification(db, user_id, data.kind, data.title, data.message)
        recipient_count = len(users)
    log_admin_action(db, admin, "NOTIFICATION_SENT", "user", data.user_id or "all", data.title)
    db.commit()
    return {"sent": recipient_count}


@router.get("/products/pending", response_model=list[dict])
def list_pending_products(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    products = db.query(Product).filter(Product.is_approved.is_(False), Product.is_active.is_(True)).order_by(Product.id).all()
    return [{"id": p.id, "name": p.name, "vendor_id": p.vendor_id, "category_id": p.category_id, "price": p.price, "stock": p.stock} for p in products]


@router.put("/products/{product_id}/approval")
def moderate_product(product_id: int, data: ProductApprovalUpdate, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_approved = data.approved
    log_admin_action(db, admin, "PRODUCT_MODERATION", "product", product.id, f"approved={data.approved}")
    if product.vendor_id:
        create_notification(db, product.vendor_id, "PRODUCT", "Product reviewed", f"Your product '{product.name}' was {'approved' if data.approved else 'rejected'}.")
    db.commit()
    return {"id": product.id, "is_approved": product.is_approved}


@router.get("/reviews/pending")
def pending_reviews(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    rows = db.query(ProductReview).filter(ProductReview.is_approved.is_(False)).order_by(ProductReview.id).all()
    return [{"id": r.id, "user_id": r.user_id, "product_id": r.product_id, "rating": r.rating, "body": r.body, "created_at": r.created_at} for r in rows]


@router.put("/reviews/{review_id}/moderation")
def moderate_review(review_id: int, data: ReviewModerationUpdate, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    review = db.query(ProductReview).filter(ProductReview.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    review.is_approved = data.approved
    log_admin_action(db, admin, "REVIEW_MODERATION", "review", review.id, f"approved={data.approved}")
    db.commit()
    return {"id": review.id, "is_approved": review.is_approved}


@router.get("/inventory/low-stock")
def low_stock(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    rows = db.query(Product).filter(Product.is_active.is_(True), Product.stock <= Product.low_stock_threshold).order_by(Product.stock).all()
    return [{"id": p.id, "name": p.name, "vendor_id": p.vendor_id, "stock": p.stock, "threshold": p.low_stock_threshold} for p in rows]


@router.post("/users/{user_id}/wallet/adjustment")
def adjust_wallet(user_id: int, data: WalletAdjustment, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()
    if not wallet:
        wallet = Wallet(user_id=user_id, balance=0)
        db.add(wallet)
        db.flush()
    amount = Decimal(str(data.amount))
    wallet.balance += amount
    db.add(WalletTransaction(wallet_id=wallet.id, amount=amount, transaction_type="CREDIT", reason=data.reason, reference=f"admin:{admin.id}"))
    log_admin_action(db, admin, "WALLET_CREDIT", "user", user_id, f"amount={amount}; reason={data.reason}")
    db.commit()
    return {"user_id": user_id, "wallet_balance": float(wallet.balance)}


@router.get("/reports/sales")
def sales_report(start_date: date | None = None, end_date: date | None = None, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    query = db.query(Order)
    if start_date:
        query = query.filter(Order.created_at >= datetime.combine(start_date, time.min))
    if end_date:
        query = query.filter(Order.created_at < datetime.combine(end_date + timedelta(days=1), time.min))
    query = query.filter(Order.status.in_(["DELIVERED", "RETURNED", "REFUNDED"]))
    return {"orders": query.count(), "gross_sales": float(query.with_entities(func.coalesce(func.sum(Order.total_amount), 0)).scalar() or 0)}


@router.get("/reports/sales.csv")
def export_sales_report(start_date: date | None = None, end_date: date | None = None, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    query = db.query(Order).filter(Order.status.in_(["DELIVERED", "RETURNED", "REFUNDED"]))
    if start_date:
        query = query.filter(Order.created_at >= datetime.combine(start_date, time.min))
    if end_date:
        query = query.filter(Order.created_at < datetime.combine(end_date + timedelta(days=1), time.min))
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["order_id", "customer_id", "status", "gross_total", "discount", "tax", "shipping", "created_at"])
    for order in query.order_by(Order.id).all():
        writer.writerow([order.id, order.user_id, order.status, order.total_amount, order.discount_amount, order.tax_amount, order.shipping_amount, order.created_at.isoformat()])
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=sales-report.csv"})


@router.get("/analytics/growth")
def growth_analytics(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    users = db.query(func.date_trunc("month", User.created_at).label("month"), func.count(User.id)).filter(User.is_admin.is_(False), User.is_vendor.is_(False)).group_by("month").order_by("month").all()
    vendors = db.query(func.date_trunc("month", User.created_at).label("month"), func.count(User.id)).filter(User.is_vendor.is_(True)).group_by("month").order_by("month").all()
    orders = db.query(func.date_trunc("month", Order.created_at).label("month"), func.count(Order.id)).group_by("month").order_by("month").all()
    return {"customers": [{"month": month.isoformat(), "count": count} for month, count in users], "vendors": [{"month": month.isoformat(), "count": count} for month, count in vendors], "orders": [{"month": month.isoformat(), "count": count} for month, count in orders]}


@router.get("/analytics/products")
def product_analytics(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    rows = db.query(OrderItem.product_id, func.sum(OrderItem.quantity).label("units_sold"), func.sum(OrderItem.quantity * OrderItem.price).label("sales")).join(Order).filter(Order.status == "DELIVERED").group_by(OrderItem.product_id).order_by(func.sum(OrderItem.quantity * OrderItem.price).desc()).all()
    return [{"product_id": product_id, "units_sold": int(units or 0), "sales": float(sales or 0)} for product_id, units, sales in rows]


@router.get("/analytics/categories")
def category_analytics(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    rows = db.query(Category.id, Category.name, func.sum(OrderItem.quantity).label("units"), func.sum(OrderItem.quantity * OrderItem.price).label("sales")).join(Product, Product.category_id == Category.id).join(OrderItem, OrderItem.product_id == Product.id).join(Order, Order.id == OrderItem.order_id).filter(Order.status == "DELIVERED").group_by(Category.id, Category.name).order_by(func.sum(OrderItem.quantity * OrderItem.price).desc()).all()
    return [{"category_id": category_id, "name": name, "units_sold": int(units or 0), "sales": float(sales or 0)} for category_id, name, units, sales in rows]


@router.get("/reports/refunds")
def refund_report(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    rows = db.query(Payment).filter(Payment.payment_status.in_(["REFUND_PENDING", "PARTIALLY_REFUNDED", "REFUNDED"])).order_by(Payment.id.desc()).limit(500).all()
    return [{"payment_id": row.id, "order_id": row.order_id, "status": row.payment_status, "amount": float(row.amount), "refund_amount": float(row.refund_amount) if row.refund_amount is not None else None, "refund_reference": row.refund_id} for row in rows]


@router.get("/returns", response_model=list[ReturnRequestResponse])
def list_returns(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    return db.query(ReturnRequest).order_by(ReturnRequest.id.desc()).all()


@router.get("/payments")
def list_payments(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    rows = db.query(Payment).order_by(Payment.id.desc()).limit(500).all()
    return [{"id": row.id, "order_id": row.order_id, "mode": row.payment_mode, "status": row.payment_status, "amount": float(row.amount), "refund_amount": float(row.refund_amount) if row.refund_amount is not None else None, "refund_id": row.refund_id, "razorpay_order_id": row.razorpay_order_id, "razorpay_payment_id": row.razorpay_payment_id} for row in rows]


@router.put("/returns/{return_id}", response_model=ReturnRequestResponse)
def review_return(return_id: int, data: ReturnRequestReview, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    request = db.query(ReturnRequest).filter(ReturnRequest.id == return_id).first()
    if not request or request.status != "REQUESTED":
        raise HTTPException(status_code=404, detail="Open return request not found")
    request.status = "APPROVED" if data.approved else "REJECTED"
    request.admin_note = data.note
    if data.approved:
        amount = data.refund_amount if data.refund_amount is not None else Decimal(str(request.order.total_amount))
        if amount > Decimal(str(request.order.total_amount)):
            raise HTTPException(status_code=400, detail="Refund exceeds order total")
        request.refund_amount = amount
        request.order.status = "RETURNED"
        for vendor_order in request.order.vendor_orders:
            if vendor_order.status == "DELIVERED":
                vendor_order.status = "RETURNED"
        if request.order.payment:
            request.order.payment.payment_status = "REFUND_PENDING"
    create_notification(db, request.user_id, "RETURN", "Return request reviewed", "Your return request was approved." if data.approved else "Your return request was rejected.")
    log_admin_action(db, admin, "RETURN_REVIEW", "return", request.id, f"approved={data.approved}")
    db.commit()
    db.refresh(request)
    return request


@router.post("/payments/{payment_id}/refund")
def process_refund(payment_id: int, data: RefundProcessRequest, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.payment_status != "REFUND_PENDING":
        raise HTTPException(status_code=409, detail="Payment is not awaiting a refund")
    return_request = db.query(ReturnRequest).filter(ReturnRequest.order_id == payment.order_id, ReturnRequest.status == "APPROVED").first()
    if data.amount is not None:
        amount = data.amount
    elif return_request and return_request.refund_amount:
        amount = Decimal(str(return_request.refund_amount))
    else:
        raise HTTPException(status_code=422, detail="Specify a refund amount")
    if amount > Decimal(str(payment.amount)):
        raise HTTPException(status_code=400, detail="Refund exceeds payment amount")
    if payment.refund_id:
        raise HTTPException(status_code=409, detail="A refund has already been submitted")

    if payment.payment_mode == "ONLINE":
        if not payment.razorpay_payment_id:
            raise HTTPException(status_code=409, detail="Gateway payment ID is missing")
        if not razorpay_is_configured():
            raise HTTPException(status_code=503, detail="Razorpay env details not present")
        try:
            result = refund_razorpay_payment(payment.razorpay_payment_id, int(amount * 100), {"order_id": str(payment.order_id)})
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Razorpay refund request failed") from exc
        payment.refund_id = result.get("id")
        payment.refund_amount = amount
        completed = result.get("status") == "processed"
    else:
        wallet = db.query(Wallet).filter(Wallet.user_id == payment.order.user_id).with_for_update().first()
        if not wallet:
            wallet = Wallet(user_id=payment.order.user_id, balance=0)
            db.add(wallet)
            db.flush()
        wallet.balance += amount
        db.add(WalletTransaction(wallet_id=wallet.id, amount=amount, transaction_type="CREDIT", reason="ORDER_REFUND", reference=f"order:{payment.order_id}"))
        payment.refund_amount = amount
        completed = True

    if completed:
        payment.payment_status = "REFUNDED" if amount >= Decimal(str(payment.amount)) else "PARTIALLY_REFUNDED"
        if payment.payment_status == "REFUNDED":
            payment.order.status = "REFUNDED"
            for vendor_order in payment.order.vendor_orders:
                if vendor_order.status == "RETURNED":
                    vendor_order.status = "REFUNDED"
        if return_request:
            return_request.status = payment.payment_status
    log_admin_action(db, admin, "REFUND_PROCESSED", "payment", payment.id, f"amount={amount}; gateway={payment.payment_mode == 'ONLINE'}")
    db.commit()
    return {"payment_id": payment.id, "refund_id": payment.refund_id, "refund_amount": str(amount), "status": payment.payment_status}


@router.get("/coupons", response_model=list[CouponResponse])
def list_coupons(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    return db.query(Coupon).order_by(Coupon.id.desc()).all()


@router.post("/coupons", response_model=CouponResponse, status_code=201)
def create_coupon(data: CouponCreate, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    code = data.code.strip().upper()
    if data.discount_type not in {"PERCENT", "FIXED"}:
        raise HTTPException(status_code=422, detail="discount_type must be PERCENT or FIXED")
    if data.discount_type == "PERCENT" and data.discount_value > 100:
        raise HTTPException(status_code=422, detail="Percentage discount cannot exceed 100")
    if data.starts_at and data.ends_at and data.ends_at <= data.starts_at:
        raise HTTPException(status_code=422, detail="ends_at must be after starts_at")
    if db.query(Coupon.id).filter(Coupon.code == code).first():
        raise HTTPException(status_code=409, detail="Coupon code already exists")
    coupon = Coupon(**data.model_dump(exclude={"code"}), code=code)
    db.add(coupon)
    log_admin_action(db, admin, "COUPON_CREATED", "coupon", code)
    db.commit()
    db.refresh(coupon)
    return coupon


@router.put("/coupons/{coupon_id}", response_model=CouponResponse)
def update_coupon(coupon_id: int, data: CouponCreate, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    coupon = db.query(Coupon).filter(Coupon.id == coupon_id).first()
    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found")
    if data.discount_type not in {"PERCENT", "FIXED"} or (data.discount_type == "PERCENT" and data.discount_value > 100):
        raise HTTPException(status_code=422, detail="Invalid discount configuration")
    normalized_code = data.code.strip().upper()
    if db.query(Coupon.id).filter(Coupon.code == normalized_code, Coupon.id != coupon.id).first():
        raise HTTPException(status_code=409, detail="Coupon code already exists")
    values = data.model_dump()
    values["code"] = normalized_code
    for field, value in values.items():
        setattr(coupon, field, value)
    log_admin_action(db, admin, "COUPON_UPDATED", "coupon", coupon.id)
    db.commit()
    db.refresh(coupon)
    return coupon


@router.get("/support-tickets")
def list_support_tickets(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    rows = db.query(SupportTicket).order_by(SupportTicket.id.desc()).all()
    return [{"id": row.id, "user_id": row.user_id, "subject": row.subject, "message": row.message, "status": row.status, "admin_reply": row.admin_reply, "created_at": row.created_at} for row in rows]


@router.put("/support-tickets/{ticket_id}")
def reply_support_ticket(ticket_id: int, data: SupportTicketReply, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Support ticket not found")
    ticket.status = data.status
    ticket.admin_reply = data.admin_reply
    create_notification(db, ticket.user_id, "SUPPORT", "Support replied", data.admin_reply)
    log_admin_action(db, admin, "SUPPORT_REPLIED", "ticket", ticket.id)
    db.commit()
    return {"id": ticket.id, "status": ticket.status, "admin_reply": ticket.admin_reply}


@router.get("/payouts")
def list_payouts(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    rows = db.query(VendorPayout).order_by(VendorPayout.id.desc()).all()
    return [{"id": row.id, "vendor_id": row.vendor_id, "amount": float(row.amount), "status": row.status, "reference": row.reference, "created_at": row.created_at} for row in rows]


@router.put("/payouts/{payout_id}")
def update_payout(payout_id: int, status: str = Query(..., pattern="^(APPROVED|PAID|REJECTED)$"), reference: str | None = None, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    payout = db.query(VendorPayout).filter(VendorPayout.id == payout_id).first()
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")
    if payout.status not in {"REQUESTED", "APPROVED"} or (status == "APPROVED" and payout.status != "REQUESTED"):
        raise HTTPException(status_code=409, detail="Invalid payout status transition")
    payout.status = status
    payout.reference = reference
    if status == "PAID":
        from datetime import datetime
        payout.paid_at = datetime.utcnow()
    create_notification(db, payout.vendor_id, "PAYOUT", "Payout updated", f"Your payout #{payout.id} is {status.lower()}.")
    log_admin_action(db, admin, "PAYOUT_STATUS", "payout", payout.id, status)
    db.commit()
    return {"id": payout.id, "status": payout.status, "reference": payout.reference}


@router.get("/commission")
def get_commission(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    setting = db.query(CommissionSetting).order_by(CommissionSetting.id.desc()).first()
    return {"commission_percent": float(setting.percent) if setting else 10.0}


@router.put("/commission")
def set_commission(percent: Decimal = Query(..., ge=0, le=100), db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    setting = db.query(CommissionSetting).order_by(CommissionSetting.id.desc()).first()
    if not setting:
        setting = CommissionSetting(percent=percent)
        db.add(setting)
    else:
        setting.percent = percent
    log_admin_action(db, admin, "COMMISSION_UPDATED", "commission", setting.id or "new", str(percent))
    db.commit()
    return {"commission_percent": float(setting.percent)}


@router.get("/audit-logs")
def audit_logs(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
    return [{"id": row.id, "actor_id": row.actor_id, "action": row.action, "entity_type": row.entity_type, "entity_id": row.entity_id, "details": row.details, "created_at": row.created_at} for row in rows]


@router.get("/settings/content")
def get_content_settings(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    keys = ["site_name", "homepage_banner", "support_email"]
    return {row.key: row.value for row in db.query(SiteSetting).filter(SiteSetting.key.in_(keys)).all()}


@router.put("/settings/content")
def update_content_setting(key: str = Query(..., pattern="^(site_name|homepage_banner|support_email)$"), value: str = Query(..., max_length=500), db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    setting = db.query(SiteSetting).filter(SiteSetting.key == key).first()
    if not setting:
        setting = SiteSetting(key=key, value=value)
        db.add(setting)
    else:
        setting.value = value
    log_admin_action(db, admin, "CONTENT_SETTING_UPDATED", "setting", key)
    db.commit()
    return {"key": key, "value": value}


@router.get("/settings/checkout")
def get_checkout_settings(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    values = {row.key: float(row.value) for row in db.query(SiteSetting).filter(SiteSetting.key.in_(["tax_percent", "shipping_flat"])).all()}
    return {"tax_percent": values.get("tax_percent", 0), "shipping_flat": values.get("shipping_flat", 0)}


@router.put("/settings/checkout")
def update_checkout_settings(tax_percent: Decimal = Query(0, ge=0, le=100), shipping_flat: Decimal = Query(0, ge=0, le=100000), db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    for key, value in (("tax_percent", tax_percent), ("shipping_flat", shipping_flat)):
        setting = db.query(SiteSetting).filter(SiteSetting.key == key).first()
        if not setting:
            setting = SiteSetting(key=key, value=str(value))
            db.add(setting)
        else:
            setting.value = str(value)
    log_admin_action(db, admin, "CHECKOUT_SETTINGS_UPDATED", "settings", "checkout", f"tax={tax_percent}; shipping={shipping_flat}")
    db.commit()
    return {"tax_percent": float(tax_percent), "shipping_flat": float(shipping_flat)}
