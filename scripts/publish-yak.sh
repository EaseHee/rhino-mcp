#!/usr/bin/env bash
# publish-yak.sh — Build Rhino Package Manager (.yak) artefacts for rhino-mcp.
#
# Stages manifest + .rhp + dependency DLLs + icon + license into a clean folder
# and invokes the bundled `yak` CLI for the requested platform(s).
#
# This script does NOT push to the YAK server. After a successful build, run:
#   yak login          # one-time
#   yak push <file>.yak
#
# Usage:
#   ./scripts/publish-yak.sh                       # build both win + mac
#   ./scripts/publish-yak.sh --platform=win        # win only
#   ./scripts/publish-yak.sh --platform=mac        # mac only
#   ./scripts/publish-yak.sh --skip-build          # reuse existing bin/Release output
#   ./scripts/publish-yak.sh --clean               # rebuild from scratch
#   ./scripts/publish-yak.sh --help
#
# Environment overrides:
#   YAK_CLI   Absolute path to the `yak` (or `yak.exe`) binary.
#             Default: macOS  -> /Applications/Rhino 8.app/Contents/Resources/bin/yak
#                      Windows -> C:/Program Files/Rhino 8/System/yak.exe

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="$ROOT/rhino_plugin/csharp"
BUILD_DIR="$PROJECT_DIR/bin/Release/net8.0"
STAGE_ROOT="$PROJECT_DIR/yak-stage"
DIST_DIR="$PROJECT_DIR/dist"
MANIFEST_SRC="$PROJECT_DIR/manifest.yml"
ICON_SRC="$ROOT/assets/rhino-mcp.png"
ICON_NAME="rhino-mcp.png"
LICENSE_SRC="$ROOT/LICENSE"
README_SRC="$ROOT/README.md"

PLATFORMS="both"
SKIP_BUILD=false
CLEAN=false

print_help() {
  sed -n '2,22p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

for arg in "$@"; do
  case "$arg" in
    --platform=win|--platform=mac|--platform=both) PLATFORMS="${arg#--platform=}" ;;
    --skip-build) SKIP_BUILD=true ;;
    --clean)      CLEAN=true ;;
    --help|-h)    print_help; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; echo "Run with --help for usage." >&2; exit 1 ;;
  esac
done

detect_yak_cli() {
  if [ -n "${YAK_CLI:-}" ]; then
    echo "$YAK_CLI"
    return
  fi
  case "$(uname -s)" in
    Darwin)  echo "/Applications/Rhino 8.app/Contents/Resources/bin/yak" ;;
    Linux)   echo "" ;;
    MINGW*|MSYS*|CYGWIN*) echo "C:/Program Files/Rhino 8/System/yak.exe" ;;
    *)       echo "" ;;
  esac
}

YAK_CLI_PATH="$(detect_yak_cli)"
if [ -z "$YAK_CLI_PATH" ] || [ ! -x "$YAK_CLI_PATH" ]; then
  echo "ERROR: yak CLI not found." >&2
  echo "  Tried: ${YAK_CLI_PATH:-<none>}" >&2
  echo "  macOS:   /Applications/Rhino 8.app/Contents/Resources/bin/yak" >&2
  echo "  Windows: C:/Program Files/Rhino 8/System/yak.exe" >&2
  echo "  Override with YAK_CLI=/absolute/path/to/yak ./scripts/publish-yak.sh" >&2
  exit 1
fi
echo ">>> Using yak CLI: $YAK_CLI_PATH"

if [ "$SKIP_BUILD" = false ]; then
  if ! command -v dotnet &>/dev/null; then
    echo "ERROR: dotnet SDK not found. Install from https://dotnet.microsoft.com/download" >&2
    exit 1
  fi
  if [ "$CLEAN" = true ]; then
    # Skip `dotnet clean` — the Korean-locale MSBuild on macOS mislabels its
    # informational "deleting" lines as errors and exits non-zero, which trips
    # `set -e`. A direct rm of the output dirs is equivalent and locale-safe.
    echo ">>> Cleaning previous build (rm bin/Release + obj/Release)..."
    rm -rf "$PROJECT_DIR/bin/Release" "$PROJECT_DIR/obj/Release"
  fi
  echo ">>> Building rhino-mcp (Release)..."
  dotnet build "$PROJECT_DIR/RhinoMCPPlugin.csproj" -c Release
fi

if [ ! -f "$BUILD_DIR/rhino-mcp.rhp" ]; then
  echo "ERROR: $BUILD_DIR/rhino-mcp.rhp not found." >&2
  echo "       Run without --skip-build first." >&2
  exit 1
fi

mkdir -p "$DIST_DIR"

stage_files() {
  local stage="$1"
  rm -rf "$stage"
  mkdir -p "$stage"

  cp "$BUILD_DIR/rhino-mcp.rhp" "$stage/"
  # Copy every runtime dependency emitted next to the .rhp (Newtonsoft.Json,
  # Roslyn assemblies, language packs, etc.). RhinoCommon/Grasshopper are
  # ExcludeAssets="runtime" so they will not appear here.
  find "$BUILD_DIR" -maxdepth 1 -type f \( -name '*.dll' -o -name '*.pdb' \) \
    -exec cp {} "$stage/" \;
  # Localised satellite assemblies live in subdirectories — preserve structure.
  find "$BUILD_DIR" -mindepth 1 -maxdepth 1 -type d -exec cp -R {} "$stage/" \;

  cp "$ICON_SRC" "$stage/$ICON_NAME"
  [ -f "$LICENSE_SRC" ] && cp "$LICENSE_SRC" "$stage/LICENSE"
  [ -f "$README_SRC" ]  && cp "$README_SRC"  "$stage/README.md"

  # Flatten manifest icon path so it resolves inside the staging directory.
  sed "s|^icon: .*$|icon: $ICON_NAME|" "$MANIFEST_SRC" > "$stage/manifest.yml"
}

build_for_platform() {
  local plat="$1"
  local stage="$STAGE_ROOT/$plat"
  echo ""
  echo ">>> Staging files for platform=$plat -> $stage"
  stage_files "$stage"

  echo ">>> Running yak build --platform $plat"
  ( cd "$stage" && "$YAK_CLI_PATH" build --platform "$plat" )

  # yak emits the .yak file inside the working directory.
  local produced
  produced="$(find "$stage" -maxdepth 1 -name '*.yak' -print -quit)"
  if [ -z "$produced" ]; then
    echo "ERROR: yak build did not produce a .yak file in $stage" >&2
    exit 1
  fi
  mv "$produced" "$DIST_DIR/"
  echo ">>> Produced: $DIST_DIR/$(basename "$produced")"
}

case "$PLATFORMS" in
  win)  build_for_platform win ;;
  mac)  build_for_platform mac ;;
  both) build_for_platform win; build_for_platform mac ;;
esac

echo ""
echo ">>> Done. Artefacts in $DIST_DIR:"
ls -lh "$DIST_DIR"/*.yak 2>/dev/null || true
echo ""
echo "Next steps (manual):"
echo "  $YAK_CLI_PATH login"
echo "  $YAK_CLI_PATH push <file>.yak"
