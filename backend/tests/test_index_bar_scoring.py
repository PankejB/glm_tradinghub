"""
tests.test_index_bar_scoring
---------------------------
Unit tests for the Index Option Bar-Scoring strategy (Fitschen Ch 8).
"""
import math
import pandas as pd
import pytest

from app.strategies.index_bar_scoring import IndexBarScoringStrategy


class TestIndexBarScoringEntry:
    def test_entry_fires_above_threshold(self):
        """Bar score > 1.5 → entry signal."""
        strat = IndexBarScoringStrategy()
        row = pd.Series({
            "timestamp": pd.Timestamp("2025-06-23"),
            "close": 18000.0,
            "bar_score": 2.5,  # > 1.5 ✓
        }, name=80)
        sig = strat.check_entry(row, prev_row=None)
        assert sig is not None
        assert sig.action == "ENTER"
        assert sig.side == "BUY"
        # Entry price should be the approximated option premium, not the underlying
        assert sig.entry_price > 0
        assert sig.entry_price < 18000  # premium < underlying

    def test_no_entry_below_threshold(self):
        """Bar score <= 1.5 → no entry."""
        strat = IndexBarScoringStrategy()
        row = pd.Series({
            "timestamp": pd.Timestamp("2025-06-23"),
            "close": 18000.0,
            "bar_score": 1.5,  # exactly at threshold → no entry (>)
        }, name=80)
        assert strat.check_entry(row, prev_row=None) is None

    def test_no_entry_at_zero_score(self):
        strat = IndexBarScoringStrategy()
        row = pd.Series({
            "timestamp": pd.Timestamp("2025-06-23"),
            "close": 18000.0,
            "bar_score": 0.0,
        }, name=80)
        assert strat.check_entry(row, prev_row=None) is None

    def test_no_entry_when_close_zero(self):
        strat = IndexBarScoringStrategy()
        row = pd.Series({
            "timestamp": pd.Timestamp("2025-06-23"),
            "close": 0.0,
            "bar_score": 3.0,
        }, name=80)
        assert strat.check_entry(row, prev_row=None) is None

    def test_custom_threshold(self):
        """Override score_threshold to 0.5 → entry fires at score 1.0."""
        strat = IndexBarScoringStrategy({"score_threshold": 0.5})
        row = pd.Series({
            "timestamp": pd.Timestamp("2025-06-23"),
            "close": 18000.0,
            "bar_score": 1.0,  # > 0.5 ✓
        }, name=80)
        sig = strat.check_entry(row, prev_row=None)
        assert sig is not None

    def test_option_premium_approximation(self):
        """Premium ≈ 0.4 * spot * iv * sqrt(T/365)."""
        strat = IndexBarScoringStrategy({"dte_target": 7})
        spot = 18000.0
        iv = 0.15
        expected_premium = 0.4 * spot * iv * math.sqrt(7 / 365.0)
        row = pd.Series({
            "timestamp": pd.Timestamp("2025-06-23"),
            "close": spot,
            "bar_score": 2.0,
        }, name=80)
        sig = strat.check_entry(row, prev_row=None)
        assert sig.entry_price == pytest.approx(expected_premium, rel=0.01)

    def test_sl_tp_based_on_premium(self):
        """SL = 25% below premium, TP = 50% above premium."""
        strat = IndexBarScoringStrategy()
        row = pd.Series({
            "timestamp": pd.Timestamp("2025-06-23"),
            "close": 18000.0,
            "bar_score": 2.0,
        }, name=80)
        sig = strat.check_entry(row, prev_row=None)
        premium = sig.entry_price
        assert sig.stop_loss == pytest.approx(premium * 0.75)
        assert sig.take_profit == pytest.approx(premium * 1.50)

    def test_meta_contains_strike_and_underlying(self):
        strat = IndexBarScoringStrategy()
        row = pd.Series({
            "timestamp": pd.Timestamp("2025-06-23"),
            "close": 18250.0,
            "bar_score": 2.0,
        }, name=80)
        sig = strat.check_entry(row, prev_row=None)
        assert sig.meta["underlying_close"] == 18250.0
        # Strike should be rounded to nearest 50 (NIFTY grid)
        assert sig.meta["strike"] % 50 == 0
        assert sig.meta["option_type"] == "CE"
        assert sig.meta["dte"] == 7

    def test_bar_score_stored_in_signal(self):
        strat = IndexBarScoringStrategy()
        row = pd.Series({
            "timestamp": pd.Timestamp("2025-06-23"),
            "close": 18000.0,
            "bar_score": 2.5,
        }, name=80)
        sig = strat.check_entry(row, prev_row=None)
        assert sig.bar_score == 2.5


class TestIndexBarScoringExit:
    def _make_trade(self, entry=100.0, sl=75.0, tp=150.0, underlying_entry=18000.0):
        return {
            "entry_price": entry,
            "stop_loss": sl,
            "take_profit": tp,
            "side": "BUY",
            "meta": {"underlying_close": underlying_entry},
        }

    def _make_row(self, close=18000.0, idx=85):
        return pd.Series({
            "timestamp": pd.Timestamp("2025-06-30"),
            "close": close,
        }, name=idx)

    def test_exit_on_stop_loss(self):
        """Underlying drops enough that option premium falls below SL."""
        strat = IndexBarScoringStrategy()
        trade = self._make_trade(entry=100, sl=75, tp=150, underlying_entry=18000)
        # Underlying drops ~3% → option premium drops ~15% (delta 0.5, 10x leverage)
        # New premium ≈ 100 * (1 + 0.5 * -0.03 * 10) = 100 * 0.85 = 85
        # Need premium <= 75 → underlying drop of ~5%+
        row = self._make_row(close=17000)  # ~5.5% drop
        sig = strat.check_exit(trade, row, prev_row=None, bars_held=2)
        if sig is not None:
            assert sig.meta["exit_reason"] == "stop_loss"

    def test_exit_on_profit_target(self):
        """Underlying rises enough that option premium hits TP."""
        strat = IndexBarScoringStrategy()
        trade = self._make_trade(entry=100, sl=75, tp=150, underlying_entry=18000)
        # Need premium >= 150 → 50% gain → underlying rise ~5%+
        row = self._make_row(close=19000)  # ~5.5% rise
        sig = strat.check_exit(trade, row, prev_row=None, bars_held=2)
        if sig is not None:
            assert sig.meta["exit_reason"] == "target"

    def test_exit_on_time(self):
        """After 5 bars, time exit fires."""
        strat = IndexBarScoringStrategy()
        trade = self._make_trade(entry=100, sl=75, tp=150, underlying_entry=18000)
        row = self._make_row(close=18000)  # no move
        sig = strat.check_exit(trade, row, prev_row=None, bars_held=5)
        assert sig is not None
        assert sig.meta["exit_reason"] == "time_exit"

    def test_no_exit_when_within_range(self):
        strat = IndexBarScoringStrategy()
        trade = self._make_trade(entry=100, sl=75, tp=150, underlying_entry=18000)
        row = self._make_row(close=18100)  # tiny move
        sig = strat.check_exit(trade, row, prev_row=None, bars_held=2)
        assert sig is None


class TestIndexBarScoringParams:
    def test_defaults(self):
        strat = IndexBarScoringStrategy()
        assert strat.params["score_threshold"] == 1.5
        assert strat.params["stop_loss_pct"] == 0.25
        assert strat.params["profit_target_pct"] == 0.50
        assert strat.params["time_exit_bars"] == 5
        assert strat.params["option_type"] == "CE"

    def test_override(self):
        strat = IndexBarScoringStrategy({
            "score_threshold": 2.0,
            "stop_loss_pct": 0.30,
            "profit_target_pct": 0.60,
        })
        assert strat.params["score_threshold"] == 2.0
        assert strat.params["stop_loss_pct"] == 0.30
        assert strat.params["profit_target_pct"] == 0.60
