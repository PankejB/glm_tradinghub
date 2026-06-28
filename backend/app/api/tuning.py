"""
app.api.tuning
--------------
GET /api/tuning/{strategy_id}  — returns slider specs for the strategy tuning UI

The slider metadata (min/max/step) is curated per strategy_type and reflects
the sensible ranges a quant would explore when tuning each Fitschen strategy.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.strategy import Strategy
from app.schemas.tuning import StrategyTuningSchema, ParameterSliderSpec

router = APIRouter(prefix="/tuning", tags=["tuning"])


# =====================================================================
#  Slider definitions per strategy type
#  Each parameter has: min, max, step, default, unit, description
# =====================================================================

STOCK_CT_SLIDERS = [
    {
        "title": "Entry Filters",
        "parameters": [
            ParameterSliderSpec(
                key="lookback_low", label="Lookback Low (days)", type="integer",
                min=3, max=20, step=1, default=8, unit="days",
                description="Number of bars to look back for the low. Lower = more sensitive, higher = fewer signals.",
            ),
            ParameterSliderSpec(
                key="sma_trend", label="Trend SMA (days)", type="integer",
                min=20, max=200, step=5, default=70, unit="days",
                description="Long-term SMA for uptrend filter. 70 is Fitschen's default.",
            ),
            ParameterSliderSpec(
                key="stddev_window", label="StdDev Window", type="integer",
                min=5, max=50, step=1, default=20, unit="days",
                description="Rolling window for standard deviation calculation.",
            ),
            ParameterSliderSpec(
                key="stddev_min_pct", label="Min Volatility (StdDev %)", type="number",
                min=0.005, max=0.05, step=0.0025, default=0.03, unit="%",
                description="Minimum StdDev as fraction of price. 0.03 = 3% (Fitschen). Lower = more trades.",
            ),
        ],
    },
    {
        "title": "Exit Rules",
        "parameters": [
            ParameterSliderSpec(
                key="profit_target", label="Profit Target", type="number",
                min=50, max=1000, step=50, default=300, unit="₹",
                description="Absolute profit target in rupees. ₹300 is Fitschen's default for stocks.",
            ),
            ParameterSliderSpec(
                key="time_exit_bars", label="Time Exit (bars)", type="integer",
                min=1, max=20, step=1, default=8, unit="bars",
                description="Exit after N bars if neither SL nor TP hit.",
            ),
        ],
    },
    {
        "title": "Risk Management",
        "parameters": [
            ParameterSliderSpec(
                key="stop_loss_stddev_mult", label="SL StdDev Multiplier", type="number",
                min=1, max=5, step=0.5, default=3, unit="x",
                description="Catastrophic stop = N × StdDev. 3x is Fitschen's default.",
            ),
            ParameterSliderSpec(
                key="risk_per_trade_pct", label="Risk Per Trade", type="number",
                min=0.25, max=3, step=0.25, default=1.0, unit="%",
                description="Fixed-risk percentage. 1% = SL hit loses exactly 1% of equity.",
            ),
        ],
    },
]

MCX_TF_SLIDERS = [
    {
        "title": "Entry Filters",
        "parameters": [
            ParameterSliderSpec(
                key="lookback_high", label="Breakout High (days)", type="integer",
                min=5, max=55, step=1, default=20, unit="days",
                description="Number of bars for breakout high. Lower = more breakouts (noisier).",
            ),
            ParameterSliderSpec(
                key="sma_trend", label="Trend SMA (days)", type="integer",
                min=20, max=200, step=5, default=70, unit="days",
                description="Long-term SMA for trend filter.",
            ),
            ParameterSliderSpec(
                key="range_window", label="Range Window", type="integer",
                min=5, max=50, step=1, default=20, unit="days",
                description="Window for average range calculation.",
            ),
            ParameterSliderSpec(
                key="range_min_pct", label="Min Range %", type="number",
                min=0.001, max=0.02, step=0.001, default=0.005, unit="%",
                description="Minimum average range as fraction of price. 0.005 = 0.5%.",
            ),
        ],
    },
    {
        "title": "Exit Rules",
        "parameters": [
            ParameterSliderSpec(
                key="trailing_stop_atr_mult", label="Trailing Stop (ATR mult)", type="number",
                min=0.5, max=5, step=0.25, default=2.0, unit="x",
                description="Trailing stop = N × ATR below highest close. Lower = tighter (more exits).",
            ),
            ParameterSliderSpec(
                key="stop_loss_stddev_mult", label="Catastrophic SL (StdDev mult)", type="number",
                min=1, max=5, step=0.5, default=3, unit="x",
                description="Catastrophic stop = N × StdDev from entry.",
            ),
        ],
    },
    {
        "title": "Risk Management",
        "parameters": [
            ParameterSliderSpec(
                key="risk_per_trade_pct", label="Risk Per Trade", type="number",
                min=0.25, max=3, step=0.25, default=1.0, unit="%",
                description="Fixed-risk percentage per trade.",
            ),
        ],
    },
]

INDEX_BS_SLIDERS = [
    {
        "title": "Bar Scoring",
        "parameters": [
            ParameterSliderSpec(
                key="score_threshold", label="Score Threshold", type="number",
                min=0.5, max=5.0, step=0.25, default=1.5,
                description="Bar score must exceed this to trigger entry. 1.5 = Top Bin (Fitschen).",
            ),
            ParameterSliderSpec(
                key="price_stddev_window", label="Price StdDev Window", type="integer",
                min=5, max=50, step=1, default=20, unit="days",
                description="Window for price weakness score.",
            ),
            ParameterSliderSpec(
                key="volume_stddev_window", label="Volume StdDev Window", type="integer",
                min=5, max=50, step=1, default=20, unit="days",
                description="Window for volume surge score.",
            ),
        ],
    },
    {
        "title": "Option Selection",
        "parameters": [
            ParameterSliderSpec(
                key="strike_offset", label="Strike Offset from ATM", type="integer",
                min=-3, max=3, step=1, default=0,
                description="0 = ATM, +1 = OTM, -1 = ITM. Negative = more expensive options.",
            ),
            ParameterSliderSpec(
                key="dte_target", label="Target DTE (days)", type="integer",
                min=1, max=30, step=1, default=7, unit="days",
                description="Target days-to-expiry for option selection.",
            ),
            ParameterSliderSpec(
                key="option_type", label="Option Type", type="select", default="CE",
                options=[
                    {"value": "CE", "label": "Call (CE)"},
                    {"value": "PE", "label": "Put (PE)"},
                ],
                description="Buy calls (long-bias) or puts (short-bias).",
            ),
        ],
    },
    {
        "title": "Exit Rules",
        "parameters": [
            ParameterSliderSpec(
                key="stop_loss_pct", label="Stop Loss %", type="number",
                min=0.10, max=0.50, step=0.05, default=0.25, unit="%",
                description="SL as fraction of option premium. 0.25 = 25% loss.",
            ),
            ParameterSliderSpec(
                key="profit_target_pct", label="Profit Target %", type="number",
                min=0.25, max=2.0, step=0.25, default=0.50, unit="%",
                description="TP as fraction of premium. 0.50 = 50% gain.",
            ),
            ParameterSliderSpec(
                key="time_exit_bars", label="Time Exit (bars)", type="integer",
                min=1, max=15, step=1, default=5, unit="bars",
                description="Exit after N bars if neither SL nor TP hit.",
            ),
        ],
    },
    {
        "title": "Risk Management",
        "parameters": [
            ParameterSliderSpec(
                key="risk_per_trade_pct", label="Risk Per Trade", type="number",
                min=0.25, max=3, step=0.25, default=1.0, unit="%",
                description="Fixed-risk percentage per trade.",
            ),
        ],
    },
]


SLIDER_MAP = {
    "stock_counter_trend": STOCK_CT_SLIDERS,
    "mcx_trend_following": MCX_TF_SLIDERS,
    "index_bar_scoring": INDEX_BS_SLIDERS,
}


@router.get("/{strategy_id}", response_model=StrategyTuningSchema)
def get_tuning_schema(
    strategy_id: int,
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return slider specs for the strategy tuning UI."""
    strat = db.get(Strategy, strategy_id)
    if not strat:
        raise HTTPException(status_code=404, detail="Strategy not found")

    groups = SLIDER_MAP.get(strat.strategy_type)
    if not groups:
        raise HTTPException(
            status_code=404,
            detail=f"No tuning schema for strategy_type={strat.strategy_type}",
        )

    # Serialize groups (they contain Pydantic models which need .model_dump())
    serialized_groups = []
    for group in groups:
        serialized_groups.append({
            "title": group["title"],
            "parameters": [p.model_dump() for p in group["parameters"]],
        })

    return StrategyTuningSchema(
        strategy_id=strat.id,
        strategy_slug=strat.slug,
        strategy_name=strat.name,
        strategy_type=strat.strategy_type,
        groups=serialized_groups,
    )
