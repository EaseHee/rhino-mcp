#!/usr/bin/env bash
# test.sh — Run the rhino-mcp test suite.
#
# Usage:
#   ./scripts/test.sh               # all tests with coverage
#   ./scripts/test.sh --fast        # skip coverage, fail fast
#   ./scripts/test.sh --live        # include tests that require a running Rhino 8
#   ./scripts/test.sh --unit        # tools + utils tests only (no bridge)
#   ./scripts/test.sh --bridge      # bridge tests only
#   ./scripts/test.sh --help

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

COV=true
FAST=false
LIVE=false
FILTER=""

for arg in "$@"; do
  case "$arg" in
    --fast)   COV=false; FAST=true ;;
    --live)   LIVE=true ;;
    --unit)   FILTER="tests/tools tests/test_utils.py tests/test_server_smoke.py" ;;
    --bridge) FILTER="tests/bridge" ;;
    --help)
      echo "Usage: $0 [--fast] [--live] [--unit] [--bridge]"
      echo ""
      echo "  --fast    Skip coverage, stop on first failure (-x)"
      echo "  --live    Include @pytest.mark.live tests (requires RHINO_LIVE=1 + Rhino 8)"
      echo "  --unit    Run tools + server smoke tests only"
      echo "  --bridge  Run bridge tests only"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

cd "$ROOT"

# Build pytest argument list.
PYTEST_ARGS=("-v")

[ "$FAST" = true ]  && PYTEST_ARGS+=("-x")
[ "$LIVE" = true ]  && export RHINO_LIVE=1

if [ "$LIVE" = false ]; then
  PYTEST_ARGS+=("-m" "not live")
fi

if [ "$COV" = true ]; then
  PYTEST_ARGS+=(
    "--cov=src/rhino_mcp"
    "--cov-report=term-missing"
    "--cov-report=html:htmlcov"
  )
fi

# Append path filter last so pytest receives it as positional arguments.
if [ -n "$FILTER" ]; then
  # shellcheck disable=SC2206
  PYTEST_ARGS+=($FILTER)
fi

echo ">>> pytest ${PYTEST_ARGS[*]}"
uv run pytest "${PYTEST_ARGS[@]}"

if [ "$COV" = true ]; then
  echo ""
  echo "HTML coverage report: htmlcov/index.html"
fi
