"""
tests.conftest
--------------
Shared pytest fixtures for the test suite.

These fixtures provide synthetic OHLCV data so tests don't depend on
the database or DhanHQ. Each fixture returns a pandas DataFrame.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Ensure backend/ is on sys.path so `from app...` works when running pytest
# from inside backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ============================================================
#  Synthetic OHLCV fixtures
# ============================================================

@pytest.fixture
def sample_ohlcv_30() -> pd.DataFrame:
    """30 bars of synthetic OHLCV data with a gentle uptrend + pullbacks.
    Enough for 8-day and 20-day lookbacks but NOT 70-day SMA."""
    np.random.seed(42)
    n = 30
    dates = pd.date_range("2025-01-01", periods=n, freq="B")  # business days
    base = 1000.0
    trend = np.linspace(0, 50, n)  # +5% uptrend over the period
    noise = np.random.normal(0, 15, n)  # ±1.5% daily noise
    close = base + trend + noise

    # Build OHLC from close: open = prev close + small gap, high/low = close ± range
    opn = np.empty(n)
    opn[0] = close[0]
    opn[1:] = close[:-1] + np.random.normal(0, 2, n - 1)
    high = np.maximum(close, opn) + np.abs(np.random.normal(0, 5, n))
    low = np.minimum(close, opn) - np.abs(np.random.normal(0, 5, n))
    volume = np.random.randint(100000, 500000, n).astype(int)

    df = pd.DataFrame({
        "timestamp": dates,
        "open": opn,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })
    return df


@pytest.fixture
def sample_ohlcv_100() -> pd.DataFrame:
    """100 bars — enough for 70-day SMA warmup + 20-day StdDev."""
    np.random.seed(123)
    n = 100
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    base = 1000.0
    # Mixed regime: uptrend first 50 bars, choppy next 30, downtrend last 20
    trend = np.concatenate([
        np.linspace(0, 80, 50),    # uptrend
        np.linspace(80, 60, 30),   # choppy/pullback
        np.linspace(60, 20, 20),   # downtrend
    ])
    noise = np.random.normal(0, 20, n)
    close = base + trend + noise

    opn = np.empty(n)
    opn[0] = close[0]
    opn[1:] = close[:-1] + np.random.normal(0, 3, n - 1)
    high = np.maximum(close, opn) + np.abs(np.random.normal(0, 8, n))
    low = np.minimum(close, opn) - np.abs(np.random.normal(0, 8, n))
    volume = np.random.randint(100000, 1_000_000, n).astype(int)

    # Inject a volume spike at bar 80
    volume[80] = 5_000_000

    df = pd.DataFrame({
        "timestamp": dates,
        "open": opn,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })
    return df


@pytest.fixture
def flat_ohlcv_30() -> pd.DataFrame:
    """30 bars at constant price — for testing edge cases (zero stddev)."""
    dates = pd.date_range("2025-01-01", periods=30, freq="B")
    return pd.DataFrame({
        "timestamp": dates,
        "open": 1000.0, "high": 1000.0, "low": 1000.0, "close": 1000.0,
        "volume": 100000,
    })


@pytest.fixture
def trending_up_ohlcv_80() -> pd.DataFrame:
    """80 bars in a clean uptrend — for trend-following entry tests.
    Each bar closes higher than the previous, with small pullbacks."""
    n = 80
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    close = [1000.0]
    for i in range(1, n):
        # +2 per day on average, with occasional -1 pullbacks
        delta = 2.5 if i % 5 != 0 else -1.0
        close.append(close[-1] + delta)
    close = np.array(close)
    opn = np.roll(close, 1)
    opn[0] = close[0]
    high = close + 3
    low = close - 3
    volume = np.full(n, 200000, dtype=int)

    return pd.DataFrame({
        "timestamp": dates, "open": opn, "high": high,
        "low": low, "close": close, "volume": volume,
    })


@pytest.fixture
def choppy_ohlcv_80() -> pd.DataFrame:
    """80 bars in a choppy/range-bound market — for counter-trend tests.
    Price oscillates between 950 and 1050 with no clear trend."""
    np.random.seed(456)
    n = 80
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    # Sine wave + noise → oscillates around 1000
    t = np.arange(n)
    close = 1000 + 40 * np.sin(t * 0.3) + np.random.normal(0, 10, n)
    opn = np.roll(close, 1)
    opn[0] = close[0]
    high = np.maximum(close, opn) + 5
    low = np.minimum(close, opn) - 5
    volume = np.random.randint(100000, 500000, n).astype(int)

    return pd.DataFrame({
        "timestamp": dates, "open": opn, "high": high,
        "low": low, "close": close, "volume": volume,
    })
