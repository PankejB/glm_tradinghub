"""
app.services.indicators
-----------------------
Vectorised indicator calculations used by all three Fitschen strategies.

All functions return pandas Series indexed like the input DataFrame.
They do NOT mutate the input.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# =============================================================
#  Basic indicators
# =============================================================

def sma(series: pd.Series, window: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False).mean()


def stddev(series: pd.Series, window: int) -> pd.Series:
    """Population standard deviation (ddof=0) — matches Fitschen's text."""
    return series.rolling(window=window, min_periods=window).std(ddof=0)


def rolling_low(series: pd.Series, window: int) -> pd.Series:
    """Rolling low (excludes current bar by shifting)."""
    return series.shift(1).rolling(window=window, min_periods=window).min()


def rolling_high(series: pd.Series, window: int) -> pd.Series:
    """Rolling high (excludes current bar by shifting)."""
    return series.shift(1).rolling(window=window, min_periods=window).max()


def average_range(df: pd.DataFrame, window: int) -> pd.Series:
    """Average (high - low) range over `window` bars."""
    rng = df["high"] - df["low"]
    return rng.rolling(window=window, min_periods=window).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    """True Range = max(H-L, |H-prevC|, |L-prevC|)."""
    prev_close = df["close"].shift(1)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def atr(df: pd.DataFrame, window: int) -> pd.Series:
    """Average True Range (Wilder-style simple mean of TR)."""
    return true_range(df).rolling(window=window, min_periods=window).mean()


# =============================================================
#  Composite / strategy-specific
# =============================================================

def stddev_pct_of_price(df: pd.DataFrame, window: int) -> pd.Series:
    """StdDev expressed as a fraction of the close price.
    Used by the volatility filter: `stddev > 3% of price`."""
    sd = stddev(df["close"], window)
    return sd / df["close"]


def range_pct_of_price(df: pd.DataFrame, window: int) -> pd.Series:
    """Average range as a fraction of close price.
    Used by MCX filter: `avg range > 0.5% of price`."""
    ar = average_range(df, window)
    return ar / df["close"]


def stop_distance_stddev(df: pd.DataFrame, window: int, mult: float) -> pd.Series:
    """Absolute stop distance = mult * stddev(close, window).
    Used by Stock/MCX catastrophic stop = 3 * 20-day StdDev."""
    return mult * stddev(df["close"], window)


# =============================================================
#  Bar-Scoring (Fitschen Ch 8)
# =============================================================

def bar_type_score(df: pd.DataFrame) -> pd.Series:
    """
    Bar Type score: rewards rejection tails (long wicks on the losing side).

    For a bullish bar (close > open):
      score = (close - low) / (high - low) - 0.5
    For a bearish bar:
      score = (high - close) / (high - low) - 0.5

    Range: [-0.5, +0.5]. Positive = bullish rejection.
    """
    body = (df["high"] - df["low"]).replace(0, np.nan)
    bull = (df["close"] > df["open"])
    score = np.where(
        bull,
        (df["close"] - df["low"]) / body - 0.5,
        (df["high"] - df["close"]) / body - 0.5,
    )
    return pd.Series(score, index=df.index, name="bar_type_score").fillna(0.0)


def price_stddev_weakness(df: pd.DataFrame, window: int) -> pd.Series:
    """
    Price StdDev weakness score:
      Higher score when current bar's close sits near the LOWER band of the
      rolling mean ± stddev envelope (i.e. price has sold off into weakness).
      This is the entry setup for a counter-trend / mean-reversion pop.

      score = (mean + sd - close) / sd   (clipped to [0, 3])
    """
    mean = sma(df["close"], window)
    sd = stddev(df["close"], window).replace(0, np.nan)
    score = (mean + sd - df["close"]) / sd
    return score.clip(lower=0, upper=3).fillna(0.0)


def volume_stddev_surge(df: pd.DataFrame, window: int) -> pd.Series:
    """
    Volume StdDev surge score:
      Higher score when current bar's volume exceeds mean+1std by a wide margin.
      score = (volume - mean) / sd   (clipped to [0, 5])
    """
    mean = sma(df["volume"].astype(float), window)
    sd = stddev(df["volume"].astype(float), window).replace(0, np.nan)
    score = (df["volume"].astype(float) - mean) / sd
    return score.clip(lower=0, upper=5).fillna(0.0)


def compute_bar_score(
    df: pd.DataFrame,
    price_window: int = 20,
    volume_window: int = 20,
) -> pd.Series:
    """
    Composite Fitschen Bar Score (Ch 8).

      score = price_stddev_weakness + volume_stddev_surge + bar_type_score

    Components (each is non-negative except bar_type which is in [-0.5, +0.5]):
      - price_stddev_weakness  ∈ [0, 3]
      - volume_stddev_surge    ∈ [0, 5]
      - bar_type_score         ∈ [-0.5, +0.5]

    Practical range ≈ [-0.5, +8.5].
    Threshold for "Top Bin" entry is typically > 1.5.
    """
    p_score = price_stddev_weakness(df, price_window)
    v_score = volume_stddev_surge(df, volume_window)
    b_score = bar_type_score(df)
    composite = p_score + v_score + b_score
    composite.name = "bar_score"
    return composite


# =============================================================
#  Convenience: attach all indicators to a DataFrame
# =============================================================

def enrich_dataframe(df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
    """
    Attach every indicator used by the three Fitschen strategies.
    Returns a new DataFrame; original is not mutated.

    params (defaults match the seeders in app.core.bootstrap):
        sma_trend: 70
        lookback_low: 8
        lookback_high: 20
        stddev_window: 20
        range_window: 20
    """
    p = {
        "sma_trend": 70,
        "lookback_low": 8,
        "lookback_high": 20,
        "stddev_window": 20,
        "range_window": 20,
        "price_stddev_window": 20,
        "volume_stddev_window": 20,
    }
    if params:
        p.update(params)

    out = df.copy()
    out["sma_70"] = sma(out["close"], p["sma_trend"])
    out["low_8"] = rolling_low(out["close"], p["lookback_low"])
    out["high_20"] = rolling_high(out["close"], p["lookback_high"])
    out["stddev_20"] = stddev(out["close"], p["stddev_window"])
    out["stddev_pct"] = stddev_pct_of_price(out, p["stddev_window"])
    out["range_avg"] = average_range(out, p["range_window"])
    out["range_pct"] = range_pct_of_price(out, p["range_window"])
    out["atr_20"] = atr(out, 20)
    out["stop_distance"] = stop_distance_stddev(out, p["stddev_window"], mult=3.0)
    out["bar_score"] = compute_bar_score(
        out,
        price_window=p["price_stddev_window"],
        volume_window=p["volume_stddev_window"],
    )
    return out
