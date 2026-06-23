"""
app.strategies.stock_counter_trend
----------------------------------
Fitschen "Building Reliable Trading Systems" — Ch 5/6 — Counter-Trend Stock logic.

ENTRY (BUY):
    Close < 8-day Low        (price has dipped below recent low — oversold)
    AND Close > 70-day SMA   (long-term uptrend is intact)
    AND 20-day StdDev > 3% of price  (volatility is high — mean-reversion pays)

EXIT:
    Time-based: after 8 bars
    OR Profit Target of ₹300 hit (absolute price move)

STOP LOSS:
    3 × 20-day StdDev below entry price   (catastrophic stop)

POSITION SIZE (handled by Backtester via Fitschen money-management):
    qty = (equity × risk_per_trade_pct%) / stop_distance
"""
from __future__ import annotations

import pandas as pd

from app.strategies.base import StrategyBase, Signal


class StockCounterTrendStrategy(StrategyBase):
    name = "Stock Counter-Trend (Fitschen Ch 5/6)"
    strategy_type = "stock_counter_trend"
    book_reference = "Building Reliable Trading Systems, Ch 5/6 — Counter-Trend Stocks"
    default_params = {
        "lookback_low": 8,
        "sma_trend": 70,
        "stddev_window": 20,
        "stddev_min_pct": 0.03,
        "stop_loss_stddev_mult": 3,
        "profit_target": 300.0,    # ₹300 absolute
        "time_exit_bars": 8,
        "risk_per_trade_pct": 1.0,
    }

    def check_entry(self, row: pd.Series, prev_row: pd.Series | None) -> Signal | None:
        close = self.safe(row.get("close"))
        low_8 = self.safe(row.get("low_8"))
        sma_70 = self.safe(row.get("sma_70"))
        stddev_pct = self.safe(row.get("stddev_pct"))
        stddev_20 = self.safe(row.get("stddev_20"))

        # All indicators must be available (warmup)
        if not (low_8 and sma_70 and stddev_20):
            return None

        # Rule 1: Close below 8-day low (mean-reversion trigger)
        below_low = close < low_8
        # Rule 2: Long-term uptrend intact
        above_sma = close > sma_70
        # Rule 3: Volatility filter — StdDev > 3% of price
        vol_ok = stddev_pct > self.params["stddev_min_pct"]

        if not (below_low and above_sma and vol_ok):
            return None

        # Stop distance = 3 × 20-day StdDev (absolute)
        stop_distance = self.params["stop_loss_stddev_mult"] * stddev_20
        stop_loss = close - stop_distance
        take_profit = close + self.params["profit_target"]

        return Signal(
            timestamp=row["timestamp"],
            bar_index=int(row.name) if not pd.isna(row.name) else 0,
            action="ENTER",
            side="BUY",
            entry_price=close,
            stop_loss=stop_loss,
            take_profit=take_profit,
            meta={
                "low_8": low_8,
                "sma_70": sma_70,
                "stddev_20": stddev_20,
                "stddev_pct": stddev_pct,
                "stop_distance": stop_distance,
            },
        )

    def check_exit(
        self,
        open_trade: dict,
        row: pd.Series,
        prev_row: pd.Series | None,
        bars_held: int,
    ) -> Signal | None:
        close = self.safe(row.get("close"))
        entry = float(open_trade["entry_price"])
        sl = open_trade.get("stop_loss")
        tp = open_trade.get("take_profit")

        # 1) Stop loss hit
        if sl is not None and close <= sl:
            return Signal(
                timestamp=row["timestamp"], bar_index=int(row.name) if not pd.isna(row.name) else 0,
                action="EXIT", side="SELL", entry_price=close,
                meta={"exit_reason": "stop_loss"},
            )
        # 2) Profit target hit
        if tp is not None and close >= tp:
            return Signal(
                timestamp=row["timestamp"], bar_index=int(row.name) if not pd.isna(row.name) else 0,
                action="EXIT", side="SELL", entry_price=close,
                meta={"exit_reason": "target"},
            )
        # 3) Time exit
        if bars_held >= self.params["time_exit_bars"]:
            return Signal(
                timestamp=row["timestamp"], bar_index=int(row.name) if not pd.isna(row.name) else 0,
                action="EXIT", side="SELL", entry_price=close,
                meta={"exit_reason": "time_exit"},
            )
        return None
