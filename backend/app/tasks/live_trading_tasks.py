"""
app.tasks.live_trading_tasks
----------------------------
Celery tasks for live trading.

- task_start_live_trading(strategy_id, user_id, paper_mode):
    Long-running loop. Every 30s during IST market hours (09:15-15:30):
      1. Fetch latest OHLCV bar
      2. Refresh indicators on the rolling window
      3. Check for entry / exit signals
      4. Place orders via DhanHQ (or paper-trade equivalent)
      5. Update TradeLog + User equity

- task_stop_trading(strategy_id, square_off):
    Sets a Redis flag that the running loop checks each tick.
    If square_off=True, also closes any open positions for the strategy.

State exchange between start/stop tasks uses Redis keys:
    trading:active:{strategy_id}  -> "1" while the loop should keep running
    trading:stop_signal:{strategy_id} -> "1" when stop has been requested
"""
from __future__ import annotations

import json
import time
from datetime import datetime, date, time as dtime, timedelta
from typing import Any

import redis as redis_lib
from loguru import logger

from celery_app import celery_app
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.strategy import Strategy
from app.models.trade_log import TradeLog
from app.models.user import User
from app.services.dhan_service import DhanService
from app.strategies import build_strategy


# ---- Redis handle for loop control ---------------------------------------
_redis = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)

ACTIVE_KEY = "trading:active:{strategy_id}"
STOP_KEY = "trading:stop_signal:{strategy_id}"


# ---- Market hours check ---------------------------------------------------
def _ist_market_open(now: datetime | None = None) -> bool:
    """
    Returns True if `now` (UTC) falls inside IST market hours 09:15-15:30 Mon-Fri.
    IST = UTC + 5:30.
    """
    now = now or datetime.utcnow()
    ist = now + timedelta(hours=5, minutes=30)
    if ist.weekday() >= 5:  # Sat=5, Sun=6
        return False
    t = ist.time()
    return dtime(9, 15) <= t <= dtime(15, 30)


# ---- Paper-trade order book (per strategy_id) -----------------------------
def _paper_place_order(side: str, qty: int, price: float, symbol: str) -> str:
    """Returns a synthetic broker order id."""
    return f"PAPER-{side}-{int(time.time() * 1000)}"


# ---- TradeLog helpers -----------------------------------------------------
def _open_trade_from_signal(sig, db, strategy_id, user_id, segment, symbol, security_id, paper_mode, qty):
    t = TradeLog(
        strategy_id=strategy_id, user_id=user_id, mode="live",
        segment=segment, security_id=str(security_id), symbol=symbol,
        side=sig.side, entry_time=datetime.utcnow(),
        entry_price=sig.entry_price, quantity=qty,
        stop_loss=sig.stop_loss, take_profit=sig.take_profit,
        bar_score=sig.bar_score, is_open=True,
        broker_order_id=None if paper_mode else None,
        meta=sig.meta,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _close_trade(trade: TradeLog, exit_price: float, reason: str, db, paper_mode: bool):
    trade.exit_time = datetime.utcnow()
    trade.exit_price = exit_price
    trade.exit_reason = reason
    pnl = (exit_price - trade.entry_price) * trade.quantity
    if trade.side == "SELL":
        pnl = -pnl
    trade.pnl = round(pnl, 2)
    trade.pnl_pct = round(pnl / (trade.entry_price * trade.quantity) * 100, 4) if trade.quantity else 0.0
    trade.bars_held = None
    trade.is_open = False
    db.commit()
    return pnl


# =============================================================
#  Main live-trading task
# =============================================================
@celery_app.task(
    name="task_start_live_trading",
    bind=True,
    soft_time_limit=None,   # long-running: ignore soft limit
    time_limit=None,
)
def task_start_live_trading(self, strategy_id: int, user_id: int, paper_mode: bool = True):
    """
    Long-running live-trading loop. Returns when stop signal received or
    market closes.
    """
    logger.info(
        "LIVE trading starting: strategy={} user={} paper={}",
        strategy_id, user_id, paper_mode,
    )
    _redis.set(ACTIVE_KEY.format(strategy_id=strategy_id), "1")
    _redis.delete(STOP_KEY.format(strategy_id=strategy_id))

    db = SessionLocal()
    try:
        strat = db.get(Strategy, strategy_id)
        if not strat:
            return {"status": "error", "error": f"Strategy {strategy_id} not found"}
        if not strat.is_tradeable and not paper_mode:
            return {
                "status": "error",
                "error": f"Strategy {strat.slug} is not tradeable (GtP <= 1.5)",
            }

        user = db.get(User, user_id) if user_id else None
        equity = user.current_equity if user else settings.DEFAULT_CAPITAL

        # Pick first allowed segment + a default symbol from strategy params
        segment = (strat.allowed_segments or ["NSE_EQ"])[0]
        symbol = strat.parameters.get("default_symbol", "RELIANCE") if strat.parameters else "RELIANCE"
        security_id = strat.parameters.get("default_security_id", "2885")  # RELIANCE default
        # Override with explicit defaults per strategy type if provided
        if strat.strategy_type == "mcx_trend_following":
            symbol = strat.parameters.get("default_symbol", "GOLD")
            security_id = strat.parameters.get("default_security_id", "2236")
        elif strat.strategy_type == "index_bar_scoring":
            symbol = strat.parameters.get("default_symbol", "NIFTY 50")
            security_id = strat.parameters.get("default_security_id", "13")

        strategy = build_strategy(strat.strategy_type, parameters=strat.parameters)
        dhan = DhanService()
        tick_interval = settings.LIVE_LOOP_INTERVAL_SEC

        logger.info(
            "LIVE loop ready: strat={} symbol={} sec={} segment={} tick={}s",
            strat.slug, symbol, security_id, segment, tick_interval,
        )

        while True:
            # 1) Stop signal?
            if _redis.get(STOP_KEY.format(strategy_id=strategy_id)) == "1":
                logger.info("Stop signal received for strategy {}", strategy_id)
                break

            # 2) Market hours?
            if not _ist_market_open():
                # Sleep longer outside market hours (avoid burning CPU)
                logger.debug("Outside IST market hours — sleeping 5min")
                time.sleep(300)
                continue

            try:
                # 3) Refresh latest bars (last 100 days for indicator warmup)
                df = DhanService.load_bars(security_id, "1D")
                if df.empty or len(df) < 80:
                    logger.warning("Insufficient bars for {} ({}), syncing…", symbol, len(df))
                    try:
                        dhan.sync_historical(security_id, symbol, segment, "1D", days=365)
                        df = DhanService.load_bars(security_id, "1D")
                    except Exception as e:  # noqa: BLE001
                        logger.error("DhanHQ sync failed: {}", e)
                        time.sleep(tick_interval)
                        continue

                # 4) Enrich with indicators + check signals on the LAST bar
                enriched = strategy.enrich(df)
                last_row = enriched.iloc[-1]
                prev_row = enriched.iloc[-2] if len(enriched) > 1 else None

                # 5) Check open trade first
                open_trade = (
                    db.query(TradeLog)
                    .filter(
                        TradeLog.strategy_id == strategy_id,
                        TradeLog.is_open.is_(True),
                        TradeLog.mode == "live",
                    )
                    .order_by(TradeLog.entry_time.desc())
                    .first()
                )

                if open_trade:
                    bars_held = 0  # we don't track per-bar in live; approximate
                    exit_sig = strategy.check_exit(
                        open_trade={
                            "entry_price": open_trade.entry_price,
                            "stop_loss": open_trade.stop_loss,
                            "take_profit": open_trade.take_profit,
                            "side": open_trade.side,
                            "meta": open_trade.meta or {},
                        },
                        row=last_row, prev_row=prev_row, bars_held=bars_held,
                    )
                    if exit_sig and exit_sig.action == "EXIT":
                        exit_price = float(last_row["close"])
                        pnl = _close_trade(open_trade, exit_price, exit_sig.meta.get("exit_reason", "signal"), db, paper_mode)
                        equity += pnl
                        if user:
                            user.current_equity = equity
                            db.commit()
                        logger.info(
                            "CLOSED {} {}: exit={} pnl=₹{}",
                            symbol, open_trade.side, exit_price, round(pnl, 2),
                        )
                else:
                    # 6) Look for entry
                    entry_sig = strategy.check_entry(last_row, prev_row)
                    if entry_sig and entry_sig.action == "ENTER":
                        stop_dist = abs(entry_sig.entry_price - (entry_sig.stop_loss or 0))
                        if stop_dist > 0:
                            qty = int((equity * settings.RISK_PER_TRADE_PCT / 100.0) / stop_dist)
                            if qty > 0:
                                if paper_mode:
                                    order_id = _paper_place_order(entry_sig.side, qty, entry_sig.entry_price, symbol)
                                else:
                                    # Live order via DhanHQ — left as TODO hook
                                    order_id = "LIVE_TODO"
                                    logger.warning("Live order placement not yet wired — paper mode only")
                                _open_trade_from_signal(
                                    entry_sig, db, strategy_id, user_id,
                                    segment, symbol, security_id, paper_mode, qty,
                                )
                                logger.info(
                                    "OPENED {} {} qty={} @ {} SL={} (order={})",
                                    entry_sig.side, symbol, qty, entry_sig.entry_price,
                                    entry_sig.stop_loss, order_id,
                                )

            except Exception as exc:  # noqa: BLE001
                logger.exception("Live tick error: {}", exc)

            time.sleep(tick_interval)

        # ---- Loop exited — clean up --------------------------------------
        _redis.delete(ACTIVE_KEY.format(strategy_id=strategy_id))
        logger.info("LIVE trading loop stopped for strategy {}", strategy_id)
        return {
            "status": "stopped",
            "strategy_id": strategy_id,
            "final_equity": equity,
        }
    finally:
        _redis.delete(ACTIVE_KEY.format(strategy_id=strategy_id))
        db.close()


# =============================================================
#  Stop task
# =============================================================
@celery_app.task(name="task_stop_trading")
def task_stop_trading(strategy_id: int | None = None, square_off: bool = True):
    """
    Signal the live trading loop(s) to stop. If square_off=True, also
    close all open positions for the strategy (paper mode only for now).
    """
    if strategy_id:
        _redis.set(STOP_KEY.format(strategy_id=strategy_id), "1")
        logger.info("Stop signal set for strategy {}", strategy_id)
        if square_off:
            _square_off_strategy(strategy_id)
    else:
        # Stop ALL active loops
        for k in _redis.scan_iter("trading:active:*"):
            sid = k.split(":")[-1]
            _redis.set(STOP_KEY.format(strategy_id=sid), "1")
            if square_off:
                _square_off_strategy(int(sid))
    return {"status": "stop_signalled", "strategy_id": strategy_id, "square_off": square_off}


def _square_off_strategy(strategy_id: int) -> int:
    """Close all open TradeLogs for this strategy. Returns count closed."""
    db = SessionLocal()
    try:
        open_trades = (
            db.query(TradeLog)
            .filter(TradeLog.strategy_id == strategy_id, TradeLog.is_open.is_(True))
            .all()
        )
        for t in open_trades:
            # Use last known close (DB doesn't have a quote here)
            exit_price = t.entry_price  # placeholder; in live, fetch LTP from DhanHQ
            _close_trade(t, exit_price, "manual_square_off", db, paper_mode=True)
        return len(open_trades)
    finally:
        db.close()
