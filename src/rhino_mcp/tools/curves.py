"""Curve query tools (length, evaluation, split, domain)."""

from __future__ import annotations

from typing import Annotated, Any

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.tools._helpers import doc
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import parameter_error
from rhino_mcp.utils.registry import Mode
from rhino_mcp.utils.serialization import bbox_to_dict, point_to_dict, vector_to_dict


class _CurveRef(BaseModel):
    doc_id: str = Field("active", description="Document handle.")
    object_id: str = Field(..., description="GUID of an existing curve.")


class _CurveAtParameter(_CurveRef):
    t: Annotated[float, Field(description="Parameter (within Domain).")]


class _CurveSplit(_CurveRef):
    parameters: list[float] = Field(..., min_length=1, description="Parameters at which to split.")


def _resolve_curve(handle, gid: str) -> r3.Curve:
    obj = handle.find_object(gid)
    geom = obj.Geometry
    if not isinstance(geom, r3.Curve):
        raise parameter_error("object_id", "must reference a curve", "curve GUID")
    return geom


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Curve Length", "readOnlyHint": True, "idempotentHint": True})
    def rhino_curve_length(args: _CurveRef) -> dict[str, Any]:
        """Return the curve's parametric domain and approximate length."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.curve.length", args.model_dump())
        h = doc(args.doc_id)
        c = _resolve_curve(h, args.object_id)
        # rhino3dm has no Length(); fall back to chord-sum via PointAt sampling.
        domain = c.Domain
        n = 256
        prev = c.PointAt(domain.T0)
        length = 0.0
        for i in range(1, n + 1):
            p = c.PointAt(domain.T0 + (domain.T1 - domain.T0) * i / n)
            dx, dy, dz = p.X - prev.X, p.Y - prev.Y, p.Z - prev.Z
            length += (dx * dx + dy * dy + dz * dz) ** 0.5
            prev = p
        return {
            "summary": {
                "object_id": args.object_id,
                "length": length,
                "domain": {"t0": domain.T0, "t1": domain.T1},
                "bounding_box": bbox_to_dict(c.GetBoundingBox()),
            },
            "text": f"Curve {args.object_id} length ≈ {length:.6f}",
        }

    @mcp.tool(annotations={"title": "Point on Curve", "readOnlyHint": True, "idempotentHint": True})
    def rhino_curve_point_at(args: _CurveAtParameter) -> dict[str, Any]:
        """Evaluate position and tangent at a parameter on the curve."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.curve.point_at", args.model_dump())
        h = doc(args.doc_id)
        c = _resolve_curve(h, args.object_id)
        if not (c.Domain.T0 <= args.t <= c.Domain.T1):
            raise parameter_error(
                "t",
                f"out of curve domain [{c.Domain.T0}, {c.Domain.T1}]",
                "value within Domain",
            )
        return {
            "summary": {
                "object_id": args.object_id,
                "t": args.t,
                "point": point_to_dict(c.PointAt(args.t)),
                "tangent": vector_to_dict(c.TangentAt(args.t)),
            },
            "text": f"Evaluated curve {args.object_id} at t={args.t}",
        }

    @mcp.tool(annotations={"title": "Split Curve at Parameters", "readOnlyHint": False})
    def rhino_curve_split(args: _CurveSplit) -> dict[str, Any]:
        """Split a curve at the given parameters; original is preserved."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.curve.split", args.model_dump())
        h = doc(args.doc_id)
        c = _resolve_curve(h, args.object_id)
        for t in args.parameters:
            if not (c.Domain.T0 <= t <= c.Domain.T1):
                raise parameter_error("parameters", f"value {t} outside curve domain")
        sorted_params = sorted(set(args.parameters))
        new_ids: list[str] = []
        starts = [c.Domain.T0, *sorted_params]
        ends = [*sorted_params, c.Domain.T1]
        for s, e in zip(starts, ends, strict=True):
            piece = c.Trim(s, e)
            if piece is not None and piece.IsValid:
                gid = h.add_index(h.file3dm.Objects.AddCurve(piece))
                new_ids.append(gid)
        return {
            "summary": {"source": args.object_id, "pieces": new_ids},
            "text": f"Split curve {args.object_id} into {len(new_ids)} pieces",
        }
