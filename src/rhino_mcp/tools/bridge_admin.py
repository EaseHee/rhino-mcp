"""Bridge administration tools: enumerate live Rhino instances and switch endpoint.

These tools work in either runtime mode. ``list_instances`` only scans the
filesystem and does not require the bridge to be connected. ``select_instance``
swaps the host/port the next bridge call will target.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from rhino_mcp.bridge.discovery import (
    apply_endpoint,
    list_rhino_instances,
    select_endpoint,
)
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import parameter_error
from rhino_mcp.utils.logging import get_logger
from rhino_mcp.utils.registry import Mode

log = get_logger("bridge_admin")


class _ListInstancesIn(BaseModel):
    stale_cleanup: bool = Field(
        True,
        description="Delete announcement files whose owning PID is gone.",
    )
    probe_timeout: float = Field(
        0.5,
        ge=0.05,
        le=5.0,
        description="TCP probe timeout in seconds.",
    )


class _SelectInstanceIn(BaseModel):
    pid: int | None = Field(None, description="Select by Rhino process id.")
    port: int | None = Field(None, description="Select by bridge TCP port.")
    doc_path_contains: str | None = Field(
        None,
        description="Substring match against the document path or title (case-insensitive).",
    )
    index: int | None = Field(
        None,
        ge=0,
        description="Zero-based index into the alive-instances list.",
    )


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Bridge: List Rhino Instances", "readOnlyHint": True, "idempotentHint": True})
    def rhino_bridge_list_instances(args: _ListInstancesIn) -> dict[str, Any]:
        """Enumerate live Rhino bridge endpoints discovered via announcement files.

        Returns one row per running Rhino on this host. Each row carries
        ``pid``, ``host``, ``port``, ``doc_path``, ``doc_title``, version, and
        an ``alive`` flag derived from a cheap TCP probe.
        """
        rows = [
            i.to_dict()
            for i in list_rhino_instances(
                stale_cleanup=args.stale_cleanup,
                probe_timeout=args.probe_timeout,
            )
        ]
        rt = runtime()
        alive_count = sum(1 for r in rows if r.get("alive"))
        return {
            "summary": {
                "count": len(rows),
                "alive_count": alive_count,
                "current_mode": rt.mode.value,
            },
            "rows": rows,
            "row_count": len(rows),
            "text": f"Discovered {len(rows)} Rhino instance(s); {alive_count} reachable.",
        }

    @mcp.tool(annotations={"title": "Bridge: Select Rhino Instance", "readOnlyHint": False})
    def rhino_bridge_select_instance(args: _SelectInstanceIn) -> dict[str, Any]:
        """Switch the next bridge call to target a specific Rhino session.

        Exactly one selector among ``pid``, ``port``, ``doc_path_contains``,
        and ``index`` should be set. The active bridge client is closed; the
        next tool call goes through lazy promotion against the new endpoint.
        """
        selectors_set = sum(
            1
            for v in (args.pid, args.port, args.doc_path_contains, args.index)
            if v is not None
        )
        if selectors_set == 0:
            raise parameter_error(
                "selector",
                "Provide exactly one of: pid, port, doc_path_contains, index.",
            )
        if selectors_set > 1:
            raise parameter_error(
                "selector",
                "Provide only one selector; multiple were given.",
            )

        target = select_endpoint(
            pid=args.pid,
            port=args.port,
            doc_path_contains=args.doc_path_contains,
            index=args.index,
        )
        if target is None:
            raise parameter_error(
                "selector",
                "No live Rhino instance matched the selector. "
                "Call rhino_bridge_list_instances to see available endpoints.",
            )

        apply_endpoint(target)

        # Drop the current bridge client so the next require_bridge() reconnects.
        rt = runtime()
        if rt.bridge is not None:
            try:
                rt.bridge.close()
            except Exception:
                pass
            rt.bridge = None
            rt.mode = Mode.STANDALONE
            # Reset cooldown so promotion happens immediately on the next call.
            rt._last_redetect_at = 0.0

        return {
            "summary": {
                "selected": target.to_dict(),
                "current_mode": rt.mode.value,
            },
            "text": (
                f"Switched bridge endpoint to {target.host}:{target.port} "
                f"(pid={target.pid}, doc={target.doc_title or '<untitled>'})."
            ),
        }
