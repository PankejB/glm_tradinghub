"""
app.core.bootstrap
------------------
Seeds default strategies (Fitschen) + admin user on first run.
"""
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user import User
from app.models.strategy import Strategy
from app.core.security import hash_password
from app.core.config import settings
from loguru import logger


# ---- Default strategy parameters (Fitschen book rules) --------------------
STOCK_CT_PARAMS = {
    "lookback_low": 8,           # 8-day low for entry
    "sma_trend": 70,             # 70-day SMA uptrend filter
    "stddev_window": 20,         # 20-day StdDev
    "stddev_min_pct": 0.03,      # volatility filter: >3% of price
    "stop_loss_stddev_mult": 3,  # 3x StdDev catastrophic stop
    "profit_target": 300,        # ₹300 fixed profit target
    "time_exit_bars": 8,         # time-based exit after 8 bars
    "risk_per_trade_pct": 1.0,   # 1% fixed-risk sizing
}

MCX_TF_PARAMS = {
    "lookback_high": 20,         # 20-day high breakout
    "sma_trend": 70,             # 70-day SMA uptrend filter
    "range_window": 20,          # 20-day average range
    "range_min_pct": 0.005,      # avg range > 0.5% of price
    "stddev_window": 20,
    "stop_loss_stddev_mult": 3,  # 3x StdDev catastrophic stop
    "trailing_stop_atr_mult": 2.0,
    "risk_per_trade_pct": 1.0,
}

INDEX_BS_PARAMS = {
    "score_threshold": 1.5,      # Top-bin bar score threshold
    "price_stddev_window": 20,
    "volume_stddev_window": 20,
    "bar_lookback": 1,           # score computed on most recent bar
    "strike_offset": 0,          # ATM (0 strikes from spot)
    "option_type": "CE",         # Calls only (long-bias)
    "dte_target": 7,             # target ~7 DTE
    "stop_loss_pct": 0.25,       # 25% SL on option premium
    "profit_target_pct": 0.50,   # 50% TP on option premium
    "time_exit_bars": 5,         # exit after 5 bars if neither hit
    "risk_per_trade_pct": 1.0,
}


STRATEGY_SEEDS = [
    {
        "name": "Stock Counter-Trend (Fitschen Ch 5/6)",
        "slug": "stock-counter-trend",
        "strategy_type": "stock_counter_trend",
        "book_reference": "Building Reliable Trading Systems, Ch 5/6 — Counter-Trend Stock logic",
        "allowed_segments": ["NSE_EQ", "NSE_FNO"],
        "parameters": STOCK_CT_PARAMS,
        "description": (
            "Buy when Close < 8-day Low AND Close > 70-day SMA AND 20d StdDev > 3% of Price. "
            "Exit at 8-bar time stop or ₹300 profit target. SL = 3 × 20d StdDev from entry."
        ),
    },
    {
        "name": "MCX Trend-Following (Fitschen Ch 5/6)",
        "slug": "mcx-trend-following",
        "strategy_type": "mcx_trend_following",
        "book_reference": "Building Reliable Trading Systems, Ch 5/6 — Trend-Following Commodity logic",
        "allowed_segments": ["MCX"],
        "parameters": MCX_TF_PARAMS,
        "description": (
            "Buy when Close > 20-day High AND Close > 70-day SMA AND Avg Range > 0.5% of Price. "
            "Exit at trailing stop or 3x StdDev catastrophic stop."
        ),
    },
    {
        "name": "Index Option Bar-Scoring (Fitschen Ch 8)",
        "slug": "index-bar-scoring",
        "strategy_type": "index_bar_scoring",
        "book_reference": "Building Reliable Trading Systems, Ch 8 — Bar-Scoring",
        "allowed_segments": ["NSE_FNO"],
        "parameters": INDEX_BS_PARAMS,
        "description": (
            "Score = f(Price StdDev weakness, Volume StdDev surge, rejection tails). "
            "Buy ATM Call Options only if Bar Score > 1.5 (Top Bin logic)."
        ),
    },
]


def seed_strategies(db: Session) -> int:
    """Insert default strategies if not present. Returns count created."""
    created = 0
    for seed in STRATEGY_SEEDS:
        exists = db.query(Strategy).filter_by(slug=seed["slug"]).first()
        if exists:
            continue
        strat = Strategy(**seed, is_active=True)
        db.add(strat)
        created += 1
        logger.info("Seeded strategy: {}", seed["slug"])
    if created:
        db.commit()
    return created


def seed_admin_user(db: Session) -> User | None:
    """Create a default admin user if no users exist."""
    if db.query(User).count() > 0:
        return None
    admin = User(
        email="admin@trading.local",
        full_name="Default Admin",
        hashed_password=hash_password("admin123"),
        starting_capital=settings.DEFAULT_CAPITAL,
        current_equity=settings.DEFAULT_CAPITAL,
        available_margin=settings.DEFAULT_CAPITAL,
        is_active=True,
        is_superuser=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    logger.warning("Created default admin user: admin@trading.local / admin123  (CHANGE PASSWORD!)")
    return admin


def run_bootstrap() -> None:
    """Run all seeders. Safe to call repeatedly."""
    db = SessionLocal()
    try:
        seed_admin_user(db)
        seed_strategies(db)
    finally:
        db.close()


if __name__ == "__main__":
    run_bootstrap()
