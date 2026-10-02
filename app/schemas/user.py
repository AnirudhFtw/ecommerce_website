from pydantic import BaseModel, EmailStr, ConfigDict


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str


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
