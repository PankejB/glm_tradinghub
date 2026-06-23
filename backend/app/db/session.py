"""
app.db.session
--------------
Engine + SessionLocal + get_db FastAPI dependency.
Uses psycopg2 (sync) so Celery workers can share the same engine.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings

# pool_pre_ping: detects dropped connections
# pool_recycle: recycle connections every 30min (Postgres default idle timeout is ~1h)
engine = create_engine(
    settings.DB_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=10,
    max_overflow=20,
    echo=(settings.APP_ENV == "development"),
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db():
    """FastAPI dependency that yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Create all tables. Used in dev / for first-run bootstrap.
    In production prefer Alembic migrations.
    """
    # Import models so they are registered on Base.metadata before create_all
    from app.db.base import Base  # noqa: WPS433 (local import is intentional)
    from app.models import (  # noqa: WPS433, F401
        user, strategy, trade_log, backtest_result, equity_curve, ohlcv_bar
    )

    Base.metadata.create_all(bind=engine)
