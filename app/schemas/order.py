from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.payment import PaymentMode
from app.models.order import OrderStatus

class OrderUserResponse(BaseModel):
    id: int
    name: str
    email: str

    model_config = ConfigDict(from_attributes=True)

class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    price: float
    vendor_order_id: int | None = None

    model_config = ConfigDict(from_attributes=True)


class VendorOrderResponse(BaseModel):
    id: int
    order_id: int
    vendor_id: int | None
    status: str
    tracking_number: str | None = None
    shipping_provider: str | None = None
    items: list[OrderItemResponse]

    model_config = ConfigDict(from_attributes=True)


class OrderResponse(BaseModel):
    id: int
    user_id: int
    total_amount: float
    status: str
    created_at: datetime | None = None
    shipping_address: str | None = None
    coupon_code: str | None = None
    discount_amount: float = 0
    tax_amount: float = 0
    shipping_amount: float = 0
    user: OrderUserResponse
    items: list[OrderItemResponse]
    vendor_orders: list[VendorOrderResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class VendorOrderStatusUpdate(BaseModel):
    status: OrderStatus
    tracking_number: str | None = Field(default=None, max_length=120)
    shipping_provider: str | None = Field(default=None, max_length=120)

class CheckoutRequest(BaseModel):
    payment_mode: PaymentMode
    address_id: int | None = None
    # Checkout may use a saved address or collect a delivery address inline.
    recipient_name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, min_length=5, max_length=30)
    address_line1: str | None = Field(default=None, min_length=1, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    state: str | None = Field(default=None, min_length=1, max_length=100)
    postal_code: str | None = Field(default=None, min_length=3, max_length=20)
    country: str = Field(default="India", max_length=80)
    save_address: bool = False
    coupon_code: str | None = None


class CheckoutResponse(BaseModel):
    order: OrderResponse
    payment_mode: PaymentMode
    razorpay_order_id: str | None = None
    razorpay_key_id: str | None = None
    amount: float
    currency: str = "INR"


class RazorpayPaymentVerification(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
