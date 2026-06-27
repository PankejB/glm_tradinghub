"""
app.models.sweep_result
-----------------------
SweepResult: stores the result of a parameter sweep (N backtest runs across
a parameter range). One row per sweep.
"""
from datetime import datetime
from sqlalchemy import String, DateTime, Float, Integer, JSON, Text, ForeignKey, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SweepResult(Base):
    __tablename__ = "sweep_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # What was tested
    segment: Mapped[str] = mapped_column(String(20), nullable=False)
    security_id: Mapped[str] = mapped_column(String(50), nullable=False)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)

    # Test window
    start_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Capital
    initial_capital: Mapped[float] = mapped_column(Float, nullable=False)

    # Sweep config (JSON): {base_parameters, sweep_parameters}
    sweep_config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Results (JSON list of SweepRunResult dicts)
    runs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    best_run: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    total_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Task linkage
    celery_task_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending | running | completed | failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    strategy = relationship("Strategy", lazy="selectin")

    __table_args__ = (
        Index("ix_sweep_results_strategy_status", "strategy_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<SweepResult id={self.id} strategy={self.strategy_id} runs={self.total_runs} status={self.status}>"
