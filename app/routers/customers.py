from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.dependencies import get_current_user
from app.models.cart import Cart, CartItem
from app.models.customer import AccountToken, Notification, ProductReview, UserAddress, Wallet, WalletTransaction, WishlistItem
from app.models.extras import ReturnRequest, SupportTicket
from app.models.order import Order, OrderItem, VendorOrder
from app.models.product import Product
from app.models.payment import Payment
from app.models.user import User
from app.schemas.customer import (
    AddressCreate,
    AddressResponse,
    NotificationResponse,
    ProfileUpdate,
    ProfileResponse,
    RefundStatusResponse,
    ReviewCreate,
    ReviewResponse,
    WalletResponse,
    WalletTransactionResponse,
    WishlistCreate,
    WishlistItemResponse,
)
from app.schemas.marketplace import ReturnRequestCreate, ReturnRequestResponse, SupportTicketCreate
from app.services.notifications import notify_admins


router = APIRouter(prefix="/customers", tags=["Customers"])


@router.post("/me/returns", response_model=ReturnRequestResponse, status_code=201)
def request_return(data: ReturnRequestCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    order = db.query(Order).filter(Order.id == data.order_id, Order.user_id == user.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "DELIVERED":
        raise HTTPException(status_code=409, detail="Only delivered orders can be returned")
    if db.query(ReturnRequest.id).filter(ReturnRequest.order_id == order.id).first():
        raise HTTPException(status_code=409, detail="A return request already exists for this order")
    request = ReturnRequest(order_id=order.id, user_id=user.id, reason=data.reason)
    db.add(request)
    notify_admins(db, "RETURN", "Return requested", f"Return requested for order #{order.id}.")
    db.commit()
    db.refresh(request)
    return request


@router.get("/me/returns", response_model=list[ReturnRequestResponse])
def list_my_returns(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(ReturnRequest).filter(ReturnRequest.user_id == user.id).order_by(ReturnRequest.id.desc()).all()


@router.get("/me/refunds", response_model=list[RefundStatusResponse])
def list_refund_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Payment).join(Order).filter(Order.user_id == user.id, Payment.payment_status.in_(["REFUND_PENDING", "PARTIALLY_REFUNDED", "REFUNDED"])).order_by(Payment.id.desc()).all()
    return [{"order_id": row.order_id, "payment_status": row.payment_status, "refund_amount": row.refund_amount, "refund_id": row.refund_id} for row in rows]


@router.post("/me/support-tickets", status_code=201)
def create_support_ticket(data: SupportTicketCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ticket = SupportTicket(user_id=user.id, subject=data.subject, message=data.message)
    db.add(ticket)
    notify_admins(db, "SUPPORT", "Support ticket opened", f"{user.name} opened ticket: {data.subject}")
    db.commit()
    db.refresh(ticket)
    return {"id": ticket.id, "subject": ticket.subject, "status": ticket.status, "created_at": ticket.created_at}


@router.get("/me/support-tickets")
def list_my_support_tickets(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(SupportTicket).filter(SupportTicket.user_id == user.id).order_by(SupportTicket.id.desc()).all()
    return [{"id": row.id, "subject": row.subject, "message": row.message, "status": row.status, "admin_reply": row.admin_reply, "created_at": row.created_at} for row in rows]


@router.get("/me/dashboard")
def customer_dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
    cart_item_count = db.query(func.coalesce(func.sum(CartItem.quantity), 0)).join(Cart).filter(Cart.user_id == user.id).scalar()
    return {
        "user": {"id": user.id, "name": user.name, "email": user.email, "phone": user.phone},
        "orders": db.query(Order).filter(Order.user_id == user.id).count(),
        "cart_item_count": cart_item_count,
        "wallet_balance": wallet.balance if wallet else 0,
        "vendor_application_status": user.vendor_application_status,
    }


@router.get("/me/profile", response_model=ProfileResponse)
def get_profile(user: User = Depends(get_current_user)):
    return user


@router.put("/me/profile", response_model=ProfileResponse)
@router.patch("/me/profile", response_model=ProfileResponse)
def update_profile(data: ProfileUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    updates = data.model_dump(exclude_unset=True)
    if "name" in updates:
        name = (updates["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="Name cannot be blank")
        user.name = name
    if "phone" in updates and user.phone != updates["phone"]:
        user.phone_verified = False
        db.query(AccountToken).filter(AccountToken.user_id == user.id, AccountToken.purpose == "PHONE_VERIFY", AccountToken.consumed_at.is_(None)).update({AccountToken.consumed_at: datetime.utcnow()}, synchronize_session=False)
        user.phone = updates["phone"]
    if "bio" in updates:
        user.bio = updates["bio"]
    db.commit()
    db.refresh(user)
    return user


@router.get("/me/addresses", response_model=list[AddressResponse])
def list_addresses(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(UserAddress).filter(UserAddress.user_id == user.id).order_by(UserAddress.is_default.desc(), UserAddress.id).all()


@router.post("/me/addresses", response_model=AddressResponse, status_code=201)
def create_address(data: AddressCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if data.is_default:
        db.query(UserAddress).filter(UserAddress.user_id == user.id).update({UserAddress.is_default: False})
    elif db.query(UserAddress.id).filter(UserAddress.user_id == user.id).count() == 0:
        data = data.model_copy(update={"is_default": True})
    address = UserAddress(user_id=user.id, **data.model_dump())
    db.add(address)
    db.commit()
    db.refresh(address)
    return address


@router.put("/me/addresses/{address_id}", response_model=AddressResponse)
def update_address(address_id: int, data: AddressCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    address = db.query(UserAddress).filter(UserAddress.id == address_id, UserAddress.user_id == user.id).first()
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")
    if data.is_default:
        db.query(UserAddress).filter(UserAddress.user_id == user.id).update({UserAddress.is_default: False})
    for field, value in data.model_dump().items():
        setattr(address, field, value)
    db.commit()
    db.refresh(address)
    return address


@router.delete("/me/addresses/{address_id}", status_code=204)
def delete_address(address_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    address = db.query(UserAddress).filter(UserAddress.id == address_id, UserAddress.user_id == user.id).first()
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")
    db.delete(address)
    db.commit()


@router.get("/me/wallet", response_model=WalletResponse)
def get_wallet(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
    if not wallet:
        wallet = Wallet(user_id=user.id, balance=0)
        db.add(wallet)
        db.commit()
        db.refresh(wallet)
    return wallet


@router.get("/me/wallet/transactions", response_model=list[WalletTransactionResponse])
def wallet_history(
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
    if not wallet:
        return []
    return db.query(WalletTransaction).filter(WalletTransaction.wallet_id == wallet.id).order_by(WalletTransaction.id.desc()).limit(limit).all()


@router.get("/me/wishlist", response_model=list[WishlistItemResponse])
def get_wishlist(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(WishlistItem).filter(WishlistItem.user_id == user.id).order_by(WishlistItem.id.desc()).all()


@router.post("/me/wishlist", response_model=WishlistItemResponse, status_code=201)
def add_wishlist_item(data: WishlistCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not db.query(Product.id).filter(Product.id == data.product_id).first():
        raise HTTPException(status_code=404, detail="Product not found")
    existing = db.query(WishlistItem).filter(WishlistItem.user_id == user.id, WishlistItem.product_id == data.product_id).first()
    if existing:
        return existing
    item = WishlistItem(user_id=user.id, product_id=data.product_id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/me/wishlist/{product_id}", status_code=204)
def remove_wishlist_item(product_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = db.query(WishlistItem).filter(WishlistItem.user_id == user.id, WishlistItem.product_id == product_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Wishlist item not found")
    db.delete(item)
    db.commit()


@router.post("/me/reviews", response_model=ReviewResponse, status_code=201)
def create_review(data: ReviewCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    product = db.query(Product).filter(Product.id == data.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    delivered_item = db.query(OrderItem).join(Order).outerjoin(OrderItem.vendor_order).filter(
        Order.user_id == user.id,
        OrderItem.product_id == product.id,
        ((VendorOrder.status == "DELIVERED") | (Order.status == "DELIVERED")),
    ).first()
    if not delivered_item:
        raise HTTPException(status_code=403, detail="Reviews require a delivered purchase")
    if db.query(ProductReview.id).filter(ProductReview.user_id == user.id, ProductReview.product_id == product.id).first():
        raise HTTPException(status_code=409, detail="You have already reviewed this product")
    review = ProductReview(user_id=user.id, product_id=product.id, order_id=delivered_item.order_id, rating=data.rating, body=data.body)
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


@router.get("/me/notifications", response_model=list[NotificationResponse])
def list_notifications(limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Notification).filter(Notification.user_id == user.id).order_by(Notification.id.desc()).limit(limit).all()


@router.put("/me/notifications/{notification_id}/read", response_model=NotificationResponse)
def mark_notification_read(notification_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    notification = db.query(Notification).filter(Notification.id == notification_id, Notification.user_id == user.id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    return notification
