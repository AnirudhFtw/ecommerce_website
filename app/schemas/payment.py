from enum import Enum
from pydantic import BaseModel


class PaymentMode(str, Enum):
    ONLINE = "ONLINE"
    COD = "COD"


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
    REFUND_PENDING = "REFUND_PENDING"


class PaymentCreate(BaseModel):
    payment_mode: PaymentMode


class RazorpayOrderResponse(BaseModel):
    order_id: int
    razorpay_order_id: str
    razorpay_key_id: str
    amount: float
    currency: str
