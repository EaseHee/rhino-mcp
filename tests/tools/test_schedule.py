"""Schedule tool tests (by_layer, by_user_text, by_material, export, object_quantity)."""

from __future__ import annotations

from pathlib import Path

import rhino3dm as r3

from rhino_mcp.document import registry
from tests.conftest import call_tool


def _mesh_box(min_pt, max_pt) -> r3.Mesh:
    m = r3.Mesh()
    a, b, c, d = (min_pt.X, min_pt.Y, min_pt.Z), (max_pt.X, min_pt.Y, min_pt.Z), (
        max_pt.X,
        max_pt.Y,
        min_pt.Z,
    ), (min_pt.X, max_pt.Y, min_pt.Z)
    e, f, g, h = (min_pt.X, min_pt.Y, max_pt.Z), (max_pt.X, min_pt.Y, max_pt.Z), (
        max_pt.X,
        max_pt.Y,
        max_pt.Z,
    ), (min_pt.X, max_pt.Y, max_pt.Z)
    for x, y, z in (a, b, c, d, e, f, g, h):
        m.Vertices.Add(x, y, z)
    m.Faces.AddFace(0, 1, 2, 3)
    m.Faces.AddFace(7, 6, 5, 4)
    m.Faces.AddFace(0, 4, 5, 1)
    m.Faces.AddFace(1, 5, 6, 2)
    m.Faces.AddFace(2, 6, 7, 3)
    m.Faces.AddFace(3, 7, 4, 0)
    return m


def _seed_doc(handle, *, walls: int = 3, floors: int = 1) -> None:
    f3 = handle.file3dm
    walls_layer = r3.Layer()
    walls_layer.Name = "Arch::Walls"
    li_walls = f3.Layers.Add(walls_layer)
    floors_layer = r3.Layer()
    floors_layer.Name = "Arch::Floors"
    li_floors = f3.Layers.Add(floors_layer)
    for i in range(walls):
        m = _mesh_box(r3.Point3d(i * 3, 0, 0), r3.Point3d(i * 3 + 2, 0.2, 3))
        attrs = r3.ObjectAttributes()
        attrs.LayerIndex = li_walls
        attrs.SetUserString("function", "wall")
        attrs.SetUserString("assembly_type", "W01")
        f3.Objects.AddMesh(m, attrs)
    for i in range(floors):
        m = _mesh_box(r3.Point3d(0, 0, 3 + i * 3), r3.Point3d(10, 5, 3.3 + i * 3))
        attrs = r3.ObjectAttributes()
        attrs.LayerIndex = li_floors
        attrs.SetUserString("function", "floor")
        attrs.SetUserString("assembly_type", "F01")
        f3.Objects.AddMesh(m, attrs)


def test_by_layer_aggregates(server_standalone) -> None:
    _mcp, tools = server_standalone
    handle = registry().get_or_create("active")
    _seed_doc(handle, walls=4, floors=2)
    res = call_tool(
        tools,
        "rhino_schedule_by_layer",
        {"fields": ["count", "area", "volume"]},
    )
    rows = res["summary"]["rows"]
    by_name = {r["layer"]: r for r in rows}
    assert by_name["Arch::Walls"]["count"] == 4
    assert by_name["Arch::Floors"]["count"] == 2
    assert by_name["Arch::Walls"]["volume"] > 0


def test_by_layer_filter_excludes_others(server_standalone) -> None:
    _mcp, tools = server_standalone
    handle = registry().get_or_create("active")
    _seed_doc(handle, walls=3, floors=2)
    res = call_tool(
        tools,
        "rhino_schedule_by_layer",
        {"layer_filter": ["Arch::Walls"], "fields": ["count"]},
    )
    rows = res["summary"]["rows"]
    assert len(rows) == 1
    assert rows[0]["layer"] == "Arch::Walls"
    assert rows[0]["count"] == 3


def test_by_layer_empty_doc_returns_empty_rows(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(tools, "rhino_schedule_by_layer", {"fields": ["count"]})
    assert res["summary"]["rows"] == []


def test_by_user_text_groups_by_assembly(server_standalone) -> None:
    _mcp, tools = server_standalone
    handle = registry().get_or_create("active")
    _seed_doc(handle, walls=5, floors=2)
    res = call_tool(
        tools,
        "rhino_schedule_by_user_text",
        {"group_key": "assembly_type", "fields": ["count"]},
    )
    rows = res["summary"]["rows"]
    assert {r["assembly_type"] for r in rows} == {"W01", "F01"}


def test_by_user_text_value_filter(server_standalone) -> None:
    _mcp, tools = server_standalone
    handle = registry().get_or_create("active")
    _seed_doc(handle, walls=2, floors=2)
    res = call_tool(
        tools,
        "rhino_schedule_by_user_text",
        {"group_key": "assembly_type", "value_filter": "W01", "fields": ["count"]},
    )
    assert len(res["summary"]["rows"]) == 1
    assert res["summary"]["rows"][0]["count"] == 2


def test_object_quantity_returns_per_object_rows(server_standalone) -> None:
    _mcp, tools = server_standalone
    handle = registry().get_or_create("active")
    _seed_doc(handle, walls=2)
    f3 = handle.file3dm
    ids = [str(f3.Objects[i].Attributes.Id) for i in range(len(f3.Objects))]
    res = call_tool(
        tools,
        "rhino_object_quantity",
        {"object_ids": ids, "fields": ["volume", "centroid", "bbox"]},
    )
    assert len(res["summary"]["rows"]) == len(ids)
    assert "centroid" in res["summary"]["rows"][0]


def test_export_csv_writes_file(server_standalone, tmp_path) -> None:
    _mcp, tools = server_standalone
    target = tmp_path / "out.csv"
    rows = [{"layer": "A", "count": 3, "area": 2.5}, {"layer": "B", "count": 1, "area": 1.0}]
    call_tool(
        tools,
        "rhino_schedule_export_csv",
        {"rows": rows, "path": str(target)},
    )
    text = Path(target).read_text(encoding="utf-8")
    assert "layer,count,area" in text.splitlines()[0]
