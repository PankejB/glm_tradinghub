"""
app.models.user
---------------
User ORM model. Holds auth credentials + current paper-trading equity.
"""
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # Paper-trading equity / margin
    # In live mode these mirror what the broker reports.
    starting_capital: Mapped[float] = mapped_column(Float, default=1_000_000.0, nullable=False)
    current_equity: Mapped[float] = mapped_column(Float, default=1_000_000.0, nullable=False)
    available_margin: Mapped[float] = mapped_column(Float, default=1_000_000.0, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} equity={self.current_equity}>"
