"""
app.main
--------
Minimal FastAPI entrypoint for Step 1.
Will be expanded with routers in Step 5.
"""
from fastapi import FastAPI

app = FastAPI(
    title="Algorithmic Trading System",
    description=(
        "Full-stack algorithmic trading system for Indian markets "
        "(NSE / NFO / MCX) implementing Keith Fitschen's "
        "'Building Reliable Trading Systems' strategies via the DhanHQ SDK."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.get("/health", tags=["meta"])
def health_check():
    return {"status": "ok", "service": "trading-backend", "version": "0.1.0"}


@app.get("/", tags=["meta"])
def root():
    return {
        "message": "Algorithmic Trading System API",
        "docs": "/docs",
        "step": 1,
        "next": "Step 2 will add SQLAlchemy models and DB layer",
    }
