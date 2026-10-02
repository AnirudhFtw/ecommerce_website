from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.database import get_db
from app.dependencies import get_current_user, get_current_admin
from app.models.user import User
from app.models.cart import Cart
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
    verify_razorpay_signature,
)
from config import settings



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

@router.post("/checkout", response_model=CheckoutResponse)
def checkout(
    checkout: CheckoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    cart = db.query(Cart).filter(
        Cart.user_id == current_user.id
    ).first()

    if not cart or not cart.items:
        raise HTTPException(
            status_code=400,
            detail="Cart is empty"
        )

    total_amount = 0

    # Validate products and stock
    vendor_orders = {}
    for cart_item in cart.items:

        product = db.query(Product).filter(
            Product.id == cart_item.product_id
        ).first()

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

        total_amount += (
            product.price * cart_item.quantity
        )

    # --------------------------------
    # CREATE ORDER
    # --------------------------------

    if checkout.payment_mode == PaymentMode.COD:

        order_status = "CONFIRMED"
        reserved_until = None

    else:

        order_status = "PENDING"
        reserved_until = datetime.utcnow() + timedelta(minutes=15)

    order = Order(
        user_id=current_user.id,
        total_amount=total_amount,
        status=order_status,
        reserved_until=reserved_until
    )

    db.add(order)
    db.flush()

    # --------------------------------
    # CREATE PAYMENT
    # --------------------------------

    payment_record = Payment(
        order_id=order.id,
        payment_mode=checkout.payment_mode.value,
        payment_status="PENDING",
        amount=total_amount
    )

    db.add(payment_record)

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
            price=product.price,
            vendor_order_id=vendor_orders[product.vendor_id].id,
        )

        db.add(order_item)

        # COD → permanently reduce stock now
        #
        # ONLINE → temporarily reserve stock now
        #
        # In our current simple implementation,
        # reservation is represented by reducing stock.
        product.stock -= cart_item.quantity

    # --------------------------------
    # CART
    # --------------------------------

    # COD → payment doesn't need to happen online,
    # so checkout is complete and cart can be cleared.

    if checkout.payment_mode == PaymentMode.COD:

        for cart_item in cart.items:
            db.delete(cart_item)

    # ONLINE → KEEP CART UNTIL PAYMENT SUCCEEDS

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
        payment_record.payment_status = "FAILED"
        order.status = OrderStatus.CANCELLED.value
        for item in order.items:
            item.product.stock += item.quantity
        for vendor_order in order.vendor_orders:
            vendor_order.status = OrderStatus.CANCELLED.value
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

    cart = db.query(Cart).filter(Cart.user_id == current_user.id).first()
    if cart:
        purchased_quantities = {}
        for line in order.items:
            purchased_quantities[line.product_id] = purchased_quantities.get(line.product_id, 0) + line.quantity
        for cart_item in list(cart.items):
            purchased = purchased_quantities.get(cart_item.product_id, 0)
            original_quantity = cart_item.quantity
            consumed = min(purchased, original_quantity)
            if consumed == original_quantity:
                db.delete(cart_item)
            elif consumed > 0:
                cart_item.quantity -= consumed
            purchased_quantities[cart_item.product_id] = purchased - consumed

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
