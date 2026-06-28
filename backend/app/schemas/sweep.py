"""
app.schemas.sweep
-----------------
Schemas for parameter sweep (auto-run N backtests across a parameter range).
"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class SweepParameterSpec(BaseModel):
    """One parameter to sweep across."""
    key: str                       # e.g. "stddev_min_pct"
    values: list[float] | list[int] | list[str]   # e.g. [0.01, 0.015, 0.02, 0.025, 0.03]


class SweepStartRequest(BaseModel):
    """Run a sweep: N backtests varying one or more parameters."""
    strategy_id: int
    segment: str
    security_id: str
    symbol: str
    start_date: datetime
    end_date: datetime
    initial_capital: float = 1_000_000.0
    base_parameters: dict = {}           # fixed parameters applied to all runs
    sweep_parameters: list[SweepParameterSpec]   # parameters to vary (1 or 2 supported)


class SweepRunResult(BaseModel):
    """Result of a single backtest run inside the sweep."""
    params: dict                        # the specific param values used
    net_profit: float
    net_profit_pct: float
    total_trades: int
    win_rate: float
    max_drawdown_pct: float
    avg_annual_return: float
    gtp_ratio: float
    is_tradeable: bool
    error: str | None = None


class SweepResultOut(BaseModel):
    """Full sweep result — list of per-run results + the best run highlighted."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    celery_task_id: str | None
    strategy_id: int
    symbol: str
    status: str                # pending | running | completed | failed
    error_message: str | None
    # The full list of run results
    runs: list[SweepRunResult] = []
    # Best run by GtP ratio (highlighted for the UI)
    best_run: SweepRunResult | None = None
    total_runs: int = 0
    completed_runs: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
