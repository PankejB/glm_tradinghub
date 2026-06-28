"""
app.backtest.portfolio_engine
-----------------------------
Portfolio Backtester — runs a single strategy across N instruments
simultaneously and aggregates the results.

Capital allocation: equal split — initial_capital / N per instrument.
Each instrument trades independently with its own 1% risk on its slice.

Aggregation:
- Combined equity curve = sum of per-instrument equity curves, aligned on
  timestamps (union of all dates, forward-filled).
- Total trades = sum across instruments.
- Net profit = sum across instruments.
- Max drawdown recomputed on combined curve (captures diversification benefit).
- GtP = combined annualized return / combined max DD %.
- is_tradeable = GtP > 1.5 (Fitschen gate).

Usage:
    from app.backtest.portfolio_engine import PortfolioBacktester, PortfolioBacktestConfig
    from app.strategies import build_strategy
    from app.services.dhan_service import DhanService

    strategy = build_strategy("stock_counter_trend", params)
    instruments = [
        {"security_id": "2885", "symbol": "RELIANCE", "segment": "NSE_EQ"},
        {"security_id": "3456", "symbol": "TATAMOTORS", "segment": "NSE_EQ"},
    ]
    pb = PortfolioBacktester(
        strategy=strategy,
        instruments=instruments,
        config=PortfolioBacktestConfig(initial_capital=1_000_000),
        start_date=datetime(2025, 6, 23),
        end_date=datetime(2026, 6, 23),
    )
    result = pb.run()
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from app.backtest.engine import Backtester, BacktestConfig, BacktestResult, _json_safe
from app.services.dhan_service import DhanService
from app.strategies.base import StrategyBase


@dataclass
class PortfolioBacktestConfig:
    initial_capital: float = 1_000_000.0
    risk_per_trade_pct: float = 1.0
    commission_per_trade: float = 20.0
    slippage_pct: float = 0.0005


@dataclass
class PortfolioInstrumentResult:
    """Per-instrument result inside a portfolio backtest."""
    security_id: str
    symbol: str
    segment: str
    backtest_result: BacktestResult | None = None
    error: str | None = None

    def to_breakdown_dict(self) -> dict:
        r = self.backtest_result
        if r is None:
            return {
                "security_id": self.security_id,
                "symbol": self.symbol,
                "segment": self.segment,
                "trades": 0,
                "net_profit": 0.0,
                "net_profit_pct": 0.0,
                "win_rate": 0.0,
                "max_drawdown_pct": 0.0,
                "gtp_ratio": 0.0,
                "is_tradeable": False,
                "error": self.error,
            }
        return {
            "security_id": self.security_id,
            "symbol": self.symbol,
            "segment": self.segment,
            "trades": r.total_trades,
            "net_profit": r.net_profit,
            "net_profit_pct": r.net_profit_pct,
            "win_rate": r.win_rate,
            "max_drawdown_pct": r.max_drawdown_pct,
            "gtp_ratio": r.gtp_ratio,
            "is_tradeable": r.is_tradeable,
            "error": self.error,
        }


@dataclass
class PortfolioBacktestResult:
    """Aggregated result across all instruments."""
    initial_capital: float
    final_equity: float
    net_profit: float
    net_profit_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    max_drawdown: float
    max_drawdown_pct: float
    avg_annual_return: float
    gtp_ratio: float
    is_tradeable: bool
    instrument_results: list[PortfolioInstrumentResult] = field(default_factory=list)
    # Combined equity curve: list of {t, equity, drawdown, drawdown_pct}
    equity_curve: list[dict] = field(default_factory=list)
    # All trades across all instruments (each trade dict gets a 'symbol' field added)
    trades: list[dict] = field(default_factory=list)
    parameters: dict = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    error: str | None = None

    @property
    def portfolio_breakdown(self) -> list[dict]:
        return [r.to_breakdown_dict() for r in self.instrument_results]

    def to_dict(self) -> dict:
        return {
            "initial_capital": self.initial_capital,
            "final_equity": self.final_equity,
            "net_profit": self.net_profit,
            "net_profit_pct": self.net_profit_pct,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct": self.max_drawdown_pct,
            "avg_annual_return": self.avg_annual_return,
            "gtp_ratio": self.gtp_ratio,
            "is_tradeable": self.is_tradeable,
            "portfolio_breakdown": _json_safe(self.portfolio_breakdown),
            "trades_json": _json_safe(self.trades),
            "equity_curve_json": _json_safe(self.equity_curve),
            "parameters": _json_safe(self.parameters),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
        }


class PortfolioBacktester:
    """
    Runs a strategy across N instruments and aggregates results.

    Each instrument gets an equal capital allocation (initial_capital / N)
    and is backtested independently. The equity curves are then summed
    date-by-date to produce the combined portfolio equity curve.
    """

    def __init__(
        self,
        strategy: StrategyBase,
        instruments: list[dict],
        config: PortfolioBacktestConfig | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> None:
        self.strategy = strategy
        self.instruments = instruments
        self.config = config or PortfolioBacktestConfig(
            initial_capital=1_000_000.0,
            risk_per_trade_pct=strategy.params.get("risk_per_trade_pct", 1.0),
        )
        self.start_date = start_date
        self.end_date = end_date

    def run(self) -> PortfolioBacktestResult:
        started_at = datetime.utcnow()
        n = len(self.instruments)
        if n == 0:
            return PortfolioBacktestResult(
                initial_capital=self.config.initial_capital,
                final_equity=self.config.initial_capital,
                net_profit=0.0, net_profit_pct=0.0,
                total_trades=0, winning_trades=0, losing_trades=0, win_rate=0.0,
                max_drawdown=0.0, max_drawdown_pct=0.0,
                avg_annual_return=0.0, gtp_ratio=0.0, is_tradeable=False,
                parameters=self.strategy.params,
                started_at=started_at, completed_at=datetime.utcnow(),
                error="No instruments provided",
            )

        per_instrument_capital = self.config.initial_capital / n
        logger.info(
            "Portfolio backtest: {} instruments, ₹{} each (total ₹{})",
            n, per_instrument_capital, self.config.initial_capital,
        )

        instrument_results: list[PortfolioInstrumentResult] = []
        all_equity_curves: list[pd.DataFrame] = []
        all_trades: list[dict] = []

        for inst in self.instruments:
            sec_id = inst["security_id"]
            symbol = inst["symbol"]
            segment = inst.get("segment", "NSE_EQ")
            instrument_type = inst.get("instrument_type")

            logger.info("→ Backtesting {} (sec={}, seg={})", symbol, sec_id, segment)

            ir = PortfolioInstrumentResult(
                security_id=str(sec_id), symbol=symbol, segment=segment,
            )

            try:
                # Load bars from DB
                df = DhanService.load_bars(
                    security_id=str(sec_id),
                    timeframe="1D",
                    start=self.start_date,
                    end=self.end_date,
                )
                if df.empty:
                    # Auto-sync from DhanHQ if missing
                    logger.warning("No local bars for {}, syncing from DhanHQ…", symbol)
                    svc = DhanService()
                    svc.sync_historical(
                        security_id=str(sec_id), symbol=symbol,
                        segment=segment, interval="1D", days=365,
                        instrument_type=instrument_type,
                    )
                    df = DhanService.load_bars(
                        security_id=str(sec_id), timeframe="1D",
                        start=self.start_date, end=self.end_date,
                    )

                if df.empty:
                    raise ValueError(f"No OHLCV data available for {symbol}")

                # Run single-instrument backtest with its capital slice
                bt = Backtester(
                    strategy=self.strategy,
                    df=df,
                    config=BacktestConfig(
                        initial_capital=per_instrument_capital,
                        risk_per_trade_pct=self.config.risk_per_trade_pct,
                        commission_per_trade=self.config.commission_per_trade,
                        slippage_pct=self.config.slippage_pct,
                    ),
                    symbol=symbol,
                    segment=segment,
                )
                result = bt.run()
                ir.backtest_result = result

                # Collect equity curve as DataFrame for later merging
                if result.equity_curve:
                    ec_df = pd.DataFrame(result.equity_curve)
                    ec_df["t"] = pd.to_datetime(ec_df["t"])
                    ec_df = ec_df.rename(columns={"equity": symbol})
                    all_equity_curves.append(ec_df[["t", symbol]])

                # Tag trades with symbol and collect
                for trade in result.trades:
                    trade["symbol"] = symbol
                    trade["segment"] = segment
                    trade["security_id"] = str(sec_id)
                    all_trades.append(trade)

                logger.info(
                    "  {} done: trades={} gtp={:.2f} pnl=₹{}",
                    symbol, result.total_trades, result.gtp_ratio, result.net_profit,
                )

            except Exception as exc:  # noqa: BLE001
                logger.exception("  {} FAILED: {}", symbol, exc)
                ir.error = str(exc)

            instrument_results.append(ir)

        # ----- Aggregate ---------------------------------------------------
        logger.info("Aggregating portfolio results…")

        # Merge equity curves on timestamp (union of dates, forward-fill)
        combined_equity, combined_curve_list = self._merge_equity_curves(
            all_equity_curves, self.config.initial_capital
        )

        # Max drawdown on combined curve
        max_dd, max_dd_pct = self._compute_max_drawdown(combined_equity)

        # Sum trades
        total_trades = sum(
            ir.backtest_result.total_trades
            for ir in instrument_results if ir.backtest_result
        )
        total_wins = sum(
            ir.backtest_result.winning_trades
            for ir in instrument_results if ir.backtest_result
        )
        total_losses = sum(
            ir.backtest_result.losing_trades
            for ir in instrument_results if ir.backtest_result
        )
        win_rate = (total_wins / total_trades * 100.0) if total_trades > 0 else 0.0

        # Sum net profit
        total_net_profit = sum(
            ir.backtest_result.net_profit
            for ir in instrument_results if ir.backtest_result
        )
        final_equity = self.config.initial_capital + total_net_profit
        net_profit_pct = (total_net_profit / self.config.initial_capital) * 100.0

        # Annualized return on combined curve
        avg_annual_return = self._annualised_return(
            self.config.initial_capital, final_equity, combined_curve_list
        )

        # GtP on combined curve
        gtp = avg_annual_return / max_dd_pct if max_dd_pct > 0 else 0.0
        is_tradeable = gtp > 1.5

        return PortfolioBacktestResult(
            initial_capital=self.config.initial_capital,
            final_equity=round(final_equity, 2),
            net_profit=round(total_net_profit, 2),
            net_profit_pct=round(net_profit_pct, 4),
            total_trades=total_trades,
            winning_trades=total_wins,
            losing_trades=total_losses,
            win_rate=round(win_rate, 4),
            max_drawdown=round(max_dd, 2),
            max_drawdown_pct=round(max_dd_pct, 4),
            avg_annual_return=round(avg_annual_return, 4),
            gtp_ratio=round(gtp, 4),
            is_tradeable=is_tradeable,
            instrument_results=instrument_results,
            equity_curve=combined_curve_list,
            trades=all_trades,
            parameters=self.strategy.params,
            started_at=started_at,
            completed_at=datetime.utcnow(),
        )

    # ----- helpers --------------------------------------------------------
    def _merge_equity_curves(
        self,
        curves: list[pd.DataFrame],
        initial_capital: float,
    ) -> tuple[pd.Series, list[dict]]:
        """
        Merge per-instrument equity curves into a combined curve.
        Returns (combined_equity_series, list_of_curve_dicts).
        Each curve dict: {t, equity, drawdown, drawdown_pct}
        """
        if not curves:
            return pd.Series(dtype=float), []

        # Outer join on timestamp, forward-fill gaps
        merged = curves[0]
        for c in curves[1:]:
            merged = pd.merge(merged, c, on="t", how="outer")
        merged = merged.sort_values("t").reset_index(drop=True)
        # Forward-fill each instrument's equity (hold last known value)
        symbol_cols = [c for c in merged.columns if c != "t"]
        merged[symbol_cols] = merged[symbol_cols].ffill().fillna(initial_capital / len(curves))
        # Sum across instruments
        merged["equity"] = merged[symbol_cols].sum(axis=1)

        # Compute drawdown
        merged["peak"] = merged["equity"].cummax()
        merged["drawdown"] = merged["peak"] - merged["equity"]
        merged["drawdown_pct"] = (merged["drawdown"] / merged["peak"] * 100.0).round(4)

        # Build the output list (downsample to <= 500 points)
        out = merged[["t", "equity", "drawdown", "drawdown_pct"]].copy()
        if len(out) > 500:
            step = max(1, len(out) // 500)
            out = out.iloc[::step]

        curve_list = []
        for _, row in out.iterrows():
            ts = row["t"]
            if hasattr(ts, "isoformat"):
                ts_str = ts.isoformat()
            else:
                ts_str = str(ts)
            curve_list.append({
                "t": ts_str,
                "equity": round(float(row["equity"]), 2),
                "drawdown": round(float(row["drawdown"]), 2),
                "drawdown_pct": float(row["drawdown_pct"]),
            })
        return merged["equity"], curve_list

    def _compute_max_drawdown(self, equity_series: pd.Series) -> tuple[float, float]:
        """Returns (max_dd_absolute, max_dd_pct)."""
        if equity_series.empty:
            return 0.0, 0.0
        peak = equity_series.cummax()
        dd = peak - equity_series
        max_dd = float(dd.max())
        peak_at_max = float(peak.iloc[dd.values.argmax()] if dd.max() > 0 else peak.iloc[0])
        max_dd_pct = (max_dd / peak_at_max * 100.0) if peak_at_max > 0 else 0.0
        return max_dd, max_dd_pct

    def _annualised_return(
        self,
        initial: float,
        final: float,
        equity_curve: list[dict],
    ) -> float:
        if not equity_curve or len(equity_curve) < 2:
            return 0.0
        try:
            t0 = datetime.fromisoformat(equity_curve[0]["t"])
            tN = datetime.fromisoformat(equity_curve[-1]["t"])
        except Exception:  # noqa: BLE001
            return 0.0
        days = (tN - t0).days
        if days <= 0 or initial <= 0 or final <= 0:
            return 0.0
        cagr = (final / initial) ** (365.0 / days) - 1.0
        return cagr * 100.0
