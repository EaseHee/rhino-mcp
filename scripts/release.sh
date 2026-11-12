#!/usr/bin/env bash
# release.sh — One-shot Yak release preparation for rhino-mcp.
#
# Runs, in order, stopping at the first failure:
#   1. version check   pyproject.toml, src/rhino_mcp/__init__.py, manifest.yml
#                      and RhinoMCPPlugin.csproj must carry the same version
#   2. install         ./scripts/install.sh --dev
#   3. checks          uv run pytest tests/ -q  +  uv run ruff check src/ tests/
#   4. packages        ./scripts/publish-yak.sh (Release builds for rh8 + rh9,
#                      win + mac packages, plug-in NOT copied into local Rhino)
#
# Nothing is pushed. The last step prints one copy-ready line,
#   '<yak>' push '<a>.yak' && '<yak>' push '<b>.yak' && ...
# and saves it to rhino_plugin/csharp/dist/push-<version>.sh.
#
# build-plugin.sh is not part of the release: it copies the .rhp into the local
# Rhino install, which then clashes with the Package Manager copy on the same
# plug-in GUID ("ID already in use").
#
# Usage:
#   ./scripts/release.sh                     # full run
#   ./scripts/release.sh --skip-install      # reuse the current environment
#   ./scripts/release.sh --skip-checks       # skip pytest + ruff
#   ./scripts/release.sh --help
#
# Only --skip-install and --skip-checks belong to release.sh. These are passed
# to publish-yak.sh as is and validated before step 1, so a typo fails fast:
#   --rhino=8|9|both  --platform=win|mac|both  --clean  --skip-build  --copy

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKIP_INSTALL=false
SKIP_CHECKS=false
PUBLISH_ARGS=()

for arg in "$@"; do
  case "$arg" in
    --skip-install) SKIP_INSTALL=true ;;
    --skip-checks)  SKIP_CHECKS=true ;;
    --help|-h)
      awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    --print-push)
      echo "ERROR: --print-push is a publish-yak.sh option; run ./scripts/publish-yak.sh --print-push" >&2
      exit 1
      ;;
    --rhino=8|--rhino=9|--rhino=both|--platform=win|--platform=mac|--platform=both|--clean|--skip-build|--copy)
      PUBLISH_ARGS+=("$arg")
      ;;
    *)
      echo "ERROR: unknown option: $arg (run with --help for usage)" >&2
      exit 1
      ;;
  esac
done

cd "$ROOT"

step() {
  echo ""
  echo "================================================================"
  echo ">>> $1"
  echo "================================================================"
}

step "1/4 Version check"
if ! command -v dotnet &>/dev/null; then
  echo "ERROR: dotnet SDK not found. Install from https://dotnet.microsoft.com/download" >&2
  exit 1
fi
pyproject_version="$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml | head -n 1)"
package_version="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' src/rhino_mcp/__init__.py | head -n 1)"
# Same reading as publish-yak.sh: first version: line, CR and quotes stripped.
manifest_version="$(sed -n 's/^version:[[:space:]]*//p' rhino_plugin/csharp/manifest.yml | head -n 1 | tr -d '\r"'"'")"
# Evaluated by MSBuild, as publish-yak.sh does, so conditional or property-based values resolve the same way.
csproj_version="$(dotnet msbuild rhino_plugin/csharp/RhinoMCPPlugin.csproj -nologo -getProperty:Version | tr -d '\r')"
echo "  pyproject.toml           $pyproject_version"
echo "  src/rhino_mcp/__init__   $package_version"
echo "  manifest.yml             $manifest_version"
echo "  RhinoMCPPlugin.csproj    $csproj_version"
if [ -z "$pyproject_version" ] \
  || [ "$package_version" != "$pyproject_version" ] \
  || [ "$manifest_version" != "$pyproject_version" ] \
  || [ "$csproj_version" != "$pyproject_version" ]; then
  echo "ERROR: version strings differ; align them before releasing." >&2
  exit 1
fi

if [ "$SKIP_INSTALL" = true ]; then
  step "2/4 Install (skipped)"
else
  step "2/4 Install"
  ./scripts/install.sh --dev
fi

if [ "$SKIP_CHECKS" = true ]; then
  step "3/4 Checks (skipped)"
else
  step "3/4 Checks"
  uv run pytest tests/ -q
  uv run ruff check src/ tests/
fi

step "4/4 Yak packages for rhino-mcp $pyproject_version"
./scripts/publish-yak.sh ${PUBLISH_ARGS[@]+"${PUBLISH_ARGS[@]}"}
