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
    items: list[OrderItemResponse]

    model_config = ConfigDict(from_attributes=True)


class OrderResponse(BaseModel):
    id: int
    user_id: int
    total_amount: float
    status: str
    user: OrderUserResponse
    items: list[OrderItemResponse]
    vendor_orders: list[VendorOrderResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class OrderStatusUpdate(BaseModel):
    status: OrderStatus

class CheckoutRequest(BaseModel):
    payment_mode: PaymentMode


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
