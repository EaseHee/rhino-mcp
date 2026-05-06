"""JSON-RPC error code matrix shared by bridge and tools.

The numeric codes mirror ``docs/dev/rpc-error-codes.md`` and the C# side
(``rhino_plugin/csharp/RpcErrorCodes.cs``). Symbol names are
mechanically the same in all three locations so a release-time drift
check is straightforward.

Tools that need to raise a bridge-domain error from Python should call
``raise_rpc_error(RpcErrorCode.X, ...)`` instead of constructing
``ToolError`` directly so the numeric code propagates to clients.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any

from rhino_mcp.utils.error_handling import ErrorCategory, ToolError


class RpcErrorCode(IntEnum):
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    HANDLER_ERROR = -32000

    BRIDGE_UI_TIMEOUT = -50001
    PAYLOAD_TOO_LARGE = -50002
    CHUNK_NOT_FOUND = -50003
    TOO_MANY_OBJECT_IDS = -50004
    BATCH_STEP_FAILED = -50005
    RENDER_JOB_UNKNOWN = -50006


_CATEGORY_BY_CODE: dict[RpcErrorCode, ErrorCategory] = {
    RpcErrorCode.PARSE_ERROR: ErrorCategory.PARAMETER,
    RpcErrorCode.INVALID_REQUEST: ErrorCategory.PARAMETER,
    RpcErrorCode.METHOD_NOT_FOUND: ErrorCategory.NOT_FOUND,
    RpcErrorCode.INVALID_PARAMS: ErrorCategory.PARAMETER,
    RpcErrorCode.INTERNAL_ERROR: ErrorCategory.INTERNAL,
    RpcErrorCode.HANDLER_ERROR: ErrorCategory.INTERNAL,
    RpcErrorCode.BRIDGE_UI_TIMEOUT: ErrorCategory.CONNECTION,
    RpcErrorCode.PAYLOAD_TOO_LARGE: ErrorCategory.INTERNAL,
    RpcErrorCode.CHUNK_NOT_FOUND: ErrorCategory.NOT_FOUND,
    RpcErrorCode.TOO_MANY_OBJECT_IDS: ErrorCategory.PARAMETER,
    RpcErrorCode.BATCH_STEP_FAILED: ErrorCategory.INTERNAL,
    RpcErrorCode.RENDER_JOB_UNKNOWN: ErrorCategory.NOT_FOUND,
}


def category_for(code: RpcErrorCode | int) -> ErrorCategory:
    """Map a JSON-RPC code to the closest local ``ErrorCategory``."""
    try:
        normalised = RpcErrorCode(int(code))
    except ValueError:
        return ErrorCategory.INTERNAL
    return _CATEGORY_BY_CODE.get(normalised, ErrorCategory.INTERNAL)


def raise_rpc_error(
    code: RpcErrorCode,
    message: str,
    *,
    hint: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    """Raise a ``ToolError`` carrying both the symbolic code and JSON-RPC numeric.

    Tools that detect a bridge-domain condition (oversized response,
    missing chunk, render job lookup miss, ...) should funnel through
    this helper. The ``ToolError.details`` payload preserves
    ``code = int(code)`` so MCP clients see the same numeric value the
    C# bridge would have emitted.
    """
    payload: dict[str, Any] = {"code": int(code)}
    if data:
        payload.update(data)
    raise ToolError(
        category_for(code),
        message,
        hint or _default_hint(code),
        details=payload,
    )


def _default_hint(code: RpcErrorCode) -> str:
    return _DEFAULT_HINTS.get(code, "Check the bridge log for context.")


_DEFAULT_HINTS: dict[RpcErrorCode, str] = {
    RpcErrorCode.BRIDGE_UI_TIMEOUT: (
        "Rhino UI thread is busy. Increase RHINO_MCP_UI_TIMEOUT or "
        "interrupt the foreground command."
    ),
    RpcErrorCode.PAYLOAD_TOO_LARGE: (
        "Response would exceed the bridge hard cap. Reduce the working "
        "set or page through results."
    ),
    RpcErrorCode.CHUNK_NOT_FOUND: (
        "Bridge chunk has expired (TTL 60 s) or never existed. Re-run "
        "the originating call."
    ),
    RpcErrorCode.TOO_MANY_OBJECT_IDS: (
        "Reduce the size of object_ids or split the call into batches."
    ),
    RpcErrorCode.BATCH_STEP_FAILED: (
        "Set on_error='continue' to keep going past failures, or fix "
        "the offending step."
    ),
    RpcErrorCode.RENDER_JOB_UNKNOWN: (
        "Render job has been evicted or completed; submit a new job."
    ),
}
