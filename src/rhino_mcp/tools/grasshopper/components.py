"""Grasshopper canvas component manipulation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.registry import Mode


class _AddComponentIn(BaseModel):
    name: str = Field(..., description="Component nickname or full name (e.g. 'Number Slider', 'Move').")
    x: float = Field(..., description="Canvas X coordinate.")
    y: float = Field(..., description="Canvas Y coordinate.")


class _ConnectIn(BaseModel):
    from_component: str = Field(..., description="Source component GUID.")
    from_output: str | int = Field(..., description="Output name or zero-based index.")
    to_component: str = Field(..., description="Target component GUID.")
    to_input: str | int = Field(..., description="Input name or zero-based index.")


class _DeleteIn(BaseModel):
    component_id: str


class _ListIn(BaseModel):
    filter: str | None = Field(None, description="Substring to filter component nicknames by.")


class _ClusterCreateIn(BaseModel):
    component_ids: list[str] = Field(..., min_length=1)
    name: str = Field(..., min_length=1)


class _ClusterExpandIn(BaseModel):
    cluster_id: str


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "GH: Add Component", "readOnlyHint": False})
    def gh_add_component(args: _AddComponentIn) -> dict[str, Any]:
        """Drop a Grasshopper component onto the active canvas."""
        return runtime().require_bridge().call("gh.component.add", args.model_dump())

    @mcp.tool(annotations={"title": "GH: Connect Components", "readOnlyHint": False})
    def gh_connect_components(args: _ConnectIn) -> dict[str, Any]:
        """Create a wire from one component output to another component input."""
        return runtime().require_bridge().call("gh.component.connect", args.model_dump())

    @mcp.tool(annotations={"title": "GH: Delete Component", "readOnlyHint": False, "destructiveHint": True})
    def gh_delete_component(args: _DeleteIn) -> dict[str, Any]:
        """Remove a component from the canvas."""
        return runtime().require_bridge().call("gh.component.delete", args.model_dump())

    @mcp.tool(annotations={"title": "GH: List Components", "readOnlyHint": True, "idempotentHint": True})
    def gh_component_list(args: _ListIn) -> dict[str, Any]:
        """List components currently on the active canvas (optionally filtered)."""
        return runtime().require_bridge().call("gh.component.list", args.model_dump())

    @mcp.tool(annotations={"title": "GH: Create Cluster", "readOnlyHint": False})
    def gh_cluster_create(args: _ClusterCreateIn) -> dict[str, Any]:
        """Group components into a named cluster."""
        return runtime().require_bridge().call("gh.cluster.create", args.model_dump())

    @mcp.tool(annotations={"title": "GH: Expand Cluster", "readOnlyHint": False})
    def gh_cluster_expand(args: _ClusterExpandIn) -> dict[str, Any]:
        """Expand a cluster back into its constituent components."""
        return runtime().require_bridge().call("gh.cluster.expand", args.model_dump())
