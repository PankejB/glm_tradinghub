"""
app.strategies.base
-------------------
Abstract base class shared by all Fitschen strategies.
Defines the contract: enrich() + generate_signals() + manage_open_position().
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from app.services.indicators import enrich_dataframe


@dataclass
class Signal:
    """One signal produced by a strategy at a given bar."""
    timestamp: datetime
    bar_index: int
    action: str            # 'ENTER' | 'EXIT' | 'HOLD'
    side: str | None       # 'BUY' | 'SELL'  (None for HOLD)
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    # For Index Bar-Scoring
    bar_score: float | None = None
    # Free-form metadata (indicator values, etc.)
    meta: dict[str, Any] = field(default_factory=dict)


class StrategyBase(ABC):
    """
    Base class. Each concrete strategy implements:
      - enrich(df) -> df with strategy-specific indicator columns
      - check_entry(row, prev_row) -> Signal | None
      - check_exit(open_trade, row, prev_row, bars_held) -> Signal | None
    """

    name: str = "base"
    strategy_type: str = "base"
    book_reference: str = ""
    default_params: dict = {}

    def __init__(self, parameters: dict | None = None) -> None:
        # Merge defaults with overrides
        self.params: dict = {**self.default_params, **(parameters or {})}

    # ----------------------------------------------------------- enrich
    def enrich(self, df: pd.DataFrame) -> pd.DataFrame:
        """Attach indicators needed by this strategy. Default uses the shared
        enrich_dataframe helper."""
        return enrich_dataframe(df, self.params)

    # ----------------------------------------------------- signal API
    @abstractmethod
    def check_entry(self, row: pd.Series, prev_row: pd.Series | None) -> Signal | None:
        """Return a Signal(action='ENTER') if entry conditions are met."""

    @abstractmethod
    def check_exit(
        self,
        open_trade: dict,
        row: pd.Series,
        prev_row: pd.Series | None,
        bars_held: int,
    ) -> Signal | None:
        """Return a Signal(action='EXIT') if exit conditions are met for the
        open trade. Returns None to hold."""

    # --------------------------------------------------------- helper
    @staticmethod
    def safe(value: Any) -> float:
        """NaN-aware accessor. Returns 0.0 for NaN/None."""
        if value is None:
            return 0.0
        try:
            f = float(value)
            return 0.0 if pd.isna(f) else f
        except (TypeError, ValueError):
            return 0.0

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} params={self.params}>"
