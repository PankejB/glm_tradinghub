#!/usr/bin/env bash
# ============================================================================
# stop.sh — Gracefully stop all algo trading services
# ============================================================================
# Stops (in this order):
#   1. Celery worker (so no new tasks are picked up)
#   2. FastAPI backend
#   3. Vite frontend
#   4. Optional: Docker containers (with --docker flag)
#
# Usage:
#   ./scripts/stop.sh             # stop the 3 app services
#   ./scripts/stop.sh --docker    # also stop postgres/redis/flower
#   ./scripts/stop.sh --force     # kill -9 anything that won't stop gracefully
# ============================================================================
set -Eeuo pipefail
IFS=$'\n\t'

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $*"; }
info() { echo -e "${BLUE}[i]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*" >&2; }

FORCE=false
STOP_DOCKER=false
if [[ "${1:-}" == "--force" ]]; then FORCE=true; fi
if [[ "${1:-}" == "--docker" ]]; then STOP_DOCKER=true; fi

# ------------------------------------------------------------------
#  Kill by port (finds the listening process and kills it)
# ------------------------------------------------------------------
kill_port() {
    local port=$1 name=$2
    local pids
    # Try ss first (most common on modern Linux), fall back to lsof
    if command -v ss >/dev/null 2>&1; then
        pids=$(ss -tlnp 2>/dev/null | grep ":${port} " | grep -oP 'pid=\K[0-9]+' | sort -u || true)
    elif command -v lsof >/dev/null 2>&1; then
        pids=$(lsof -ti :${port} 2>/dev/null || true)
    fi
    if [[ -z "$pids" ]]; then
        log "$name (port $port): not running"
        return 0
    fi
    info "Stopping $name (port $port, PIDs: $(echo $pids | tr '\n' ' '))"
    if $FORCE; then
        for p in $pids; do kill -9 "$p" 2>/dev/null || true; done
    else
        for p in $pids; do kill "$p" 2>/dev/null || true; done
        # Wait up to 5s for graceful shutdown
        for i in $(seq 1 5); do
            still=$(ss -tlnp 2>/dev/null | grep ":${port} " || true)
            if [[ -z "$still" ]]; then break; fi
            sleep 1
        done
        # Force kill if still alive
        still=$(ss -tlnp 2>/dev/null | grep ":${port} " | grep -oP 'pid=\K[0-9]+' | sort -u || true)
        if [[ -n "$still" ]]; then
            warn "$name didn't stop gracefully — force killing"
            for p in $still; do kill -9 "$p" 2>/dev/null || true; done
        fi
    fi
    log "$name stopped"
}

# ------------------------------------------------------------------
#  Kill celery workers by pattern
# ------------------------------------------------------------------
kill_celery() {
    local pids
    pids=$(pgrep -f "celery.*celery_app" 2>/dev/null || true)
    if [[ -z "$pids" ]]; then
        log "Celery worker: not running"
        return 0
    fi
    info "Stopping Celery worker (PIDs: $(echo $pids | tr '\n' ' '))"
    # Try celery's own graceful shutdown command first
    if ! $FORCE; then
        cd backend 2>/dev/null && source .venv/bin/activate 2>/dev/null && \
            celery -A celery_app control shutdown 2>/dev/null || true
        sleep 3
    fi
    # Kill any remaining
    pids=$(pgrep -f "celery.*celery_app" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        if $FORCE; then
            for p in $pids; do kill -9 "$p" 2>/dev/null || true; done
        else
            for p in $pids; do kill "$p" 2>/dev/null || true; done
            sleep 2
            pids=$(pgrep -f "celery.*celery_app" 2>/dev/null || true)
            if [[ -n "$pids" ]]; then
                warn "Celery didn't stop gracefully — force killing"
                for p in $pids; do kill -9 "$p" 2>/dev/null || true; done
            fi
        fi
    fi
    log "Celery worker stopped"
}

# ------------------------------------------------------------------
#  Stop docker containers
# ------------------------------------------------------------------
stop_docker() {
    info "Stopping Docker containers (Postgres, Redis, Flower)…"
    docker compose down 2>/dev/null
    log "Docker containers stopped"
}

# ------------------------------------------------------------------
#  Main
# ------------------------------------------------------------------
echo ""
echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${CYAN}  STOPPING SERVICES${NC}"
echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════${NC}"
echo ""

# Kill the start.sh parent script first (so it doesn't respawn children)
START_PIDS=$(pgrep -f "scripts/start.sh" 2>/dev/null || true)
if [[ -n "$START_PIDS" ]]; then
    info "Stopping start.sh launcher (PIDs: $(echo $START_PIDS | tr '\n' ' '))"
    for p in $START_PIDS; do kill "$p" 2>/dev/null || true; done
    sleep 1
fi

# Stop services in reverse order: frontend → celery → api
kill_port 5173 "Frontend (Vite)"
kill_celery
kill_port 8000 "FastAPI backend"

if $STOP_DOCKER; then
    stop_docker
fi

echo ""
log "All services stopped."
echo ""
info "To restart: ./scripts/start.sh"
echo ""
