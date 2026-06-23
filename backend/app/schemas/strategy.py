"""
app.schemas.strategy
--------------------
"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class StrategyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    strategy_type: str
    book_reference: str | None
    allowed_segments: list
    parameters: dict
    latest_gtp_ratio: float | None
    is_tradeable: bool
    description: str | None
    is_active: bool
    created_at: datetime
