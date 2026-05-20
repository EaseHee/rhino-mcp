# Troubleshooting

## Quick diagnostic

```bash
./scripts/check-bridge.sh
```

Prints a PASS / FAIL / WARN verdict for every layer of the bridge detection stack and shows the exact fix for each failure.

---

## Bridge setup inside Rhino 8

The most common reason `rhino-mcp` starts in standalone mode is that the **C# bridge plugin is not loaded in Rhino 8**.

### Step 1 — Build the plugin (once)

```bash
dotnet build rhino_plugin/csharp -c Release
```

This emits `rhino_plugin/csharp/bin/Release/net8.0/rhino-mcp.rhp`.

### Step 2 — Load the .rhp in Rhino 8

Drag-and-drop the `.rhp` onto a Rhino viewport, or open `_PluginManager` and click *Install...*.
The plugin is loaded once and survives Rhino restarts.
You can verify with `_-PluginManager` and looking for the `rhino-mcp` entry.

On **success** the Rhino command history shows:

```
[rhino-mcp] listening on unix:///tmp/rhino_mcp.sock    ← macOS/Linux
[rhino-mcp] listening on \\.\pipe\rhino_mcp            ← Windows
[rhino-mcp] listening on tcp://127.0.0.1:4242          ← TCP forced
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

1. **Rhino 8 is running**.
2. **The `rhino-mcp.rhp` C# plug-in is loaded** — install via the
   Rhino package manager, or build locally with
   `./scripts/build-plugin.sh --release`.  The plug-in auto-starts the
   bridge on `OnLoad`; no script execution is required.
3. **TCP port is reachable** — default `127.0.0.1:4242`. Check with
   `nc -z 127.0.0.1 4242`.
4. **Env vars match** — `RHINO_HOST` / `RHINO_PORT` are the same on
   both sides if you overrode the defaults.
5. Run the diagnostic: `./scripts/check-bridge.sh`.

### Bridge running but server still goes standalone

v0.5.1+: the server lazy-promotes to BRIDGE on the first tool call
once the plug-in becomes reachable.  No MCP server restart is required.

If promotion does not happen:

```bash
# Verify the plug-in is loaded inside Rhino — type in Rhino's command line:
#   _PluginManager           (look for "rhino-mcp", status "Loaded")
#
# Re-run the diagnostic; the plug-in should respond to ping:
./scripts/check-bridge.sh
```

### "Tool 'X' requires Rhino bridge mode."

Server started in standalone mode before the bridge was up.
Start the bridge in Rhino first, then restart the server:

```bash
./scripts/run.sh --bridge
# Or with automatic fallback (connector mode):
./scripts/run.sh --connector --bridge
```

### "Invalid parameter: axis" on `rhino_cylinder`

`rhino3dm` cannot place a circle on an arbitrary plane in standalone mode.
Use the world-Z axis (`{x:0,y:0,z:1}`) or switch to bridge mode.

### "non-3DM" import error

`rhino_import` only handles `.3dm` in standalone.
STEP/IGES/DXF imports require Rhino's importers — use bridge mode.

### MCP stdio transport corrupted

JSON-decode errors in Claude Desktop mean something is writing to stdout. `rhino-mcp` logs to stderr only.
Run with `RHINO_MCP_LOG_LEVEL=DEBUG` to confirm.

### Grasshopper bake is empty

- Run `gh_run` before `gh_bake_to_rhino`
- Check component output with `gh_get_parameter`
- Some components emit data, not geometry

### Multiple Rhino instances — wrong document responding (v0.6)

Symptoms: tools edit the *other* open Rhino document, or
`rhino_bridge_list_instances` shows 0 or 1 instance when 2+ are running.

Checks:

1. List discovered listeners — they live in `RHINO_MCP_LISTENER_DIR`
   (`${TMPDIR:-/tmp}/rhino-mcp-listeners` by default; `%LOCALAPPDATA%/rhino-mcp/listeners` on Windows):

   ```bash
   ls /tmp/rhino-mcp-listeners/   # or %LOCALAPPDATA%\rhino-mcp\listeners\
   ```

   One JSON per `{pid}-{port}` is expected.

2. If only one file exists despite two Rhinos running, the second
   Rhino loaded an older plugin build (pre-v0.6, no announcement
   writer). Rebuild and reload:

   ```bash
   dotnet build rhino_plugin/csharp -c Release
   ```

3. Switch which Rhino receives calls:

   ```text
   rhino_bridge_list_instances()
   rhino_bridge_select_instance(doc_path_contains="site.3dm")
   ```

4. Stale entries (Rhino crashed without cleaning up): the next
   `rhino_bridge_list_instances` call with `stale_cleanup=true`
   (default) deletes JSON files whose PID is gone.

### `rhino_execute_csharp` rejected before running

Error message includes
`C# execution is disabled. Set RHINO_MCP_ALLOW_CSHARP=1`. The tool is
gated behind an opt-in env var. Set it on the **Rhino process side**
(or wherever the bridge plugin lives), then restart:

```bash
RHINO_MCP_ALLOW_CSHARP=1 /Applications/Rhino\ 8.app/Contents/MacOS/Rhinoceros
```

The gate is intentional — Roslyn scripts have full RhinoCommon access.

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
