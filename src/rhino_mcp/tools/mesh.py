"""Mesh tools.

``rhino_mesh_box`` runs in standalone mode (we build the mesh manually). Every
other operation needs RhinoCommon's mesher and is therefore bridge-only.
"""

from __future__ import annotations

from typing import Annotated, Any

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.models.geometry_types import Point3dModel
from rhino_mcp.tools._helpers import (
    add_object_with_attrs,
    doc,
    object_summary,
    text_for,
)
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.registry import Mode


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )
    layer: str | None = Field(None)
    name: str | None = Field(None)


class _MeshBoxIn(_DocArg):
    corner: Point3dModel
    size_x: Annotated[float, Field(gt=0)]
    size_y: Annotated[float, Field(gt=0)]
    size_z: Annotated[float, Field(gt=0)]
    divisions_x: Annotated[int, Field(ge=1, le=128)] = 1
    divisions_y: Annotated[int, Field(ge=1, le=128)] = 1
    divisions_z: Annotated[int, Field(ge=1, le=128)] = 1


class _MeshFromIdIn(_DocArg):
    object_id: str
    quality: Annotated[float, Field(gt=0, le=1.0, description="0..1 (1 = finest)")] = 0.5


class _MeshOpIn(_DocArg):
    object_id: str


class _MeshReduceIn(_DocArg):
    object_id: str
    target_face_count: Annotated[int, Field(ge=4)]


class _MeshBooleanIn(_DocArg):
    a_ids: list[str] = Field(..., min_length=1)
    b_ids: list[str] = Field(..., min_length=1)


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Add Mesh Box", "readOnlyHint": False})
    def rhino_mesh_box(args: _MeshBoxIn) -> dict[str, Any]:
        """Add a quad mesh box with the given subdivisions."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.mesh.box", args.model_dump())
        h = doc(args.doc_id)
        mesh = _build_mesh_box(
            args.corner,
            args.size_x,
            args.size_y,
            args.size_z,
            args.divisions_x,
            args.divisions_y,
            args.divisions_z,
        )
        gid = add_object_with_attrs(h, "AddMesh", mesh, layer=args.layer, name=args.name)
        return {"summary": object_summary(h, gid, "MeshBox"), "text": text_for("MeshBox", gid)}

    if mode is Mode.STANDALONE:
        return  # bridge-only tools below are skipped in standalone mode

    @mcp.tool(annotations={"title": "Mesh from Surface", "readOnlyHint": False})
    def rhino_mesh_from_surface(args: _MeshFromIdIn) -> dict[str, Any]:
        """Mesh a surface (bridge only)."""
        return runtime().require_bridge().call("rhino.mesh.from_surface", args.model_dump())

    @mcp.tool(annotations={"title": "Mesh from Brep", "readOnlyHint": False})
    def rhino_mesh_from_brep(args: _MeshFromIdIn) -> dict[str, Any]:
        """Mesh a Brep (bridge only)."""
        return runtime().require_bridge().call("rhino.mesh.from_brep", args.model_dump())

    @mcp.tool(annotations={"title": "Weld Mesh", "readOnlyHint": False})
    def rhino_weld_mesh(args: _MeshOpIn) -> dict[str, Any]:
        """Weld coincident vertices in a mesh."""
        return runtime().require_bridge().call("rhino.mesh.weld", args.model_dump())

    @mcp.tool(annotations={"title": "Unweld Mesh", "readOnlyHint": False})
    def rhino_unweld_mesh(args: _MeshOpIn) -> dict[str, Any]:
        """Unweld vertices to break mesh smoothing."""
        return runtime().require_bridge().call("rhino.mesh.unweld", args.model_dump())

    @mcp.tool(annotations={"title": "Reduce Mesh", "readOnlyHint": False, "destructiveHint": True})
    def rhino_reduce_mesh(args: _MeshReduceIn) -> dict[str, Any]:
        """Reduce a mesh to a target face count."""
        return runtime().require_bridge().call("rhino.mesh.reduce", args.model_dump())

    @mcp.tool(annotations={"title": "Mesh Boolean Union", "readOnlyHint": False, "destructiveHint": True})
    def rhino_mesh_boolean_union(args: _MeshBooleanIn) -> dict[str, Any]:
        """Boolean-union meshes."""
        return runtime().require_bridge().call("rhino.mesh.boolean_union", args.model_dump())

    @mcp.tool(annotations={"title": "Mesh Boolean Difference", "readOnlyHint": False, "destructiveHint": True})
    def rhino_mesh_boolean_difference(args: _MeshBooleanIn) -> dict[str, Any]:
        """Boolean-difference meshes (a - b)."""
        return runtime().require_bridge().call("rhino.mesh.boolean_difference", args.model_dump())


def _build_mesh_box(
    corner: Point3dModel,
    sx: float,
    sy: float,
    sz: float,
    nx: int,
    ny: int,
    nz: int,
) -> r3.Mesh:
    """Build a hollow mesh box with subdivisions on each face."""
    mesh = r3.Mesh()
    cx, cy, cz = corner.x, corner.y, corner.z
    # Helper: stamp a planar grid into ``mesh`` with given uv→xyz mapping.

    def stamp_grid(uvs_to_xyz, n_u, n_v) -> None:
        base = mesh.Vertices.__len__()
        for j in range(n_v + 1):
            for i in range(n_u + 1):
                x, y, z = uvs_to_xyz(i / n_u, j / n_v)
                mesh.Vertices.Add(x, y, z)
        for j in range(n_v):
            for i in range(n_u):
                a = base + j * (n_u + 1) + i
                b = a + 1
                c = a + (n_u + 1) + 1
                d = a + (n_u + 1)
                mesh.Faces.AddFace(a, b, c, d)

    # bottom (z = cz)
    stamp_grid(lambda u, v: (cx + u * sx, cy + v * sy, cz), nx, ny)
    # top (z = cz + sz)
    stamp_grid(lambda u, v: (cx + u * sx, cy + v * sy, cz + sz), nx, ny)
    # front (y = cy)
    stamp_grid(lambda u, v: (cx + u * sx, cy, cz + v * sz), nx, nz)
    # back (y = cy + sy)
    stamp_grid(lambda u, v: (cx + u * sx, cy + sy, cz + v * sz), nx, nz)
    # left (x = cx)
    stamp_grid(lambda u, v: (cx, cy + u * sy, cz + v * sz), ny, nz)
    # right
    stamp_grid(lambda u, v: (cx + sx, cy + u * sy, cz + v * sz), ny, nz)
    return mesh
