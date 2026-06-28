"""
app.api.data
------------
POST /api/data/sync  — trigger 1-year OHLCV sync for an instrument
GET  /api/data/bars  — load persisted bars
"""
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.deps import get_current_user
from app.services.dhan_service import DhanService

router = APIRouter(prefix="/data", tags=["data"])


class SyncRequest(BaseModel):
    security_id: str
    symbol: str
    segment: str   # NSE_EQ | NSE_FNO | MCX
    interval: str = "1D"
    days: int = 365
    # Override instrument_type when segment is NSE_FNO or MCX
    # (defaults: NSE_EQ→EQUITY, NSE_FNO→INDEX, MCX→FUTCOM)
    instrument_type: str | None = None


@router.post("/sync")
def sync_data(
    payload: SyncRequest,
    _=Depends(get_current_user),
):
    """Synchronously fetch & persist 1-year of OHLCV. Returns bar count."""
    try:
        svc = DhanService()
        n = svc.sync_historical(
            security_id=payload.security_id,
            symbol=payload.symbol,
            segment=payload.segment,
            interval=payload.interval,
            days=payload.days,
            instrument_type=payload.instrument_type,
        )
        return {
            "security_id": payload.security_id,
            "symbol": payload.symbol,
            "bars_synced": n,
            "interval": payload.interval,
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"DhanHQ sync failed: {exc}")


@router.get("/bars")
def get_bars(
    security_id: str = Query(...),
    timeframe: str = Query("1D"),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    _=Depends(get_current_user),
):
    df = DhanService.load_bars(security_id, timeframe, start, end)
    if df.empty:
        return {"bars": [], "count": 0}
    df["timestamp"] = df["timestamp"].astype(str)
    return {"bars": df.to_dict(orient="records"), "count": len(df)}
