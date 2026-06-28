"""
app.api.strategies
------------------
GET /api/strategies                — list all
GET /api/strategies/{strategy_id}  — detail
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.strategy import Strategy
from app.schemas.strategy import StrategyOut

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("", response_model=list[StrategyOut])
def list_strategies(
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(Strategy).order_by(Strategy.id).all()


@router.get("/{strategy_id}", response_model=StrategyOut)
def get_strategy(
    strategy_id: int,
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    s = db.get(Strategy, strategy_id)
    if not s:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return s
