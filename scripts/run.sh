#!/usr/bin/env bash
# run.sh — Start the rhino-mcp server.
#
# Usage:
#   ./scripts/run.sh                          # stdio mode (Claude Desktop default)
#   ./scripts/run.sh --http                   # HTTP mode, port 8765
#   ./scripts/run.sh --http --port 9000       # custom port
#   ./scripts/run.sh --bridge                 # force bridge mode (requires Rhino 8)
#   ./scripts/run.sh --standalone             # force standalone (rhino3dm only)
#   ./scripts/run.sh --connector              # HTTP + stateless + allow-external (claude.ai)
#   ./scripts/run.sh --connector --bridge     # bridge mode via claude.ai connector
#   ./scripts/run.sh --docker                 # run via docker compose
#   ./scripts/run.sh --help

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TRANSPORT="stdio"
PORT=8765
HOST="127.0.0.1"
FORCE_MODE=""
USE_DOCKER=false
CONNECTOR=false
LOG_LEVEL="${RHINO_MCP_LOG_LEVEL:-INFO}"

_usage() {
  cat <<'EOF'
Usage: run.sh [options]

Transport:
  --stdio             stdio transport (default; used by Claude Desktop)
  --http              Streamable HTTP transport on HOST:PORT

Network (HTTP mode):
  --port PORT         Listen port              [default: 8765]
  --host HOST         Listen host              [default: 127.0.0.1]

Mode:
  --bridge            Force bridge mode (requires Rhino 8 + RhinoMCPBridge.py)
  --standalone        Force standalone mode (rhino3dm only, no Rhino needed)

Connector (claude.ai remote MCP):
  --connector         Shorthand for --http --stateless --allow-external
                      Binds to 0.0.0.0 so a tunnel (ngrok/cloudflare) can reach it.
                      Combine with --bridge to expose all 130+ tools.

Other:
  --docker            Start via docker compose (HTTP, port 8765)

Environment variables:
  RHINO_HOST              Rhino bridge TCP host  [default: localhost]
  RHINO_PORT              Rhino bridge TCP port  [default: 4242]
  RHINO_MCP_LOG_LEVEL     Log level              [default: INFO]

claude.ai connector quick-start
────────────────────────────────
  # Standalone (no Rhino required):
  ./scripts/run.sh --connector --standalone

  # Bridge (all 130+ tools, Rhino 8 must be running with RhinoMCPBridge.py):
  ./scripts/run.sh --connector --bridge

  # Then expose with ngrok (separate terminal):
  ngrok http 8765

  # Add connector in claude.ai → Settings → Connectors → Add custom:
  #   URL: https://<ngrok-subdomain>.ngrok-free.app/mcp
EOF
}

for arg in "$@"; do
  case "$arg" in
    --http)       TRANSPORT="http" ;;
    --stdio)      TRANSPORT="stdio" ;;
    --bridge)     FORCE_MODE="bridge" ;;
    --standalone) FORCE_MODE="standalone" ;;
    --connector)  CONNECTOR=true; TRANSPORT="http"; HOST="0.0.0.0" ;;
    --docker)     USE_DOCKER=true ;;
    --help)       _usage; exit 0 ;;
    --port)       shift; PORT="$1" ;;
    --host)       shift; HOST="$1" ;;
    *)            echo "Unknown option: $arg  (run with --help)" >&2; exit 1 ;;
  esac
done

cd "$ROOT"

# ── docker ────────────────────────────────────────────────────────────────────
if [ "$USE_DOCKER" = true ]; then
  echo ">>> Starting rhino-mcp via docker compose (HTTP :8765)"
  RHINO_MCP_FORCE_MODE="${FORCE_MODE:-standalone}" \
    docker compose -f docker/docker-compose.yml up --build
  exit 0
fi

# ── native ────────────────────────────────────────────────────────────────────
export RHINO_MCP_LOG_LEVEL="$LOG_LEVEL"
[ -n "$FORCE_MODE" ] && export RHINO_MCP_FORCE_MODE="$FORCE_MODE"

if [ "$CONNECTOR" = true ]; then
  # In connector mode, a failed bridge connection falls back to standalone
  # so the server keeps running even when Rhino 8 is not yet started.
  export RHINO_MCP_BRIDGE_OPTIONAL=1

  echo ""
  echo "┌─ rhino-mcp connector mode ───────────────────────────────────────┐"
  echo "│  Transport : Streamable HTTP (stateless)                         │"
  echo "│  Binding   : 0.0.0.0:$PORT                                          │"
  echo "│  Mode      : ${FORCE_MODE:-auto-detect} (bridge optional)                    │"
  echo "│  Endpoint  : http://localhost:$PORT/mcp                             │"
  echo "│                                                                  │"
  echo "│  Bridge fallback: if Rhino 8 is not running, server starts in   │"
  echo "│  standalone mode. Restart after launching RhinoMCPBridge to     │"
  echo "│  enable all bridge tools.                                        │"
  echo "│                                                                  │"
  echo "│  To expose publicly:                                             │"
  echo "│    ngrok http $PORT                                                 │"
  echo "│    cloudflared tunnel --url http://localhost:$PORT                  │"
  echo "│                                                                  │"
  echo "│  Then add in claude.ai → Settings → Connectors:                 │"
  echo "│    https://<tunnel-host>/mcp                                     │"
  echo "└──────────────────────────────────────────────────────────────────┘"
  echo ""
  uv run rhino-mcp \
    --transport http \
    --host "$HOST" \
    --port "$PORT" \
    --stateless \
    --allow-external
elif [ "$TRANSPORT" = "http" ]; then
  echo ">>> Starting rhino-mcp [HTTP] on $HOST:$PORT  (mode: ${FORCE_MODE:-auto})"
  uv run rhino-mcp --transport http --host "$HOST" --port "$PORT"
else
  echo ">>> Starting rhino-mcp [stdio]  (mode: ${FORCE_MODE:-auto})"
  uv run rhino-mcp
fi
