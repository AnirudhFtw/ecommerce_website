from datetime import datetime
from decimal import Decimal
from pydantic import EmailStr
from pydantic import BaseModel, ConfigDict, Field


class ReturnRequestCreate(BaseModel):
    order_id: int = Field(gt=0)
    reason: str = Field(min_length=5, max_length=2000)


class ReturnRequestReview(BaseModel):
    approved: bool
    refund_amount: Decimal | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, max_length=1000)


class ReturnRequestResponse(BaseModel):
    id: int
    order_id: int
    user_id: int
    reason: str
    status: str
    refund_amount: Decimal | None
    admin_note: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CouponCreate(BaseModel):
    code: str = Field(min_length=3, max_length=40)
    discount_type: str
    discount_value: Decimal = Field(gt=0)
    minimum_order_amount: Decimal = Field(default=Decimal("0"), ge=0)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    max_redemptions: int | None = Field(default=None, gt=0)
    is_active: bool = True


class CouponResponse(CouponCreate):
    id: int
    redemption_count: int
    model_config = ConfigDict(from_attributes=True)


class RefundProcessRequest(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0)


class PayoutRequest(BaseModel):
    amount: Decimal = Field(gt=0)


class SupportTicketCreate(BaseModel):
    subject: str = Field(min_length=3, max_length=160)
    message: str = Field(min_length=10, max_length=5000)


class SupportTicketReply(BaseModel):
    status: str = "CLOSED"
    admin_reply: str = Field(min_length=1, max_length=5000)
