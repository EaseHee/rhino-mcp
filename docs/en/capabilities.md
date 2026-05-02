# Capability matrix

Which tools run in which mode, and why.

`rhino3dm` ships only the OpenNURBS file format and a small subset of geometry constructors. It cannot perform:

- Boolean operations (union / difference / intersection) on Breps or meshes.
- Surface lofting, sweeping (1- or 2-rail), network surfaces, patch, blend, fillet, offset.
- Mesh generation from Breps/Surfaces; mesh welding, reduction, mesh booleans.
- Viewport interaction (named views, display modes, zoom-extents, render).
- Grasshopper.

For those, the bridge plugin running inside Rhino 8 is required. The capability matrix below summarises this.

| Tool                                | Standalone (rhino3dm) | Bridge (Rhino 8 + RhinoCommon/Grasshopper) |
|-------------------------------------|:---------------------:|:------------------------------------------:|
| `rhino_point` … `rhino_rebuild_curve` | ✓ | ✓ |
| `rhino_curve_length/point_at/split` | ✓ | ✓ |
| `rhino_box`, `rhino_sphere`, `rhino_cylinder` (Z-axis) | ✓ | ✓ |
| `rhino_cone`, `rhino_torus` | ✓ (mesh) | ✓ (Brep) |
| `rhino_boolean_union/difference/intersection` | ✗ | ✓ |
| `rhino_shell`, `rhino_cap_holes` | ✗ | ✓ |
| `rhino_plane_surface` … `rhino_offset_surface` (11 surface tools) | ✗ | ✓ |
| `rhino_mesh_box` | ✓ | ✓ |
| `rhino_mesh_from_*`, `rhino_weld_mesh`, `rhino_unweld_mesh`, `rhino_reduce_mesh`, mesh booleans | ✗ | ✓ |
| `rhino_move/rotate/scale/mirror/orient/array_*/selection_bbox` | ✓ | ✓ |
| `rhino_flow`, `rhino_cage_edit` | ✗ | ✓ |
| `rhino_text_dot` | ✓ | ✓ |
| `rhino_text` | ✓ (text-dot fallback) | ✓ (true text annotation) |
| `rhino_dimension_*`, `rhino_leader`, `rhino_hatch`, `rhino_clipping_plane` | ✗ | ✓ |
| `rhino_layer_create/delete/set_color`, `rhino_object_*`, `rhino_group` | ✓ | ✓ |
| `rhino_block_create`, `rhino_block_insert` | ✗ | ✓ |
| `rhino_material_create`, `rhino_material_assign` | ✓ | ✓ |
| `rhino_render_viewport` | ✗ | ✓ |
| `rhino_open`, `rhino_save`, `rhino_export_obj`, `rhino_export_stl` | ✓ | ✓ |
| `rhino_import` (.3dm) | ✓ | ✓ |
| `rhino_import` (STEP/IGES/DXF), `rhino_export_step/iges/dxf`, `rhino_screenshot` | ✗ | ✓ |
| `rhino_area`, `rhino_volume` (mesh inputs) | ✓ | ✓ |
| `rhino_bounding_box`, `rhino_distance` | ✓ | ✓ |
| `rhino_curvature_analysis`, `rhino_draft_angle`, `rhino_zebra`, `rhino_section`, `rhino_contour` | ✗ | ✓ |
| `rhino_view_set`, `rhino_zoom_extent`, `rhino_named_view_save`, `rhino_display_mode_set`, `rhino_turntable` | ✗ | ✓ |
| All `gh_*` (22 tools) | ✗ | ✓ |
| `rhino_execute_python`, `rhino_execute_csharp` (scripting) | ✗ | ✓ |
| `rhino_search_rhinoscript_functions`, `rhino_get_rhinoscript_docs` + 2 more (RS docs) | ✓ | ✓ |
| `rhino_undo`, `rhino_redo` (history) | ✗ | ✓ |
| `rhino_batch_modify` (batch operations) | ✗ | ✓ |
| `rhino_bend`, `rhino_twist`, `rhino_taper`, `rhino_flow_along_curve` (deformation) | ✗ | ✓ |
| `rhino_rebuild_surface`, `rhino_unroll`, `rhino_surface_from_points` + 2 more (NURBS) | ✗ | ✓ |
| `rhino_create_subd`, `rhino_subd_to_nurbs` (SubD) | ✗ | ✓ |
| `rhino_match_surface`, `rhino_blend_surface_edges`, `rhino_merge_surfaces` (srf match) | ✗ | ✓ |
| `rhino_dup_edge`, `rhino_dup_border`, `rhino_isocurve`, `rhino_make2d` (extraction) | ✗ | ✓ |
| `rhino_get_control_points`, `rhino_set_control_points` (control points) | ✗ | ✓ |
| `rhino_panelize_surface`, `rhino_create_uv_grid`, `rhino_panel_frames` (paneling) | ✗ | ✓ |
| `rhino_place_grid`, `rhino_stack_floors`, `rhino_scatter`, `rhino_replicate_along_curve` (composition, v0.2) | ✓ | ✓ |
| `rhino_document_units_get/set`, `rhino_tolerance_get/set`, `rhino_origin_set`, `rhino_document_settings` (document hygiene, v0.2) | ✓ | ✓ |
| `rhino_validate_brep`, `rhino_report_mesh_health`, `rhino_curve_continuity` (validation, v0.2) | ✓ | ✓ |
| `rhino_check_naked_edges` (naked-edge enumeration, v0.2) | ✗ | ✓ |
| `gh_template_list` (catalogue, v0.2) | ✓ | ✓ |
| `gh_load_template`, `gh_bind_template_parameter`, `gh_run_template` (v0.2) | ✗ | ✓ |
| `rhino_skin_from_sections`, `rhino_section_at_axis(u/v)` (freeform skin, v0.2) | ✓ | ✓ |
| `rhino_section_at_axis(x/y/z)`, `rhino_axis_ribs` (freeform skin world-axis, v0.2) | ✗ | ✓ |
| `rhino_uv_grid_panels`, `rhino_panel_planarity`, `rhino_panel_curvature_classify` (paneling, v0.2) | ✓ | ✓ |
| `rhino_surface_normal_at`, `rhino_surface_developable_score` (curvature, v0.2) | ✓ | ✓ |
| `rhino_surface_curvature_at` (true Gaussian/mean/principal, v0.2) | ✗ | ✓ |
| `rhino_attractor_displace_points`, `rhino_smooth_polyline` (fields, v0.2) | ✓ | ✓ |

In numbers: ~89 standalone tools, ~156+ with the C# bridge.
