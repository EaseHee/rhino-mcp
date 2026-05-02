"""Strategic guidance prompts surfaced to MCP clients.

Each function here is registered as an MCP prompt and returns a plain
markdown-flavoured string. The text references the actual tool names exposed
by this server (``rhino_*``) so the LLM can reuse them without hallucinating
APIs from other Rhino MCP implementations.
"""

from __future__ import annotations


def general_strategy() -> str:
    """High-level decision tree for driving Rhino through rhino-mcp."""
    return """
============================================================
RHINO-MCP STRATEGY GUIDE
============================================================

STEP 1: ORIENT YOURSELF
-----------------------
Before mutating anything, build a mental model of the document:

- rhino_document_summary()  -> object/layer counts, type histogram
- rhino_layer_list()        -> layer hierarchy with colours
- rhino_list_objects(limit=50, offset=0) -> paginated object inventory
- rhino_get_selected_objects() (bridge only) -> active selection

For very large documents always use ``limit`` + ``offset`` on
rhino_list_objects; the response carries a ``pagination`` block.


STEP 2: PICK THE RIGHT TOOL
---------------------------
Creating geometry:

- Primitives (point, line, circle, arc, polyline, rectangle, polygon,
  helix, spiral, NURBS curve)
    -> rhino_point / rhino_line / rhino_circle / rhino_arc / ...
- Solids (box, sphere, cylinder, cone, torus)
    -> rhino_box / rhino_sphere / rhino_cylinder / ...
- Surfaces (extrude, revolve, loft, sweep, network, patch, blend, fillet)
    -> rhino_extrude / rhino_revolve / rhino_loft / ...
- Boolean ops on closed solids
    -> rhino_boolean_union / _difference / _intersection
- Mesh operations
    -> rhino_mesh_box / rhino_mesh_from_brep / rhino_reduce_mesh / ...
- Anything truly bespoke
    -> rhino_execute_python (bridge) — see ``rhinoscript_workflow``

Modifying geometry:

- Affine transform on existing objects
    -> rhino_move / rhino_rotate / rhino_scale / rhino_mirror / rhino_orient
- Pattern replication
    -> rhino_array_linear / _polar / _rectangular
- Layer / metadata
    -> rhino_object_move_to_layer / rhino_set_user_text
- Bulk attribute edits
    -> rhino_batch_modify (bridge) — much faster than per-object calls

Selection:

- Known IDs                       -> rhino_object_select(object_ids=[...])
- Pattern / colour / layer / type -> rhino_object_select(name_pattern, layer,
                                     color, object_type, user_text)
- Already selected in Rhino       -> rhino_get_selected_objects

Querying:

- One ID known            -> rhino_object_info(object_id=...)
- Filtered list           -> rhino_list_objects(layer=..., kind=...)
- Metadata round-trip     -> rhino_get_user_text / rhino_set_user_text
- Quantitative analysis   -> rhino_area / _volume / _bounding_box /
                              _distance / _curvature_analysis / _section /
                              _contour


STEP 3: BEST PRACTICES
----------------------
1. NAMING — give every created object a meaningful ``name`` so later tools
   can reference it without juggling GUIDs.

2. BATCHING — when creating > 3 similar objects, prefer the dedicated
   batch tools (e.g. rhino_array_*) over a Python loop of single calls.
   When you do iterate, keep batches under ~50 objects per turn.

3. LAYERS — partition output across rhino_layer_create()'d layers; never
   pile new geometry onto the active default layer.

4. UNDO SAFETY — bridge-mode mutations are wrapped in undo records, so
   rhino_undo / rhino_redo can recover from a wrong turn.

5. VERIFY VISUALLY — after non-trivial changes call rhino_zoom_extent
   followed by rhino_screenshot(as_base64=true) to inspect the result
   inline. See ``viewport_workflow``.

6. STAY OUT OF rhinoscriptsyntax UNLESS NECESSARY — the structured tools
   above cover the common cases. Only fall back to rhino_execute_python
   when no native tool fits, and follow ``rhinoscript_workflow`` exactly.

7. ERROR CATEGORIES — failures carry a category in
   ``error.category`` (connection, timeout, parameter, not_found,
   unsupported, gh_component, internal). Branch on this:
   - ``unsupported`` -> the tool requires bridge mode; prompt the user
     to start Rhino 8 + RhinoMCPBridge and retry.
   - ``not_found``   -> object/file does not exist; re-discover via
     rhino_list_objects or rhino_document_summary.
   - ``parameter``   -> input invalid; read the ``hint`` for the allowed
     range/type and fix the call rather than blindly retrying.
""".strip()


def rhinoscript_workflow() -> str:
    """Mandatory steps before invoking rhino_execute_python."""
    return """
============================================================
RHINOSCRIPT PYTHON WORKFLOW (rhino_execute_python)
============================================================

rhino_execute_python runs arbitrary code inside the live Rhino process.
That power makes it the wrong default — prefer the structured tools.
When you must drop down to it, follow these steps every single time.


STEP 1: SEARCH THE API
----------------------
Never recall function names from memory. Use one of:

- rhino_search_rhinoscript_functions(query="boolean")
    -> ranked function-name search
- rhino_get_rhinoscript_docs(query="loft surface between curves")
    -> full documentation snippet for the matched functions
- rhino_list_rhinoscript_modules()
    -> the catalogue of modules (curve, surface, mesh, ...)
- rhino_get_module_functions(module="curve")
    -> every function exported by one module


STEP 2: READ THE SIGNATURE CAREFULLY
------------------------------------
Each doc entry contains:
- the exact parameter list (names, order, types)
- return type (often a GUID string, sometimes None on failure)
- one or more example snippets

Pay special attention to:
- Points are lists [x, y, z], not tuples or Point3d objects.
- Object references travel as GUID strings, never as live objects.
- Many functions return None on failure; check before using the result.


STEP 3: WRITE WITH ONLY VERIFIED FUNCTIONS
------------------------------------------
- import rhinoscriptsyntax as rs
- Call only functions you saw in the doc results.
- Match the parameter spelling exactly (case + order matter).
- Use print(...) for any value you want surfaced back to the LLM.


STEP 4: EXECUTE
---------------
rhino_execute_python(
    code=\"\"\"
    import rhinoscriptsyntax as rs
    line_id = rs.AddLine([0, 0, 0], [10, 0, 0])
    print(line_id)
    \"\"\".strip()
)

If the call returns an error with category=parameter or internal,
re-read STEP 2 — almost every failure here is a hallucinated signature.


COMMON FAILURE MODES
--------------------
- Guessing names like rs.MakeBox (does not exist; use rs.AddBox).
- Wrong argument order (rs.RotateObject(obj, angle, axis) vs
  (obj, axis, angle) — check the doc).
- Treating GUID strings as live objects (rs.* expects GUIDs).
- Forgetting that rs functions mutate the doc; the structured rhino_*
  tools are usually a clearer choice.
""".strip()


def viewport_workflow() -> str:
    """Visual verification workflow (bridge mode)."""
    return """
============================================================
VIEWPORT VERIFICATION WORKFLOW
============================================================

LLMs cannot see Rhino's viewport directly, but rhino-mcp can return a
PNG screenshot inline as base64 so the next turn can reason about
what was actually rendered.


WHEN TO USE
-----------
- After a non-trivial create/modify cycle, before reporting "done".
- When the user reports "this doesn't look right" and you need ground
  truth instead of guessing from object IDs.
- Before cleanup operations (boolean / trim / delete) so you can
  compare a before/after pair.


STEPS
-----
1. Frame the model:
     rhino_zoom_extent()
   Optionally constrain to specific objects via object_ids=[...].

2. (Optional) Switch display mode for clarity:
     rhino_display_mode_set(mode="Shaded")    # or "Wireframe", "Rendered"

3. Capture the viewport inline:
     rhino_screenshot(
         path="/tmp/rhino_mcp_capture.png",
         width=1280,
         height=720,
         as_base64=True,
     )
   The response carries:
     - summary.path                  -> on-disk PNG (handy for the user)
     - image_base64                  -> PNG bytes you can read directly
     - mime                          -> "image/png"

4. Read the base64 payload — DO NOT call additional tools just to look at
   the file again, the data is already in the response.


TIPS
----
- Keep width/height moderate (e.g. 1280x720). Larger screenshots blow
  through context budget without adding signal.
- For animated previews use rhino_turntable instead; it writes a frame
  sequence to disk.
- Bridge mode only — standalone (rhino3dm) has no viewport.
""".strip()
