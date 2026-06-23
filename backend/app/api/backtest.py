"""
app.api.backtest
----------------
POST /api/backtest/start           — dispatch Celery task
GET  /api/backtest/status/{task_id} — poll task + load BacktestResult row
GET  /api/backtest/results         — recent results
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.strategy import Strategy
from app.models.backtest_result import BacktestResult
from app.schemas.backtest import BacktestStartRequest, BacktestStatusOut

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.post("/start")
def start_backtest(
    payload: BacktestStartRequest,
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Validate strategy exists
    strat = db.get(Strategy, payload.strategy_id)
    if not strat:
        raise HTTPException(status_code=404, detail="Strategy not found")

    # Create a pending BacktestResult row (Celery task will fill it in)
    br = BacktestResult(
        strategy_id=payload.strategy_id,
        segment=payload.segment,
        security_id=payload.security_id,
        symbol=payload.symbol,
        start_date=payload.start_date,
        end_date=payload.end_date,
        initial_capital=payload.initial_capital,
        final_equity=payload.initial_capital,
        net_profit=0.0,
        net_profit_pct=0.0,
        total_trades=0,
        parameters={**strat.parameters, **payload.parameters},
        status="pending",
    )
    db.add(br)
    db.commit()
    db.refresh(br)

    # Dispatch the Celery task (imported lazily to avoid circular import)
    from app.tasks.backtest_tasks import task_run_backtest
    async_result = task_run_backtest.delay(br.id)

    # Persist the Celery task id so we can poll it
    br.celery_task_id = async_result.id
    db.commit()

    return {
        "backtest_id": br.id,
        "task_id": async_result.id,
        "status": "pending",
        "message": "Backtest dispatched to Celery worker",
    }


@router.get("/status/{task_id}", response_model=BacktestStatusOut)
def backtest_status(
    task_id: str,
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    br = db.query(BacktestResult).filter_by(celery_task_id=task_id).first()
    if not br:
        raise HTTPException(status_code=404, detail="Backtest not found for this task_id")

    # If Celery result is available, surface its state too
    try:
        from celery_app import celery_app
        r = celery_app.AsyncResult(task_id)
        celery_state = r.state
        if r.failed() and br.status != "failed":
            br.status = "failed"
            br.error_message = str(r.result)
            db.commit()
    except Exception:  # noqa: BLE001
        celery_state = "UNKNOWN"

    out = BacktestStatusOut.model_validate(br)
    # Attach celery state for the frontend if needed
    return out


@router.get("/results", response_model=list[BacktestStatusOut])
def list_recent_results(
    limit: int = Query(20, ge=1, le=100),
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(BacktestResult)
        .order_by(BacktestResult.created_at.desc())
        .limit(limit)
        .all()
    )
