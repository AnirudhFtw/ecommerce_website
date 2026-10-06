from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from config import settings

DATABASE_URL = settings.DATABASE_URL
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL env details not present")

if DATABASE_URL.startswith(("postgresql://", "postgres://")):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://" if DATABASE_URL.startswith("postgres://") else "postgresql://",
        "postgresql+psycopg2://",
        1
    )

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
