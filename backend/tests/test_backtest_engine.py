"""
tests.test_backtest_engine
-------------------------
Unit tests for the Backtester engine (position sizing, PnL, GtP, drawdown).
"""
import pandas as pd
import pytest
from datetime import datetime, timedelta

from app.backtest.engine import Backtester, BacktestConfig, BacktestResult
from app.strategies.base import StrategyBase, Signal
from app.strategies.stock_counter_trend import StockCounterTrendStrategy
from app.strategies.mcx_trend_following import McxTrendFollowingStrategy


# ============================================================
#  Helper: a strategy that always fires entry on bar 5 and exits on bar 10
# ============================================================

class AlwaysEnterStrategy(StrategyBase):
    """Test double: fires a deterministic entry on bar 5, exits on bar 10."""
    name = "Always Enter (Test)"
    strategy_type = "test_always_enter"
    book_reference = "Test fixture"
    default_params = {
        "lookback_low": 8, "sma_trend": 70, "stddev_window": 20,
        "stddev_min_pct": 0.03, "stop_loss_stddev_mult": 3,
        "profit_target": 300.0, "time_exit_bars": 8, "risk_per_trade_pct": 1.0,
    }

    def check_entry(self, row, prev_row):
        if int(row.name) == 5:
            close = float(row["close"])
            return Signal(
                timestamp=row["timestamp"], bar_index=5,
                action="ENTER", side="BUY",
                entry_price=close, stop_loss=close - 50, take_profit=close + 100,
                meta={"test": True},
            )
        return None

    def check_exit(self, open_trade, row, prev_row, bars_held):
        if int(row.name) == 10:
            return Signal(
                timestamp=row["timestamp"], bar_index=10,
                action="EXIT", side="SELL",
                entry_price=float(row["close"]),
                meta={"exit_reason": "test_exit"},
            )
        return None


# ============================================================
#  Position sizing (Fitschen Fixed-Risk)
# ============================================================

class TestPositionSizing:
    def test_basic_sizing(self):
        """qty = (equity * 1%) / stop_distance."""
        bt = Backtester(
            strategy=AlwaysEnterStrategy(),
            df=pd.DataFrame({"timestamp": [], "open": [], "high": [], "low": [], "close": [], "volume": []}),
        )
        sig = Signal(
            timestamp=datetime.now(), bar_index=0, action="ENTER", side="BUY",
            entry_price=1000.0, stop_loss=990.0,  # stop_distance = 10
        )
        qty = bt._size_position(equity=100_000, sig=sig)
        # risk_amount = 100000 * 1% = 1000
        # qty = 1000 / 10 = 100
        assert qty == 100

    def test_zero_stop_distance_returns_zero(self):
        bt = Backtester(strategy=AlwaysEnterStrategy(), df=pd.DataFrame({
            "timestamp": [], "open": [], "high": [], "low": [], "close": [], "volume": []
        }))
        sig = Signal(
            timestamp=datetime.now(), bar_index=0, action="ENTER", side="BUY",
            entry_price=1000.0, stop_loss=1000.0,  # zero distance
        )
        assert bt._size_position(equity=100_000, sig=sig) == 0

    def test_no_entry_price_returns_zero(self):
        bt = Backtester(strategy=AlwaysEnterStrategy(), df=pd.DataFrame({
            "timestamp": [], "open": [], "high": [], "low": [], "close": [], "volume": []
        }))
        sig = Signal(
            timestamp=datetime.now(), bar_index=0, action="ENTER", side="BUY",
            entry_price=0.0, stop_loss=10.0,
        )
        assert bt._size_position(equity=100_000, sig=sig) == 0

    def test_sizing_scales_with_equity(self):
        """Double equity → double qty (linear relationship)."""
        bt = Backtester(strategy=AlwaysEnterStrategy(), df=pd.DataFrame({
            "timestamp": [], "open": [], "high": [], "low": [], "close": [], "volume": []
        }))
        sig = Signal(
            timestamp=datetime.now(), bar_index=0, action="ENTER", side="BUY",
            entry_price=1000.0, stop_loss=990.0,
        )
        qty_100k = bt._size_position(equity=100_000, sig=sig)
        qty_200k = bt._size_position(equity=200_000, sig=sig)
        assert qty_200k == qty_100k * 2

    def test_custom_risk_pct(self):
        """2% risk → double qty vs 1%."""
        bt = Backtester(
            strategy=AlwaysEnterStrategy({"risk_per_trade_pct": 2.0}),
            df=pd.DataFrame({"timestamp": [], "open": [], "high": [], "low": [], "close": [], "volume": []}),
            config=BacktestConfig(risk_per_trade_pct=2.0),
        )
        sig = Signal(
            timestamp=datetime.now(), bar_index=0, action="ENTER", side="BUY",
            entry_price=1000.0, stop_loss=990.0,
        )
        qty = bt._size_position(equity=100_000, sig=sig)
        # risk_amount = 100000 * 2% = 2000; qty = 2000 / 10 = 200
        assert qty == 200


# ============================================================
#  Slippage + PnL
# ============================================================

class TestSlippageAndPnl:
    def test_buy_slippage_increases_price(self):
        bt = Backtester(strategy=AlwaysEnterStrategy(), df=pd.DataFrame({
            "timestamp": [], "open": [], "high": [], "low": [], "close": [], "volume": []
        }))
        slipped = bt._apply_slippage(1000.0, is_buy=True)
        assert slipped > 1000.0
        assert slipped == pytest.approx(1000.0 * 1.0005)

    def test_sell_slippage_decreases_price(self):
        bt = Backtester(strategy=AlwaysEnterStrategy(), df=pd.DataFrame({
            "timestamp": [], "open": [], "high": [], "low": [], "close": [], "volume": []
        }))
        slipped = bt._apply_slippage(1000.0, is_buy=False)
        assert slipped < 1000.0

    def test_pnl_long_winner(self):
        """BUY at 100, exit at 110, qty=10 → gross = 100, minus commission."""
        bt = Backtester(
            strategy=AlwaysEnterStrategy(),
            df=pd.DataFrame({"timestamp": [], "open": [], "high": [], "low": [], "close": [], "volume": []}),
            config=BacktestConfig(commission_per_trade=20.0),
        )
        trade = {"entry_price": 100.0, "quantity": 10, "side": "BUY"}
        pnl = bt._compute_pnl(trade, exit_price=110.0)
        # gross = (110 - 100) * 10 = 100; minus 2 * 20 = 60
        assert pnl == pytest.approx(60.0)

    def test_pnl_long_loser(self):
        """BUY at 100, exit at 95, qty=10 → gross = -50, minus commission."""
        bt = Backtester(
            strategy=AlwaysEnterStrategy(),
            df=pd.DataFrame({"timestamp": [], "open": [], "high": [], "low": [], "close": [], "volume": []}),
            config=BacktestConfig(commission_per_trade=20.0),
        )
        trade = {"entry_price": 100.0, "quantity": 10, "side": "BUY"}
        pnl = bt._compute_pnl(trade, exit_price=95.0)
        # gross = (95 - 100) * 10 = -50; minus 40 = -90
        assert pnl == pytest.approx(-90.0)


# ============================================================
#  Full backtest run
# ============================================================

class TestBacktesterRun:
    def _make_df(self, n=15):
        """15 bars at constant price 1000."""
        dates = pd.date_range("2025-01-01", periods=n, freq="B")
        return pd.DataFrame({
            "timestamp": dates,
            "open": 1000.0, "high": 1005.0, "low": 995.0,
            "close": 1000.0, "volume": 100000,
        })

    def test_backtest_completes_with_always_enter(self):
        """The AlwaysEnterStrategy fires on bar 5 and exits on bar 10."""
        df = self._make_df(15)
        bt = Backtester(
            strategy=AlwaysEnterStrategy(),
            df=df,
            config=BacktestConfig(initial_capital=100_000, commission_per_trade=0),
        )
        result = bt.run()
        assert result.total_trades == 1
        assert result.error is None

    def test_backtest_initial_final_equity(self):
        df = self._make_df(15)
        bt = Backtester(
            strategy=AlwaysEnterStrategy(),
            df=df,
            config=BacktestConfig(initial_capital=100_000, commission_per_trade=0),
        )
        result = bt.run()
        assert result.initial_capital == 100_000
        # Final equity should be initial + pnl (could be 0 if flat price)
        assert isinstance(result.final_equity, float)

    def test_equity_curve_has_n_points(self):
        df = self._make_df(15)
        bt = Backtester(
            strategy=AlwaysEnterStrategy(),
            df=df,
            config=BacktestConfig(initial_capital=100_000),
        )
        result = bt.run()
        assert len(result.equity_curve) == 15

    def test_no_trades_when_strategy_never_fires(self):
        """Use a strategy that never fires — should produce 0 trades."""
        class NeverEnterStrategy(AlwaysEnterStrategy):
            def check_entry(self, row, prev_row):
                return None
        df = self._make_df(15)
        bt = Backtester(
            strategy=NeverEnterStrategy(),
            df=df,
            config=BacktestConfig(initial_capital=100_000),
        )
        result = bt.run()
        assert result.total_trades == 0
        assert result.net_profit == 0
        assert result.final_equity == 100_000

    def test_gtp_zero_when_no_drawdown(self):
        """If max_drawdown_pct = 0, GtP should be 0 (avoid division by zero)."""
        df = self._make_df(15)
        bt = Backtester(
            strategy=AlwaysEnterStrategy(),
            df=df,
            config=BacktestConfig(initial_capital=100_000, commission_per_trade=0, slippage_pct=0),
        )
        result = bt.run()
        # With flat price, no drawdown → GtP = 0
        if result.max_drawdown_pct == 0:
            assert result.gtp_ratio == 0


# ============================================================
#  Strategy registry
# ============================================================

class TestStrategyRegistry:
    def test_build_stock_counter_trend(self):
        from app.strategies import build_strategy, StockCounterTrendStrategy
        s = build_strategy("stock_counter_trend")
        assert isinstance(s, StockCounterTrendStrategy)

    def test_build_mcx_trend_following(self):
        from app.strategies import build_strategy, McxTrendFollowingStrategy
        s = build_strategy("mcx_trend_following")
        assert isinstance(s, McxTrendFollowingStrategy)

    def test_build_index_bar_scoring(self):
        from app.strategies import build_strategy, IndexBarScoringStrategy
        s = build_strategy("index_bar_scoring")
        assert isinstance(s, IndexBarScoringStrategy)

    def test_build_unknown_type_raises(self):
        from app.strategies import build_strategy
        with pytest.raises(ValueError, match="Unknown strategy_type"):
            build_strategy("nonexistent_strategy")

    def test_build_with_param_override(self):
        from app.strategies import build_strategy
        s = build_strategy("stock_counter_trend", {"profit_target": 500})
        assert s.params["profit_target"] == 500
        # Default preserved
        assert s.params["lookback_low"] == 8
