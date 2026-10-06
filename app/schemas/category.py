from pydantic import BaseModel, ConfigDict


class CategoryCreate(BaseModel):
    name: str
    parent_id: int | None = None


class CategoryResponse(BaseModel):
    id: int
    name: str
    parent_id: int | None = None

    model_config = ConfigDict(from_attributes=True)
