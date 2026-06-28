"""
app.api.journal
---------------
GET /api/journal/trades         — paginated trade history with filters
GET /api/journal/analytics      — aggregated performance metrics
GET /api/journal/equity-curve   — historical equity curve (from EquityCurve table)
GET /api/journal/monthly-returns — monthly P&L breakdown
GET /api/journal/streaks        — win/loss streak analysis
"""
from datetime import datetime, date, timedelta
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, extract
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.trade_log import TradeLog
from app.models.equity_curve import EquityCurve
from app.models.user import User

router = APIRouter(prefix="/journal", tags=["journal"])


@router.get("/trades")
def list_trades(
    mode: str | None = Query(None, description="Filter by mode: 'live' or 'backtest'"),
    strategy_id: int | None = Query(None),
    symbol: str | None = Query(None),
    is_open: bool | None = Query(None),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Paginated trade history with optional filters."""
    q = db.query(TradeLog)
    if mode:
        q = q.filter(TradeLog.mode == mode)
    if strategy_id:
        q = q.filter(TradeLog.strategy_id == strategy_id)
    if symbol:
        q = q.filter(TradeLog.symbol == symbol)
    if is_open is not None:
        q = q.filter(TradeLog.is_open.is_(is_open))
    if start_date:
        q = q.filter(TradeLog.entry_time >= start_date)
    if end_date:
        q = q.filter(TradeLog.entry_time <= end_date)

    total = q.count()
    trades = (
        q.order_by(TradeLog.entry_time.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "trades": [
            {
                "id": t.id,
                "strategy_id": t.strategy_id,
                "mode": t.mode,
                "segment": t.segment,
                "symbol": t.symbol,
                "side": t.side,
                "entry_time": t.entry_time,
                "entry_price": t.entry_price,
                "quantity": t.quantity,
                "stop_loss": t.stop_loss,
                "take_profit": t.take_profit,
                "exit_time": t.exit_time,
                "exit_price": t.exit_price,
                "exit_reason": t.exit_reason,
                "pnl": t.pnl,
                "pnl_pct": t.pnl_pct,
                "bars_held": t.bars_held,
                "bar_score": t.bar_score,
                "is_open": t.is_open,
                "broker_order_id": t.broker_order_id,
            }
            for t in trades
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/analytics")
def get_analytics(
    mode: str | None = Query("live", description="'live' or 'backtest' or 'all'"),
    days: int = Query(90, ge=1, le=365, description="Lookback days"),
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aggregated performance metrics for the dashboard."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    q = db.query(TradeLog).filter(TradeLog.entry_time >= cutoff)
    if mode and mode != "all":
        q = q.filter(TradeLog.mode == mode)

    trades = q.all()
    closed_trades = [t for t in trades if not t.is_open and t.pnl is not None]
    open_trades = [t for t in trades if t.is_open]

    if not closed_trades:
        return {
            "period_days": days,
            "mode": mode,
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
            "total_pnl": 0.0,
            "largest_win": 0.0,
            "largest_loss": 0.0,
            "avg_hold_bars": 0.0,
            "open_positions": len(open_trades),
        }

    wins = [t for t in closed_trades if t.pnl > 0]
    losses = [t for t in closed_trades if t.pnl < 0]
    total_win = sum(t.pnl for t in wins)
    total_loss = abs(sum(t.pnl for t in losses))
    total_pnl = sum(t.pnl for t in closed_trades)

    # Profit factor = gross profit / gross loss
    profit_factor = total_win / total_loss if total_loss > 0 else float("inf") if total_win > 0 else 0.0

    # Average hold duration (bars)
    hold_bars = [t.bars_held for t in closed_trades if t.bars_held is not None]
    avg_hold = sum(hold_bars) / len(hold_bars) if hold_bars else 0.0

    # Exit reason breakdown
    exit_reasons = defaultdict(int)
    for t in closed_trades:
        exit_reasons[t.exit_reason or "unknown"] += 1

    # Per-symbol breakdown
    per_symbol = defaultdict(lambda: {"trades": 0, "pnl": 0.0})
    for t in closed_trades:
        per_symbol[t.symbol]["trades"] += 1
        per_symbol[t.symbol]["pnl"] += t.pnl

    return {
        "period_days": days,
        "mode": mode,
        "total_trades": len(closed_trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": round(len(wins) / len(closed_trades) * 100, 2) if closed_trades else 0.0,
        "avg_win": round(total_win / len(wins), 2) if wins else 0.0,
        "avg_loss": round(total_loss / len(losses), 2) if losses else 0.0,
        "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else 999.99,
        "total_pnl": round(total_pnl, 2),
        "largest_win": round(max((t.pnl for t in wins), default=0.0), 2),
        "largest_loss": round(min((t.pnl for t in losses), default=0.0), 2),
        "avg_hold_bars": round(avg_hold, 2),
        "open_positions": len(open_trades),
        "exit_reasons": dict(exit_reasons),
        "per_symbol": [
            {"symbol": sym, "trades": d["trades"], "pnl": round(d["pnl"], 2)}
            for sym, d in sorted(per_symbol.items(), key=lambda x: -x[1]["pnl"])
        ],
    }


@router.get("/equity-curve")
def get_equity_curve(
    days: int = Query(30, ge=1, le=365),
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Historical equity curve from the EquityCurve table."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(EquityCurve)
        .filter(EquityCurve.timestamp >= cutoff)
        .order_by(EquityCurve.timestamp.asc())
        .all()
    )
    return {
        "points": [
            {
                "t": r.timestamp.isoformat(),
                "equity": r.equity,
                "available_margin": r.available_margin,
                "open_pnl": r.open_pnl,
                "realized_pnl_day": r.realized_pnl_day,
            }
            for r in rows
        ],
        "count": len(rows),
    }


@router.get("/monthly-returns")
def get_monthly_returns(
    year: int | None = Query(None, description="Year (defaults to current year)"),
    mode: str = Query("live"),
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Monthly P&L breakdown for a given year."""
    if year is None:
        year = datetime.utcnow().year

    q = db.query(
        extract("year", TradeLog.exit_time).label("yr"),
        extract("month", TradeLog.exit_time).label("mo"),
        func.count(TradeLog.id).label("trades"),
        func.sum(TradeLog.pnl).label("pnl"),
    ).filter(
        TradeLog.mode == mode,
        TradeLog.is_open.is_(False),
        extract("year", TradeLog.exit_time) == year,
    ).group_by("yr", "mo").order_by("mo")

    rows = q.all()
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    monthly = {m: {"trades": 0, "pnl": 0.0} for m in months}
    for r in rows:
        m = months[int(r.mo) - 1]
        monthly[m] = {"trades": int(r.trades), "pnl": round(float(r.pnl or 0), 2)}

    return {
        "year": year,
        "mode": mode,
        "months": [{"month": m, **d} for m, d in monthly.items()],
        "total_pnl": round(sum(d["pnl"] for d in monthly.values()), 2),
        "total_trades": sum(d["trades"] for d in monthly.values()),
    }


@router.get("/streaks")
def get_streaks(
    mode: str = Query("live"),
    limit: int = Query(100, ge=10, le=500),
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Win/loss streak analysis — current streak + longest streaks."""
    trades = (
        db.query(TradeLog)
        .filter(TradeLog.mode == mode, TradeLog.is_open.is_(False))
        .order_by(TradeLog.exit_time.asc())
        .limit(limit)
        .all()
    )

    if not trades:
        return {
            "current_streak": {"type": "none", "count": 0},
            "longest_win_streak": 0,
            "longest_loss_streak": 0,
            "total_sequences": 0,
        }

    # Build sequence of W/L
    sequence = []
    for t in trades:
        if t.pnl and t.pnl > 0:
            sequence.append("W")
        elif t.pnl and t.pnl < 0:
            sequence.append("L")
        else:
            sequence.append("=")

    # Find streaks
    streaks = []
    current_type = sequence[0]
    current_count = 1
    for s in sequence[1:]:
        if s == current_type:
            current_count += 1
        else:
            streaks.append((current_type, current_count))
            current_type = s
            current_count = 1
    streaks.append((current_type, current_count))

    longest_win = max((c for t, c in streaks if t == "W"), default=0)
    longest_loss = max((c for t, c in streaks if t == "L"), default=0)
    current = streaks[-1]

    return {
        "current_streak": {"type": current[0], "count": current[1]},
        "longest_win_streak": longest_win,
        "longest_loss_streak": longest_loss,
        "total_sequences": len(streaks),
        "recent_sequence": "".join(sequence[-20:]),  # last 20 trades as a string
    }
