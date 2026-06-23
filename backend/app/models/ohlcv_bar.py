"""
app.models.ohlcv_bar
--------------------
OhlcvBar: candle storage. Designed to be created as a TimeScaleDB hypertable
(run the migration SQL after schema is created).

Hypertable creation (run once after init_db()):
    SELECT create_hypertable('ohlcv_bars', 'timestamp');
"""
from datetime import datetime
from sqlalchemy import String, DateTime, Float, Integer, BigInteger, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OhlcvBar(Base):
    __tablename__ = "ohlcv_bars"

    # Use BigInteger PK for high-write hypertable
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    segment: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    # DhanHQ numeric security id
    security_id: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(50), index=True, nullable=False)

    # '1m' | '5m' | '15m' | '1h' | '1D'
    timeframe: Mapped[str] = mapped_column(String(10), default="1D", nullable=False)

    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)

    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "security_id", "timeframe", "timestamp",
            name="uq_ohlcv_sec_tf_ts"
        ),
        Index("ix_ohlcv_sec_tf_ts", "security_id", "timeframe", "timestamp"),
    )

    def __repr__(self) -> str:
        return (
            f"<OhlcvBar {self.symbol} {self.timeframe} "
            f"ts={self.timestamp} O={self.open} H={self.high} "
            f"L={self.low} C={self.close} V={self.volume}>"
        )
