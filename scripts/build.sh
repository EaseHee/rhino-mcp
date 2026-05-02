#!/usr/bin/env bash
# build.sh — Lint, type-check, and build the rhino-mcp distribution.
#
# Usage:
#   ./scripts/build.sh              # lint + typecheck + wheel + sdist
#   ./scripts/build.sh --lint-only
#   ./scripts/build.sh --no-lint
#   ./scripts/build.sh --docker     # also build Docker image
#   ./scripts/build.sh --help

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_LINT=true
RUN_TYPECHECK=true
RUN_DIST=true
RUN_DOCKER=false

for arg in "$@"; do
  case "$arg" in
    --lint-only)   RUN_TYPECHECK=false; RUN_DIST=false ;;
    --no-lint)     RUN_LINT=false ;;
    --docker)      RUN_DOCKER=true ;;
    --help)
      echo "Usage: $0 [--lint-only] [--no-lint] [--docker]"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

cd "$ROOT"

# ── lint ──────────────────────────────────────────────────────────────────────
if [ "$RUN_LINT" = true ]; then
  echo ">>> ruff check src/ tests/"
  uv run ruff check src/ tests/
  echo ">>> ruff format --check src/ tests/"
  uv run ruff format --check src/ tests/
  echo "Lint passed."
fi

# ── type check ────────────────────────────────────────────────────────────────
if [ "$RUN_TYPECHECK" = true ]; then
  echo ""
  echo ">>> mypy src/rhino_mcp"
  uv run mypy src/rhino_mcp
  echo "Type check passed."
fi

# ── dist ──────────────────────────────────────────────────────────────────────
if [ "$RUN_DIST" = true ]; then
  echo ""
  echo ">>> Building wheel + sdist"
  rm -rf dist/
  uv run python -m build --wheel --sdist
  echo ""
  echo "Artifacts:"
  ls -lh dist/
fi

# ── docker ────────────────────────────────────────────────────────────────────
if [ "$RUN_DOCKER" = true ]; then
  echo ""
  echo ">>> Building Docker image rhino-mcp:latest"
  docker build -f docker/Dockerfile -t rhino-mcp:latest .
  echo "Docker image built: rhino-mcp:latest"
fi

echo ""
echo "Build complete."
