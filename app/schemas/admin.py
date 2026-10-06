from pydantic import BaseModel, Field


class ProductApprovalUpdate(BaseModel):
    approved: bool


class ReviewModerationUpdate(BaseModel):
    approved: bool


class WalletAdjustment(BaseModel):
    amount: float = Field(gt=0, le=100000)
    reason: str = Field(min_length=3, max_length=80)


class AdminRoleUpdate(BaseModel):
    is_admin: bool


class AdminNotificationCreate(BaseModel):
    kind: str = Field(min_length=2, max_length=40)
    title: str = Field(min_length=2, max_length=160)
    message: str = Field(min_length=2, max_length=2000)
    user_id: int | None = Field(default=None, gt=0)
