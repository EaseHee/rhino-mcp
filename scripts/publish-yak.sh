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
#   ./scripts/publish-yak.sh --rhino=9             # Rhino 9 only (default: both 8 and 9)
#   ./scripts/publish-yak.sh --skip-build          # reuse existing bin/rh<N>/Release output
#   ./scripts/publish-yak.sh --clean               # rebuild from scratch
#   ./scripts/publish-yak.sh --help
#
# Environment overrides:
#   YAK_CLI   Absolute path to the `yak` (or `yak.exe`) binary.
#             Default: newest /Applications/Rhino N.app/Contents/Resources/bin/yak
#                      or C:/Program Files/Rhino N/System/yak.exe
#
# One package version carries one distribution per Rhino major: yak derives
# the rh8 / rh9 tag from the RhinoCommon version each .rhp was built against.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="$ROOT/rhino_plugin/csharp"
STAGE_ROOT="$PROJECT_DIR/yak-stage"
DIST_DIR="$PROJECT_DIR/dist"
MANIFEST_SRC="$PROJECT_DIR/manifest.yml"
ICON_SRC="$ROOT/assets/rhino-mcp.png"
ICON_NAME="rhino-mcp.png"
LICENSE_SRC="$ROOT/LICENSE"
README_SRC="$ROOT/README.md"

PLATFORMS="both"
RHINO_MAJORS="8 9"
SKIP_BUILD=false
CLEAN=false

print_help() {
  awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "${BASH_SOURCE[0]}"
}

for arg in "$@"; do
  case "$arg" in
    --platform=win|--platform=mac|--platform=both) PLATFORMS="${arg#--platform=}" ;;
    --rhino=8)    RHINO_MAJORS="8" ;;
    --rhino=9)    RHINO_MAJORS="9" ;;
    --rhino=both) RHINO_MAJORS="8 9" ;;
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
    Darwin)
      # Pick the highest-versioned Rhino *.app under /Applications. Fall back
      # to the well-known Rhino 8 path so existing installs keep working.
      local rhino_app
      rhino_app="$(/bin/ls -d /Applications/Rhino*.app 2>/dev/null \
        | sort -V \
        | tail -n 1)"
      if [ -n "$rhino_app" ] && [ -x "$rhino_app/Contents/Resources/bin/yak" ]; then
        echo "$rhino_app/Contents/Resources/bin/yak"
      else
        echo "/Applications/Rhino 9.app/Contents/Resources/bin/yak"
      fi
      ;;
    Linux)   echo "" ;;
    MINGW*|MSYS*|CYGWIN*)
      # Prefer the highest-versioned Rhino N install under Program Files.
      local rhino_dir
      rhino_dir="$(/bin/ls -d '/c/Program Files/Rhino '*/System/yak.exe 2>/dev/null \
        | sort -V \
        | tail -n 1)"
      if [ -n "$rhino_dir" ]; then
        echo "$rhino_dir"
      else
        echo "C:/Program Files/Rhino 9/System/yak.exe"
      fi
      ;;
    *)       echo "" ;;
  esac
}

YAK_CLI_PATH="$(detect_yak_cli)"
if [ -z "$YAK_CLI_PATH" ] || [ ! -x "$YAK_CLI_PATH" ]; then
  echo "ERROR: yak CLI not found." >&2
  echo "  Tried: ${YAK_CLI_PATH:-<none>}" >&2
  echo "  macOS:   /Applications/Rhino N.app/Contents/Resources/bin/yak" >&2
  echo "  Windows: C:/Program Files/Rhino N/System/yak.exe" >&2
  echo "  Override with YAK_CLI=/absolute/path/to/yak ./scripts/publish-yak.sh" >&2
  exit 1
fi
echo ">>> Using yak CLI: $YAK_CLI_PATH"

build_dir_for() {
  echo "$PROJECT_DIR/bin/rh$1/Release/net8.0"
}

# dotnet is needed even with --skip-build: the manifest reads developer info from the csproj.
if ! command -v dotnet &>/dev/null; then
  echo "ERROR: dotnet SDK not found. Install from https://dotnet.microsoft.com/download" >&2
  exit 1
fi

csproj_property() {
  dotnet msbuild "$PROJECT_DIR/RhinoMCPPlugin.csproj" -nologo -getProperty:"$1" | tr -d '\r'
}

DEVELOPER_NAME="$(csproj_property DeveloperName)"
DEVELOPER_EMAIL="$(csproj_property DeveloperEmail)"
REPOSITORY_URL="$(csproj_property RepositoryUrl)"
for value in "$DEVELOPER_NAME" "$DEVELOPER_EMAIL" "$REPOSITORY_URL"; do
  if [ -z "$value" ]; then
    echo "ERROR: developer info missing from RhinoMCPPlugin.csproj." >&2
    exit 1
  fi
done

for major in $RHINO_MAJORS; do
  if [ "$SKIP_BUILD" = false ]; then
    if [ "$CLEAN" = true ]; then
      # Skip `dotnet clean` — the Korean-locale MSBuild on macOS mislabels its
      # informational "deleting" lines as errors and exits non-zero, which trips
      # `set -e`. A direct rm of the output dirs is equivalent and locale-safe.
      echo ">>> Cleaning previous rh$major build..."
      rm -rf "$PROJECT_DIR/bin/rh$major" "$PROJECT_DIR/obj/Release"
    fi
    echo ">>> Building rhino-mcp for Rhino $major (Release)..."
    dotnet build "$PROJECT_DIR/RhinoMCPPlugin.csproj" -c Release \
      -p:RhinoMajor="$major" -p:SkipPluginCopy=true
  fi
  if [ ! -f "$(build_dir_for "$major")/rhino-mcp.rhp" ]; then
    echo "ERROR: $(build_dir_for "$major")/rhino-mcp.rhp not found." >&2
    echo "       Run without --skip-build first." >&2
    exit 1
  fi
done

mkdir -p "$DIST_DIR"

stage_files() {
  local stage="$1"
  local BUILD_DIR="$2"
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

  # Flatten manifest icon path so it resolves inside the staging directory,
  # and fill developer placeholders from the csproj.
  sed -e "s|^icon: .*$|icon: $ICON_NAME|" \
      -e "s|{{DEVELOPER_NAME}}|$DEVELOPER_NAME|g" \
      -e "s|{{DEVELOPER_EMAIL}}|$DEVELOPER_EMAIL|g" \
      -e "s|{{REPOSITORY_URL}}|$REPOSITORY_URL|g" \
      "$MANIFEST_SRC" > "$stage/manifest.yml"
  if grep -q '{{' "$stage/manifest.yml"; then
    echo "ERROR: unfilled placeholder left in $stage/manifest.yml" >&2
    exit 1
  fi
}

build_for_platform() {
  local plat="$1"
  local major="$2"
  local stage="$STAGE_ROOT/rh$major-$plat"
  echo ""
  echo ">>> Staging files for Rhino $major platform=$plat -> $stage"
  stage_files "$stage" "$(build_dir_for "$major")"

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

for major in $RHINO_MAJORS; do
  case "$PLATFORMS" in
    win)  build_for_platform win "$major" ;;
    mac)  build_for_platform mac "$major" ;;
    both) build_for_platform win "$major"; build_for_platform mac "$major" ;;
  esac
done

echo ""
echo ">>> Done. Artefacts in $DIST_DIR:"
ls -lh "$DIST_DIR"/*.yak 2>/dev/null || true
echo ""
echo "Next steps (manual):"
echo "  '$YAK_CLI_PATH' login"
echo "  '$YAK_CLI_PATH' push <file>.yak"
