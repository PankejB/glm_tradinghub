"""
app.api.trading
---------------
POST /api/trading/start
POST /api/trading/stop
GET  /api/trading/active
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.strategy import Strategy
from app.models.user import User
from app.schemas.trading import TradingStartRequest, TradingStopRequest

router = APIRouter(prefix="/trading", tags=["trading"])


@router.post("/start")
def start_trading(
    payload: TradingStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    strat = db.get(Strategy, payload.strategy_id)
    if not strat:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if not strat.is_tradeable:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Strategy '{strat.slug}' is NOT tradeable "
                f"(GtP={strat.latest_gtp_ratio or 0:.2f}, need > 1.5). "
                f"Run a backtest first."
            ),
        )

    from app.tasks.live_trading_tasks import task_start_live_trading
    user_id = payload.user_id or current_user.id
    async_result = task_start_live_trading.delay(
        strategy_id=payload.strategy_id,
        user_id=user_id,
        paper_mode=payload.paper_mode,
    )
    return {
        "task_id": async_result.id,
        "strategy_id": payload.strategy_id,
        "strategy_slug": strat.slug,
        "paper_mode": payload.paper_mode,
        "status": "dispatched",
        "message": "Live trading loop started",
    }


@router.post("/stop")
def stop_trading(
    payload: TradingStopRequest,
    _=Depends(get_current_user),
):
    from app.tasks.live_trading_tasks import task_stop_trading
    async_result = task_stop_trading.delay(
        strategy_id=payload.strategy_id,
        square_off=payload.square_off,
    )
    return {
        "task_id": async_result.id,
        "strategy_id": payload.strategy_id,
        "square_off": payload.square_off,
        "status": "dispatched",
        "message": "Stop signal sent to live trading loop",
    }


@router.get("/active")
def list_active_tasks(_=Depends(get_current_user)):
    """Return currently-running live-trading Celery tasks."""
    from celery_app import celery_app
    inspect = celery_app.control.inspect()
    active = inspect.active() or {}
    live_tasks = []
    for _worker, tasks in active.items():
        for t in tasks:
            if "live_trading" in t.get("name", ""):
                live_tasks.append({
                    "task_id": t.get("id"),
                    "name": t.get("name"),
                    "args": t.get("args"),
                    "started_at": t.get("time_start"),
                })
    return {"active_live_tasks": live_tasks}
