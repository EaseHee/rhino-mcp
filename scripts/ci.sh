#!/usr/bin/env bash
# ci.sh — Single-command CI pipeline: install → lint → typecheck → test → build.
#
# Mirrors what the CI/CD system runs. Useful for local pre-push validation.
#
# Usage:
#   ./scripts/ci.sh             # full pipeline
#   ./scripts/ci.sh --no-build  # skip wheel/sdist artifact step
#   ./scripts/ci.sh --help

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
BUILD_DIST=true

for arg in "$@"; do
  case "$arg" in
    --no-build) BUILD_DIST=false ;;
    --help)
      echo "Usage: $0 [--no-build]"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

# Elapsed time helper.
START=$(date +%s)
elapsed() { echo "$(( $(date +%s) - START ))s"; }

step() {
  echo ""
  echo "════════════════════════════════════════════════════════"
  echo "  STEP $1: $2"
  echo "════════════════════════════════════════════════════════"
}

cd "$ROOT"

# ── Step 1: Install ───────────────────────────────────────────────────────────
step 1 "Install (dev)"
bash "$SCRIPTS/install.sh" --dev

# ── Step 2: Lint ─────────────────────────────────────────────────────────────
step 2 "Lint + format check"
bash "$SCRIPTS/build.sh" --lint-only

# ── Step 3: Type check ────────────────────────────────────────────────────────
step 3 "Type check (mypy)"
uv run mypy src/rhino_mcp

# ── Step 4: Test ─────────────────────────────────────────────────────────────
step 4 "Test suite (coverage)"
bash "$SCRIPTS/test.sh"

# ── Step 5: Build ─────────────────────────────────────────────────────────────
if [ "$BUILD_DIST" = true ]; then
  step 5 "Build wheel + sdist"
  bash "$SCRIPTS/build.sh" --no-lint
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════"
echo "  CI pipeline passed  ($(elapsed))"
echo "════════════════════════════════════════════════════════"
