"""
app.schemas.trading
-------------------
"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class TradingStartRequest(BaseModel):
    strategy_id: int
    user_id: int | None = None
    paper_mode: bool = True     # if True, no real orders are placed


class TradingStopRequest(BaseModel):
    strategy_id: int | None = None   # if None, stop all
    square_off: bool = True         # close open positions


class TradeLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: int
    mode: str
    segment: str
    security_id: str
    symbol: str
    side: str
    entry_time: datetime
    entry_price: float
    quantity: int
    stop_loss: float | None
    take_profit: float | None
    exit_time: datetime | None
    exit_price: float | None
    exit_reason: str | None
    pnl: float | None
    pnl_pct: float | None
    bars_held: int | None
    bar_score: float | None
    is_open: bool
    broker_order_id: str | None


class PortfolioStatusOut(BaseModel):
    user_id: int | None
    starting_capital: float
    current_equity: float
    available_margin: float
    open_pnl: float
    realized_pnl_today: float
    open_positions: list[TradeLogOut]
    active_strategies: list[int]
    last_updated: datetime
