"""Grasshopper template loader (bridge only).

The template catalogue is described declaratively in
``src/rhino_mcp/data/gh_templates/manifest.json``. The Python side reads
that manifest so the LLM can list templates and check parameter contracts
without touching Rhino. Loading and binding actually run inside Rhino via
the bridge handler ``rhino.gh_templates.*``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, Field

from rhino_mcp.tools._helpers import bridge_call, require_bridge_only
from rhino_mcp.utils.error_handling import not_found_error, parameter_error
from rhino_mcp.utils.registry import Mode

_MANIFEST_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "gh_templates" / "manifest.json"


def _load_manifest() -> dict[str, Any]:
    if not _MANIFEST_PATH.exists():
        raise not_found_error("manifest", str(_MANIFEST_PATH))
    with _MANIFEST_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _template_dir() -> Path:
    return _MANIFEST_PATH.parent


class _TemplateListIn(BaseModel):
    pass


class _TemplateLoadIn(BaseModel):
    name: str = Field(..., description="Template name from gh_template_list (e.g. 'panel_grid').")
    canvas_target: str = Field(
        "active",
        description="'active' loads on the current canvas; 'new' creates a fresh canvas first.",
    )


class _BindParameterIn(BaseModel):
    template_id: str = Field(..., description="ID returned by gh_load_template.")
    parameter: str = Field(..., description="Parameter name as declared in the template manifest.")
    value: float | int | bool | str = Field(..., description="Value coerced to the parameter's declared type.")


class _RunTemplateIn(BaseModel):
    template_id: str = Field(..., description="ID returned by gh_load_template.")
    bake: bool = Field(True, description="Bake outputs into the active Rhino document after the solution settles.")
    layer: str = Field(
        "Templates",
        description="Bake target layer (created if absent).",
    )
    timeout_seconds: Annotated[float, Field(gt=0, le=600)] = Field(
        30.0, description="Maximum solution wait."
    )


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    # List tool is mode-independent — it reads the manifest off disk so even
    # standalone clients can discover the catalogue and parameter contract.
    @mcp.tool(annotations={"title": "GH Template: List", "readOnlyHint": True})
    def gh_template_list(args: _TemplateListIn) -> dict[str, Any]:
        """List bundled Grasshopper templates with their parameter contracts.

        ``available=False`` means the .gh binary has not been shipped yet —
        the contract is described in the manifest but loading it will fail
        until the binary is placed alongside the manifest.
        """
        manifest = _load_manifest()
        tpl_dir = _template_dir()
        items: list[dict[str, Any]] = []
        for name, spec in manifest.get("templates", {}).items():
            file_name = spec.get("file", f"{name}.gh")
            available = (tpl_dir / file_name).exists()
            items.append({
                "name": name,
                "description": spec.get("description", ""),
                "parameters": spec.get("parameters", {}),
                "outputs": spec.get("outputs", []),
                "use_case": spec.get("use_case", ""),
                "file": file_name,
                "available": available,
            })
        return {
            "summary": {"count": len(items), "templates": items},
            "text": f"{len(items)} template(s); "
            f"{sum(1 for t in items if t['available'])} have binaries.",
        }

    if mode is Mode.STANDALONE:
        return  # bridge-only template ops below

    @mcp.tool(annotations={"title": "GH Template: Load", "readOnlyHint": False})
    def gh_load_template(args: _TemplateLoadIn) -> dict[str, Any]:
        """Open a bundled template on the canvas and return its template_id + parameter map."""
        require_bridge_only("gh_load_template")
        manifest = _load_manifest()
        templates = manifest.get("templates", {})
        if args.name not in templates:
            allowed = ", ".join(sorted(templates.keys()))
            raise parameter_error("name", f"unknown template '{args.name}'", allowed=allowed)
        spec = templates[args.name]
        tpl_path = _template_dir() / spec.get("file", f"{args.name}.gh")
        if not tpl_path.exists():
            raise not_found_error("template binary", str(tpl_path))
        return bridge_call(
            "rhino.gh_templates.load",
            {
                "name": args.name,
                "path": str(tpl_path),
                "canvas_target": args.canvas_target,
                "manifest_parameters": spec.get("parameters", {}),
            },
        )

    @mcp.tool(annotations={"title": "GH Template: Bind Parameter", "readOnlyHint": False})
    def gh_bind_template_parameter(args: _BindParameterIn) -> dict[str, Any]:
        """Set a single named parameter on a loaded template (slider / panel / toggle)."""
        require_bridge_only("gh_bind_template_parameter")
        return bridge_call("rhino.gh_templates.bind_parameter", args.model_dump())

    @mcp.tool(annotations={"title": "GH Template: Run", "readOnlyHint": False})
    def gh_run_template(args: _RunTemplateIn) -> dict[str, Any]:
        """Force a fresh solution and (optionally) bake the declared outputs."""
        require_bridge_only("gh_run_template")
        return bridge_call("rhino.gh_templates.run", args.model_dump())
