#!/usr/bin/env bash
# publish-yak.sh — Build Rhino Package Manager (.yak) artefacts for rhino-mcp.
#
# Stages manifest + .rhp + dependency DLLs + icon + license into a clean folder
# and invokes the bundled `yak` CLI for the requested platform(s).
#
# This script does NOT push to the Yak server. It ends by printing one
# copy-ready line that pushes every package of this version:
#   '<yak>' push '<dist>/a.yak' && '<yak>' push '<dist>/b.yak' && ...
# The same line is saved to rhino_plugin/csharp/dist/push-<version>.sh (run it with bash).
# Every requested Rhino major x platform must have exactly one package, and each
# .rhp must carry the csproj Version and PluginGuid, or nothing is printed.
# Log in once beforehand with: '<yak>' login
#
# Usage:
#   ./scripts/publish-yak.sh                       # build both win + mac
#   ./scripts/publish-yak.sh --platform=win        # win only
#   ./scripts/publish-yak.sh --platform=mac        # mac only
#   ./scripts/publish-yak.sh --rhino=9             # Rhino 9 only (default: both 8 and 9)
#   ./scripts/publish-yak.sh --skip-build          # reuse existing bin/rh<N>/Release output
#   ./scripts/publish-yak.sh --clean               # rebuild from scratch
#   ./scripts/publish-yak.sh --print-push          # no build; print the push line for dist/ packages
#   ./scripts/publish-yak.sh --copy                # also copy the push line to the clipboard
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
PRINT_ONLY=false
COPY=false

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
    --print-push) PRINT_ONLY=true ;;
    --copy)       COPY=true ;;
    --help|-h)    print_help; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; echo "Run with --help for usage." >&2; exit 1 ;;
  esac
done

case "$PLATFORMS" in
  both) PLATFORM_LIST="win mac" ;;
  *)    PLATFORM_LIST="$PLATFORMS" ;;
esac

detect_yak_cli() {
  if [ -n "${YAK_CLI:-}" ]; then
    echo "$YAK_CLI"
    return
  fi
  case "$(uname -s)" in
    Darwin)
      # Pick the highest-versioned Rhino *.app under /Applications. Fall back
      # to the well-known Rhino 9 path so existing installs keep working.
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

# Package file names come from the manifest version.
PACKAGE_VERSION="$(sed -n 's/^version:[[:space:]]*//p' "$MANIFEST_SRC" | head -n 1 | tr -d '\r"'"'")"
if [ -z "$PACKAGE_VERSION" ]; then
  echo "ERROR: no version: line in $MANIFEST_SRC" >&2
  exit 1
fi

# Single-quote a word for bash / zsh; embedded single quotes become '\''.
shell_quote() {
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

# Print and save one line that pushes every given package, stopping at the first failure.
emit_push_command() {
  if [ "$#" -eq 0 ]; then
    echo "ERROR: no rhino-mcp-$PACKAGE_VERSION packages to push in $DIST_DIR" >&2
    exit 1
  fi
  local yak line="" file plural="s"
  if [ "$#" -eq 1 ]; then plural=""; fi
  yak="$(shell_quote "$YAK_CLI_PATH")"
  for file in "$@"; do
    [ -n "$line" ] && line="$line && "
    line="$line$yak push $(shell_quote "$file")"
  done

  local script_file="$DIST_DIR/push-$PACKAGE_VERSION.sh"
  {
    echo "#!/usr/bin/env bash"
    echo "# Generated by scripts/publish-yak.sh: push rhino-mcp $PACKAGE_VERSION ($# package$plural)."
    echo "# Log in once beforehand with: $yak login"
    echo "$line"
  } > "$script_file"
  chmod +x "$script_file"

  echo ""
  echo ">>> Push rhino-mcp $PACKAGE_VERSION ($# package$plural). Log in once beforehand with: $yak login"
  echo ">>> Copy the line between the markers, or run: bash $(shell_quote "$script_file")"
  echo "----- 8< -----"
  echo "$line"
  echo "----- >8 -----"

  if [ "$COPY" = true ]; then
    if command -v pbcopy &>/dev/null; then
      printf '%s' "$line" | pbcopy && echo ">>> Copied to the clipboard."
    elif command -v clip.exe &>/dev/null; then
      printf '%s' "$line" | clip.exe && echo ">>> Copied to the clipboard."
    else
      echo "NOTE: no clipboard tool (pbcopy / clip.exe) found; copy the line above by hand."
    fi
  fi
}

# Collect exactly one dist/ package of this version per selected major and platform.
collect_dist_packages() {
  local major plat file problems="" matches
  COLLECTED=()
  for major in $RHINO_MAJORS; do
    for plat in $PLATFORM_LIST; do
      matches=()
      for file in "$DIST_DIR"/rhino-mcp-"$PACKAGE_VERSION"-rh"$major"_*-"$plat".yak; do
        # An if, not `[ ] &&`: a false test as the last command would make set -e exit silently.
        if [ -f "$file" ]; then matches+=("$file"); fi
      done
      case "${#matches[@]}" in
        1) COLLECTED+=("${matches[0]}") ;;
        0) problems="$problems
  missing: rh$major $plat (rhino-mcp-$PACKAGE_VERSION-rh${major}_*-$plat.yak)" ;;
        *) problems="$problems
  ambiguous: rh$major $plat has ${#matches[@]} packages; keep one: $(basename -a "${matches[@]}" | tr '\n' ' ')" ;;
      esac
    done
  done
  if [ -n "$problems" ]; then
    echo "ERROR: dist/ does not hold one package per requested distribution:$problems" >&2
    echo "  Rebuild them, or narrow the selection with --rhino= / --platform=." >&2
    exit 1
  fi
}

if [ "$PRINT_ONLY" = true ]; then
  collect_dist_packages
  emit_push_command ${COLLECTED[@]+"${COLLECTED[@]}"}
  exit 0
fi

build_dir_for() {
  echo "$PROJECT_DIR/bin/rh$1/Release/net8.0"
}

# dotnet is needed even with --skip-build: the manifest reads developer info from the csproj.
if ! command -v dotnet &>/dev/null; then
  echo "ERROR: dotnet SDK not found. Install from https://dotnet.microsoft.com/download" >&2
  exit 1
fi

# One MSBuild evaluation for every csproj property; -getProperty with several names prints JSON, one property per line.
CSPROJ_JSON="$(dotnet msbuild "$PROJECT_DIR/RhinoMCPPlugin.csproj" -nologo \
  -getProperty:DeveloperName -getProperty:DeveloperEmail -getProperty:RepositoryUrl \
  -getProperty:Version -getProperty:PluginGuid | tr -d '\r')"

csproj_property() {
  printf '%s\n' "$CSPROJ_JSON" | sed -n "s/^[[:space:]]*\"$1\":[[:space:]]*\"\(.*\)\",\{0,1\}[[:space:]]*$/\1/p"
}

DEVELOPER_NAME="$(csproj_property DeveloperName)"
DEVELOPER_EMAIL="$(csproj_property DeveloperEmail)"
REPOSITORY_URL="$(csproj_property RepositoryUrl)"
ASSEMBLY_VERSION="$(csproj_property Version)"
PLUGIN_GUID="$(csproj_property PluginGuid)"
for value in "$DEVELOPER_NAME" "$DEVELOPER_EMAIL" "$REPOSITORY_URL" "$ASSEMBLY_VERSION" "$PLUGIN_GUID"; do
  case "$value" in
    ''|*\\*)
      echo "ERROR: could not read DeveloperName / DeveloperEmail / RepositoryUrl / Version / PluginGuid from RhinoMCPPlugin.csproj." >&2
      exit 1
      ;;
  esac
done

# A manifest / assembly version mismatch would publish a package whose .rhp reports another version.
if [ "$ASSEMBLY_VERSION" != "$PACKAGE_VERSION" ]; then
  echo "ERROR: manifest.yml version $PACKAGE_VERSION differs from csproj Version $ASSEMBLY_VERSION." >&2
  exit 1
fi

# Reject a stale .rhp (typically with --skip-build): it must carry this Version and the PluginGuid.
verify_built_rhp() {
  local rhp="$1" built_version
  # The SDK writes AssemblyInformationalVersion as "<Version>+<commit sha>" when git is available.
  built_version="$(LC_ALL=C grep -a -o -E '[0-9]+\.[0-9]+\.[0-9]+\+[0-9a-f]{7,40}' "$rhp" | head -n 1 | cut -d+ -f1 || true)"
  if [ -z "$built_version" ] && LC_ALL=C grep -a -q -F "$PACKAGE_VERSION.0" "$rhp"; then
    built_version="$PACKAGE_VERSION"
  fi
  if [ "$built_version" != "$PACKAGE_VERSION" ]; then
    echo "ERROR: $rhp was built as version ${built_version:-<unknown>}, not $PACKAGE_VERSION." >&2
    echo "       Rebuild without --skip-build." >&2
    exit 1
  fi
  if ! LC_ALL=C grep -a -q -F "$PLUGIN_GUID" "$rhp"; then
    echo "ERROR: $rhp does not carry the plug-in GUID $PLUGIN_GUID; Rhino would not register it." >&2
    echo "       Rebuild without --skip-build." >&2
    exit 1
  fi
}

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
  verify_built_rhp "$(build_dir_for "$major")/rhino-mcp.rhp"
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

PRODUCED=()

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
  PRODUCED+=("$DIST_DIR/$(basename "$produced")")
  echo ">>> Produced: $DIST_DIR/$(basename "$produced")"
}

for major in $RHINO_MAJORS; do
  for plat in $PLATFORM_LIST; do
    build_for_platform "$plat" "$major"
  done
done

echo ""
echo ">>> Done. Packages built in this run:"
ls -lh "${PRODUCED[@]}"

emit_push_command "${PRODUCED[@]}"
