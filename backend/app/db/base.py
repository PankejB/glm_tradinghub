"""
app.db.base
-----------
SQLAlchemy declarative Base. All ORM models inherit from this.
"""
from sqlalchemy.orm import declarative_base, DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


# Convenience alias for legacy style: `class Foo(Base):`
Base = declarative_base()  # type: ignore[assignment]
