# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-05-03

### Added — modeling experience upgrade

- **Composition tools** (`tools/composition.py`, both modes) — one-shot
  multi-object placement so the LLM doesn't have to drive a transform
  loop call-by-call:
  - `rhino_place_grid` — count_x × count_y grid, optional `skip_origin`
    and `name_prefix`.
  - `rhino_stack_floors` — stack copies vertically (architectural
    storey replication).
  - `rhino_scatter` — scatter inside a 2-D AABB with deterministic
    `seed` and optional Z-rotation jitter.
  - `rhino_replicate_along_curve` — distribute copies along a curve at
    evenly spaced parameters, optional tangent alignment.
- **Document hygiene tools** (`tools/document_config.py`, both modes) —
  surface units / tolerances / base point as first-class queryable
  state instead of silent footguns:
  - `rhino_document_units_get` / `rhino_document_units_set`
    (with `scale_existing` flag).
  - `rhino_tolerance_get` / `rhino_tolerance_set`.
  - `rhino_origin_set` (`reference` / `translate` modes).
  - `rhino_document_settings` — bundled summary in one call.
  - `rhino_document_summary` extended with `units`, `tolerances`,
    `base_point`, `layer_tree_depth`.
- **Geometry validation tools** (`tools/geometry_validation.py`) —
  surface topology issues that silently break booleans, exports, and
  fabrication:
  - `rhino_validate_brep` — closed/solid/manifold flags, edge/face
    counts, structured `issues` payload.
  - `rhino_check_naked_edges` (bridge only) — enumerate naked edges
    with index + length.
  - `rhino_report_mesh_health` — closed/manifold/vertex/face report.
  - `rhino_curve_continuity` — span count, planarity, periodic, log.
- **Grasshopper template loader** (`tools/grasshopper/templates.py`):
  - `gh_template_list` (both modes) — manifest-driven catalogue with
    parameter contracts; reports `available` per binary.
  - `gh_load_template` / `gh_bind_template_parameter` /
    `gh_run_template` (bridge only).
  - `src/rhino_mcp/data/gh_templates/manifest.json` ships 4 declared
    templates: `panel_grid`, `morph_to_surface`, `offset_facade`,
    `field_scatter`. Binaries are populated separately (see the
    `README.md` in that folder).
- **3 new strategy prompts** in `prompts/strategy.py`:
  - `parametric_workflow` — iterative slider sweeps + comparable
    variants + validation per variant.
  - `bim_authoring_workflow` — layer tree, grouping, and `user_text`
    metadata conventions for architectural authoring.
  - `design_dialogue_workflow` — multi-turn design checkpoints with
    user-in-the-loop confirmation.
- **3 new examples**:
  - `examples/architectural_massing.py` — site grid + stacked floors +
    BIM metadata + validation (standalone).
  - `examples/iterative_design_exploration.py` — GH template + slider
    sweep + screenshot comparison (bridge only).
  - `examples/validation_workflow.py` — pre-flight Brep / Curve / Mesh
    health check (both modes).
- **Free-form architecture toolkit** — purpose-built for
  doubly-curved / non-rectilinear architectural design:
  - `tools/freeform/skin.py` — `rhino_skin_from_sections` (chain ruled
    surfaces between ordered sections in standalone, true Brep loft on
    bridge), `rhino_section_at_axis` (UV iso-curves both modes; world
    X/Y/Z plane slicing on bridge), `rhino_axis_ribs` (bridge) for
    waffle fabrication.
  - `tools/freeform/paneling.py` — `rhino_uv_grid_panels` (mesh /
    curves / corners output), `rhino_panel_planarity` (per-cell best-
    fit-plane deviation with stats), `rhino_panel_curvature_classify`
    (planar / single_curved_u / single_curved_v / synclastic /
    anticlastic via 4-corner normal heuristic in standalone, true
    Gaussian via `Surface.CurvatureAt` on bridge).
  - `tools/freeform/curvature.py` — `rhino_surface_normal_at`,
    `rhino_surface_developable_score` (0 ≈ developable, 1 ≈ fully
    doubly-curved), and `rhino_surface_curvature_at` (bridge — true
    Gaussian / mean / principal k₁ k₂ + directions).
  - `tools/freeform/fields.py` — `rhino_attractor_displace_points`
    (linear / inverse / gaussian falloff; point or curve attractor),
    `rhino_smooth_polyline` (Laplacian smoothing with optional
    endpoint pinning).
- **4 new strategy prompts** in `prompts/strategy.py`:
  - `parametric_workflow` — iterative slider sweeps + comparable
    variants + validation per variant.
  - `bim_authoring_workflow` — layer tree, grouping, and `user_text`
    metadata conventions for architectural authoring.
  - `design_dialogue_workflow` — multi-turn design checkpoints with
    user-in-the-loop confirmation.
  - `freeform_workflow` — 6-step guide for non-rectilinear authoring:
    shape → curvature check → panelise → refine → fabricate → report.
- **4 new examples**:
  - `examples/architectural_massing.py` — site grid + stacked floors +
    BIM metadata + validation (standalone).
  - `examples/iterative_design_exploration.py` — GH template + slider
    sweep + screenshot comparison (bridge only).
  - `examples/validation_workflow.py` — pre-flight Brep / Curve / Mesh
    health check (both modes).
  - `examples/freeform_canopy.py` — varying-radius arc sections →
    multi-segment skin → per-segment panelisation + classification →
    aggregate panel report (standalone).
- **C# bridge handlers** (`rhino_plugin/csharp/Handlers/`):
  - `CompositionHandler` (4 methods).
  - `DocumentConfigHandler` (6 methods, base point persisted via
    document strings since RhinoCommon does not expose
    `ModelBasePoint` uniformly across Rhino 8 builds).
  - `ValidationHandler` (4 methods, with naked-edge enumeration).
  - `GhTemplatesHandler` (3 methods, name-based parameter binding).
  - `FreeformHandler` (12 methods — true Gaussian curvature, Brep /
    mesh plane slicing, RhinoCommon `Brep.CreateFromLoft`).
  - `CommandDispatcher.cs` adds 28 new `Register(...)` entries.

### Changed

- `pyproject.toml` version bumped to `0.2.0`; `__init__.py` mirrors.
- Hatch wheel `artifacts` extended to ship
  `src/rhino_mcp/data/gh_templates/*.json|*.gh|*.md`.
- `register(mcp, mode)` on `tools/grasshopper/templates.py` registers
  `gh_template_list` in both modes and the loader / bind / run trio
  only when the bridge is reachable, so standalone clients can still
  discover the catalogue.
- `_register_prompts` now exports 7 prompts (was 3 in v0.1).

### Fixed (uncovered while wiring v0.2 tests)

- `tools/query.py:rhino_object_info` used `.Faces.Count` /
  `.Edges.Count` / `.Vertices.Count` — rhino3dm 8.x's binding does not
  expose these as `Count` properties, so every `rhino_object_info`
  call against a Brep / Mesh in standalone raised `AttributeError`.
  Now uses `len(...)`.
- `tools/query.py` layer iteration accessed `lay.Color.R` etc., but
  rhino3dm's `Layer.Color` is a 4-tuple of ints rather than a struct
  with named fields. `rhino_document_summary` and `rhino_layer_list`
  now read `(r, g, b)` defensively from either shape.

### Tests

- 38 new tests, total 166 passed:
  - `tests/tools/test_composition.py` (8)
  - `tests/tools/test_document_config.py` (6)
  - `tests/tools/test_geometry_validation.py` (5)
  - `tests/tools/test_gh_templates.py` (4)
  - `tests/tools/test_freeform.py` (12)
  - `tests/test_prompts.py` extended with 4 prompt-coverage tests
    (now 9 tests in that file).

### Verification

- `uv run pytest tests/ -q` → 166 passed.
- `uv run ruff check src/ tests/` → All checks passed.
- `dotnet build rhino_plugin/csharp/ -c Release` → 0 errors / 0 warnings.

## [0.1.0 — pre-release notes (was Unreleased)]

### Added
- Project logo at `assets/rhino-logo.png` referenced from both READMEs;
  `pyproject.toml` sdist `include` now ships the `assets/` directory.
- MCP prompts package (`src/rhino_mcp/prompts/strategy.py`) with three
  guides: `general_strategy`, `rhinoscript_workflow`, `viewport_workflow`.
- `rhino_screenshot(as_base64=True)` returns the PNG bytes inline as
  `image_base64` for LLM visual verification.
- `rhino_object_select` filter matrix: `name_pattern`, `layer`, `color`,
  `object_type`, `user_text`, `deselect_first` — combined with AND.
- `rhino_list_objects` carries a `pagination` block
  (`total`, `offset`, `limit`, `returned`, `has_more`).
- Async tool variants for `rhino_list_objects`, `rhino_document_summary`,
  `rhino_layer_list` using `BridgeClient.async_call`.
- `Transport.is_alive()` non-destructive liveness probe with `MSG_PEEK`
  (TCP/Unix) and `PeekNamedPipe` (Windows).
- Reconnect backoff jitter: `RHINO_MCP_RECONNECT_BASE_DELAY`,
  `RHINO_MCP_RECONNECT_JITTER`.
- `tools/_helpers.bridge_call` / `bridge_call_async` wrappers emitting
  DEBUG-level input/output traces.
- 17 new tests (`test_prompts.py`, `test_query.py`,
  `test_select_filters.py`, three new bridge connection tests).
- Thread-safe runtime context with lock protection (`tools/context.py`)
- Bridge auto-reconnection with configurable retries (`RHINO_MCP_RECONNECT_RETRIES`)
- Bridge health check: `ping()`, `is_healthy`, `reconnect()` methods
- `ErrorCategory.TIMEOUT` for timeout-specific error handling
- Transport buffer clearing on connection failure (all 3 transports)
- Request ID mismatch detection (raises error instead of warning)
- Docker compose health check configuration
- CLAUDE.md project documentation
- CONTRIBUTING.md with tool creation guide
- 33 new tests: bridge edge cases, Grasshopper tools, display/surface tools

### Changed
- README.md / README.ko.md largely rewritten: launch-mode matrix,
  per-OS Claude Desktop config-file paths, Cursor IDE example,
  claude.ai remote-connector walkthrough, base64 screenshot /
  pagination / rich-select usage examples, four new env vars
  documented, troubleshooting expanded.
- All Korean comments and docstrings in `src/`, `tests/`, and the C#
  plugin replaced with English to match the project convention.
- Pydantic `Field(...)` descriptions filled in across every tool module
  so parameter help surfaces in MCP clients.
- Removed private FastMCP API access (`_tool_manager._tools`) from server.py
- `send_line` now wraps OSError as ConnectionError across all transports
- `recv_line` now distinguishes TimeoutError from ConnectionError
- `register_tools()` logs warning when zero tools match the runtime mode
- Startup errors now show user-friendly messages with distinct exit codes
- Shared helper functions (`find_layer_index`, `find_material_index`) in `_helpers.py`

### Fixed
- `query.py` used `File3dmObjectTable.Count` which the rhino3dm 8.x
  binding does not expose, raising `AttributeError` on every standalone
  `list_objects` / `document_summary` / `layer_list`. Now uses `len(...)`.
- C# `IOHandler.Screenshot` previously read `output_path` while the
  Python tool sent `path` — both keys are now accepted.
- Global `_RUNTIME` state race condition under concurrent access
- Silent fallback to STANDALONE mode masking configuration errors
- Stale `_connected` flag not updated on transport failure
- Partial buffer data persisting after connection loss

## [0.1.0] - 2025-04-25

### Added
- Initial release
- 51 standalone tools (rhino3dm) + 119 bridge tools (RhinoCommon + Grasshopper)
- Dual-mode architecture: standalone and bridge
- Three transport types: named pipes (Windows), Unix sockets (macOS/Linux), TCP
- FastMCP server with stdio and Streamable HTTP transports
- Docker support with docker-compose
- Bilingual documentation (English + Korean)
- 62 pytest tests with 70% coverage threshold
- 3 example scripts: basic modeling, Grasshopper workflow, parametric facade
