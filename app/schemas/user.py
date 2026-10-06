from pydantic import BaseModel, EmailStr, ConfigDict, Field


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    is_admin: bool
    is_vendor: bool = False
    vendor_application_status: str = "NONE"
    shop_name: str | None = None
    email_verified: bool = False

    model_config = ConfigDict(from_attributes=True)


class VendorApplicationCreate(BaseModel):
    shop_name: str
    note: str | None = None


class VendorApplicationReview(BaseModel):
    approved: bool
    note: str | None = None


class Token(BaseModel):
    access_token: str
    token_type: str
