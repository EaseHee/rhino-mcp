#!/usr/bin/env bash
# install.sh — Install rhino-mcp and its dependencies.
#
# Usage:
#   ./scripts/install.sh           # production install
#   ./scripts/install.sh --dev     # include dev extras (pytest, ruff, mypy)
#   ./scripts/install.sh --help

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEV=false

# ── argument parsing ──────────────────────────────────────────────────────────
for arg in "$@"; do
  case "$arg" in
    --dev)  DEV=true ;;
    --help)
      echo "Usage: $0 [--dev]"
      echo ""
      echo "  --dev   Install dev extras: pytest, ruff, mypy, pytest-cov, pytest-asyncio"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg  (run with --help for usage)" >&2
      exit 1
      ;;
  esac
done

# ── prerequisites ─────────────────────────────────────────────────────────────
check_cmd() {
  if ! command -v "$1" &>/dev/null; then
    echo "ERROR: '$1' not found. $2" >&2
    exit 1
  fi
}

check_cmd python3 "Install Python 3.11+ from https://python.org"

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
REQUIRED_MAJOR=3
REQUIRED_MINOR=11
ACTUAL_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
ACTUAL_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$ACTUAL_MAJOR" -lt "$REQUIRED_MAJOR" ] || \
   ([ "$ACTUAL_MAJOR" -eq "$REQUIRED_MAJOR" ] && [ "$ACTUAL_MINOR" -lt "$REQUIRED_MINOR" ]); then
  echo "ERROR: Python $REQUIRED_MAJOR.$REQUIRED_MINOR+ required, found $PYTHON_VERSION" >&2
  exit 1
fi

# Install uv if missing.
if ! command -v uv &>/dev/null; then
  echo ">>> uv not found — installing via official installer..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

check_cmd uv "uv installation failed. See https://docs.astral.sh/uv/"

# ── install ───────────────────────────────────────────────────────────────────
cd "$ROOT"
echo ">>> Installing rhino-mcp (Python $PYTHON_VERSION, root: $ROOT)"

if [ "$DEV" = true ]; then
  echo ">>> Mode: development (including dev extras)"
  uv sync
  uv pip install -e '.[dev]'
else
  echo ">>> Mode: production"
  uv pip install .
fi

# ── verify ────────────────────────────────────────────────────────────────────
echo ""
echo ">>> Verifying installation..."
uv run python -c "import rhino_mcp; print('  rhino_mcp:', rhino_mcp.__file__)"
uv run python -c "import rhino3dm; print('  rhino3dm :', rhino3dm.__version__)"
uv run python -c "import importlib.metadata; print('  mcp      :', importlib.metadata.version('mcp'))"

echo ""
echo "Installation complete."
echo ""
echo "Next steps:"
echo "  Start server (stdio):  rhino-mcp"
echo "  Start server (HTTP):   rhino-mcp --transport http --port 8765"
echo "  Run tests:             ./scripts/test.sh"
