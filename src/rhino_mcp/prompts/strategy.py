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


def parametric_workflow() -> str:
    """Iterative parametric exploration workflow (sliders, sweeps, comparisons)."""
    return """
============================================================
PARAMETRIC EXPLORATION WORKFLOW
============================================================

Use this workflow when the user wants to *explore* a design space
("what if the bay is 6/8/10/12 m?") rather than build a single fixed
artefact. The structure below converts open-ended requests into a
finite, comparable set of design candidates.


STEP 1: VERIFY DOCUMENT HYGIENE FIRST
-------------------------------------
Before any parametric run, confirm the document is in a known state:

- rhino_document_summary()  -> units, tolerances, base point, layer tree
- rhino_document_units_set(units="m"|"mm"|...) if the user's spec implies
  a different unit than the document. Ask the user before changing units
  on a document that already has geometry.
- rhino_tolerance_set if the spec mentions a fabrication tolerance that
  differs from the document's. Tighter tolerance = slower booleans.

A wrong unit silently produces "facade panels of 1.2 km" — diagnose it
once at the top instead of debugging downstream.


STEP 2: PARAMETERISE
--------------------
Identify the variables that drive the question and how they map to
tools.

- Bundled GH templates:
    gh_template_list()                       -> catalogue + parameter
                                                 contracts (count_x,
                                                 panel_w, etc.)
    gh_load_template(name="panel_grid")
    gh_bind_template_parameter(template_id, parameter, value)
    gh_run_template(template_id, bake=True)

- Pure geometry tools:
    rhino_place_grid / rhino_stack_floors    -> regular layouts
    rhino_scatter(seed=...)                   -> stochastic layouts;
                                                 ALWAYS pass a seed so
                                                 successive runs are
                                                 comparable.
    rhino_replicate_along_curve              -> path-driven repetition

- Custom GH wiring:
    gh_add_component / gh_connect_components / gh_set_slider — only when
    no template fits. Prefer extending the templates manifest over
    building the same wiring twice.


STEP 3: SAMPLE THE SPACE
------------------------
Pick a sweep schedule before running anything. Three patterns cover
~95 % of real questions:

- Linear sweep         -> 4-6 evenly spaced values per variable.
- Cross product (2-D)  -> small grids only (e.g. 4x4); explodes fast.
- Anchored variants    -> baseline + 2-3 variations on one variable.

Save each variant under its own layer or named view so you can switch
between them visually:
    rhino_layer_create(name="study/v01_8m")
    rhino_named_view_save(name="study_v01_8m")  (bridge)


STEP 4: EVALUATE
----------------
For every variant, capture quantitative + visual feedback:

- rhino_zoom_extent()
- rhino_screenshot(as_base64=True)            -> visual delta in chat
- rhino_area / rhino_volume / rhino_bounding_box
                                               -> hard numbers
- rhino_validate_brep / rhino_report_mesh_health
                                               -> catch silent topology
                                                 failures BEFORE the
                                                 user sees them

Do NOT skip validation between variants — a parametric sweep that
silently leaks invalid geometry into the model wastes the user's
review time.


STEP 5: SUMMARISE
-----------------
After the sweep, return a compact comparison table to the user:

  variant | parameter | area | volume | screenshot
  v01     | 8 m       | 240  | 720    | (base64)
  v02     | 10 m      | 300  | 900    | (base64)
  ...

Then ask the user which direction to refine. Do not collapse the
options unilaterally — the point of the sweep is the choice.
""".strip()


def bim_authoring_workflow() -> str:
    """Layer / grouping / metadata conventions for architectural authoring."""
    return """
============================================================
BIM AUTHORING WORKFLOW (architectural conventions)
============================================================

LLM-authored Rhino models tend to dump everything onto the active
layer with random names. Downstream consumers (drawings, schedules,
exports) then can't filter by discipline, phase, or material. Apply
the conventions below from the first geometry call.


LAYER STRUCTURE
---------------
Use a discipline / element / state hierarchy. Default tree:

  Site/
    Topography
    Boundary
  Arch/
    Walls/
      Existing
      Proposed/Demolished
    Floors
    Roof
    Openings/
      Doors
      Windows
    Furniture
  Struct/
    Columns
    Beams
    Slabs
  MEP/
    Ducts
    Pipes
    Equipment

Create layers in advance:
    rhino_layer_create(name="Arch::Walls::Proposed",
                       color={"r":160,"g":160,"b":160})

Use "::" as the separator (Rhino's native nested-layer syntax).
``rhino_layer_list`` returns full paths so you can verify the tree.
``rhino_document_summary`` reports ``layer_tree_depth`` so you can spot
flat (= un-organised) documents at a glance.


GROUPING
--------
Group composite assemblies, not single primitives:

- A wall + its door cut + the door object  -> one group.
- A column + cap + base                     -> one group.
- A floor slab + its perimeter beam         -> one group.

Use ``rhino_group`` with a stable name like "WallType_W01_Group_05" so
follow-up turns can re-select the entire assembly.


METADATA (user_text)
--------------------
Attach machine-readable metadata to every meaningful object so a
schedule / BOM tool can filter without parsing names:

    rhino_set_user_text(object_id=..., key="function", value="wall")
    rhino_set_user_text(..., key="material", value="CIP_concrete")
    rhino_set_user_text(..., key="revision", value="A.02")
    rhino_set_user_text(..., key="fire_rating", value="2h")

Standard keys to populate:
- function       (wall / floor / column / beam / opening / fixture)
- material       (concrete / steel / glass / timber_clt / brick / ...)
- assembly_type  (W01, F02, ...) — references a separate spec
- phase          (existing / proposed / demolished)
- revision       (A.01, A.02, ...)
- fire_rating    (none / 1h / 2h / 3h)

Read them back with ``rhino_get_user_text``. Filter selections via
``rhino_object_select(user_text={"function":"wall"})`` — much faster
than scanning names.


VERIFICATION
------------
Before reporting the model "done":
1. rhino_document_summary  -> confirm units, tolerances, layer tree
                              depth >= 2.
2. rhino_layer_list         -> confirm naming hygiene (no "Default" or
                              "Layer 03").
3. Sample a few user_text reads to confirm metadata is attached.
""".strip()


def design_dialogue_workflow() -> str:
    """Multi-turn, user-in-the-loop design checkpoints."""
    return """
============================================================
DESIGN DIALOGUE WORKFLOW
============================================================

LLMs tend to commit to a single interpretation of an ambiguous brief
("design a small cafe"), generate hundreds of objects, and then ask
the user whether it looks right. By that point reverting requires a
visible amount of work. Use this workflow to keep the user in the
loop on decisions that change the design substantially.


PRINCIPLE
---------
Take small visible steps. Show the result. Confirm the next decision
before scaling up.


STEP 1: DETECT AMBIGUITY EARLY
------------------------------
Before generating, list the underspecified variables:

- Site footprint, orientation, north arrow, base point
- Plot size, setback rules, floor height, total floor count
- Programme allocation (offices vs residential vs mixed)
- Material palette and its visual weight
- Output scale (mm-precision detail vs urban massing)

If two or more of these are missing, ASK the user before generating
geometry. A short question saves the cost of regenerating.


STEP 2: SHOW BEFORE EXPANDING
-----------------------------
Generate the simplest representative sample first — typically:

- One floor plate (rhino_rectangle / rhino_extrude) instead of all
  floors.
- One paneling cell (gh_template_list / panel_grid) at default
  parameters instead of a finished facade.
- A single typical wall with its assembly metadata instead of all
  walls.

Then run the viewport_workflow:
    rhino_zoom_extent()
    rhino_screenshot(as_base64=True)

…and ask "Should I extend this to N floors / M bays / the whole
site?". Do not extend silently.


STEP 3: CHECKPOINT BEFORE BIG MOVES
-----------------------------------
Before any irreversible-feeling step, save a checkpoint the user can
revert to:

- Bridge: rhino_named_view_save(name="checkpoint/<step>")
- Either mode: rhino_set_user_text on a milestone object with
                key="checkpoint", value="<step>".
- Save a separate doc copy via rhino_save(path=".../v<step>.3dm").

When the user says "go back to before the facade", the named view +
the saved 3dm let you return without re-deriving anything.


STEP 4: BATCH USER QUESTIONS
----------------------------
Do not ping-pong on tiny choices. When you need user input, group
multiple questions into a single message:

  Before I extend the facade, please confirm:
    1. Panel size: 1.0x0.8 m (default) or another?
    2. Bay alignment: continuous strip or per-floor break?
    3. Material: anodised aluminium or precast concrete?

Wait for one combined answer rather than asking three separate turns.


STEP 5: CLOSE THE LOOP
----------------------
When the user accepts a step, persist the decision:

- rhino_set_user_text(..., key="design_decision",
                       value="2025-..._panel_1m_aluminium")
- rhino_named_view_save("decision/...")

Future turns can then re-read the decision instead of re-asking.
""".strip()


def freeform_workflow() -> str:
    """Free-form architectural authoring workflow."""
    return """
============================================================
FREE-FORM (NON-RECTILINEAR) WORKFLOW
============================================================

Use this when the brief involves doubly-curved surfaces — pavilions,
canopies, blob masses, parametric facades, organic shells. The
structured tools below replace the "drop into rhino_execute_python and
hope" pattern that wastes turns and produces invalid geometry.


STEP 1: SHAPE THE FORM
----------------------
Pick the construction method that matches the user's brief:

- Sections → skin
    rhino_skin_from_sections(section_curve_ids=[c1, c2, c3, ...])
    Standalone produces a chain of ruled surfaces between adjacent
    sections; bridge mode produces a single Brep loft.

- Single profile → revolution
    rhino_revolve(profile_id, axis, angle_degrees)            (existing)

- Two rails + cross-section
    rhino_sweep1 / rhino_sweep2                               (bridge)

- Network of curves (matrix of u + v lines)
    rhino_network_surface(curves)                             (bridge)

- Organic / soft form
    rhino_create_subd / rhino_subd_to_nurbs                   (bridge)

After construction, immediately run validation so a malformed loft
isn't carried through downstream:

    rhino_validate_brep(object_id=<surface>)


STEP 2: CHECK CURVATURE BEFORE PANELISING
-----------------------------------------
Doubly-curved surfaces fabricate at higher cost than single-curved or
planar zones. Quantify the spread first:

    rhino_surface_developable_score(surface_id, sample_u=16, sample_v=16)
        -> 0 = developable (cheap, can be unrolled flat)
           1 = strongly doubly-curved (every panel custom)

For point-by-point inspection use:
    rhino_surface_normal_at(surface_id, u, v)
    rhino_surface_curvature_at(surface_id, u, v)               (bridge)


STEP 3: PANELISE
----------------
Sample the surface on a regular UxV grid:

    rhino_uv_grid_panels(
        surface_id, count_u=12, count_v=8,
        output="mesh"|"curves"|"corners",
        layer="Panels",
    )

Then quantify per-panel cost drivers:

    rhino_panel_planarity(surface_id, count_u, count_v, tolerance=0.005)
        -> max / mean / non_planar_count + per-panel error

    rhino_panel_curvature_classify(
        surface_id, count_u, count_v,
        planar_tolerance=0.005,
        single_curve_tolerance=0.05,
    )
        -> class_counts: {planar, single_curved_u, single_curved_v,
                          synclastic, anticlastic}

Read the class_counts before reporting to the user — "32 % of panels
require double-curvature glass" is more useful than "the model is
done".


STEP 4: REFINE FORM (if costs are too high)
-------------------------------------------
If too many anticlastic / synclastic panels appear, change the form,
not the paneling resolution:

- Smooth section curves before re-skinning:
    rhino_smooth_polyline(curve_id, iterations=5, factor=0.5)
- Pull control points toward an attractor (point or curve):
    rhino_attractor_displace_points(
        point_object_ids=[...], attractor_curve_id=...,
        falloff="gaussian", strength=-0.3, max_distance=10,
    )
  Negative strength repels — useful to *flatten* a region.

Re-skin and re-classify until ``synclastic + anticlastic`` is below
the budget the user set.


STEP 5: FABRICATE
-----------------
Once the panel mix is acceptable, generate fabrication geometry:

- Slice into ribs for a waffle build:
    rhino_axis_ribs(object_id, axis_a="x", axis_b="y", count_a, count_b)
                                                                (bridge)
- Slice into UV strips for fabric / membrane fabrication:
    rhino_section_at_axis(object_id, axis="u"|"v", count=N)
- Unroll developable strips:
    rhino_unroll(object_id)                                     (bridge)


STEP 6: REPORT
--------------
End the cycle with a quantitative summary:

  - Surface developability score
  - Panel class breakdown
  - Largest planarity error
  - Total panel count and segregation by curvature class

This gives the user a concrete handle on cost and constructability,
not just a screenshot.
""".strip()


def drawing_documentation() -> str:
    """Drawing-set authoring workflow (sheets, views, title block, PDF)."""
    return """
============================================================
DRAWING DOCUMENTATION WORKFLOW
============================================================

Use this when the user wants deliverables — plan / elevation / section
sheets ready for review or printing — rather than just a 3-D model.
The tools below collapse "model -> drawing set" into call bundles.


STEP 1: SET UP HYGIENE FIRST
----------------------------
A drawing set authored against the wrong unit or scale is worse than
no drawing set. Run document hygiene checks before placing the first
sheet:

- rhino_document_summary -> verify units / tolerances / layer tree
- rhino_document_units_set("mm") if the document is not in mm yet
  (mm is the conventional unit for sheet layouts; geometry can stay
  in m as long as the viewport scale is computed accordingly)


STEP 2: CREATE THE SHEET
------------------------
- rhino_drawing_sheet_create(
      name="A-101_Plans", width_mm=420, height_mm=297,
      scale_denominator=100,
  )
  -> sheet_id; sheet rectangle on layer "Sheets::A-101_Plans"

ISO sheet sizes:
  A4: 297 x 210 | A3: 420 x 297 | A2: 594 x 420 | A1: 841 x 594


STEP 3: PLACE VIEWS (bridge only)
---------------------------------
For each view (plan, east elevation, south elevation, section A):

- rhino_drawing_view_place(
      sheet_id, object_ids=[...], view_plane="Top",
      target_origin={"x":..., "y":..., "z":0},
      viewport_scale=0.01,  # 1:100
      hidden_line=True,
  )

Multi-pass layout: pick a 2x2 grid for typical residential, 3x1 for
commercial elevations + section. Leave 30 mm gutters between views.

For sections:
- rhino_drawing_section_cut(
      sheet_id, object_ids=[...],
      plane_origin=..., plane_normal=..., target_origin=...,
  )


STEP 4: FINISH WITH TITLE BLOCK
-------------------------------
- rhino_drawing_title_block_add(
      sheet_id, project="House A",
      title="Ground Floor Plan", scale_text="1:100",
      date_iso="2026-05-03", drawn_by="...",
      sheet_no="A-101", north_arrow_angle_deg=15,
  )
  -> emits north arrow + scale bar + bottom-right table.

If multiple revisions are in flight, mark changes:
- rhino_annotation_revision_cloud(boundary_points=[...], revision_no="R2")


STEP 5: EXPORT (bridge only)
----------------------------
- rhino_drawing_export_pdf(sheet_id, path="/abs/path.pdf", dpi=300)


COMMON FAILURE MODES
--------------------
- Mixed units between document and sheet — ALWAYS verify with
  rhino_document_units_get before STEP 2.
- Calling view_place in standalone (rhino3dm) — that's bridge-only.
  Surface "unsupported" errors to the user with a hint to start Rhino.
- Forgetting north arrow rotation when the site grid is not aligned to
  true north.
""".strip()


def quantity_takeoff() -> str:
    """Quantity / BOM workflow (per-layer / per-material / per-user_text)."""
    return """
============================================================
QUANTITY TAKEOFF WORKFLOW
============================================================

Use this when the user wants numbers — area schedules, material BOMs,
window/door schedules — rather than visual deliverables. Pair with the
``bim_authoring_workflow`` so the metadata you query was attached to
each object during creation.


STEP 1: VERIFY METADATA HYGIENE
-------------------------------
A schedule is only as good as the metadata it groups by. Before any
takeoff, audit:

- rhino_document_summary -> confirm layer_tree_depth >= 2 (organised)
- rhino_layer_list       -> spot the discipline/element/state tree
- rhino_object_select(user_text={"function":"wall"}) — sanity check
  that user_text is being populated. Empty selection = no metadata.

If user_text is sparse, run a remediation pass with
``rhino_set_user_text`` BEFORE running schedules — otherwise the BOM
will be incomplete.


STEP 2: AGGREGATE
-----------------
Pick the schedule shape that matches the question:

- "How much wall by layer?" — per-layer area:
    rhino_schedule_by_layer(
        layer_filter=["Arch::Walls"],
        fields=["count","area"],
        include_sublayers=True,
    )

- "Window schedule by assembly type" — group by user_text:
    rhino_schedule_by_user_text(
        group_key="assembly_type",
        fields=["count"],
    )

- "Material BOM" — per assigned material:
    rhino_schedule_by_material(fields=["count","area","volume"])

- "Detail per object for review":
    rhino_object_quantity(
        object_ids=[...],
        fields=["area","volume","centroid","bbox"],
    )


STEP 3: EXPORT
--------------
For documents and downstream tools:

- rhino_schedule_export_csv(rows=<schedule.rows>, path="...")

The same row format works for every rhino_schedule_* response, so a
single export call wraps the chosen takeoff.


STEP 4: REPORT
--------------
Return a compact summary table to the user. For each row include the
group key + the fields they asked for. Round areas to whole m^2 / sq ft
based on the document units (use rhino_document_units_get to know
which).


CAVEATS
-------
- Standalone area/volume is only accurate for meshes; for Brep area
  the bridge mode call must be used (ScheduleHandler uses
  ``AreaMassProperties`` server-side).
- ``include_sublayers`` defaults to True; explicitly set False if the
  user wants strict per-layer counts (e.g. "exactly Arch::Walls, not
  its children").
- "Default" material in by_material rows means the object had no
  explicit material assignment — surface this fact to the user before
  reporting totals.
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
