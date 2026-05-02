# Troubleshooting

## Quick diagnostic

```bash
./scripts/check-bridge.sh
```

Prints a PASS / FAIL / WARN verdict for every layer of the bridge detection stack
and shows the exact fix for each failure.

---

## Bridge setup inside Rhino 8

The most common reason `rhino-mcp` starts in standalone mode is that
**RhinoMCPBridge.py is not running inside Rhino 8**.

### Step 1 — Install the bridge file (once)

```bash
python rhino_plugin/install.py
```

Platform install paths:

| OS      | Path |
|---------|------|
| macOS   | `~/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/RhinoMCPBridge.py` |
| Windows | `%APPDATA%\McNeel\Rhinoceros\8.0\scripts\RhinoMCPBridge.py` |
| Linux   | `~/.config/Rhino/8.0/scripts/RhinoMCPBridge.py` |

### Step 2 — Start the bridge in Rhino 8

Type in the Rhino command line:

```
_-RunPythonScript "path/to/RhinoMCPBridge.py"
```

> macOS example:
> ```
> _-RunPythonScript "/Users/<you>/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/RhinoMCPBridge.py"
> ```

On **success** the Rhino command history shows:

```
[RhinoMCPBridge] listening on unix:///tmp/rhino_mcp.sock    ← macOS/Linux
[RhinoMCPBridge] listening on \\.\pipe\rhino_mcp            ← Windows
[RhinoMCPBridge] listening on tcp://127.0.0.1:4242          ← TCP forced
```

### Step 3 — Verify connectivity

```bash
./scripts/check-bridge.sh
```

Look for "Bridge responded to ping" with the Rhino / GH version printed.

---

## Transport reference

| Platform | Default transport | Socket / pipe path |
|----------|-------------------|--------------------|
| macOS    | Unix socket | `/tmp/rhino_mcp.sock` (or `$RHINO_MCP_SOCKET`) |
| Linux    | Unix socket | `$XDG_RUNTIME_DIR/rhino_mcp.sock` or `/tmp/rhino_mcp.sock` |
| Windows  | Named pipe  | `\\.\pipe\rhino_mcp` |
| All      | TCP (opt)   | `$RHINO_HOST:$RHINO_PORT` (default `localhost:4242`) |

Force TCP on both sides:

```bash
# Rhino side (set before starting bridge)
export RHINO_MCP_TRANSPORT_KIND=tcp

# Server side
RHINO_MCP_TRANSPORT_KIND=tcp uv run rhino-mcp
```

Custom socket path:

```bash
export RHINO_MCP_SOCKET=/custom/path/rhino.sock   # both sides
```

---

## Common failures

### "Cannot reach Rhino bridge."

Checklist:

1. **Rhino 8 is running**
2. **Bridge is running** — `_-RunPythonScript` was executed in Rhino
3. **Socket file exists** (macOS):
   ```bash
   ls -la /tmp/rhino_mcp.sock
   ```
4. **Env vars match** — `RHINO_HOST` / `RHINO_PORT` / `RHINO_MCP_SOCKET` are the same on both sides
5. Run the diagnostic: `./scripts/check-bridge.sh`

### Bridge running but server still goes standalone

Socket file exists but connection is refused:

```bash
file /tmp/rhino_mcp.sock   # must report "socket"
# If Rhino was restarted, re-run _-RunPythonScript to recreate the socket.

# Switch to TCP for testing:
RHINO_MCP_TRANSPORT_KIND=tcp ./scripts/check-bridge.sh --tcp
```

### "Tool 'X' requires Rhino bridge mode."

Server started in standalone mode before the bridge was up. Start the bridge in
Rhino first, then restart the server:

```bash
./scripts/run.sh --bridge
# Or with automatic fallback (connector mode):
./scripts/run.sh --connector --bridge
```

### "Invalid parameter: axis" on `rhino_cylinder`

`rhino3dm` cannot place a circle on an arbitrary plane in standalone mode. Use the
world-Z axis (`{x:0,y:0,z:1}`) or switch to bridge mode.

### "non-3DM" import error

`rhino_import` only handles `.3dm` in standalone. STEP/IGES/DXF imports require
Rhino's importers — use bridge mode.

### MCP stdio transport corrupted

JSON-decode errors in Claude Desktop mean something is writing to stdout. `rhino-mcp`
logs to stderr only. Run with `RHINO_MCP_LOG_LEVEL=DEBUG` to confirm.

### Grasshopper bake is empty

- Run `gh_run` before `gh_bake_to_rhino`
- Check component output with `gh_get_parameter`
- Some components emit data, not geometry

---

## Error categories

| Category         | Meaning |
|------------------|---------|
| `connection`     | Bridge unreachable |
| `timeout`        | Bridge response timed out |
| `parameter`      | Input value rejected (range/type error) |
| `not_found`      | Document / object / layer identifier not found |
| `unsupported`    | Tool requires bridge mode; server is standalone |
| `gh_component`   | Grasshopper component name match failed |
| `internal`       | Bridge raised exception; `details` contains Python trace |

---

## Diagnostics

```bash
# Full bridge check:
./scripts/check-bridge.sh

# List tools in standalone mode:
RHINO_MCP_FORCE_MODE=standalone uv run python -c \
  "from rhino_mcp.server import build_server; from rhino_mcp.utils.registry import Mode; \
   m,c=build_server(runtime_mode=Mode.STANDALONE); \
   import pprint; mgr=getattr(m,'_tool_manager',None); \
   pprint.pprint(sorted(mgr._tools.keys()) if mgr else [])"

# Bridge mode with debug logs:
RHINO_MCP_FORCE_MODE=bridge RHINO_MCP_LOG_LEVEL=DEBUG uv run rhino-mcp

# Introspect schemas with MCP Inspector:
npx @modelcontextprotocol/inspector uv run rhino-mcp
```
