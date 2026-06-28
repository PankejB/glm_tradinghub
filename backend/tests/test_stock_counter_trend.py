"""
tests.test_stock_counter_trend
------------------------------
Unit tests for the Stock Counter-Trend strategy (Fitschen Ch 5/6).
"""
import pandas as pd
import pytest

from app.strategies.stock_counter_trend import StockCounterTrendStrategy
from app.strategies.base import Signal
from app.services.indicators import enrich_dataframe


class TestStockCounterTrendEntry:
    def test_no_entry_during_warmup(self, sample_ohlcv_30):
        """Strategy should NOT fire before indicators are warmed up."""
        strat = StockCounterTrendStrategy()
        df = strat.enrich(sample_ohlcv_30)
        # Bar 0-69 won't have sma_70 (need 70 bars), so check bar 5
        row = df.iloc[5]
        sig = strat.check_entry(row, prev_row=df.iloc[4])
        assert sig is None  # insufficient warmup

    def test_no_entry_when_all_conditions_fail(self, sample_ohlcv_100):
        """Bar where close > low_8 (no dip) → no entry."""
        strat = StockCounterTrendStrategy()
        df = strat.enrich(sample_ohlcv_100)
        # Find a bar where close > low_8 (not below 8-day low)
        for i in range(70, len(df)):
            row = df.iloc[i]
            if row["close"] > row["low_8"]:
                sig = strat.check_entry(row, prev_row=df.iloc[i-1])
                assert sig is None
                return
        # If we can't find one, the test data is unusual
        pytest.skip("Could not find a non-trigger bar in test data")

    def test_entry_fires_when_all_conditions_met(self):
        """Construct a synthetic bar where all 3 conditions are met."""
        strat = StockCounterTrendStrategy()
        # Build a row dict manually
        row = pd.Series({
            "timestamp": pd.Timestamp("2025-06-23"),
            "close": 1000.0,
            "low_8": 1010.0,          # close < low_8 ✓
            "sma_70": 990.0,           # close > sma_70 ✓
            "stddev_20": 35.0,
            "stddev_pct": 0.035,       # > 3% ✓
        }, name=80)
        sig = strat.check_entry(row, prev_row=None)
        assert sig is not None
        assert sig.action == "ENTER"
        assert sig.side == "BUY"
        assert sig.entry_price == 1000.0
        # SL = 1000 - 3 * 35 = 895
        assert sig.stop_loss == pytest.approx(895.0)
        # TP = 1000 + 300 = 1300
        assert sig.take_profit == pytest.approx(1300.0)

    def test_entry_rejected_when_stddev_below_threshold(self):
        """stddev_pct = 2% < 3% threshold → no entry."""
        strat = StockCounterTrendStrategy()
        row = pd.Series({
            "timestamp": pd.Timestamp("2025-06-23"),
            "close": 1000.0,
            "low_8": 1010.0,           # close < low_8 ✓
            "sma_70": 990.0,            # close > sma_70 ✓
            "stddev_20": 20.0,
            "stddev_pct": 0.02,         # < 3% ✗
        }, name=80)
        sig = strat.check_entry(row, prev_row=None)
        assert sig is None

    def test_entry_rejected_when_below_sma(self):
        """close < sma_70 → no entry (downtrend)."""
        strat = StockCounterTrendStrategy()
        row = pd.Series({
            "timestamp": pd.Timestamp("2025-06-23"),
            "close": 1000.0,
            "low_8": 1010.0,           # close < low_8 ✓
            "sma_70": 1050.0,           # close < sma_70 ✗
            "stddev_20": 35.0,
            "stddev_pct": 0.035,        # > 3% ✓
        }, name=80)
        sig = strat.check_entry(row, prev_row=None)
        assert sig is None

    def test_entry_rejected_when_above_low(self):
        """close > low_8 → no entry (no dip)."""
        strat = StockCounterTrendStrategy()
        row = pd.Series({
            "timestamp": pd.Timestamp("2025-06-23"),
            "close": 1000.0,
            "low_8": 990.0,            # close > low_8 ✗
            "sma_70": 990.0,            # close > sma_70 ✓
            "stddev_20": 35.0,
            "stddev_pct": 0.035,        # > 3% ✓
        }, name=80)
        sig = strat.check_entry(row, prev_row=None)
        assert sig is None

    def test_custom_stddev_threshold(self):
        """Override stddev_min_pct to 0.01 → entry fires at 2%."""
        strat = StockCounterTrendStrategy({"stddev_min_pct": 0.01})
        row = pd.Series({
            "timestamp": pd.Timestamp("2025-06-23"),
            "close": 1000.0,
            "low_8": 1010.0, "sma_70": 990.0,
            "stddev_20": 20.0, "stddev_pct": 0.02,
        }, name=80)
        sig = strat.check_entry(row, prev_row=None)
        assert sig is not None  # now passes with 1% threshold

    def test_meta_contains_indicators(self):
        strat = StockCounterTrendStrategy()
        row = pd.Series({
            "timestamp": pd.Timestamp("2025-06-23"),
            "close": 1000.0,
            "low_8": 1010.0, "sma_70": 990.0,
            "stddev_20": 35.0, "stddev_pct": 0.035,
        }, name=80)
        sig = strat.check_entry(row, prev_row=None)
        assert "low_8" in sig.meta
        assert "sma_70" in sig.meta
        assert "stddev_20" in sig.meta
        assert "stddev_pct" in sig.meta
        assert "stop_distance" in sig.meta


class TestStockCounterTrendExit:
    def _make_trade(self, entry=1000.0, sl=950.0, tp=1300.0):
        return {
            "entry_price": entry,
            "stop_loss": sl,
            "take_profit": tp,
            "side": "BUY",
            "meta": {},
        }

    def _make_row(self, close=1000.0, idx=80):
        return pd.Series({
            "timestamp": pd.Timestamp("2025-06-23"),
            "close": close,
        }, name=idx)

    def test_exit_on_stop_loss(self):
        strat = StockCounterTrendStrategy()
        trade = self._make_trade(entry=1000, sl=950, tp=1300)
        row = self._make_row(close=945)  # below SL
        sig = strat.check_exit(trade, row, prev_row=None, bars_held=2)
        assert sig is not None
        assert sig.action == "EXIT"
        assert sig.meta["exit_reason"] == "stop_loss"

    def test_exit_on_profit_target(self):
        strat = StockCounterTrendStrategy()
        trade = self._make_trade(entry=1000, sl=950, tp=1300)
        row = self._make_row(close=1310)  # above TP
        sig = strat.check_exit(trade, row, prev_row=None, bars_held=3)
        assert sig is not None
        assert sig.meta["exit_reason"] == "target"

    def test_exit_on_time(self):
        """After 8 bars, time exit fires."""
        strat = StockCounterTrendStrategy()
        trade = self._make_trade(entry=1000, sl=950, tp=1300)
        row = self._make_row(close=1050)  # between SL and TP
        sig = strat.check_exit(trade, row, prev_row=None, bars_held=8)
        assert sig is not None
        assert sig.meta["exit_reason"] == "time_exit"

    def test_no_exit_when_within_range(self):
        """Price between SL and TP, before time exit → hold."""
        strat = StockCounterTrendStrategy()
        trade = self._make_trade(entry=1000, sl=950, tp=1300)
        row = self._make_row(close=1050)
        sig = strat.check_exit(trade, row, prev_row=None, bars_held=3)
        assert sig is None

    def test_stop_loss_takes_priority_over_time(self):
        """If both SL hit AND time exit on same bar, SL wins (checked first)."""
        strat = StockCounterTrendStrategy()
        trade = self._make_trade(entry=1000, sl=950, tp=1300)
        row = self._make_row(close=945)  # below SL
        sig = strat.check_exit(trade, row, prev_row=None, bars_held=10)
        assert sig.meta["exit_reason"] == "stop_loss"

    def test_custom_time_exit_bars(self):
        """Override time_exit_bars to 3 → fires earlier."""
        strat = StockCounterTrendStrategy({"time_exit_bars": 3})
        trade = self._make_trade(entry=1000, sl=950, tp=1300)
        row = self._make_row(close=1050)
        sig = strat.check_exit(trade, row, prev_row=None, bars_held=3)
        assert sig is not None
        assert sig.meta["exit_reason"] == "time_exit"


class TestStockCounterTrendParams:
    def test_default_params(self):
        strat = StockCounterTrendStrategy()
        assert strat.params["lookback_low"] == 8
        assert strat.params["sma_trend"] == 70
        assert strat.params["stddev_min_pct"] == 0.03
        assert strat.params["profit_target"] == 300.0
        assert strat.params["time_exit_bars"] == 8

    def test_param_override(self):
        strat = StockCounterTrendStrategy({"profit_target": 500, "time_exit_bars": 5})
        assert strat.params["profit_target"] == 500
        assert strat.params["time_exit_bars"] == 5
        # Non-overridden params keep defaults
        assert strat.params["lookback_low"] == 8
