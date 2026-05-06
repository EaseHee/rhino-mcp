"""Object transformation tools (move/rotate/scale/mirror/array/orient/flow/cage_edit)."""

from __future__ import annotations

import math
from typing import Annotated, Any

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.models.geometry_types import PlaneModel, Point3dModel, Vector3dModel
from rhino_mcp.tools._helpers import MAX_OBJECT_IDS, doc, to_point, to_vector
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import parameter_error, unsupported_in_standalone
from rhino_mcp.utils.registry import Mode
from rhino_mcp.utils.serialization import bbox_to_dict


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )


class _MoveIn(_DocArg):
    object_ids: list[str] = Field(..., min_length=1, max_length=MAX_OBJECT_IDS)
    translation: Vector3dModel
    make_copy: bool = Field(False, description="Duplicate before transforming.")


class _RotateIn(_DocArg):
    object_ids: list[str] = Field(..., min_length=1, max_length=MAX_OBJECT_IDS)
    center: Point3dModel
    axis: Vector3dModel = Field(default_factory=lambda: Vector3dModel(x=0.0, y=0.0, z=1.0))
    angle_degrees: float
    make_copy: bool = Field(False)


class _ScaleIn(_DocArg):
    object_ids: list[str] = Field(..., min_length=1, max_length=MAX_OBJECT_IDS)
    center: Point3dModel
    factor_x: Annotated[float, Field(gt=0)]
    factor_y: Annotated[float, Field(gt=0)]
    factor_z: Annotated[float, Field(gt=0)]
    make_copy: bool = Field(False)


class _MirrorIn(_DocArg):
    object_ids: list[str] = Field(..., min_length=1, max_length=MAX_OBJECT_IDS)
    plane: PlaneModel
    make_copy: bool = Field(True)


class _ArrayLinearIn(_DocArg):
    object_ids: list[str] = Field(..., min_length=1, max_length=MAX_OBJECT_IDS)
    direction: Vector3dModel
    spacing: Annotated[float, Field(gt=0)]
    count: Annotated[int, Field(ge=2, le=1024)]


class _ArrayPolarIn(_DocArg):
    object_ids: list[str] = Field(..., min_length=1, max_length=MAX_OBJECT_IDS)
    center: Point3dModel
    axis: Vector3dModel = Field(default_factory=lambda: Vector3dModel(x=0.0, y=0.0, z=1.0))
    count: Annotated[int, Field(ge=2, le=512)]
    total_angle_degrees: Annotated[float, Field(gt=0, le=360)] = 360


class _ArrayRectangularIn(_DocArg):
    object_ids: list[str] = Field(..., min_length=1, max_length=MAX_OBJECT_IDS)
    count_x: Annotated[int, Field(ge=1, le=256)]
    count_y: Annotated[int, Field(ge=1, le=256)]
    count_z: Annotated[int, Field(ge=1, le=256)] = 1
    spacing_x: Annotated[float, Field(gt=0)]
    spacing_y: Annotated[float, Field(gt=0)]
    spacing_z: Annotated[float, Field(gt=0)] = 1.0


class _OrientIn(_DocArg):
    object_ids: list[str] = Field(..., min_length=1, max_length=MAX_OBJECT_IDS)
    from_plane: PlaneModel
    to_plane: PlaneModel
    make_copy: bool = Field(False)


class _FlowIn(_DocArg):
    object_ids: list[str]
    base_curve_id: str
    target_curve_id: str


class _CageIn(_DocArg):
    object_ids: list[str]
    cage_object_id: str


def _apply(handle, ids: list[str], xform: r3.Transform, copy: bool) -> list[str]:
    """Apply ``xform`` to each object id; return resulting GUIDs."""
    new_ids: list[str] = []
    for gid in ids:
        obj = handle.find_object(gid)
        geom = obj.Geometry
        if copy:
            duplicated = geom.Duplicate()
            duplicated.Transform(xform)
            new_id = handle.file3dm.Objects.Add(duplicated, obj.Attributes)
            new_ids.append(handle.add_index(new_id))
        else:
            geom.Transform(xform)
            # rhino3dm doesn't expose direct in-place replacement of geometry;
            # delete + re-add preserves attributes.
            attrs = obj.Attributes
            handle.file3dm.Objects.Delete(obj.Attributes.Id)
            new_id = handle.file3dm.Objects.Add(geom, attrs)
            new_ids.append(handle.add_index(new_id))
    return new_ids


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Move Objects", "readOnlyHint": False})
    def rhino_move(args: _MoveIn) -> dict[str, Any]:
        """Translate (or copy) the given objects by a vector."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.transform.move", args.model_dump())
        h = doc(args.doc_id)
        xf = r3.Transform.Translation(to_vector(args.translation))
        new_ids = _apply(h, args.object_ids, xf, args.make_copy)
        return {"summary": {"object_ids": new_ids}, "text": f"Moved {len(new_ids)} object(s)"}

    @mcp.tool(annotations={"title": "Rotate Objects", "readOnlyHint": False})
    def rhino_rotate(args: _RotateIn) -> dict[str, Any]:
        """Rotate objects about an axis through a centre point."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.transform.rotate", args.model_dump())
        h = doc(args.doc_id)
        xf = r3.Transform.Rotation(
            math.radians(args.angle_degrees), to_vector(args.axis), to_point(args.center)
        )
        new_ids = _apply(h, args.object_ids, xf, args.make_copy)
        return {"summary": {"object_ids": new_ids}, "text": f"Rotated {len(new_ids)} object(s)"}

    @mcp.tool(annotations={"title": "Scale Objects", "readOnlyHint": False})
    def rhino_scale(args: _ScaleIn) -> dict[str, Any]:
        """Scale objects non-uniformly about a centre."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.transform.scale", args.model_dump())
        h = doc(args.doc_id)
        plane = r3.Plane(to_point(args.center), r3.Vector3d(0, 0, 1))
        xf = r3.Transform.Scale(plane, args.factor_x, args.factor_y, args.factor_z)
        new_ids = _apply(h, args.object_ids, xf, args.make_copy)
        return {"summary": {"object_ids": new_ids}, "text": f"Scaled {len(new_ids)} object(s)"}

    @mcp.tool(annotations={"title": "Mirror Objects", "readOnlyHint": False})
    def rhino_mirror(args: _MirrorIn) -> dict[str, Any]:
        """Mirror objects across a plane (copies by default)."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.transform.mirror", args.model_dump())
        h = doc(args.doc_id)
        plane = r3.Plane(
            to_point(args.plane.origin), to_vector(args.plane.x_axis), to_vector(args.plane.y_axis)
        )
        xf = r3.Transform.Mirror(plane.Origin, plane.ZAxis)
        new_ids = _apply(h, args.object_ids, xf, args.make_copy)
        return {"summary": {"object_ids": new_ids}, "text": f"Mirrored {len(new_ids)} object(s)"}

    @mcp.tool(annotations={"title": "Linear Array", "readOnlyHint": False})
    def rhino_array_linear(args: _ArrayLinearIn) -> dict[str, Any]:
        """Array objects along a vector with constant spacing."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.transform.array_linear", args.model_dump())
        h = doc(args.doc_id)
        d = to_vector(args.direction)
        length = (d.X * d.X + d.Y * d.Y + d.Z * d.Z) ** 0.5
        if length == 0:
            raise parameter_error("direction", "must be non-zero")
        unit = r3.Vector3d(d.X / length, d.Y / length, d.Z / length)
        new_ids: list[str] = []
        for k in range(1, args.count):
            offset = r3.Vector3d(unit.X * args.spacing * k, unit.Y * args.spacing * k, unit.Z * args.spacing * k)
            xf = r3.Transform.Translation(offset)
            new_ids.extend(_apply(h, args.object_ids, xf, copy=True))
        return {"summary": {"object_ids": new_ids}, "text": f"Linear array produced {len(new_ids)} copies"}

    @mcp.tool(annotations={"title": "Polar Array", "readOnlyHint": False})
    def rhino_array_polar(args: _ArrayPolarIn) -> dict[str, Any]:
        """Array objects in a polar pattern."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.transform.array_polar", args.model_dump())
        h = doc(args.doc_id)
        new_ids: list[str] = []
        step = math.radians(args.total_angle_degrees) / max(args.count - 1, 1)
        for k in range(1, args.count):
            xf = r3.Transform.Rotation(step * k, to_vector(args.axis), to_point(args.center))
            new_ids.extend(_apply(h, args.object_ids, xf, copy=True))
        return {"summary": {"object_ids": new_ids}, "text": f"Polar array produced {len(new_ids)} copies"}

    @mcp.tool(annotations={"title": "Rectangular Array", "readOnlyHint": False})
    def rhino_array_rectangular(args: _ArrayRectangularIn) -> dict[str, Any]:
        """Array objects in a 3D rectangular grid."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call(
                "rhino.transform.array_rectangular", args.model_dump()
            )
        h = doc(args.doc_id)
        new_ids: list[str] = []
        for ix in range(args.count_x):
            for iy in range(args.count_y):
                for iz in range(args.count_z):
                    if ix == iy == iz == 0:
                        continue
                    xf = r3.Transform.Translation(
                        r3.Vector3d(
                            ix * args.spacing_x,
                            iy * args.spacing_y,
                            iz * args.spacing_z,
                        )
                    )
                    new_ids.extend(_apply(h, args.object_ids, xf, copy=True))
        return {"summary": {"object_ids": new_ids}, "text": f"Rectangular array produced {len(new_ids)} copies"}

    @mcp.tool(annotations={"title": "Orient Objects", "readOnlyHint": False})
    def rhino_orient(args: _OrientIn) -> dict[str, Any]:
        """Orient objects from one plane to another (PlaneToPlane transform)."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.transform.orient", args.model_dump())
        h = doc(args.doc_id)
        from_plane = r3.Plane(
            to_point(args.from_plane.origin),
            to_vector(args.from_plane.x_axis),
            to_vector(args.from_plane.y_axis),
        )
        to_plane = r3.Plane(
            to_point(args.to_plane.origin),
            to_vector(args.to_plane.x_axis),
            to_vector(args.to_plane.y_axis),
        )
        xf = r3.Transform.PlaneToPlane(from_plane, to_plane)
        new_ids = _apply(h, args.object_ids, xf, args.make_copy)
        return {"summary": {"object_ids": new_ids}, "text": f"Oriented {len(new_ids)} object(s)"}

    @mcp.tool(annotations={"title": "Bounding Box of Selection", "readOnlyHint": True})
    def rhino_selection_bbox(args: _DocArg) -> dict[str, Any]:
        """Return the union bounding box of all objects in the document."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.transform.selection_bbox", args.model_dump())
        h = doc(args.doc_id)
        bb = h.file3dm.Objects.GetBoundingBox()
        return {"summary": {"bounding_box": bbox_to_dict(bb)}, "text": "Computed bounding box"}

    if mode is Mode.STANDALONE:
        return  # bridge-only transform tools below

    @mcp.tool(annotations={"title": "Flow Along Curve", "readOnlyHint": False})
    def rhino_flow(args: _FlowIn) -> dict[str, Any]:
        """Flow objects from one curve onto another (bridge only)."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_flow")
        return runtime().require_bridge().call("rhino.transform.flow", args.model_dump())

    @mcp.tool(annotations={"title": "Cage Edit", "readOnlyHint": False})
    def rhino_cage_edit(args: _CageIn) -> dict[str, Any]:
        """Deform objects with a control cage (bridge only)."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_cage_edit")
        return runtime().require_bridge().call("rhino.transform.cage_edit", args.model_dump())
