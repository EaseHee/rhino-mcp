"""Geometry validation tools — surface the topology issues that silently
break booleans, exports, and fabrication.

In standalone mode the rhino3dm API exposes high-level flags
(``IsValid`` / ``IsSolid`` / ``IsManifold`` / ``IsClosed``) plus Brep
face/loop/trim topology (8.32+), from which naked edges are derived;
self-intersection scans still require RhinoCommon (bridge).
The tools here surface what is available in each mode and route the
deeper checks through the bridge transparently.
"""

from __future__ import annotations

from typing import Any

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.tools._helpers import bridge_call, curve_length, doc
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import not_found_error, parameter_error
from rhino_mcp.utils.registry import Mode


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )


class _ObjectIn(_DocArg):
    object_id: str = Field(..., description="Object to validate.")


def _find_obj(handle: Any, gid: str) -> Any:
    obj = handle.file3dm.Objects.FindId(gid)
    if obj is None:
        raise not_found_error("object", gid)
    return obj


def _issue(severity: str, description: str, *, hint: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"severity": severity, "description": description}
    if hint is not None:
        payload["hint"] = hint
    return payload


def edge_valence(brep: Any) -> list[int]:
    """Return, per Brep edge, how many trims reference it (1 = naked, 2 = interior).

    rhino3dm has no ``BrepEdge.Valence`` / ``TrimIndices``; the count is built
    from ``BrepFace.Loops -> BrepLoop.Trims -> BrepTrim.EdgeIndex``. Singular
    trims (cone apex) carry ``EdgeIndex == -1`` and are skipped.
    """
    counts = [0] * len(brep.Edges)
    for fi in range(len(brep.Faces)):
        for loop in brep.Faces[fi].Loops:
            for trim in loop.Trims:
                ei = trim.EdgeIndex
                if 0 <= ei < len(counts):
                    counts[ei] += 1
    return counts


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Validate Brep", "readOnlyHint": True})
    def rhino_validate_brep(args: _ObjectIn) -> dict[str, Any]:
        """Validate a Brep — closed/solid/manifold, face/edge counts, log of issues.

        Standalone surfaces ``IsValid``/``IsSolid``/``IsManifold``/edge+face
        counts and the rhino3dm validation log. Bridge mode adds a list of
        naked-edge identifiers and lengths via RhinoCommon.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.validation.brep", args.model_dump())
        h = doc(args.doc_id)
        obj = _find_obj(h, args.object_id)
        geom = obj.Geometry
        if not isinstance(geom, r3.Brep):
            raise parameter_error("object_id", "must reference a Brep")
        is_valid, log = geom.IsValidWithLog
        issues: list[dict[str, Any]] = []
        if not is_valid:
            for line in (log or "").strip().splitlines():
                issues.append(_issue("error", line.strip()))
        if not geom.IsSolid:
            issues.append(_issue(
                "warning",
                "Brep is not closed (open shell)",
                hint="Use rhino_check_naked_edges to locate gaps; cap_holes or join may close it.",
            ))
        if not geom.IsManifold:
            issues.append(_issue(
                "error",
                "Brep is non-manifold",
                hint="Non-manifold edges break booleans and many exports. Split the body into manifold pieces.",
            ))
        return {
            "summary": {
                "object_id": args.object_id,
                "is_valid": is_valid,
                "is_solid": geom.IsSolid,
                "is_manifold": geom.IsManifold,
                "face_count": len(geom.Faces),
                "edge_count": len(geom.Edges),
                "issues": issues,
            },
            "text": (
                f"Brep {args.object_id}: valid={is_valid}, solid={geom.IsSolid}, "
                f"manifold={geom.IsManifold}, issues={len(issues)}"
            ),
        }

    @mcp.tool(annotations={"title": "Mesh Health Report", "readOnlyHint": True})
    def rhino_report_mesh_health(args: _ObjectIn) -> dict[str, Any]:
        """Mesh health — closed, manifold, vertex/face counts, validity log."""
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.validation.mesh", args.model_dump())
        h = doc(args.doc_id)
        obj = _find_obj(h, args.object_id)
        geom = obj.Geometry
        if not isinstance(geom, r3.Mesh):
            raise parameter_error("object_id", "must reference a Mesh")
        is_valid, log = geom.IsValidWithLog
        issues: list[dict[str, Any]] = []
        if not is_valid:
            for line in (log or "").strip().splitlines():
                issues.append(_issue("error", line.strip()))
        if not geom.IsClosed:
            issues.append(_issue(
                "warning",
                "Mesh is not closed (has open boundary)",
                hint="Boolean / volume / 3-D-print exports require a closed mesh.",
            ))
        if not geom.IsManifold:
            issues.append(_issue(
                "warning",
                "Mesh has non-manifold edges",
                hint="Split into manifold pieces or rebuild with cleaner topology.",
            ))
        return {
            "summary": {
                "object_id": args.object_id,
                "is_valid": is_valid,
                "is_closed": geom.IsClosed,
                "is_manifold": geom.IsManifold,
                "vertex_count": len(geom.Vertices),
                "face_count": len(geom.Faces),
                "issues": issues,
            },
            "text": (
                f"Mesh {args.object_id}: valid={is_valid}, closed={geom.IsClosed}, "
                f"vertices={len(geom.Vertices)}, faces={len(geom.Faces)}"
            ),
        }

    @mcp.tool(annotations={"title": "Curve Continuity Report", "readOnlyHint": True})
    def rhino_curve_continuity(args: _ObjectIn) -> dict[str, Any]:
        """Curve sanity — span count, closed flag, planarity, periodic, validity log."""
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.validation.curve", args.model_dump())
        h = doc(args.doc_id)
        obj = _find_obj(h, args.object_id)
        geom = obj.Geometry
        if not isinstance(geom, r3.Curve):
            raise parameter_error("object_id", "must reference a curve")
        is_valid, log = geom.IsValidWithLog
        issues: list[dict[str, Any]] = []
        if not is_valid:
            for line in (log or "").strip().splitlines():
                issues.append(_issue("error", line.strip()))
        return {
            "summary": {
                "object_id": args.object_id,
                "is_valid": is_valid,
                "is_closed": geom.IsClosed,
                "is_planar": geom.IsPlanar(),
                "is_periodic": geom.IsPeriodic,
                "span_count": geom.SpanCount,
                "degree": geom.Degree,
                "domain": [geom.Domain.T0, geom.Domain.T1],
                "issues": issues,
            },
            "text": (
                f"Curve {args.object_id}: closed={geom.IsClosed}, "
                f"planar={geom.IsPlanar()}, spans={geom.SpanCount}, deg={geom.Degree}"
            ),
        }

    @mcp.tool(annotations={"title": "Naked Edges", "readOnlyHint": True})
    def rhino_check_naked_edges(args: _ObjectIn) -> dict[str, Any]:
        """Enumerate naked (boundary) edges of a Brep with their lengths.

        Returns ``[{edge_index, length}, ...]`` plus the gap count. Standalone
        derives edge valence from Brep trims (an edge referenced by exactly
        one trim is naked) and also reports non-manifold edges (3+ trims).
        Bridge mode forwards to RhinoCommon ``BrepEdge.Valence``.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.validation.naked_edges", args.model_dump())
        h = doc(args.doc_id)
        geom: Any = _find_obj(h, args.object_id).Geometry
        if not isinstance(geom, r3.Brep):
            raise parameter_error("object_id", "must reference a Brep")
        valence = edge_valence(geom)
        edges = [
            {"edge_index": i, "length": curve_length(geom.Edges[i])}  # type: ignore[index]
            for i, n in enumerate(valence)
            if n == 1
        ]
        non_manifold = [i for i, n in enumerate(valence) if n > 2]
        return {
            "summary": {
                "object_id": args.object_id,
                "naked_edge_count": len(edges),
                "edges": edges,
                "non_manifold_edge_indices": non_manifold,
            },
            "text": f"Brep {args.object_id}: {len(edges)} naked edge(s)",
        }
