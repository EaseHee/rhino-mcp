"""Freeform skin / section / rib tools.

Standalone (rhino3dm) is constrained: it can chain ruled surfaces between
adjacent section curves but lacks a general loft-from-N-curves and lacks
arbitrary plane slicing. Bridge mode upgrades each tool to a true
RhinoCommon implementation.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

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


class _SkinIn(_DocArg):
    section_curve_ids: list[str] = Field(
        ...,
        min_length=2,
        description=(
            "Ordered section curves the skin should pass through. Two curves "
            "produce a single ruled surface; three or more produce a chain of "
            "ruled surfaces in standalone, or a true loft Brep in bridge mode."
        ),
    )
    closed: bool = Field(False, description="If True, the last section is rejoined to the first.")
    layer: str | None = Field(None, description="Target layer (created if absent).")
    name: str | None = Field(None, description="Optional name for the resulting object(s).")


class _SectionAtAxisIn(_DocArg):
    object_id: str = Field(..., description="Surface to section. Bridge mode also accepts Breps and meshes.")
    axis: str = Field(
        "z",
        description="Axis to slice along: 'x' / 'y' / 'z' for world axes (bridge), or 'u' / 'v' for surface isocurves (both modes).",
    )
    count: Annotated[int, Field(ge=2, le=512)] = Field(8, description="Number of slices.")
    layer: str | None = Field(None, description="Target layer for output curves.")


class _AxisRibsIn(_DocArg):
    object_id: str = Field(..., description="Surface or Brep to extract orthogonal ribs from (bridge only).")
    axis_a: str = Field("x", description="First rib axis ('x' / 'y' / 'z').")
    axis_b: str = Field("y", description="Second rib axis ('x' / 'y' / 'z'). Must differ from axis_a.")
    count_a: Annotated[int, Field(ge=1, le=128)] = Field(6)
    count_b: Annotated[int, Field(ge=1, le=128)] = Field(6)
    layer: str | None = Field(None)


def _find(handle: Any, gid: str) -> Any:
    obj = handle.file3dm.Objects.FindId(gid)
    if obj is None:
        raise not_found_error("object", gid)
    return obj


def _add_surface(handle: Any, surface: Any, *, layer: str | None, name: str | None) -> str:
    attrs = r3.ObjectAttributes()
    if layer is not None:
        from rhino_mcp.tools._helpers import _resolve_layer_index

        attrs.LayerIndex = _resolve_layer_index(handle, layer)
    if name is not None:
        attrs.Name = name
    new_id: UUID = handle.file3dm.Objects.Add(surface, attrs)
    return handle.add_index(new_id)


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Skin From Sections", "readOnlyHint": False})
    def rhino_skin_from_sections(args: _SkinIn) -> dict[str, Any]:
        """Generate a skin (loft-equivalent) through ordered section curves.

        - Standalone: chains ``CreateRuledSurface`` between adjacent section
          pairs and returns the list of surface IDs; the caller can join them
          downstream if needed.
        - Bridge: emits a single Brep loft via ``Brep.CreateFromLoft``.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.freeform.skin", args.model_dump())
        h = doc(args.doc_id)
        curves: list[r3.Curve] = []
        for cid in args.section_curve_ids:
            obj = _find(h, cid)
            geom = obj.Geometry
            if not isinstance(geom, r3.Curve):
                raise parameter_error("section_curve_ids", f"{cid} is not a curve")
            curves.append(geom)
        if args.closed:
            curves.append(curves[0])

        new_ids: list[str] = []
        for i in range(len(curves) - 1):
            srf = r3.NurbsSurface.CreateRuledSurface(curves[i], curves[i + 1])
            if srf is None:
                raise parameter_error(
                    "section_curve_ids",
                    f"could not create ruled surface between sections {i} and {i + 1}",
                )
            name = f"{args.name}_seg{i:02d}" if args.name else None
            new_ids.append(_add_surface(h, srf, layer=args.layer, name=name))

        return {
            "summary": {
                "object_ids": new_ids,
                "section_count": len(args.section_curve_ids),
                "closed": args.closed,
            },
            "text": (
                f"Skin built as {len(new_ids)} ruled surface(s) from "
                f"{len(args.section_curve_ids)} section(s)"
            ),
        }

    @mcp.tool(annotations={"title": "Section At Axis", "readOnlyHint": False})
    def rhino_section_at_axis(args: _SectionAtAxisIn) -> dict[str, Any]:
        """Slice a surface (or Brep / mesh in bridge) into ``count`` section curves.

        Standalone supports ``axis='u'`` and ``axis='v'`` (surface isocurves).
        World-axis slicing (``axis='x'/'y'/'z'``) requires bridge mode.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.freeform.section_at_axis", args.model_dump())
        if args.axis.lower() not in ("u", "v"):
            raise parameter_error(
                "axis",
                "standalone supports 'u' or 'v' (surface isocurves only); "
                "'x' / 'y' / 'z' world slicing is bridge-only",
                allowed="u, v",
            )
        h = doc(args.doc_id)
        obj = _find(h, args.object_id)
        geom = obj.Geometry
        if isinstance(geom, r3.Brep) and len(geom.Faces) == 1:
            srf = geom.Faces[0].UnderlyingSurface()  # type: ignore[attr-defined]
        elif isinstance(geom, r3.Surface):
            srf = geom
        else:
            raise parameter_error(
                "object_id",
                "standalone section requires a single-face Brep or a Surface; "
                "use bridge mode for general Breps and meshes",
            )

        domain = srf.Domain(0) if args.axis.lower() == "v" else srf.Domain(1)
        # IsoCurve(direction, constant) — direction=0 → curve runs along v
        # at constant u, direction=1 → along u at constant v.
        direction = 0 if args.axis.lower() == "v" else 1
        new_ids: list[str] = []
        for k in range(args.count):
            t = domain.T0 + (domain.T1 - domain.T0) * (k / max(args.count - 1, 1))
            iso = srf.IsoCurve(direction, t)
            if iso is None:
                continue
            attrs = r3.ObjectAttributes()
            if args.layer is not None:
                from rhino_mcp.tools._helpers import _resolve_layer_index

                attrs.LayerIndex = _resolve_layer_index(h, args.layer)
            new_id = h.file3dm.Objects.Add(iso, attrs)
            new_ids.append(h.add_index(new_id))

        return {
            "summary": {"object_ids": new_ids, "axis": args.axis, "count": len(new_ids)},
            "text": f"Sectioned {len(new_ids)} {args.axis}-isocurves",
        }

    if mode is Mode.STANDALONE:
        return  # bridge-only rib tool below

    @mcp.tool(annotations={"title": "Axis Ribs (waffle)", "readOnlyHint": False})
    def rhino_axis_ribs(args: _AxisRibsIn) -> dict[str, Any]:
        """Generate two orthogonal sets of section ribs (waffle-style fabrication, bridge only)."""
        require_bridge_only("rhino_axis_ribs")
        if args.axis_a == args.axis_b:
            raise parameter_error("axis_b", "axis_a and axis_b must differ")
        return bridge_call("rhino.freeform.axis_ribs", args.model_dump())
