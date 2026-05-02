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


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "GH: Read DataTree", "readOnlyHint": True})
    def gh_data_tree_get(args: _GetIn) -> dict[str, Any]:
        """Read a component output as a DataTree (list of branches)."""
        return runtime().require_bridge().call("gh.data_tree.get", args.model_dump())

    @mcp.tool(annotations={"title": "GH: Write DataTree", "readOnlyHint": False})
    def gh_data_tree_set(args: _SetIn) -> dict[str, Any]:
        """Push a DataTree into a component input."""
        return runtime().require_bridge().call("gh.data_tree.set", args.model_dump())
