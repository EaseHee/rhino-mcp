"""Generic bridge call batching.

A single ``rhino_batch_call`` tool dispatches N JSON-RPC methods in one
round-trip so massing / paneling / blocks workflows that emit dozens of
sequential bridge calls pay the network + UI-thread marshalling cost
only once. The bridge handler (``rhino.batch.execute``) runs every step
on Rhino's UI thread sequentially and returns per-row pass/fail in a
``results`` array.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from rhino_mcp.tools._helpers import bridge_call_batch
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import unsupported_in_standalone
from rhino_mcp.utils.registry import Mode

# Method names must address either the Rhino bridge surface or the
# Grasshopper surface — keep the gate narrow so a typo can't dispatch
# to an arbitrary string.
_METHOD_RE = re.compile(r"^(rhino|gh)\.[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)+$")


class _Step(BaseModel):
    method: str = Field(
        ...,
        description=(
            "Bridge JSON-RPC method name (NOT the MCP tool name). The bridge "
            "dispatcher uses 'rhino.<category>.<action>' or 'gh.<category>."
            "<action>' routes, e.g. 'rhino.layer.create', 'rhino.layer.delete', "
            "'rhino.query.document_summary', 'rhino.query.layer_list', "
            "'gh.component.add'. The MCP tool name (e.g. 'rhino_document_summary') "
            "is NOT a valid method here — translate to the dispatcher route by "
            "replacing the leading 'rhino_' with the namespaced form."
        ),
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON object passed verbatim to the bridge handler.",
    )


class _BatchCallIn(BaseModel):
    steps: list[_Step] = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Sequence of {method, params} entries dispatched in order.",
    )
    on_error: Literal["stop", "continue"] = Field(
        "stop",
        description=(
            "'stop' (default) aborts the batch on the first failure and raises; "
            "'continue' records the error in the results array and proceeds."
        ),
    )


def register(mcp: Any, mode: Mode) -> None:
    @mcp.tool(annotations={"title": "Bridge: Batch Call", "readOnlyHint": False})
    def rhino_batch_call(args: _BatchCallIn) -> dict[str, Any]:
        """Dispatch multiple bridge methods in a single round-trip.

        IMPORTANT: ``steps[].method`` is a **bridge dispatcher route**, not
        an MCP tool name. The MCP tool ``rhino_layer_create`` maps to the
        dispatcher route ``rhino.layer.create``; ``rhino_document_summary``
        maps to ``rhino.query.document_summary`` (NOT ``rhino.document.summary``).
        Standalone-only tools (``rhino_set_user_text`` etc. that have no
        ``bridge_call`` path) cannot be batched. A wrong route name returns
        an ``error`` row with ``HandlerError``; the batch aborts when
        ``on_error='stop'``.

        Measured impact (v0.6.x, localhost): direct sequential layer.create
        ~580ms/op vs batched ~340ms/op — N x ~240ms saved per batch (the
        MCP↔bridge round-trip cost paid once instead of N times). Effective
        for any workflow that issues >5 bridge calls back-to-back.

        Returns ``{summary: {total, ok, failed, on_error}, results: [...]}``
        where each ``results`` entry has ``index``, ``method``, ``status``
        (``"ok"`` | ``"error"``), and either ``result`` or ``error``.
        """
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_batch_call")

        for i, step in enumerate(args.steps):
            if not _METHOD_RE.match(step.method):
                from rhino_mcp.utils.error_handling import parameter_error

                raise parameter_error(
                    f"steps[{i}].method",
                    f"invalid method name {step.method!r}; expected 'rhino.*' or 'gh.*'",
                )

        result = bridge_call_batch(
            [{"method": s.method, "params": s.params} for s in args.steps],
            on_error=args.on_error,
        )

        summary = result.get("summary", {})
        ok = summary.get("ok", 0)
        failed = summary.get("failed", 0)
        total = summary.get("total", len(args.steps))
        text = (
            f"Batch executed: {ok}/{total} ok, {failed} failed "
            f"(on_error={args.on_error})."
        )
        result["text"] = text
        return result
