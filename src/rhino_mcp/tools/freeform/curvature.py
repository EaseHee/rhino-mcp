"""Surface curvature analysis.

Standalone exposes the basic frame / normal evaluation that rhino3dm
supports plus a developability score sampled from neighbouring normals.
The full Gaussian / mean / principal curvatures require RhinoCommon
(``Surface.CurvatureAt``) and route through the bridge.
"""

from __future__ import annotations

import math
from typing import Annotated, Any

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.tools._helpers import bridge_call, doc, require_bridge_only
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import not_found_error, parameter_error
from rhino_mcp.utils.registry import Mode


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )


class _NormalAtIn(_DocArg):
    surface_id: str = Field(..., description="Surface (or single-face Brep).")
    u: Annotated[float, Field(ge=0.0, le=1.0, description="Normalised U parameter (0 .. 1).")]
    v: Annotated[float, Field(ge=0.0, le=1.0, description="Normalised V parameter (0 .. 1).")]


class _DevScoreIn(_DocArg):
    surface_id: str = Field(..., description="Surface to evaluate.")
    sample_u: Annotated[int, Field(ge=2, le=512)] = Field(16)
    sample_v: Annotated[int, Field(ge=2, le=512)] = Field(16)


class _CurvAtIn(_DocArg):
    surface_id: str = Field(..., description="Surface (bridge-only true Gaussian / mean / principal).")
    u: Annotated[float, Field(ge=0.0, le=1.0)]
    v: Annotated[float, Field(ge=0.0, le=1.0)]


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
        "standalone curvature requires a Surface or single-face Brep",
    )


def _normalised_param(srf: r3.Surface, t: float, axis: int) -> float:
    d = srf.Domain(axis)
    return d.T0 + (d.T1 - d.T0) * t


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Surface Normal At", "readOnlyHint": True})
    def rhino_surface_normal_at(args: _NormalAtIn) -> dict[str, Any]:
        """Evaluate the surface unit normal at a normalised (u, v).

        ``u`` and ``v`` are 0..1 ratios over the surface's domain; the
        actual parameters are computed internally so the LLM doesn't need
        to know the domain bounds.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.freeform.normal_at", args.model_dump())
        h = doc(args.doc_id)
        srf = _resolve_surface(h, args.surface_id)
        u = _normalised_param(srf, args.u, 0)
        v = _normalised_param(srf, args.v, 1)
        n = srf.NormalAt(u, v)
        p = srf.PointAt(u, v)
        return {
            "summary": {
                "point": {"x": p.X, "y": p.Y, "z": p.Z},
                "normal": {"x": n.X, "y": n.Y, "z": n.Z},
                "u": args.u,
                "v": args.v,
            },
            "text": f"Normal at u={args.u}, v={args.v}",
        }

    @mcp.tool(annotations={"title": "Surface Developable Score", "readOnlyHint": True})
    def rhino_surface_developable_score(args: _DevScoreIn) -> dict[str, Any]:
        """Estimate how far a surface deviates from being developable.

        Samples a (sample_u+1) x (sample_v+1) grid of normals; for each
        interior 2x2 block computes the maximum angle (in radians) between
        adjacent normals. Reports max / mean / RMS over the whole sheet
        plus a 0..1 normalised score (0 = perfectly developable,
        1 = π/2 normal swing within a single cell).

        A truly developable surface (cone, cylinder, plane) returns ~0;
        a sphere section returns a positive value proportional to the
        spanned solid angle.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.freeform.developable_score", args.model_dump())
        h = doc(args.doc_id)
        srf = _resolve_surface(h, args.surface_id)
        du = srf.Domain(0)
        dv = srf.Domain(1)
        normals: list[list[r3.Vector3d]] = []
        for j in range(args.sample_v + 1):
            v = dv.T0 + (dv.T1 - dv.T0) * (j / args.sample_v)
            row: list[r3.Vector3d] = []
            for i in range(args.sample_u + 1):
                u = du.T0 + (du.T1 - du.T0) * (i / args.sample_u)
                row.append(srf.NormalAt(u, v))
            normals.append(row)

        max_a = 0.0
        sum_a = 0.0
        sum_sq = 0.0
        n_pairs = 0
        for j in range(args.sample_v + 1):
            for i in range(args.sample_u + 1):
                n0 = normals[j][i]
                if i + 1 <= args.sample_u:
                    n1 = normals[j][i + 1]
                    a = _angle(n0, n1)
                    max_a = max(max_a, a)
                    sum_a += a
                    sum_sq += a * a
                    n_pairs += 1
                if j + 1 <= args.sample_v:
                    n1 = normals[j + 1][i]
                    a = _angle(n0, n1)
                    max_a = max(max_a, a)
                    sum_a += a
                    sum_sq += a * a
                    n_pairs += 1
        mean = sum_a / n_pairs if n_pairs else 0.0
        rms = math.sqrt(sum_sq / n_pairs) if n_pairs else 0.0
        return {
            "summary": {
                "max_radians": max_a,
                "mean_radians": mean,
                "rms_radians": rms,
                "score_normalised": min(max_a / (math.pi / 2), 1.0),
                "sample_u": args.sample_u,
                "sample_v": args.sample_v,
            },
            "text": (
                f"Developability: max={math.degrees(max_a):.2f}°, mean={math.degrees(mean):.2f}°, "
                f"score={min(max_a / (math.pi / 2), 1.0):.3f} (0=developable, 1=fully doubly-curved)"
            ),
        }

    if mode is Mode.STANDALONE:
        return  # bridge-only true curvature evaluation below

    @mcp.tool(annotations={"title": "Surface Curvature At (bridge)", "readOnlyHint": True})
    def rhino_surface_curvature_at(args: _CurvAtIn) -> dict[str, Any]:
        """Evaluate true Gaussian / mean / principal curvatures at (u, v) (bridge only)."""
        require_bridge_only("rhino_surface_curvature_at")
        return bridge_call("rhino.freeform.curvature_at", args.model_dump())


def _angle(a: r3.Vector3d, b: r3.Vector3d) -> float:
    la = math.sqrt(a.X * a.X + a.Y * a.Y + a.Z * a.Z)
    lb = math.sqrt(b.X * b.X + b.Y * b.Y + b.Z * b.Z)
    if la == 0 or lb == 0:
        return 0.0
    c = (a.X * b.X + a.Y * b.Y + a.Z * b.Z) / (la * lb)
    return math.acos(max(-1.0, min(1.0, c)))
