#!/usr/bin/env bash
# ============================================================================
# restart.sh — Restart all services (stop + start)
# ============================================================================
# Useful when you've changed backend/.env or pulled new code.
#
# Usage:
#   ./scripts/restart.sh
# ============================================================================
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Restarting all services…"
"$SCRIPT_DIR/stop.sh" || true
sleep 2
exec "$SCRIPT_DIR/start.sh"
