"""
app.strategies.mcx_trend_following
----------------------------------
Fitschen "Building Reliable Trading Systems" — Ch 5/6 — Trend-Following Commodity logic.

ENTRY (BUY):
    Close > 20-day High     (breakout above recent high)
    AND Close > 70-day SMA  (long-term uptrend filter)
    AND Average Range > 0.5% of price  (volatility filter — needs movement)

EXIT:
    Trailing Stop based on 2x ATR from highest close since entry
    OR 3x StdDev catastrophic stop (held fixed from entry)

POSITION SIZE:
    qty = (equity × 1%) / catastrophic_stop_distance
"""
from __future__ import annotations

import pandas as pd

from app.strategies.base import StrategyBase, Signal


class McxTrendFollowingStrategy(StrategyBase):
    name = "MCX Trend-Following (Fitschen Ch 5/6)"
    strategy_type = "mcx_trend_following"
    book_reference = "Building Reliable Trading Systems, Ch 5/6 — Trend-Following Commodity"
    default_params = {
        "lookback_high": 20,
        "sma_trend": 70,
        "range_window": 20,
        "range_min_pct": 0.005,
        "stddev_window": 20,
        "stop_loss_stddev_mult": 3,
        "trailing_stop_atr_mult": 2.0,
        "risk_per_trade_pct": 1.0,
    }

    def check_entry(self, row: pd.Series, prev_row: pd.Series | None) -> Signal | None:
        close = self.safe(row.get("close"))
        high_20 = self.safe(row.get("high_20"))
        sma_70 = self.safe(row.get("sma_70"))
        range_pct = self.safe(row.get("range_pct"))
        stddev_20 = self.safe(row.get("stddev_20"))
        atr_20 = self.safe(row.get("atr_20"))

        if not (high_20 and sma_70 and stddev_20):
            return None

        # Rule 1: breakout above 20-day high
        breakout = close > high_20
        # Rule 2: trend filter
        above_sma = close > sma_70
        # Rule 3: range filter — avg range > 0.5% of price
        range_ok = range_pct > self.params["range_min_pct"]

        if not (breakout and above_sma and range_ok):
            return None

        # Catastrophic stop = 3x StdDev below entry
        stop_distance = self.params["stop_loss_stddev_mult"] * stddev_20
        stop_loss = close - stop_distance
        # Trailing stop initial = 2x ATR below entry
        trailing_init = close - self.params["trailing_stop_atr_mult"] * atr_20 if atr_20 else None

        return Signal(
            timestamp=row["timestamp"],
            bar_index=int(row.name) if not pd.isna(row.name) else 0,
            action="ENTER",
            side="BUY",
            entry_price=close,
            stop_loss=stop_loss,
            take_profit=None,   # trend-following: no fixed TP, let trailing run
            meta={
                "high_20": high_20,
                "sma_70": sma_70,
                "range_pct": range_pct,
                "stddev_20": stddev_20,
                "atr_20": atr_20,
                "stop_distance": stop_distance,
                "trailing_stop_initial": trailing_init,
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
        high_since_entry = float(open_trade.get("meta", {}).get("high_since_entry", open_trade["entry_price"]))
        atr_20 = self.safe(row.get("atr_20"))
        sl = open_trade.get("stop_loss")

        # 1) Catastrophic stop (fixed from entry)
        if sl is not None and close <= sl:
            return Signal(
                timestamp=row["timestamp"], bar_index=int(row.name) if not pd.isna(row.name) else 0,
                action="EXIT", side="SELL", entry_price=close,
                meta={"exit_reason": "catastrophic_stop"},
            )

        # 2) Trailing stop: 2x ATR below highest close since entry
        if atr_20:
            new_high = max(high_since_entry, close)
            trailing_stop = new_high - self.params["trailing_stop_atr_mult"] * atr_20
            # Trailing only moves UP (never expands risk)
            prev_trailing = open_trade.get("meta", {}).get("trailing_stop_current", trailing_stop)
            trailing_stop = max(trailing_stop, prev_trailing)
            # Note: the Backtester persists trailing_stop_current back into the trade dict
            if close <= trailing_stop and bars_held > 0:
                return Signal(
                    timestamp=row["timestamp"],
                    bar_index=int(row.name) if not pd.isna(row.name) else 0,
                    action="EXIT", side="SELL", entry_price=close,
                    meta={
                        "exit_reason": "trailing_stop",
                        "trailing_stop": trailing_stop,
                        "high_since_entry": new_high,
                    },
                )

        return None
