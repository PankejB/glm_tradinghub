"""
app.api.sweep
-------------
POST /api/sweep/start           — dispatch parameter sweep Celery task
GET  /api/sweep/status/{task_id} — poll sweep status
GET  /api/sweep/results         — recent sweeps
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.strategy import Strategy
from app.models.sweep_result import SweepResult
from app.schemas.sweep import SweepStartRequest, SweepResultOut

router = APIRouter(prefix="/sweep", tags=["sweep"])


@router.post("/start")
def start_sweep(
    payload: SweepStartRequest,
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start a parameter sweep — runs N backtests varying one or two parameters."""
    if not payload.sweep_parameters:
        raise HTTPException(
            status_code=400,
            detail="At least one sweep_parameter is required",
        )
    if len(payload.sweep_parameters) > 2:
        raise HTTPException(
            status_code=400,
            detail="Sweep supports at most 2 parameters (for a 2D heatmap)",
        )
    # Limit total combinations to prevent runaway jobs
    total_combos = 1
    for p in payload.sweep_parameters:
        total_combos *= len(p.values)
    if total_combos > 100:
        raise HTTPException(
            status_code=400,
            detail=f"Sweep would generate {total_combos} runs (max 100). Reduce parameter values.",
        )

    strat = db.get(Strategy, payload.strategy_id)
    if not strat:
        raise HTTPException(status_code=404, detail="Strategy not found")

    # Create the SweepResult row
    sr = SweepResult(
        strategy_id=payload.strategy_id,
        segment=payload.segment,
        security_id=payload.security_id,
        symbol=payload.symbol,
        start_date=payload.start_date,
        end_date=payload.end_date,
        initial_capital=payload.initial_capital,
        sweep_config={
            "base_parameters": payload.base_parameters,
            "sweep_parameters": [p.model_dump() for p in payload.sweep_parameters],
        },
        total_runs=total_combos,
        status="pending",
    )
    db.add(sr)
    db.commit()
    db.refresh(sr)

    # Dispatch Celery task
    from app.tasks.sweep_tasks import task_run_parameter_sweep
    async_result = task_run_parameter_sweep.delay(
        sweep_result_id=sr.id,
        base_parameters=payload.base_parameters,
        sweep_parameters=[p.model_dump() for p in payload.sweep_parameters],
    )
    sr.celery_task_id = async_result.id
    db.commit()

    return {
        "sweep_id": sr.id,
        "task_id": async_result.id,
        "total_runs": total_combos,
        "status": "pending",
        "message": f"Parameter sweep dispatched ({total_combos} runs)",
    }


@router.get("/status/{task_id}", response_model=SweepResultOut)
def sweep_status(
    task_id: str,
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sr = db.query(SweepResult).filter_by(celery_task_id=task_id).first()
    if not sr:
        raise HTTPException(status_code=404, detail="Sweep not found for this task_id")

    # Sync with Celery state
    try:
        from celery_app import celery_app
        r = celery_app.AsyncResult(task_id)
        if r.failed() and sr.status != "failed":
            sr.status = "failed"
            sr.error_message = str(r.result)
            db.commit()
    except Exception:  # noqa: BLE001
        pass

    return SweepResultOut.model_validate(sr)


@router.get("/results", response_model=list[SweepResultOut])
def list_recent_sweeps(
    limit: int = Query(20, ge=1, le=100),
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(SweepResult)
        .order_by(SweepResult.created_at.desc())
        .limit(limit)
        .all()
    )
