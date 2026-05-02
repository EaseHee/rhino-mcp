"""Document configuration tools — units, tolerances, base point.

These let the LLM read and set the document settings that silently break
modeling when ignored: a model authored in millimetres but reused with
metre-scale spacings produces nonsense; tolerance mismatches mask boolean
failures. Surfacing them as first-class tools moves these footguns from
"guess and pray" to "query and assert".
"""

from __future__ import annotations

import math
from typing import Annotated, Any

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.models.geometry_types import Point3dModel
from rhino_mcp.tools._helpers import bridge_call, doc, to_point
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import parameter_error
from rhino_mcp.utils.registry import Mode

# rhino3dm.UnitSystem maps and string aliases the LLM is likely to send.
_UNITS_NAME_TO_ENUM: dict[str, r3.UnitSystem] = {
    "mm": r3.UnitSystem.Millimeters,
    "millimeters": r3.UnitSystem.Millimeters,
    "millimetre": r3.UnitSystem.Millimeters,
    "millimetres": r3.UnitSystem.Millimeters,
    "cm": r3.UnitSystem.Centimeters,
    "centimeters": r3.UnitSystem.Centimeters,
    "m": r3.UnitSystem.Meters,
    "meter": r3.UnitSystem.Meters,
    "meters": r3.UnitSystem.Meters,
    "metre": r3.UnitSystem.Meters,
    "metres": r3.UnitSystem.Meters,
    "km": r3.UnitSystem.Kilometers,
    "in": r3.UnitSystem.Inches,
    "inch": r3.UnitSystem.Inches,
    "inches": r3.UnitSystem.Inches,
    "ft": r3.UnitSystem.Feet,
    "feet": r3.UnitSystem.Feet,
    "yd": r3.UnitSystem.Yards,
    "yards": r3.UnitSystem.Yards,
    "mi": r3.UnitSystem.Miles,
    "miles": r3.UnitSystem.Miles,
}

_UNITS_ENUM_TO_NAME: dict[int, str] = {
    int(r3.UnitSystem.Millimeters): "mm",
    int(r3.UnitSystem.Centimeters): "cm",
    int(r3.UnitSystem.Meters): "m",
    int(r3.UnitSystem.Kilometers): "km",
    int(r3.UnitSystem.Inches): "in",
    int(r3.UnitSystem.Feet): "ft",
    int(r3.UnitSystem.Yards): "yd",
    int(r3.UnitSystem.Miles): "mi",
}


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )


class _UnitsSetIn(_DocArg):
    units: str = Field(
        ...,
        description="Unit name. Accepted aliases: mm, cm, m, km, in, ft, yd, mi (and their long forms).",
    )
    scale_existing: bool = Field(
        False,
        description=(
            "If True, existing geometry is scaled to preserve real-world size when "
            "the unit changes. If False, only the document setting is updated and "
            "raw coordinates are reinterpreted under the new unit."
        ),
    )


class _ToleranceSetIn(_DocArg):
    absolute: Annotated[float, Field(gt=0, description="Model absolute tolerance (document units).")]
    angle_degrees: Annotated[float, Field(gt=0, le=90, description="Angle tolerance in degrees.")]
    relative: Annotated[float | None, Field(gt=0, lt=1)] = Field(
        None, description="Optional model relative tolerance (0 < r < 1)."
    )


class _OriginSetIn(_DocArg):
    base_point: Point3dModel = Field(..., description="New model base point in world coordinates.")
    mode: str = Field(
        "reference",
        description=(
            "'reference' stores the base point as a metadata anchor without moving geometry. "
            "'translate' shifts every existing object so the supplied point becomes the new origin."
        ),
    )


def _resolve_units(name: str) -> r3.UnitSystem:
    key = name.strip().lower()
    if key not in _UNITS_NAME_TO_ENUM:
        allowed = ", ".join(sorted(set(_UNITS_NAME_TO_ENUM.keys())))
        raise parameter_error("units", f"unknown unit '{name}'", allowed=allowed)
    return _UNITS_NAME_TO_ENUM[key]


def _scale_factor(src: r3.UnitSystem, dst: r3.UnitSystem) -> float:
    return r3.UnitSystem.UnitScale(src, dst)  # type: ignore[no-any-return]


def _summarise_settings(handle: Any) -> dict[str, Any]:
    s = handle.file3dm.Settings
    unit_int = int(s.ModelUnitSystem)
    return {
        "units": _UNITS_ENUM_TO_NAME.get(unit_int, str(s.ModelUnitSystem)),
        "tolerances": {
            "absolute": s.ModelAbsoluteTolerance,
            "angle_degrees": s.ModelAngleToleranceDegrees,
            "relative": s.ModelRelativeTolerance,
        },
        "base_point": {
            "x": s.ModelBasePoint.X,
            "y": s.ModelBasePoint.Y,
            "z": s.ModelBasePoint.Z,
        },
    }


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Get Document Units", "readOnlyHint": True})
    def rhino_document_units_get(args: _DocArg) -> dict[str, Any]:
        """Read the current document unit system."""
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.document_config.units_get", args.model_dump())
        h = doc(args.doc_id)
        unit_int = int(h.file3dm.Settings.ModelUnitSystem)
        name = _UNITS_ENUM_TO_NAME.get(unit_int, str(h.file3dm.Settings.ModelUnitSystem))
        return {"summary": {"units": name}, "text": f"Document units: {name}"}

    @mcp.tool(annotations={"title": "Set Document Units", "readOnlyHint": False})
    def rhino_document_units_set(args: _UnitsSetIn) -> dict[str, Any]:
        """Set the document unit system, optionally scaling existing geometry."""
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.document_config.units_set", args.model_dump())
        h = doc(args.doc_id)
        target = _resolve_units(args.units)
        prev = h.file3dm.Settings.ModelUnitSystem
        if args.scale_existing and int(prev) != int(target):
            factor = _scale_factor(prev, target)
            scale_xf = r3.Transform.Scale(r3.Plane.WorldXY(), factor, factor, factor) \
                if hasattr(r3.Plane, "WorldXY") else None
            if scale_xf is None:
                # rhino3dm's Scale(plane, fx, fy, fz) is overloaded; use the simpler 4x4 path.
                t = r3.Transform.Identity()
                t.M00 = factor
                t.M11 = factor
                t.M22 = factor
                scale_xf = t
            for i in range(len(h.file3dm.Objects)):
                obj = h.file3dm.Objects[i]
                geom = obj.Geometry
                geom.Transform(scale_xf)
        h.file3dm.Settings.ModelUnitSystem = target
        return {
            "summary": {"units": _UNITS_ENUM_TO_NAME.get(int(target), args.units), "scaled": args.scale_existing},
            "text": f"Units → {args.units} (scaled={args.scale_existing})",
        }

    @mcp.tool(annotations={"title": "Get Document Tolerances", "readOnlyHint": True})
    def rhino_tolerance_get(args: _DocArg) -> dict[str, Any]:
        """Read absolute / angle / relative model tolerances."""
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.document_config.tolerance_get", args.model_dump())
        h = doc(args.doc_id)
        s = h.file3dm.Settings
        return {
            "summary": {
                "absolute": s.ModelAbsoluteTolerance,
                "angle_degrees": s.ModelAngleToleranceDegrees,
                "relative": s.ModelRelativeTolerance,
            },
            "text": (
                f"Tolerances — abs={s.ModelAbsoluteTolerance}, "
                f"angle={s.ModelAngleToleranceDegrees}°, rel={s.ModelRelativeTolerance}"
            ),
        }

    @mcp.tool(annotations={"title": "Set Document Tolerances", "readOnlyHint": False})
    def rhino_tolerance_set(args: _ToleranceSetIn) -> dict[str, Any]:
        """Set absolute / angle / (optional) relative tolerances on the document."""
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.document_config.tolerance_set", args.model_dump())
        h = doc(args.doc_id)
        s = h.file3dm.Settings
        s.ModelAbsoluteTolerance = float(args.absolute)
        s.ModelAngleToleranceRadians = math.radians(float(args.angle_degrees))
        if args.relative is not None:
            s.ModelRelativeTolerance = float(args.relative)
        return {
            "summary": {
                "absolute": s.ModelAbsoluteTolerance,
                "angle_degrees": s.ModelAngleToleranceDegrees,
                "relative": s.ModelRelativeTolerance,
            },
            "text": "Tolerances updated",
        }

    @mcp.tool(annotations={"title": "Set Model Base Point", "readOnlyHint": False})
    def rhino_origin_set(args: _OriginSetIn) -> dict[str, Any]:
        """Set the model base point.

        ``mode='reference'`` stores the point as metadata only — useful for
        geo-referencing without disturbing existing geometry. ``mode='translate'``
        shifts every object so the supplied point becomes the new (0,0,0).
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.document_config.origin_set", args.model_dump())
        if args.mode not in ("reference", "translate"):
            raise parameter_error("mode", "must be 'reference' or 'translate'")
        h = doc(args.doc_id)
        new_origin = to_point(args.base_point)
        if args.mode == "translate":
            shift = r3.Transform.Translation(r3.Vector3d(-new_origin.X, -new_origin.Y, -new_origin.Z))
            for i in range(len(h.file3dm.Objects)):
                obj = h.file3dm.Objects[i]
                obj.Geometry.Transform(shift)
            stored = r3.Point3d(0.0, 0.0, 0.0)
        else:
            stored = new_origin
        h.file3dm.Settings.ModelBasePoint = stored
        return {
            "summary": {"base_point": {"x": stored.X, "y": stored.Y, "z": stored.Z}, "mode": args.mode},
            "text": f"Base point set ({args.mode})",
        }

    @mcp.tool(annotations={"title": "Document Settings Summary", "readOnlyHint": True})
    def rhino_document_settings(args: _DocArg) -> dict[str, Any]:
        """Bundled units / tolerances / base point in one call."""
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.document_config.settings", args.model_dump())
        h = doc(args.doc_id)
        s = _summarise_settings(h)
        return {
            "summary": s,
            "text": (
                f"{s['units']} | abs={s['tolerances']['absolute']} | "
                f"base=({s['base_point']['x']:.3f},{s['base_point']['y']:.3f},{s['base_point']['z']:.3f})"
            ),
        }
