"""Composition tool tests (place_grid, stack_floors, scatter, replicate_along_curve)."""

from __future__ import annotations

import pytest

from tests.conftest import call_tool


def _make_sphere(tools, x=0.0, y=0.0, z=0.0, r=1.0):
    res = call_tool(
        tools,
        "rhino_sphere",
        {"center": {"x": x, "y": y, "z": z}, "radius": r},
    )
    return res["summary"]["object_id"]


def test_place_grid_skip_origin_returns_count_minus_one(server_standalone) -> None:
    _mcp, tools = server_standalone
    sid = _make_sphere(tools)
    res = call_tool(
        tools,
        "rhino_place_grid",
        {
            "source_object_id": sid,
            "base_point": {"x": 0, "y": 0, "z": 0},
            "count_x": 3,
            "count_y": 4,
            "spacing_x": 5.0,
            "spacing_y": 5.0,
            "skip_origin": True,
        },
    )
    # 3 * 4 = 12 cells, origin skipped → 11 copies
    assert len(res["summary"]["object_ids"]) == 11


def test_place_grid_full_returns_full_count(server_standalone) -> None:
    _mcp, tools = server_standalone
    sid = _make_sphere(tools)
    res = call_tool(
        tools,
        "rhino_place_grid",
        {
            "source_object_id": sid,
            "base_point": {"x": 0, "y": 0, "z": 0},
            "count_x": 2,
            "count_y": 2,
            "spacing_x": 1.0,
            "spacing_y": 1.0,
            "skip_origin": False,
        },
    )
    assert len(res["summary"]["object_ids"]) == 4


def test_place_grid_invalid_source_raises(server_standalone) -> None:
    _mcp, tools = server_standalone
    with pytest.raises(Exception, match=r".+"):
        call_tool(
            tools,
            "rhino_place_grid",
            {
                "source_object_id": "00000000-0000-0000-0000-000000000000",
                "base_point": {"x": 0, "y": 0, "z": 0},
                "count_x": 2,
                "count_y": 2,
                "spacing_x": 1.0,
                "spacing_y": 1.0,
            },
        )


def test_stack_floors_produces_n_copies(server_standalone) -> None:
    _mcp, tools = server_standalone
    sid = _make_sphere(tools)
    res = call_tool(
        tools,
        "rhino_stack_floors",
        {
            "source_object_id": sid,
            "floor_count": 7,
            "floor_height": 3.5,
            "name_prefix": "Slab",
        },
    )
    assert len(res["summary"]["object_ids"]) == 7
    assert res["summary"]["floor_count"] == 7


def test_scatter_is_deterministic_with_seed(server_standalone) -> None:
    _mcp, tools = server_standalone
    sid = _make_sphere(tools)
    payload = {
        "source_object_id": sid,
        "boundary_min": {"x": 0, "y": 0, "z": 0},
        "boundary_max": {"x": 50, "y": 30, "z": 0},
        "count": 12,
        "seed": 42,
    }
    a = call_tool(tools, "rhino_scatter", payload)
    # Re-run with same seed should yield the same number of copies.
    b = call_tool(tools, "rhino_scatter", payload)
    assert len(a["summary"]["object_ids"]) == 12
    assert len(b["summary"]["object_ids"]) == 12


def test_scatter_invalid_boundary_raises(server_standalone) -> None:
    _mcp, tools = server_standalone
    sid = _make_sphere(tools)
    with pytest.raises(Exception, match=r".+"):
        call_tool(
            tools,
            "rhino_scatter",
            {
                "source_object_id": sid,
                "boundary_min": {"x": 10, "y": 10, "z": 0},
                "boundary_max": {"x": 5, "y": 5, "z": 0},
                "count": 4,
            },
        )


def test_replicate_along_curve_endpoint_count(server_standalone) -> None:
    _mcp, tools = server_standalone
    sid = _make_sphere(tools)
    line = call_tool(
        tools,
        "rhino_line",
        {"start": {"x": 0, "y": 0, "z": 0}, "end": {"x": 100, "y": 0, "z": 0}},
    )
    cid = line["summary"]["object_id"]
    res = call_tool(
        tools,
        "rhino_replicate_along_curve",
        {
            "source_object_id": sid,
            "curve_id": cid,
            "count": 5,
            "align_to_tangent": False,
            "include_endpoints": True,
        },
    )
    assert len(res["summary"]["object_ids"]) == 5


def test_replicate_along_curve_aligned_to_tangent(server_standalone) -> None:
    _mcp, tools = server_standalone
    sid = _make_sphere(tools)
    line = call_tool(
        tools,
        "rhino_line",
        {"start": {"x": 0, "y": 0, "z": 0}, "end": {"x": 0, "y": 50, "z": 0}},
    )
    cid = line["summary"]["object_id"]
    res = call_tool(
        tools,
        "rhino_replicate_along_curve",
        {
            "source_object_id": sid,
            "curve_id": cid,
            "count": 3,
            "align_to_tangent": True,
            "include_endpoints": True,
        },
    )
    assert len(res["summary"]["object_ids"]) == 3
    assert res["summary"]["aligned"] is True
