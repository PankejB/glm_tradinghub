"""
app.api.router
--------------
Aggregates all sub-routers under /api.
"""
from fastapi import APIRouter

from app.api import auth, strategies, backtest, trading, portfolio, data

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(strategies.router)
api_router.include_router(backtest.router)
api_router.include_router(trading.router)
api_router.include_router(portfolio.router)
api_router.include_router(data.router)
