"""
app.schemas.tuning
------------------
Schema for strategy parameter tuning metadata (sliders).
"""
from pydantic import BaseModel


class ParameterSliderSpec(BaseModel):
    """One slider definition for the tuning UI."""
    key: str                       # parameter key, e.g. "stddev_min_pct"
    label: str                     # human-readable label
    type: str = "number"           # 'number' | 'integer' | 'select'
    min: float | None = None
    max: float | None = None
    step: float = 1.0
    default: float | str = 0
    unit: str = ""                 # '%', '₹', 'days', 'bars', 'x'
    description: str = ""
    # For 'select' type
    options: list[dict] | None = None   # [{value, label}, ...]


class StrategyTuningSchema(BaseModel):
    """Full tuning schema for one strategy."""
    strategy_id: int
    strategy_slug: str
    strategy_name: str
    strategy_type: str
    groups: list[dict]    # [{title, parameters: [ParameterSliderSpec]}]
