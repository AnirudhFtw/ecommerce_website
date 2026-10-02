from pydantic import BaseModel, ConfigDict, Field


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1)
    price: float = Field(gt=0)
    stock: int = Field(ge=0)
    category_id: int = Field(gt=0)

    model_config = ConfigDict(str_strip_whitespace=True)


class ProductResponse(BaseModel):
    id: int
    name: str
    description: str | None
    price: float
    stock: int
    category_id: int
    vendor_id: int | None = None

    model_config = ConfigDict(from_attributes=True)

class ProductListResponse(BaseModel):
    products: list[ProductResponse]
    total: int
    page: int
    limit: int
    total_pages: int
