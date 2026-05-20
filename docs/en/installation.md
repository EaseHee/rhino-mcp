# Installation

## Prerequisites

- Python 3.11 or newer.
- (Optional) McNeel Rhino 8 — required only for **bridge mode** (RhinoCommon, viewport, render, Grasshopper).
- (Optional) Docker, if you prefer running the server in a container.

## Install the server

### `uv` (recommended)

```bash
uv tool install rhino-mcp
```

To run a development checkout:

```bash
git clone https://github.com/easehee/rhino-mcp.git
cd rhino-mcp
uv sync
uv run rhino-mcp --help
```

### `pip`

```bash
pip install rhino3dm-mcp
rhino-mcp --version
```

On Windows, install the optional extra for the named-pipe transport:

```bash
pip install 'rhino3dm-mcp[windows]'
```

`rhino_bridge_list_instances` (multi-Rhino discovery) needs no extra.

## Install the Rhino bridge plugin

The bridge is a C# Rhino plugin (`rhino_plugin/csharp/`) that runs inside Rhino 8 and exposes RhinoCommon + Grasshopper to the MCP server over a JSON-RPC socket.

```bash
dotnet build rhino_plugin/csharp -c Release
```

The build emits `rhino_plugin/csharp/bin/Release/net8.0/rhino-mcp.rhp`.
Drag-and-drop that `.rhp` onto a Rhino 8 viewport (or load it via `_PluginManager`).
Once loaded the plugin starts a JSON-RPC listener on the platform-native transport (named pipe on Windows, Unix domain socket on macOS/Linux) and the MCP server auto-detects it on startup.

## Configure Claude Desktop

Edit `claude_desktop_config.json` (Claude Desktop → *Settings → Developer → Edit Config*):

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
