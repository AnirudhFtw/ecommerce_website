from fastapi import FastAPI

from app.routers.products import router as product_router
from app.routers.categories import router as category_router
from app.routers.auth import router as auth_router
from app.routers.cart import router as cart_router
from app.routers.orders import router as order_router


app = FastAPI(
    title="E-Commerce API",
    description="Backend API for an e-commerce application",
    version="1.0.0"
)


app.include_router(product_router)
app.include_router(category_router)
app.include_router(auth_router)
app.include_router(cart_router)
app.include_router(order_router)

@app.get("/")
def home():
    return {"message": "E-Commerce API is running"}