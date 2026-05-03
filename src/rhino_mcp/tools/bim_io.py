"""BIM interchange tools — IFC and gbXML import / export.

These tools are bridge-only because the conversion pipelines live inside
Rhino 8's RhinoCommon (IFC plug-in / gbXML add-in). The Python layer
forwards the JSON-RPC call and surfaces a structured result.

Tool catalogue:
- rhino_export_ifc / rhino_import_ifc — IFC2x3 / IFC4 round-trip.
- rhino_export_gbxml — gbXML for energy / thermal interchange.
- rhino_bim_metadata_set — write IFC entity attributes onto Rhino
  objects via user_text (works in both modes; bridge mode also
  pushes the same data into the IFC export pipeline).

The standalone build silently falls through to ``unsupported_in_standalone``
for the conversion tools but supports ``rhino_bim_metadata_set`` so an
LLM can still tag objects ahead of a bridge round-trip.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from rhino_mcp.tools._helpers import bridge_call, doc, require_bridge_only
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import not_found_error, parameter_error
from rhino_mcp.utils.registry import Mode

_IFC_SCHEMAS = ("IFC2x3", "IFC4", "IFC4x3")
_DEFAULT_ENTITY_MAP = {
    "wall": "IfcWallStandardCase",
    "floor": "IfcSlab",
    "slab": "IfcSlab",
    "roof": "IfcRoof",
    "column": "IfcColumn",
    "beam": "IfcBeam",
    "door": "IfcDoor",
    "window": "IfcWindow",
    "stair": "IfcStair",
    "railing": "IfcRailing",
    "furniture": "IfcFurnishingElement",
}


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )


class _ExportIfcIn(_DocArg):
    path: str = Field(..., description="Absolute output IFC path (.ifc).")
    schema_version: str = Field(
        "IFC4",
        description="IFC schema. Allowed: IFC2x3 / IFC4 / IFC4x3.",
    )
    object_ids: list[str] | None = Field(
        None,
        description="If set, only these objects are exported. Default: all visible objects.",
    )
    entity_type_map: dict[str, str] | None = Field(
        None,
        description=(
            "Override the default function -> IfcEntity map. Keys are user_text "
            "'function' values; values are IFC entity names. Defaults cover wall, "
            "floor, roof, column, beam, door, window, stair, railing, furniture."
        ),
    )
    project_name: str = Field(
        "rhino-mcp export",
        description="IFC project name written to IfcProject.Name.",
    )


class _ImportIfcIn(_DocArg):
    path: str = Field(..., description="IFC file to import (.ifc).")
    filter_by_type: list[str] | None = Field(
        None,
        description="Optional whitelist of IFC entity names (e.g. ['IfcWall', 'IfcSlab']).",
    )
    target_layer_root: str = Field(
        "BIM",
        description="Top-level layer; imported objects are nested under <root>::<IfcType>.",
    )


class _ExportGbXmlIn(_DocArg):
    path: str = Field(..., description="Absolute output gbXML path (.xml).")
    object_ids: list[str] | None = Field(None)
    zone_user_text_key: str | None = Field(
        None,
        description="user_text key whose value names the gbXML zone. Default: 'zone'.",
    )


class _BimMetadataIn(_DocArg):
    object_ids: list[str] = Field(..., min_length=1)
    entity_type: str = Field(
        ..., description="IFC entity name (e.g. 'IfcWallStandardCase')."
    )
    properties: dict[str, str] = Field(
        default_factory=dict,
        description="IFC PropertySet payload — key/value strings written as user_text.",
    )
    pset_name: str = Field(
        "Pset_RhinoMcp",
        description="Property set name. IFC viewers group properties by this name.",
    )


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Export IFC", "readOnlyHint": False})
    def rhino_export_ifc(args: _ExportIfcIn) -> dict[str, Any]:
        """Export the active document (or a subset) to IFC2x3 / IFC4 / IFC4x3 (bridge only)."""
        require_bridge_only("rhino_export_ifc")
        if args.schema_version not in _IFC_SCHEMAS:
            raise parameter_error(
                "schema_version",
                f"unknown IFC schema '{args.schema_version}'",
                allowed=", ".join(_IFC_SCHEMAS),
            )
        payload = args.model_dump()
        if not args.entity_type_map:
            payload["entity_type_map"] = _DEFAULT_ENTITY_MAP
        return bridge_call("rhino.bim.export_ifc", payload)

    @mcp.tool(annotations={"title": "Import IFC", "readOnlyHint": False})
    def rhino_import_ifc(args: _ImportIfcIn) -> dict[str, Any]:
        """Import an IFC file, mapping each entity to a layer under ``target_layer_root`` (bridge only)."""
        require_bridge_only("rhino_import_ifc")
        return bridge_call("rhino.bim.import_ifc", args.model_dump())

    @mcp.tool(annotations={"title": "Export gbXML", "readOnlyHint": False})
    def rhino_export_gbxml(args: _ExportGbXmlIn) -> dict[str, Any]:
        """Export thermal / structural BIM payload to gbXML (bridge only)."""
        require_bridge_only("rhino_export_gbxml")
        return bridge_call("rhino.bim.export_gbxml", args.model_dump())

    @mcp.tool(annotations={"title": "Set BIM Metadata", "readOnlyHint": False})
    def rhino_bim_metadata_set(args: _BimMetadataIn) -> dict[str, Any]:
        """Tag objects with IFC entity + property-set metadata.

        Standalone writes ``Pset_RhinoMcp::<key>`` user_text on each object;
        bridge mode does the same and additionally pushes into Rhino's IFC
        property-set table so a subsequent IFC export carries them across.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.bim.metadata_set", args.model_dump())
        h = doc(args.doc_id)
        applied: list[str] = []
        for oid in args.object_ids:
            obj = h.file3dm.Objects.FindId(oid)
            if obj is None:
                raise not_found_error("object", oid)
            obj.Attributes.SetUserString("ifc_entity", args.entity_type)
            obj.Attributes.SetUserString("ifc_pset", args.pset_name)
            for k, v in args.properties.items():
                obj.Attributes.SetUserString(f"{args.pset_name}::{k}", v)
            applied.append(oid)
        return {
            "summary": {
                "object_ids": applied,
                "entity_type": args.entity_type,
                "pset_name": args.pset_name,
                "property_count": len(args.properties),
            },
            "text": f"Tagged {len(applied)} object(s) as {args.entity_type}",
        }
