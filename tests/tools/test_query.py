"""Query tool tests (standalone mode pagination, filtering)."""

from __future__ import annotations

from tests.conftest import call_tool


def _make_points(tools, count: int) -> list[str]:
    ids: list[str] = []
    for i in range(count):
        res = call_tool(tools, "rhino_point", {"point": {"x": float(i), "y": 0, "z": 0}})
        ids.append(res["summary"]["object_id"])
    return ids


def test_list_objects_includes_pagination_metadata(server_standalone) -> None:
    _mcp, tools = server_standalone
    ids = _make_points(tools, 5)

    res = call_tool(tools, "rhino_list_objects", {"limit": 3, "offset": 0})

    pagination = res["pagination"]
    assert pagination["total"] == 5
    assert pagination["offset"] == 0
    assert pagination["limit"] == 3
    assert pagination["returned"] == 3
    assert pagination["has_more"] is True
    assert len(res["summary"]["objects"]) == 3
    # Returned object_ids must be a prefix of the inserted set.
    returned_ids = [o["object_id"] for o in res["summary"]["objects"]]
    assert returned_ids == ids[:3]


def test_list_objects_pagination_last_page(server_standalone) -> None:
    _mcp, tools = server_standalone
    _make_points(tools, 5)

    res = call_tool(tools, "rhino_list_objects", {"limit": 3, "offset": 3})

    pagination = res["pagination"]
    assert pagination["total"] == 5
    assert pagination["offset"] == 3
    assert pagination["returned"] == 2
    assert pagination["has_more"] is False
    assert len(res["summary"]["objects"]) == 2


def test_list_objects_empty_document(server_standalone) -> None:
    _mcp, tools = server_standalone
    res = call_tool(tools, "rhino_list_objects", {"limit": 50, "offset": 0})
    pagination = res["pagination"]
    assert pagination["total"] == 0
    assert pagination["returned"] == 0
    assert pagination["has_more"] is False


def test_list_objects_kind_filter(server_standalone) -> None:
    _mcp, tools = server_standalone
    _make_points(tools, 2)
    call_tool(tools, "rhino_circle", {"center": {"x": 0, "y": 0, "z": 0}, "radius": 1.0})

    points = call_tool(tools, "rhino_list_objects", {"kind": "Point"})
    assert points["pagination"]["total"] == 2
    assert all(o["kind"] == "Point" for o in points["summary"]["objects"])
