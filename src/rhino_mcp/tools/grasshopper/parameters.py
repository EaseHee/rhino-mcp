"""Grasshopper parameter and input-widget control."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from rhino_mcp.models.grasshopper_types import GhParameterValue
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.registry import Mode


class _GetIn(BaseModel):
    component_id: str
    output: str | int = Field(0, description="Output name or zero-based index.")


class _SetIn(BaseModel):
    component_id: str
    input: str | int = Field(0, description="Input name or zero-based index.")
    value: GhParameterValue


class _SliderIn(BaseModel):
    component_id: str
    value: float


class _PanelIn(BaseModel):
    component_id: str
    text: str


class _ToggleIn(BaseModel):
    component_id: str
    value: bool


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "GH: Get Parameter", "readOnlyHint": True})
    def gh_get_parameter(args: _GetIn) -> dict[str, Any]:
        """Read the current value of a component parameter."""
        return runtime().require_bridge().call("gh.parameter.get", args.model_dump())

    @mcp.tool(annotations={"title": "GH: Set Parameter", "readOnlyHint": False})
    def gh_set_parameter(args: _SetIn) -> dict[str, Any]:
        """Push a value into a component parameter."""
        return runtime().require_bridge().call("gh.parameter.set", args.model_dump())

    @mcp.tool(annotations={"title": "GH: Set Slider", "readOnlyHint": False})
    def gh_set_slider(args: _SliderIn) -> dict[str, Any]:
        """Set a Number Slider component to a numeric value."""
        return runtime().require_bridge().call("gh.parameter.set_slider", args.model_dump())

    @mcp.tool(annotations={"title": "GH: Set Panel", "readOnlyHint": False})
    def gh_set_panel(args: _PanelIn) -> dict[str, Any]:
        """Set the text contents of a Panel component."""
        return runtime().require_bridge().call("gh.parameter.set_panel", args.model_dump())

    @mcp.tool(annotations={"title": "GH: Set Boolean Toggle", "readOnlyHint": False})
    def gh_set_toggle(args: _ToggleIn) -> dict[str, Any]:
        """Set a Boolean Toggle component to true or false."""
        return runtime().require_bridge().call("gh.parameter.set_toggle", args.model_dump())
