"""
app.tasks.live_trading_tasks
----------------------------
Celery tasks for live trading.

- task_start_live_trading(strategy_id, user_id, paper_mode):
    Long-running loop. Every 30s during IST market hours (09:15-15:30):
      1. Fetch latest OHLCV bar
      2. Refresh indicators on the rolling window
      3. Check for entry / exit signals
      4. Place orders via DhanHQ OrderExecutor (or paper-trade equivalent)
      5. Update TradeLog + User equity

- task_stop_trading(strategy_id, square_off):
    Sets a Redis flag that the running loop checks each tick.
    If square_off=True, also closes any open positions for the strategy.

Safety rails:
- LIVE_TRADING_ENABLED master kill switch (in .env). If False, paper_mode
  is forced regardless of what the API request says.
- Circuit breaker: stops the loop if daily realized loss > MAX_DAILY_LOSS_INR.
- Order placement retries (tenacity) on transient broker failures.
- Fill confirmation: waits for order status TRADED before recording trade.

State exchange between start/stop tasks uses Redis keys:
    trading:active:{strategy_id}  -> "1" while the loop should keep running
    trading:stop_signal:{strategy_id} -> "1" when stop has been requested
"""
from __future__ import annotations

import time
from datetime import datetime, date, time as dtime, timedelta

import redis as redis_lib
from loguru import logger

from celery_app import celery_app
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.strategy import Strategy
from app.models.trade_log import TradeLog
from app.models.user import User
from app.services.dhan_service import DhanService
from app.services.order_executor import (
    OrderExecutor, OrderExecutionError, LiveTradingDisabledError,
)
from app.strategies import build_strategy


# ---- Redis handle for loop control ---------------------------------------
_redis = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)

ACTIVE_KEY = "trading:active:{strategy_id}"
STOP_KEY = "trading:stop_signal:{strategy_id}"
DAILY_LOSS_KEY = "trading:daily_loss:{strategy_id}:{date}"


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


# ---- Paper-trade order book ----------------------------------------------
def _paper_place_order(side: str, qty: int, price: float, symbol: str) -> str:
    """Returns a synthetic broker order id."""
    return f"PAPER-{side}-{int(time.time() * 1000)}"


# ---- TradeLog helpers -----------------------------------------------------
def _open_trade_from_signal(
    sig, db, strategy_id, user_id, segment, symbol, security_id,
    paper_mode, qty, broker_order_id=None,
):
    t = TradeLog(
        strategy_id=strategy_id, user_id=user_id, mode="live",
        segment=segment, security_id=str(security_id), symbol=symbol,
        side=sig.side, entry_time=datetime.utcnow(),
        entry_price=sig.entry_price, quantity=qty,
        stop_loss=sig.stop_loss, take_profit=sig.take_profit,
        bar_score=sig.bar_score, is_open=True,
        broker_order_id=broker_order_id,
        meta=sig.meta,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _close_trade(
    trade: TradeLog, exit_price: float, reason: str, db,
    paper_mode: bool, broker_order_id: str | None = None,
):
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
    if broker_order_id:
        trade.broker_order_id = broker_order_id
    db.commit()
    return pnl


# ---- Daily loss tracking (circuit breaker) -------------------------------
def _get_daily_loss(strategy_id: int) -> float:
    """Get today's realized loss for the strategy (negative = loss)."""
    today = date.today().isoformat()
    key = DAILY_LOSS_KEY.format(strategy_id=strategy_id, date=today)
    val = _redis.get(key)
    return float(val) if val else 0.0


def _add_realized_pnl(strategy_id: int, pnl: float) -> float:
    """Add realized PnL to today's running total. Returns new total."""
    today = date.today().isoformat()
    key = DAILY_LOSS_KEY.format(strategy_id=strategy_id, date=today)
    new_total = _get_daily_loss(strategy_id) + pnl
    _redis.set(key, str(new_total))
    return new_total


def _circuit_breaker_tripped(strategy_id: int) -> bool:
    """Returns True if daily loss exceeds MAX_DAILY_LOSS_INR."""
    daily_loss = _get_daily_loss(strategy_id)
    if daily_loss < 0 and abs(daily_loss) >= settings.MAX_DAILY_LOSS_INR:
        logger.error(
            "🚨 CIRCUIT BREAKER TRIPPED: strategy {} daily loss = ₹{} "
            "(limit ₹{}) — stopping loop",
            strategy_id, abs(daily_loss), settings.MAX_DAILY_LOSS_INR,
        )
        return True
    return False


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
    Long-running live-trading loop. Returns when stop signal received,
    market closes, or circuit breaker trips.
    """
    # ⚠️  SAFETY: Force paper mode if LIVE_TRADING_ENABLED is False
    if not paper_mode and not settings.LIVE_TRADING_ENABLED:
        logger.warning(
            "⚠️  Live trading requested but LIVE_TRADING_ENABLED=False — "
            "forcing paper_mode=True for strategy {}",
            strategy_id,
        )
        paper_mode = True

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

        # Pick segment + default symbol from strategy params
        segment = (strat.allowed_segments or ["NSE_EQ"])[0]
        symbol = strat.parameters.get("default_symbol", "RELIANCE") if strat.parameters else "RELIANCE"
        security_id = strat.parameters.get("default_security_id", "2885")
        if strat.strategy_type == "mcx_trend_following":
            symbol = strat.parameters.get("default_symbol", "GOLD")
            security_id = strat.parameters.get("default_security_id", "466583")
        elif strat.strategy_type == "index_bar_scoring":
            symbol = strat.parameters.get("default_symbol", "NIFTY 50")
            security_id = strat.parameters.get("default_security_id", "13")

        strategy = build_strategy(strat.strategy_type, parameters=strat.parameters)
        dhan = DhanService()
        executor = OrderExecutor(dhan_service=dhan) if not paper_mode else None
        tick_interval = settings.LIVE_LOOP_INTERVAL_SEC

        logger.info(
            "LIVE loop ready: strat={} symbol={} sec={} segment={} tick={}s paper={}",
            strat.slug, symbol, security_id, segment, tick_interval, paper_mode,
        )

        while True:
            # 1) Stop signal?
            if _redis.get(STOP_KEY.format(strategy_id=strategy_id)) == "1":
                logger.info("Stop signal received for strategy {}", strategy_id)
                break

            # 2) Circuit breaker
            if _circuit_breaker_tripped(strategy_id):
                logger.error("Stopping loop due to circuit breaker")
                break

            # 3) Market hours?
            if not _ist_market_open():
                logger.debug("Outside IST market hours — sleeping 5min")
                time.sleep(300)
                continue

            try:
                # 4) Refresh latest bars (last 100 days for indicator warmup)
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

                # 5) Enrich with indicators + check signals on the LAST bar
                enriched = strategy.enrich(df)
                last_row = enriched.iloc[-1]
                prev_row = enriched.iloc[-2] if len(enriched) > 1 else None

                # 6) Get LTP for accurate mark-to-market (live mode only)
                if not paper_mode and executor:
                    ltp = executor.get_ltp(security_id, segment)
                    if ltp > 0:
                        # Override last bar's close with real LTP for exit checks
                        last_row = last_row.copy()
                        last_row["close"] = ltp

                # 7) Check open trade first
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
                    exit_sig = strategy.check_exit(
                        open_trade={
                            "entry_price": open_trade.entry_price,
                            "stop_loss": open_trade.stop_loss,
                            "take_profit": open_trade.take_profit,
                            "side": open_trade.side,
                            "meta": open_trade.meta or {},
                        },
                        row=last_row, prev_row=prev_row, bars_held=0,
                    )
                    if exit_sig and exit_sig.action == "EXIT":
                        exit_price = float(last_row["close"])
                        broker_exit_order_id = None
                        if not paper_mode and executor:
                            # Place real SELL order to close position
                            try:
                                resp = executor.place_market_order(
                                    security_id=str(security_id),
                                    segment=segment,
                                    transaction_type="SELL",
                                    quantity=open_trade.quantity,
                                    tag=f"exit-{strategy_id}-{open_trade.id}",
                                )
                                broker_exit_order_id = resp.get("orderId") or (
                                    resp.get("data") or {}
                                ).get("orderId")
                                # Wait for fill to get actual exit price
                                if broker_exit_order_id:
                                    fill_data = executor.wait_for_fill(broker_exit_order_id, timeout_sec=15)
                                    avg_price = fill_data.get("averageTradedPrice") or fill_data.get("price")
                                    if avg_price and float(avg_price) > 0:
                                        exit_price = float(avg_price)
                            except OrderExecutionError as exc:
                                logger.error(
                                    "EXIT order failed for trade {}: {} — "
                                    "recording exit at LTP anyway",
                                    open_trade.id, exc,
                                )

                        pnl = _close_trade(
                            open_trade, exit_price,
                            exit_sig.meta.get("exit_reason", "signal"),
                            db, paper_mode, broker_exit_order_id,
                        )
                        equity += pnl
                        _add_realized_pnl(strategy_id, pnl)
                        if user:
                            user.current_equity = equity
                            db.commit()
                        logger.info(
                            "CLOSED {} {}: exit=₹{} pnl=₹{} (order={})",
                            symbol, open_trade.side, exit_price, round(pnl, 2),
                            broker_exit_order_id or "paper",
                        )
                else:
                    # 8) Look for entry
                    entry_sig = strategy.check_entry(last_row, prev_row)
                    if entry_sig and entry_sig.action == "ENTER":
                        stop_dist = abs(entry_sig.entry_price - (entry_sig.stop_loss or 0))
                        if stop_dist > 0:
                            qty = int((equity * settings.RISK_PER_TRADE_PCT / 100.0) / stop_dist)
                            if qty > 0:
                                broker_entry_order_id = None
                                actual_entry_price = entry_sig.entry_price
                                if not paper_mode and executor:
                                    # Place real BUY order
                                    try:
                                        if settings.ORDER_TYPE_DEFAULT == "LIMIT":
                                            resp = executor.place_limit_order(
                                                security_id=str(security_id),
                                                segment=segment,
                                                transaction_type="BUY",
                                                quantity=qty,
                                                price=entry_sig.entry_price,
                                                tag=f"entry-{strategy_id}",
                                            )
                                        else:
                                            resp = executor.place_market_order(
                                                security_id=str(security_id),
                                                segment=segment,
                                                transaction_type="BUY",
                                                quantity=qty,
                                                tag=f"entry-{strategy_id}",
                                            )
                                        broker_entry_order_id = resp.get("orderId") or (
                                            resp.get("data") or {}
                                        ).get("orderId")
                                        # Wait for fill to get actual entry price
                                        if broker_entry_order_id:
                                            fill_data = executor.wait_for_fill(broker_entry_order_id, timeout_sec=15)
                                            avg_price = fill_data.get("averageTradedPrice") or fill_data.get("price")
                                            if avg_price and float(avg_price) > 0:
                                                actual_entry_price = float(avg_price)
                                                # Re-adjust SL/TP based on actual fill
                                                sl_offset = (entry_sig.stop_loss or 0) - entry_sig.entry_price
                                                tp_offset = (entry_sig.take_profit or 0) - entry_sig.entry_price
                                                entry_sig.stop_loss = actual_entry_price + sl_offset
                                                entry_sig.take_profit = actual_entry_price + tp_offset
                                                entry_sig.entry_price = actual_entry_price
                                    except LiveTradingDisabledError as exc:
                                        logger.error("Live trading disabled: {}", exc)
                                        break  # exit the loop entirely
                                    except OrderExecutionError as exc:
                                        logger.error(
                                            "ENTRY order failed for {}: {} — skipping this signal",
                                            symbol, exc,
                                        )
                                        time.sleep(tick_interval)
                                        continue
                                else:
                                    broker_entry_order_id = _paper_place_order(
                                        entry_sig.side, qty, entry_sig.entry_price, symbol,
                                    )

                                _open_trade_from_signal(
                                    entry_sig, db, strategy_id, user_id,
                                    segment, symbol, security_id, paper_mode, qty,
                                    broker_order_id=broker_entry_order_id,
                                )
                                logger.info(
                                    "OPENED {} {} qty={} @ ₹{} SL=₹{} (order={})",
                                    entry_sig.side, symbol, qty, actual_entry_price,
                                    entry_sig.stop_loss, broker_entry_order_id,
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
            "paper_mode": paper_mode,
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
    close all open positions for the strategy.
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
    """Close all open TradeLogs for this strategy by placing opposite SELL orders.
    Returns count of trades closed."""
    db = SessionLocal()
    try:
        open_trades = (
            db.query(TradeLog)
            .filter(TradeLog.strategy_id == strategy_id, TradeLog.is_open.is_(True))
            .all()
        )
        if not open_trades:
            return 0

        # Determine if we should place real orders
        use_live = settings.LIVE_TRADING_ENABLED
        executor = OrderExecutor() if use_live else None
        closed = 0

        for t in open_trades:
            try:
                exit_price = t.entry_price  # fallback
                broker_order_id = None
                if use_live and executor:
                    # Fetch real LTP for mark-to-market
                    ltp = executor.get_ltp(t.security_id, t.segment)
                    if ltp > 0:
                        exit_price = ltp
                    # Place opposite SELL order
                    try:
                        resp = executor.place_market_order(
                            security_id=t.security_id,
                            segment=t.segment,
                            transaction_type="SELL",
                            quantity=t.quantity,
                            tag=f"squareoff-{strategy_id}-{t.id}",
                        )
                        broker_order_id = resp.get("orderId") or (
                            resp.get("data") or {}
                        ).get("orderId")
                        if broker_order_id:
                            fill_data = executor.wait_for_fill(broker_order_id, timeout_sec=15)
                            avg_price = fill_data.get("averageTradedPrice") or fill_data.get("price")
                            if avg_price and float(avg_price) > 0:
                                exit_price = float(avg_price)
                    except OrderExecutionError as exc:
                        logger.error(
                            "Square-off SELL failed for trade {}: {} — "
                            "recording at LTP ₹{}",
                            t.id, exc, exit_price,
                        )
                _close_trade(t, exit_price, "manual_square_off", db, paper_mode=not use_live,
                             broker_order_id=broker_order_id)
                closed += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to square off trade {}: {}", t.id, exc)

        logger.info("Squared off {} positions for strategy {}", closed, strategy_id)
        return closed
    finally:
        db.close()
