"""Drawing-set tools — sheet, view placement, title block, PDF export.

These collapse the "model -> drawing set" workflow into call-bundles so the
LLM can issue a single instruction ("emit a 1:100 plan + east elevation +
section A on an A3 sheet") rather than orchestrating ``rhino_make2d``,
transforms, and annotation creation by hand.

Standalone (rhino3dm) supports sheet metadata, title block, north arrow,
and scale bar drawing on a layer-based "sheet" surrogate. View placement,
section cuts and PDF export require RhinoCommon (bridge mode) because they
need ``Make2DCommand``, projection, and ``FilePdf``.
"""

from __future__ import annotations

import math
from typing import Annotated, Any
from uuid import UUID

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.models.geometry_types import Point3dModel
from rhino_mcp.tools._helpers import (
    MAX_OBJECT_IDS,
    bridge_call,
    doc,
    require_bridge_only,
    to_point,
)
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import not_found_error, parameter_error
from rhino_mcp.utils.registry import Mode

_SHEET_USER_TEXT_KEYS = ("sheet_name", "sheet_width_mm", "sheet_height_mm", "sheet_scale")


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )


class _SheetCreateIn(_DocArg):
    name: str = Field(..., min_length=1, description="Sheet name (used as layer + title-block label).")
    width_mm: Annotated[float, Field(gt=0, le=10000)] = 420.0
    height_mm: Annotated[float, Field(gt=0, le=10000)] = 297.0
    scale_denominator: Annotated[int, Field(ge=1, le=10000)] = 100
    origin: Point3dModel = Field(
        default_factory=lambda: Point3dModel(x=0.0, y=0.0, z=0.0),
        description="World-space anchor for the sheet's lower-left corner.",
    )


class _ViewPlaceIn(_DocArg):
    sheet_id: str = Field(..., description="Sheet id from rhino_drawing_sheet_create.")
    object_ids: list[str] = Field(..., min_length=1, max_length=MAX_OBJECT_IDS)
    view_plane: str = Field(
        "Top",
        description="Top | Front | Right | Back | Left | Bottom (world projection).",
    )
    target_origin: Point3dModel = Field(
        ..., description="Lower-left of the placed view inside the sheet."
    )
    viewport_scale: Annotated[float, Field(gt=0, le=1000)] = Field(
        0.01,
        description="Drawing unit per model unit (0.01 = 1:100). Defaults to the sheet scale.",
    )
    hidden_line: bool = Field(True, description="Apply Make2D hidden-line filtering.")
    layer: str | None = Field(None, description="Layer for the placed view geometry.")


class _SectionCutIn(_DocArg):
    sheet_id: str = Field(...)
    object_ids: list[str] = Field(..., min_length=1, max_length=MAX_OBJECT_IDS)
    plane_origin: Point3dModel
    plane_normal: Point3dModel
    target_origin: Point3dModel
    viewport_scale: Annotated[float, Field(gt=0, le=1000)] = 0.01
    layer: str | None = Field(None)


class _TitleBlockIn(_DocArg):
    sheet_id: str = Field(...)
    project: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    scale_text: str = Field("1:100")
    date_iso: str = Field(..., description="ISO-8601 date, e.g. 2026-05-03.")
    drawn_by: str = Field("")
    sheet_no: str = Field("A-001")
    north_arrow_angle_deg: float = Field(0.0, description="Bearing of north relative to sheet +Y, clockwise.")
    add_north_arrow: bool = Field(True)
    add_scale_bar: bool = Field(True)


class _ExportPdfIn(_DocArg):
    sheet_id: str = Field(...)
    path: str = Field(..., description="Absolute output PDF path.")
    dpi: Annotated[int, Field(ge=72, le=2400)] = 300


def _find_sheet(handle: Any, sheet_id: str) -> Any:
    obj = handle.file3dm.Objects.FindId(sheet_id)
    if obj is None:
        raise not_found_error("sheet", sheet_id)
    if obj.Attributes.GetUserString("sheet_name") in (None, ""):
        raise parameter_error("sheet_id", "id does not refer to a sheet (missing sheet_name user_text)")
    return obj


def _add_polyline(handle: Any, points: list[r3.Point3d], *, layer_index: int, name: str | None = None) -> str:
    poly = r3.Polyline()
    for p in points:
        poly.Add(p.X, p.Y, p.Z)
    pc = poly.ToPolylineCurve()
    attrs = r3.ObjectAttributes()
    attrs.LayerIndex = layer_index
    if name is not None:
        attrs.Name = name
    new_id: UUID = handle.file3dm.Objects.Add(pc, attrs)
    return handle.add_index(new_id)


def _ensure_sheet_layer(handle: Any, sheet_name: str) -> int:
    layer_name = f"Sheets::{sheet_name}"
    from rhino_mcp.tools._helpers import _resolve_layer_index

    return _resolve_layer_index(handle, layer_name)


def _draw_north_arrow(
    handle: Any,
    origin: r3.Point3d,
    size_mm: float,
    angle_deg: float,
    layer_index: int,
) -> list[str]:
    """Triangle pointing toward "north" + a 'N' label below."""
    a = math.radians(90.0 - angle_deg)  # clockwise from sheet +Y
    tip = r3.Point3d(origin.X + size_mm * math.cos(a), origin.Y + size_mm * math.sin(a), origin.Z)
    half = size_mm * 0.25
    side = math.radians(90.0 - angle_deg + 150.0)
    side2 = math.radians(90.0 - angle_deg - 150.0)
    bl = r3.Point3d(origin.X + half * math.cos(side), origin.Y + half * math.sin(side), origin.Z)
    br = r3.Point3d(origin.X + half * math.cos(side2), origin.Y + half * math.sin(side2), origin.Z)
    arrow = _add_polyline(handle, [tip, bl, origin, br, tip], layer_index=layer_index, name="north_arrow")
    label = r3.TextDot("N", r3.Point3d(origin.X, origin.Y - size_mm * 0.4, origin.Z))
    attrs = r3.ObjectAttributes()
    attrs.LayerIndex = layer_index
    attrs.Name = "north_arrow_label"
    new_id = handle.file3dm.Objects.Add(label, attrs)
    return [arrow, handle.add_index(new_id)]


def _draw_scale_bar(
    handle: Any,
    origin: r3.Point3d,
    total_length_mm: float,
    divisions: int,
    scale_denominator: int,
    layer_index: int,
) -> list[str]:
    h = max(2.0, total_length_mm * 0.05)
    seg = total_length_mm / max(divisions, 1)
    ids: list[str] = []
    for i in range(divisions):
        x0 = origin.X + i * seg
        x1 = origin.X + (i + 1) * seg
        rect = [
            r3.Point3d(x0, origin.Y, origin.Z),
            r3.Point3d(x1, origin.Y, origin.Z),
            r3.Point3d(x1, origin.Y + h, origin.Z),
            r3.Point3d(x0, origin.Y + h, origin.Z),
            r3.Point3d(x0, origin.Y, origin.Z),
        ]
        ids.append(_add_polyline(handle, rect, layer_index=layer_index, name=f"scale_bar_{i}"))
    label_pt = r3.Point3d(origin.X, origin.Y - h, origin.Z)
    real_meters = (total_length_mm / 1000.0) * scale_denominator
    td = r3.TextDot(f"0 .. {real_meters:.1f} m  (1:{scale_denominator})", label_pt)
    attrs = r3.ObjectAttributes()
    attrs.LayerIndex = layer_index
    attrs.Name = "scale_bar_label"
    new_id = handle.file3dm.Objects.Add(td, attrs)
    ids.append(handle.add_index(new_id))
    return ids


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Create Drawing Sheet", "readOnlyHint": False})
    def rhino_drawing_sheet_create(args: _SheetCreateIn) -> dict[str, Any]:
        """Create a sheet container — a rectangle on layer ``Sheets::<name>`` carrying user_text metadata.

        The rectangle's corners define the sheet bounds; user_text holds the
        sheet name, paper size (mm), and scale denominator so subsequent
        view-placement / title-block / export tools can re-derive it.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.drawing.sheet_create", args.model_dump())
        h = doc(args.doc_id)
        layer_index = _ensure_sheet_layer(h, args.name)
        origin = to_point(args.origin)
        corners = [
            r3.Point3d(origin.X, origin.Y, origin.Z),
            r3.Point3d(origin.X + args.width_mm, origin.Y, origin.Z),
            r3.Point3d(origin.X + args.width_mm, origin.Y + args.height_mm, origin.Z),
            r3.Point3d(origin.X, origin.Y + args.height_mm, origin.Z),
            r3.Point3d(origin.X, origin.Y, origin.Z),
        ]
        poly = r3.Polyline()
        for p in corners:
            poly.Add(p.X, p.Y, p.Z)
        pc = poly.ToPolylineCurve()
        attrs = r3.ObjectAttributes()
        attrs.LayerIndex = layer_index
        attrs.Name = f"sheet_{args.name}"
        attrs.SetUserString("sheet_name", args.name)
        attrs.SetUserString("sheet_width_mm", str(args.width_mm))
        attrs.SetUserString("sheet_height_mm", str(args.height_mm))
        attrs.SetUserString("sheet_scale", str(args.scale_denominator))
        attrs.SetUserString("sheet_origin", f"{origin.X},{origin.Y},{origin.Z}")
        new_id: UUID = h.file3dm.Objects.Add(pc, attrs)
        sid = h.add_index(new_id)
        return {
            "summary": {
                "sheet_id": sid,
                "name": args.name,
                "width_mm": args.width_mm,
                "height_mm": args.height_mm,
                "scale_denominator": args.scale_denominator,
                "layer": f"Sheets::{args.name}",
            },
            "text": f"Sheet '{args.name}' ({args.width_mm}x{args.height_mm} mm @1:{args.scale_denominator})",
        }

    @mcp.tool(annotations={"title": "Place Drawing View", "readOnlyHint": False})
    def rhino_drawing_view_place(args: _ViewPlaceIn) -> dict[str, Any]:
        """Project objects to a 2-D view (Make2D) and place the result on a sheet (bridge only)."""
        require_bridge_only("rhino_drawing_view_place")
        return bridge_call("rhino.drawing.view_place", args.model_dump())

    @mcp.tool(annotations={"title": "Drawing Section Cut", "readOnlyHint": False})
    def rhino_drawing_section_cut(args: _SectionCutIn) -> dict[str, Any]:
        """Cut a section through objects with a plane and place the trace on a sheet (bridge only)."""
        require_bridge_only("rhino_drawing_section_cut")
        return bridge_call("rhino.drawing.section_cut", args.model_dump())

    @mcp.tool(annotations={"title": "Add Title Block", "readOnlyHint": False})
    def rhino_drawing_title_block_add(args: _TitleBlockIn) -> dict[str, Any]:
        """Add the bottom-right title block, north arrow, and scale bar to a sheet."""
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.drawing.title_block_add", args.model_dump())
        h = doc(args.doc_id)
        sheet_obj = _find_sheet(h, args.sheet_id)
        sheet_name = sheet_obj.Attributes.GetUserString("sheet_name")
        try:
            width_mm = float(sheet_obj.Attributes.GetUserString("sheet_width_mm") or "0")
            height_mm = float(sheet_obj.Attributes.GetUserString("sheet_height_mm") or "0")
        except ValueError as exc:  # pragma: no cover - sheet metadata corruption
            raise parameter_error("sheet_id", "sheet metadata is corrupted") from exc
        origin_raw = sheet_obj.Attributes.GetUserString("sheet_origin") or "0,0,0"
        try:
            ox, oy, oz = (float(s) for s in origin_raw.split(","))
        except ValueError:
            ox, oy, oz = 0.0, 0.0, 0.0
        layer_index = _ensure_sheet_layer(h, sheet_name)

        ids: list[str] = []

        # Title block: lower-right rectangle 80 mm wide x 30 mm tall.
        tb_w, tb_h = min(120.0, width_mm * 0.4), min(45.0, height_mm * 0.18)
        tb_x = ox + width_mm - tb_w - 5.0
        tb_y = oy + 5.0
        tb_corners = [
            r3.Point3d(tb_x, tb_y, oz),
            r3.Point3d(tb_x + tb_w, tb_y, oz),
            r3.Point3d(tb_x + tb_w, tb_y + tb_h, oz),
            r3.Point3d(tb_x, tb_y + tb_h, oz),
            r3.Point3d(tb_x, tb_y, oz),
        ]
        ids.append(_add_polyline(h, tb_corners, layer_index=layer_index, name="title_block"))

        labels = [
            ("project", args.project, tb_x + 4.0, tb_y + tb_h - 6.0),
            ("title", args.title, tb_x + 4.0, tb_y + tb_h - 14.0),
            ("scale", args.scale_text, tb_x + 4.0, tb_y + 12.0),
            ("date", args.date_iso, tb_x + 4.0, tb_y + 4.0),
            ("drawn_by", args.drawn_by, tb_x + tb_w * 0.5, tb_y + 4.0),
            ("sheet_no", args.sheet_no, tb_x + tb_w - 30.0, tb_y + 4.0),
        ]
        for key, value, lx, ly in labels:
            if not value:
                continue
            td = r3.TextDot(f"{key}: {value}", r3.Point3d(lx, ly, oz))
            attrs = r3.ObjectAttributes()
            attrs.LayerIndex = layer_index
            attrs.Name = f"tb_{key}"
            new_id = h.file3dm.Objects.Add(td, attrs)
            ids.append(h.add_index(new_id))

        # North arrow: top-left, 20 mm.
        if args.add_north_arrow:
            na_origin = r3.Point3d(ox + 25.0, oy + height_mm - 25.0, oz)
            ids.extend(_draw_north_arrow(h, na_origin, 20.0, args.north_arrow_angle_deg, layer_index))

        # Scale bar: bottom-left.
        if args.add_scale_bar:
            sb_origin = r3.Point3d(ox + 10.0, oy + 10.0, oz)
            ids.extend(_draw_scale_bar(h, sb_origin, 50.0, 5, _safe_int(args.scale_text), layer_index))

        return {
            "summary": {
                "sheet_id": args.sheet_id,
                "object_ids": ids,
                "labels": [k for k, v, _, _ in labels if v],
            },
            "text": f"Title block added to '{sheet_name}' ({len(ids)} objects)",
        }

    @mcp.tool(annotations={"title": "Export Sheet to PDF", "readOnlyHint": False})
    def rhino_drawing_export_pdf(args: _ExportPdfIn) -> dict[str, Any]:
        """Export a sheet to PDF (bridge only)."""
        require_bridge_only("rhino_drawing_export_pdf")
        return bridge_call("rhino.drawing.export_pdf", args.model_dump())


def _safe_int(scale_text: str) -> int:
    """Parse "1:100" -> 100; fall back to 100 on any parse failure."""
    if ":" in scale_text:
        try:
            return int(scale_text.split(":", 1)[1])
        except ValueError:
            return 100
    try:
        return int(scale_text)
    except ValueError:
        return 100
