#!/usr/bin/env bash
# ============================================================================
# setup.sh — One-shot environment setup for glm_tradinghub on WSL2 Ubuntu
# ============================================================================
# Run with:
#   cd ~/glm_tradinghub   (or wherever you cloned the repo)
#   chmod +x scripts/setup.sh
#   ./scripts/setup.sh
#
# What it does:
#   Phase 0: Install system packages (Python 3.11, Node 20, Docker deps, build tools)
#   Phase 1: Start Docker infra (PostgreSQL+TimeScaleDB, Redis, Flower)
#   Phase 2: Create Python venv, install backend deps, write backend/.env
#   Phase 3: Install frontend deps
#   Phase 4: Run DB migrations (create tables) + seed admin user + 3 strategies
#   Phase 5: Smoke-test the API (curl /health)
#   Phase 6: Print next-step instructions
#
# Safe to re-run — every step is idempotent.
# ============================================================================

set -Eeuo pipefail
IFS=$'\n\t'

# ----------------------- pretty logging -------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $*"; }
info() { echo -e "${BLUE}[i]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*" >&2; }
step() { echo -e "\n${BOLD}${CYAN}════════════════════════════════════════════════════════════${NC}"; \
         echo -e "${BOLD}${CYAN}  PHASE $1: $2${NC}"; \
         echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════${NC}\n"; }

trap 'err "Failed on line $LINENO. Command: $BASH_COMMAND"; exit 1' ERR

# ----------------------- detect repo root -----------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"
info "Repo root: $REPO_ROOT"

# Sanity check
if [[ ! -f "docker-compose.yml" || ! -d "backend" || ! -d "frontend" ]]; then
    err "This doesn't look like the glm_tradinghub repo root."
    err "Expected: docker-compose.yml, backend/, frontend/"
    err "Found in: $REPO_ROOT"
    exit 1
fi

# ============================================================================
step 0 "Install system packages (Python 3.11, Node 20, build tools)"
# ============================================================================

# Only install if apt is available (i.e., we're in Ubuntu/Debian WSL2)
if command -v apt-get >/dev/null 2>&1; then
    info "Updating apt and installing base packages…"
    sudo apt-get update -y
    sudo apt-get install -y \
        ca-certificates curl git build-essential \
        python3.11 python3.11-venv python3.11-dev \
        libpq-dev libssl-dev libffi-dev \
        postgresql-client redis-tools \
        < /dev/null

    # Node 20 via NodeSource
    if ! command -v node >/dev/null 2>&1 || [[ "$(node --version 2>/dev/null | cut -d. -f1 | tr -d v)" -lt 18 ]]; then
        info "Installing Node 20 LTS via NodeSource…"
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
        sudo apt-get install -y nodejs < /dev/null
    fi
else
    warn "apt-get not found — skipping system package installation."
    warn "Make sure Python 3.11+, Node 18+, and Docker are installed manually."
fi

# Verify
log "Python: $(python3 --version 2>&1)"
log "Node:   $(node --version 2>&1)"
log "npm:    $(npm --version 2>&1)"

# ============================================================================
step 1 "Start Docker infrastructure (PostgreSQL, Redis, Flower)"
# ============================================================================

if ! command -v docker >/dev/null 2>&1; then
    err "Docker not found. Install Docker Desktop for Windows with WSL2 integration:"
    err "  https://www.docker.com/products/docker-desktop/"
    err "Enable WSL2 integration in Docker Desktop → Settings → Resources → WSL Integration."
    exit 1
fi

info "Starting docker compose stack…"
docker compose up -d

# Wait for postgres to be healthy
info "Waiting for PostgreSQL to become healthy (max 60s)…"
for i in $(seq 1 30); do
    status=$(docker inspect --format='{{.State.Health.Status}}' trading_postgres 2>/dev/null || echo "missing")
    if [[ "$status" == "healthy" ]]; then
        log "PostgreSQL healthy"
        break
    fi
    sleep 2
    if [[ $i -eq 30 ]]; then
        err "PostgreSQL failed to become healthy in 60s"
        docker compose logs --tail=20 postgres
        exit 1
    fi
done

# Wait for redis
info "Waiting for Redis…"
for i in $(seq 1 15); do
    if docker exec trading_redis redis-cli ping 2>/dev/null | grep -q PONG; then
        log "Redis responding to PING"
        break
    fi
    sleep 1
    if [[ $i -eq 15 ]]; then
        err "Redis not responding"
        docker compose logs --tail=20 redis
        exit 1
    fi
done

log "Docker stack is up:"
docker compose ps

# ============================================================================
step 2 "Python venv + backend dependencies + .env"
# ============================================================================

cd "$REPO_ROOT/backend"

if [[ ! -d ".venv" ]]; then
    info "Creating Python 3.11 virtualenv…"
    python3.11 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

info "Upgrading pip + installing backend requirements…"
pip install --upgrade pip wheel setuptools
pip install -r requirements.txt

# Write backend/.env if missing or if user passed creds via env
ENV_FILE="$REPO_ROOT/backend/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    info "Writing backend/.env from .env.example…"
    cp .env.example .env

    # If user provided DHAN creds via env, inject them
    if [[ -n "${DHAN_CLIENT_ID:-}" ]]; then
        sed -i "s|^DHAN_CLIENT_ID=.*|DHAN_CLIENT_ID=${DHAN_CLIENT_ID}|" .env
    fi
    if [[ -n "${DHAN_ACCESS_TOKEN:-}" ]]; then
        sed -i "s|^DHAN_ACCESS_TOKEN=.*|DHAN_ACCESS_TOKEN=${DHAN_ACCESS_TOKEN}|" .env
    fi

    # Generate a random JWT_SECRET
    JWT_RAND=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
    sed -i "s|^JWT_SECRET=.*|JWT_SECRET=${JWT_RAND}|" .env

    warn "backend/.env created with defaults."
    warn "Edit it now to add your real DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN."
    warn "  → $ENV_FILE"
else
    log "backend/.env already exists — leaving it untouched"
fi

cd "$REPO_ROOT"

# ============================================================================
step 3 "Frontend dependencies"
# ============================================================================

cd "$REPO_ROOT/frontend"

if [[ ! -f ".env.local" ]]; then
    info "Writing frontend/.env.local from .env.example…"
    cp .env.example .env.local
fi

info "Installing npm packages (this can take 1-2 min)…"
npm install

log "Frontend deps installed"

cd "$REPO_ROOT"

# ============================================================================
step 4 "Create DB tables + seed admin user + 3 strategies"
# ============================================================================

cd "$REPO_ROOT/backend"
source .venv/bin/activate

info "Creating DB tables + seeding admin user + strategies…"
python3 -c "from app.db.session import init_db; init_db()"
python3 -c "from app.core.bootstrap import run_bootstrap; run_bootstrap()"

# Verify the seed
info "Verifying seed…"
python3 <<'EOF'
from app.db.session import SessionLocal
from app.models.user import User
from app.models.strategy import Strategy

db = SessionLocal()
users = db.query(User).count()
strats = db.query(Strategy).count()
print(f"  Users:      {users}  (expected ≥1)")
print(f"  Strategies: {strats}  (expected 3)")
for s in db.query(Strategy).order_by(Strategy.id).all():
    print(f"    [{s.id}] {s.slug}  ({s.strategy_type})")
db.close()
EOF

cd "$REPO_ROOT"

# ============================================================================
step 5 "Smoke-test the FastAPI server"
# ============================================================================

cd "$REPO_ROOT/backend"
source .venv/bin/activate

info "Starting FastAPI on :8000 in background for smoke test…"
# Start uvicorn, give it 5s, curl /health, then kill it
uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning &
UVICORN_PID=$!
sleep 5

echo ""
info "Health check:"
if curl -sS http://127.0.0.1:8000/health; then
    echo ""
    log "FastAPI is responding"
else
    err "FastAPI health check failed"
fi

echo ""
info "Strategies endpoint (unauth should return 401):"
curl -sS -o /dev/null -w "  HTTP %{http_code} (expected 401)\n" http://127.0.0.1:8000/api/strategies

echo ""
info "Stopping smoke-test uvicorn…"
kill $UVICORN_PID 2>/dev/null || true
wait $UVICORN_PID 2>/dev/null || true

cd "$REPO_ROOT"

# ============================================================================
step 6 "Done — next steps"
# ============================================================================

cat <<EOF

${BOLD}${GREEN}═══════════════════════════════════════════════════════════════
  ✅  SETUP COMPLETE
═══════════════════════════════════════════════════════════════${NC}

${BOLD}Infrastructure (running in Docker):${NC}
  • PostgreSQL+TimeScaleDB  →  localhost:5432   (user: trader / pass: traderpass / db: trading_db)
  • Redis                    →  localhost:6379
  • Flower (Celery monitor)  →  http://localhost:5555

${BOLD}Backend (start in a terminal):${NC}
  cd ~/glm_tradinghub/backend
  source .venv/bin/activate
  uvicorn app.main:app --reload --port 8000
  → API:    http://localhost:8000
  → Docs:   http://localhost:8000/docs

${BOLD}Celery worker (separate terminal):${NC}
  cd ~/glm_tradinghub/backend
  source .venv/bin/activate
  celery -A celery_app worker --loglevel=info

${BOLD}Frontend (separate terminal):${NC}
  cd ~/glm_tradinghub/frontend
  npm run dev
  → http://localhost:5173
  → Login: admin@trading.local / admin123

${BOLD}Before trading:${NC}
  Edit backend/.env and fill in your real DhanHQ credentials:
    DHAN_CLIENT_ID=...
    DHAN_ACCESS_TOKEN=...
  (You can get them from https://dhanhq.co — Settings → API)

${BOLD}Optional — convert ohlcv_bars to a TimeScaleDB hypertable:${NC}
  docker exec trading_postgres psql -U trader -d trading_db -c \\
    "CREATE EXTENSION IF NOT EXISTS timescaledb; \\
     SELECT create_hypertable('ohlcv_bars', 'timestamp', migrate_data => true);"

${YELLOW}⚠️  SECURITY: revoke the GitHub PAT you used to push (https://github.com/settings/tokens)${NC}

EOF
