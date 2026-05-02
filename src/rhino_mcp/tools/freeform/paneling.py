"""Panel rationalisation for doubly-curved (free-form) surfaces.

Standalone offers a 4-corner approximation that's enough to drive
fabrication decisions: planarity error per panel and per-panel curvature
class (planar / single-curved / synclastic / anticlastic) computed from
sampled corner normals. Bridge mode upgrades the tools to use
RhinoCommon's true Gaussian curvature evaluation.
"""

from __future__ import annotations

import math
from typing import Annotated, Any
from uuid import UUID

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.tools._helpers import bridge_call, doc
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import not_found_error, parameter_error
from rhino_mcp.utils.registry import Mode


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )


class _UvGridIn(_DocArg):
    surface_id: str = Field(..., description="Surface (or single-face Brep) to panelise.")
    count_u: Annotated[int, Field(ge=1, le=512, description="Cell count along U.")]
    count_v: Annotated[int, Field(ge=1, le=512, description="Cell count along V.")]
    output: str = Field(
        "mesh",
        description="'mesh' produces a single quad mesh whose faces are the panels; 'curves' emits the U + V iso-curves; 'corners' returns just the corner points without writing geometry.",
    )
    layer: str | None = Field(None, description="Target layer.")


class _PlanarityIn(_DocArg):
    surface_id: str = Field(..., description="Surface to evaluate.")
    count_u: Annotated[int, Field(ge=1, le=512)] = Field(8)
    count_v: Annotated[int, Field(ge=1, le=512)] = Field(8)
    tolerance: Annotated[float, Field(gt=0)] = Field(
        0.001,
        description="Planarity tolerance (document units). Cells whose worst-corner deviation exceeds this are flagged as non-planar.",
    )


class _CurvClassIn(_DocArg):
    surface_id: str = Field(..., description="Surface to classify.")
    count_u: Annotated[int, Field(ge=1, le=512)] = Field(8)
    count_v: Annotated[int, Field(ge=1, le=512)] = Field(8)
    planar_tolerance: Annotated[float, Field(gt=0)] = Field(0.001)
    single_curve_tolerance: Annotated[float, Field(gt=0, le=1.0)] = Field(
        0.05,
        description="Threshold (radians) on per-axis normal change below which a direction is considered straight. 0.05 ~ 2.9°.",
    )


def _vec_sub(a: r3.Point3d, b: r3.Point3d) -> tuple[float, float, float]:
    return (a.X - b.X, a.Y - b.Y, a.Z - b.Z)


def _vec_add(*vs: tuple[float, float, float]) -> tuple[float, float, float]:
    sx = sy = sz = 0.0
    for x, y, z in vs:
        sx += x
        sy += y
        sz += z
    return sx, sy, sz


def _vec_scale(v: tuple[float, float, float], s: float) -> tuple[float, float, float]:
    return v[0] * s, v[1] * s, v[2] * s


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _length(v: tuple[float, float, float]) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _normalize(v: tuple[float, float, float]) -> tuple[float, float, float]:
    n = _length(v)
    return (v[0] / n, v[1] / n, v[2] / n) if n > 0 else (0.0, 0.0, 0.0)


def _normal_from_rh(n: r3.Vector3d) -> tuple[float, float, float]:
    return (n.X, n.Y, n.Z)


def _resolve_surface(handle: Any, gid: str) -> r3.Surface:
    obj = handle.file3dm.Objects.FindId(gid)
    if obj is None:
        raise not_found_error("object", gid)
    geom = obj.Geometry
    if isinstance(geom, r3.Surface):
        return geom
    if isinstance(geom, r3.Brep) and len(geom.Faces) == 1:
        return geom.Faces[0].UnderlyingSurface()  # type: ignore[attr-defined,return-value]
    raise parameter_error(
        "surface_id",
        "standalone paneling needs a Surface or single-face Brep; use bridge mode for general Breps",
    )


def _sample_grid(srf: r3.Surface, count_u: int, count_v: int) -> tuple[list[list[r3.Point3d]], list[list[tuple[float, float, float]]]]:
    """Sample (count_u+1) * (count_v+1) points and normals on a regular UV grid."""
    du = srf.Domain(0)
    dv = srf.Domain(1)
    rows_p: list[list[r3.Point3d]] = []
    rows_n: list[list[tuple[float, float, float]]] = []
    for j in range(count_v + 1):
        v = dv.T0 + (dv.T1 - dv.T0) * (j / count_v)
        row_p: list[r3.Point3d] = []
        row_n: list[tuple[float, float, float]] = []
        for i in range(count_u + 1):
            u = du.T0 + (du.T1 - du.T0) * (i / count_u)
            row_p.append(srf.PointAt(u, v))
            n = srf.NormalAt(u, v)
            row_n.append(_normal_from_rh(n))
        rows_p.append(row_p)
        rows_n.append(row_n)
    return rows_p, rows_n


def _angle_between(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    la, lb = _length(a), _length(b)
    if la == 0 or lb == 0:
        return 0.0
    c = max(-1.0, min(1.0, _dot(a, b) / (la * lb)))
    return math.acos(c)


def _classify_cell(
    p00: r3.Point3d,
    p10: r3.Point3d,
    p01: r3.Point3d,
    p11: r3.Point3d,
    n00: tuple[float, float, float],
    n10: tuple[float, float, float],
    n01: tuple[float, float, float],
    n11: tuple[float, float, float],
    planar_tol: float,
    single_curve_tol: float,
) -> tuple[str, float, float, float]:
    """Return (class, planarity_error, dN_du, dN_dv) for one quad cell.

    ``class`` is one of ``planar`` / ``single_curved_u`` / ``single_curved_v``
    / ``synclastic`` / ``anticlastic``. Single-curved variants name the
    direction *along* which the surface curves (perpendicular to the
    direction that stays straight).
    """
    # Planarity error: distance of P11 from the plane fitted through the
    # other three corners.
    e1 = _vec_sub(p10, p00)
    e2 = _vec_sub(p01, p00)
    n_plane = _normalize(_cross(e1, e2))
    if n_plane == (0.0, 0.0, 0.0):
        planarity = 0.0
    else:
        d = _vec_sub(p11, p00)
        planarity = abs(_dot(d, n_plane))

    # Average normal change along U / V (in radians).
    du_change = 0.5 * (_angle_between(n00, n10) + _angle_between(n01, n11))
    dv_change = 0.5 * (_angle_between(n00, n01) + _angle_between(n10, n11))

    if planarity < planar_tol and du_change < single_curve_tol and dv_change < single_curve_tol:
        return ("planar", planarity, du_change, dv_change)
    if du_change < single_curve_tol:
        return ("single_curved_v", planarity, du_change, dv_change)
    if dv_change < single_curve_tol:
        return ("single_curved_u", planarity, du_change, dv_change)
    # Both directions curve — distinguish synclastic vs anticlastic by the
    # signed Gaussian-curvature proxy: dot of (n10 - n00) cross (n01 - n00)
    # with the average panel normal. Positive → both curl same way (sphere),
    # negative → saddle.
    dnu = _vec_sub_n(n10, n00)
    dnv = _vec_sub_n(n01, n00)
    sign_proxy = _dot(_cross(dnu, dnv), n_plane)
    return ("synclastic" if sign_proxy > 0 else "anticlastic", planarity, du_change, dv_change)


def _vec_sub_n(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "UV-Grid Panels", "readOnlyHint": False})
    def rhino_uv_grid_panels(args: _UvGridIn) -> dict[str, Any]:
        """Sample a surface on a regular UxV grid and emit it as panels.

        ``output='mesh'`` writes a single quad mesh (one face per panel) to
        the doc; ``'curves'`` writes count_u+count_v isocurves; ``'corners'``
        only returns the (count_u+1) x (count_v+1) sample points without
        writing geometry.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.freeform.uv_grid_panels", args.model_dump())
        if args.output not in ("mesh", "curves", "corners"):
            raise parameter_error("output", "must be 'mesh', 'curves', or 'corners'", allowed="mesh, curves, corners")
        h = doc(args.doc_id)
        srf = _resolve_surface(h, args.surface_id)
        rows_p, _ = _sample_grid(srf, args.count_u, args.count_v)

        if args.output == "corners":
            corners = [
                {"i": i, "j": j, "x": rows_p[j][i].X, "y": rows_p[j][i].Y, "z": rows_p[j][i].Z}
                for j in range(len(rows_p))
                for i in range(len(rows_p[j]))
            ]
            return {
                "summary": {"corners": corners, "count_u": args.count_u, "count_v": args.count_v},
                "text": f"Sampled {len(corners)} grid corners ({args.count_u + 1} x {args.count_v + 1})",
            }

        if args.output == "curves":
            from rhino_mcp.tools._helpers import _resolve_layer_index

            attrs_template = r3.ObjectAttributes()
            if args.layer is not None:
                attrs_template.LayerIndex = _resolve_layer_index(h, args.layer)

            # Emit U-direction isocurves (one per V step)
            new_ids: list[str] = []
            du = srf.Domain(0)
            dv = srf.Domain(1)
            for j in range(args.count_v + 1):
                v = dv.T0 + (dv.T1 - dv.T0) * (j / args.count_v)
                iso = srf.IsoCurve(1, v)
                if iso is not None:
                    attrs = r3.ObjectAttributes()
                    attrs.LayerIndex = attrs_template.LayerIndex
                    nid = h.file3dm.Objects.Add(iso, attrs)
                    new_ids.append(h.add_index(nid))
            for i in range(args.count_u + 1):
                u = du.T0 + (du.T1 - du.T0) * (i / args.count_u)
                iso = srf.IsoCurve(0, u)
                if iso is not None:
                    attrs = r3.ObjectAttributes()
                    attrs.LayerIndex = attrs_template.LayerIndex
                    nid = h.file3dm.Objects.Add(iso, attrs)
                    new_ids.append(h.add_index(nid))
            return {
                "summary": {"object_ids": new_ids, "count_u": args.count_u, "count_v": args.count_v},
                "text": f"Wrote {len(new_ids)} isocurves",
            }

        # Default: mesh
        m = r3.Mesh()
        # Vertices indexed (i + (count_u+1) * j)
        for j in range(args.count_v + 1):
            for i in range(args.count_u + 1):
                p = rows_p[j][i]
                m.Vertices.Add(p.X, p.Y, p.Z)
        for j in range(args.count_v):
            for i in range(args.count_u):
                a = i + (args.count_u + 1) * j
                b = (i + 1) + (args.count_u + 1) * j
                c = (i + 1) + (args.count_u + 1) * (j + 1)
                d = i + (args.count_u + 1) * (j + 1)
                m.Faces.AddFace(a, b, c, d)

        attrs = r3.ObjectAttributes()
        if args.layer is not None:
            from rhino_mcp.tools._helpers import _resolve_layer_index

            attrs.LayerIndex = _resolve_layer_index(h, args.layer)
        new_id: UUID = h.file3dm.Objects.Add(m, attrs)
        gid = h.add_index(new_id)
        return {
            "summary": {
                "object_id": gid,
                "count_u": args.count_u,
                "count_v": args.count_v,
                "panel_count": args.count_u * args.count_v,
            },
            "text": f"Wrote panel mesh: {args.count_u * args.count_v} quads",
        }

    @mcp.tool(annotations={"title": "Panel Planarity Report", "readOnlyHint": True})
    def rhino_panel_planarity(args: _PlanarityIn) -> dict[str, Any]:
        """Per-panel planarity report on a UxV grid sampled from a surface.

        Each cell's planarity error = distance of the 4th corner from the
        plane fitted through the first three. Cells whose error > tolerance
        are flagged. The returned ``stats`` block summarises max / mean /
        non-planar count for high-level reporting.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.freeform.panel_planarity", args.model_dump())
        h = doc(args.doc_id)
        srf = _resolve_surface(h, args.surface_id)
        rows_p, _ = _sample_grid(srf, args.count_u, args.count_v)

        cells: list[dict[str, Any]] = []
        max_err = 0.0
        sum_err = 0.0
        violators = 0
        for j in range(args.count_v):
            for i in range(args.count_u):
                p00 = rows_p[j][i]
                p10 = rows_p[j][i + 1]
                p01 = rows_p[j + 1][i]
                p11 = rows_p[j + 1][i + 1]
                e1 = _vec_sub(p10, p00)
                e2 = _vec_sub(p01, p00)
                n_plane = _normalize(_cross(e1, e2))
                if n_plane == (0.0, 0.0, 0.0):
                    err = 0.0
                else:
                    err = abs(_dot(_vec_sub(p11, p00), n_plane))
                cells.append({"i": i, "j": j, "planarity_error": err, "violates": err > args.tolerance})
                max_err = max(max_err, err)
                sum_err += err
                if err > args.tolerance:
                    violators += 1
        n = len(cells)
        return {
            "summary": {
                "count_u": args.count_u,
                "count_v": args.count_v,
                "panel_count": n,
                "tolerance": args.tolerance,
                "stats": {
                    "max_error": max_err,
                    "mean_error": sum_err / n if n else 0.0,
                    "non_planar_count": violators,
                    "planar_ratio": (n - violators) / n if n else 1.0,
                },
                "panels": cells,
            },
            "text": (
                f"Panel planarity: {violators}/{n} non-planar, "
                f"max error={max_err:.6g}, mean={sum_err / n if n else 0.0:.6g}"
            ),
        }

    @mcp.tool(annotations={"title": "Panel Curvature Classify", "readOnlyHint": True})
    def rhino_panel_curvature_classify(args: _CurvClassIn) -> dict[str, Any]:
        """Classify each UxV panel by curvature class (planar / single_* / synclastic / anticlastic).

        Standalone uses a 4-corner normal heuristic (no full Gaussian K).
        Bridge mode reports true Gaussian + mean curvature per cell.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.freeform.panel_curvature_classify", args.model_dump())
        h = doc(args.doc_id)
        srf = _resolve_surface(h, args.surface_id)
        rows_p, rows_n = _sample_grid(srf, args.count_u, args.count_v)

        cells: list[dict[str, Any]] = []
        counts: dict[str, int] = {
            "planar": 0,
            "single_curved_u": 0,
            "single_curved_v": 0,
            "synclastic": 0,
            "anticlastic": 0,
        }
        for j in range(args.count_v):
            for i in range(args.count_u):
                p00, p10, p01, p11 = rows_p[j][i], rows_p[j][i + 1], rows_p[j + 1][i], rows_p[j + 1][i + 1]
                n00, n10, n01, n11 = rows_n[j][i], rows_n[j][i + 1], rows_n[j + 1][i], rows_n[j + 1][i + 1]
                klass, planarity, du, dv = _classify_cell(
                    p00, p10, p01, p11, n00, n10, n01, n11,
                    args.planar_tolerance, args.single_curve_tolerance,
                )
                cells.append({
                    "i": i, "j": j, "class": klass,
                    "planarity_error": planarity,
                    "dN_du_radians": du,
                    "dN_dv_radians": dv,
                })
                counts[klass] = counts.get(klass, 0) + 1
        return {
            "summary": {
                "count_u": args.count_u,
                "count_v": args.count_v,
                "panel_count": args.count_u * args.count_v,
                "class_counts": counts,
                "panels": cells,
            },
            "text": (
                "Panel classes: "
                + ", ".join(f"{k}={v}" for k, v in counts.items() if v)
            ),
        }
