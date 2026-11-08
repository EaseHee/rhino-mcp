#!/usr/bin/env bash
# ci.sh — Single-command CI pipeline: install → lint → typecheck → test → plugin → build.
#
# Mirrors .github/workflows/ci.yml: ruff check gates, mypy is informational,
# pytest gates, and the C# plug-in is built for Rhino 8 and Rhino 9 without
# copying into a local Rhino install. Useful for local pre-push validation.
#
# Usage:
#   ./scripts/ci.sh              # full pipeline
#   ./scripts/ci.sh --no-build   # skip wheel/sdist artifact step
#   ./scripts/ci.sh --no-plugin  # skip the C# plug-in builds
#   ./scripts/ci.sh --help

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
BUILD_DIST=true
BUILD_PLUGIN=true

for arg in "$@"; do
  case "$arg" in
    --no-build)  BUILD_DIST=false ;;
    --no-plugin) BUILD_PLUGIN=false ;;
    --help)
      echo "Usage: $0 [--no-build] [--no-plugin]"
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
step 2 "Lint (ruff check)"
bash "$SCRIPTS/build.sh" --lint-only

# ── Step 3: Type check ────────────────────────────────────────────────────────
step 3 "Type check (mypy, informational)"
uv run mypy src/rhino_mcp || echo "mypy reported errors (informational, as in CI)."

# ── Step 4: Test ─────────────────────────────────────────────────────────────
step 4 "Test suite (coverage)"
bash "$SCRIPTS/test.sh"

# ── Step 5: C# plug-in ────────────────────────────────────────────────────────
if [ "$BUILD_PLUGIN" = true ]; then
  step 5 "C# plug-in (Rhino 8 + Rhino 9)"
  if command -v dotnet &>/dev/null; then
    bash "$SCRIPTS/build-plugin.sh" --release --rhino=both --no-install
  else
    echo "dotnet SDK not found; skipping plug-in build (CI builds it on Windows)."
  fi
fi

# ── Step 6: Build ─────────────────────────────────────────────────────────────
if [ "$BUILD_DIST" = true ]; then
  step 6 "Build wheel + sdist"
  bash "$SCRIPTS/build.sh" --no-lint
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════"
echo "  CI pipeline passed  ($(elapsed))"
echo "════════════════════════════════════════════════════════"
