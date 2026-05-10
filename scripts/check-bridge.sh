#!/usr/bin/env bash
# check-bridge.sh — Diagnose why rhino-mcp falls back to standalone mode.
#
# Walks the bridge detection stack (TCP reachability → JSON-RPC ping →
# detect_mode result) and prints a PASS / FAIL / WARN verdict for each
# step.  The current rhino-mcp bridge is a TCP transport implemented by
# the C# `.rhp` plug-in loaded inside Rhino 8 — there is no
# `rhino-mcp.py` script anymore, and the macOS / Linux Unix-socket
# transport was retired in v0.4.
#
# Usage:
#   ./scripts/check-bridge.sh
#   ./scripts/check-bridge.sh --verbose

set -uo pipefail

VERBOSE=false
for arg in "$@"; do
  case "$arg" in
    --verbose) VERBOSE=true ;;
    --help)
      echo "Usage: $0 [--verbose]"
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

PASS="[PASS]"
FAIL="[FAIL]"
WARN="[WARN]"
INFO="[INFO]"
SEP="────────────────────────────────────────────────────────"

echo "$SEP"
echo "  rhino-mcp bridge diagnostic"
echo "$SEP"
echo ""

# ── Platform ──────────────────────────────────────────────────────────────────
PLATFORM="$(uname -s)"
echo "$INFO  Platform : $PLATFORM"

RHINO_HOST="${RHINO_HOST:-localhost}"
RHINO_PORT="${RHINO_PORT:-4242}"
echo "$INFO  TCP target : $RHINO_HOST:$RHINO_PORT"

# ── TCP reachability ──────────────────────────────────────────────────────────
echo ""
echo "1. TCP transport ($RHINO_HOST:$RHINO_PORT)"
if uv run python -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.connect(('$RHINO_HOST', $RHINO_PORT))
    s.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
  echo "   $PASS  TCP port is open"
else
  echo "   $FAIL  TCP port $RHINO_PORT is not reachable"
  echo "          → Open Rhino 8 with the rhino-mcp.rhp C# plug-in loaded."
  echo "          → Install the plug-in via the Rhino package manager,"
  echo "            or build locally: ./scripts/build-plugin.sh --release"
fi

# ── Full ping via BridgeClient ─────────────────────────────────────────────────
echo ""
echo "2. JSON-RPC ping"
PING_OUTPUT=$(uv run python -c "
import os, sys
os.environ.pop('RHINO_MCP_FORCE_MODE', None)
os.environ.pop('RHINO_MCP_BRIDGE_OPTIONAL', None)
from rhino_mcp.bridge.rhino_connection import BridgeClient
client = BridgeClient.auto(timeout=3.0)
if client is None:
    print('FAIL')
    sys.exit(1)
try:
    pong = client.call('rhino.ping', {})
    print('PASS')
    print('rhino:', pong.get('rhino'))
    print('grasshopper:', pong.get('grasshopper'))
    print('bridge_version:', pong.get('bridge_version'))
    print('protocol_version:', pong.get('protocol_version'))
except Exception as e:
    print('FAIL:', e)
    sys.exit(1)
" 2>/dev/null)

if echo "$PING_OUTPUT" | grep -q "^PASS"; then
  echo "   $PASS  Bridge responded to ping"
  echo "$PING_OUTPUT" | grep -v "^PASS" | while IFS= read -r line; do
    echo "          $line"
  done
else
  echo "   $FAIL  Bridge did not respond"
  [ "$VERBOSE" = true ] && echo "          $PING_OUTPUT"
fi

# ── Mode detection summary ────────────────────────────────────────────────────
echo ""
echo "3. Mode detection result"
MODE=$(uv run python -c "
import os
os.environ.pop('RHINO_MCP_FORCE_MODE', None)
os.environ.pop('RHINO_MCP_BRIDGE_OPTIONAL', None)
from rhino_mcp.bridge.rhino_connection import detect_mode
mode, client = detect_mode()
print(mode.value, 'with-client' if client else 'no-client')
" 2>/dev/null)

if echo "$MODE" | grep -q "^bridge"; then
  echo "   $PASS  $MODE"
  echo "          → rhino-mcp will start in BRIDGE mode (~235 tools)."
else
  echo "   $WARN  $MODE"
  echo "          → rhino-mcp will start in STANDALONE mode (~234 tools)."
  echo "          → v0.5.1+: bridge tools auto-promote on first call once"
  echo "            the rhino-mcp.rhp plug-in becomes reachable; no MCP"
  echo "            server restart is required."
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "$SEP"
if echo "$MODE" | grep -q "^bridge"; then
  echo "  Result: Bridge is reachable. Run:  ./scripts/run.sh --bridge"
else
  echo "  Result: Bridge is NOT reachable."
  echo ""
  echo "  Quick fix:"
  echo "    1. Open Rhino 8."
  echo "    2. Install the rhino-mcp.rhp plug-in"
  echo "       — package manager (yak), or build locally:"
  echo "         ./scripts/build-plugin.sh --release"
  echo "    3. Inside Rhino, type:  _McpInstall"
  echo "       (configures Claude Desktop and verifies the launcher.)"
  echo "    4. Re-run this script."
fi
echo "$SEP"
