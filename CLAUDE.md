# rhino-mcp

MCP server connecting Claude to McNeel Rhino 8 and Grasshopper.

## Architecture

- **Standalone mode**: `rhino3dm` (headless Python lib) for `.3dm` file I/O. ~72 tools.
- **Bridge mode**: C# plugin (`rhino_plugin/csharp/`) with JSON-RPC 2.0. ~130+ tools.
- Mode auto-detected at startup (`detect_mode()`). Override with `RHINO_MCP_FORCE_MODE`.
- Legacy Python bridge (`RhinoMCPBridge.py`) supports ~8 methods; C# bridge recommended.

## Project Structure

```
src/rhino_mcp/
  server.py          # entrypoint, FastMCP server, tool registration
  transport.py       # stdio/HTTP transport selection
  document.py        # DocumentHandle registry (rhino3dm.File3dm wrapper)
  data/              # static data (rhinoscriptsyntax.json)
  tools/             # tool modules (26 categories)
    context.py       # runtime state (mode, bridge client)
    _helpers.py      # shared utilities (to_point, doc, add_object_with_attrs, etc.)
    geometry.py      # points, curves, primitives, rebuild_curve
    curves.py        # curve analysis, point_at, split
    solids.py        # box, sphere, cylinder, cone, torus, booleans
    surfaces.py      # plane, extrude, revolve, loft, sweep, blend, fillet, offset
    mesh.py          # mesh creation, booleans, weld, reduce
    transform.py     # move, rotate, scale, mirror, orient, array
    annotation.py    # text, dimensions, leader, hatch, clipping plane
    layers.py        # layer CRUD, visibility, lock
    materials.py     # material create, assign
    io.py            # open, save, import, export (OBJ/STL/STEP/IGES/DXF)
    analysis.py      # bbox, area, volume, distance, curvature, section, contour
    query.py         # list_objects, object_info, document_summary, selected_objects
    display.py       # viewport, zoom, named views, display modes (bridge)
    scripting.py     # execute Python/C# scripts in Rhino (bridge)
    rhinoscript_docs.py  # RhinoScript API search and documentation (both)
    history.py       # undo/redo (bridge)
    batch.py         # batch modify objects (bridge)
    deformation.py   # bend, twist, taper, flow along curve (bridge)
    nurbs.py         # rebuild surface, surface from points, unroll, evaluate (bridge)
    subd.py          # SubD create, to NURBS (bridge)
    surface_match.py # match, blend edges, merge (bridge)
    extraction.py    # dup edge/border, isocurve, make2d (bridge)
    control_points.py # get/set NURBS control points (bridge)
    paneling.py      # panelize, UV grid, panel frames (bridge)
    grasshopper/     # GH canvas, components, data_tree, parameters (bridge)
  bridge/            # JSON-RPC transport layer
    rhino_connection.py  # BridgeClient, detect_mode()
    transport_base.py    # abstract Transport
    tcp_socket.py / unix_socket.py / named_pipe.py
  models/            # Pydantic data models
  utils/             # registry, error_handling, logging, serialization
rhino_plugin/
  csharp/            # C# bridge plugin (recommended, 130+ methods)
    Handlers/        # 14+ handler classes (one per category)
    CommandDispatcher.cs  # method → handler routing
  RhinoMCPBridge.py  # legacy Python bridge (8 methods, deprecated)
tests/               # pytest (110+ tests)
```

## Development

```bash
uv sync
uv pip install -e '.[dev]'
uv run pytest tests/ -v                    # all tests
uv run pytest tests/ --cov=src/rhino_mcp   # coverage
uv run ruff check src/ tests/              # lint
uv run mypy src/rhino_mcp                  # type check
dotnet build rhino_plugin/csharp/          # build C# plugin
```

## Adding a New Tool

1. Create `src/rhino_mcp/tools/<category>.py` with Pydantic input model + tool function
2. Define `register(mcp, mode)` using `@mcp.tool()` decorator
3. Add `(Mode.BOTH|BRIDGE, <module>.register)` to `server.py:_tool_specs()`
4. Bridge mode: `runtime().require_bridge().call("rhino.category.action", args.model_dump())`
5. Standalone mode: use `rhino3dm` API directly
6. Return format: `{"summary": {...}, "text": "..."}`
7. Errors: `parameter_error()`, `not_found_error()`, `unsupported_in_standalone()`
8. For bridge-only tools, create C# handler in `rhino_plugin/csharp/Handlers/<Category>Handler.cs`
9. Register bridge method in `rhino_plugin/csharp/CommandDispatcher.cs`
10. Add tests in `tests/tools/test_<category>.py`

## Conventions

- Tool first argument: `args: _InputModel` (Pydantic BaseModel)
- `doc_id` field: default `"active"` (DocumentHandle lookup)
- Shared logic in `_helpers.py`
- `Mode` enum: `STANDALONE`, `BRIDGE`, `BOTH`
- Commit messages: English title + English body (Conventional Commits)
- Code comments: English only

## Key Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RHINO_MCP_TRANSPORT` | `stdio` | `stdio` or `http` |
| `RHINO_MCP_FORCE_MODE` | auto | `standalone` or `bridge` |
| `RHINO_MCP_BRIDGE_OPTIONAL` | `0` | `1` = fall back to standalone if bridge is unreachable (connector mode) |
| `RHINO_HOST` | `localhost` | Bridge TCP host |
| `RHINO_PORT` | `4242` | Bridge TCP port |
| `RHINO_MCP_LOG_LEVEL` | `INFO` | Logging level |
