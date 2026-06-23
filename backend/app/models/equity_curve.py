"""
app.models.equity_curve
-----------------------
EquityCurve: live (not backtest) equity samples for the dashboard chart.
One row per tick (e.g. every 5 minutes during market hours).
"""
from datetime import datetime
from sqlalchemy import DateTime, Float, Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EquityCurve(Base):
    __tablename__ = "equity_curve"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    equity: Mapped[float] = mapped_column(Float, nullable=False)
    available_margin: Mapped[float] = mapped_column(Float, nullable=False)
    open_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    realized_pnl_day: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    __table_args__ = (
        Index("ix_equity_curve_user_ts", "user_id", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<EquityCurve ts={self.timestamp} equity={self.equity}>"
