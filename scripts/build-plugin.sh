#!/usr/bin/env bash
# build-plugin.sh — Build the C# Rhino plugin for Rhino 8 and/or Rhino 9.
#
# Prerequisites:
#   - .NET 8 SDK (https://dotnet.microsoft.com/download/dotnet/8.0)
#     The plugin targets net8.0; Rhino 9 (.NET 10) loads it via roll-forward.
#   - NuGet packages (restored automatically): RhinoCommon, Grasshopper,
#     Newtonsoft.Json, Microsoft.CodeAnalysis.CSharp.Scripting (Roslyn).
#
# The .csproj picks the RhinoCommon version from -p:RhinoMajor (8 or 9),
# writes to rhino_plugin/csharp/bin/rh<N>/<Config>/net8.0/, and its PostBuild
# target copies the .rhp into the matching local Rhino install
# (/Applications/Rhino <N>.app/Contents/PlugIns/ on macOS,
# %APPDATA%/McNeel/Rhinoceros/<N>.0/Plug-ins/rhino-mcp/ on Windows) when it exists.
#
# Usage:
#   ./scripts/build-plugin.sh                  # Rhino 9, Debug, install
#   ./scripts/build-plugin.sh --release        # release build
#   ./scripts/build-plugin.sh --rhino=8        # Rhino 8 build
#   ./scripts/build-plugin.sh --rhino=both     # Rhino 8 and Rhino 9
#   ./scripts/build-plugin.sh --no-install     # build only (SkipPluginCopy)
#   ./scripts/build-plugin.sh --clean          # clean before build
#   ./scripts/build-plugin.sh --help

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="$ROOT/rhino_plugin/csharp/RhinoMCPPlugin.csproj"
CONFIG="Debug"
CLEAN=false
RHINO="9"
SKIP_COPY=false

for arg in "$@"; do
  case "$arg" in
    --release)    CONFIG="Release" ;;
    --clean)      CLEAN=true ;;
    --no-install) SKIP_COPY=true ;;
    --rhino=*)    RHINO="${arg#--rhino=}" ;;
    --help)
      echo "Usage: $0 [--release] [--clean] [--rhino=8|9|both] [--no-install]"
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

case "$RHINO" in
  8) MAJORS=(8) ;;
  9) MAJORS=(9) ;;
  both) MAJORS=(8 9) ;;
  *) echo "ERROR: --rhino must be 8, 9 or both (got '$RHINO')" >&2; exit 1 ;;
esac

if ! command -v dotnet &>/dev/null; then
  echo "ERROR: dotnet SDK not found. Install from https://dotnet.microsoft.com/download" >&2
  exit 1
fi

cd "$ROOT/rhino_plugin/csharp"

for major in "${MAJORS[@]}"; do
  out_dir="$ROOT/rhino_plugin/csharp/bin/rh$major/$CONFIG"
  # Intermediates are shared across majors (only BaseOutputPath is per-major).
  obj_dir="$ROOT/rhino_plugin/csharp/obj/$CONFIG"

  if [ "$CLEAN" = true ]; then
    # Skip `dotnet clean`: the Korean-locale MSBuild on macOS mislabels its
    # informational "deleting" lines as errors and exits non-zero.
    echo ">>> Cleaning previous Rhino $major build ($out_dir)..."
    rm -rf "$out_dir" "$obj_dir"
  fi

  echo ">>> Building rhino-mcp for Rhino $major ($CONFIG)..."
  dotnet build "$PROJECT" -c "$CONFIG" -p:RhinoMajor="$major" -p:SkipPluginCopy="$SKIP_COPY"

  built="$out_dir/net8.0/rhino-mcp.rhp"
  if [ -f "$built" ]; then
    echo ">>> Built: $built"
  else
    echo "WARNING: build output not found at $built" >&2
  fi

  if [ "$SKIP_COPY" = true ]; then
    continue
  fi

  if [ "$(uname -s)" = "Darwin" ]; then
    rhp="/Applications/Rhino $major.app/Contents/PlugIns/rhino-mcp.rhp"
  else
    rhp="${APPDATA:-}/McNeel/Rhinoceros/$major.0/Plug-ins/rhino-mcp/rhino-mcp.rhp"
  fi

  if [ -f "$rhp" ]; then
    echo ">>> Installed: $rhp"
    ls -lh "$rhp"
    echo ">>> Restart Rhino $major to load the plugin."
    echo "    Bridge will auto-start on tcp://127.0.0.1:4242 (next free port if taken)."
  else
    echo "NOTE: Rhino $major is not installed at the default location; the plug-in was not copied."
    echo "      Drag $built onto a running Rhino window to load it manually."
  fi
  echo ""
done
