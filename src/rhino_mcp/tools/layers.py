"""Layer, group, and per-object selection tools.

Block / instance authoring lives in ``tools/blocks.py``.
"""

from __future__ import annotations

import re
from typing import Any

import rhino3dm as r3
from pydantic import BaseModel, Field, field_validator

from rhino_mcp.models.geometry_types import ColorRGBA
from rhino_mcp.tools._helpers import MAX_OBJECT_IDS, doc, find_layer_index
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import not_found_error
from rhino_mcp.utils.registry import Mode


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )


class _LayerCreateIn(_DocArg):
    name: str = Field(..., min_length=1, description="Layer name (unique).")
    color: ColorRGBA | None = None
    visible: bool = True


class _LayerNameIn(_DocArg):
    name: str = Field(..., min_length=1)


class _LayerColorIn(_LayerNameIn):
    color: ColorRGBA


class _MoveToLayerIn(_DocArg):
    object_ids: list[str] = Field(..., min_length=1, max_length=MAX_OBJECT_IDS)
    layer: str


class _ObjectsIn(_DocArg):
    object_ids: list[str] = Field(..., min_length=1, max_length=MAX_OBJECT_IDS)


class _ObjectSelectIn(_DocArg):
    """Select objects by ID and/or attribute filters.

    All fields are optional but at least one filter must match for the
    selection to be non-empty. The standalone implementation tags matching
    objects with the ``rhino_mcp_selected`` user-string; bridge mode forwards
    to ``rhino.object.select`` and lets Rhino's selection state handle it.
    """

    object_ids: list[str] | None = Field(
        None,
        description="Restrict selection to these object IDs (validates each exists).",
    )
    name_pattern: str | None = Field(
        None,
        description="Glob-style pattern matched against object names (e.g. ``Wall_*``).",
    )
    layer: str | None = Field(
        None,
        description="Restrict to objects on this layer (exact name match).",
    )
    color: tuple[int, int, int] | None = Field(
        None,
        description="RGB triple matched against ``ObjectColor`` (only when ColorSource=ColorFromObject).",
    )
    object_type: str | None = Field(
        None,
        description=(
            "Filter by Rhino object type. Accepts canonical names like "
            "``Curve``, ``Brep``, ``Mesh``, ``Point``, ``Annotation``, "
            "``Surface``, ``Extrusion`` (case-insensitive)."
        ),
    )
    user_text: dict[str, str] | None = Field(
        None,
        description="Match objects whose user-text contains all listed key/value pairs.",
    )
    deselect_first: bool = Field(
        True,
        description="Clear the existing selection before applying filters.",
    )

    @field_validator("color")
    @classmethod
    def _check_color_range(cls, v: tuple[int, int, int] | None) -> tuple[int, int, int] | None:
        if v is None:
            return v
        if any(c < 0 or c > 255 for c in v):
            raise ValueError("color components must be in [0, 255]")
        return v


class _GroupIn(_DocArg):
    object_ids: list[str] = Field(..., min_length=1, max_length=MAX_OBJECT_IDS)
    name: str | None = None


def _find_layer(handle, name: str) -> int:
    idx = find_layer_index(handle, name)
    if idx is None:
        raise not_found_error("layer", name)
    return idx


_TYPE_ALIASES = {
    "curve": ("Curve", "PolyCurve", "NurbsCurve", "ArcCurve", "PolylineCurve", "LineCurve"),
    "surface": ("Surface", "NurbsSurface", "RevSurface", "PlaneSurface", "SumSurface"),
    "brep": ("Brep",),
    "mesh": ("Mesh",),
    "point": ("Point", "PointCloud"),
    "annotation": ("Text", "TextDot", "Dimension", "Leader"),
    "extrusion": ("Extrusion",),
}


def _kind_matches(kind: str, requested: str) -> bool:
    requested_lower = requested.lower()
    if kind.lower() == requested_lower:
        return True
    aliases = _TYPE_ALIASES.get(requested_lower, ())
    return kind in aliases


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Compile a glob (``*``, ``?``) pattern into a full-match regex."""
    parts: list[str] = []
    for ch in pattern:
        if ch == "*":
            parts.append(".*")
        elif ch == "?":
            parts.append(".")
        else:
            parts.append(re.escape(ch))
    return re.compile("^" + "".join(parts) + "$")


def _select_matching_ids(handle, args) -> list[str]:
    """Filter objects in ``handle`` against ``args`` and return matching IDs."""
    name_re = _glob_to_regex(args.name_pattern) if args.name_pattern else None
    color_match = tuple(args.color) if args.color else None

    if args.object_ids:
        # Validate provided IDs exist; respect remaining filters as a refine step.
        candidates = []
        for gid in args.object_ids:
            obj = handle.file3dm.Objects.FindId(gid)
            if obj is None:
                raise not_found_error("object", gid)
            candidates.append(obj)
    else:
        candidates = [handle.file3dm.Objects[i] for i in range(len(handle.file3dm.Objects))]

    matched: list[str] = []
    for obj in candidates:
        attrs = obj.Attributes
        if args.layer:
            idx = attrs.LayerIndex
            if not (0 <= idx < len(handle.file3dm.Layers)):
                continue
            if handle.file3dm.Layers[idx].Name != args.layer:
                continue
        if name_re is not None and not name_re.match(attrs.Name or ""):
            continue
        if color_match is not None:
            color = attrs.ObjectColor
            if color is None:
                continue
            if (color[0], color[1], color[2]) != color_match:
                continue
        if args.object_type and not _kind_matches(type(obj.Geometry).__name__, args.object_type):
            continue
        if args.user_text:
            ok = True
            for k, v in args.user_text.items():
                if obj.Geometry.GetUserString(k) != v:
                    ok = False
                    break
            if not ok:
                continue
        matched.append(str(attrs.Id))
    return matched


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Create Layer", "readOnlyHint": False})
    def rhino_layer_create(args: _LayerCreateIn) -> dict[str, Any]:
        """Create a layer with optional colour and visibility."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.layer.create", args.model_dump())
        h = doc(args.doc_id)
        layer = r3.Layer()
        layer.Name = args.name
        if args.color is not None:
            layer.Color = (args.color.r, args.color.g, args.color.b, args.color.a)
        layer.Visible = args.visible
        idx = h.file3dm.Layers.Add(layer)
        return {
            "summary": {"name": args.name, "index": idx, "doc_id": h.doc_id},
            "text": f"Created layer '{args.name}' at index {idx}",
        }

    @mcp.tool(annotations={"title": "Delete Layer", "readOnlyHint": False, "destructiveHint": True})
    def rhino_layer_delete(args: _LayerNameIn) -> dict[str, Any]:
        """Delete a layer by name (in standalone mode the layer is hidden + name-prefixed)."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.layer.delete", args.model_dump())
        h = doc(args.doc_id)
        idx = _find_layer(h, args.name)
        # rhino3dm Layers expose no Delete; the closest non-bridge option is to
        # hide the layer and rename it so subsequent finds skip it.
        layer = h.file3dm.Layers[idx]
        layer.Visible = False
        layer.Name = f"~deleted~{args.name}"
        return {"summary": {"name": args.name, "index": idx}, "text": f"Marked layer '{args.name}' deleted"}

    @mcp.tool(annotations={"title": "Set Layer Colour", "readOnlyHint": False})
    def rhino_layer_set_color(args: _LayerColorIn) -> dict[str, Any]:
        """Change a layer's display colour."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.layer.set_color", args.model_dump())
        h = doc(args.doc_id)
        idx = _find_layer(h, args.name)
        h.file3dm.Layers[idx].Color = (args.color.r, args.color.g, args.color.b, args.color.a)
        return {"summary": {"name": args.name, "color": args.color.model_dump()}, "text": f"Set colour for layer '{args.name}'"}

    @mcp.tool(annotations={"title": "Move Objects to Layer", "readOnlyHint": False})
    def rhino_object_move_to_layer(args: _MoveToLayerIn) -> dict[str, Any]:
        """Reassign one or more objects to a different layer (creating it if absent)."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.object.move_to_layer", args.model_dump())
        h = doc(args.doc_id)
        try:
            idx = _find_layer(h, args.layer)
        except Exception:
            layer = r3.Layer()
            layer.Name = args.layer
            idx = h.file3dm.Layers.Add(layer)
        moved: list[str] = []
        for gid in args.object_ids:
            obj = h.find_object(gid)
            attrs = obj.Attributes
            attrs.LayerIndex = idx
            geom = obj.Geometry
            h.file3dm.Objects.Delete(obj.Attributes.Id)
            new_id = h.file3dm.Objects.Add(geom, attrs)
            moved.append(h.add_index(new_id))
        return {"summary": {"object_ids": moved, "layer": args.layer}, "text": f"Moved {len(moved)} object(s) to '{args.layer}'"}

    @mcp.tool(annotations={"title": "Select Objects", "readOnlyHint": False})
    def rhino_object_select(args: _ObjectSelectIn) -> dict[str, Any]:
        """Select objects by ID and/or attribute filters.

        Filter fields combine with AND semantics. ``object_ids`` short-circuits
        the other filters when provided. Standalone mode marks matches with the
        ``rhino_mcp_selected`` user-string (since rhino3dm has no selection
        state); bridge mode delegates to Rhino's native selection.
        """
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.object.select", args.model_dump())
        h = doc(args.doc_id)
        matched_ids = _select_matching_ids(h, args)
        if args.deselect_first:
            for i in range(len(h.file3dm.Objects)):
                h.file3dm.Objects[i].Geometry.SetUserString("rhino_mcp_selected", "")
        for gid in matched_ids:
            obj = h.file3dm.Objects.FindId(gid)
            if obj is not None:
                obj.Geometry.SetUserString("rhino_mcp_selected", "1")
        return {
            "summary": {"object_ids": matched_ids, "count": len(matched_ids)},
            "text": f"Selected {len(matched_ids)} object(s)",
        }

    @mcp.tool(annotations={"title": "Delete Objects", "readOnlyHint": False, "destructiveHint": True})
    def rhino_object_delete(args: _ObjectsIn) -> dict[str, Any]:
        """Delete the given objects from the document."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.object.delete", args.model_dump())
        h = doc(args.doc_id)
        deleted: list[str] = []
        for gid in args.object_ids:
            obj = h.find_object(gid)
            h.file3dm.Objects.Delete(obj.Attributes.Id)
            # rhino3dm's Delete returns None; verify by re-querying.
            if h.file3dm.Objects.FindId(gid) is None:
                deleted.append(gid)
        return {"summary": {"deleted": deleted}, "text": f"Deleted {len(deleted)} object(s)"}

    @mcp.tool(annotations={"title": "Group Objects", "readOnlyHint": False})
    def rhino_group(args: _GroupIn) -> dict[str, Any]:
        """Group objects together under a (named) group."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.group.create", args.model_dump())
        h = doc(args.doc_id)
        group = r3.Group()
        if args.name is not None:
            group.Name = args.name
        h.file3dm.Groups.Add(group)
        # rhino3dm's Groups.Add returns None; fish the assigned index out of
        # the Group instance after insertion.
        group_index = h.file3dm.Groups[len(h.file3dm.Groups) - 1].Index
        for obj_id in args.object_ids:
            obj = h.find_object(obj_id)
            obj.Attributes.AddToGroup(group_index)
        return {
            "summary": {"group_index": group_index, "object_ids": args.object_ids, "name": args.name},
            "text": f"Created group {group_index} with {len(args.object_ids)} member(s)",
        }

