#!/usr/bin/env bash
# start-monitor.sh — Launch the NightClaw local monitor runtime.
#
# Starts nightclaw_bridge --serve alongside the workspace so the Data Flow
# and Sessions monitor pages are fully functional: HTTP file serving,
# WebSocket fanout, ops socket ingest, and admin command routing via
# nightclaw-admin.sh. All wiring follows the specs in the existing repo.
#
# Usage:
#   bash scripts/start-monitor.sh [--bridge-port PORT] [--http-port PORT] [--token TOKEN] [--sessions-path PATH]
#
# Defaults:
#   --bridge-port   8787   WebSocket port (browser connects here for /ws + /sessions)
#   --http-port     8080   HTTP port (serve apps/monitor/*.html + nc_config.json)
#   --token         (none) Set NIGHTCLAW_BRIDGE_TOKEN for RW admin commands
#   --sessions-path PATH  Persist session data to this JSON file
#
# Default persistence path: $ROOT/sessions.json
# Pass --sessions-path to override it, or --sessions-path '' if you intentionally
# want ephemeral in-memory-only history for a test session.
#
# The monitor stops when this script is interrupted (Ctrl-C).
# The engine (nightclaw-ops.py) runs independently — this script only starts
# the monitor side. Run your cron worker/manager sessions separately.

set -euo pipefail

# ── Workspace detection (mirrors nightclaw-admin.sh) ────────────────────────
detect_root() {
    if [[ -n "${NIGHTCLAW_ROOT:-}" ]] && [[ -f "$NIGHTCLAW_ROOT/ACTIVE-PROJECTS.md" ]]; then
        echo "$NIGHTCLAW_ROOT"; return
    fi
    local dir="$PWD"
    while [[ "$dir" != "/" ]]; do
        if [[ -f "$dir/ACTIVE-PROJECTS.md" ]] && [[ -d "$dir/orchestration-os" ]]; then
            echo "$dir"; return
        fi
        dir="$(dirname "$dir")"
    done
    echo "ERROR: Cannot find NightClaw workspace. Run from workspace root or set NIGHTCLAW_ROOT." >&2
    exit 1
}

ROOT="$(detect_root)"
cd "$ROOT"

# ── Argument parsing ─────────────────────────────────────────────────────────
BRIDGE_PORT=8787
HTTP_PORT=8080
TOKEN="${NIGHTCLAW_BRIDGE_TOKEN:-}"
SESSIONS_PATH="__DEFAULT__"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --bridge-port)   BRIDGE_PORT="$2";   shift 2 ;;
        --http-port)     HTTP_PORT="$2";     shift 2 ;;
        --token)         TOKEN="$2";         shift 2 ;;
        --sessions-path) SESSIONS_PATH="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

# ── Pre-flight checks ────────────────────────────────────────────────────────
if ! python3 -c "import nightclaw_bridge" 2>/dev/null; then
    echo "ERROR: nightclaw_bridge not importable. Run: pip install -r requirements.txt" >&2
    exit 1
fi

# ── Export token for bridge privilege gating ─────────────────────────────────
if [[ -n "$TOKEN" ]]; then
    export NIGHTCLAW_BRIDGE_TOKEN="$TOKEN"
    echo "[nightclaw] Bridge token set — RW admin commands enabled."
else
    echo "[nightclaw] No bridge token — admin commands are read-only."
    echo "            Pass --token <secret> or set NIGHTCLAW_BRIDGE_TOKEN to enable RW."
fi

# ── Derive the ops socket path the bridge will use ───────────────────────────
# This mirrors the logic in nightclaw_common.socket_path so the startup
# banner shows the exact path — useful for debugging bridge↔engine wiring.
OPS_SOCK="${NIGHTCLAW_OPS_SOCK:-}"
if [[ -z "$OPS_SOCK" ]]; then
    OPS_SOCK="$(python3 -c "
from nightclaw_common.socket_path import ops_socket_path
import os, sys
ws = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
print(ops_socket_path(ws))
" "$ROOT" 2>/dev/null || echo "/tmp/nightclaw-ops.sock")"
fi

echo "[nightclaw] Starting local monitor runtime…"
echo "            Workspace : $ROOT"
echo "            HTTP      : http://127.0.0.1:${HTTP_PORT}/nightclaw-monitor.html"
echo "            WebSocket : ws://127.0.0.1:${BRIDGE_PORT}"
echo "            Ops socket: $OPS_SOCK"
echo ""
echo "            Open the monitor in your browser at:"
echo "            http://127.0.0.1:${HTTP_PORT}/nightclaw-monitor.html"
echo ""
echo "            Press Ctrl-C to stop."
echo ""

# ── Launch bridge ────────────────────────────────────────────────────────────
SESSIONS_ARG=()
if [[ "$SESSIONS_PATH" == "__DEFAULT__" ]]; then
    SESSIONS_PATH="$ROOT/sessions.json"
fi
if [[ -n "$SESSIONS_PATH" ]]; then
    SESSIONS_ARG=(--sessions-path "$SESSIONS_PATH")
    echo "[nightclaw] Sessions persisted to: $SESSIONS_PATH"
else
    echo "[nightclaw] Sessions history: in-memory only"
fi

exec python3 -m nightclaw_bridge \
    --serve \
    --workspace "$ROOT" \
    --bridge-port "$BRIDGE_PORT" \
    --http-port "$HTTP_PORT" \
    "${SESSIONS_ARG[@]}"
