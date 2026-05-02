"""Pydantic models for Grasshopper canvas/component/data-tree shapes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class GhComponentRef(BaseModel):
    """Identifier for a component instance on the active canvas."""

    component_id: str = Field(..., description="GUID of the component on the canvas")


class GhParameterValue(BaseModel):
    """A single value to push into (or pulled from) a Grasshopper parameter."""

    type: Literal[
        "number",
        "integer",
        "boolean",
        "text",
        "point",
        "vector",
        "plane",
        "geometry_json",
    ] = Field(..., description="Discriminator for the payload")
    value: Any = Field(..., description="Type-specific payload (see `type`)")


class GhDataTreePath(BaseModel):
    """A Grasshopper data-tree branch path, e.g. ``{0;1;2}``."""

    indices: list[int] = Field(..., description="Branch indices, outer first")


class GhConnection(BaseModel):
    """A wire from one component output to another component input."""

    from_component: str = Field(..., description="Source component GUID")
    from_output: str | int = Field(..., description="Source output name or index")
    to_component: str = Field(..., description="Target component GUID")
    to_input: str | int = Field(..., description="Target input name or index")
