"""
app.api.trading
---------------
GET  /api/trading/status        — is live trading enabled? (kill switch state)
POST /api/trading/start
POST /api/trading/stop
GET  /api/trading/active
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.strategy import Strategy
from app.models.user import User
from app.schemas.trading import TradingStartRequest, TradingStopRequest

router = APIRouter(prefix="/trading", tags=["trading"])


@router.get("/status")
def trading_status(_=Depends(get_current_user)):
    """Returns whether live trading (real orders) is enabled.
    Frontend uses this to show warnings + disable the live-mode toggle."""
    return {
        "live_trading_enabled": settings.LIVE_TRADING_ENABLED,
        "order_type_default": settings.ORDER_TYPE_DEFAULT,
        "max_daily_loss_inr": settings.MAX_DAILY_LOSS_INR,
        "product_types": {
            "NSE_EQ":  settings.ORDER_PRODUCT_TYPE_EQ,
            "NSE_FNO": settings.ORDER_PRODUCT_TYPE_FNO,
            "MCX":     settings.ORDER_PRODUCT_TYPE_MCX,
        },
        "warning": (
            "⚠️ LIVE TRADING IS ENABLED. Real orders will be placed."
            if settings.LIVE_TRADING_ENABLED
            else "Live trading is DISABLED (paper mode only). Set LIVE_TRADING_ENABLED=true in .env to enable."
        ),
    }


@router.post("/start")
def start_trading(
    payload: TradingStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    strat = db.get(Strategy, payload.strategy_id)
    if not strat:
        raise HTTPException(status_code=404, detail="Strategy not found")

    # SAFETY: if live trading is disabled, force paper_mode=True
    effective_paper_mode = payload.paper_mode or not settings.LIVE_TRADING_ENABLED
    if not payload.paper_mode and not settings.LIVE_TRADING_ENABLED:
        # Frontend asked for live, but kill switch is off → return warning
        return {
            "task_id": None,
            "strategy_id": payload.strategy_id,
            "paper_mode": True,
            "status": "forced_paper",
            "message": (
                "Live trading is DISABLED (LIVE_TRADING_ENABLED=false). "
                "Started in PAPER mode instead. To enable live trading, "
                "set LIVE_TRADING_ENABLED=true in backend/.env and restart."
            ),
        }

    if not strat.is_tradeable and not effective_paper_mode:
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
        paper_mode=effective_paper_mode,
    )
    return {
        "task_id": async_result.id,
        "strategy_id": payload.strategy_id,
        "strategy_slug": strat.slug,
        "paper_mode": effective_paper_mode,
        "status": "dispatched",
        "message": (
            "⚠️ LIVE trading loop started (real orders will be placed)"
            if not effective_paper_mode
            else "Paper trading loop started (no real orders)"
        ),
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
