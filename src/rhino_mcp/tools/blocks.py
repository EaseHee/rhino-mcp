"""Block / instance reuse tools.

Architecture relies heavily on reusable component families (windows,
doors, structural modules, furniture). Rhino's block system gives a
single definition that all instances mirror — edit the definition once
and every instance updates.

Standalone (rhino3dm) supports define + insert + list (via
``InstanceDefinitionGeometry`` / ``File3dm.AllInstanceDefinitions``).
Explode and redefine require RhinoCommon (bridge mode) because rhino3dm
doesn't expose the InstanceDefinitionTable mutator API.
"""

from __future__ import annotations

import math
from typing import Any
from uuid import UUID

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.models.geometry_types import Point3dModel
from rhino_mcp.tools._helpers import bridge_call, doc, require_bridge_only, to_point
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import not_found_error, parameter_error
from rhino_mcp.utils.registry import Mode


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )


class _BlockDefineIn(_DocArg):
    object_ids: list[str] = Field(..., min_length=1, description="Objects that compose the block geometry.")
    base_point: Point3dModel = Field(..., description="Insertion anchor for the block.")
    name: str = Field(..., min_length=1)
    description: str = Field("")
    replace_objects: bool = Field(
        True,
        description="If True (bridge), replace the source objects with a single instance at the base point.",
    )


class _BlockInsertIn(_DocArg):
    name: str = Field(..., min_length=1, description="Block definition name.")
    insertion_point: Point3dModel
    scale: tuple[float, float, float] = Field((1.0, 1.0, 1.0))
    rotation_deg: float = Field(0.0)
    layer: str | None = Field(None)
    instance_name: str | None = Field(None)


class _BlockListIn(_DocArg):
    pass


class _BlockExplodeIn(_DocArg):
    instance_id: str = Field(..., description="Block instance to explode.")
    keep_instance: bool = Field(
        False,
        description="If True (bridge), keep the instance and emit a copy of its geometry instead of replacing it.",
    )


class _BlockRedefineIn(_DocArg):
    name: str = Field(..., min_length=1)
    object_ids: list[str] = Field(..., min_length=1)
    base_point: Point3dModel | None = Field(None)


def _find_obj(handle: Any, gid: str) -> Any:
    obj = handle.file3dm.Objects.FindId(gid)
    if obj is None:
        raise not_found_error("object", gid)
    return obj


def _find_definition_by_name(handle: Any, name: str) -> Any | None:
    table = handle.file3dm.InstanceDefinitions
    for i in range(len(table)):
        d = table[i]
        if d.Name == name:
            return d
    return None


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Define Block", "readOnlyHint": False})
    def rhino_block_define(args: _BlockDefineIn) -> dict[str, Any]:
        """Create a block definition from a list of objects.

        Standalone uses ``rhino3dm.InstanceDefinitionGeometry`` to register
        the geometry under ``name``. Bridge mode mirrors that and additionally
        replaces the source objects with a single instance at the base point
        when ``replace_objects=True``.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.block.define", args.model_dump())
        h = doc(args.doc_id)
        if _find_definition_by_name(h, args.name) is not None:
            raise parameter_error("name", f"block definition '{args.name}' already exists")
        geometry: list[Any] = []
        attributes: list[Any] = []
        for oid in args.object_ids:
            obj = _find_obj(h, oid)
            geometry.append(obj.Geometry.Duplicate())
            # rhino3dm ObjectAttributes has no Duplicate(); reuse the existing
            # attributes instance — it's owned by the doc and survives Add().
            attributes.append(obj.Attributes)
        idx: int = h.file3dm.InstanceDefinitions.Add(
            args.name,
            args.description,
            "",
            "",
            to_point(args.base_point),
            tuple(geometry),
            tuple(attributes),
        )
        return {
            "summary": {
                "definition_index": idx,
                "name": args.name,
                "object_count": len(args.object_ids),
            },
            "text": f"Block defined: {args.name} ({len(args.object_ids)} object(s))",
        }

    @mcp.tool(annotations={"title": "Insert Block", "readOnlyHint": False})
    def rhino_block_insert(args: _BlockInsertIn) -> dict[str, Any]:
        """Insert a block instance at ``insertion_point`` with optional scale + rotation.

        Standalone constructs a ``rhino3dm.InstanceReferenceGeometry`` and
        applies the transform to it. Bridge mode forwards to RhinoCommon's
        ``Doc.Objects.AddInstanceObject`` which honours the active layer
        and links the instance to the definition.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.block.insert", args.model_dump())
        h = doc(args.doc_id)
        idef = _find_definition_by_name(h, args.name)
        if idef is None:
            raise not_found_error("block definition", args.name)
        # Build (rotate * scale * translate) transform for the instance.
        ip = to_point(args.insertion_point)
        sx, sy, sz = args.scale
        m = r3.Transform.Identity()
        m.M00 = sx * math.cos(math.radians(args.rotation_deg))
        m.M01 = -sy * math.sin(math.radians(args.rotation_deg))
        m.M10 = sx * math.sin(math.radians(args.rotation_deg))
        m.M11 = sy * math.cos(math.radians(args.rotation_deg))
        m.M22 = sz
        m.M03 = ip.X
        m.M13 = ip.Y
        m.M23 = ip.Z
        try:
            ref = r3.InstanceReference(idef.Id, m)
        except Exception as exc:
            raise parameter_error(
                "name",
                f"rhino3dm could not instantiate definition '{args.name}': {exc}",
            ) from exc
        attrs = r3.ObjectAttributes()
        if args.layer is not None:
            from rhino_mcp.tools._helpers import _resolve_layer_index

            attrs.LayerIndex = _resolve_layer_index(h, args.layer)
        if args.instance_name is not None:
            attrs.Name = args.instance_name
        new_id: UUID = h.file3dm.Objects.Add(ref, attrs)
        sid = h.add_index(new_id)
        return {
            "summary": {
                "instance_id": sid,
                "definition_name": args.name,
                "scale": list(args.scale),
                "rotation_deg": args.rotation_deg,
            },
            "text": f"Inserted block '{args.name}' as {sid}",
        }

    @mcp.tool(annotations={"title": "List Blocks", "readOnlyHint": True})
    def rhino_block_list(args: _BlockListIn) -> dict[str, Any]:
        """List every block definition with a per-definition object + instance count."""
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.block.list", args.model_dump())
        h = doc(args.doc_id)
        table = h.file3dm.InstanceDefinitions
        # Pre-count instances per definition by iterating model objects.
        instance_counts: dict[str, int] = {}
        for i in range(len(h.file3dm.Objects)):
            obj = h.file3dm.Objects[i]
            geom = obj.Geometry
            if isinstance(geom, r3.InstanceReference):
                key = str(geom.ParentIdefId)
                instance_counts[key] = instance_counts.get(key, 0) + 1
        rows: list[dict[str, Any]] = []
        for i in range(len(table)):
            d = table[i]
            try:
                obj_ids = d.GetObjectIds()
                obj_count = len(obj_ids) if obj_ids is not None else 0
            except Exception:  # pragma: no cover - rhino3dm version safety
                obj_count = 0
            rows.append(
                {
                    "name": d.Name,
                    "description": d.Description,
                    "object_count": obj_count,
                    "instance_count": instance_counts.get(str(d.Id), 0),
                }
            )
        return {
            "summary": {"definitions": rows, "count": len(rows)},
            "text": f"{len(rows)} block definition(s)",
        }

    @mcp.tool(annotations={"title": "Explode Block Instance", "readOnlyHint": False})
    def rhino_block_explode(args: _BlockExplodeIn) -> dict[str, Any]:
        """Explode a block instance into individual objects (bridge only)."""
        require_bridge_only("rhino_block_explode")
        return bridge_call("rhino.block.explode", args.model_dump())

    @mcp.tool(annotations={"title": "Redefine Block", "readOnlyHint": False})
    def rhino_block_redefine(args: _BlockRedefineIn) -> dict[str, Any]:
        """Replace a block definition's geometry, propagating to every instance (bridge only)."""
        require_bridge_only("rhino_block_redefine")
        return bridge_call("rhino.block.redefine", args.model_dump())
