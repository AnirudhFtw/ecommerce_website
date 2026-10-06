from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from decimal import Decimal

from app.database import get_db
from app.dependencies import get_current_user, get_current_admin
from app.models.user import User
from app.models.cart import Cart
from app.models.customer import UserAddress, Wallet, WalletTransaction
from app.models.extras import Coupon, SiteSetting
from app.models.order import Order, OrderItem, VendorOrder
from app.models.product import Product
from app.schemas.order import (
    CheckoutRequest,
    CheckoutResponse,
    OrderResponse,
    OrderStatusUpdate,
    RazorpayPaymentVerification,
)
from app.models.order import OrderStatus
from app.schemas.payment import PaymentMode
from app.models.payment import Payment
from app.services.payment import (
    create_razorpay_order,
    fetch_razorpay_payment,
    razorpay_is_configured,
    verify_razorpay_signature,
)
from config import settings
from app.services.notifications import create_notification, notify_admins



router = APIRouter(
    prefix="/orders",
    tags=["Orders"]
)


@router.get("/", response_model=list[OrderResponse])
def get_all_orders(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    return db.query(Order).order_by(Order.id.desc()).all()

@router.get("/myorders", response_model=list[OrderResponse])
def get_my_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return db.query(Order).filter(
        Order.user_id == current_user.id
    ).order_by(Order.id.desc()).all()


@router.get("/{order_id}/tracking")
def track_order(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == user.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"order_id": order.id, "status": order.status, "created_at": order.created_at, "vendor_orders": [
        {"id": item.id, "vendor_id": item.vendor_id, "status": item.status, "tracking_number": item.tracking_number, "shipping_provider": item.shipping_provider}
        for item in order.vendor_orders
    ]}


@router.get("/{order_id}/invoice")
def get_invoice(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == user.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return {
        "invoice_number": f"INV-{order.id:08d}",
        "order_id": order.id,
        "created_at": order.created_at,
        "customer": {"name": order.user.name, "email": order.user.email},
        "shipping_address": order.shipping_address,
        "items": [{"product_id": item.product_id, "name": item.product.name, "quantity": item.quantity, "unit_price": item.price, "line_total": round(item.quantity * item.price, 2)} for item in order.items],
        "subtotal": round(sum(item.quantity * item.price for item in order.items), 2),
        "discount": order.discount_amount,
        "tax": order.tax_amount,
        "shipping": order.shipping_amount,
        "total": order.total_amount,
    }

@router.post("/checkout", response_model=CheckoutResponse)
def checkout(
    checkout: CheckoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if checkout.payment_mode == PaymentMode.ONLINE and not razorpay_is_configured():
        raise HTTPException(status_code=503, detail="Razorpay env details not present")
    cart = db.query(Cart).filter(
        Cart.user_id == current_user.id
    ).first()

    if not cart or not cart.items:
        raise HTTPException(
            status_code=400,
            detail="Cart is empty"
        )

    shipping_address = None
    selected_address = None
    if checkout.address_id is not None:
        selected_address = db.query(UserAddress).filter(
            UserAddress.id == checkout.address_id,
            UserAddress.user_id == current_user.id,
        ).first()
    elif not checkout.address_line1:
        selected_address = db.query(UserAddress).filter(
            UserAddress.user_id == current_user.id,
            UserAddress.is_default.is_(True),
        ).first()
        if not selected_address:
            selected_address = db.query(UserAddress).filter(
                UserAddress.user_id == current_user.id,
            ).order_by(UserAddress.id).first()

    if selected_address:
        shipping_parts = [
            selected_address.recipient_name, selected_address.phone,
            selected_address.address_line1, selected_address.address_line2,
            selected_address.city, selected_address.state,
            selected_address.postal_code, selected_address.country,
        ]
        shipping_address = ", ".join(part for part in shipping_parts if part)
    elif checkout.address_line1:
        required = {
            "recipient_name": checkout.recipient_name,
            "phone": checkout.phone or current_user.phone,
            "city": checkout.city,
            "state": checkout.state,
            "postal_code": checkout.postal_code,
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise HTTPException(status_code=422, detail=f"Delivery address is incomplete; missing: {', '.join(missing)}")
        shipping_address = ", ".join(part for part in [
            required["recipient_name"], required["phone"], checkout.address_line1,
            checkout.address_line2, required["city"], required["state"],
            required["postal_code"], checkout.country,
        ] if part)
        if checkout.save_address:
            has_saved_address = db.query(UserAddress.id).filter(UserAddress.user_id == current_user.id).first() is not None
            db.add(UserAddress(
                user_id=current_user.id,
                recipient_name=required["recipient_name"], phone=required["phone"],
                address_line1=checkout.address_line1, address_line2=checkout.address_line2,
                city=required["city"], state=required["state"], postal_code=required["postal_code"],
                country=checkout.country, is_default=not has_saved_address,
            ))
    elif checkout.address_id is not None:
        raise HTTPException(status_code=404, detail="Saved address not found for this account. Choose one of your saved addresses or enter a delivery address.")
    else:
        raise HTTPException(status_code=422, detail="No delivery address found. Add an address to your profile or enter one at checkout.")

    subtotal = 0.0

    # Validate products and stock
    vendor_orders = {}
    for cart_item in cart.items:

        product = db.query(Product).filter(
            Product.id == cart_item.product_id,
            Product.is_active.is_(True),
            Product.is_approved.is_(True),
        ).with_for_update().first()

        if not product:
            raise HTTPException(
                status_code=404,
                detail="Product not found"
            )

        if cart_item.quantity > product.stock:
            raise HTTPException(
                status_code=400,
                detail=f"Not enough stock for {product.name}"
            )

        effective_price = round(product.price * (1 - float(product.discount_percent or 0) / 100), 2)
        subtotal += effective_price * cart_item.quantity

    coupon = None
    discount_amount = 0.0
    if checkout.coupon_code:
        coupon = db.query(Coupon).filter(Coupon.code == checkout.coupon_code.strip().upper()).with_for_update().first()
        now = datetime.utcnow()
        if not coupon or not coupon.is_active:
            raise HTTPException(status_code=400, detail="Coupon is invalid")
        if coupon.starts_at and coupon.starts_at > now or coupon.ends_at and coupon.ends_at < now:
            raise HTTPException(status_code=400, detail="Coupon is not currently active")
        if coupon.max_redemptions is not None and coupon.redemption_count >= coupon.max_redemptions:
            raise HTTPException(status_code=400, detail="Coupon redemption limit reached")
        if subtotal < float(coupon.minimum_order_amount):
            raise HTTPException(status_code=400, detail="Order does not meet the coupon minimum")
        if coupon.discount_type == "PERCENT":
            discount_amount = round(subtotal * float(coupon.discount_value) / 100, 2)
        elif coupon.discount_type == "FIXED":
            discount_amount = min(subtotal, float(coupon.discount_value))
        else:
            raise HTTPException(status_code=400, detail="Coupon configuration is invalid")
    total_amount = round(subtotal - discount_amount, 2)
    site_settings = {row.key: row.value for row in db.query(SiteSetting).filter(SiteSetting.key.in_(["tax_percent", "shipping_flat"])).all()}
    tax_percent = float(site_settings.get("tax_percent", 0))
    shipping_amount = float(site_settings.get("shipping_flat", 0))
    tax_amount = round(total_amount * tax_percent / 100, 2)
    total_amount = round(total_amount + tax_amount + shipping_amount, 2)
    if checkout.payment_mode == PaymentMode.ONLINE and total_amount <= 0:
        raise HTTPException(status_code=400, detail="Online orders must have a positive total")

    # --------------------------------
    # CREATE ORDER
    # --------------------------------

    wallet = None
    if checkout.payment_mode == PaymentMode.WALLET:
        wallet = db.query(Wallet).filter(Wallet.user_id == current_user.id).with_for_update().first()
        if not wallet or wallet.balance < Decimal(str(round(total_amount, 2))):
            raise HTTPException(status_code=400, detail="Insufficient wallet balance")

    if checkout.payment_mode in {PaymentMode.COD, PaymentMode.WALLET}:

        order_status = "CONFIRMED"
        reserved_until = None

    else:

        order_status = "PENDING"
        reserved_until = datetime.utcnow() + timedelta(minutes=15)

    order = Order(
        user_id=current_user.id,
        total_amount=total_amount,
        status=order_status,
        reserved_until=reserved_until,
        shipping_address=shipping_address,
        coupon_code=coupon.code if coupon else None,
        discount_amount=discount_amount,
        tax_amount=tax_amount,
        shipping_amount=shipping_amount,
    )

    db.add(order)
    db.flush()

    # --------------------------------
    # CREATE PAYMENT
    # --------------------------------

    payment_record = Payment(
        order_id=order.id,
        payment_mode=checkout.payment_mode.value,
        payment_status="PAID" if checkout.payment_mode == PaymentMode.WALLET else "PENDING",
        amount=total_amount
    )

    db.add(payment_record)
    if coupon:
        coupon.redemption_count += 1

    if checkout.payment_mode == PaymentMode.WALLET and wallet:
        debit = Decimal(str(round(total_amount, 2)))
        wallet.balance -= debit
        db.add(WalletTransaction(
            wallet_id=wallet.id,
            amount=debit,
            transaction_type="DEBIT",
            reason="ORDER_PAYMENT",
            reference=f"order:{order.id}",
        ))

    if checkout.payment_mode == PaymentMode.ONLINE:
        razorpay_order = create_razorpay_order(
            amount=total_amount,
            receipt=f"order_{order.id}"
        )
        payment_record.razorpay_order_id = razorpay_order["id"]
    # --------------------------------
    # CREATE ORDER ITEMS
    # --------------------------------

    for cart_item in cart.items:

        product = db.query(Product).filter(
            Product.id == cart_item.product_id
        ).first()

        if product.vendor_id not in vendor_orders:
            vendor_order = VendorOrder(
                order_id=order.id,
                vendor_id=product.vendor_id,
                status=order_status,
            )
            db.add(vendor_order)
            db.flush()
            vendor_orders[product.vendor_id] = vendor_order

        order_item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=cart_item.quantity,
            price=round(product.price * (1 - float(product.discount_percent or 0) / 100), 2),
            vendor_order_id=vendor_orders[product.vendor_id].id,
        )

        db.add(order_item)

        # COD → permanently reduce stock now
        #
        # ONLINE → temporarily reserve stock now
        #
        # In our current simple implementation,
        # reservation is represented by reducing stock.
        previous_stock = product.stock
        product.stock -= cart_item.quantity
        if previous_stock > product.low_stock_threshold >= product.stock:
            if product.vendor_id:
                create_notification(db, product.vendor_id, "LOW_STOCK", "Product low on stock", f"'{product.name}' is low on stock.")
            notify_admins(db, "LOW_STOCK", "Product low on stock", f"'{product.name}' has {product.stock} units remaining.")

    # --------------------------------
    # CART
    # --------------------------------

    # The order now owns a snapshot of every cart line, so clear the cart for
    # every payment mode. A later payment callback must not delete new cart items.
    for cart_item in list(cart.items):
        db.delete(cart_item)

    create_notification(db, current_user.id, "ORDER", "Order placed", f"Order #{order.id} has been placed.")
    for vendor_order in order.vendor_orders:
        if vendor_order.vendor_id:
            create_notification(db, vendor_order.vendor_id, "ORDER", "New order", f"You have a new order #{order.id}.")
    db.commit()
    db.refresh(order)

    return {
        "order": order,
        "payment_mode": checkout.payment_mode,
        "razorpay_order_id": payment_record.razorpay_order_id,
        "razorpay_key_id": settings.RAZORPAY_KEY_ID if checkout.payment_mode == PaymentMode.ONLINE else None,
        "amount": total_amount,
    }


@router.post("/{order_id}/payment/verify", response_model=OrderResponse)
def verify_payment(
    order_id: int,
    verification: RazorpayPaymentVerification,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.user_id == current_user.id,
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    payment_record = order.payment
    if not payment_record or payment_record.payment_mode != PaymentMode.ONLINE.value:
        raise HTTPException(status_code=400, detail="Order does not have an online payment")
    if verification.razorpay_order_id != payment_record.razorpay_order_id:
        raise HTTPException(status_code=400, detail="Payment order does not match")
    if not verify_razorpay_signature(
        verification.razorpay_order_id,
        verification.razorpay_payment_id,
        verification.razorpay_signature,
    ):
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    try:
        gateway_payment = fetch_razorpay_payment(verification.razorpay_payment_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Could not verify payment status with Razorpay") from exc
    if (
        gateway_payment.get("order_id") != payment_record.razorpay_order_id
        or gateway_payment.get("amount") != int(round(order.total_amount * 100))
        or gateway_payment.get("currency") != "INR"
    ):
        raise HTTPException(status_code=400, detail="Payment details do not match this order")
    if gateway_payment.get("status") != "captured":
        raise HTTPException(status_code=409, detail="Payment is not captured yet")

    if order.reserved_until and datetime.utcnow() > order.reserved_until:
        payment_record.payment_status = "REFUND_PENDING"
        payment_record.razorpay_payment_id = verification.razorpay_payment_id
        order.status = OrderStatus.CANCELLED.value
        if order.coupon_code:
            expired_coupon = db.query(Coupon).filter(Coupon.code == order.coupon_code).with_for_update().first()
            if expired_coupon and expired_coupon.redemption_count > 0:
                expired_coupon.redemption_count -= 1
        for item in order.items:
            item.product.stock += item.quantity
        for vendor_order in order.vendor_orders:
            vendor_order.status = OrderStatus.CANCELLED.value
        create_notification(db, current_user.id, "REFUND", "Payment needs a refund", f"Payment for expired order #{order.id} requires a refund.")
        notify_admins(db, "REFUND", "Expired order payment", f"Captured payment for expired order #{order.id} requires a refund.")
        db.commit()
        raise HTTPException(status_code=409, detail="Payment reservation has expired; start checkout again")

    if payment_record.payment_status == "PAID":
        if payment_record.razorpay_payment_id != verification.razorpay_payment_id:
            raise HTTPException(status_code=409, detail="Order is already paid with a different payment")
        return order
    if payment_record.payment_status != "PENDING":
        raise HTTPException(status_code=409, detail="Payment is not pending")

    payment_record.payment_status = "PAID"
    payment_record.razorpay_payment_id = verification.razorpay_payment_id
    order.status = OrderStatus.CONFIRMED.value
    order.reserved_until = None
    for vendor_order in order.vendor_orders:
        vendor_order.status = OrderStatus.CONFIRMED.value
        if vendor_order.vendor_id:
            create_notification(db, vendor_order.vendor_id, "PAYMENT", "Order ready to process", f"Order #{order.id} payment was confirmed.")
    create_notification(db, current_user.id, "PAYMENT", "Payment confirmed", f"Payment for order #{order.id} was captured.")

    db.commit()
    db.refresh(order)
    return order

@router.put("/{order_id}/status", response_model=OrderResponse)
def update_order_status(
    order_id: int,
    status_data: OrderStatusUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    order = db.query(Order).filter(
        Order.id == order_id
    ).first()

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    order.status = status_data.status.value

    db.commit()
    db.refresh(order)

    return order

@router.put("/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.user_id == current_user.id
    ).first()

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    if order.status not in ["PENDING", "CONFIRMED"]:
        raise HTTPException(
            status_code=400,
            detail="Order cannot be cancelled"
        )

    if any(
        vendor_order.status not in {"PENDING", "CONFIRMED"}
        for vendor_order in order.vendor_orders
    ):
        raise HTTPException(
            status_code=400,
            detail="Order cannot be cancelled after vendor processing has started",
        )

    if order.payment and order.payment.payment_status == "PAID":
        order.payment.payment_status = "REFUND_PENDING"
    elif order.payment and order.payment.payment_status == "PENDING":
        order.payment.payment_status = "FAILED" if order.payment.payment_mode == PaymentMode.ONLINE.value else "CANCELLED"

    if order.coupon_code:
        coupon = db.query(Coupon).filter(Coupon.code == order.coupon_code).with_for_update().first()
        if coupon and coupon.redemption_count > 0:
            coupon.redemption_count -= 1

    for item in order.items:
        product = db.query(Product).filter(
            Product.id == item.product_id
        ).first()

        if product:
            product.stock += item.quantity

    order.status = OrderStatus.CANCELLED.value
    for vendor_order in order.vendor_orders:
        vendor_order.status = OrderStatus.CANCELLED.value

    db.commit()
    db.refresh(order)

    return order
