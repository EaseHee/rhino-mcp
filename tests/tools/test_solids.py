"""Solid-tool tests."""

from __future__ import annotations

import pytest

from tests.conftest import call_tool


def test_add_box_sphere_cylinder(server_standalone) -> None:
    _mcp, tools = server_standalone
    box = call_tool(
        tools,
        "rhino_box",
        {
            "corner": {"x": 0, "y": 0, "z": 0},
            "size_x": 1,
            "size_y": 2,
            "size_z": 3,
        },
    )
    sphere = call_tool(
        tools, "rhino_sphere", {"center": {"x": 5, "y": 0, "z": 0}, "radius": 2.5}
    )
    cyl = call_tool(
        tools,
        "rhino_cylinder",
        {
            "base_center": {"x": 0, "y": 0, "z": 0},
            "radius": 1.0,
            "height": 5.0,
            "axis": {"x": 0, "y": 0, "z": 1},
        },
    )
    for r in (box, sphere, cyl):
        bb = r["summary"]["bounding_box"]
        assert bb["max"]["x"] > bb["min"]["x"]


def test_cylinder_non_z_axis_rejected_in_standalone(server_standalone) -> None:
    _mcp, tools = server_standalone
    with pytest.raises(Exception):  # noqa: B017
        call_tool(
            tools,
            "rhino_cylinder",
            {
                "base_center": {"x": 0, "y": 0, "z": 0},
                "radius": 1.0,
                "height": 5.0,
                "axis": {"x": 1, "y": 0, "z": 0},
            },
        )


def test_cone_and_torus_emit_objects(server_standalone) -> None:
    _mcp, tools = server_standalone
    cone = call_tool(
        tools,
        "rhino_cone",
        {
            "base_center": {"x": 0, "y": 0, "z": 0},
            "radius": 2.0,
            "height": 4.0,
        },
    )
    torus = call_tool(
        tools,
        "rhino_torus",
        {
            "center": {"x": 0, "y": 0, "z": 0},
            "major_radius": 5.0,
            "minor_radius": 1.0,
        },
    )
    assert cone["summary"]["object_id"]
    assert torus["summary"]["object_id"]


def _geometry(object_id: str):  # type: ignore[no-untyped-def]
    from rhino_mcp.document import registry

    return registry().get("active").find_object(object_id).Geometry


def test_cone_is_exact_revolved_solid(server_standalone) -> None:
    import rhino3dm as r3

    _mcp, tools = server_standalone
    res = call_tool(
        tools,
        "rhino_cone",
        {"base_center": {"x": 1, "y": 2, "z": 3}, "radius": 2.0, "height": 4.0},
    )
    geom = _geometry(res["summary"]["object_id"])
    assert isinstance(geom, r3.Brep)
    assert geom.IsSolid
    # Side face + base cap; a tessellated mesh would have dozens of faces.
    assert len(geom.Faces) == 2
    bb = res["summary"]["bounding_box"]
    assert bb["min"]["z"] == pytest.approx(3.0)
    assert bb["max"]["z"] == pytest.approx(7.0)
    assert bb["max"]["x"] == pytest.approx(3.0)


def test_torus_is_exact_revolved_solid(server_standalone) -> None:
    import rhino3dm as r3

    _mcp, tools = server_standalone
    res = call_tool(
        tools,
        "rhino_torus",
        {"center": {"x": 0, "y": 0, "z": 0}, "major_radius": 5.0, "minor_radius": 1.0},
    )
    geom = _geometry(res["summary"]["object_id"])
    assert isinstance(geom, r3.Brep)
    assert geom.IsSolid
    assert len(geom.Faces) == 1
    tight = geom.GetTightBoundingBox()
    assert tight.Max.X == pytest.approx(6.0)
    assert tight.Max.Z == pytest.approx(1.0)
    assert tight.Min.Z == pytest.approx(-1.0)
