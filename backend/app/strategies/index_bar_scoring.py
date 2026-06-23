"""
app.strategies.index_bar_scoring
--------------------------------
Fitschen "Building Reliable Trading Systems" — Ch 8 — Bar-Scoring.

ENTRY (BUY ATM Call):
    Bar Score > 1.5   (Top Bin logic — strongest score bucket)

Bar Score is a composite of three sub-scores (see app.services.indicators.compute_bar_score):
    price_stddev_weakness ∈ [0, 3]    — close sitting at/below lower Bollinger-style band
    volume_stddev_surge   ∈ [0, 5]    — volume spike vs its own stddev
    bar_type_score        ∈ [-0.5, +0.5] — bullish rejection wick

Composite ∈ [-0.5, +8.5]; threshold 1.5 isolates the upper "Top Bin".

Exit:
    25% SL on option premium
    50% TP on option premium
    Time exit after 5 bars

Note: this strategy operates on the underlying index OHLCV (e.g. NIFTY 50).
The actual option price is approximated at entry using a simplified
premium = max(intrinsic, 0) + time_value_factor. For real trading, the
DhanService will fetch the live option chain to select the ATM strike.
"""
from __future__ import annotations

import math
import pandas as pd

from app.strategies.base import StrategyBase, Signal


class IndexBarScoringStrategy(StrategyBase):
    name = "Index Option Bar-Scoring (Fitschen Ch 8)"
    strategy_type = "index_bar_scoring"
    book_reference = "Building Reliable Trading Systems, Ch 8 — Bar-Scoring"
    default_params = {
        "score_threshold": 1.5,
        "price_stddev_window": 20,
        "volume_stddev_window": 20,
        "bar_lookback": 1,
        "strike_offset": 0,
        "option_type": "CE",
        "dte_target": 7,
        "stop_loss_pct": 0.25,
        "profit_target_pct": 0.50,
        "time_exit_bars": 5,
        "risk_per_trade_pct": 1.0,
    }

    def _approx_atm_option_premium(self, spot: float, iv_pct: float = 0.15) -> float:
        """
        Rough ATM call premium estimate for sizing purposes.
        Uses a simplified BSM: ATM call ≈ 0.4 * spot * iv * sqrt(T/365)

        iv_pct: annualised IV as a fraction (0.15 = 15%)
        T: target DTE days
        """
        T = self.params["dte_target"]
        return 0.4 * spot * iv_pct * math.sqrt(T / 365.0)

    def check_entry(self, row: pd.Series, prev_row: pd.Series | None) -> Signal | None:
        score = self.safe(row.get("bar_score"))
        close = self.safe(row.get("close"))

        if score == 0.0 or close == 0.0:
            return None

        if score <= self.params["score_threshold"]:
            return None

        # Approximate premium + SL/TP on the option (not the underlying)
        premium = self._approx_atm_option_premium(close)
        sl = premium * (1 - self.params["stop_loss_pct"])
        tp = premium * (1 + self.params["profit_target_pct"])

        return Signal(
            timestamp=row["timestamp"],
            bar_index=int(row.name) if not pd.isna(row.name) else 0,
            action="ENTER",
            side="BUY",
            entry_price=premium,        # NOTE: option premium, not underlying
            stop_loss=sl,
            take_profit=tp,
            bar_score=score,
            meta={
                "underlying_close": close,
                "strike": round(close / 50) * 50,   # rough NIFTY strike grid (50-pt)
                "option_type": self.params["option_type"],
                "dte": self.params["dte_target"],
                "score_components": {
                    "bar_score": score,
                },
            },
        )

    def check_exit(
        self,
        open_trade: dict,
        row: pd.Series,
        prev_row: pd.Series | None,
        bars_held: int,
    ) -> Signal | None:
        # For backtest we re-evaluate premium off the underlying's move.
        entry = float(open_trade["entry_price"])
        underlying_entry = float(open_trade.get("meta", {}).get("underlying_close", entry))
        underlying_now = self.safe(row.get("close"))

        # Approx premium scaling: if underlying moves x%, option moves with delta ≈ 0.5
        delta = 0.5
        move_pct = (underlying_now - underlying_entry) / underlying_entry if underlying_entry else 0.0
        approx_premium_now = entry * (1 + delta * move_pct * 10)  # leverage ~10x for ATM

        sl = open_trade.get("stop_loss")
        tp = open_trade.get("take_profit")

        if sl is not None and approx_premium_now <= sl:
            return Signal(
                timestamp=row["timestamp"], bar_index=int(row.name) if not pd.isna(row.name) else 0,
                action="EXIT", side="SELL", entry_price=approx_premium_now,
                meta={"exit_reason": "stop_loss", "underlying_close": underlying_now},
            )
        if tp is not None and approx_premium_now >= tp:
            return Signal(
                timestamp=row["timestamp"], bar_index=int(row.name) if not pd.isna(row.name) else 0,
                action="EXIT", side="SELL", entry_price=approx_premium_now,
                meta={"exit_reason": "target", "underlying_close": underlying_now},
            )
        if bars_held >= self.params["time_exit_bars"]:
            return Signal(
                timestamp=row["timestamp"], bar_index=int(row.name) if not pd.isna(row.name) else 0,
                action="EXIT", side="SELL", entry_price=approx_premium_now,
                meta={"exit_reason": "time_exit", "underlying_close": underlying_now},
            )
        return None
