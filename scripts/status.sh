#!/usr/bin/env bash
# ============================================================================
# status.sh — Check what's running + health of all services
# ============================================================================
# Quick health check for the algo trading system.
# Shows: which services are up, their ports, health endpoints, and config.
#
# Usage:
#   ./scripts/status.sh
# ============================================================================
set -Eeuo pipefail
IFS=$'\n\t'

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $*"; }
down() { echo -e "  ${RED}✗${NC} $*"; }
warn() { echo -e "  ${YELLOW}!${NC} $*"; }
header() { echo -e "\n${BOLD}${CYAN}════════════════════════════════════════════════════════════${NC}"; \
           echo -e "${BOLD}${CYAN}  $1${NC}"; \
           echo -e "${BOLD}${CYAN}════════════════════════════════════════════════════════════${NC}"; }

# ----------------------- check by port --------------------------------------
check_port() {
    local port=$1 name=$2
    if command -v ss >/dev/null 2>&1; then
        if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
            ok "$name — port $port is listening"
            return 0
        else
            down "$name — port $port not listening"
            return 1
        fi
    fi
    warn "Cannot check port $port (ss not available)"
    return 1
}

check_http() {
    local url=$1 name=$2
    if curl -sS --max-time 3 "$url" >/dev/null 2>&1; then
        ok "$name — $url responds"
        return 0
    else
        down "$name — $url not responding"
        return 1
    fi
}

# ----------------------- main -----------------------------------------------
header "ALGO TRADING SYSTEM — STATUS"
echo ""

# Docker
echo -e "${BOLD}Docker containers:${NC}"
for svc in trading_postgres trading_redis trading_flower; do
    status=$(docker inspect --format='{{.State.Status}}' "$svc" 2>/dev/null || echo "missing")
    if [[ "$status" == "running" ]]; then
        health=$(docker inspect --format='{{.State.Health.Status}}' "$svc" 2>/dev/null || echo "n/a")
        ok "$svc — running (health: $health)"
    else
        down "$svc — $status"
    fi
done
echo ""

# Services
echo -e "${BOLD}Application services:${NC}"
api_up=false
worker_up=false
web_up=false
check_port 8000 "FastAPI backend" && api_up=true
check_port 5173 "Frontend (Vite)" && web_up=true

# Celery: check by looking for the process
if pgrep -f "celery.*celery_app" >/dev/null 2>&1; then
    ok "Celery worker — process running ($(pgrep -f 'celery.*celery_app' | wc -l) PIDs)"
    worker_up=true
else
    down "Celery worker — not running"
fi
echo ""

# HTTP health checks
echo -e "${BOLD}HTTP health checks:${NC}"
if $api_up; then
    check_http http://localhost:8000/health "FastAPI /health"
fi
if $worker_up; then
    check_http http://localhost:5555 "Flower dashboard"
fi
if $web_up; then
    check_http http://localhost:5173 "Frontend"
fi
echo ""

# Config summary
echo -e "${BOLD}Configuration:${NC}"
if [[ -f backend/.env ]]; then
    # Source the .env to read key settings (without printing secrets)
    set -a
    # shellcheck disable=SC1091
    source backend/.env 2>/dev/null || true
    set +a
    if [[ "${LIVE_TRADING_ENABLED:-false}" == "true" ]]; then
        warn "LIVE TRADING IS ENABLED — real orders will be placed"
    else
        ok "LIVE_TRADING_ENABLED=false (paper mode only)"
    fi
    if [[ "${TELEGRAM_ENABLED:-false}" == "true" ]]; then
        ok "Telegram alerts ENABLED (chat_id: ${TELEGRAM_CHAT_ID:-not set})"
    else
        ok "Telegram alerts disabled"
    fi
    ok "Max daily loss: ₹${MAX_DAILY_LOSS_INR:-50000}"
else
    down "backend/.env not found"
fi
echo ""

# Quick summary
echo -e "${BOLD}Summary:${NC}"
all_ok=true
$api_up || { down "FastAPI backend is down"; all_ok=false; }
$worker_up || { down "Celery worker is down"; all_ok=false; }
$web_up || { down "Frontend is down"; all_ok=false; }

if $all_ok; then
    echo ""
    ok "🚀 ALL SYSTEMS GO — open http://localhost:5173"
else
    echo ""
    warn "Some services are down. Run: ./scripts/start.sh"
fi
echo ""
