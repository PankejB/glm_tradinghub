"""
app.main
--------
FastAPI entrypoint. Wires:
- logging (loguru intercept)
- DB table creation + seed bootstrap on startup
- routers (auth, strategies, backtest, trading, portfolio)
- CORS for the React frontend
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import init_db
from app.core.bootstrap import run_bootstrap
from app.api.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Starting Algorithmic Trading System backend (env={})", settings.APP_ENV)
    try:
        init_db()
        logger.info("DB tables ensured")
        run_bootstrap()
        logger.info("Bootstrap completed")
    except Exception as exc:  # noqa: BLE001
        # Don't crash the app — DB may not be up yet in dev. Log loudly.
        logger.error("Startup DB/bootstrap failed: {}", exc)
    yield
    logger.info("Shutting down backend")


app = FastAPI(
    title="Algorithmic Trading System",
    description=(
        "Full-stack algorithmic trading system for Indian markets "
        "(NSE / NFO / MCX) implementing Keith Fitschen's "
        "'Building Reliable Trading Systems' strategies via the DhanHQ SDK."
    ),
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS — allow the React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers under /api
app.include_router(api_router, prefix="/api")


@app.get("/health", tags=["meta"])
def health_check():
    return {"status": "ok", "service": "trading-backend", "version": "0.2.0"}


@app.get("/", tags=["meta"])
def root():
    return {
        "message": "Algorithmic Trading System API",
        "docs": "/docs",
        "step": 2,
        "endpoints": [
            "/api/auth/login",
            "/api/strategies",
            "/api/backtest/start",
            "/api/backtest/status/{task_id}",
            "/api/trading/start",
            "/api/trading/stop",
            "/api/portfolio/status",
        ],
    }
