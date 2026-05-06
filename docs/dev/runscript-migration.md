# RunScript Migration Matrix

The bridge plugin still routes a number of operations through `RhinoApp.RunScript(...)` because either (a) the equivalent RhinoCommon API was removed in Rhino 8 (`FilePdf.AddPage`), (b) the API exposes only a fraction of the UI command's options, or (c) the operation depends on modal user interaction.

After v0.4.2 every site is wrapped in `HandlerBase.SafeRunScript(...)`, which traces the script line (gated by `RHINO_MCP_TRACE_RUNSCRIPT=1`) and issues `_Escape` if the call throws — so a partial token like `_Width=` can no longer leak to Rhino's command line.

This document tracks the **post-wrapper** roadmap: which sites should be migrated to direct RhinoCommon calls, which should stay on RunScript, and what the priority is.

## Legend

- **Replace** — direct RhinoCommon API exists and is preferred. File a
  follow-up task.
- **Keep** — RunScript is the only viable path (Rhino 8 API removed or
  too narrow). SafeRunScript + arg validation is the long-term answer.
- **Investigate** — likely replaceable but the API surface needs a quick
  spike before committing.

| Handler | Method | Current script | Recommendation | Priority | Notes |
|---|---|---|---|---|---|
| `IOHandler` | `Open` | `_-Open "{path}"` | Replace | P1 | `RhinoDoc.OpenFile(path)` |
| `IOHandler` | `Save` | `_-Save` / `_-SaveAs "{path}"` | Replace | P1 | `Doc.WriteFile(path, options)` |
| `IOHandler` | `Import` | `_-Import "{path}" _Enter` | Replace | P1 | `Doc.Import(path, options)` (if signature stable in 8.x) |
| `IOHandler` | `Export*` (STEP/IGES/OBJ/STL/DXF) | `_-Export "{path}" _Enter` | Replace | P1 | `Doc.WriteFile` per format. UI options surface only by RunScript. |
| `IOHandler` | `Screenshot` | `_-ViewCaptureToFile "{path}" _Width=… _Height=… _Enter` | Replace | **P0** | `new Rhino.Display.ViewCapture { Width=w, Height=h }.CaptureToBitmap(view)` then `bmp.Save(path)`. Removes the most failure-prone RunScript line. |
| `IOHandler` | `BlockCreate` | `_Block` (modal!) | Investigate | P3 | `_Block` is interactive. Probably keep RunScript and warn the LLM. |
| `IOHandler` | `BlockInsert` | `_-Insert "{name}" _Enter` | Replace | P2 | `Doc.Objects.AddInstanceObject(definitionIndex, transform)` |
| `SurfaceMatchHandler` | `MatchSrf` etc. | `_-MatchSrf _SelId {srcId} …` | Investigate | P2 | RhinoCommon has `Brep.CreateMatchSurface` family but option coverage is narrower. |
| `SurfaceHandler` | `BlendSurface` | `_-BlendSrf …` | Investigate | P2 | `Brep.CreateBlendSurface` exists; verify options. |
| `SurfaceHandler` | `FilletSurface` | `_-FilletSrf …` | Investigate | P2 | `Brep.CreateFilletSurface` |
| `TransformHandler` | `Flow` | `_-Flow _SelId {first()} …` | Keep | P3 | No direct RhinoCommon equivalent. Validation already added. |
| `TransformHandler` | `CageEdit` | `_-CageEdit …` | Keep | P3 | UI-driven workflow. |
| `ExtractionHandler` | `Make2D` | `_-Make2D …` | Replace | P2 | `HiddenLineDrawing.Compute(parameters)` |
| `DrawingHandler` | `ExportPdf` | `_-Print _Setup _Destination _PDF …` | **Keep** | — | `FilePdf.AddPage` was removed in Rhino 8.x (see `.claude/rules/csharp-handler.md`). RunScript is the supported path. |
| `DisplayHandler` | `NamedViewSave` | `_-NamedView _Save "{name}" _Enter` | Replace | P3 | `Doc.NamedViews.Add(name, viewport)` |
| `DisplayHandler` | `Turntable` | `_-Turntable _FrameCount=… _OutputFile=…` | Keep | P3 | Plugin-provided command, no RhinoCommon API. |
| `DisplayHandler` | `RenderToFile` | `_-Render` + `_-SaveRenderWindowAs` | Investigate | P3 | `Render.RenderPipeline` is non-trivial. |
| `RenderHandler` | `SetRenderEngine` | `_-SetCurrentRenderPlugIn "{engine}"` | Replace | P3 | `RenderSettings` accessor in RhinoCommon. |
| `RenderHandler` | `SaveRenderWindowAs` | RunScript chain | Investigate | P3 | Same as DisplayHandler.RenderToFile. |
| `LayerHandler` | `SetEnvironment` | `_-Environment _SetActive _File "{hdri}" _Enter` | Replace | P3 | `Doc.RenderSettings.CurrentEnvironment` in 8.x |
| `BimIoHandler` | `Export*` / `Import*` | `_-Export "{path}"` / `_-Import "{path}"` | Replace | P2 | Same as `IOHandler.Export*`. |
| `GrasshopperHandler` | `ClusterCreate` / `ClusterExpand` | `_GrasshopperCluster*` (modal) | Keep | — | UI commands; no scripting API. |
| `AnalysisHandler` | `DraftAngleAnalysis` etc. | `_DraftAngleAnalysis` etc. (modal) | Keep | — | These are display-mode toggles; behaviour is bound to UI. |
| `AnnotationHandler` | `DimLinear` etc. | `_DimLinear` etc. (modal) | Keep | — | Pure modal commands; replacement would be `Doc.Objects.AddDimension(...)` per shape — file separate task. |

## Priority guide

- **P0** — directly tied to user-visible incidents. Migrate first.
- **P1** — high call volume, cleanly replaceable. Schedule next minor.
- **P2** — replaceable but with non-trivial API exploration.
- **P3** — low-value or interactive command; SafeRunScript wrapper is good enough.

## Next steps

1. Open a follow-up plan for the P0 row (`IOHandler.Screenshot` → `ViewCapture`).
2. Use `csharp-rhinocommon-checker` agent on every P1/P2 spike — Rhino 8.x
   minor releases drift the API enough that signatures must be re-verified
   per Rhino update.
3. After each migration, drop the row from the table and add a CHANGELOG
   entry that mentions the new behaviour (especially error surface
   changes — RhinoCommon throws structured exceptions, RunScript silently
   fails into the command line).
