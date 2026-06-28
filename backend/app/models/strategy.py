"""
app.models.strategy
-------------------
Strategy registry. Each row corresponds to one of the three Fitschen strategies.
"""
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Float, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)

    # 'stock_counter_trend' | 'mcx_trend_following' | 'index_bar_scoring'
    strategy_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Human-readable Fitschen chapter reference, e.g. "Ch 5/6 Counter-Trend Stocks"
    book_reference: Mapped[str] = mapped_column(String(255), nullable=True)

    # Asset classes this strategy is allowed to trade (JSON list)
    # e.g. ["NSE_EQ", "NSE_FNO"] or ["MCX_COMMODITY"]
    allowed_segments: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Tunable parameters (JSON), per-strategy defaults defined in Step 4.
    parameters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Tradeability gate (Fitschen GtP > 1.5 rule)
    # Computed by Backtester and cached here for the dashboard.
    latest_gtp_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_tradeable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    description: Mapped[str] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<Strategy id={self.id} slug={self.slug!r} type={self.strategy_type}>"
