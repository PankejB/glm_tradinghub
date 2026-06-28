"""
diagnose_strategy.py — Run a strategy on the local DB and print why signals
are (or aren't) triggering.

Usage:
    cd ~/glm_tradinghub/backend
    source .venv/bin/activate
    python3 -m scripts.diagnose_strategy        # if placed under backend/scripts/
    # or:
    python3 diagnose_strategy.py
"""
import sys
from datetime import date, timedelta

import pandas as pd

from app.db.session import SessionLocal
from app.models.ohlcv_bar import OhlcvBar
from app.models.strategy import Strategy
from app.services.indicators import enrich_dataframe
from app.strategies import build_strategy


def main():
    symbol = "RELIANCE"
    security_id = "2885"
    timeframe = "1D"

    db = SessionLocal()
    try:
        # Load bars
        rows = (
            db.query(OhlcvBar)
            .filter(
                OhlcvBar.security_id == security_id,
                OhlcvBar.timeframe == timeframe,
            )
            .order_by(OhlcvBar.timestamp.asc())
            .all()
        )
        if not rows:
            print(f"✗ No bars found for {symbol} (security_id={security_id})")
            return
        df = pd.DataFrame([{
            "timestamp": r.timestamp,
            "open": r.open, "high": r.high, "low": r.low,
            "close": r.close, "volume": r.volume,
        } for r in rows])
        print(f"✓ Loaded {len(df)} bars for {symbol}")
        print(f"  Date range: {df['timestamp'].min()} → {df['timestamp'].max()}")
        print(f"  Price range: ₹{df['close'].min():.2f} → ₹{df['close'].max():.2f}")
        print()

        # Load the Stock Counter-Trend strategy
        strat_row = db.query(Strategy).filter_by(slug="stock-counter-trend").first()
        if not strat_row:
            print("✗ Strategy 'stock-counter-trend' not found in DB")
            return
        strategy = build_strategy(strat_row.strategy_type, strat_row.parameters)

        # Enrich with indicators
        enriched = strategy.enrich(df)
        print(f"✓ Enriched DataFrame shape: {enriched.shape}")
        print(f"✓ Columns: {enriched.columns.tolist()}")
        print()

        # Show last 20 bars with key indicators
        print("=" * 100)
        print(f"Last 20 bars — indicator values")
        print("=" * 100)
        cols_to_show = [
            "timestamp", "close",
            "low_8", "sma_70",
            "stddev_20", "stddev_pct",
        ]
        cols_to_show = [c for c in cols_to_show if c in enriched.columns]
        recent = enriched[cols_to_show].tail(20).copy()
        # Format numbers
        for c in recent.columns:
            if c == "timestamp":
                recent[c] = recent[c].dt.strftime("%Y-%m-%d")
            elif c in ("stddev_pct",):
                recent[c] = recent[c].apply(lambda v: f"{v:.4f}" if pd.notna(v) else "NaN")
            else:
                recent[c] = recent[c].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "NaN")
        print(recent.to_string(index=False))
        print()

        # Count how many bars meet each individual condition
        print("=" * 100)
        print("Condition analysis (across all bars)")
        print("=" * 100)

        close = enriched["close"]
        low_8 = enriched["low_8"]
        sma_70 = enriched["sma_70"]
        stddev_pct = enriched["stddev_pct"]

        n_total = len(enriched)
        n_valid = enriched[["low_8", "sma_70", "stddev_pct"]].dropna().shape[0]

        # Each condition
        cond_below_low = (close < low_8).sum()
        cond_above_sma = (close > sma_70).sum()
        cond_vol_ok = (stddev_pct > 0.03).sum()

        # Combinations
        combo_1_2 = ((close < low_8) & (close > sma_70)).sum()
        combo_1_3 = ((close < low_8) & (stddev_pct > 0.03)).sum()
        combo_2_3 = ((close > sma_70) & (stddev_pct > 0.03)).sum()
        combo_all = ((close < low_8) & (close > sma_70) & (stddev_pct > 0.03)).sum()

        print(f"Total bars:                {n_total}")
        print(f"Bars with all indicators:  {n_valid}")
        print()
        print(f"Condition 1 (Close < 8d Low):       {cond_below_low} bars meet it ({cond_below_low/max(n_valid,1)*100:.1f}%)")
        print(f"Condition 2 (Close > 70d SMA):      {cond_above_sma} bars meet it ({cond_above_sma/max(n_valid,1)*100:.1f}%)")
        print(f"Condition 3 (StdDev% > 3%):         {cond_vol_ok} bars meet it ({cond_vol_ok/max(n_valid,1)*100:.1f}%)")
        print()
        print(f"Combo (1 AND 2):                    {combo_1_2} bars")
        print(f"Combo (1 AND 3):                    {combo_1_3} bars")
        print(f"Combo (2 AND 3):                    {combo_2_3} bars")
        print(f"Combo (1 AND 2 AND 3) = ENTRY:      {combo_all} bars  ← this is why trades={combo_all}")
        print()

        if combo_all == 0:
            print("=" * 100)
            print("⚠️  ZERO entry signals triggered. Possible reasons:")
            print("=" * 100)
            if cond_below_low == 0:
                print("  • RELIANCE never traded below its 8-day low in the test window")
                print("    (bullish regime — pullbacks weren't deep enough)")
            if cond_vol_ok == 0:
                print("  • RELIANCE's 20-day StdDev never exceeded 3% of price")
                print(f"    Max StdDev% in data: {stddev_pct.max():.4f} ({stddev_pct.max()*100:.2f}%)")
                print("    → Consider lowering stddev_min_pct from 0.03 to a value just above max")
            if cond_above_sma == 0:
                print("  • RELIANCE never traded above its 70-day SMA (sustained downtrend)")
            if combo_1_2 == 0 and cond_below_low > 0 and cond_above_sma > 0:
                print("  • Conditions 1 and 2 never occurred on the same bar")
                print("    (when below 8d low, the 70d SMA was already above price)")
        print()

        # Show which bars came CLOSEST to triggering (max stddev_pct where cond 1+2 hold)
        candidates = enriched[(close < low_8) & (close > sma_70)].copy()
        if not candidates.empty:
            print("=" * 100)
            print(f"Bars meeting Conditions 1+2 (Close<8dLow AND Close>70dSMA): {len(candidates)}")
            print(f"Top 10 by StdDev% (closest to triggering Condition 3):")
            print("=" * 100)
            top = candidates.nlargest(10, "stddev_pct")[
                ["timestamp", "close", "low_8", "sma_70", "stddev_20", "stddev_pct"]
            ].copy()
            top["timestamp"] = top["timestamp"].dt.strftime("%Y-%m-%d")
            top["stddev_pct"] = top["stddev_pct"].apply(lambda v: f"{v:.4f}")
            for c in ["close", "low_8", "sma_70", "stddev_20"]:
                top[c] = top[c].apply(lambda v: f"{v:.2f}")
            print(top.to_string(index=False))
        else:
            print("No bars meet Conditions 1+2 together — strategy cannot trigger on this data.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
