"""Quantity / schedule tools — per-layer / per-material / per-user_text aggregation.

These tools collapse "iterate, measure, group, sum" into single calls so the
LLM can answer "how much CIP_concrete by area?" or "give me a window
schedule grouped by assembly_type" without driving a Python loop.

Standalone uses ``rhino3dm`` aggregation; bridge mode forwards to the C#
``ScheduleHandler`` which uses ``AreaMassProperties`` / ``VolumeMassProperties``
for accurate Brep area/volume.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.tools._helpers import MAX_OBJECT_IDS, bridge_call, doc
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import not_found_error, parameter_error
from rhino_mcp.utils.registry import Mode

_DEFAULT_FIELDS = ("count", "area", "volume")
_ALLOWED_FIELDS = {"count", "area", "volume", "length"}


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )


class _ByLayerIn(_DocArg):
    layer_filter: list[str] | None = Field(
        None,
        description="If set, only these layer names (or path prefixes) are aggregated.",
    )
    fields: list[str] = Field(
        default_factory=lambda: list(_DEFAULT_FIELDS),
        description="Fields to compute per layer: count, area, volume, length.",
    )
    include_sublayers: bool = Field(
        True,
        description="If True, layers under each filter (Arch::Walls + Arch::Walls::Existing) are merged.",
    )


class _ByUserTextIn(_DocArg):
    group_key: str = Field(..., min_length=1, description="user_text key to group by, e.g. 'function'.")
    value_filter: str | None = Field(
        None,
        description="If set, only objects whose value matches are included.",
    )
    fields: list[str] = Field(default_factory=lambda: list(_DEFAULT_FIELDS))


class _ByMaterialIn(_DocArg):
    fields: list[str] = Field(default_factory=lambda: list(_DEFAULT_FIELDS))


class _ObjectQuantityIn(_DocArg):
    object_ids: list[str] = Field(..., min_length=1, max_length=MAX_OBJECT_IDS)
    fields: list[str] = Field(
        default_factory=lambda: ["area", "volume", "length", "centroid", "bbox"],
        description="Per-object measurements to include.",
    )


class _ExportCsvIn(BaseModel):
    rows: list[dict[str, Any]] = Field(..., min_length=1)
    path: str = Field(..., description="Absolute output CSV path.")
    columns: list[str] | None = Field(
        None,
        description="Column order; defaults to the keys of the first row.",
    )


def _validate_fields(fields: list[str]) -> list[str]:
    bad = [f for f in fields if f not in _ALLOWED_FIELDS]
    if bad:
        raise parameter_error(
            "fields",
            f"unknown fields: {bad}",
            allowed=", ".join(sorted(_ALLOWED_FIELDS)),
        )
    return fields


def _measure_geom_area(geom: Any) -> float:
    if isinstance(geom, r3.Mesh):
        total = 0.0
        for i in range(len(geom.Faces)):
            face = geom.Faces[i]
            a = geom.Vertices[face[0]]
            b = geom.Vertices[face[1]]
            c = geom.Vertices[face[2]]
            d = geom.Vertices[face[3]]
            total += _tri_area(a, b, c)
            if face[2] != face[3]:
                total += _tri_area(a, c, d)
        return total
    return 0.0


def _tri_area(a: Any, b: Any, c: Any) -> float:
    ux, uy, uz = b.X - a.X, b.Y - a.Y, b.Z - a.Z
    vx, vy, vz = c.X - a.X, c.Y - a.Y, c.Z - a.Z
    cx = uy * vz - uz * vy
    cy = uz * vx - ux * vz
    cz = ux * vy - uy * vx
    return 0.5 * (cx * cx + cy * cy + cz * cz) ** 0.5


def _measure_geom_volume(geom: Any) -> float:
    if isinstance(geom, r3.Mesh):
        total = 0.0
        for i in range(len(geom.Faces)):
            face = geom.Faces[i]
            a = geom.Vertices[face[0]]
            b = geom.Vertices[face[1]]
            c = geom.Vertices[face[2]]
            d = geom.Vertices[face[3]]
            total += _tet_signed(a, b, c)
            if face[2] != face[3]:
                total += _tet_signed(a, c, d)
        return abs(total)
    return 0.0


def _tet_signed(a: Any, b: Any, c: Any) -> float:
    return (
        a.X * (b.Y * c.Z - b.Z * c.Y)
        - a.Y * (b.X * c.Z - b.Z * c.X)
        + a.Z * (b.X * c.Y - b.Y * c.X)
    ) / 6.0


def _measure_geom_length(geom: Any) -> float:
    if isinstance(geom, r3.Curve):
        try:
            return float(geom.GetLength())
        except Exception:  # pragma: no cover - rhino3dm version safety
            return 0.0
    return 0.0


def _accumulate(row: dict[str, Any], geom: Any, fields: list[str]) -> None:
    if "count" in fields:
        row["count"] = row.get("count", 0) + 1
    if "area" in fields:
        row["area"] = round(row.get("area", 0.0) + _measure_geom_area(geom), 6)
    if "volume" in fields:
        row["volume"] = round(row.get("volume", 0.0) + _measure_geom_volume(geom), 6)
    if "length" in fields:
        row["length"] = round(row.get("length", 0.0) + _measure_geom_length(geom), 6)


def _layer_path(layer: Any) -> str:
    return layer.FullPath if hasattr(layer, "FullPath") and layer.FullPath else layer.Name


def _layer_matches(path: str, filters: list[str] | None, include_sublayers: bool) -> bool:
    if not filters:
        return True
    for f in filters:
        if path == f:
            return True
        if include_sublayers and path.startswith(f"{f}::"):
            return True
    return False


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Schedule by Layer", "readOnlyHint": True})
    def rhino_schedule_by_layer(args: _ByLayerIn) -> dict[str, Any]:
        """Aggregate objects per layer with optional filter and sublayer merging.

        Returns ``rows`` (one entry per layer) plus a ``totals`` block.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.schedule.by_layer", args.model_dump())
        fields = _validate_fields(args.fields)
        h = doc(args.doc_id)
        f = h.file3dm
        layer_paths: dict[int, str] = {}
        for i in range(len(f.Layers)):
            layer_paths[i] = _layer_path(f.Layers[i])

        rows_by_layer: dict[str, dict[str, Any]] = {}
        for i in range(len(f.Objects)):
            obj = f.Objects[i]
            li = obj.Attributes.LayerIndex
            path = layer_paths.get(li, "")
            if not _layer_matches(path, args.layer_filter, args.include_sublayers):
                continue
            row = rows_by_layer.setdefault(path, {"layer": path})
            _accumulate(row, obj.Geometry, fields)

        rows = sorted(rows_by_layer.values(), key=lambda r: r["layer"])
        totals = {field: 0.0 for field in fields if field != "count"}
        if "count" in fields:
            totals["count"] = 0
        for r in rows:
            for f_ in fields:
                if f_ in r:
                    totals[f_] = totals.get(f_, 0) + r[f_]
        return {
            "summary": {
                "rows": rows,
                "totals": totals,
                "row_count": len(rows),
                "fields": fields,
            },
            "text": f"Schedule by layer: {len(rows)} row(s), totals={totals}",
        }

    @mcp.tool(annotations={"title": "Schedule by User Text", "readOnlyHint": True})
    def rhino_schedule_by_user_text(args: _ByUserTextIn) -> dict[str, Any]:
        """Aggregate objects grouping by ``user_text[group_key]`` value.

        Useful for BIM-style schedules: ``group_key='assembly_type'`` produces a
        wall/window schedule, ``group_key='material'`` produces a material BOM.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.schedule.by_user_text", args.model_dump())
        fields = _validate_fields(args.fields)
        h = doc(args.doc_id)
        f = h.file3dm
        rows_by_value: dict[str, dict[str, Any]] = {}
        for i in range(len(f.Objects)):
            obj = f.Objects[i]
            value = obj.Attributes.GetUserString(args.group_key) or ""
            if not value:
                continue
            if args.value_filter is not None and value != args.value_filter:
                continue
            row = rows_by_value.setdefault(value, {args.group_key: value})
            _accumulate(row, obj.Geometry, fields)

        rows = sorted(rows_by_value.values(), key=lambda r: r[args.group_key])
        return {
            "summary": {
                "rows": rows,
                "group_key": args.group_key,
                "row_count": len(rows),
                "fields": fields,
            },
            "text": f"Schedule by '{args.group_key}': {len(rows)} group(s)",
        }

    @mcp.tool(annotations={"title": "Schedule by Material", "readOnlyHint": True})
    def rhino_schedule_by_material(args: _ByMaterialIn) -> dict[str, Any]:
        """Aggregate objects grouped by assigned material name.

        Standalone treats ``MaterialIndex == -1`` (default material) as
        'Default'. Bridge mode resolves each object's effective material via
        Rhino's render content lookup.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.schedule.by_material", args.model_dump())
        fields = _validate_fields(args.fields)
        h = doc(args.doc_id)
        f = h.file3dm
        materials: dict[int, str] = {-1: "Default"}
        for i in range(len(f.Materials)):
            materials[i] = f.Materials[i].Name or f"Material_{i}"

        rows_by_mat: dict[str, dict[str, Any]] = {}
        for i in range(len(f.Objects)):
            obj = f.Objects[i]
            mat_idx = obj.Attributes.MaterialIndex
            mat_name = materials.get(mat_idx, "Default")
            row = rows_by_mat.setdefault(mat_name, {"material": mat_name})
            _accumulate(row, obj.Geometry, fields)

        rows = sorted(rows_by_mat.values(), key=lambda r: r["material"])
        return {
            "summary": {"rows": rows, "row_count": len(rows), "fields": fields},
            "text": f"Schedule by material: {len(rows)} material(s)",
        }

    @mcp.tool(annotations={"title": "Object Quantities", "readOnlyHint": True})
    def rhino_object_quantity(args: _ObjectQuantityIn) -> dict[str, Any]:
        """Per-object measurement table — one row per object_id with the requested fields."""
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.schedule.object_quantity", args.model_dump())
        h = doc(args.doc_id)
        rows: list[dict[str, Any]] = []
        for oid in args.object_ids:
            obj = h.file3dm.Objects.FindId(oid)
            if obj is None:
                raise not_found_error("object", oid)
            geom = obj.Geometry
            entry: dict[str, Any] = {"object_id": oid, "kind": type(geom).__name__}
            if "area" in args.fields:
                entry["area"] = round(_measure_geom_area(geom), 6)
            if "volume" in args.fields:
                entry["volume"] = round(_measure_geom_volume(geom), 6)
            if "length" in args.fields:
                entry["length"] = round(_measure_geom_length(geom), 6)
            if "centroid" in args.fields:
                bb = geom.GetBoundingBox()
                cx = 0.5 * (bb.Min.X + bb.Max.X)
                cy = 0.5 * (bb.Min.Y + bb.Max.Y)
                cz = 0.5 * (bb.Min.Z + bb.Max.Z)
                entry["centroid"] = {"x": cx, "y": cy, "z": cz}
            if "bbox" in args.fields:
                bb = geom.GetBoundingBox()
                entry["bbox"] = {
                    "min": {"x": bb.Min.X, "y": bb.Min.Y, "z": bb.Min.Z},
                    "max": {"x": bb.Max.X, "y": bb.Max.Y, "z": bb.Max.Z},
                }
            rows.append(entry)
        return {
            "summary": {"rows": rows, "row_count": len(rows)},
            "text": f"Object quantities: {len(rows)} row(s)",
        }

    @mcp.tool(annotations={"title": "Export Schedule CSV", "readOnlyHint": False})
    def rhino_schedule_export_csv(args: _ExportCsvIn) -> dict[str, Any]:
        """Write rows produced by any rhino_schedule_* tool to CSV."""
        target = Path(args.path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        cols = args.columns or list(args.rows[0].keys())
        with target.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            writer.writeheader()
            for r in args.rows:
                serialised = {
                    k: (
                        ",".join(f"{vv:.3f}" if isinstance(vv, float) else str(vv) for vv in v.values())
                        if isinstance(v, dict)
                        else v
                    )
                    for k, v in r.items()
                }
                writer.writerow(serialised)
        return {
            "summary": {"path": str(target), "row_count": len(args.rows), "columns": cols},
            "text": f"Wrote {len(args.rows)} row(s) to {target}",
        }
