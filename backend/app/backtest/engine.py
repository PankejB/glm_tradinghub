"""
app.backtest.engine
-------------------
The Backtester. Runs a strategy over an enriched OHLCV DataFrame and
emits a BacktestResult dict + equity curve.

Key Fitschen rules implemented here:
- Fixed-Risk Money Management (Ch 11/14):
    qty = (equity × risk_per_trade_pct/100) / stop_distance
    → if SL is hit, loss = exactly risk_per_trade_pct% of equity
- One position at a time per strategy
- Tradeability gate: Gain-to-Pain Ratio > 1.5
    GtP = avg_annual_return / max_drawdown
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from app.strategies.base import StrategyBase, Signal


# ----------------------------------------------------------------------
#  JSON sanitiser — converts datetimes/numpy scalars to JSON-safe types
# ----------------------------------------------------------------------
def _json_safe(obj: Any) -> Any:
    """Recursively convert datetimes, numpy types, and pandas timestamps
    into JSON-serialisable primitives. SQLAlchemy's JSON column uses
    json.dumps() which cannot handle these natively."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


@dataclass
class BacktestConfig:
    initial_capital: float = 1_000_000.0
    risk_per_trade_pct: float = 1.0
    commission_per_trade: float = 20.0     # ₹20 per order (typical discount broker)
    slippage_pct: float = 0.0005           # 0.05% slippage on entry/exit
    allow_short: bool = False              # strategies here are long-only


@dataclass
class BacktestResult:
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
    trades: list[dict] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)
    parameters: dict = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    error: str | None = None

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
            "trades_json": self.trades,
            "equity_curve_json": self.equity_curve,
            "parameters": self.parameters,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
        }


class Backtester:
    """
    Event-driven backtester (single-pass, vectorised indicators + per-bar loop).

    Usage:
        bt = Backtester(strategy, df, config=BacktestConfig(initial_capital=1_000_000))
        result = bt.run()
    """

    def __init__(
        self,
        strategy: StrategyBase,
        df: pd.DataFrame,
        config: BacktestConfig | None = None,
        symbol: str = "UNKNOWN",
        segment: str = "NSE_EQ",
    ) -> None:
        self.strategy = strategy
        self.config = config or BacktestConfig(
            initial_capital=1_000_000.0,
            risk_per_trade_pct=strategy.params.get("risk_per_trade_pct", 1.0),
        )
        self.symbol = symbol
        self.segment = segment
        # Enrich once with strategy indicators (vectorised)
        self.df = strategy.enrich(df.reset_index(drop=True).copy())

    # ----------------------------------------------------------- run loop
    def run(self) -> BacktestResult:
        started_at = datetime.utcnow()
        try:
            return self._run_inner(started_at)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Backtest failed: {}", exc)
            return BacktestResult(
                initial_capital=self.config.initial_capital,
                final_equity=self.config.initial_capital,
                net_profit=0.0, net_profit_pct=0.0,
                total_trades=0, winning_trades=0, losing_trades=0, win_rate=0.0,
                max_drawdown=0.0, max_drawdown_pct=0.0,
                avg_annual_return=0.0, gtp_ratio=0.0, is_tradeable=False,
                parameters=self.strategy.params,
                started_at=started_at, completed_at=datetime.utcnow(),
                error=str(exc),
            )

    def _run_inner(self, started_at: datetime) -> BacktestResult:
        equity = self.config.initial_capital
        peak_equity = equity
        max_dd = 0.0
        max_dd_pct = 0.0

        open_trade: dict | None = None
        trades: list[dict] = []
        equity_curve: list[dict] = []

        df = self.df
        prev_row: pd.Series | None = None

        for i in range(len(df)):
            row = df.iloc[i]
            ts = row["timestamp"]
            if hasattr(ts, "to_pydatetime"):
                ts = ts.to_pydatetime()

            # ----- Manage open trade first ---------------------------------
            if open_trade is not None:
                bars_held = i - open_trade["bar_index"]
                # Update trailing-stop housekeeping for MCX strategy
                self._update_trailing_state(open_trade, row)
                exit_sig = self.strategy.check_exit(open_trade, row, prev_row, bars_held)
                if exit_sig is not None:
                    exit_price = self._apply_slippage(exit_sig.entry_price, is_buy=False)
                    pnl = self._compute_pnl(open_trade, exit_price)
                    equity += pnl
                    open_trade.update({
                        "exit_time": ts,
                        "exit_price": exit_price,
                        "exit_reason": exit_sig.meta.get("exit_reason", "unknown"),
                        "pnl": pnl,
                        "pnl_pct": pnl / (open_trade["entry_price"] * open_trade["quantity"]) * 100 if open_trade["quantity"] else 0.0,
                        "bars_held": bars_held,
                        "is_open": False,
                    })
                    trades.append(open_trade)
                    open_trade = None

            # ----- Look for entry (only if flat) ---------------------------
            if open_trade is None:
                entry_sig = self.strategy.check_entry(row, prev_row)
                if entry_sig and entry_sig.action == "ENTER":
                    qty = self._size_position(equity, entry_sig)
                    if qty > 0:
                        entry_price = self._apply_slippage(entry_sig.entry_price, is_buy=True)
                        open_trade = {
                            "entry_time": ts,
                            "entry_price": entry_price,
                            "quantity": qty,
                            "stop_loss": entry_sig.stop_loss,
                            "take_profit": entry_sig.take_profit,
                            "bar_index": i,
                            "bar_score": entry_sig.bar_score,
                            "side": entry_sig.side,
                            "segment": self.segment,
                            "symbol": self.symbol,
                            "risk_amount": (equity * self.config.risk_per_trade_pct / 100.0),
                            "meta": dict(entry_sig.meta),
                            "is_open": True,
                        }

            # ----- Mark-to-market equity -----------------------------------
            if open_trade is not None:
                cur_price = self._apply_slippage(float(row["close"]), is_buy=False)
                unreal = (cur_price - open_trade["entry_price"]) * open_trade["quantity"]
                if open_trade["side"] == "SELL":
                    unreal = -unreal
                mtm_equity = equity + unreal
            else:
                mtm_equity = equity

            peak_equity = max(peak_equity, mtm_equity)
            dd = peak_equity - mtm_equity
            dd_pct = dd / peak_equity if peak_equity > 0 else 0.0
            max_dd = max(max_dd, dd)
            max_dd_pct = max(max_dd_pct, dd_pct)

            equity_curve.append({
                "t": ts.isoformat() if isinstance(ts, datetime) else str(ts),
                "equity": round(mtm_equity, 2),
                "drawdown": round(dd, 2),
                "drawdown_pct": round(dd_pct * 100, 4),
            })

            prev_row = row

        # ----- Force-close any trade still open at end ---------------------
        if open_trade is not None:
            last_row = df.iloc[-1]
            exit_price = self._apply_slippage(float(last_row["close"]), is_buy=False)
            pnl = self._compute_pnl(open_trade, exit_price)
            equity += pnl
            open_trade.update({
                "exit_time": last_row["timestamp"].to_pydatetime()
                if hasattr(last_row["timestamp"], "to_pydatetime")
                else last_row["timestamp"],
                "exit_price": exit_price,
                "exit_reason": "end_of_data",
                "pnl": pnl,
                "pnl_pct": pnl / (open_trade["entry_price"] * open_trade["quantity"]) * 100 if open_trade["quantity"] else 0.0,
                "bars_held": len(df) - 1 - open_trade["bar_index"],
                "is_open": False,
            })
            trades.append(open_trade)
            open_trade = None

        # ----- Aggregate metrics ------------------------------------------
        final_equity = equity
        net_profit = final_equity - self.config.initial_capital
        net_profit_pct = net_profit / self.config.initial_capital * 100.0
        total_trades = len(trades)
        wins = sum(1 for t in trades if (t.get("pnl") or 0) > 0)
        losses = sum(1 for t in trades if (t.get("pnl") or 0) < 0)
        win_rate = wins / total_trades * 100.0 if total_trades else 0.0

        # Annualised return approximation using date span of equity curve
        avg_annual_return = self._annualised_return(
            self.config.initial_capital, final_equity, equity_curve
        )

        # Gain-to-Pain ratio
        gtp = avg_annual_return / (max_dd_pct * 100.0) if max_dd_pct > 0 else 0.0
        is_tradeable = gtp > 1.5

        # Sanitise trades + parameters for JSON persistence (DB JSON column)
        # Converts datetime → ISO string, numpy scalars → Python scalars.
        trades_safe = _json_safe(trades)
        params_safe = _json_safe(self.strategy.params)

        return BacktestResult(
            initial_capital=self.config.initial_capital,
            final_equity=round(final_equity, 2),
            net_profit=round(net_profit, 2),
            net_profit_pct=round(net_profit_pct, 4),
            total_trades=total_trades,
            winning_trades=wins,
            losing_trades=losses,
            win_rate=round(win_rate, 4),
            max_drawdown=round(max_dd, 2),
            max_drawdown_pct=round(max_dd_pct * 100, 4),
            avg_annual_return=round(avg_annual_return, 4),
            gtp_ratio=round(gtp, 4),
            is_tradeable=is_tradeable,
            trades=trades_safe,
            equity_curve=equity_curve,
            parameters=params_safe,
            started_at=started_at,
            completed_at=datetime.utcnow(),
        )

    # ----- helpers --------------------------------------------------------
    def _size_position(self, equity: float, sig: Signal) -> int:
        """
        Fitschen Fixed-Risk sizing (Ch 11/14):
            qty = (equity × risk_pct/100) / stop_distance
            → SL hit → loss == risk_pct% of equity

        For option strategies, sig.entry_price is already the option premium.
        """
        if not sig.entry_price or not sig.stop_loss:
            return 0
        stop_distance = abs(sig.entry_price - sig.stop_loss)
        if stop_distance <= 0:
            return 0
        risk_amount = equity * self.config.risk_per_trade_pct / 100.0
        qty = risk_amount / stop_distance
        # Round down to nearest 1 (stocks/options: lot size handled outside)
        return max(int(qty // 1), 0)

    def _apply_slippage(self, price: float, is_buy: bool) -> float:
        slip = self.config.slippage_pct
        return price * (1 + slip) if is_buy else price * (1 - slip)

    def _compute_pnl(self, trade: dict, exit_price: float) -> float:
        entry = trade["entry_price"]
        qty = trade["quantity"]
        gross = (exit_price - entry) * qty
        if trade.get("side") == "SELL":
            gross = -gross
        # Subtract commission (entry + exit)
        return gross - 2 * self.config.commission_per_trade

    def _update_trailing_state(self, trade: dict, row: pd.Series) -> None:
        """For MCX strategy: track highest close since entry + trailing stop."""
        meta = trade.get("meta") or {}
        close = float(row["close"]) if not pd.isna(row["close"]) else trade["entry_price"]
        prev_high = meta.get("high_since_entry", trade["entry_price"])
        new_high = max(prev_high, close)
        meta["high_since_entry"] = new_high

        atr = row.get("atr_20")
        if atr is not None and not pd.isna(atr) and float(atr) > 0:
            mult = self.strategy.params.get("trailing_stop_atr_mult", 2.0)
            new_trailing = new_high - mult * float(atr)
            prev_trailing = meta.get("trailing_stop_current", new_trailing)
            meta["trailing_stop_current"] = max(new_trailing, prev_trailing)
        trade["meta"] = meta

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
        if days <= 0:
            return 0.0
        if initial <= 0 or final <= 0:
            return 0.0
        cagr = (final / initial) ** (365.0 / days) - 1.0
        return cagr * 100.0
