"""
app.tasks.portfolio_backtest_tasks
----------------------------------
Celery task: run a portfolio backtest (strategy across N instruments)
in the background and persist the aggregated result + child results.
"""
from datetime import datetime
from loguru import logger

from celery_app import celery_app
from app.db.session import SessionLocal
from app.models.backtest_result import BacktestResult
from app.models.strategy import Strategy
from app.strategies import build_strategy
from app.backtest.portfolio_engine import PortfolioBacktester, PortfolioBacktestConfig


@celery_app.task(
    name="task_run_portfolio_backtest",
    bind=True,
    max_retries=1,
    default_retry_delay=10,
)
def task_run_portfolio_backtest(
    self,
    parent_result_id: int,
    instruments: list[dict],
    start_date: str,
    end_date: str,
    parameters: dict | None = None,
):
    """
    Run a portfolio backtest. The parent BacktestResult row is already
    created by the API endpoint with status='pending' and is_portfolio=True.

    Args:
        parent_result_id: id of the parent BacktestResult row
        instruments: list of {security_id, symbol, segment, instrument_type?}
        start_date: ISO date string
        end_date: ISO date string
        parameters: strategy parameter overrides (applied to all instruments)
    """
    db = SessionLocal()
    try:
        parent = db.get(BacktestResult, parent_result_id)
        if not parent:
            logger.error("Portfolio parent BacktestResult {} not found", parent_result_id)
            return {"status": "error", "error": "Parent BacktestResult not found"}

        parent.status = "running"
        db.commit()
        logger.info(
            "Portfolio backtest #{} starting: {} instruments, strategy_id={}",
            parent.id, len(instruments), parent.strategy_id,
        )

        strat = db.get(Strategy, parent.strategy_id)
        if not strat:
            parent.status = "failed"
            parent.error_message = f"Strategy {parent.strategy_id} not found"
            db.commit()
            return {"status": "error", "error": parent.error_message}

        # Parse dates
        try:
            start_dt = datetime.fromisoformat(start_date) if isinstance(start_date, str) else start_date
            end_dt = datetime.fromisoformat(end_date) if isinstance(end_date, str) else end_date
        except Exception as exc:
            parent.status = "failed"
            parent.error_message = f"Date parse error: {exc}"
            db.commit()
            return {"status": "error", "error": parent.error_message}

        # Build strategy with merged parameters
        merged_params = {**strat.parameters, **(parameters or {})}
        strategy = build_strategy(strat.strategy_type, merged_params)

        # Run portfolio backtester
        pb = PortfolioBacktester(
            strategy=strategy,
            instruments=instruments,
            config=PortfolioBacktestConfig(
                initial_capital=parent.initial_capital,
                risk_per_trade_pct=merged_params.get("risk_per_trade_pct", 1.0),
            ),
            start_date=start_dt,
            end_date=end_dt,
        )
        result = pb.run()

        # ----- Persist parent (aggregated) result -------------------------
        parent.final_equity = result.final_equity
        parent.net_profit = result.net_profit
        parent.net_profit_pct = result.net_profit_pct
        parent.total_trades = result.total_trades
        parent.winning_trades = result.winning_trades
        parent.losing_trades = result.losing_trades
        parent.win_rate = result.win_rate
        parent.max_drawdown = result.max_drawdown
        parent.max_drawdown_pct = result.max_drawdown_pct
        parent.avg_annual_return = result.avg_annual_return
        parent.gtp_ratio = result.gtp_ratio
        parent.is_tradeable = result.is_tradeable
        parent.trades_json = result.trades
        parent.equity_curve_json = result.equity_curve
        parent.portfolio_breakdown = result.portfolio_breakdown
        parent.status = "failed" if result.error else "completed"
        parent.error_message = result.error
        parent.completed_at = datetime.utcnow()

        # ----- Persist child rows (one per instrument) --------------------
        for ir in result.instrument_results:
            child = BacktestResult(
                strategy_id=parent.strategy_id,
                segment=ir.segment,
                security_id=ir.security_id,
                symbol=ir.symbol,
                start_date=start_dt,
                end_date=end_dt,
                initial_capital=parent.initial_capital / len(instruments),
                final_equity=ir.backtest_result.final_equity if ir.backtest_result else parent.initial_capital / len(instruments),
                net_profit=ir.backtest_result.net_profit if ir.backtest_result else 0.0,
                net_profit_pct=ir.backtest_result.net_profit_pct if ir.backtest_result else 0.0,
                total_trades=ir.backtest_result.total_trades if ir.backtest_result else 0,
                winning_trades=ir.backtest_result.winning_trades if ir.backtest_result else 0,
                losing_trades=ir.backtest_result.losing_trades if ir.backtest_result else 0,
                win_rate=ir.backtest_result.win_rate if ir.backtest_result else 0.0,
                max_drawdown=ir.backtest_result.max_drawdown if ir.backtest_result else 0.0,
                max_drawdown_pct=ir.backtest_result.max_drawdown_pct if ir.backtest_result else 0.0,
                avg_annual_return=ir.backtest_result.avg_annual_return if ir.backtest_result else 0.0,
                gtp_ratio=ir.backtest_result.gtp_ratio if ir.backtest_result else 0.0,
                is_tradeable=ir.backtest_result.is_tradeable if ir.backtest_result else False,
                trades_json=ir.backtest_result.trades if ir.backtest_result else [],
                equity_curve_json=ir.backtest_result.equity_curve if ir.backtest_result else [],
                parameters=merged_params,
                is_portfolio=False,
                parent_portfolio_id=parent.id,
                status="failed" if ir.error else "completed",
                error_message=ir.error,
                completed_at=datetime.utcnow(),
            )
            db.add(child)

        # Update strategy tradeability if portfolio is tradeable
        if result.is_tradeable and not strat.is_tradeable:
            strat.is_tradeable = True
            strat.latest_gtp_ratio = result.gtp_ratio
            logger.info(
                "Strategy {} marked tradeable (portfolio GtP={})",
                strat.slug, result.gtp_ratio,
            )
        elif result.gtp_ratio > (strat.latest_gtp_ratio or 0):
            strat.latest_gtp_ratio = result.gtp_ratio

        db.commit()
        logger.info(
            "Portfolio backtest #{} done: instruments={} trades={} gtp={:.2f} tradeable={} pnl=₹{}",
            parent.id, len(instruments), result.total_trades,
            result.gtp_ratio, result.is_tradeable, result.net_profit,
        )
        return {
            "status": parent.status,
            "backtest_id": parent.id,
            "gtp_ratio": result.gtp_ratio,
            "is_tradeable": result.is_tradeable,
            "total_trades": result.total_trades,
            "net_profit": result.net_profit,
            "instruments": len(instruments),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Portfolio backtest task failed: {}", exc)
        try:
            parent = db.get(BacktestResult, parent_result_id)
            if parent:
                parent.status = "failed"
                parent.error_message = str(exc)
                parent.completed_at = datetime.utcnow()
                db.commit()
        except Exception:  # noqa: BLE001
            pass
        return {"status": "error", "error": str(exc)}
    finally:
        db.close()
