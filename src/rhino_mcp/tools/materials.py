"""Material creation/assignment, physical presets, environment HDRI, plus render-viewport (bridge-only)."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Annotated, Any

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.models.geometry_types import ColorRGBA
from rhino_mcp.tools._helpers import (
    MAX_OBJECT_IDS,
    bridge_call,
    doc,
    find_material_index,
    require_bridge_only,
)
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import (
    not_found_error,
    parameter_error,
    unsupported_in_standalone,
)
from rhino_mcp.utils.registry import Mode

_PRESET_CACHE: dict[str, Any] | None = None


def _load_presets() -> dict[str, Any]:
    """Load and cache the material-preset catalogue shipped under ``data/``."""
    global _PRESET_CACHE
    if _PRESET_CACHE is None:
        raw = files("rhino_mcp.data").joinpath("material_presets.json").read_text(encoding="utf-8")
        _PRESET_CACHE = json.loads(raw)
    return _PRESET_CACHE


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )


class _MaterialCreateIn(_DocArg):
    name: str = Field(..., min_length=1)
    diffuse: ColorRGBA = Field(default_factory=ColorRGBA)
    transparency: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    glossiness: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0


class _MaterialAssignIn(_DocArg):
    material_name: str
    object_ids: list[str] = Field(..., min_length=1, max_length=MAX_OBJECT_IDS)


class _RenderIn(_DocArg):
    width: Annotated[int, Field(ge=64, le=8192)] = 1280
    height: Annotated[int, Field(ge=64, le=8192)] = 720
    output_path: str


class _PresetListIn(BaseModel):
    category: str | None = Field(
        None,
        description="If set, only presets in this category are returned (stone, metal, glass, wood, plaster, fabric, polymer, landscape).",
    )


class _PresetCreateIn(_DocArg):
    preset_name: str = Field(
        ..., description="Preset key from rhino_material_preset_list (e.g. 'glass_low_e')."
    )
    material_name: str | None = Field(
        None,
        description="Override the document-side material name. Defaults to the preset key.",
    )


class _EnvironmentSetIn(_DocArg):
    hdri_path: str = Field(
        ...,
        description="Absolute path to an HDRI / EXR file used as the scene environment.",
    )
    rotation_deg: float = Field(0.0, description="Rotation around world Z (degrees).")
    background_strength: Annotated[float, Field(ge=0.0, le=10.0)] = 1.0
    use_for_lighting: bool = Field(True)
    use_for_background: bool = Field(True)


def _find_material(handle, name: str) -> int:
    idx = find_material_index(handle, name)
    if idx is None:
        raise not_found_error("material", name)
    return idx


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Create Material", "readOnlyHint": False})
    def rhino_material_create(args: _MaterialCreateIn) -> dict[str, Any]:
        """Create a material with diffuse colour, transparency, and glossiness."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.material.create", args.model_dump())
        h = doc(args.doc_id)
        m = r3.Material()
        m.Name = args.name
        m.DiffuseColor = (args.diffuse.r, args.diffuse.g, args.diffuse.b, args.diffuse.a)
        m.Transparency = args.transparency
        m.Shine = args.glossiness * 255  # rhino3dm uses 0..255
        idx = h.file3dm.Materials.Add(m)
        return {
            "summary": {"name": args.name, "index": idx, "doc_id": h.doc_id},
            "text": f"Created material '{args.name}' (index {idx})",
        }

    @mcp.tool(annotations={"title": "Assign Material", "readOnlyHint": False})
    def rhino_material_assign(args: _MaterialAssignIn) -> dict[str, Any]:
        """Assign an existing material to one or more objects."""
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.material.assign", args.model_dump())
        h = doc(args.doc_id)
        idx = _find_material(h, args.material_name)
        updated: list[str] = []
        for gid in args.object_ids:
            obj = h.find_object(gid)
            attrs = obj.Attributes
            attrs.MaterialIndex = idx
            attrs.MaterialSource = r3.ObjectMaterialSource.MaterialFromObject
            geom = obj.Geometry
            h.file3dm.Objects.Delete(obj.Attributes.Id)
            new_id = h.file3dm.Objects.Add(geom, attrs)
            updated.append(h.add_index(new_id))
        return {
            "summary": {"material": args.material_name, "object_ids": updated},
            "text": f"Assigned '{args.material_name}' to {len(updated)} object(s)",
        }

    @mcp.tool(annotations={"title": "List Material Presets", "readOnlyHint": True, "idempotentHint": True})
    def rhino_material_preset_list(args: _PresetListIn) -> dict[str, Any]:
        """List physical-material presets bundled with rhino-mcp.

        Returns the full catalogue (or a single category subset) so the LLM
        can pick a known-good name before calling ``rhino_material_preset_create``.
        """
        catalogue = _load_presets()
        rows: list[dict[str, Any]] = []
        for key, spec in catalogue["presets"].items():
            if args.category and spec.get("category") != args.category:
                continue
            rows.append({"name": key, **spec})
        return {
            "summary": {
                "presets": rows,
                "count": len(rows),
                "version": catalogue.get("version", 1),
            },
            "text": f"{len(rows)} material preset(s)",
        }

    @mcp.tool(annotations={"title": "Create Material From Preset", "readOnlyHint": False})
    def rhino_material_preset_create(args: _PresetCreateIn) -> dict[str, Any]:
        """Create a document material from a bundled physical preset.

        Standalone uses rhino3dm's basic Material (diffuse / transparency /
        shine). Bridge mode also pushes the matching Rhino PBR render
        content + IOR for photoreal output.
        """
        catalogue = _load_presets()
        spec = catalogue["presets"].get(args.preset_name)
        if spec is None:
            raise parameter_error(
                "preset_name",
                f"unknown preset '{args.preset_name}'",
                allowed=", ".join(sorted(catalogue["presets"].keys())),
            )
        material_name = args.material_name or args.preset_name
        if runtime().mode is Mode.BRIDGE:
            payload = args.model_dump()
            payload["material_name"] = material_name
            payload["spec"] = spec
            return bridge_call("rhino.material.preset_create", payload)
        h = doc(args.doc_id)
        m = r3.Material()
        m.Name = material_name
        r_, g_, b_ = spec["diffuse"][:3]
        m.DiffuseColor = (r_, g_, b_, 255)
        m.Transparency = float(spec.get("transparency", 0.0))
        m.Shine = int(float(spec.get("glossiness", 0.0)) * 255)
        idx = h.file3dm.Materials.Add(m)
        return {
            "summary": {
                "name": material_name,
                "preset": args.preset_name,
                "category": spec.get("category"),
                "index": idx,
                "diffuse": spec["diffuse"],
                "transparency": spec.get("transparency"),
                "glossiness": spec.get("glossiness"),
            },
            "text": f"Created material '{material_name}' from preset '{args.preset_name}'",
        }

    if mode is Mode.STANDALONE:
        return  # bridge-only render + environment tools below

    @mcp.tool(annotations={"title": "Render Viewport", "readOnlyHint": False})
    def rhino_render_viewport(args: _RenderIn) -> dict[str, Any]:
        """Render the active viewport to an image file (bridge required)."""
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_render_viewport")
        return runtime().require_bridge().call("rhino.render.viewport", args.model_dump())

    @mcp.tool(annotations={"title": "Set HDRI Environment", "readOnlyHint": False})
    def rhino_environment_set(args: _EnvironmentSetIn) -> dict[str, Any]:
        """Attach an HDRI/EXR environment used for lighting + background (bridge only)."""
        require_bridge_only("rhino_environment_set")
        return bridge_call("rhino.material.environment_set", args.model_dump())
