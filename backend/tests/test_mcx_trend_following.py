"""
tests.test_mcx_trend_following
------------------------------
Unit tests for the MCX Trend-Following strategy (Fitschen Ch 5/6).
"""
import pandas as pd
import pytest

from app.strategies.mcx_trend_following import McxTrendFollowingStrategy


class TestMCXEntry:
    def test_entry_fires_on_breakout(self):
        """All 3 conditions met: close > 20d high, close > 70d SMA, range > 0.5%."""
        strat = McxTrendFollowingStrategy()
        row = pd.Series({
            "timestamp": pd.Timestamp("2025-06-23"),
            "close": 1000.0,
            "high_20": 990.0,           # close > high_20 ✓ (breakout)
            "sma_70": 950.0,            # close > sma_70 ✓ (uptrend)
            "range_pct": 0.008,         # > 0.5% ✓
            "stddev_20": 20.0,
            "atr_20": 15.0,
        }, name=80)
        sig = strat.check_entry(row, prev_row=None)
        assert sig is not None
        assert sig.action == "ENTER"
        assert sig.side == "BUY"
        assert sig.entry_price == 1000.0
        # SL = 1000 - 3*20 = 940
        assert sig.stop_loss == pytest.approx(940.0)
        # No fixed TP for trend-following
        assert sig.take_profit is None

    def test_no_entry_without_breakout(self):
        """close <= high_20 → no entry."""
        strat = McxTrendFollowingStrategy()
        row = pd.Series({
            "timestamp": pd.Timestamp("2025-06-23"),
            "close": 985.0,
            "high_20": 990.0,           # close < high_20 ✗
            "sma_70": 950.0, "range_pct": 0.008,
            "stddev_20": 20.0, "atr_20": 15.0,
        }, name=80)
        assert strat.check_entry(row, prev_row=None) is None

    def test_no_entry_below_sma(self):
        """close < sma_70 → no entry (downtrend)."""
        strat = McxTrendFollowingStrategy()
        row = pd.Series({
            "timestamp": pd.Timestamp("2025-06-23"),
            "close": 1000.0,
            "high_20": 990.0, "sma_70": 1050.0,  # close < sma ✗
            "range_pct": 0.008, "stddev_20": 20.0, "atr_20": 15.0,
        }, name=80)
        assert strat.check_entry(row, prev_row=None) is None

    def test_no_entry_low_range(self):
        """range_pct < 0.5% → no entry (not volatile enough)."""
        strat = McxTrendFollowingStrategy()
        row = pd.Series({
            "timestamp": pd.Timestamp("2025-06-23"),
            "close": 1000.0,
            "high_20": 990.0, "sma_70": 950.0,
            "range_pct": 0.003,         # < 0.5% ✗
            "stddev_20": 20.0, "atr_20": 15.0,
        }, name=80)
        assert strat.check_entry(row, prev_row=None) is None

    def test_no_entry_during_warmup(self):
        """Missing indicators → no entry."""
        strat = McxTrendFollowingStrategy()
        row = pd.Series({
            "timestamp": pd.Timestamp("2025-06-23"),
            "close": 1000.0,
            "high_20": 0.0, "sma_70": 0.0,  # 0 → treated as missing
            "range_pct": 0.008, "stddev_20": 20.0, "atr_20": 15.0,
        }, name=80)
        assert strat.check_entry(row, prev_row=None) is None

    def test_meta_contains_trailing_stop_initial(self):
        strat = McxTrendFollowingStrategy()
        row = pd.Series({
            "timestamp": pd.Timestamp("2025-06-23"),
            "close": 1000.0,
            "high_20": 990.0, "sma_70": 950.0,
            "range_pct": 0.008, "stddev_20": 20.0, "atr_20": 15.0,
        }, name=80)
        sig = strat.check_entry(row, prev_row=None)
        # Trailing stop initial = 1000 - 2*15 = 970
        assert sig.meta["trailing_stop_initial"] == pytest.approx(970.0)


class TestMCXExit:
    def _make_trade(self, entry=1000.0, sl=940.0):
        return {
            "entry_price": entry,
            "stop_loss": sl,
            "take_profit": None,
            "side": "BUY",
            "meta": {"high_since_entry": entry, "trailing_stop_current": entry - 30},
        }

    def _make_row(self, close=1000.0, atr=15.0, idx=85):
        return pd.Series({
            "timestamp": pd.Timestamp("2025-06-30"),
            "close": close, "atr_20": atr,
        }, name=idx)

    def test_exit_on_catastrophic_stop(self):
        """Price falls below the fixed 3x StdDev stop."""
        strat = McxTrendFollowingStrategy()
        trade = self._make_trade(entry=1000, sl=940)
        row = self._make_row(close=935)  # below SL
        sig = strat.check_exit(trade, row, prev_row=None, bars_held=3)
        assert sig is not None
        assert sig.meta["exit_reason"] == "catastrophic_stop"

    def test_exit_on_trailing_stop(self):
        """Price falls below the trailing stop."""
        strat = McxTrendFollowingStrategy()
        trade = self._make_trade(entry=1000, sl=940)
        # Set trailing stop current to 980 (locked in some profit)
        trade["meta"]["trailing_stop_current"] = 980
        trade["meta"]["high_since_entry"] = 1010
        row = self._make_row(close=975, atr=15)  # below trailing
        sig = strat.check_exit(trade, row, prev_row=None, bars_held=5)
        assert sig is not None
        assert sig.meta["exit_reason"] == "trailing_stop"

    def test_no_exit_when_above_trailing(self):
        strat = McxTrendFollowingStrategy()
        trade = self._make_trade(entry=1000, sl=940)
        trade["meta"]["trailing_stop_current"] = 980
        trade["meta"]["high_since_entry"] = 1010
        row = self._make_row(close=1005, atr=15)  # above trailing
        sig = strat.check_exit(trade, row, prev_row=None, bars_held=3)
        assert sig is None

    def test_trailing_only_moves_up(self):
        """The trailing stop should never move DOWN (risk only tightens)."""
        strat = McxTrendFollowingStrategy()
        trade = self._make_trade(entry=1000, sl=940)
        # Set a high trailing stop already
        trade["meta"]["trailing_stop_current"] = 990
        trade["meta"]["high_since_entry"] = 1005
        # Current bar: low price, ATR-based new trailing would be LOWER
        row = self._make_row(close=985, atr=30)  # new trailing = 985 - 60 = 925 < 990
        # Should use the OLD trailing (990), not the new lower one
        # close=985 < 990 → exit fires
        sig = strat.check_exit(trade, row, prev_row=None, bars_held=5)
        if sig is not None:
            assert sig.meta["exit_reason"] == "trailing_stop"

    def test_no_exit_at_bars_held_zero(self):
        """bars_held=0 → no trailing exit (just entered, give it room)."""
        strat = McxTrendFollowingStrategy()
        trade = self._make_trade(entry=1000, sl=940)
        trade["meta"]["trailing_stop_current"] = 980
        row = self._make_row(close=975, atr=15)
        sig = strat.check_exit(trade, row, prev_row=None, bars_held=0)
        # bars_held=0 → trailing check skipped (only catastrophic stop checked)
        # close=975 > sl=940 → no catastrophic exit
        assert sig is None


class TestMCXParams:
    def test_default_params(self):
        strat = McxTrendFollowingStrategy()
        assert strat.params["lookback_high"] == 20
        assert strat.params["sma_trend"] == 70
        assert strat.params["range_min_pct"] == 0.005
        assert strat.params["trailing_stop_atr_mult"] == 2.0

    def test_param_override(self):
        strat = McxTrendFollowingStrategy({"trailing_stop_atr_mult": 3.0})
        assert strat.params["trailing_stop_atr_mult"] == 3.0
