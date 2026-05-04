#!/usr/bin/env bash
# check-bridge.sh — Diagnose why rhino-mcp falls back to standalone mode.
#
# Checks every layer of the bridge detection stack and prints a clear
# PASS / FAIL / WARN verdict for each step.
#
# Usage:
#   ./scripts/check-bridge.sh
#   ./scripts/check-bridge.sh --tcp      # check TCP transport only
#   ./scripts/check-bridge.sh --verbose  # show raw output from ping

set -uo pipefail

TCP_ONLY=false
VERBOSE=false
for arg in "$@"; do
  case "$arg" in
    --tcp)     TCP_ONLY=true ;;
    --verbose) VERBOSE=true ;;
    --help)
      echo "Usage: $0 [--tcp] [--verbose]"
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

# ── Unix socket (macOS / Linux) ────────────────────────────────────────────────
if [ "$PLATFORM" != "Darwin" ] && [ "$PLATFORM" != "Linux" ]; then
  TCP_ONLY=true
fi

TRANSPORT_KIND="${RHINO_MCP_TRANSPORT_KIND:-}"
if [ "$TRANSPORT_KIND" = "tcp" ]; then
  TCP_ONLY=true
fi

echo ""
echo "1. Unix socket (macOS/Linux primary transport)"
if [ "$TCP_ONLY" = true ]; then
  echo "   $WARN  Skipped — TCP-only mode"
else
  SOCK_PATH="${RHINO_MCP_SOCKET:-}"
  if [ -z "$SOCK_PATH" ]; then
    XDG="${XDG_RUNTIME_DIR:-}"
    if [ -n "$XDG" ]; then
      SOCK_PATH="$XDG/rhino_mcp.sock"
    else
      SOCK_PATH="/tmp/rhino_mcp.sock"
    fi
  fi
  echo "   $INFO  Expected socket path: $SOCK_PATH"
  if [ -S "$SOCK_PATH" ]; then
    echo "   $PASS  Socket file exists"
    # Try to connect
    if uv run python -c "
import socket, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.connect('$SOCK_PATH')
    s.close()
    sys.exit(0)
except Exception as e:
    print('  connect error:', e, file=sys.stderr)
    sys.exit(1)
" 2>/dev/null; then
      echo "   $PASS  Socket is accepting connections"
    else
      echo "   $FAIL  Socket file exists but is NOT accepting connections"
      echo "          → rhino-mcp.py may have crashed or Rhino restarted."
      echo "          → In Rhino: _-RunPythonScript \"<path>/rhino-mcp.py\""
    fi
  else
    echo "   $FAIL  Socket file not found at $SOCK_PATH"
    echo "          → rhino-mcp.py is not running inside Rhino 8."
    echo ""
    echo "   Fix:"
    echo "     1. Open Rhino 8"
    echo "     2. Run in Rhino command line:"
    BRIDGE_PATH="$(python3 -c "import os; print(os.path.expanduser('~/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/rhino-mcp.py'))" 2>/dev/null || echo "~/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/rhino-mcp.py")"
    echo "          _-RunPythonScript \"$BRIDGE_PATH\""
    echo "     3. Look for \"[rhino-mcp] listening on unix://...\" in Rhino output"
  fi
fi

# ── TCP ────────────────────────────────────────────────────────────────────────
echo ""
echo "2. TCP transport ($RHINO_HOST:$RHINO_PORT)"
if uv run python -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.connect(('$RHINO_HOST', $RHINO_PORT))
    s.close()
    sys.exit(0)
except Exception as e:
    sys.exit(1)
" 2>/dev/null; then
  echo "   $PASS  TCP port is open"
else
  echo "   $WARN  TCP port $RHINO_PORT is not reachable"
  echo "          → Set RHINO_MCP_TRANSPORT_KIND=tcp in Rhino environment,"
  echo "            or use the default unix socket transport (macOS/Linux)."
fi

# ── Full ping via BridgeClient ─────────────────────────────────────────────────
echo ""
echo "3. JSON-RPC ping"
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
echo "4. Mode detection result"
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
  echo "          → rhino-mcp will start in BRIDGE mode (all tools available)"
else
  echo "   $WARN  $MODE"
  echo "          → rhino-mcp will start in STANDALONE mode (~50 tools)"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "$SEP"
if echo "$MODE" | grep -q "^bridge"; then
  echo "  Result: Bridge is reachable. Run:  ./scripts/run.sh --bridge"
else
  echo "  Result: Bridge is NOT reachable."
  echo ""
  echo "  Quick fix (macOS):"
  echo "    1. Open Rhino 8"
  echo "    2. Install bridge (once):  python rhino_plugin/install.py"
  echo "    3. In Rhino command line:"
  BRIDGE_PATH_2="$(python3 -c "import os; print(os.path.expanduser('~/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/rhino-mcp.py'))" 2>/dev/null || echo "~/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/rhino-mcp.py")"
  echo "         _-RunPythonScript \"$BRIDGE_PATH_2\""
  echo "    4. Confirm: \"[rhino-mcp] listening on unix://...\" appears in output"
  echo "    5. Re-run this script to verify"
  echo ""
  echo "  If Rhino is running but bridge still fails, try TCP mode:"
  echo "    RHINO_MCP_TRANSPORT_KIND=tcp ./scripts/check-bridge.sh --tcp"
fi
echo "$SEP"
