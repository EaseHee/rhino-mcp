# Manual Verification — Bridge Stability + Command-line Hardening (v0.4.2)

The unit suite covers the Python side of the bridge client (reconnect path, buffer reset, keepalive flag).
The C# bridge has no automated harness, so v0.4.2 ships with this scripted manual checklist.
Run after rebuilding `rhino-mcp.rhp` and re-installing into Rhino 8.

## Prerequisites

```bash
# 1. Build and install the latest plugin
dotnet build rhino_plugin/csharp -c Release
# Drag bin/Release/net8.0/rhino-mcp.rhp into Rhino, or use _PluginManager → Install.

# 2. Confirm the bridge is listening
RHINO_MCP_FORCE_MODE=bridge \
RHINO_MCP_LOG_LEVEL=DEBUG \
uv run rhino-mcp ping
# Expect: pong with rhino, grasshopper, protocol_version=1.1, connected_clients>=1
```

If `protocol_version` is missing in the pong, you are still running an older `.rhp`.
Reinstall before continuing.

## Scenario A — Ping flood (basic stability)

```bash
RHINO_MCP_FORCE_MODE=bridge \
uv run python -c "
from rhino_mcp.bridge.rhino_connection import BridgeClient
c = BridgeClient.auto(timeout=2.0)
assert c is not None, 'bridge unreachable'
for i in range(1000):
    pong = c.call('rhino.ping', {})
    assert 'rhino' in pong
print('OK', c.transport_name)
"
```

Expected: completes in <30 s, no `connection_error`, no warning lines from the plugin window.

## Scenario B — Idle keepalive

Run the client interactively:

```python
from rhino_mcp.bridge.rhino_connection import BridgeClient
import time
c = BridgeClient.auto(timeout=2.0)
c.call('rhino.ping', {})
time.sleep(90)            # leave the connection idle
print(c.call('rhino.ping', {}))   # must succeed; no reconnect
```

Expected: second ping succeeds without a reconnect log line.
Confirms SO_KEEPALIVE keeps the OS-side connection live across idle intervals.
Without keepalive, some VPN/router paths kill TCP after ~60 s — the upgrade should make those paths usable.

## Scenario C — UI-thread timeout

Reproduce with a synthetic long handler.
Easiest: open Rhino, run `_-Test_DialogBox` (any modal that pauses the UI thread), then from a shell:

```bash
RHINO_MCP_UI_TIMEOUT=5 \
uv run python -c "
from rhino_mcp.bridge.rhino_connection import BridgeClient
import time
c = BridgeClient.auto(timeout=2.0)
print(c.call('rhino.ping', {}))     # immediate OK
# now switch focus to Rhino, open a modal dialog, retry:
time.sleep(10)
print(c.call('rhino.ping', {}))     # should NOT hang
"
```

Expected: the second call returns within ~5 s with a JSON-RPC error `code = -50001` (`UI thread dispatch exceeded 5s`).
Before v0.4.2 the client would have received a successful but empty response and the dispatch would silently keep running.

## Scenario D — Screenshot bad arguments

```python
from rhino_mcp.bridge.rhino_connection import BridgeClient
c = BridgeClient.auto(timeout=2.0)

# Negative width
try:
    c.call('rhino.io.screenshot', {'path': '/tmp/x.png', 'width': -1, 'height': 720})
except Exception as exc:
    print('rejected as expected:', exc)
```

Expected:

1. Client receives a structured error (no UI side effect).
2. Rhino's command line shows **no `_Width` token left over**. Inspect
   visually — the bottom of the Rhino window should still display the
   default prompt.

Repeat with `path=""` and `path='C:\\bad"name.png'` (the latter to exercise the new quote rejection in `RequirePath`).

## Scenario E — Export bad path

```python
c.call('rhino.io.export_step', {'path': ''})
```

Expected: rejected before any RunScript is dispatched.
No leftover tokens on Rhino's command line.

## Scenario F — Concurrent client count

Open two terminals, each running `BridgeClient.auto()`.
Then:

```python
print(c.call('rhino.ping', {})['connected_clients'])
```

Expected: `connected_clients` reflects the actual count (>=2).
Closing one client and re-pinging should drop the number on the next tick.

## Reporting

Capture the Rhino command-line area as a screenshot for scenarios D / E and attach to the v0.4.2 release notes.
The remainder are observable through the MCP client logs (`RHINO_MCP_LOG_LEVEL=DEBUG`).
