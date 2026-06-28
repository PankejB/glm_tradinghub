#!/usr/bin/env bash
# ============================================================================
# start.sh — One-click launcher for the algo trading system
# ============================================================================
# Starts all 3 services in ONE terminal with color-coded prefixed logs:
#   [API]     — FastAPI backend (port 8000)
#   [WORKER]  — Celery worker
#   [WEB]     — Vite dev server (port 5173)
#
# Usage:
#   ./scripts/start.sh          # start everything
#   ./scripts/start.sh --check  # check prerequisites only (don't start)
#
# Ctrl+C in this terminal will gracefully stop ALL services.
# Logs are also persisted to logs/{api,worker,web}.log
#
# Prerequisites: run scripts/setup.sh once first.
# ============================================================================
set -Eeuo pipefail
IFS=$'\n\t'

# ----------------------- pretty logging -------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
# Prefix colors (for each service)
API_C='\033[0;35m'     # purple
WORKER_C='\033[0;36m'  # cyan
WEB_C='\033[0;33m'     # orange

log()  { echo -e "${GREEN}[✓]${NC} $*"; }
info() { echo -e "${BLUE}[i]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*" >&2; }
header() { echo -e "\n${BOLD}${CYAN}════════════════════════════════════════════════════════════${NC}"; \
           echo -e "${BOLD}${CYAN}  $1${NC}"; \
           echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════${NC}\n"; }

# ----------------------- detect repo root -----------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# ----------------------- preflight checks -----------------------------------
header "PREFLIGHT CHECKS"

# 1. Backend venv exists?
if [[ ! -d "backend/.venv" ]]; then
    err "backend/.venv not found. Run scripts/setup.sh first."
    exit 1
fi
log "Backend venv found"

# 2. Frontend node_modules exists?
if [[ ! -d "frontend/node_modules" ]]; then
    err "frontend/node_modules not found. Run scripts/setup.sh first."
    exit 1
fi
log "Frontend node_modules found"

# 3. Docker containers running?
if ! docker compose ps --format json 2>/dev/null | head -1 | grep -q "running"; then
    warn "Docker containers don't appear to be running. Starting them…"
    docker compose up -d
    sleep 5
fi

# Verify postgres + redis are healthy
for i in $(seq 1 15); do
    pg_status=$(docker inspect --format='{{.State.Health.Status}}' trading_postgres 2>/dev/null || echo "missing")
    if [[ "$pg_status" == "healthy" ]]; then
        log "PostgreSQL healthy"
        break
    fi
    sleep 2
    if [[ $i -eq 15 ]]; then
        err "PostgreSQL not healthy. Run: docker compose up -d"
        exit 1
    fi
done

if docker exec trading_redis redis-cli ping 2>/dev/null | grep -q PONG; then
    log "Redis responding"
else
    err "Redis not responding. Run: docker compose up -d"
    exit 1
fi

# 4. Backend .env exists?
if [[ ! -f "backend/.env" ]]; then
    err "backend/.env not found. Run scripts/setup.sh first."
    exit 1
fi
log "backend/.env found"

# 5. Is anything already running on our ports?
check_port() {
    local port=$1 name=$2
    if command -v ss >/dev/null 2>&1; then
        if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
            warn "Port ${port} (${name}) is already in use — service may already be running"
            return 1
        fi
    fi
    return 0
}
check_port 8000 "API" || true
check_port 5173 "frontend" || true

# If --check flag, exit here
if [[ "${1:-}" == "--check" ]]; then
    log "All prerequisites OK. Run without --check to start services."
    exit 0
fi

# ----------------------- prepare log directory ------------------------------
mkdir -p logs
> logs/api.log
> logs/worker.log
> logs/web.log

# ----------------------- trap Ctrl+C ----------------------------------------
PIDS=()
cleanup() {
    echo ""
    header "SHUTTING DOWN"
    info "Stopping all services (Ctrl+C again to force-kill)…"
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    # Wait up to 5s for graceful shutdown
    for i in $(seq 1 5); do
        any_alive=false
        for pid in "${PIDS[@]}"; do
            if kill -0 "$pid" 2>/dev/null; then any_alive=true; break; fi
        done
        if ! $any_alive; then break; fi
        sleep 1
    done
    # Force kill if still alive
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            warn "Force-killing PID $pid"
            kill -9 "$pid" 2>/dev/null || true
        fi
    done
    log "All services stopped. Logs saved to logs/"
    exit 0
}
trap cleanup SIGINT SIGTERM

# ----------------------- launch services ------------------------------------
header "STARTING SERVICES"

# --- 1. FastAPI backend ---
info "Starting FastAPI backend on :8000…"
(
    cd backend
    source .venv/bin/activate
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload 2>&1
) | while IFS= read -r line; do
    echo -e "${API_C}[API]${NC} $line" | tee -a logs/api.log
done &
PIDS+=($!)

# --- 2. Celery worker ---
info "Starting Celery worker…"
(
    cd backend
    source .venv/bin/activate
    exec celery -A celery_app worker --loglevel=info --concurrency=2 2>&1
) | while IFS= read -r line; do
    echo -e "${WORKER_C}[WORKER]${NC} $line" | tee -a logs/worker.log
done &
PIDS+=($!)

# Give the API a 3-second head start before launching frontend
sleep 3

# --- 3. Frontend (Vite) ---
info "Starting frontend on :5173…"
(
    cd frontend
    exec npm run dev 2>&1
) | while IFS= read -r line; do
    echo -e "${WEB_C}[WEB]${NC} $line" | tee -a logs/web.log
done &
PIDS+=($!)

# ----------------------- wait for services to be ready ----------------------
header "WAITING FOR SERVICES"

# Wait for API
info "Waiting for FastAPI on :8000…"
for i in $(seq 1 20); do
    if curl -sS http://localhost:8000/health >/dev/null 2>&1; then
        log "FastAPI is ready"
        break
    fi
    sleep 1
    if [[ $i -eq 20 ]]; then
        warn "FastAPI didn't respond in 20s — check logs/api.log"
    fi
done

# Wait for frontend
info "Waiting for Vite on :5173…"
for i in $(seq 1 20); do
    if curl -sS http://localhost:5173 >/dev/null 2>&1; then
        log "Frontend is ready"
        break
    fi
    sleep 1
    if [[ $i -eq 20 ]]; then
        warn "Frontend didn't respond in 20s — check logs/web.log"
    fi
done

# ----------------------- success banner -------------------------------------
header "🚀 ALL SERVICES RUNNING"

cat <<EOF
${BOLD}Services:${NC}
  ${API_C}[API]${NC}     FastAPI + Swagger docs    →  http://localhost:8000
  ${WORKER_C}[WORKER]${NC}  Celery worker              →  http://localhost:5555 (Flower)
  ${WEB_C}[WEB]${NC}     React frontend             →  http://localhost:5173

${BOLD}Login:${NC}  admin@trading.dev / admin123

${BOLD}Logs:${NC}   tail -f logs/api.log logs/worker.log logs/web.log

${BOLD}Stop:${NC}    Press ${BOLD}Ctrl+C${NC} in this terminal (graceful)
         or run: ./scripts/stop.sh

${YELLOW}⚠️  Live trading is ${BOLD}OFF${NC}${YELLOW} by default. To enable real orders:
   1. Edit backend/.env → set LIVE_TRADING_ENABLED=true
   2. Run ./scripts/stop.sh && ./scripts/start.sh${NC}

EOF

# ----------------------- keep foreground (wait for children) ----------------
info "Press Ctrl+C to stop all services"
wait
