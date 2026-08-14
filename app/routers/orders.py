from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.cart import Cart, CartItem
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.schemas.order import CheckoutRequest, OrderResponse

from app.dependencies import get_current_user, get_current_admin
from app.models.order import Order, OrderItem, OrderStatus
from app.schemas.order import (
    OrderResponse,
    OrderStatusUpdate,
    OrderUserResponse
)
from app.schemas.payment import PaymentMode
from app.models.payment import Payment
from app.services import payment
from app.services.payment import create_razorpay_order



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

@router.post("/checkout", response_model=OrderResponse)
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

    payment = Payment(
        order_id=order.id,
        payment_mode=checkout.payment_mode.value,
        payment_status="PENDING",
        amount=total_amount
    )

    db.add(payment)

    if checkout.payment_mode == PaymentMode.ONLINE:
        razorpay_order = create_razorpay_order(
            amount=total_amount,
            receipt=f"order_{order.id}"
        )
    payment.razorpay_order_id = razorpay_order["id"]
    # --------------------------------
    # CREATE ORDER ITEMS
    # --------------------------------

    for cart_item in cart.items:

        product = db.query(Product).filter(
            Product.id == cart_item.product_id
        ).first()

        order_item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=cart_item.quantity,
            price=product.price
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

    for item in order.items:
        product = db.query(Product).filter(
            Product.id == item.product_id
        ).first()

        if product:
            product.stock += item.quantity

    order.status = OrderStatus.CANCELLED.value

    db.commit()
    db.refresh(order)

    return order