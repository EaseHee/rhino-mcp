# Troubleshooting

## Quick diagnostic

```bash
./scripts/check-bridge.sh
```

Prints a PASS / FAIL / WARN verdict for every layer of the bridge detection stack (TCP port, JSON-RPC ping, mode detection) and shows the fix for each failure.
When the bridge answers, it also prints the running Rhino major, the major the plug-in was built for, and warns when they differ.

---

## Bridge setup inside Rhino 8 / Rhino 9

The most common reason `rhino-mcp` starts in standalone mode is that the **C# bridge plugin is not loaded in Rhino**.

### Step 1 — Get the plugin

Install it from the Rhino Package Manager (pick the `rh9` package in Rhino 9 and `rh8` in Rhino 8), or build it locally:

```bash
./scripts/build-plugin.sh --release              # Rhino 9 (default)
./scripts/build-plugin.sh --release --rhino=8    # Rhino 8
./scripts/build-plugin.sh --release --rhino=both --no-install   # build only
```

The script wraps `dotnet build rhino_plugin/csharp -c Release -p:RhinoMajor=<8|9>` and emits `rhino_plugin/csharp/bin/rh<N>/Release/net8.0/rhino-mcp.rhp`.
When `/Applications/Rhino <N>.app` (macOS) or `%APPDATA%/McNeel/Rhinoceros/<N>.0/` (Windows) exists, the build copies the plug-in there.

### Step 2 — Load the .rhp

Drag-and-drop the `.rhp` onto a Rhino viewport, or open `_PluginManager` and click *Install...*.
The plugin is loaded once and survives Rhino restarts.
You can verify with `_-PluginManager` and looking for the `rhino-mcp` entry.

On **success** the Rhino command history shows:

```
[rhino-mcp] Plugin loaded. Type "_McpInstall" to register rhino-mcp with Claude Desktop, Claude Code, Codex or Antigravity.
[rhino-mcp] listening on tcp://127.0.0.1:4242 (protocol=...)
```

A second Rhino instance takes the next free port (4243, 4244, … up to 4257).

### Step 3 — Register the server with your MCP client

Type `_McpInstall` in Rhino and pick the clients, or run `rhino-mcp install --client detected` in a terminal.
See [installation.md](installation.md#register-the-server-with-your-mcp-client) for every client and flag.

### Step 4 — Verify connectivity

```bash
./scripts/check-bridge.sh
```

Look for "Bridge responded to ping" with the Rhino / GH version printed.

---

## Transport reference

The C# plug-in listens on **TCP only**: `127.0.0.1:4242`, or the next free port up to 4257 when several Rhino instances run.
The server finds every instance through the listener announcement files (see *Multiple Rhino instances* below) and `RHINO_HOST` / `RHINO_PORT` (default `localhost:4242`).

For compatibility with the pre-0.4 Python bridge, the server still probes a Unix socket (`/tmp/rhino_mcp.sock` when the file exists, macOS / Linux) or a named pipe (`\\.\pipe\rhino_mcp`, Windows) before TCP.
The current plug-in serves neither, so skip the probe when it slows start-up:

```bash
RHINO_MCP_TRANSPORT_KIND=tcp uv run rhino-mcp
```

---

## Common failures

### "Cannot reach Rhino bridge."

Checklist:

1. **Rhino 8 or Rhino 9 is running**.
2. **The `rhino-mcp.rhp` C# plug-in is loaded**: install it via the Rhino package manager, or build it locally with `./scripts/build-plugin.sh --release`.
   The plug-in auto-starts the bridge on `OnLoad`; no script execution is required.
3. **TCP port is reachable**: default `127.0.0.1:4242`. Check with `nc -z 127.0.0.1 4242`.
4. **Env vars match**: `RHINO_HOST` / `RHINO_PORT` point at the instance you want if you overrode the defaults.
5. Run the diagnostic: `./scripts/check-bridge.sh`.

### Bridge running but server still goes standalone

v0.5.1+: the server lazy-promotes to BRIDGE on the first bridge-only tool call once the plug-in becomes reachable.
Since v0.7.0 a dual-mode tool whose standalone path cannot serve the request re-detects the bridge too and retries on it.
No MCP server restart is required.

If promotion does not happen:

```bash
# Verify the plug-in is loaded inside Rhino — type in Rhino's command line:
#   _PluginManager           (look for "rhino-mcp", status "Loaded")
#
# Re-run the diagnostic; the plug-in should respond to ping:
./scripts/check-bridge.sh
```

Under `RHINO_MCP_FORCE_MODE=standalone` neither MCP resources nor dual-mode tools promote; bridge-only tools still try to reach the bridge when called.

### "Tool 'X' requires Rhino bridge mode."

The operation needs RhinoCommon (for example `rhino_import` of a non-3DM file, or `rhino_export_step`) and no bridge was reachable.
Before returning this error the server re-detects the bridge (at most once every `RHINO_MCP_REDETECT_COOLDOWN` seconds, default 5) and, when the plug-in answers, runs the tool on the bridge instead.
So load the plug-in and call the tool again; if the error comes back right away, wait out the cooldown.
Under `RHINO_MCP_FORCE_MODE=standalone` no re-detection happens; remove it and restart the server.

### "Plug-in was built for Rhino N" warning

```
Bridge on tcp://... runs in Rhino 9 but the plug-in was built for Rhino 8. Install the rh9 package from the Rhino Package Manager.
```

A `net8.0` build for the other major usually still loads (Rhino 9 runs .NET 10 and rolls forward), but RhinoCommon API differences are not covered.
Install the matching package, or rebuild with `./scripts/build-plugin.sh --release --rhino=<running major>`.
The Rhino command line shows the same note when the plug-in loads.

### `_McpInstall` reports "No launcher provides rhino-mcp X or newer"

`_McpInstall` needs a server at least as new as the plug-in.
It runs `--version` on every launcher it finds (uvx with `--from rhino3dm-mcp>=<plug-in version>`, then each `rhino-mcp` script on PATH and in `~/.local/bin`, then each `python3` / `python` with `-m rhino_mcp.server`) and uses the first one that qualifies.
Each skipped launcher is printed with the reason, for example `no rhino3dm-mcp>=0.7.0 on PyPI yet` or `server 0.6.0 is older than 0.7.0`.

When none qualifies (typically before the release reaches PyPI), install the server from a local checkout and run `_McpInstall` again:

```bash
uv tool install --force --from /path/to/rhino-mcp rhino3dm-mcp   # puts rhino-mcp in ~/.local/bin
```

After the release is on PyPI, `uv tool upgrade rhino3dm-mcp` (or `uvx --refresh rhino3dm-mcp --version`) is enough.
The registered entry points at the launcher that passed the check: `uvx --from rhino3dm-mcp>=<version> rhino3dm-mcp`, or the absolute path of that installation's own `rhino-mcp` script.

### A client does not show the rhino-mcp tools

- Check the registration state: `rhino-mcp install --list-clients`.
  `error` means the config file could not be parsed; fix it or restore a `.bak.<timestamp>` copy next to it.
- Restart the client after installing (Claude Desktop, Codex and Antigravity read the config at start-up).
- Claude Code: `claude mcp list` should list `rhino-mcp` in the user scope.
- `RHINO_MCP_TOOLSETS` in the entry's `env` hides groups; unset it, or add the group you need (`core,bim,freeform,gh,render,scripting,docs`).

### 3dm file opens in Rhino but not in standalone mode

rhino3dm 8.35 reads files up to archive version 90 (Rhino 9).
For a newer file the error reports `archive_version` and suggests bridge mode or re-saving in an older format.
`unreadable or corrupt` with a known version usually means a truncated file.

### McNeel RhinoMCP is also installed

Rhino 9's built-in RhinoMCP (`MCPStart` / `MCPConnect`) uses HTTP port 10500, and rhino-mcp uses TCP 4242 and upward, so both can run at once.
Register them under different names in the MCP client (rhino-mcp uses `rhino-mcp` by default) so their entries do not overwrite each other.

### Viewport capture returns no image

`rhino_screenshot`, `rhino_viewport_preview` and `rhino_viewport_image` fail with "Viewport capture returned no image" when the plug-in did not send image data.
An older plug-in build ignores the inline-image request; update the plug-in to the version matching the server.
With a current plug-in, make sure a viewport is visible and retry.
Pass `include_image=false` with a `path` to save the file without returning the image.

### "Invalid parameter: axis" on `rhino_cylinder`

`rhino3dm` cannot place a circle on an arbitrary plane in standalone mode.
Use the world-Z axis (`{x:0,y:0,z:1}`) or switch to bridge mode.

### "non-3DM" import error

`rhino_import` only handles `.3dm` in standalone.
STEP/IGES/DXF imports require Rhino's importers — use bridge mode.

### MCP stdio transport corrupted

JSON-decode errors in the MCP client mean something is writing to stdout. `rhino-mcp` logs to stderr only.
Run with `RHINO_MCP_LOG_LEVEL=DEBUG` to confirm.

### Grasshopper bake is empty

- Run `gh_run` before `gh_bake_to_rhino`
- Check component output with `gh_get_parameter`
- Some components emit data, not geometry

### Multiple Rhino instances — wrong document responding (v0.6)

Symptoms: tools edit the *other* open Rhino document, or `rhino_bridge_list_instances` shows 0 or 1 instance when 2+ are running.

Checks:

1. List discovered listeners — they live in `RHINO_MCP_LISTENER_DIR` (`${TMPDIR:-/tmp}/rhino-mcp-listeners` by default; `%LOCALAPPDATA%/rhino-mcp/listeners` on Windows):

   ```bash
   ls /tmp/rhino-mcp-listeners/   # or %LOCALAPPDATA%\rhino-mcp\listeners\
   ```

   One JSON per `{pid}-{port}` is expected.

2. If only one file exists despite two Rhinos running, the second Rhino loaded an older plugin build (pre-v0.6, no announcement writer).
   Rebuild and reload:

   ```bash
   ./scripts/build-plugin.sh --release --rhino=9   # or --rhino=8
   ```

3. Switch which Rhino receives calls:

   ```text
   rhino_bridge_list_instances()
   rhino_bridge_select_instance(doc_path_contains="site.3dm")
   ```

4. Stale entries (Rhino crashed without cleaning up): the next `rhino_bridge_list_instances` call with `stale_cleanup=true` (default) deletes JSON files whose PID is gone.

### `rhino_execute_csharp` rejected before running

Error message includes `C# execution is disabled. Set RHINO_MCP_ALLOW_CSHARP=1`.
The tool is gated behind an opt-in env var that the **rhino-mcp server** reads, so set it in the `env` block of the MCP client entry (or the shell that starts the server) and restart the server:

```json
"env": { "RHINO_MCP_TRANSPORT": "stdio", "RHINO_MCP_ALLOW_CSHARP": "1" }
```

`rhino-mcp install --force` keeps user-added env keys such as this one.
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

# Only some tool groups:
./scripts/run.sh --toolsets core,gh

# Bridge mode with debug logs:
RHINO_MCP_FORCE_MODE=bridge RHINO_MCP_LOG_LEVEL=DEBUG uv run rhino-mcp

# Client registration state:
uv run rhino-mcp install --list-clients

# Introspect schemas with MCP Inspector:
npx @modelcontextprotocol/inspector uv run rhino-mcp
```
