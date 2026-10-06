from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.user import User
from app.dependencies import get_current_admin
from app.database import get_db
from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryResponse


router = APIRouter(
    prefix="/categories",
    tags=["Categories"]
)


@router.post("/", response_model=CategoryResponse)
def create_category(
    category: CategoryCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    existing = db.query(Category).filter(
        Category.name == category.name
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Category already exists"
        )

    if category.parent_id is not None and not db.query(Category.id).filter(Category.id == category.parent_id).first():
        raise HTTPException(status_code=404, detail="Parent category not found")

    new_category = Category(
        name=category.name,
        parent_id=category.parent_id,
    )

    db.add(new_category)
    db.commit()
    db.refresh(new_category)

    return new_category


@router.get("/", response_model=list[CategoryResponse])
def get_categories(
    db: Session = Depends(get_db)
):
    return db.query(Category).all()


@router.put("/{category_id}", response_model=CategoryResponse)
def update_category(category_id: int, data: CategoryCreate, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    duplicate = db.query(Category.id).filter(Category.name == data.name, Category.id != category_id).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Category name already exists")
    if data.parent_id == category_id:
        raise HTTPException(status_code=400, detail="A category cannot be its own parent")
    parent = db.query(Category).filter(Category.id == data.parent_id).first() if data.parent_id is not None else None
    if data.parent_id is not None and not parent:
        raise HTTPException(status_code=404, detail="Parent category not found")
    ancestor = parent
    while ancestor:
        if ancestor.id == category_id:
            raise HTTPException(status_code=400, detail="Category hierarchy cannot contain a cycle")
        ancestor = ancestor.parent
    category.name = data.name
    category.parent_id = data.parent_id
    db.commit()
    db.refresh(category)
    return category
