# Grasshopper guide

All Grasshopper tools are bridge-only. They forward JSON-RPC requests to the `RhinoMCPBridge.rhp` C# plugin loaded inside Rhino 8 with Grasshopper open.

## Prerequisites

1. Rhino 8 running.
2. Grasshopper window open at least once (the canvas DocumentServer is initialised lazily).
3. `RhinoMCPBridge.rhp` loaded in Rhino's Plugin Manager (`dotnet build rhino_plugin/csharp -c Release` then drag-drop the `.rhp`).
4. `rhino-mcp` running with `RHINO_MCP_FORCE_MODE=bridge`.

## Canvas lifecycle

```text
gh_open_file  → load .gh / .ghx
gh_new_canvas → start a fresh document
gh_save_file  → write current canvas
gh_reset      → clear cached solution
gh_run        → recompute (force a fresh solution by default)
```

## Adding components

Component names are matched against Grasshopper's nickname dictionary (case-insensitive). If a name is ambiguous, prefix with the plug-in: `"Pufferfish.TweenCurves"`.

```jsonc
gh_add_component { "name": "Number Slider", "x": -100, "y": 0 }
gh_add_component { "name": "Move",          "x":  100, "y": 0 }
```

The bridge returns the new component's GUID. Use that GUID to wire it:

```jsonc
gh_connect_components {
  "from_component": "<slider_id>",  "from_output": 0,
  "to_component":   "<move_id>",    "to_input":   "T"
}
```

Outputs and inputs accept either a zero-based index or the parameter nickname.

## Driving inputs

| Widget          | Tool                  | Notes |
|-----------------|-----------------------|-------|
| Number Slider   | `gh_set_slider`       | numeric value clamped to slider range |
| Panel           | `gh_set_panel`        | multi-line text supported |
| Boolean Toggle  | `gh_set_toggle`       | `true` / `false` |
| Generic param   | `gh_set_parameter`    | uses `GhParameterValue` discriminator |

`GhParameterValue.type` ∈ `{number, integer, boolean, text, point, vector, plane, geometry_json}`. For `geometry_json`, pass the rhino3dm `Encode()` JSON of the geometry; the bridge `Decode`s it on the Rhino side.

## Reading outputs

```jsonc
gh_get_parameter { "component_id": "<id>", "output": "Result" }
```

Returns either a single value or a flattened list. Use `gh_data_tree_get` when branch structure matters:

```jsonc
gh_data_tree_get { "component_id": "<id>", "output": 0 }
// → {"branches": [{"path": [0,0], "values": [...]}, ...]}
```

`gh_data_tree_set` accepts the symmetric structure:

```jsonc
gh_data_tree_set {
  "component_id": "<id>", "input": 0,
  "branches": [
    [{"indices":[0,0]}, [{"type":"number","value":1.5}, {"type":"number","value":3.0}]],
    [{"indices":[0,1]}, [{"type":"number","value":2.5}]]
  ]
}
```

## Baking

```jsonc
gh_bake_to_rhino { "component_ids": ["<id1>", "<id2>"], "layer": "Bake/Output" }
```

Returns the GUIDs of the newly added Rhino objects.

## Example session (with Claude)

```
You:  Open /work/wing.gh and run it.
Claude: gh_open_file → gh_run

You:  Sweep the 'span' slider from 8 to 16 in 9 steps and bake each result into a new layer.
Claude:
   for s in [8, 9, ..., 16]:
       gh_set_slider {component_id: "<span>", value: s}
       gh_run        {new_solution: true}
       gh_bake_to_rhino {component_ids: ["<output>"], layer: f"Bake/{s}"}
```

## Troubleshooting

| Symptom                                      | Fix |
|----------------------------------------------|-----|
| `gh_component_missing`                       | Component name not matched; install the plug-in or use `gh_component_list` to find an alternative. |
| `No active Grasshopper document.`            | Open the Grasshopper editor at least once before issuing tool calls. |
| Slider value clamps unexpectedly             | The slider's domain is set on the canvas; either widen it via the bridge (planned) or adjust on the canvas. |
| Bake produces zero objects                   | The component output is empty for the current solution; run `gh_run` first and confirm with `gh_get_parameter`. |
