import hashlib
import hmac
import json
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.customer import Notification
from app.models.extras import ReturnRequest
from app.models.order import OrderStatus
from app.models.payment import Payment
from config import settings


router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/razorpay/webhook")
async def razorpay_webhook(
    request: Request,
    db: Session = Depends(get_db),
    signature: str | None = Header(default=None, alias="X-Razorpay-Signature"),
):
    secret = settings.RAZORPAY_WEBHOOK_SECRET
    if not secret:
        raise HTTPException(status_code=503, detail="Razorpay webhook env details not present")
    body = await request.body()
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=400, detail="Invalid Razorpay webhook signature")
    try:
        event = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook payload") from exc

    event_type = event.get("event")
    if event_type not in {"refund.processed", "refund.failed"}:
        return {"received": True, "handled": False}

    refund = event.get("payload", {}).get("refund", {}).get("entity", {})
    refund_id = refund.get("id")
    gateway_payment_id = refund.get("payment_id")
    query = db.query(Payment).filter(Payment.payment_mode == "ONLINE")
    payment = query.filter(Payment.refund_id == refund_id).first() if refund_id else None
    if payment is None and gateway_payment_id:
        payment = query.filter(Payment.razorpay_payment_id == gateway_payment_id).first()
    if payment is None:
        # Razorpay can retry the notification; acknowledge unknown/late events
        # so they do not cause an endless retry storm.
        return {"received": True, "handled": False}
    if payment.refund_id and refund_id and payment.refund_id != refund_id:
        return {"received": True, "handled": False}
    if payment.payment_status in {"REFUNDED", "PARTIALLY_REFUNDED"}:
        return {"received": True, "handled": True, "status": payment.payment_status}

    if event_type == "refund.failed":
        payment.refund_id = None
        payment.refund_amount = None
        payment.payment_status = "REFUND_PENDING"
        db.commit()
        return {"received": True, "handled": True, "status": payment.payment_status}

    amount = Decimal(str(refund.get("amount", 0))) / Decimal("100")
    if amount <= 0 or amount > Decimal(str(payment.amount)):
        raise HTTPException(status_code=400, detail="Refund amount is invalid")
    payment.refund_id = refund_id
    payment.refund_amount = amount
    payment.payment_status = "REFUNDED" if amount >= Decimal(str(payment.amount)) else "PARTIALLY_REFUNDED"
    if payment.payment_status == "REFUNDED":
        payment.order.status = OrderStatus.REFUNDED.value
        for vendor_order in payment.order.vendor_orders:
            if vendor_order.status == "RETURNED":
                vendor_order.status = OrderStatus.REFUNDED.value
    return_request = db.query(ReturnRequest).filter(
        ReturnRequest.order_id == payment.order_id,
        ReturnRequest.status == "APPROVED",
    ).first()
    if return_request:
        return_request.status = payment.payment_status
    db.add(Notification(
        user_id=payment.order.user_id,
        kind="REFUND",
        title="Refund processed",
        message=f"Refund for order #{payment.order_id} was processed.",
    ))
    db.commit()
    return {"received": True, "handled": True, "status": payment.payment_status}
