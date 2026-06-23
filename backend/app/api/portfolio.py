"""
app.api.portfolio
-----------------
GET /api/portfolio/status
"""
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.trade_log import TradeLog
from app.schemas.trading import PortfolioStatusOut, TradeLogOut

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/status", response_model=PortfolioStatusOut)
def portfolio_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    open_trades = (
        db.query(TradeLog)
        .filter(TradeLog.user_id == current_user.id, TradeLog.is_open.is_(True), TradeLog.mode == "live")
        .all()
    )
    open_pnl = sum((t.pnl or 0.0) for t in open_trades if t.pnl is not None)

    # Realized PnL today
    today = datetime.utcnow().date()
    closed_today = (
        db.query(TradeLog)
        .filter(
            TradeLog.user_id == current_user.id,
            TradeLog.is_open.is_(False),
            TradeLog.mode == "live",
            TradeLog.exit_time >= datetime(today.year, today.month, today.day),
        )
        .all()
    )
    realized_pnl_today = sum((t.pnl or 0.0) for t in closed_today)

    return PortfolioStatusOut(
        user_id=current_user.id,
        starting_capital=current_user.starting_capital,
        current_equity=current_user.current_equity,
        available_margin=current_user.available_margin,
        open_pnl=open_pnl,
        realized_pnl_today=realized_pnl_today,
        open_positions=[TradeLogOut.model_validate(t) for t in open_trades],
        active_strategies=[t.strategy_id for t in open_trades],
        last_updated=datetime.utcnow(),
    )
