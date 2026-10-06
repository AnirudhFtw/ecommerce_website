from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from pydantic import EmailStr


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    bio: str | None = Field(default=None, max_length=1000)


class ProfileResponse(BaseModel):
    id: int
    name: str
    email: str
    phone: str | None
    bio: str | None
    email_verified: bool
    phone_verified: bool
    model_config = ConfigDict(from_attributes=True)


class AddressCreate(BaseModel):
    label: str = Field(default="Home", max_length=40)
    recipient_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=5, max_length=30)
    address_line1: str = Field(min_length=1, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    postal_code: str = Field(min_length=3, max_length=20)
    country: str = Field(default="India", max_length=80)
    is_default: bool = False


class AddressResponse(AddressCreate):
    id: int
    user_id: int
    model_config = ConfigDict(from_attributes=True)


class WalletResponse(BaseModel):
    balance: Decimal
    model_config = ConfigDict(from_attributes=True)


class WalletTransactionResponse(BaseModel):
    id: int
    amount: Decimal
    transaction_type: str
    reason: str
    reference: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ProductSummary(BaseModel):
    id: int
    name: str
    price: float
    stock: int
    model_config = ConfigDict(from_attributes=True)


class WishlistCreate(BaseModel):
    product_id: int = Field(gt=0)


class WishlistItemResponse(BaseModel):
    id: int
    product_id: int
    created_at: datetime
    product: ProductSummary
    model_config = ConfigDict(from_attributes=True)


class ReviewCreate(BaseModel):
    product_id: int = Field(gt=0)
    rating: int = Field(ge=1, le=5)
    body: str | None = Field(default=None, max_length=2000)


class ReviewResponse(BaseModel):
    id: int
    user_id: int
    product_id: int
    rating: int
    body: str | None
    is_approved: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class NotificationResponse(BaseModel):
    id: int
    kind: str
    title: str
    message: str
    is_read: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class RefundStatusResponse(BaseModel):
    order_id: int
    payment_status: str
    refund_amount: Decimal | None
    refund_id: str | None


class VendorProfileUpdate(BaseModel):
    shop_name: str = Field(min_length=2, max_length=150)
    vendor_application_note: str | None = Field(default=None, max_length=500)


class AccountTokenRequest(BaseModel):
    token: str = Field(min_length=20, max_length=256)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordReset(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)
