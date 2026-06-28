"""
app.tasks.sweep_tasks
---------------------
Celery task: run a parameter sweep — N backtests varying one or two
parameters across a range. Persists results + identifies the best run
by GtP ratio.
"""
import itertools
from datetime import datetime
from loguru import logger

from celery_app import celery_app
from app.db.session import SessionLocal
from app.models.sweep_result import SweepResult
from app.models.strategy import Strategy
from app.services.dhan_service import DhanService
from app.strategies import build_strategy
from app.backtest.engine import Backtester, BacktestConfig


def _generate_param_combinations(sweep_parameters: list[dict]) -> list[dict]:
    """
    Generate all combinations of sweep parameter values.
    For 1 parameter: returns [{key: val1}, {key: val2}, ...]
    For 2 parameters: returns cartesian product [{k1:v1, k2:v1}, {k1:v1, k2:v2}, ...]
    """
    if not sweep_parameters:
        return [{}]

    keys = [p["key"] for p in sweep_parameters]
    value_lists = [p["values"] for p in sweep_parameters]

    combinations = []
    for combo in itertools.product(*value_lists):
        combinations.append(dict(zip(keys, combo)))
    return combinations


@celery_app.task(
    name="task_run_parameter_sweep",
    bind=True,
    max_retries=1,
    default_retry_delay=10,
)
def task_run_parameter_sweep(
    self,
    sweep_result_id: int,
    base_parameters: dict,
    sweep_parameters: list[dict],
):
    """Run a parameter sweep. The SweepResult row is already created by the API."""
    db = SessionLocal()
    try:
        sr = db.get(SweepResult, sweep_result_id)
        if not sr:
            logger.error("SweepResult {} not found", sweep_result_id)
            return {"status": "error", "error": "SweepResult not found"}

        sr.status = "running"
        sr.started_at = datetime.utcnow()
        db.commit()

        strat = db.get(Strategy, sr.strategy_id)
        if not strat:
            sr.status = "failed"
            sr.error_message = f"Strategy {sr.strategy_id} not found"
            db.commit()
            return {"status": "error", "error": sr.error_message}

        # Generate all parameter combinations
        combinations = _generate_param_combinations(sweep_parameters)
        sr.total_runs = len(combinations)
        db.commit()

        logger.info(
            "Parameter sweep #{} starting: {} combinations, strategy_id={}",
            sr.id, len(combinations), sr.strategy_id,
        )

        # Load bars ONCE (all sweep runs use the same data)
        df = DhanService.load_bars(
            security_id=sr.security_id, timeframe="1D",
            start=sr.start_date, end=sr.end_date,
        )
        if df.empty:
            # Try syncing from DhanHQ
            logger.warning("No local bars for {}, syncing…", sr.symbol)
            svc = DhanService()
            svc.sync_historical(
                security_id=sr.security_id, symbol=sr.symbol,
                segment=sr.segment, interval="1D", days=365,
            )
            df = DhanService.load_bars(
                security_id=sr.security_id, timeframe="1D",
                start=sr.start_date, end=sr.end_date,
            )

        if df.empty:
            sr.status = "failed"
            sr.error_message = f"No OHLCV data for {sr.symbol}"
            db.commit()
            return {"status": "error", "error": sr.error_message}

        logger.info("Loaded {} bars for {} ({}..{})",
                    len(df), sr.symbol, df["timestamp"].min(), df["timestamp"].max())

        # Run backtest for each parameter combination
        runs = []
        best_run = None
        best_gtp = -999.0
        completed = 0

        for i, combo in enumerate(combinations):
            # Merge base params with sweep combo (combo overrides base)
            merged_params = {**strat.parameters, **base_parameters, **combo}

            logger.info(
                "  Sweep run {}/{}: params={}",
                i + 1, len(combinations), combo,
            )

            try:
                strategy = build_strategy(strat.strategy_type, merged_params)
                bt = Backtester(
                    strategy=strategy,
                    df=df,
                    config=BacktestConfig(
                        initial_capital=sr.initial_capital,
                        risk_per_trade_pct=merged_params.get("risk_per_trade_pct", 1.0),
                    ),
                    symbol=sr.symbol,
                    segment=sr.segment,
                )
                result = bt.run()

                run_result = {
                    "params": combo,
                    "net_profit": result.net_profit,
                    "net_profit_pct": result.net_profit_pct,
                    "total_trades": result.total_trades,
                    "win_rate": result.win_rate,
                    "max_drawdown_pct": result.max_drawdown_pct,
                    "avg_annual_return": result.avg_annual_return,
                    "gtp_ratio": result.gtp_ratio,
                    "is_tradeable": result.is_tradeable,
                    "error": result.error,
                }
                runs.append(run_result)
                completed += 1

                # Track best run by GtP
                if result.gtp_ratio > best_gtp:
                    best_gtp = result.gtp_ratio
                    best_run = run_result

                logger.info(
                    "    → trades={} gtp={:.2f} pnl=₹{}",
                    result.total_trades, result.gtp_ratio, result.net_profit,
                )

            except Exception as exc:  # noqa: BLE001
                logger.exception("  Sweep run {} failed: {}", i + 1, exc)
                runs.append({
                    "params": combo,
                    "net_profit": 0.0, "net_profit_pct": 0.0,
                    "total_trades": 0, "win_rate": 0.0,
                    "max_drawdown_pct": 0.0, "avg_annual_return": 0.0,
                    "gtp_ratio": 0.0, "is_tradeable": False,
                    "error": str(exc),
                })

            # Update progress in DB every 5 runs (don't commit too often)
            if completed % 5 == 0 or i == len(combinations) - 1:
                sr.runs = runs
                sr.completed_runs = completed
                sr.best_run = best_run
                db.commit()

        # Final update
        sr.runs = runs
        sr.completed_runs = completed
        sr.best_run = best_run
        sr.status = "completed"
        sr.completed_at = datetime.utcnow()
        db.commit()

        # Update strategy tradeability if best run is tradeable
        if best_run and best_run.get("is_tradeable") and not strat.is_tradeable:
            strat.is_tradeable = True
            strat.latest_gtp_ratio = best_run["gtp_ratio"]
            logger.info("Strategy {} marked tradeable (sweep best GtP={})",
                        strat.slug, best_run["gtp_ratio"])
        elif best_run and best_run.get("gtp_ratio", 0) > (strat.latest_gtp_ratio or 0):
            strat.latest_gtp_ratio = best_run["gtp_ratio"]

        db.commit()

        logger.info(
            "Parameter sweep #{} done: {} runs, best GtP={:.2f}",
            sr.id, completed, best_gtp if best_run else 0,
        )
        return {
            "status": "completed",
            "sweep_id": sr.id,
            "total_runs": len(combinations),
            "completed_runs": completed,
            "best_gtp": best_run["gtp_ratio"] if best_run else 0,
            "best_params": best_run["params"] if best_run else {},
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Parameter sweep task failed: {}", exc)
        try:
            sr = db.get(SweepResult, sweep_result_id)
            if sr:
                sr.status = "failed"
                sr.error_message = str(exc)
                sr.completed_at = datetime.utcnow()
                db.commit()
        except Exception:  # noqa: BLE001
            pass
        return {"status": "error", "error": str(exc)}
    finally:
        db.close()
