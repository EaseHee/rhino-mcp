#!/usr/bin/env bash
# build-plugin.sh — Build the C# Rhino plugin and install to Rhino's PlugIns directory.
#
# Prerequisites:
#   - .NET 8 SDK (https://dotnet.microsoft.com/download/dotnet/8.0)
#   - NuGet packages: RhinoCommon, Grasshopper, Newtonsoft.Json,
#     Microsoft.CodeAnalysis.CSharp.Scripting (Roslyn — for C# script execution)
#
# The .csproj PostBuild target copies the .rhp to /Applications/Rhino 8.app/Contents/PlugIns/
# automatically on macOS. This script just invokes dotnet build.
#
# Usage:
#   ./scripts/build-plugin.sh              # build + install
#   ./scripts/build-plugin.sh --release    # release build
#   ./scripts/build-plugin.sh --clean      # clean before build
#   ./scripts/build-plugin.sh --help

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="$ROOT/rhino_plugin/csharp/RhinoMCPPlugin.csproj"
CONFIG="Debug"
CLEAN=false

for arg in "$@"; do
  case "$arg" in
    --release) CONFIG="Release" ;;
    --clean)   CLEAN=true ;;
    --help)
      echo "Usage: $0 [--release] [--clean]"
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

if ! command -v dotnet &>/dev/null; then
  echo "ERROR: dotnet SDK not found. Install from https://dotnet.microsoft.com/download" >&2
  exit 1
fi

cd "$ROOT/rhino_plugin/csharp"

if [ "$CLEAN" = true ]; then
  echo ">>> Cleaning..."
  dotnet clean "$PROJECT" -c "$CONFIG" -q
fi

echo ">>> Building RhinoMCPBridge ($CONFIG)..."
dotnet build "$PROJECT" -c "$CONFIG"

# Verify install
if [ "$(uname -s)" = "Darwin" ]; then
  RHP="/Applications/Rhino 8.app/Contents/PlugIns/RhinoMCPBridge.rhp"
else
  RHP="$APPDATA/McNeel/Rhinoceros/8.0/Plug-ins/RhinoMCPBridge/RhinoMCPBridge.rhp"
fi

if [ -f "$RHP" ]; then
  echo ""
  echo ">>> Installed: $RHP"
  ls -lh "$RHP"
  echo ""
  echo ">>> Restart Rhino 8 to load the plugin."
  echo "    Bridge will auto-start on tcp://127.0.0.1:4242"
else
  echo ""
  echo "WARNING: .rhp not found at expected location."
  echo "         Check build output above for PostBuild copy errors."
fi
