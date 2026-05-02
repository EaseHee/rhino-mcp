"""Serialise rhino3dm geometry to/from plain dicts.

The wire format is dict-of-floats by default (compact, debuggable, mirrors the
JSON shape RhinoCommon's ``CommonObject.ToJSON`` produces). For Brep/Mesh/SubD
we fall back to the rhino3dm built-in ``Encode``/``Decode`` JSON which round-trips
faithfully across the bridge.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import rhino3dm as r3


def point_to_dict(p: r3.Point3d) -> dict[str, float]:
    return {"x": p.X, "y": p.Y, "z": p.Z}


def dict_to_point(d: dict[str, Any]) -> r3.Point3d:
    return r3.Point3d(float(d["x"]), float(d["y"]), float(d.get("z", 0.0)))


def vector_to_dict(v: r3.Vector3d) -> dict[str, float]:
    return {"x": v.X, "y": v.Y, "z": v.Z}


def dict_to_vector(d: dict[str, Any]) -> r3.Vector3d:
    return r3.Vector3d(float(d["x"]), float(d["y"]), float(d.get("z", 0.0)))


def plane_to_dict(p: r3.Plane) -> dict[str, dict[str, float]]:
    return {
        "origin": point_to_dict(p.Origin),
        "x_axis": vector_to_dict(p.XAxis),
        "y_axis": vector_to_dict(p.YAxis),
        "z_axis": vector_to_dict(p.ZAxis),
    }


def dict_to_plane(d: dict[str, Any]) -> r3.Plane:
    if "x_axis" in d and "y_axis" in d:
        return r3.Plane(
            dict_to_point(d["origin"]),
            dict_to_vector(d["x_axis"]),
            dict_to_vector(d["y_axis"]),
        )
    return r3.Plane(dict_to_point(d["origin"]), dict_to_vector(d["normal"]))


def bbox_to_dict(b: r3.BoundingBox) -> dict[str, dict[str, float]]:
    return {"min": point_to_dict(b.Min), "max": point_to_dict(b.Max)}


def transform_to_matrix(t: r3.Transform) -> list[list[float]]:
    return [
        [t.M00, t.M01, t.M02, t.M03],
        [t.M10, t.M11, t.M12, t.M13],
        [t.M20, t.M21, t.M22, t.M23],
        [t.M30, t.M31, t.M32, t.M33],
    ]


def matrix_to_transform(m: list[list[float]]) -> r3.Transform:
    t = r3.Transform.Identity()
    t.M00, t.M01, t.M02, t.M03 = m[0]
    t.M10, t.M11, t.M12, t.M13 = m[1]
    t.M20, t.M21, t.M22, t.M23 = m[2]
    t.M30, t.M31, t.M32, t.M33 = m[3]
    return t


def geometry_to_json(geom: r3.GeometryBase) -> str:
    """Encode any rhino3dm geometry to its JSON wire format."""
    return geom.Encode()  # type: ignore[no-any-return]


def geometry_from_json(payload: str | dict[str, Any]) -> r3.GeometryBase:
    """Decode the rhino3dm JSON wire format back to a geometry instance."""
    return r3.CommonObject.Decode(payload)  # type: ignore[no-any-return]


def gid_str(gid: UUID | str) -> str:
    return str(gid)
