# Installation

## Prerequisites

- Python 3.11 or newer.
- (Optional) McNeel Rhino 8 or Rhino 9 — required only for **bridge mode** (RhinoCommon, viewport, render, Grasshopper).
- (Optional) Docker, if you prefer running the server in a container.

## Install the server

### `uv` (recommended)

```bash
uv tool install rhino-mcp
```

To run a development checkout:

```bash
git clone https://github.com/EaseHee/rhino-mcp.git
cd rhino-mcp
uv sync
uv run rhino-mcp --help
```

### `pip`

```bash
pip install rhino3dm-mcp
rhino-mcp --version
```

The optional Windows extra (pywin32) is only needed for the legacy pre-0.4 named-pipe bridge; the current plug-in listens on TCP:

```bash
pip install 'rhino3dm-mcp[windows]'
```

`rhino_bridge_list_instances` (multi-Rhino discovery) needs no extra.

The minimum `rhino3dm` is 8.35. Its macOS wheels require macOS 14 or newer.

## Register the server with your MCP client

`rhino-mcp install` writes the `rhino-mcp` entry into the config of one or more MCP clients (default: Claude Desktop).

```bash
rhino-mcp install                          # Claude Desktop
rhino-mcp install --client claude-code     # Claude Code (user scope)
rhino-mcp install --client codex --client antigravity   # repeatable
rhino-mcp install --client detected        # every client found on this machine
rhino-mcp install --client all             # every supported client
rhino-mcp install --list-clients [--json]  # detection / installation state
rhino-mcp install --dry-run                # preview without writing
rhino-mcp uninstall --client all           # remove only the rhino-mcp entry
```

| Client | Target |
|--------|--------|
| `claude-desktop` | `claude_desktop_config.json` (unchanged) |
| `claude-code` | `claude mcp add-json --scope user` when the `claude` CLI exists, otherwise `mcpServers` in `~/.claude.json` (honours `CLAUDE_CONFIG_DIR`) |
| `codex` | `$CODEX_HOME/config.toml` or `~/.codex/config.toml`, table `[mcp_servers.rhino-mcp]`; comments and other tables are preserved |
| `antigravity` | `~/.gemini/antigravity/mcp_config.json` |

Other useful flags: `--name`, `--config-path` (single concrete client only), `--no-backup`, `--mode {auto,standalone,bridge}`, `--transport {stdio,http}`, `--launcher {auto,uvx,rhino-mcp,python}`, `--force`.
Every write is preceded by a `.bak.<timestamp>` copy of the previous config.

### From inside Rhino: `_McpInstall`

With the bridge plugin loaded, type `_McpInstall` on the Rhino command line.
The command offers toggles for ClaudeDesktop, ClaudeCode, Codex and Antigravity plus All and Uninstall; the initial state comes from detection.
It passes `--launcher` so every config receives an absolute launcher path.
Each launcher is checked with `--version` first, and the first one serving at least the minimum server version the plug-in's flags need (currently 0.7.0, independent of the plug-in version) is used (uvx with `--from rhino3dm-mcp>=<minimum>`, then installed `rhino-mcp` scripts, then `python -m rhino_mcp.server`).
Before a release reaches PyPI, install the server locally with `uv tool install --force --from <path-to-rhino-mcp> rhino3dm-mcp` (see [troubleshooting](troubleshooting.md)).
`rhino-mcp install` itself registers `uvx` only when PyPI serves its own version; otherwise the entry points at the installation that ran it.
Launchers are searched on `PATH` plus `~/.local/bin`, `~/.cargo/bin`, `/opt/homebrew/bin` and `/usr/local/bin`.

## Install the Rhino bridge plugin

The bridge is a C# Rhino plugin (`rhino_plugin/csharp/`) that runs inside Rhino 8 or Rhino 9 and exposes RhinoCommon + Grasshopper to the MCP server over a JSON-RPC socket.

```bash
./scripts/build-plugin.sh --release                 # Rhino 9 (default), copies into Rhino 9.app
./scripts/build-plugin.sh --release --rhino=8       # Rhino 8
./scripts/build-plugin.sh --release --rhino=both --no-install

# Equivalent raw dotnet calls:
dotnet build rhino_plugin/csharp -c Release                    # Rhino 9 (default)
dotnet build rhino_plugin/csharp -c Release -p:RhinoMajor=8    # Rhino 8
dotnet build rhino_plugin/csharp -c Release -p:SkipPluginCopy=true
```

The `RhinoMajor` MSBuild property selects the RhinoCommon / Grasshopper reference (`9` selects 9.0.26300.9401, `8` selects 8.36.26296.17001).
The target framework stays `net8.0` for both: Rhino 9 runs on .NET 10 and loads `net8.0` plug-ins through roll-forward.
The build emits `rhino-mcp.rhp` under `rhino_plugin/csharp/bin/rh9/` or `bin/rh8/`.
Unless `-p:SkipPluginCopy=true` is set, post-build copies the plug-in into `/Applications/Rhino N.app` (macOS) or `%APPDATA%/McNeel/Rhinoceros/N.0/Plug-ins/rhino-mcp/` (Windows), and only when that Rhino install exists.

Package Manager: `./scripts/publish-yak.sh --rhino=8|9|both` (default `both`) produces separate `rh8` and `rh9` Yak distributions.
It ends with one copy-ready line that pushes them all (`'<yak>' push '<a>.yak' && …`), also saved to `rhino_plugin/csharp/dist/push-<version>.sh`.
`./scripts/release.sh` runs the version check, install, tests and this step in one go; neither script pushes.
In Rhino 9, install the `rh9` package; a build for the wrong Rhino major still loads, but the Python side logs a warning.

Drag-and-drop the `.rhp` onto a Rhino viewport (or load it via `_PluginManager`).
Once loaded the plugin starts a JSON-RPC listener on TCP `127.0.0.1:4242` (the next free port up to 4257 for additional Rhino instances) and the MCP server auto-detects it on startup, or on the first bridge-only tool call.

## Configure Claude Desktop manually

If you prefer not to use `rhino-mcp install`, edit `claude_desktop_config.json` (Claude Desktop → *Settings → Developer → Edit Config*):

```json
{
  "mcpServers": {
    "rhino-mcp": {
      "command": "uvx",
      "args": ["rhino3dm-mcp"],
      "env": {
        "RHINO_MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

Restart Claude Desktop.
The `rhino_*` and `gh_*` tools should appear in the tool palette.

## Verify

```bash
RHINO_MCP_FORCE_MODE=standalone uv run rhino-mcp --help
```

Or with the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector uv run rhino-mcp
```
