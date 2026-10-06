from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from config import settings
from app.middleware.rate_limit import RateLimitMiddleware

from app.routers.products import router as product_router
from app.routers.categories import router as category_router
from app.routers.auth import router as auth_router
from app.routers.cart import router as cart_router
from app.routers.orders import router as order_router
from app.routers.vendors import router as vendor_router
from app.routers.customers import router as customer_router
from app.routers.admin import router as admin_router
from app.routers.payments import router as payment_router


app = FastAPI(
    title="E-Commerce API",
    description="Backend API for an e-commerce application",
    version="1.0.0"
)

media_dir = Path(__file__).resolve().parent / "static"
media_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=media_dir), name="media")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(RateLimitMiddleware)


app.include_router(product_router)
app.include_router(category_router)
app.include_router(auth_router)
app.include_router(cart_router)
app.include_router(order_router)
app.include_router(vendor_router)
app.include_router(customer_router)
app.include_router(admin_router)
app.include_router(payment_router)

@app.get("/")
def home():
    return {"message": "E-Commerce API is running"}
