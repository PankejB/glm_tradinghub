"""
app.models.trade_log
--------------------
TradeLog: one row per executed trade (entry + exit), for both backtest & live.
"""
from datetime import datetime
from sqlalchemy import (
    String, DateTime, Float, Integer, JSON, Text, ForeignKey, Boolean, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TradeLog(Base):
    __tablename__ = "trade_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )

    # 'backtest' or 'live'
    mode: Mapped[str] = mapped_column(String(20), default="backtest", nullable=False)

    # Broker / segment info
    segment: Mapped[str] = mapped_column(String(20), nullable=False)  # NSE_EQ, NSE_FNO, MCX
    security_id: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    tradingsymbol: Mapped[str] = mapped_column(String(100), nullable=True)

    # Trade direction
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # BUY / SELL

    # Entry
    entry_time: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    # Risk parameters at entry
    stop_loss: Mapped[float] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float] = mapped_column(Float, nullable=True)

    # Exit (nullable if still open)
    exit_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # 'target' | 'stop_loss' | 'time_exit' | 'trailing_stop' | 'manual' | 'catastrophic_stop'

    # PnL
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    bars_held: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Risk taken on entry (₹ amount if SL hit)
    risk_amount: Mapped[float | None] = mapped_column(Float, nullable=True)

    # For Index Bar-Scoring: the bar score that triggered entry
    bar_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # For live trades: broker order IDs
    broker_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    strategy = relationship("Strategy", lazy="selectin")

    __table_args__ = (
        Index("ix_trade_logs_strategy_mode", "strategy_id", "mode"),
        Index("ix_trade_logs_open_mode", "is_open", "mode"),
    )

    def __repr__(self) -> str:
        return (
            f"<TradeLog id={self.id} {self.side} {self.symbol} "
            f"qty={self.quantity} entry={self.entry_price} exit={self.exit_price}>"
        )
