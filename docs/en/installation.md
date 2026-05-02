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
pip install rhino-mcp
rhino-mcp --version
```

On Windows, install the optional extra for the named-pipe transport:

```bash
pip install 'rhino-mcp[windows]'
```

## Install the Rhino bridge plugin

The bridge is a single Python file (`rhino_plugin/RhinoMCPBridge.py`) that runs inside Rhino 8 and exposes RhinoCommon + Grasshopper to the MCP server over a socket.

```bash
python rhino_plugin/install.py
```

This copies the bridge to your Rhino scripts directory:

| OS       | Path |
|----------|------|
| Windows  | `%APPDATA%\McNeel\Rhinoceros\8.0\scripts\RhinoMCPBridge.py` |
| macOS    | `~/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/RhinoMCPBridge.py` |
| Linux    | `~/.config/Rhino/8.0/scripts/RhinoMCPBridge.py` |

Inside Rhino:

```
_-RunPythonScript "<the path above>"
```

You can also paste the script into Rhino's ScriptEditor and run it from there. The bridge prints a startup line with the transport URL it's listening on.

## Configure Claude Desktop

Edit `claude_desktop_config.json` (Claude Desktop → *Settings → Developer → Edit Config*):

```json
{
  "mcpServers": {
    "rhino-mcp": {
      "command": "uvx",
      "args": ["rhino-mcp"],
      "env": {
        "RHINO_MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

Restart Claude Desktop. The `rhino_*` and `gh_*` tools should appear in the tool palette.

## Verify

```bash
RHINO_MCP_FORCE_MODE=standalone uv run rhino-mcp --help
```

Or with the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector uv run rhino-mcp
```
