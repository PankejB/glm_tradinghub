"""
app.schemas.backtest
--------------------
"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class BacktestStartRequest(BaseModel):
    strategy_id: int
    segment: str               # e.g. "NSE_EQ"
    security_id: str
    symbol: str
    start_date: datetime
    end_date: datetime
    initial_capital: float = 1_000_000.0
    parameters: dict = {}      # optional overrides


class BacktestStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    celery_task_id: str | None
    status: str                # pending | running | completed | failed
    error_message: str | None
    strategy_id: int
    symbol: str
    # Metrics (populated on completion)
    net_profit: float | None = None
    net_profit_pct: float | None = None
    total_trades: int | None = None
    win_rate: float | None = None
    max_drawdown_pct: float | None = None
    avg_annual_return: float | None = None
    gtp_ratio: float | None = None
    is_tradeable: bool | None = None
    trades_json: list | None = None
    equity_curve_json: list | None = None
    completed_at: datetime | None = None
