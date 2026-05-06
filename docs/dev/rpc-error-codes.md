# JSON-RPC Error Code Matrix

The bridge follows the JSON-RPC 2.0 spec for the standard `-326xx` codes and reserves the `-50000 .. -50099` range for server-domain errors.
Both sides emit codes from this table; clients should branch on the numeric code, not the message text.

## Standard codes

| Code | Symbol | Meaning |
|---|---|---|
| `-32700` | `ParseError` | Request line was not valid JSON. |
| `-32600` | `InvalidRequest` | JSON-RPC envelope is missing `method` or otherwise malformed. |
| `-32601` | `MethodNotFound` | The dispatcher has no handler for `method`. |
| `-32602` | `InvalidParams` | Pydantic validation rejected the input shape (max_length, missing field, ...). |
| `-32603` | `InternalError` | Unhandled exception inside the dispatcher framework. |
| `-32000` | `HandlerError` | Caught exception inside a handler (RhinoCommon throws, argument errors). The `data.trace` field carries the C# stack trace. |

## Bridge-domain codes (`-50000 .. -50099`)

| Code | Symbol | Meaning |
|---|---|---|
| `-50001` | `BridgeUiTimeout` | UI-thread dispatch exceeded `RHINO_MCP_UI_TIMEOUT` seconds. The dispatch may continue running on the UI thread; the client received an immediate error. |
| `-50002` | `PayloadTooLarge` | Single response would exceed the bridge hard cap (`RHINO_MCP_PAYLOAD_HARD_CAP`, default 256 MB). Use chunking. |
| `-50003` | `ChunkNotFound` | `rhino.bridge.fetch_chunk` was called with a `chunk_id` that has expired (TTL 60 s) or never existed. |
| `-50004` | `TooManyObjectIds` | The input array `object_ids` exceeded the per-tool max (default `MAX_OBJECT_IDS = 500`, override with `RHINO_MCP_MAX_OBJECT_IDS`). |
| `-50005` | `BatchStepFailed` | A step inside `rhino.batch.execute` failed when `on_error="stop"`. The `data.failed_index` and `data.cause` fields locate the failure. |
| `-50006` | `RenderJobUnknown` | `rhino.render.queue.status` / `cancel` referenced a `job_id` that does not exist or has been evicted. |

## Reserved ranges

- `-50100 .. -50199` — reserved for future Grasshopper-domain errors (solver
  failures, plugin load errors, DataTree shape mismatches).
- `-50200 .. -50299` — reserved for future BIM-domain errors
  (PropertySet schema violations, IFC mapping errors).

When introducing a new domain, take the next free 100-block and append a new section to this table.
Do not reuse existing codes for new meanings.

## Client mapping

`src/rhino_mcp/utils/rpc_errors.py` exposes `RpcErrorCode` (IntEnum) and `raise_rpc_error(code, message, data=None)` for symmetric mapping.
Tools should not raise raw `ToolError` for new bridge-domain conditions; route through `raise_rpc_error` so the symbol stays in lockstep with the C# constants.

## C# constants

`rhino_plugin/csharp/RpcErrorCodes.cs` mirrors this table as `const int` fields.
Both sides are kept in sync by `release-coordinator` agent (planned: matrix drift check on release).
