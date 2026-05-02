<div align="center">

<img src="assets/rhino-logo.png" alt="rhino-logo"/>

# rhino-mcp

**Drive McNeel Rhino 8 and Grasshopper from Claude through the Model Context Protocol.**

![PyPI](https://img.shields.io/pypi/v/rhino-mcp)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Rhino](https://img.shields.io/badge/Rhino-8-red)
![MCP](https://img.shields.io/badge/MCP-compatible-purple)
![Platform](https://img.shields.io/badge/platform-windows%20%7C%20macos%20%7C%20linux-lightgrey)

[English](./README.md) · [한국어](./README.ko.md)

</div>

---

## Overview

`rhino-mcp` is a Model Context Protocol server that lets Claude (or any MCP client) drive Rhino 8 — creating geometry, manipulating layers and materials, baking Grasshopper output, exporting STEP/IGES/STL/OBJ — through plain natural-language tool calls. It runs in two modes:

- **Standalone** (default): backed by [`rhino3dm`](https://github.com/mcneel/rhino3dm) for headless `.3dm` file authoring; works without Rhino installed and exposes **~89 tools** (geometry, file-I/O, transform, layer, material, analysis, RhinoScript docs, composition, document hygiene, geometry validation, GH template catalogue, *and* freeform skin / panelisation / curvature / fields for non-rectilinear architecture).
- **Bridge**: when the C# bridge plugin is loaded in a live Rhino 8 session, the server transparently forwards every call (booleans, lofts, sweeps, viewport, render, scripting, deformation, NURBS editing, SubD, paneling, freeform analysis with true Gaussian curvature, *and* every Grasshopper operation including templates) to RhinoCommon and Grasshopper.Instances, exposing **156+ tools**.

## Features

- **Full geometry catalogue** — points, lines, polylines, arcs, circles, ellipses, polygons, helixes, NURBS curves, rebuilds.
- **Solids and meshes** — boxes, spheres, cylinders, cones, tori, mesh boxes; booleans / sweeps / lofts / fillets via the bridge.
- **Transforms** — move, rotate, scale, mirror, plane-to-plane orient, linear/polar/rectangular arrays.
- **Script execution** — run arbitrary RhinoScript Python (IronPython) or RhinoCommon C# (Roslyn) code in a live Rhino session, with built-in RhinoScript API documentation search (899 functions).
- **Advanced modeling** — deformation (bend/twist/taper/flow), NURBS editing (rebuild/unroll/evaluate), SubD, surface matching, extraction (dup edge/border/isocurve/Make2D), control points, and paneling tools.
- **Undo / redo and batch operations** — every bridge operation is wrapped in undo records; batch modify changes many objects in a single call.
- **Layers, materials, blocks, groups** — full attribute control on the document.
- **File I/O** — open/save `.3dm`, export OBJ/STL standalone; STEP/IGES/DXF and screenshots via the bridge.
- **Inline base64 screenshots** — `rhino_screenshot(as_base64=True)` returns the PNG payload inline for visual verification by the LLM.
- **Rich object selection** — `rhino_object_select` filters by glob name pattern, layer, RGB color, object type, and user-text key/value pairs.
- **Pagination on bulk queries** — `rhino_list_objects` returns a `pagination: {total, offset, limit, returned, has_more}` block so large documents stay manageable.
- **Scene composition shortcuts** (v0.2) — `rhino_place_grid`, `rhino_stack_floors`, `rhino_scatter`, `rhino_replicate_along_curve` collapse "loop + transform" into a single tool call.
- **Document hygiene tools** (v0.2) — query/set units, tolerances, and base point (`rhino_document_units_*`, `rhino_tolerance_*`, `rhino_origin_set`); `rhino_document_summary` exposes them so the LLM can verify scale before issuing geometry calls.
- **Geometry validation** (v0.2) — `rhino_validate_brep`, `rhino_report_mesh_health`, `rhino_curve_continuity`, plus `rhino_check_naked_edges` (bridge) for explicit topology diagnostics before booleans / exports.
- **Grasshopper template loader** (v0.2) — `gh_template_list` reads a manifest of pre-wired definitions; `gh_load_template`, `gh_bind_template_parameter`, `gh_run_template` (bridge) load, parameterise, and bake them.
- **Free-form architecture toolkit** — `rhino_skin_from_sections`, `rhino_uv_grid_panels`, `rhino_panel_planarity`, `rhino_panel_curvature_classify`, `rhino_surface_developable_score`, `rhino_attractor_displace_points`, `rhino_smooth_polyline`. Bridge mode adds true Gaussian / mean / principal curvature, world-axis slicing, and waffle ribs.
- **Strategy prompts for the LLM** — seven `@mcp.prompt()` guides (`general_strategy`, `rhinoscript_workflow`, `viewport_workflow`, `parametric_workflow`, `bim_authoring_workflow`, `design_dialogue_workflow`, `freeform_workflow`) help Claude pick the right tool, avoid hallucinated APIs, and keep the user in the loop on design decisions.
- **Async-capable tools** — read-only query tools run on `async def` so concurrent bridge round-trips don't stall the MCP transport.
- **Robust connection layer** — JSON-RPC over named pipe / Unix socket / TCP with `MSG_PEEK` liveness probes and exponential backoff with jitter on reconnect.
- **Grasshopper automation** — open `.gh` files, drop components, wire them, set sliders/panels/toggles, run, bake, read DataTrees.
- **Three transports** — stdio (Claude Desktop), Streamable HTTP, Docker/TCP.
- **Capability-aware registration** — bridge-only tools are simply not registered when no bridge is reachable; no stub functions, ever.
- **Actionable errors** — every failure carries a category, a remediation hint, and details the agent can act on.

## Architecture

```
┌──────────────┐     stdio | HTTP      ┌────────────────┐
│  Claude /    │ ◀──────────────────▶ │   rhino-mcp    │
│  MCP client  │                      │   (Python)     │
└──────────────┘                      └─────┬──────────┘
                                            │
                              JSON-RPC 2.0  │   (named pipe / unix socket / TCP)
                                            │
                                  ┌─────────▼──────────┐
                                  │  C# Bridge Plugin  │
                                  │  (inside Rhino 8)  │
                                  │  ────────────────  │
                                  │  RhinoCommon       │
                                  │  Grasshopper       │
                                  │  Roslyn (C# exec)  │
                                  │  IronPython (Py)   │
                                  └────────────────────┘
```

In **standalone** mode the right-hand side is replaced by an in-process `rhino3dm.File3dm` document; bridge-only tools are unregistered.

## Requirements

- Python 3.11 or newer
- `rhino3dm >= 8.9`, `mcp[cli] >= 1.2`, `pydantic >= 2.6` (installed automatically)
- Optional: McNeel Rhino 8 (any platform) — needed only for bridge mode
- Optional: .NET 8 SDK — to build the C# bridge plugin (`dotnet build`)
- Optional: `pywin32` on Windows for the named-pipe transport

## Installation

### Using uv (recommended)

```bash
uv tool install rhino-mcp
# or, from a checkout:
uv sync && uv run rhino-mcp
```

### Using pip

```bash
pip install rhino-mcp
rhino-mcp --version
```

### Docker

```bash
docker compose -f docker/docker-compose.yml up --build
```

The container exposes the server over Streamable HTTP on TCP `:8765`.

## Running the server

`rhino-mcp` is normally launched by an MCP client (Claude Desktop / Cursor / claude.ai connector) via the `command + args` you put into the client's config. You can also run it manually for debugging.

### Launch modes

| Use case                                | Command                                                                        |
|-----------------------------------------|--------------------------------------------------------------------------------|
| Stdio (Claude Desktop default)          | `uvx rhino-mcp` *or* `rhino-mcp`                                               |
| Streamable HTTP (local dev / Cursor)    | `rhino-mcp --transport http --host 127.0.0.1 --port 8765`                      |
| Streamable HTTP (claude.ai connector)   | `rhino-mcp --transport http --host 0.0.0.0 --port 8765 --allow-external --stateless` |
| Docker (HTTP on `:8765`)                | `docker compose -f docker/docker-compose.yml up --build`                       |
| Force standalone (no Rhino needed)      | `RHINO_MCP_FORCE_MODE=standalone rhino-mcp`                                    |
| Force bridge (fail fast if Rhino down)  | `RHINO_MCP_FORCE_MODE=bridge rhino-mcp`                                        |
| Force bridge with HTTP fallback         | `RHINO_MCP_FORCE_MODE=bridge RHINO_MCP_BRIDGE_OPTIONAL=1 rhino-mcp --transport http` |
| Show all CLI flags                      | `rhino-mcp --help`                                                             |

The HTTP endpoint is `http://<host>:<port>/mcp`. Use `--allow-external` only when exposing the server through ngrok / Cloudflare Tunnel / etc. — it disables DNS-rebinding protection.

### Claude Desktop (stdio)

`claude_desktop_config.json` lives at:

| OS      | Path                                                                                    |
|---------|-----------------------------------------------------------------------------------------|
| macOS   | `~/Library/Application Support/Claude/claude_desktop_config.json`                       |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json`                                           |
| Linux   | `~/.config/Claude/claude_desktop_config.json`                                           |

Paste this entry under `mcpServers`:

```json
{
  "mcpServers": {
    "rhino-mcp": {
      "command": "uvx",
      "args": ["rhino-mcp"],
      "env": {
        "RHINO_MCP_TRANSPORT": "stdio",
        "RHINO_HOST": "127.0.0.1",
        "RHINO_PORT": "4242",
        "RHINO_MCP_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

Prefer a checkout? Point `command` at `uv` and run from the repo:

```json
{
  "mcpServers": {
    "rhino-mcp": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/rhino-mcp", "run", "rhino-mcp"],
      "env": { "RHINO_MCP_LOG_LEVEL": "DEBUG" }
    }
  }
}
```

Restart Claude Desktop; the rhino-mcp tools and the three strategy prompts (`general_strategy`, `rhinoscript_workflow`, `viewport_workflow`) appear in the palette.

### Cursor IDE

Cursor reads `~/.cursor/mcp.json` (global) or `<project>/.cursor/mcp.json` (per-project):

```json
{
  "mcpServers": {
    "rhino-mcp": {
      "command": "uvx",
      "args": ["rhino-mcp"],
      "env": { "RHINO_MCP_FORCE_MODE": "bridge" }
    }
  }
}
```

### claude.ai remote connector (Streamable HTTP)

1. Run the server with HTTP + external access:

   ```bash
   rhino-mcp --transport http --host 0.0.0.0 --port 8765 --allow-external --stateless
   ```

2. Tunnel it (e.g. `ngrok http 8765`) and grab the public HTTPS URL.

3. In claude.ai → Settings → Connectors → *Add custom connector*, set the URL to `https://<your-tunnel>/mcp`.

### Generic stdio MCP clients

Any MCP-compatible client (mcp-inspector, Continue, Claude Code, etc.) that can spawn a subprocess will work — give it `uvx rhino-mcp` or the path to your `rhino-mcp` entry-point and inherit env vars from the table below.

### Rhino-side bridge plugin (C# — recommended)

Build and install the C# plugin for full 130+ tool support. The included helper script wraps `dotnet build` and verifies the post-build install location:

```bash
./scripts/build-plugin.sh             # debug build + install
./scripts/build-plugin.sh --release   # release build
./scripts/build-plugin.sh --clean     # clean + rebuild

# Or invoke dotnet directly:
dotnet build rhino_plugin/csharp/RhinoMCPPlugin.csproj -c Release
```

Post-build targets copy the `.rhp`:

| OS      | Path                                                                                  |
|---------|---------------------------------------------------------------------------------------|
| macOS   | `/Applications/Rhino 8.app/Contents/PlugIns/RhinoMCPBridge.rhp`                       |
| Windows | `%APPDATA%/McNeel/Rhinoceros/8.0/Plug-ins/RhinoMCPBridge/RhinoMCPBridge.rhp`           |

Restart Rhino 8 — the bridge starts automatically on load (TCP `:4242` by default). Then restart `rhino-mcp` (or set `RHINO_MCP_FORCE_MODE=bridge`) and the bridge-only tools become available.

<details>
<summary>Legacy Python bridge (deprecated, 8 methods)</summary>

```bash
python rhino_plugin/install.py
# Then in Rhino 8:
_-RunPythonScript "<scripts dir>/RhinoMCPBridge.py"
```

The Python bridge supports only a handful of methods. Use the C# plugin for script execution, undo/redo, batch, deformation, NURBS, SubD, paneling, base64 screenshots, and more.
</details>

## Quick start

```python
# After "rhino-mcp" is configured in Claude Desktop, ask Claude:
#   "Create a 10-unit sphere at the origin and save the document to /tmp/demo.3dm"
# Behind the scenes Claude calls rhino_sphere → rhino_save.
```

### Strategy prompts

Three MCP prompts are registered automatically and surfaced in the client's prompt picker:

| Prompt                  | When to use                                                                                  |
|-------------------------|----------------------------------------------------------------------------------------------|
| `general_strategy`      | Decision tree for orienting in a document → choosing the right tool → best practices.        |
| `rhinoscript_workflow`  | Mandatory steps **before** invoking `rhino_execute_python` so the LLM doesn't hallucinate APIs. |
| `viewport_workflow`     | How to combine `rhino_zoom_extent` + `rhino_screenshot(as_base64=True)` for visual checks.    |

Telling Claude "use the general_strategy prompt before you start" gives much better tool selection on long sessions.

### Visual verification with base64 screenshots

```text
"Build a 5x5x5 box on layer 'Demo', then take a 1280x720 base64 screenshot so you can confirm it landed."
```

Claude calls `rhino_box → rhino_zoom_extent → rhino_screenshot(as_base64=True)` and reads the inline PNG from the response (`image_base64` field) on the next turn.

### Pagination & rich filtering

```text
"List the first 50 curves on the 'Walls' layer, then select every object whose name matches 'Pillar_*' on layer 'Structure'."
```

`rhino_list_objects` returns a `pagination` block; iterate with `offset += limit` until `has_more` is `false`. `rhino_object_select` accepts `name_pattern`, `layer`, `color`, `object_type`, `user_text`, and `deselect_first`.

Standalone smoke run from the shell:

```bash
RHINO_MCP_FORCE_MODE=standalone uv run python - <<'PY'
import asyncio
from rhino_mcp.server import build_server
from rhino_mcp.utils.registry import Mode

mcp, count = build_server(runtime_mode=Mode.STANDALONE, bridge_client=None)
print(f"{count} tools registered")
sphere = asyncio.run(
    mcp._tool_manager._tools["rhino_sphere"].run(
        {"args": {"center": {"x": 0, "y": 0, "z": 0}, "radius": 10.0}}
    )
)
print(sphere)
PY
```

## Tools reference (summary)

| Category       | Standalone | + Bridge  | Notable members |
|----------------|------------|-----------|-----------------|
| Geometry       | 14         | 14        | `rhino_point`, `rhino_circle`, `rhino_helix`, `rhino_nurbs_curve`, `rhino_rebuild_curve` |
| Curves         | 3          | 3         | `rhino_curve_length`, `rhino_curve_point_at`, `rhino_curve_split` |
| Solids         | 5          | 10        | `rhino_box`, `rhino_sphere`, `rhino_boolean_union` (bridge) |
| Surfaces       | 0          | 11        | `rhino_loft`, `rhino_sweep1`, `rhino_revolve` |
| Mesh           | 1          | 8         | `rhino_mesh_box`, `rhino_weld_mesh` (bridge) |
| Transform      | 9          | 11        | `rhino_array_polar`, `rhino_orient`, `rhino_flow` (bridge) |
| Annotation     | 2          | 8         | `rhino_text_dot`, `rhino_dimension_linear` (bridge) |
| Layer / Object | 6          | 8         | `rhino_layer_create`, `rhino_block_insert` (bridge) |
| Material       | 2          | 3         | `rhino_material_create`, `rhino_render_viewport` (bridge) |
| File I/O       | 5          | 9         | `rhino_save`, `rhino_export_step` (bridge) |
| Analysis       | 4          | 9         | `rhino_volume`, `rhino_zebra` (bridge) |
| Query          | 7          | 8         | `rhino_list_objects`, `rhino_document_summary`, `rhino_get_selected_objects` (bridge) |
| Display        | 0          | 5         | `rhino_zoom_extent`, `rhino_named_view_save` |
| **Scripting**  | 0          | **2**     | **`rhino_execute_python`**, **`rhino_execute_csharp`** |
| **RS Docs**    | **4**      | **4**     | **`rhino_search_rhinoscript_functions`**, **`rhino_get_rhinoscript_docs`** |
| **History**    | 0          | **2**     | **`rhino_undo`**, **`rhino_redo`** |
| **Batch**      | 0          | **1**     | **`rhino_batch_modify`** |
| **Deformation**| 0          | **4**     | **`rhino_bend`**, **`rhino_twist`**, **`rhino_taper`**, **`rhino_flow_along_curve`** |
| **NURBS**      | 0          | **5**     | **`rhino_rebuild_surface`**, **`rhino_unroll`**, **`rhino_surface_from_points`** |
| **SubD**       | 0          | **2**     | **`rhino_create_subd`**, **`rhino_subd_to_nurbs`** |
| **Srf Match**  | 0          | **3**     | **`rhino_match_surface`**, **`rhino_blend_surface_edges`**, **`rhino_merge_surfaces`** |
| **Extraction** | 0          | **4**     | **`rhino_dup_edge`**, **`rhino_dup_border`**, **`rhino_isocurve`**, **`rhino_make2d`** |
| **Ctrl Points**| 0          | **2**     | **`rhino_get_control_points`**, **`rhino_set_control_points`** |
| **Paneling**   | 0          | **3**     | **`rhino_panelize_surface`**, **`rhino_create_uv_grid`**, **`rhino_panel_frames`** |
| Grasshopper    | 0          | 22        | `gh_set_slider`, `gh_bake_to_rhino`, `gh_data_tree_get` |

Detailed signatures live in [docs/en/tools-reference.md](docs/en/tools-reference.md).

## Grasshopper integration

```text
1. Start Rhino 8 → open Grasshopper → load your `.gh` definition.
2. Run `_-RunPythonScript "<path>/RhinoMCPBridge.py"` (or rely on the startup hook).
3. Set `RHINO_MCP_FORCE_MODE=bridge` and restart rhino-mcp.
4. From Claude:
   - "Open /work/wing.gh, set the 'span' slider to 12.5, run, bake to layer 'Wing'."
   - "Read the output of the 'Voronoi' component as a DataTree."
```

See [docs/en/grasshopper-guide.md](docs/en/grasshopper-guide.md) for canvas/component/cluster recipes.

## Configuration

Every knob is controlled by an environment variable. CLI flags override env where applicable.

| Variable                            | Default            | Purpose |
|-------------------------------------|--------------------|---------|
| `RHINO_MCP_TRANSPORT`               | `stdio`            | `stdio` or `http` (Streamable HTTP) |
| `RHINO_MCP_FORCE_MODE`              | _(auto)_           | Force `standalone` or `bridge` |
| `RHINO_MCP_BRIDGE_OPTIONAL`         | `0`                | When `1` and `RHINO_MCP_FORCE_MODE=bridge`, fall back to standalone if the bridge is unreachable (recommended for HTTP connectors). |
| `RHINO_MCP_TRANSPORT_KIND`          | _(auto)_           | Bridge transport selector: `pipe` / `unix` / `tcp` |
| `RHINO_HOST`, `RHINO_PORT`          | `localhost:4242`   | TCP transport endpoint |
| `RHINO_MCP_PIPE`                    | `rhino_mcp`        | Windows named-pipe name |
| `RHINO_MCP_SOCKET`                  | _(XDG runtime)_    | Unix socket path override |
| `RHINO_MCP_BRIDGE_TIMEOUT`          | `1` (auto), `5` (forced) | Seconds to wait for a bridge ping |
| `RHINO_MCP_RECONNECT_RETRIES`       | `1`                | Max reconnect attempts after a transient transport failure |
| `RHINO_MCP_RECONNECT_BASE_DELAY`    | `0.5`              | Base delay (seconds) for exponential backoff |
| `RHINO_MCP_RECONNECT_JITTER`        | `0.25`             | Symmetric jitter ratio (`0` disables, useful for tests) |
| `RHINO_MCP_LOG_LEVEL`               | `INFO`             | Stderr log level. Set `DEBUG` to see every bridge JSON-RPC call. |

## Development

```bash
git clone https://github.com/easehee/rhino-mcp.git
cd rhino-mcp
uv venv && source .venv/bin/activate
uv pip install -e '.[dev]'

# Tests + coverage
uv run pytest --cov=src/rhino_mcp

# Lint + type check
uv run ruff check src/ tests/
uv run mypy src/rhino_mcp

# Build the C# bridge plugin (auto-installs into Rhino on macOS/Windows)
./scripts/build-plugin.sh --release

# Wheel + sdist
./scripts/build.sh
```

### Manual smoke test against a running server

```bash
# Terminal A — start the server with verbose logging
RHINO_MCP_LOG_LEVEL=DEBUG rhino-mcp --transport http --port 8765

# Terminal B — list tools via the MCP inspector or a curl probe
npx @modelcontextprotocol/inspector http://127.0.0.1:8765/mcp
```

## Troubleshooting

| Symptom                                   | Likely cause / remediation |
|-------------------------------------------|----------------------------|
| `Cannot reach Rhino bridge.`              | Start Rhino 8 with the C# bridge plugin loaded; verify `RHINO_HOST`/`RHINO_PORT`. |
| Bridge-only tool absent in Claude         | Server is in standalone mode — load the bridge plugin or set `RHINO_MCP_FORCE_MODE=bridge`. |
| `Invalid parameter: axis` (cylinder)      | Standalone supports only `{x:0,y:0,z:1}`; switch to bridge for arbitrary axes. |
| `non-3DM` import error                    | Standalone import is `.3dm`-only; use bridge mode for STEP/IGES/DXF. |
| `transport failure on tcp://...`          | The bridge crashed or Rhino was closed — `rhino-mcp` will reconnect with exponential backoff (`RHINO_MCP_RECONNECT_RETRIES`). |
| Stdout corrupted under stdio transport    | Always log to stderr; rhino-mcp does this — verify no third-party libraries print to stdout. |
| `image_base64` missing from screenshot    | Caller passed `as_base64=False` (default) **or** the screenshot file failed to write — check the `summary.path` and `base64_error` fields. |
| Pagination loops forever                  | Always advance `offset` by `pagination.returned`, not by `limit`; the last page may be partial. |
| `rhino_object_select` returns 0 matches   | Filters AND together — try removing one filter at a time; the `color` filter only works on objects with `ColorSource=ColorFromObject`. |

More in [docs/en/troubleshooting.md](docs/en/troubleshooting.md).

## License

MIT — see [LICENSE](./LICENSE).
