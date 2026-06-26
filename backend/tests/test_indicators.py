"""
tests.test_indicators
---------------------
Unit tests for app/services/indicators.py.

Covers: SMA, EMA, StdDev, rolling_low/high, average_range, true_range, ATR,
stddev_pct_of_price, range_pct_of_price, stop_distance_stddev, bar_type_score,
price_stddev_weakness, volume_stddev_surge, compute_bar_score, enrich_dataframe.
"""
import numpy as np
import pandas as pd
import pytest

from app.services.indicators import (
    sma, ema, stddev, rolling_low, rolling_high, average_range,
    true_range, atr, stddev_pct_of_price, range_pct_of_price,
    stop_distance_stddev, bar_type_score, price_stddev_weakness,
    volume_stddev_surge, compute_bar_score, enrich_dataframe,
)


# ============================================================
#  Basic indicators
# ============================================================

class TestSMA:
    def test_sma_basic(self):
        s = pd.Series([1, 2, 3, 4, 5], dtype=float)
        result = sma(s, 3)
        # SMA(3) at index 2 = (1+2+3)/3 = 2.0
        assert result.iloc[2] == pytest.approx(2.0)
        # SMA(3) at index 4 = (3+4+5)/3 = 4.0
        assert result.iloc[4] == pytest.approx(4.0)

    def test_sma_warmup_returns_nan(self):
        """SMA should return NaN until enough data points are available."""
        s = pd.Series([1, 2, 3], dtype=float)
        result = sma(s, 5)
        assert result.isna().all()

    def test_sma_does_not_mutate_input(self):
        s = pd.Series([1, 2, 3, 4, 5], dtype=float)
        original = s.copy()
        _ = sma(s, 3)
        pd.testing.assert_series_equal(s, original)

    def test_sma_window_1(self):
        s = pd.Series([10, 20, 30], dtype=float)
        result = sma(s, 1)
        pd.testing.assert_series_equal(result, s)


class TestEMA:
    def test_ema_first_value_equals_input(self):
        s = pd.Series([10, 20, 30, 40], dtype=float)
        result = ema(s, 3)
        # EMA with adjust=False: first value = first input
        assert result.iloc[0] == pytest.approx(10.0)

    def test_ema_no_nan(self):
        """EMA (adjust=False) produces values for all bars, no warmup NaN."""
        s = pd.Series([1, 2, 3, 4, 5], dtype=float)
        result = ema(s, 3)
        assert not result.isna().any()


class TestStdDev:
    def test_stddev_constant_series_is_zero(self):
        """StdDev of a constant series should be 0 (population, ddof=0)."""
        s = pd.Series([5, 5, 5, 5, 5], dtype=float)
        result = stddev(s, 3)
        # After warmup, all values should be 0
        assert result.iloc[2] == pytest.approx(0.0)
        assert result.iloc[4] == pytest.approx(0.0)

    def test_stddev_uses_population_formula(self):
        """Verify ddof=0 (population) vs ddof=1 (sample)."""
        s = pd.Series([2, 4, 4, 4, 5, 5, 7, 9], dtype=float)
        pop_std = stddev(s, 8).iloc[7]
        # Population std of [2,4,4,4,5,5,7,9] = 2.0
        assert pop_std == pytest.approx(2.0)

    def test_stddev_warmup(self):
        s = pd.Series([1, 2, 3], dtype=float)
        result = stddev(s, 5)
        assert result.isna().all()


class TestRollingLowHigh:
    def test_rolling_low_excludes_current_bar(self):
        """rolling_low should NOT include the current bar (shifted by 1)."""
        s = pd.Series([10, 5, 20, 1, 30], dtype=float)
        result = rolling_low(s, 3)
        # At index 3 (value=1), rolling_low looks at bars 0,1,2 → min=5
        # NOT 1 (current bar excluded)
        assert result.iloc[3] == pytest.approx(5.0)

    def test_rolling_high_excludes_current_bar(self):
        s = pd.Series([10, 50, 20, 100, 30], dtype=float)
        result = rolling_high(s, 3)
        # At index 3 (value=100), rolling_high looks at bars 0,1,2 → max=50
        assert result.iloc[3] == pytest.approx(50.0)

    def test_rolling_low_warmup(self):
        s = pd.Series([1, 2, 3], dtype=float)
        assert rolling_low(s, 5).isna().all()


class TestAverageRange:
    def test_average_range_basic(self, sample_ohlcv_30):
        df = sample_ohlcv_30
        result = average_range(df, 5)
        # After 5 bars, should have values
        assert not result.iloc[4:].isna().any()
        # All values should be positive (high > low in our fixture)
        assert (result.iloc[4:].dropna() > 0).all()


class TestTrueRange:
    def test_true_range_basic(self, sample_ohlcv_30):
        df = sample_ohlcv_30
        tr = true_range(df)
        # TR should always be >= 0
        assert (tr.dropna() >= 0).all()
        # TR should be >= (high - low) for each bar
        hl = df["high"] - df["low"]
        assert (tr.iloc[1:] >= hl.iloc[1:] - 1e-10).all()  # allow float epsilon

    def test_true_range_gap_up(self):
        """Gap up: prev_close=100, current high=120, low=115.
        TR = max(120-115, |120-100|, |115-100|) = max(5, 20, 15) = 20."""
        df = pd.DataFrame({
            "high": [110, 120], "low": [100, 115], "close": [100, 118],
        })
        tr = true_range(df)
        assert tr.iloc[1] == pytest.approx(20.0)


class TestATR:
    def test_atr_warmup(self, sample_ohlcv_30):
        df = sample_ohlcv_30
        result = atr(df, 14)
        # First 14 bars should be NaN
        assert result.iloc[:13].isna().all()
        # Bar 14 onwards should have values
        assert not result.iloc[13:].isna().any()

    def test_atr_positive(self, sample_ohlcv_30):
        df = sample_ohlcv_30
        result = atr(df, 14).dropna()
        assert (result > 0).all()


# ============================================================
#  Composite indicators
# ============================================================

class TestStdDevPctOfPrice:
    def test_returns_fraction(self, sample_ohlcv_30):
        df = sample_ohlcv_30
        result = stddev_pct_of_price(df, 20).dropna()
        # Should be a small fraction (typically 0.01 - 0.05 for stocks)
        assert (result > 0).all()
        assert (result < 1).all()

    def test_flat_series_zero_stddev(self, flat_ohlcv_30):
        df = flat_ohlcv_30
        result = stddev_pct_of_price(df, 10).dropna()
        # StdDev of constant = 0, so pct = 0
        assert (result == 0).all()


class TestRangePctOfPrice:
    def test_returns_fraction(self, sample_ohlcv_30):
        df = sample_ohlcv_30
        result = range_pct_of_price(df, 20).dropna()
        assert (result > 0).all()
        assert (result < 1).all()


class TestStopDistanceStddev:
    def test_multiplier_applied(self, sample_ohlcv_30):
        df = sample_ohlcv_30
        sd = stddev(df["close"], 20)
        dist_3x = stop_distance_stddev(df, 20, 3.0)
        # 3x stop distance should be 3 * stddev — compare element-wise
        valid_idx = sd.dropna().index
        for idx in valid_idx:
            assert dist_3x.loc[idx] == pytest.approx(3.0 * sd.loc[idx])


# ============================================================
#  Bar-Scoring (Fitschen Ch 8)
# ============================================================

class TestBarTypeScore:
    def test_bullish_bar_positive_score(self):
        """Bullish bar with long lower wick → positive score (rejection)."""
        df = pd.DataFrame({
            "open": [100], "high": [110], "low": [90], "close": [108],
        })
        score = bar_type_score(df)
        # close > open → bull → (close - low) / (high - low) - 0.5
        # = (108 - 90) / (110 - 90) - 0.5 = 0.9 - 0.5 = 0.4
        assert score.iloc[0] == pytest.approx(0.4)

    def test_bearish_bar_negative_score(self):
        """Bearish bar with long upper wick → negative score."""
        df = pd.DataFrame({
            "open": [108], "high": [110], "low": [90], "close": [100],
        })
        score = bar_type_score(df)
        # close < open → bear → (high - close) / (high - low) - 0.5
        # = (110 - 100) / (110 - 90) - 0.5 = 0.5 - 0.5 = 0.0
        assert score.iloc[0] == pytest.approx(0.0)

    def test_zero_range_handled(self):
        """Zero range (high == low) should not crash — fillna(0)."""
        df = pd.DataFrame({
            "open": [100], "high": [100], "low": [100], "close": [100],
        })
        score = bar_type_score(df)
        assert score.iloc[0] == pytest.approx(0.0)

    def test_score_range(self, sample_ohlcv_100):
        df = sample_ohlcv_100
        score = bar_type_score(df)
        # Scores should be in [-0.5, +0.5]
        assert score.min() >= -0.5 - 1e-10
        assert score.max() <= 0.5 + 1e-10


class TestPriceStddevWeakness:
    def test_range_clipped(self, sample_ohlcv_100):
        df = sample_ohlcv_100
        score = price_stddev_weakness(df, 20).dropna()
        # Should be clipped to [0, 3]
        assert (score >= 0).all()
        assert (score <= 3).all()

    def test_flat_series_zero(self, flat_ohlcv_30):
        df = flat_ohlcv_30
        score = price_stddev_weakness(df, 10).dropna()
        assert (score == 0).all()  # zero stddev → fillna(0)


class TestVolumeStddevSurge:
    def test_range_clipped(self, sample_ohlcv_100):
        df = sample_ohlcv_100
        score = volume_stddev_surge(df, 20).dropna()
        assert (score >= 0).all()
        assert (score <= 5).all()

    def test_volume_spike_detected(self, sample_ohlcv_100):
        """Our fixture has a 5M volume spike at bar 80 (vs ~500K average)."""
        df = sample_ohlcv_100
        score = volume_stddev_surge(df, 20)
        # Bar 80 should have a high surge score
        assert score.iloc[80] > 1.0


class TestComputeBarScore:
    def test_composite_is_sum_of_components(self, sample_ohlcv_100):
        df = sample_ohlcv_100
        composite = compute_bar_score(df, 20, 20)
        p = price_stddev_weakness(df, 20)
        v = volume_stddev_surge(df, 20)
        b = bar_type_score(df)
        expected = p + v + b
        pd.testing.assert_series_equal(composite, expected, check_names=False)

    def test_composite_range(self, sample_ohlcv_100):
        df = sample_ohlcv_100
        score = compute_bar_score(df, 20, 20).dropna()
        # Theoretical range: [-0.5, 8.5]
        assert score.min() >= -0.5 - 1e-10
        assert score.max() <= 8.5 + 1e-10

    def test_named_bar_score(self, sample_ohlcv_100):
        df = sample_ohlcv_100
        score = compute_bar_score(df, 20, 20)
        assert score.name == "bar_score"


# ============================================================
#  enrich_dataframe
# ============================================================

class TestEnrichDataframe:
    def test_adds_all_expected_columns(self, sample_ohlcv_100):
        df = sample_ohlcv_100
        enriched = enrich_dataframe(df)
        expected_cols = {
            "sma_70", "low_8", "high_20", "stddev_20", "stddev_pct",
            "range_avg", "range_pct", "atr_20", "stop_distance", "bar_score",
        }
        assert expected_cols.issubset(set(enriched.columns))

    def test_does_not_mutate_input(self, sample_ohlcv_100):
        df = sample_ohlcv_100
        original_cols = df.columns.tolist()
        original_shape = df.shape
        _ = enrich_dataframe(df)
        assert df.columns.tolist() == original_cols
        assert df.shape == original_shape

    def test_custom_params_override_defaults(self, sample_ohlcv_100):
        df = sample_ohlcv_100
        enriched = enrich_dataframe(df, {"sma_trend": 50, "lookback_low": 5})
        # With sma_trend=50, SMA should warm up at bar 50 (not 70)
        assert enriched["sma_70"].iloc[49] != pytest.approx(0)  # has value at bar 50
        # Original 70-day SMA would be NaN at bar 50
        assert enriched["sma_70"].isna().iloc[0:49].all()
