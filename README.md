# Algorithmic Trading System — Fitschen Rules + DhanHQ

A production-grade, full-stack algorithmic trading system for the **Indian market** (NSE Stocks, Stock Options, Index Options, MCX Commodities) built on the trading logic from Keith Fitschen's *"Building Reliable Trading Systems"*.

## Tech Stack

| Layer        | Technology                                                      |
| ------------ | --------------------------------------------------------------- |
| Backend      | Python 3.11, FastAPI, SQLAlchemy 2.x, Celery, Redis             |
| Frontend     | React 18 (Vite), TailwindCSS, Recharts, React Query, Axios      |
| Database     | PostgreSQL 15 (+ TimeScaleDB extension for OHLCV)               |
| Broker API   | [`dhanhq`](https://pypi.org/project/dhanhq/)                    |
| Tasks        | Celery + Redis (broker + result backend)                        |
| Version Ctrl | Git                                                             |

## Repository Layout

```
.
├── backend/                 # FastAPI + Celery + Strategies
│   ├── app/
│   │   ├── api/             # REST endpoints
│   │   ├── core/            # Config, security, logging
│   │   ├── db/              # SQLAlchemy session & engine
│   │   ├── models/          # ORM models
│   │   ├── schemas/         # Pydantic schemas
│   │   ├── services/        # DhanService, indicator engine
│   │   ├── strategies/      # Fitschen strategy classes
│   │   ├── backtest/        # Backtester engine
│   │   ├── tasks/           # Celery tasks (backtest + live loop)
│   │   └── main.py          # FastAPI entrypoint
│   ├── requirements.txt
│   ├── .env.example
│   └── celery_app.py
├── frontend/                # React + Vite + Tailwind
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── .env.example
├── .gitignore
└── README.md
```

## Trading Logic Implemented (Fitschen)

1. **Stock Cash/Options — Counter-Trend (Ch 5/6)**
   - Entry: `Close < 8-day Low` AND `Close > 70-day SMA` AND `20d StdDev > 3% of Price`
   - Exit: time-based (8 bars) OR Profit Target ₹300
   - Stop: 3 × 20-day StdDev from entry

2. **MCX Commodity — Trend-Following (Ch 5/6)**
   - Entry: `Close > 20-day High` AND `Close > 70-day SMA` AND `Avg Range > 0.5% of Price`
   - Exit: Trailing stop OR 3× StdDev catastrophic stop

3. **Index Option — Bar-Scoring (Ch 8)**
   - Score = f(Price StdDev weakness, Volume StdDev surge, rejection tails)
   - Entry: Buy ATM Call if `Bar Score > 1.5` (Top Bin logic)

4. **Money Management (Ch 11/14)**
   - Fixed-Risk Percentage: size position so SL hit = exactly **1% of current equity**

## Tradeability Filter

A strategy is considered tradeable only if **Gain-to-Pain Ratio (GtP) > 1.5**, where  
`GtP = Avg Annual Return / Max Drawdown`.

## Quick Start

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN, etc.
uvicorn app.main:app --reload --port 8000

# Worker (separate terminal)
celery -A celery_app worker --loglevel=info

# Frontend
cd ../frontend
npm install
cp .env.example .env.local
npm run dev
```

## Status

Built iteratively in 7 steps. See `worklog.md` for the build log.

> ⚠️ **Disclaimer:** This software is for educational/research purposes. Algorithmic trading in Indian markets involves significant risk. Test thoroughly on paper before going live. The authors are not responsible for any financial losses.
