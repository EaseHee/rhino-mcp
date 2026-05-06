"""Grasshopper DataTree read/write."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from rhino_mcp.models.grasshopper_types import GhDataTreePath, GhParameterValue
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.registry import Mode


class _GetIn(BaseModel):
    component_id: str
    output: str | int = Field(0)


class _SetIn(BaseModel):
    component_id: str
    input: str | int = Field(0)
    branches: list[tuple[GhDataTreePath, list[GhParameterValue]]] = Field(
        ..., description="A list of (path, values) tuples."
    )


class _BatchGetIn(BaseModel):
    queries: list[_GetIn] = Field(..., min_length=1, max_length=500)


class _BatchSetIn(BaseModel):
    assignments: list[_SetIn] = Field(..., min_length=1, max_length=500)
    defer_solve: bool = Field(
        True,
        description=(
            "When True (default), suspend the GH solver while applying every "
            "assignment, then trigger a single recompute. Falls back to per-"
            "assignment recompute when False."
        ),
    )


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "GH: Read DataTree", "readOnlyHint": True})
    def gh_data_tree_get(args: _GetIn) -> dict[str, Any]:
        """Read a component output as a DataTree (list of branches)."""
        return runtime().require_bridge().call("gh.data_tree.get", args.model_dump())

    @mcp.tool(annotations={"title": "GH: Write DataTree", "readOnlyHint": False})
    def gh_data_tree_set(args: _SetIn) -> dict[str, Any]:
        """Push a DataTree into a component input."""
        return runtime().require_bridge().call("gh.data_tree.set", args.model_dump())

    @mcp.tool(annotations={"title": "GH: Read DataTree (batch)", "readOnlyHint": True})
    def gh_data_tree_get_batch(args: _BatchGetIn) -> dict[str, Any]:
        """Read multiple component outputs in a single bridge round-trip."""
        return runtime().require_bridge().call(
            "gh.data_tree.get_batch", args.model_dump()
        )

    @mcp.tool(annotations={"title": "GH: Write DataTree (batch)", "readOnlyHint": False})
    def gh_data_tree_set_batch(args: _BatchSetIn) -> dict[str, Any]:
        """Apply many DataTree assignments at once with a single GH solve.

        With ``defer_solve=True`` (default) the GH document is paused while
        the assignments are applied and recomputed exactly once at the end —
        critical for parameter sweeps where N independent ``set`` calls
        would otherwise trigger N solver runs.
        """
        return runtime().require_bridge().call(
            "gh.data_tree.set_batch", args.model_dump()
        )
