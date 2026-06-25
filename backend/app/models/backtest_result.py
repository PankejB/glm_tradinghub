"""
app.models.backtest_result
--------------------------
BacktestResult: summary row per backtest run (one per strategy + instrument + window).
"""
from datetime import datetime
from sqlalchemy import String, DateTime, Float, Integer, JSON, Text, ForeignKey, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class BacktestResult(Base):
    __tablename__ = "backtest_results"

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
    final_equity: Mapped[float] = mapped_column(Float, nullable=False)

    # Headline metrics
    net_profit: Mapped[float] = mapped_column(Float, nullable=False)
    net_profit_pct: Mapped[float] = mapped_column(Float, nullable=False)
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    losing_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Risk metrics
    max_drawdown: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_annual_return: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Fitschen tradeability gate
    gtp_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_tradeable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Full per-trade breakdown (JSON list)
    trades_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Equity curve sample points (JSON list of {t, equity})
    # Sampled (e.g. daily closes) so the chart stays light.
    equity_curve_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Parameters used
    parameters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # ----- Portfolio backtest fields -----
    # True for a parent portfolio backtest; False for single-instrument or child rows.
    is_portfolio: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # For child rows: points to the parent portfolio BacktestResult.id
    parent_portfolio_id: Mapped[int | None] = mapped_column(
        ForeignKey("backtest_results.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    # Per-instrument breakdown for portfolio backtests (JSON list of dicts):
    #   [{security_id, symbol, segment, trades, net_profit, gtp_ratio, max_dd_pct, win_rate, ...}, ...]
    portfolio_breakdown: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Task linkage
    celery_task_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending | running | completed | failed

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    strategy = relationship("Strategy", lazy="selectin")
    # Child results of a portfolio backtest
    child_results = relationship(
        "BacktestResult",
        backref="parent_portfolio",
        remote_side="BacktestResult.id",
        primaryjoin="BacktestResult.id==BacktestResult.parent_portfolio_id",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_backtest_results_strategy_status", "strategy_id", "status"),
        Index("ix_backtest_results_portfolio", "is_portfolio", "parent_portfolio_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<BacktestResult id={self.id} strategy={self.strategy_id} "
            f"symbol={self.symbol!r} gtp={self.gtp_ratio:.2f} "
            f"tradeable={self.is_tradeable}>"
        )
