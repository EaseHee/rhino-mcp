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


class _ConnectManyIn(BaseModel):
    connections: list[_ConnectIn] = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Batch of wire definitions to add in one round-trip.",
    )
    stop_on_error: bool = Field(
        False,
        description=(
            "When False (default) the bridge attempts every wire and reports per-row "
            "status; when True the first failure aborts the batch."
        ),
    )


class _DeleteIn(BaseModel):
    component_id: str


class _ListIn(BaseModel):
    filter: str | None = Field(None, description="Substring to filter component nicknames by.")


class _ClusterCreateIn(BaseModel):
    component_ids: list[str] = Field(..., min_length=1)
    name: str = Field(..., min_length=1)


class _ClusterExpandIn(BaseModel):
    cluster_id: str


class _PluginListIn(BaseModel):
    pass


class _ComponentSearchIn(BaseModel):
    query: str | None = Field(
        None,
        description=(
            "Case-insensitive substring matched against component name, nickname, "
            "and subcategory. Empty/None returns the first 'limit' entries."
        ),
    )
    plugin: str | None = Field(
        None,
        description=(
            "Filter by source plugin (file name match, case-insensitive). Useful "
            "for narrowing to LunchBox / Ladybug / Pufferfish, etc."
        ),
    )
    category: str | None = Field(
        None,
        description="Filter by category or subcategory (case-insensitive substring).",
    )
    limit: int = Field(
        50, ge=1, le=500, description="Maximum number of rows returned in 'rows'."
    )


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "GH: Add Component", "readOnlyHint": False})
    def gh_add_component(args: _AddComponentIn) -> dict[str, Any]:
        """Drop a Grasshopper component onto the active canvas."""
        return runtime().require_bridge().call("gh.component.add", args.model_dump())

    @mcp.tool(annotations={"title": "GH: Connect Components", "readOnlyHint": False})
    def gh_connect_components(args: _ConnectIn) -> dict[str, Any]:
        """Create a wire from one component output to another component input."""
        return runtime().require_bridge().call("gh.component.connect", args.model_dump())

    @mcp.tool(annotations={"title": "GH: Connect Many", "readOnlyHint": False})
    def gh_connect_many(args: _ConnectManyIn) -> dict[str, Any]:
        """Add multiple wires in a single round-trip.

        Returns a per-row ``results`` array so partial failures are visible
        (each row carries ``status`` and, on error, ``error``).
        """
        return runtime().require_bridge().call(
            "gh.component.connect_many",
            {
                "connections": [c.model_dump() for c in args.connections],
                "stop_on_error": args.stop_on_error,
            },
        )

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

    @mcp.tool(annotations={"title": "GH: List Loaded Plugins", "readOnlyHint": True, "idempotentHint": True})
    def gh_plugin_list(args: _PluginListIn) -> dict[str, Any]:
        """Enumerate Grasshopper plugin libraries currently loaded.

        Returns one entry per ``GH_AssemblyInfo`` library: id, name, author,
        version, description, and the on-disk path. Useful for the LLM to
        discover whether the user has LunchBox / Ladybug / Kangaroo etc.
        installed before attempting to drop in a custom component.
        """
        return runtime().require_bridge().call("gh.plugin.list", args.model_dump())

    @mcp.tool(annotations={"title": "GH: Search Components", "readOnlyHint": True, "idempotentHint": True})
    def gh_components_search(args: _ComponentSearchIn) -> dict[str, Any]:
        """Search the Grasshopper component catalog (built-in + plugin-supplied).

        Returns ``rows`` of ``{guid, name, nickname, category, subcategory,
        description, plugin}`` and a ``summary`` block with match counts.
        Use this to find the GUID needed by ``gh_add_component`` before
        dropping a component on the canvas.
        """
        return runtime().require_bridge().call("gh.components.search", args.model_dump())
