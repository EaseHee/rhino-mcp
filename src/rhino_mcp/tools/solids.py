"""Solid primitives and boolean operations.

Primitives (box/sphere/cylinder/cone/torus) work in standalone via Brep
factories. Booleans, shell, and cap-holes are bridge-only because rhino3dm
does not ship the solid-modelling kernel.
"""

from __future__ import annotations

from typing import Annotated, Any

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.models.geometry_types import Point3dModel, Vector3dModel
from rhino_mcp.tools._helpers import (
    add_object_with_attrs,
    doc,
    object_summary,
    require_bridge_only,
    text_for,
    to_point,
)
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import parameter_error, unsupported_in_standalone
from rhino_mcp.utils.registry import Mode


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )
    layer: str | None = Field(None)
    name: str | None = Field(None)


class _BoxIn(_DocArg):
    corner: Point3dModel = Field(..., description="Lower-left-front corner.")
    size_x: Annotated[float, Field(gt=0)]
    size_y: Annotated[float, Field(gt=0)]
    size_z: Annotated[float, Field(gt=0)]


class _SphereIn(_DocArg):
    center: Point3dModel
    radius: Annotated[float, Field(gt=0)]


class _CylinderIn(_DocArg):
    base_center: Point3dModel = Field(..., description="Centre of the base circle.")
    radius: Annotated[float, Field(gt=0)]
    height: Annotated[float, Field(gt=0)]
    axis: Vector3dModel = Field(
        default_factory=lambda: Vector3dModel(x=0.0, y=0.0, z=1.0),
        description="Cylinder axis direction (default world Z).",
    )
    capped: bool = Field(True, description="Cap top and bottom.")


class _ConeIn(_DocArg):
    base_center: Point3dModel
    radius: Annotated[float, Field(gt=0)]
    height: Annotated[float, Field(gt=0)]


class _TorusIn(_DocArg):
    center: Point3dModel
    major_radius: Annotated[float, Field(gt=0)]
    minor_radius: Annotated[float, Field(gt=0)]


class _BooleanIn(_DocArg):
    a_ids: list[str] = Field(..., min_length=1, description="First operand brep GUIDs.")
    b_ids: list[str] = Field(..., min_length=1, description="Second operand brep GUIDs.")


class _ShellIn(_DocArg):
    object_id: str
    thickness: Annotated[float, Field(gt=0)]
    open_face_indices: list[int] = Field(default_factory=list)


class _CapHolesIn(_DocArg):
    object_id: str


def _add_brep(handle, brep: r3.Brep | None, kind: str, layer, name) -> dict[str, Any]:
    if brep is None or not brep.IsValid:
        raise parameter_error("inputs", f"could not build a valid Brep for {kind}")
    gid = add_object_with_attrs(handle, "AddBrep", brep, layer=layer, name=name)
    return {"summary": object_summary(handle, gid, kind), "text": text_for(kind, gid)}


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Add Box (solid)", "readOnlyHint": False})
    def rhino_box(args: _BoxIn) -> dict[str, Any]:
        """Add a rectangular box (axis-aligned in standalone mode)."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.solid.box", args.model_dump())
        h = doc(args.doc_id)
        c = args.corner
        bb = r3.BoundingBox(
            r3.Point3d(c.x, c.y, c.z),
            r3.Point3d(c.x + args.size_x, c.y + args.size_y, c.z + args.size_z),
        )
        box = r3.Box(bb)
        return _add_brep(h, r3.Brep.CreateFromBox(box), "Box", args.layer, args.name)

    @mcp.tool(annotations={"title": "Add Sphere", "readOnlyHint": False})
    def rhino_sphere(args: _SphereIn) -> dict[str, Any]:
        """Add a sphere primitive."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.solid.sphere", args.model_dump())
        h = doc(args.doc_id)
        sphere = r3.Sphere(to_point(args.center), args.radius)
        return _add_brep(h, sphere.ToBrep(), "Sphere", args.layer, args.name)

    @mcp.tool(annotations={"title": "Add Cylinder", "readOnlyHint": False})
    def rhino_cylinder(args: _CylinderIn) -> dict[str, Any]:
        """Add a cylinder; in standalone mode the axis must be world Z."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.solid.cylinder", args.model_dump())
        if not (args.axis.x == 0 and args.axis.y == 0 and args.axis.z != 0):
            raise parameter_error(
                "axis",
                "standalone mode supports only the world Z axis",
                "{x:0,y:0,z:1} or use bridge mode",
            )
        h = doc(args.doc_id)
        circle = r3.Circle(to_point(args.base_center), args.radius)
        cyl = r3.Cylinder(circle, args.height)
        return _add_brep(
            h, r3.Brep.CreateFromCylinder(cyl, args.capped, args.capped), "Cylinder", args.layer, args.name
        )

    @mcp.tool(annotations={"title": "Add Cone", "readOnlyHint": False})
    def rhino_cone(args: _ConeIn) -> dict[str, Any]:
        """Add a cone primitive (bridge required for non-Z axes)."""
        # rhino3dm exposes Cone but its constructor is sealed; we therefore
        # build the cone as a revolved Brep on the XZ plane in standalone mode.
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.solid.cone", args.model_dump())
        h = doc(args.doc_id)
        # Axis line: from base_center upward by height
        c = args.base_center
        # Build a profile (apex → base rim) then revolve via NurbsSurface.
        # rhino3dm has no RevSurface.Create with profile/axis/angle; fall back
        # to constructing a polyline-cone Brep via NurbsSurface ruled surface.
        rim_count = 64
        base_pts: list[r3.Point3d] = []
        import math

        for i in range(rim_count + 1):
            theta = 2 * math.pi * i / rim_count
            base_pts.append(
                r3.Point3d(c.x + args.radius * math.cos(theta), c.y + args.radius * math.sin(theta), c.z)
            )
        side = r3.Polyline()
        for p in base_pts:
            side.Add(p.X, p.Y, p.Z)
        # Approximate the cone as a polysurface mesh (sufficient for IO/visualisation).
        mesh = r3.Mesh()
        apex_idx = mesh.Vertices.Add(c.x, c.y, c.z + args.height)
        base_indices = [mesh.Vertices.Add(p.X, p.Y, p.Z) for p in base_pts]
        for i in range(rim_count):
            mesh.Faces.AddFace(apex_idx, base_indices[i], base_indices[i + 1])
        # Cap the base with a triangle fan.
        center_idx = mesh.Vertices.Add(c.x, c.y, c.z)
        for i in range(rim_count):
            mesh.Faces.AddFace(center_idx, base_indices[i + 1], base_indices[i])
        gid = add_object_with_attrs(h, "AddMesh", mesh, layer=args.layer, name=args.name)
        return {"summary": object_summary(h, gid, "Cone"), "text": text_for("Cone (mesh)", gid)}

    @mcp.tool(annotations={"title": "Add Torus", "readOnlyHint": False})
    def rhino_torus(args: _TorusIn) -> dict[str, Any]:
        """Add a torus primitive (mesh approximation in standalone mode)."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.solid.torus", args.model_dump())
        h = doc(args.doc_id)
        import math

        u_steps, v_steps = 48, 24
        mesh = r3.Mesh()
        c = args.center
        for i in range(u_steps):
            for j in range(v_steps):
                u = 2 * math.pi * i / u_steps
                v = 2 * math.pi * j / v_steps
                cx = (args.major_radius + args.minor_radius * math.cos(v)) * math.cos(u)
                cy = (args.major_radius + args.minor_radius * math.cos(v)) * math.sin(u)
                cz = args.minor_radius * math.sin(v)
                mesh.Vertices.Add(c.x + cx, c.y + cy, c.z + cz)
        for i in range(u_steps):
            for j in range(v_steps):
                a = i * v_steps + j
                b = ((i + 1) % u_steps) * v_steps + j
                bb = ((i + 1) % u_steps) * v_steps + (j + 1) % v_steps
                d = i * v_steps + (j + 1) % v_steps
                mesh.Faces.AddFace(a, b, bb, d)
        gid = add_object_with_attrs(h, "AddMesh", mesh, layer=args.layer, name=args.name)
        return {"summary": object_summary(h, gid, "Torus"), "text": text_for("Torus (mesh)", gid)}

    if mode is Mode.STANDALONE:
        return  # bridge-only operations below

    @mcp.tool(annotations={"title": "Boolean Union", "readOnlyHint": False, "destructiveHint": True})
    def rhino_boolean_union(args: _BooleanIn) -> dict[str, Any]:
        """Boolean-union the given Brep groups. Bridge required."""
        require_bridge_only("rhino_boolean_union")
        return runtime().require_bridge().call("rhino.solid.boolean_union", args.model_dump())

    @mcp.tool(annotations={"title": "Boolean Difference", "readOnlyHint": False, "destructiveHint": True})
    def rhino_boolean_difference(args: _BooleanIn) -> dict[str, Any]:
        """Subtract ``b_ids`` from ``a_ids``. Bridge required."""
        require_bridge_only("rhino_boolean_difference")
        return runtime().require_bridge().call("rhino.solid.boolean_difference", args.model_dump())

    @mcp.tool(
        annotations={"title": "Boolean Intersection", "readOnlyHint": False, "destructiveHint": True}
    )
    def rhino_boolean_intersection(args: _BooleanIn) -> dict[str, Any]:
        """Intersect ``a_ids`` with ``b_ids``. Bridge required."""
        require_bridge_only("rhino_boolean_intersection")
        return runtime().require_bridge().call("rhino.solid.boolean_intersection", args.model_dump())

    @mcp.tool(annotations={"title": "Shell Solid", "readOnlyHint": False, "destructiveHint": True})
    def rhino_shell(args: _ShellIn) -> dict[str, Any]:
        """Hollow a closed Brep, optionally leaving the listed faces open."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_shell")
        return runtime().require_bridge().call("rhino.solid.shell", args.model_dump())

    @mcp.tool(annotations={"title": "Cap Brep Holes", "readOnlyHint": False})
    def rhino_cap_holes(args: _CapHolesIn) -> dict[str, Any]:
        """Cap all open holes of a Brep."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_cap_holes")
        return runtime().require_bridge().call("rhino.solid.cap_holes", args.model_dump())
