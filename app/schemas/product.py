from pydantic import BaseModel, ConfigDict, Field


class ProductImageResponse(BaseModel):
    id: int
    image_url: str
    alt_text: str | None
    sort_order: int
    model_config = ConfigDict(from_attributes=True)


class ProductSpecificationResponse(BaseModel):
    id: int
    name: str
    value: str
    model_config = ConfigDict(from_attributes=True)


class ProductSpecificationInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=1000)


class ProductSpecificationsUpdate(BaseModel):
    items: list[ProductSpecificationInput] = Field(max_length=30)


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1)
    price: float = Field(gt=0)
    stock: int = Field(ge=0)
    category_id: int = Field(gt=0)
    discount_percent: float = Field(default=0, ge=0, le=100)
    low_stock_threshold: int = Field(default=5, ge=0)

    model_config = ConfigDict(str_strip_whitespace=True)


class ProductResponse(BaseModel):
    id: int
    name: str
    description: str | None
    price: float
    stock: int
    category_id: int
    vendor_id: int | None = None
    is_active: bool = True
    is_approved: bool = True
    discount_percent: float = 0
    low_stock_threshold: int = 5
    images: list[ProductImageResponse] = Field(default_factory=list)
    specifications: list[ProductSpecificationResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

class ProductListResponse(BaseModel):
    products: list[ProductResponse]
    total: int
    page: int
    limit: int
    total_pages: int
