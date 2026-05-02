"""Batch modification tools.

Bridge-only — apply multiple attribute/transform changes to many objects
in a single call, wrapped in one undo record.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from rhino_mcp.models.geometry_types import Point3dModel, Vector3dModel
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import unsupported_in_standalone
from rhino_mcp.utils.registry import Mode


class _ModifySpec(BaseModel):
    """Specification for modifying a single object."""

    id: str = Field(..., description="Object GUID.")
    translation: Vector3dModel | None = Field(None, description="Translation vector.")
    rotation_axis: Vector3dModel | None = Field(None, description="Rotation axis direction.")
    rotation_center: Point3dModel | None = Field(None, description="Rotation centre point.")
    rotation_angle_degrees: float | None = Field(None, description="Rotation angle in degrees.")
    scale_factor: float | None = Field(None, ge=0.001, le=10000, description="Uniform scale factor.")
    scale_center: Point3dModel | None = Field(None, description="Scale centre point.")
    color: tuple[int, int, int] | None = Field(None, description="RGB colour (0-255).")
    layer: str | None = Field(None, description="Target layer name.")
    visible: bool | None = Field(None, description="Object visibility.")
    name: str | None = Field(None, description="Object name.")


class _BatchModifyIn(BaseModel):
    objects: list[_ModifySpec] = Field(..., min_length=1, max_length=10000)
    apply_to_all: bool = Field(
        False,
        description=(
            "When True, use the first spec's modifications for ALL objects "
            "in the document (ignores 'id' in specs)."
        ),
    )


def register(mcp: Any, mode: str) -> None:
    @mcp.tool(annotations={"title": "Batch Modify Objects"})
    def rhino_batch_modify(args: _BatchModifyIn) -> dict[str, Any]:
        """Modify many objects in a single call.

        Each spec can include any combination of: translation, rotation,
        scale, colour, layer, visibility, and name.  All changes are wrapped
        in one undo record — ``rhino_undo(steps=1)`` reverts the entire batch.

        When ``apply_to_all`` is ``True``, the modifications from the first
        spec are applied to every object in the document.
        """
        if runtime().mode is Mode.STANDALONE:
            raise unsupported_in_standalone("rhino_batch_modify")

        payload = {
            "objects": [spec.model_dump(exclude_none=True) for spec in args.objects],
            "apply_to_all": args.apply_to_all,
        }
        result = runtime().require_bridge().call("rhino.batch.modify", payload)

        ok = result.get("success_count", 0)
        fail = result.get("failure_count", 0)
        total = result.get("total", len(args.objects))
        errors = result.get("errors", [])

        if fail == 0:
            text = f"Modified {ok} object(s)."
        elif ok == 0:
            detail = "; ".join(f"{e['id']}: {e['error']}" for e in errors[:5])
            text = f"All {fail} modifications failed. {detail}"
        else:
            detail = "; ".join(f"{e['id']}: {e['error']}" for e in errors[:5])
            text = f"Modified {ok}/{total}. {fail} failed: {detail}"

        return {
            "summary": {
                "success_count": ok,
                "failure_count": fail,
                "total": total,
            },
            "text": text,
        }
