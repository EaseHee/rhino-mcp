# Configuration

`rhino-mcp` is configured entirely by environment variables and a small set of CLI flags.
Everything else flows from those.

## CLI flags

```
rhino-mcp [--transport {stdio,http}] [--host HOST] [--port PORT] [--version]
```

`--transport` overrides `RHINO_MCP_TRANSPORT`. `--host` / `--port` are honoured only when the transport is HTTP.

## Environment variables

### Server transport (MCP side)

| Variable               | Default | Notes |
|------------------------|---------|-------|
| `RHINO_MCP_TRANSPORT`  | `stdio` | `stdio` (Claude Desktop) or `http` (Streamable HTTP). `streamable-http` is accepted as an alias of `http`. |
| `RHINO_MCP_LOG_LEVEL`  | `INFO`  | One of `DEBUG`, `INFO`, `WARNING`, `ERROR`. Logs always go to stderr. |

### Bridge connection (Rhino side)

| Variable                       | Default          | Notes |
|--------------------------------|------------------|-------|
| `RHINO_MCP_FORCE_MODE`         | _(auto)_         | `standalone` skips bridge detection; `bridge` requires the bridge to be reachable and aborts otherwise. |
| `RHINO_MCP_BRIDGE_OPTIONAL`    | `0`              | When `1` and `FORCE_MODE=bridge`, an unreachable bridge falls back to standalone instead of aborting. |
| `RHINO_MCP_BRIDGE_TIMEOUT`     | `5`              | Seconds the auto-detector waits for a bridge `ping` response. |
| `RHINO_MCP_RECONNECT_RETRIES`  | `3`              | Number of reconnect attempts after a transport failure (with exponential backoff). |
| `RHINO_MCP_REDETECT_COOLDOWN`  | `5`              | Minimum seconds between back-to-back lazy bridge re-detection attempts. |
| `RHINO_MCP_TRANSPORT_KIND`     | _(auto)_         | Forces a specific bridge transport: `pipe`, `unix`, or `tcp`. |
| `RHINO_HOST`                   | `localhost`      | TCP host of the bridge. |
| `RHINO_PORT`                   | `4242`           | TCP port of the bridge. |
| `RHINO_MCP_PIPE`               | `rhino_mcp`      | Named-pipe instance name (Windows). |
| `RHINO_MCP_SOCKET`             | _(XDG runtime)_  | Unix-socket path. Default is `$XDG_RUNTIME_DIR/rhino_mcp.sock`, or `/tmp/rhino_mcp.sock`. |
| `RHINO_MCP_KEEPALIVE_IDLE`     | `20`             | TCP keepalive idle seconds before the OS probes the peer. |
| `RHINO_MCP_KEEPALIVE_INTERVAL` | `10`             | TCP keepalive probe interval seconds. |
| `RHINO_MCP_LISTENER_DIR`       | _(auto)_         | Directory the C# plugin writes per-process announcement JSON files to (consumed by `rhino_bridge_list_instances`). Auto: `${TMPDIR:-/tmp}/rhino-mcp-listeners` on POSIX, `%LOCALAPPDATA%/rhino-mcp/listeners` on Windows. |

### Server side (C# bridge plugin)

| Variable                         | Default | Notes |
|----------------------------------|---------|-------|
| `RHINO_MCP_HEARTBEAT_INTERVAL`   | `10`    | Seconds between `rhino.heartbeat` notifications written by the bridge during long-running handlers (make2d, render, script execute, etc.). Keeps the socket lively so client-side keepalive does not give up. |
| `RHINO_MCP_UI_TIMEOUT`           | `30`    | Seconds the bridge waits for a UI-thread dispatch to complete before returning a timeout error. |
| `RHINO_MCP_SEND_TIMEOUT_MS`      | `30000` | Bridge socket send timeout in milliseconds. |

### Tool safety (Python side)

| Variable                          | Default | Notes |
|-----------------------------------|---------|-------|
| `RHINO_MCP_ALLOW_MODAL_COMMAND`   | _(off)_ | When `1`, disables the static check in `rhino_execute_python` that rejects modal `rs.Command(_Move / _Mirror / _Rotate / _Copy / _Scale / _SelLayer / _Layer _Assign)` patterns known to break the bridge. Use only for debugging. |
| `RHINO_MCP_ALLOW_CSHARP`          | _(off)_ | Gate for `rhino_execute_csharp`. Must be `1` for the tool to proceed; otherwise the call fails with a parameter error before any bridge round-trip. Set this only in trusted sessions — Roslyn scripts have full RhinoCommon access. |

### Multi-Rhino discovery (v0.6)

The C# plugin writes a per-process announcement file
(`{pid}-{port}.json`) into `RHINO_MCP_LISTENER_DIR` on load and refreshes
it on every document open / new / close. When `RHINO_PORT` is unset, the
plugin probes 4242, 4243, … upward and binds the first free port so two
or more Rhino instances on the same host coexist without manual config.
The Python side enumerates listeners via `rhino_bridge_list_instances`
and switches active endpoint with `rhino_bridge_select_instance`.

## Transport selection logic

1. The server decides its **MCP transport** (`stdio` vs HTTP) from `--transport` / `RHINO_MCP_TRANSPORT`.
2. The server decides its **runtime mode** (standalone vs bridge):
   - If `RHINO_MCP_FORCE_MODE` is set, that wins.
   - Otherwise, candidate bridge transports are tried in priority order (named pipe on Windows; unix socket on macOS/Linux; TCP fallback). The first one that accepts `rhino.ping` wins.
   - If none respond before the timeout, the server falls back to standalone.
3. Tool registration consults the runtime mode. Bridge-only tools are simply not registered when standalone.

## Per-deployment recipes

### Claude Desktop, no Rhino installed

```json
{ "rhino-mcp": { "command": "uvx", "args": ["rhino3dm-mcp"],
                 "env": {"RHINO_MCP_FORCE_MODE": "standalone"} } }
```

### Claude Desktop with a live Rhino on the same machine

Default config — auto-detection finds the bridge.

### Remote Rhino on a workstation, MCP server in Docker

```yaml
services:
  rhino-mcp:
    image: rhino-mcp:latest
    environment:
      RHINO_MCP_TRANSPORT: http
      RHINO_MCP_FORCE_MODE: bridge
      RHINO_MCP_TRANSPORT_KIND: tcp
      RHINO_HOST: workstation.local
      RHINO_PORT: 4242
    ports: ["8765:8765"]
```

### Headless CI

```bash
RHINO_MCP_FORCE_MODE=standalone pytest
```
