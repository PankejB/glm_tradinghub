"""
app.tasks.backtest_tasks
------------------------
Celery task: run a backtest in the background and persist the result.

Triggered by POST /api/backtest/start which:
1. Creates a BacktestResult row with status='pending'
2. Calls task_run_backtest.delay(br.id)
"""
from datetime import datetime
from loguru import logger

from celery_app import celery_app
from app.db.session import SessionLocal
from app.models.backtest_result import BacktestResult
from app.models.strategy import Strategy
from app.services.dhan_service import DhanService
from app.strategies import build_strategy
from app.backtest.engine import Backtester, BacktestConfig


@celery_app.task(
    name="task_run_backtest",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
)
def task_run_backtest(self, backtest_result_id: int):
    """
    Run a backtest given a BacktestResult.id.
    Updates the row in-place with metrics + equity curve when done.
    """
    db = SessionLocal()
    try:
        br = db.get(BacktestResult, backtest_result_id)
        if not br:
            logger.error("BacktestResult {} not found", backtest_result_id)
            return {"status": "error", "error": "BacktestResult not found"}

        br.status = "running"
        br.started_at_marker = datetime.utcnow() if False else None  # noop
        db.commit()
        logger.info("Backtest #{} starting (strategy_id={}, symbol={})",
                    br.id, br.strategy_id, br.symbol)

        strat = db.get(Strategy, br.strategy_id)
        if not strat:
            br.status = "failed"
            br.error_message = f"Strategy {br.strategy_id} not found"
            db.commit()
            return {"status": "error", "error": br.error_message}

        # ---- Load OHLCV from DB (already synced via /api/data/sync) -------
        df = DhanService.load_bars(
            security_id=br.security_id,
            timeframe="1D",
            start=br.start_date,
            end=br.end_date,
        )
        if df.empty:
            # Try to fetch live from DhanHQ if DB has nothing for this symbol
            logger.warning("No local bars for {}, fetching from DhanHQ…", br.symbol)
            svc = DhanService()
            n = svc.sync_historical(
                security_id=br.security_id,
                symbol=br.symbol,
                segment=br.segment,
                interval="1D",
                days=365,
            )
            df = DhanService.load_bars(
                security_id=br.security_id, timeframe="1D",
                start=br.start_date, end=br.end_date,
            )
            logger.info("Fetched {} bars from DhanHQ for {}", n, br.symbol)

        if df.empty:
            br.status = "failed"
            br.error_message = f"No OHLCV data for {br.symbol}"
            db.commit()
            return {"status": "error", "error": br.error_message}

        logger.info("Loaded {} bars for {} ({}..{})",
                    len(df), br.symbol, df["timestamp"].min(), df["timestamp"].max())

        # ---- Build strategy + run backtester ------------------------------
        strategy = build_strategy(strat.strategy_type, parameters=br.parameters)
        bt = Backtester(
            strategy=strategy,
            df=df,
            config=BacktestConfig(
                initial_capital=br.initial_capital,
                risk_per_trade_pct=strategy.params.get("risk_per_trade_pct", 1.0),
            ),
            symbol=br.symbol,
            segment=br.segment,
        )
        result = bt.run()

        # ---- Persist results ----------------------------------------------
        br.final_equity = result.final_equity
        br.net_profit = result.net_profit
        br.net_profit_pct = result.net_profit_pct
        br.total_trades = result.total_trades
        br.winning_trades = result.winning_trades
        br.losing_trades = result.losing_trades
        br.win_rate = result.win_rate
        br.max_drawdown = result.max_drawdown
        br.max_drawdown_pct = result.max_drawdown_pct
        br.avg_annual_return = result.avg_annual_return
        br.gtp_ratio = result.gtp_ratio
        br.is_tradeable = result.is_tradeable
        br.trades_json = result.trades
        br.equity_curve_json = result.equity_curve
        br.status = "failed" if result.error else "completed"
        br.error_message = result.error
        br.completed_at = datetime.utcnow()

        # Update the strategy's cached tradeability flag
        if result.is_tradeable and not strat.is_tradeable:
            strat.is_tradeable = True
            strat.latest_gtp_ratio = result.gtp_ratio
            logger.info("Strategy {} marked tradeable (GtP={})",
                        strat.slug, result.gtp_ratio)
        elif result.gtp_ratio > (strat.latest_gtp_ratio or 0):
            strat.latest_gtp_ratio = result.gtp_ratio

        db.commit()
        logger.info(
            "Backtest #{} done: trades={} gtp={:.2f} tradeable={} pnl={}",
            br.id, result.total_trades, result.gtp_ratio,
            result.is_tradeable, result.net_profit,
        )
        return {
            "status": br.status,
            "backtest_id": br.id,
            "gtp_ratio": result.gtp_ratio,
            "is_tradeable": result.is_tradeable,
            "total_trades": result.total_trades,
            "net_profit": result.net_profit,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Backtest task failed: {}", exc)
        try:
            br = db.get(BacktestResult, backtest_result_id)
            if br:
                br.status = "failed"
                br.error_message = str(exc)
                br.completed_at = datetime.utcnow()
                db.commit()
        except Exception:  # noqa: BLE001
            pass
        return {"status": "error", "error": str(exc)}
    finally:
        db.close()
