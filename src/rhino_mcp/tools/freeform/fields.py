"""Field-based deformation — attractors, smoothing.

Form-finding moves an LLM otherwise has to hand-code in
``rhino_execute_python``. ``rhino_attractor_displace_points`` shifts a
list of points toward or away from an attractor with a chosen falloff;
``rhino_smooth_polyline`` applies Laplacian smoothing to a polyline /
NURBS-curve control-point set.
"""

from __future__ import annotations

import math
from typing import Annotated, Any

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.models.geometry_types import Point3dModel
from rhino_mcp.tools._helpers import bridge_call, doc, to_point
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import not_found_error, parameter_error
from rhino_mcp.utils.registry import Mode


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )


class _AttractorIn(_DocArg):
    point_object_ids: list[str] = Field(
        ...,
        min_length=1,
        description="Object IDs of point objects to displace. (Curves and meshes are skipped.)",
    )
    attractor_point: Point3dModel | None = Field(
        None,
        description="Attractor location. Provide either ``attractor_point`` or ``attractor_curve_id``.",
    )
    attractor_curve_id: str | None = Field(
        None,
        description="Attractor as a curve (each point is pulled toward its closest sample on the curve).",
    )
    falloff: str = Field(
        "linear",
        description="Falloff with distance: 'linear' (1 - d/max), 'inverse' (1 / (1 + d)), 'gaussian' (exp(-(d/sigma)^2)).",
    )
    strength: float = Field(
        1.0,
        description="Displacement scale. Positive pulls toward the attractor; negative repels.",
    )
    max_distance: Annotated[float, Field(gt=0)] = Field(
        50.0,
        description="Distance beyond which the attractor has no effect. For 'gaussian' falloff this is also the sigma.",
    )


class _SmoothPolylineIn(_DocArg):
    curve_id: str = Field(
        ...,
        description="Polyline curve to smooth. NURBS curves are smoothed on their control-point net.",
    )
    iterations: Annotated[int, Field(ge=1, le=200)] = Field(3)
    factor: Annotated[float, Field(gt=0.0, le=1.0)] = Field(
        0.5, description="Per-iteration blend factor (0 = no change, 1 = full Laplacian replacement)."
    )
    pin_endpoints: bool = Field(True, description="If True, the first and last control points are not moved.")


def _find(handle: Any, gid: str) -> Any:
    obj = handle.file3dm.Objects.FindId(gid)
    if obj is None:
        raise not_found_error("object", gid)
    return obj


def _falloff_weight(d: float, max_d: float, kind: str) -> float:
    if d >= max_d and kind != "gaussian":
        return 0.0
    if kind == "linear":
        return 1.0 - d / max_d
    if kind == "inverse":
        return 1.0 / (1.0 + d)
    if kind == "gaussian":
        return math.exp(-(d * d) / (max_d * max_d))
    raise parameter_error("falloff", f"unknown falloff '{kind}'", allowed="linear, inverse, gaussian")


def _closest_param(crv: r3.Curve, p: r3.Point3d, samples: int = 64) -> tuple[r3.Point3d, float]:
    """Brute-force closest-point on a curve via uniform sampling.

    rhino3dm doesn't expose ``Curve.ClosestPoint`` in standalone, so we
    sample and minimise. ``samples`` 64 is sufficient for typical
    architectural attractor curves; bridge mode uses RhinoCommon's
    analytic version when accuracy matters.
    """
    dom = crv.Domain
    best_d2 = float("inf")
    best_p = crv.PointAt(dom.T0)
    for k in range(samples + 1):
        t = dom.T0 + (dom.T1 - dom.T0) * (k / samples)
        q = crv.PointAt(t)
        dx, dy, dz = q.X - p.X, q.Y - p.Y, q.Z - p.Z
        d2 = dx * dx + dy * dy + dz * dz
        if d2 < best_d2:
            best_d2 = d2
            best_p = q
    return best_p, math.sqrt(best_d2)


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Attractor Displace Points", "readOnlyHint": False})
    def rhino_attractor_displace_points(args: _AttractorIn) -> dict[str, Any]:
        """Displace each input point along the vector to an attractor with a falloff.

        Positive ``strength`` pulls toward the attractor; negative pushes
        away. The attractor is either a fixed point (``attractor_point``)
        or a curve (``attractor_curve_id``); for curves each point's
        attractor is the closest sample on the curve.

        Returns the *new* point IDs (the originals are deleted; this is a
        form-finding move, not a duplicating one).
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.freeform.attractor_displace_points", args.model_dump())
        if (args.attractor_point is None) == (args.attractor_curve_id is None):
            raise parameter_error(
                "attractor_point",
                "provide exactly one of 'attractor_point' or 'attractor_curve_id'",
            )
        h = doc(args.doc_id)
        attractor_pt = to_point(args.attractor_point) if args.attractor_point is not None else None
        attractor_crv = None
        if args.attractor_curve_id is not None:
            ao = _find(h, args.attractor_curve_id)
            if not isinstance(ao.Geometry, r3.Curve):
                raise parameter_error("attractor_curve_id", "must reference a curve")
            attractor_crv = ao.Geometry

        new_ids: list[str] = []
        skipped: list[str] = []
        for pid in args.point_object_ids:
            obj = _find(h, pid)
            geom = obj.Geometry
            if not isinstance(geom, r3.Point):
                skipped.append(pid)
                continue
            p = geom.Location
            if attractor_pt is not None:
                target = attractor_pt
                d = math.sqrt((p.X - target.X) ** 2 + (p.Y - target.Y) ** 2 + (p.Z - target.Z) ** 2)
            else:
                assert attractor_crv is not None
                target, d = _closest_param(attractor_crv, p)
            w = _falloff_weight(d, args.max_distance, args.falloff)
            if w == 0.0:
                continue  # outside influence — leave the point untouched
            tx = (target.X - p.X) * args.strength * w
            ty = (target.Y - p.Y) * args.strength * w
            tz = (target.Z - p.Z) * args.strength * w
            new_p = r3.Point3d(p.X + tx, p.Y + ty, p.Z + tz)
            attrs = obj.Attributes
            h.file3dm.Objects.Delete(obj.Attributes.Id)
            new_id = h.file3dm.Objects.Add(r3.Point(new_p), attrs)
            new_ids.append(h.add_index(new_id))

        return {
            "summary": {
                "object_ids": new_ids,
                "skipped": skipped,
                "input_count": len(args.point_object_ids),
                "moved": len(new_ids),
            },
            "text": (
                f"Attractor: moved {len(new_ids)}/{len(args.point_object_ids)} point(s) "
                f"(skipped {len(skipped)} non-point input(s))"
            ),
        }

    @mcp.tool(annotations={"title": "Smooth Polyline / Curve", "readOnlyHint": False})
    def rhino_smooth_polyline(args: _SmoothPolylineIn) -> dict[str, Any]:
        """Apply Laplacian smoothing to a polyline (or NURBS curve via its control points).

        Each iteration replaces every interior point P_i with
        ``(1 - factor) * P_i + factor * (P_{i-1} + P_{i+1}) / 2``.
        With ``pin_endpoints=True`` the first and last points are held.
        Returns the new curve's object_id (the input is replaced).
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.freeform.smooth_polyline", args.model_dump())
        h = doc(args.doc_id)
        obj = _find(h, args.curve_id)
        geom = obj.Geometry
        pts: list[r3.Point3d] = []
        if isinstance(geom, r3.PolylineCurve):
            poly = geom.ToPolyline()
            for i in range(len(poly)):
                pts.append(poly[i])
            is_polyline = True
        elif isinstance(geom, r3.NurbsCurve):
            nc = geom
            for i in range(nc.Points.Count):
                cp = nc.Points[i]
                pts.append(r3.Point3d(cp.Location.X, cp.Location.Y, cp.Location.Z))
            is_polyline = False
        else:
            raise parameter_error("curve_id", "must reference a polyline or NURBS curve")

        n = len(pts)
        if n < 3:
            return {
                "summary": {"object_id": args.curve_id, "iterations": 0},
                "text": "Curve has fewer than 3 points; nothing to smooth.",
            }

        # Iterative Laplacian smoothing
        for _ in range(args.iterations):
            new_pts = list(pts)
            for i in range(1, n - 1):
                avg_x = 0.5 * (pts[i - 1].X + pts[i + 1].X)
                avg_y = 0.5 * (pts[i - 1].Y + pts[i + 1].Y)
                avg_z = 0.5 * (pts[i - 1].Z + pts[i + 1].Z)
                new_pts[i] = r3.Point3d(
                    (1 - args.factor) * pts[i].X + args.factor * avg_x,
                    (1 - args.factor) * pts[i].Y + args.factor * avg_y,
                    (1 - args.factor) * pts[i].Z + args.factor * avg_z,
                )
            if not args.pin_endpoints:
                # Smooth endpoints with their single neighbour.
                if n >= 2:
                    new_pts[0] = r3.Point3d(
                        (1 - args.factor) * pts[0].X + args.factor * pts[1].X,
                        (1 - args.factor) * pts[0].Y + args.factor * pts[1].Y,
                        (1 - args.factor) * pts[0].Z + args.factor * pts[1].Z,
                    )
                    new_pts[-1] = r3.Point3d(
                        (1 - args.factor) * pts[-1].X + args.factor * pts[-2].X,
                        (1 - args.factor) * pts[-1].Y + args.factor * pts[-2].Y,
                        (1 - args.factor) * pts[-1].Z + args.factor * pts[-2].Z,
                    )
            pts = new_pts

        # Build replacement curve
        if is_polyline:
            new_poly = r3.Polyline()
            for p in pts:
                new_poly.Add(p.X, p.Y, p.Z)
            new_geom = r3.PolylineCurve(new_poly)
        else:
            new_geom = r3.NurbsCurve.Create(
                False,
                geom.Degree if hasattr(geom, "Degree") else 3,
                pts,
            )
            if new_geom is None:
                # Fall back to polyline
                new_poly = r3.Polyline()
                for p in pts:
                    new_poly.Add(p.X, p.Y, p.Z)
                new_geom = r3.PolylineCurve(new_poly)
        attrs = obj.Attributes
        h.file3dm.Objects.Delete(obj.Attributes.Id)
        new_id = h.file3dm.Objects.Add(new_geom, attrs)
        gid = h.add_index(new_id)
        return {
            "summary": {"object_id": gid, "iterations": args.iterations, "factor": args.factor},
            "text": f"Smoothed curve: {args.iterations} iterations, factor={args.factor}",
        }
