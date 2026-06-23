# Runbook — Algorithmic Trading System

This runbook covers: setup, running locally, and pushing to GitHub.

---

## 1. Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.11+ | Backend |
| Node | 18+ | Frontend |
| Docker | 24+ | For PostgreSQL + Redis |
| Git | 2.30+ | Version control |
| DhanHQ account | — | Get `CLIENT_ID` + `ACCESS_TOKEN` from https://dhanhq.co |

---

## 2. Local Setup

### 2.1 Clone & enter

```bash
git clone <your-github-url> algo-trading-system
cd algo-trading-system
```

### 2.2 Start infra (PostgreSQL + Redis + Flower)

```bash
docker compose up -d
# Verify:
docker compose ps
# → trading_postgres  (healthy)
# → trading_redis     (healthy)
# → trading_flower    (running)
```

### 2.3 Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Create .env from template and fill in real values
cp .env.example .env
# Edit .env:
#   DHAN_CLIENT_ID=...
#   DHAN_ACCESS_TOKEN=...
#   DB_URL=postgresql+psycopg2://trader:traderpass@localhost:5432/trading_db
#   REDIS_URL=redis://localhost:6379/0
#   CELERY_BROKER_URL=redis://localhost:6379/1
#   CELERY_RESULT_BACKEND=redis://localhost:6379/2
#   JWT_SECRET=<long random string>

# Run the API (auto-creates tables + seeds admin user + 3 strategies)
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000/docs — you should see all endpoints.

### 2.4 Celery worker (separate terminal)

```bash
cd backend
source .venv/bin/activate
celery -A celery_app worker --loglevel=info
```

Optional — Flower dashboard for monitoring Celery:
```bash
# Already running via docker compose at http://localhost:5555
# Or run manually:
celery -A celery_app flower --port=5555
```

### 2.5 Frontend

```bash
cd frontend
npm install
cp .env.example .env.local        # VITE_API_BASE_URL=http://localhost:8000
npm run dev
```

Open http://localhost:5173 — login with `admin@trading.dev / admin123`.

---

## 3. First Trading Run (End-to-End)

1. **Sync historical data** for one instrument:
   ```bash
   curl -X POST http://localhost:8000/api/data/sync \
     -H "Authorization: Bearer <JWT>" \
     -H "Content-Type: application/json" \
     -d '{
       "security_id": "2885",
       "symbol": "RELIANCE",
       "segment": "NSE_EQ",
       "interval": "1D",
       "days": 365
     }'
   ```

2. **Run a backtest** via the UI:
   - Open http://localhost:5173/backtest
   - Select "Stock Counter-Trend (Fitschen Ch 5/6)"
   - Symbol: RELIANCE, Security ID: 2885
   - Start date: 1 year ago, End date: today
   - Click **Run Backtest**
   - Watch the status poll until `COMPLETED`
   - If GtP > 1.5, the strategy will be auto-marked tradeable

3. **Start paper trading**:
   - Open http://localhost:5173/live
   - Toggle on **Paper Mode** (recommended for first run)
   - Click **Start** on the strategy card
   - Watch the live logs console
   - The loop ticks every 30s during IST market hours (09:15–15:30 Mon–Fri)

4. **Stop trading**:
   - Click **Stop** on the strategy card, or
   - Click **STOP ALL** (panic button — squares off all positions)

---

## 4. Push to GitHub

### 4.1 Create the GitHub repo

Either:
- Web: https://github.com/new → name it `algo-trading-system` → **don't** initialize with README
- CLI: `gh repo create algo-trading-system --private --source=. --remote=origin`

### 4.2 Wire remote & push

From the repo root (`algo-trading-system/`):

```bash
# (Optional) review your history — should be 6 commits, one per step
git log --oneline

# Add the remote (skip if `gh repo create` already did it)
git remote add origin git@github.com:<YOUR_USERNAME>/algo-trading-system.git

# Verify
git remote -v

# Push main branch
git push -u origin main
```

### 4.3 Subsequent feature work

```bash
# Create a feature branch
git checkout -b feat/add-atr-stop

# ... make changes ...

git add .
git commit -m "feat: add ATR-based stop for MCX strategy"
git push -u origin feat/add-atr-stop

# Open PR on GitHub, get review, merge to main
```

---

## 5. Endpoint Cheat-Sheet

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/auth/login` | Login → JWT |
| POST | `/api/auth/register` | New user |
| GET  | `/api/auth/me` | Current user |
| GET  | `/api/strategies` | List 3 Fitschen strategies |
| GET  | `/api/strategies/{id}` | Strategy detail |
| POST | `/api/data/sync` | Sync 1-year OHLCV from DhanHQ |
| GET  | `/api/data/bars` | Load persisted bars |
| POST | `/api/backtest/start` | Dispatch backtest Celery task |
| GET  | `/api/backtest/status/{task_id}` | Poll backtest status + result |
| GET  | `/api/backtest/results` | Recent backtest results |
| POST | `/api/trading/start` | Dispatch live trading Celery task |
| POST | `/api/trading/stop` | Signal loop to stop (+ square off) |
| GET  | `/api/trading/active` | List currently-running live tasks |
| GET  | `/api/portfolio/status` | Equity, margin, open positions |
| GET  | `/health` | Backend health |

All `/api/*` endpoints (except `/api/auth/login` and `/api/auth/register`) require `Authorization: Bearer <JWT>`.

---

## 6. Troubleshooting

| Symptom | Likely cause / fix |
|---------|------------------------|
| `uvicorn` fails with `psycopg2.OperationalError` | Postgres not up. `docker compose up -d` then retry. |
| Celery worker shows `ConnectionError: redis` | Redis not up. Same fix. |
| `/api/data/sync` returns 500 with dhanhq error | `DHAN_CLIENT_ID` / `DHAN_ACCESS_TOKEN` invalid or expired. Regenerate from dhanhq.co. |
| Frontend 401 on every call | JWT expired. Logout + login again. |
| Backtest shows 0 trades | Insufficient warmup data — ensure ≥80 bars synced. Try increasing `days` in sync call. |
| Strategy marked "not tradeable" | GtP ≤ 1.5 on last backtest. Either tune parameters or stick to paper mode. |
| Live loop says "outside market hours" | IST 09:15–15:30 Mon–Fri only. To test on weekend, temporarily edit `_ist_market_open()` in `app/tasks/live_trading_tasks.py`. |

---

## 7. Safety Notes

- **Paper Mode is ON by default.** Live order placement via DhanHQ is stubbed as `LIVE_TODO` in `app/tasks/live_trading_tasks.py`. Wire it up only after thorough paper testing.
- **GtP gate is enforced.** Even if you flip paper mode off, the API rejects starting a strategy whose `is_tradeable=False`.
- **Secrets never committed.** `.env` and `.env.local` are in `.gitignore`. Don't override that.
- **TimeScaleDB hypertable.** After first `init_db()`, run once:
  ```sql
  -- connect to trading_db as trader
  CREATE EXTENSION IF NOT EXISTS timescaledb;
  SELECT create_hypertable('ohlcv_bars', 'timestamp', migrate_data => true);
  ```
