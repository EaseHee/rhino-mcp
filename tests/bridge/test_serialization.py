"""Serialisation round-trip tests."""

from __future__ import annotations

import rhino3dm as r3

from rhino_mcp.utils.serialization import (
    bbox_to_dict,
    dict_to_plane,
    dict_to_point,
    dict_to_vector,
    matrix_to_transform,
    plane_to_dict,
    point_to_dict,
    transform_to_matrix,
    vector_to_dict,
)


def test_point_round_trip() -> None:
    p = r3.Point3d(1.5, -2.0, 3.25)
    d = point_to_dict(p)
    p2 = dict_to_point(d)
    assert (p2.X, p2.Y, p2.Z) == (1.5, -2.0, 3.25)


def test_vector_round_trip() -> None:
    v = r3.Vector3d(1.0, 0.0, -1.0)
    d = vector_to_dict(v)
    v2 = dict_to_vector(d)
    assert (v2.X, v2.Y, v2.Z) == (1.0, 0.0, -1.0)


def test_plane_round_trip_with_axes() -> None:
    p = r3.Plane(r3.Point3d(1, 2, 3), r3.Vector3d(1, 0, 0), r3.Vector3d(0, 1, 0))
    d = plane_to_dict(p)
    p2 = dict_to_plane(d)
    assert (p2.Origin.X, p2.Origin.Y, p2.Origin.Z) == (1, 2, 3)


def test_bbox_dict() -> None:
    bb = r3.BoundingBox(r3.Point3d(-1, -1, -1), r3.Point3d(2, 3, 4))
    d = bbox_to_dict(bb)
    assert d["min"]["x"] == -1
    assert d["max"]["z"] == 4


def test_transform_matrix_round_trip() -> None:
    t = r3.Transform.Translation(r3.Vector3d(5, 0, 0))
    matrix = transform_to_matrix(t)
    t2 = matrix_to_transform(matrix)
    # Compare element-wise.
    for r in range(4):
        for c in range(4):
            assert getattr(t, f"M{r}{c}") == getattr(t2, f"M{r}{c}")
