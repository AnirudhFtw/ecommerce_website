from pydantic import BaseModel, ConfigDict
from app.schemas.payment import PaymentMode
from app.models.order import OrderStatus
from app.schemas.payment import PaymentMode

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

    model_config = ConfigDict(from_attributes=True)


class OrderResponse(BaseModel):
    id: int
    user_id: int
    total_amount: float
    status: str
    user: OrderUserResponse
    items: list[OrderItemResponse]

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