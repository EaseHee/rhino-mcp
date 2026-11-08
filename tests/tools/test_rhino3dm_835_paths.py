"""Standalone paths enabled by rhino3dm 8.32+/8.35 APIs (v0.7.0)."""

from __future__ import annotations

import math
import os
from types import SimpleNamespace
from typing import Any

import pytest
import rhino3dm as r3

from rhino_mcp import document as document_mod
from rhino_mcp.document import registry
from rhino_mcp.tools import _helpers
from rhino_mcp.tools.geometry_validation import edge_valence
from rhino_mcp.tools.schedule import curve_length
from rhino_mcp.tools.subd import subd_summary
from rhino_mcp.utils.error_handling import ToolError
from tests.conftest import call_tool

_RHINO9_SAMPLE = (
    "/Applications/Rhino 9.app/Contents/Frameworks/RhCore.framework/Versions/A/Resources/"
    "en.lproj/Blocks/Elements/Cars/car1b.3dm"
)


def _add_geometry(geom: Any) -> str:
    handle = registry().get_or_create("active")
    return handle.add_index(handle.file3dm.Objects.Add(geom, None))


def _rotated_sphere() -> r3.Brep:
    brep = r3.Sphere(r3.Point3d(0, 0, 0), 1.0).ToBrep()
    brep.Transform(r3.Transform.Rotation(math.pi / 4, r3.Vector3d(1, 1, 0), r3.Point3d(0, 0, 0)))
    return brep


# ---------------------------------------------------------------- dim style


def test_dimension_style_standalone_writes_table(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(
        tools,
        "rhino_annotation_dimension_style",
        {"name": "Arch 1-100", "font": "Arial", "text_height": 3.5, "arrow_size": 1.25},
    )
    s = res["summary"]
    assert s["index"] == 0
    assert s["name"] == "Arch 1-100"
    table = registry().get("active").file3dm.DimStyles
    assert len(table) == 1
    assert table[0].TextHeight == pytest.approx(3.5)
    assert table[0].ArrowLength == pytest.approx(1.25)
    assert table[0].Font.FamilyName == "Arial"


def test_dimension_style_duplicate_name_rejected(server_standalone) -> None:
    _mcp, tools = server_standalone
    call_tool(tools, "rhino_annotation_dimension_style", {"name": "Dup"})
    with pytest.raises(Exception, match="Invalid parameter: name"):
        call_tool(tools, "rhino_annotation_dimension_style", {"name": "Dup"})


@pytest.mark.parametrize("variant", [" Dup ", "dup", "DUP "])
def test_dimension_style_duplicate_after_normalisation_rejected(server_standalone, variant) -> None:
    _mcp, tools = server_standalone
    call_tool(tools, "rhino_annotation_dimension_style", {"name": "Dup"})
    with pytest.raises(Exception, match="Invalid parameter: name"):
        call_tool(tools, "rhino_annotation_dimension_style", {"name": variant})
    table = registry().get("active").file3dm.DimStyles
    assert [table[i].Name for i in range(len(table))] == ["Dup"]


def test_dimension_style_name_is_trimmed(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(tools, "rhino_annotation_dimension_style", {"name": "  Arch  "})
    assert res["summary"]["name"] == "Arch"


def test_dimension_style_survives_3dm_round_trip(server_standalone, tmp_path) -> None:
    _mcp, tools = server_standalone
    call_tool(tools, "rhino_annotation_dimension_style", {"name": "RT", "text_height": 4.0})
    target = registry().save("active", tmp_path / "ds.3dm")
    reread = r3.File3dm.Read(str(target))
    names = [reread.DimStyles[i].Name for i in range(len(reread.DimStyles))]
    assert "RT" in names


# --------------------------------------------------------------- naked edges


def test_naked_edges_closed_box_is_zero(server_standalone) -> None:
    _mcp, tools = server_standalone
    box = call_tool(
        tools,
        "rhino_box",
        {"corner": {"x": 0, "y": 0, "z": 0}, "size_x": 1.0, "size_y": 2.0, "size_z": 3.0},
    )
    res = call_tool(tools, "rhino_check_naked_edges", {"object_id": box["summary"]["object_id"]})
    assert res["summary"]["naked_edge_count"] == 0
    assert res["summary"]["non_manifold_edge_indices"] == []


def test_naked_edges_open_cylinder_reports_both_rims(server_standalone) -> None:
    _mcp, tools = server_standalone
    cyl = call_tool(
        tools,
        "rhino_cylinder",
        {"base_center": {"x": 0, "y": 0, "z": 0}, "radius": 2.0, "height": 5.0, "capped": False},
    )
    res = call_tool(tools, "rhino_check_naked_edges", {"object_id": cyl["summary"]["object_id"]})
    s = res["summary"]
    assert s["naked_edge_count"] == 2
    for edge in s["edges"]:
        assert edge["length"] == pytest.approx(2 * math.pi * 2.0, rel=1e-6)


def test_edge_valence_flat_surface_all_naked() -> None:
    srf = r3.PlaneSurface(r3.Plane.WorldXY(), r3.Interval(0, 1), r3.Interval(0, 2))
    brep = r3.Brep.CreateFromSurface(srf)
    assert edge_valence(brep) == [1, 1, 1, 1]


# --------------------------------------------------------------------- SubD


class _FakeIter:
    def __init__(self, items: list[Any]) -> None:
        self._items = items
        self._pos = 0

    @property
    def Count(self) -> int:
        return len(self._items)

    def First(self) -> Any:
        self._pos = 0
        return self._items[0] if self._items else SimpleNamespace()

    def Next(self) -> Any:
        self._pos += 1
        return self._items[self._pos] if self._pos < len(self._items) else None


def _fake_subd() -> SimpleNamespace:
    pt = SimpleNamespace(X=1.0, Y=2.0, Z=3.0)
    vtag = r3.SubDVertexTag
    etag = r3.SubDEdgeTag
    vertices = [
        SimpleNamespace(Id=1, Tag=vtag.Corner, IsCorner=True, IsDart=False, ControlNetPoint=pt),
        SimpleNamespace(Id=2, Tag=vtag.Smooth, IsCorner=False, IsDart=False, ControlNetPoint=pt),
        SimpleNamespace(Id=3, Tag=vtag.Crease, IsCorner=False, IsDart=False, ControlNetPoint=pt),
    ]

    def edge(index: int, tag: Any, faces: int, crease: bool, sharp: bool, sh: float) -> SimpleNamespace:
        return SimpleNamespace(
            Id=index, Tag=tag, FaceCount=faces, IsCrease=crease, IsSharp=sharp,
            EndSharpness=lambda _end, _sh=sh: _sh,
        )

    edges = [
        edge(10, etag.Crease, 1, True, False, 0.0),
        edge(11, etag.Smooth, 2, False, True, 2.5),
        edge(12, etag.Smooth, 2, False, False, 0.0),
    ]
    faces = [SimpleNamespace(EdgeCount=4), SimpleNamespace(EdgeCount=4), SimpleNamespace(EdgeCount=3)]
    return SimpleNamespace(
        Vertices=_FakeIter(vertices), Edges=_FakeIter(edges), Faces=_FakeIter(faces),
        VertexCount=3, EdgeCount=3, FaceCount=3, IsSolid=False,
    )


def test_subd_summary_counts_tags_and_creases() -> None:
    s = subd_summary(_fake_subd(), include_creases=True)
    assert s["vertex_tags"] == {"Corner": 1, "Crease": 1, "Smooth": 1}
    assert s["edge_tags"] == {"Crease": 1, "Smooth": 2}
    assert s["face_side_counts"] == {"3": 1, "4": 2}
    assert s["boundary_edge_count"] == 1
    assert s["crease_edge_count"] == 1
    assert s["sharp_edge_count"] == 1
    assert s["max_edge_sharpness"] == pytest.approx(2.5)
    assert s["corner_vertex_count"] == 1
    assert [c["edge_id"] for c in s["creases"]] == [10, 11]
    assert s["corners"] == [{"vertex_id": 1, "point": {"x": 1.0, "y": 2.0, "z": 3.0}}]


def test_subd_inspect_bridge_handler_emits_standalone_keys() -> None:
    # The C# handler cannot run here; guard the shared payload contract textually.
    import pathlib
    import re

    s = subd_summary(_fake_subd(), include_creases=True)
    expected = set(s) | {"object_id", "bounding_box"}
    expected |= set(s["creases"][0]) | set(s["corners"][0])
    src = (
        pathlib.Path(__file__).resolve().parents[2]
        / "rhino_plugin" / "csharp" / "Handlers" / "SubDHandler.cs"
    ).read_text(encoding="utf-8")
    inspect_body = src[src.index("public JObject Inspect("):]
    emitted = set(re.findall(r'\["([a-z_]+)"\]\s*=', inspect_body))
    assert expected - emitted == set()


def test_subd_inspect_standalone_on_real_subd(server_standalone) -> None:
    _mcp, tools = server_standalone
    gid = _add_geometry(r3.SubD())
    res = call_tool(tools, "rhino_subd_inspect", {"object_id": gid})
    s = res["summary"]
    assert s["object_id"] == gid
    assert (s["vertex_count"], s["edge_count"], s["face_count"]) == (0, 0, 0)
    assert s["creases"] == []
    info = call_tool(tools, "rhino_object_info", {"object_id": gid})
    assert info["summary"]["kind"] == "SubD"
    assert info["summary"]["face_count"] == 0


def test_subd_inspect_rejects_non_subd(server_standalone) -> None:
    _mcp, tools = server_standalone
    pt = call_tool(tools, "rhino_point", {"point": {"x": 0, "y": 0, "z": 0}})
    with pytest.raises(Exception, match="Invalid parameter: object_id"):
        call_tool(tools, "rhino_subd_inspect", {"object_id": pt["summary"]["object_id"]})


# -------------------------------------------------------------- tight bbox


def test_tight_bbox_option_in_query_analysis_schedule(server_standalone) -> None:
    _mcp, tools = server_standalone
    gid = _add_geometry(_rotated_sphere())
    loose = call_tool(tools, "rhino_bounding_box", {"object_ids": [gid], "tight": False})["summary"][
        "bounding_box"
    ]
    tight = call_tool(tools, "rhino_bounding_box", {"object_ids": [gid], "tight": True})["summary"][
        "bounding_box"
    ]
    assert tight["max"]["x"] < loose["max"]["x"] - 0.1
    # The default matches bridge mode, which always returns the exact box.
    default = call_tool(tools, "rhino_bounding_box", {"object_ids": [gid]})["summary"]["bounding_box"]
    assert default["max"]["x"] == pytest.approx(tight["max"]["x"])
    info = call_tool(tools, "rhino_object_info", {"object_id": gid, "tight": True})
    assert info["summary"]["bbox"]["max"]["x"] == pytest.approx(tight["max"]["x"])
    listed = call_tool(tools, "rhino_list_objects", {"tight": True})
    assert listed["summary"]["objects"][0]["bbox"]["max"]["x"] == pytest.approx(tight["max"]["x"])
    rows = call_tool(
        tools, "rhino_object_quantity", {"object_ids": [gid], "fields": ["bbox"], "tight": True}
    )["summary"]["rows"]
    assert rows[0]["bbox"]["max"]["x"] == pytest.approx(tight["max"]["x"])


# ------------------------------------------------------------ curve length


def test_curve_length_line_circle_polyline() -> None:
    assert curve_length(r3.LineCurve(r3.Point3d(0, 0, 0), r3.Point3d(3, 4, 0))) == pytest.approx(5.0)
    circle = r3.Circle(r3.Point3d(0, 0, 0), 3.0).ToNurbsCurve()
    assert curve_length(circle) == pytest.approx(2 * math.pi * 3.0, rel=1e-9)
    poly = r3.Polyline()
    for x, y in ((0, 0), (1, 0), (1, 2)):
        poly.Add(x, y, 0)
    assert curve_length(poly.ToPolylineCurve()) == pytest.approx(3.0)


@pytest.mark.parametrize("degree", [3, 5])
def test_curve_length_higher_degree_matches_dense_chord_sum(degree: int) -> None:
    pts = [r3.Point3d(i, math.sin(i) * 2, (i % 3) * 0.5) for i in range(12)]
    curve = r3.NurbsCurve.Create(False, degree, pts)
    t0, t1 = curve.Domain.T0, curve.Domain.T1
    n = 20000
    samples = [curve.PointAt(t0 + (t1 - t0) * i / n) for i in range(n + 1)]
    chord = sum(samples[i].DistanceTo(samples[i + 1]) for i in range(n))
    # A dense chord sum underestimates by O(1/n^2), well under 1e-7 here.
    assert curve_length(curve) == pytest.approx(chord, rel=1e-7)


def test_curve_length_long_polyline_is_exact() -> None:
    poly = r3.Polyline()
    expected = 0.0
    prev = None
    for i in range(500):
        p = r3.Point3d(i, (i * 7) % 5, (i * 3) % 2)
        poly.Add(p.X, p.Y, p.Z)
        if prev is not None:
            expected += prev.DistanceTo(p)
        prev = p
    assert curve_length(poly.ToPolylineCurve()) == pytest.approx(expected, rel=1e-12)


def test_object_info_curve_reports_length(server_standalone) -> None:
    _mcp, tools = server_standalone
    line = call_tool(
        tools, "rhino_line", {"start": {"x": 0, "y": 0, "z": 0}, "end": {"x": 0, "y": 6, "z": 8}}
    )
    info = call_tool(tools, "rhino_object_info", {"object_id": line["summary"]["object_id"]})
    assert info["summary"]["length"] == pytest.approx(10.0)


# ------------------------------------------------------- layer resolution


def test_resolve_layer_index_is_idempotent_for_normalised_names(fresh_doc) -> None:
    first = _helpers._resolve_layer_index(fresh_doc, " Walls ")
    again = _helpers._resolve_layer_index(fresh_doc, " Walls ")
    plain = _helpers._resolve_layer_index(fresh_doc, "Walls")
    assert first == again == plain
    assert len(fresh_doc.file3dm.Layers) == 1


def test_resolve_layer_index_rejects_blank_name(fresh_doc) -> None:
    with pytest.raises(ToolError):
        _helpers._resolve_layer_index(fresh_doc, "   ")


def test_find_layer_index_miss_returns_none_and_skips_bad_slots() -> None:
    class _Table:
        def __init__(self) -> None:
            self._rows = [SimpleNamespace(Name="A"), None, SimpleNamespace(Name="B")]

        def __len__(self) -> int:
            return 4  # one more slot than entries: mimics a stale/raising index

        def __getitem__(self, i: int) -> Any:
            if i >= len(self._rows):
                raise IndexError(i)
            return self._rows[i]

        def FindName(self, *_a: Any) -> None:
            return None

        def FindIndex(self, i: int) -> Any:
            raise IndexError(i)

    handle = SimpleNamespace(file3dm=SimpleNamespace(Layers=_Table()))
    assert _helpers.find_layer_index(handle, "B") == 2  # type: ignore[arg-type]
    assert _helpers.find_layer_index(handle, "missing") is None  # type: ignore[arg-type]


# ----------------------------------------------------------- document open


def _fake_r3(read: Any, version: int) -> SimpleNamespace:
    return SimpleNamespace(
        File3dm=SimpleNamespace(Read=read, ReadArchiveVersion=lambda _p: version),
    )


@pytest.mark.parametrize(
    ("read", "version", "pattern"),
    [
        (lambda _p: None, 100, r"archive version 100 is newer"),
        (lambda _p: (_ for _ in ()).throw(RuntimeError("boom")), 100, r"archive version 100 is newer"),
        (lambda _p: None, 80, r"unreadable or corrupt \(3dm archive version 80\)"),
        (lambda _p: None, 0, r"not a 3dm file"),
    ],
)
def test_open_unreadable_reports_archive_version(monkeypatch, tmp_path, read, version, pattern) -> None:
    path = tmp_path / "x.3dm"
    path.write_bytes(b"not really a 3dm")
    monkeypatch.setattr(document_mod, "r3", _fake_r3(read, version))
    with pytest.raises(ToolError, match=pattern) as info:
        registry().open(path)
    assert info.value.details["archive_version"] == version
    if version > document_mod.MAX_KNOWN_ARCHIVE_VERSION:
        assert "bridge mode" in info.value.hint


def test_open_real_garbage_file_is_tool_error(tmp_path) -> None:
    path = tmp_path / "garbage.3dm"
    path.write_bytes(b"garbage")
    with pytest.raises(ToolError, match="not a 3dm file"):
        registry().open(path)


@pytest.mark.skipif(not os.path.exists(_RHINO9_SAMPLE), reason="Rhino 9 sample file not installed")
def test_open_rhino9_archive_v90_reads() -> None:
    assert r3.File3dm.ReadArchiveVersion(_RHINO9_SAMPLE) == 90
    handle = registry().open(_RHINO9_SAMPLE)
    assert len(handle.file3dm.Objects) > 0


# ---------------------------------------------------------------- layer list


def test_layer_list_standalone_reports_lock_and_visibility(server_standalone) -> None:
    _mcp, tools = server_standalone
    f = registry().get_or_create("active").file3dm
    layer = r3.Layer()
    layer.Name = "Walls"
    layer.Locked = True
    layer.Visible = False
    f.Layers.Add(layer)
    res = call_tool(tools, "rhino_layer_list", {})
    walls = [lay for lay in res["summary"]["layers"] if lay["name"] == "Walls"]
    assert walls == [walls[0]]
    assert walls[0]["locked"] is True
    assert walls[0]["visible"] is False
