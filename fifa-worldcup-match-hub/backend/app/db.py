from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

_database_url = settings.database_url
# Render (and most hosts) hand out plain postgresql:// URLs, which SQLAlchemy resolves to the
# psycopg2 driver by default. We install psycopg (v3) instead, so force that dialect explicitly.
if _database_url.startswith("postgresql://") or _database_url.startswith("postgres://"):
    _database_url = _database_url.split("://", 1)[1]
    _database_url = f"postgresql+psycopg://{_database_url}"

connect_args = {"check_same_thread": False} if _database_url.startswith("sqlite") else {}
engine = create_engine(_database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401  (ensure models are registered)

    Base.metadata.create_all(bind=engine)
