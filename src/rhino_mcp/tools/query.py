"""Document and object query tools.

Read-only tools for inspecting document state: object lists, layer tree,
object details, selection state, and user text metadata.
Standalone mode uses rhino3dm; bridge mode forwards to the C# plugin.
"""

from __future__ import annotations

from typing import Annotated, Any

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.tools._helpers import doc
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.registry import Mode
from rhino_mcp.utils.serialization import bbox_to_dict


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )


class _ListObjectsIn(_DocArg):
    layer: str | None = Field(None, description="Filter by layer name (optional).")
    kind: str | None = Field(
        None,
        description="Filter by object type: Point, Curve, Brep, Mesh, ... (optional).",
    )
    offset: Annotated[
        int,
        Field(
            ge=0,
            description="Skip this many filtered objects before returning results.",
        ),
    ] = 0
    limit: Annotated[
        int,
        Field(
            ge=1,
            le=500,
            description="Maximum number of objects in the response (paginate with ``offset``).",
        ),
    ] = 100


class _ObjectInfoIn(_DocArg):
    object_id: str


class _SelectedObjectsIn(_DocArg):
    include_attributes: bool = Field(False, description="Include colour, material, and other attributes.")


class _LayerListIn(_DocArg):
    pass


class _UserTextIn(_DocArg):
    object_id: str
    key: str | None = Field(None, description="Specific key to read (omit for all).")


class _SetUserTextIn(_DocArg):
    object_id: str
    key: str
    value: str


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]

    @mcp.tool(annotations={"title": "List Objects", "readOnlyHint": True})
    async def rhino_list_objects(args: _ListObjectsIn) -> dict[str, Any]:
        """List objects in the document with optional layer/type filter.

        Returns up to ``limit`` objects starting at ``offset`` (after filters).
        The response carries a ``pagination`` block — ``{total, offset, limit,
        returned, has_more}`` — so the caller can iterate without guessing.

        Async so concurrent ``rhino_*`` queries don't block FastMCP's event
        loop while the bridge round-trip is in flight.
        """
        if runtime().mode is Mode.BRIDGE:
            return await runtime().require_bridge().async_call(
                "rhino.query.list_objects", args.model_dump()
            )
        h = doc(args.doc_id)
        objects: list[dict[str, Any]] = []
        obj_count = len(h.file3dm.Objects)
        layer_count = len(h.file3dm.Layers)
        # First pass: count total filtered objects (for accurate pagination).
        total_matched = 0
        for i in range(obj_count):
            obj = h.file3dm.Objects[i]
            kind = type(obj.Geometry).__name__
            layer_idx = obj.Attributes.LayerIndex
            layer_name = (
                h.file3dm.Layers[layer_idx].Name
                if 0 <= layer_idx < layer_count
                else ""
            )
            if args.layer and layer_name != args.layer:
                continue
            if args.kind and kind.lower() != args.kind.lower():
                continue
            total_matched += 1
            # Slice the matched stream by [offset, offset+limit).
            position = total_matched - 1
            if position < args.offset or len(objects) >= args.limit:
                continue
            bbox = obj.Geometry.GetBoundingBox()
            objects.append(
                {
                    "object_id": str(obj.Attributes.Id),
                    "kind": kind,
                    "layer": layer_name,
                    "name": obj.Attributes.Name or "",
                    "bbox": bbox_to_dict(bbox),
                }
            )

        pagination = {
            "total": total_matched,
            "offset": args.offset,
            "limit": args.limit,
            "returned": len(objects),
            "has_more": args.offset + len(objects) < total_matched,
        }
        return {
            "summary": {"count": len(objects), "offset": args.offset, "objects": objects},
            "pagination": pagination,
            "text": (
                f"{len(objects)}/{total_matched} objects listed "
                f"(offset={args.offset}, has_more={pagination['has_more']})"
            ),
        }

    @mcp.tool(annotations={"title": "Get Object Info", "readOnlyHint": True})
    def rhino_object_info(args: _ObjectInfoIn) -> dict[str, Any]:
        """Get detailed info about a single object (geometry type, layer, bbox, etc.)."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.query.object_info", args.model_dump())
        h = doc(args.doc_id)
        obj = h.file3dm.Objects.FindId(args.object_id)
        if obj is None:
            from rhino_mcp.utils.error_handling import not_found_error
            raise not_found_error("object", args.object_id)
        geom = obj.Geometry
        kind = type(geom).__name__
        bbox = geom.GetBoundingBox()
        layer_idx = obj.Attributes.LayerIndex
        layer_name = ""
        if 0 <= layer_idx < len(h.file3dm.Layers):
            layer_name = h.file3dm.Layers[layer_idx].Name

        info: dict[str, Any] = {
            "object_id": str(obj.Attributes.Id),
            "kind": kind,
            "layer": layer_name,
            "name": obj.Attributes.Name or "",
            "bbox": bbox_to_dict(bbox),
            "is_valid": geom.IsValid,
        }

        if isinstance(geom, r3.Curve):
            info["is_closed"] = geom.IsClosed
            info["domain"] = [geom.Domain.Min, geom.Domain.Max]
            info["length"] = geom.GetLength()
        elif isinstance(geom, r3.Brep):
            info["face_count"] = len(geom.Faces)
            info["edge_count"] = len(geom.Edges)
            info["is_solid"] = geom.IsSolid
        elif isinstance(geom, r3.Mesh):
            info["vertex_count"] = len(geom.Vertices)
            info["face_count"] = len(geom.Faces)

        return {"summary": info, "text": f"{kind}: {args.object_id}"}

    @mcp.tool(annotations={"title": "Document Summary", "readOnlyHint": True})
    async def rhino_document_summary(args: _DocArg) -> dict[str, Any]:
        """Get a high-level summary of the document (object counts, layers, etc.)."""
        if runtime().mode is Mode.BRIDGE:
            return await runtime().require_bridge().async_call(
                "rhino.query.document_summary", args.model_dump()
            )
        h = doc(args.doc_id)
        f = h.file3dm
        obj_count = len(f.Objects)
        layer_count = len(f.Layers)
        type_counts: dict[str, int] = {}
        for i in range(obj_count):
            kind = type(f.Objects[i].Geometry).__name__
            type_counts[kind] = type_counts.get(kind, 0) + 1

        layers = []
        for i in range(layer_count):
            lay = f.Layers[i]
            color = lay.Color
            r_, g_, b_ = (color[0], color[1], color[2]) if isinstance(color, tuple) else (
                color.R, color.G, color.B
            )
            layers.append({
                "index": i,
                "name": lay.Name,
                "color": {"r": r_, "g": g_, "b": b_},
                "visible": lay.Visible,
            })

        # Extended document hygiene fields (units / tolerances / base point /
        # layer-tree depth) so the LLM can verify it's modeling at the right
        # scale before issuing geometry calls.
        s = f.Settings
        from rhino_mcp.tools.document_config import _UNITS_ENUM_TO_NAME

        unit_int = int(s.ModelUnitSystem)
        units_name = _UNITS_ENUM_TO_NAME.get(unit_int, str(s.ModelUnitSystem))
        layer_tree_depth = 0
        for i in range(layer_count):
            full = f.Layers[i].FullPath if hasattr(f.Layers[i], "FullPath") else f.Layers[i].Name
            if full:
                depth = full.count("::") + 1
                if depth > layer_tree_depth:
                    layer_tree_depth = depth

        return {
            "summary": {
                "total_objects": obj_count,
                "type_counts": type_counts,
                "layer_count": layer_count,
                "layers": layers,
                "units": units_name,
                "tolerances": {
                    "absolute": s.ModelAbsoluteTolerance,
                    "angle_degrees": s.ModelAngleToleranceDegrees,
                    "relative": s.ModelRelativeTolerance,
                },
                "base_point": {
                    "x": s.ModelBasePoint.X,
                    "y": s.ModelBasePoint.Y,
                    "z": s.ModelBasePoint.Z,
                },
                "layer_tree_depth": layer_tree_depth,
            },
            "text": f"Document: {obj_count} objects, {layer_count} layers, units={units_name}"
        }

    @mcp.tool(annotations={"title": "List Layers", "readOnlyHint": True})
    async def rhino_layer_list(args: _LayerListIn) -> dict[str, Any]:
        """List all layers with their properties (color, visibility, object count)."""
        if runtime().mode is Mode.BRIDGE:
            return await runtime().require_bridge().async_call(
                "rhino.query.layer_list", args.model_dump()
            )
        h = doc(args.doc_id)
        f = h.file3dm
        obj_count = len(f.Objects)
        layer_count = len(f.Layers)

        # Count objects per layer
        layer_obj_count: dict[int, int] = {}
        for i in range(obj_count):
            idx = f.Objects[i].Attributes.LayerIndex
            layer_obj_count[idx] = layer_obj_count.get(idx, 0) + 1

        layers = []
        for i in range(layer_count):
            lay = f.Layers[i]
            color = lay.Color
            r_, g_, b_ = (color[0], color[1], color[2]) if isinstance(color, tuple) else (
                color.R, color.G, color.B
            )
            layers.append({
                "index": i,
                "name": lay.Name,
                "full_path": lay.FullPath if hasattr(lay, 'FullPath') else lay.Name,
                "color": {"r": r_, "g": g_, "b": b_},
                "visible": lay.Visible,
                "locked": lay.IsLocked,
                "object_count": layer_obj_count.get(i, 0),
            })

        return {
            "summary": {"count": len(layers), "layers": layers},
            "text": f"{len(layers)} layers"
        }

    if mode in (Mode.BRIDGE, Mode.BOTH) and runtime().mode is not Mode.STANDALONE:
        @mcp.tool(annotations={"title": "Get Selected Objects", "readOnlyHint": True})
        def rhino_get_selected_objects(args: _SelectedObjectsIn) -> dict[str, Any]:
            """Get information about the currently selected objects in Rhino.

            Bridge-only — standalone mode has no selection concept.
            When ``include_attributes`` is True, colour, material, and other
            attributes are included in the output.
            """
            result = runtime().require_bridge().call(
                "rhino.query.selected_objects",
                {"include_attributes": args.include_attributes},
            )
            count = result.get("count", 0)
            return {
                "summary": result,
                "text": f"{count} object(s) selected.",
            }

    @mcp.tool(annotations={"title": "Get User Text", "readOnlyHint": True})
    def rhino_get_user_text(args: _UserTextIn) -> dict[str, Any]:
        """Read user text (key-value metadata) attached to an object."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.query.get_user_text", args.model_dump())
        h = doc(args.doc_id)
        obj = h.file3dm.Objects.FindId(args.object_id)
        if obj is None:
            from rhino_mcp.utils.error_handling import not_found_error
            raise not_found_error("object", args.object_id)
        if args.key:
            val = obj.Attributes.GetUserString(args.key)
            return {"summary": {"key": args.key, "value": val or ""}}
        # Return all user strings
        keys = obj.Attributes.GetUserStrings()
        data = {}
        if keys:
            for k in keys.AllKeys:
                data[k] = keys[k]
        return {"summary": {"user_text": data, "count": len(data)}}

    @mcp.tool(annotations={"title": "Set User Text", "readOnlyHint": False})
    def rhino_set_user_text(args: _SetUserTextIn) -> dict[str, Any]:
        """Attach a key-value user text entry to an object."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.query.set_user_text", args.model_dump())
        h = doc(args.doc_id)
        obj = h.file3dm.Objects.FindId(args.object_id)
        if obj is None:
            from rhino_mcp.utils.error_handling import not_found_error
            raise not_found_error("object", args.object_id)
        obj.Attributes.SetUserString(args.key, args.value)
        return {"summary": {"key": args.key, "value": args.value}, "text": f"User text set: {args.key}={args.value}"}
