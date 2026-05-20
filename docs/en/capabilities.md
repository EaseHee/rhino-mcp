# Capability matrix

Which tools run in which mode, and why.

`rhino3dm` ships only the OpenNURBS file format and a small subset of geometry constructors.
It cannot perform:

- Boolean operations (union / difference / intersection) on Breps or meshes.
- Surface lofting, sweeping (1- or 2-rail), network surfaces, patch, blend, fillet, offset.
- Mesh generation from Breps/Surfaces; mesh welding, reduction, mesh booleans.
- Viewport interaction (named views, display modes, zoom-extents, render).
- Grasshopper.

For those, the bridge plugin running inside Rhino 8 is required.
The capability matrix below summarises this.

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
| `rhino_block_define`, `rhino_block_insert`, `rhino_block_list` (v0.3) | ✓ | ✓ |
| `rhino_block_explode`, `rhino_block_redefine` (v0.3) | ✗ | ✓ |
| `rhino_material_create`, `rhino_material_assign` | ✓ | ✓ |
| `rhino_render_viewport` | ✗ | ✓ |
| `rhino_open`, `rhino_save`, `rhino_export_obj`, `rhino_export_stl` | ✓ | ✓ |
| `rhino_import` (.3dm) | ✓ | ✓ |
| `rhino_import` (STEP/IGES/DXF), `rhino_export_step/iges/dxf`, `rhino_screenshot` | ✗ | ✓ |
| `rhino_area`, `rhino_volume` (mesh inputs) | ✓ | ✓ |
| `rhino_bounding_box`, `rhino_distance` | ✓ | ✓ |
| `rhino_curvature_analysis`, `rhino_draft_angle`, `rhino_zebra`, `rhino_section`, `rhino_contour` | ✗ | ✓ |
| `rhino_view_set`, `rhino_zoom_extent`, `rhino_named_view_save`, `rhino_display_mode_set`, `rhino_turntable` | ✗ | ✓ |
| All `gh_*` (26 tools) | ✗ | ✓ |
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
| `rhino_drawing_sheet_create`, `rhino_drawing_title_block_add` (drawing, v0.3) | ✓ | ✓ |
| `rhino_drawing_view_place`, `rhino_drawing_section_cut`, `rhino_drawing_export_pdf` (v0.3) | ✗ | ✓ |
| `rhino_schedule_by_layer/by_user_text/by_material`, `rhino_object_quantity`, `rhino_schedule_export_csv` (schedule, v0.3) | ✓ | ✓ |
| `rhino_sun_position`, `rhino_sun_path`, `rhino_shadow_project` (environment, v0.3) | ✓ | ✓ |
| `rhino_solar_exposure_estimate` (ray-cast, v0.3) | ✗ | ✓ |
| `rhino_annotation_north_arrow/scale_bar/revision_cloud/callout` (annotation, v0.3) | ✓ | ✓ |
| `rhino_annotation_dimension_style` (DimStyle table, v0.3) | ✗ | ✓ |
| `rhino_bim_metadata_set` (IFC entity + Pset tagging, v0.3) | ✓ | ✓ |
| `rhino_export_ifc`, `rhino_import_ifc`, `rhino_export_gbxml` (BIM I/O, v0.3) | ✗ | ✓ |
| `rhino_material_preset_list`, `rhino_material_preset_create` (presets, v0.3) | ✓ | ✓ |
| `rhino_environment_set` (HDRI env, v0.3) | ✗ | ✓ |
| `rhino_camera_set`, `rhino_light_add`, `rhino_render_setup`, `rhino_render_to_file`, `rhino_turntable_render` (render, v0.3) | ✗ | ✓ |
| `rhino_direct_irradiance`, `rhino_daylight_factor` (precision daylight, v0.3) | ✓ | ✓ |
| `gh_plugin_list`, `gh_components_search` (GH plugin catalog, v0.5) | ✗ | ✓ |
| `gh_data_tree_get_batch`, `gh_data_tree_set_batch` (DataTree batch, v0.5) | ✗ | ✓ |
| `rhino_bim_pset_get`, `rhino_bim_pset_set`, `rhino_bim_pset_delete` (IFC PropertySet, v0.5) | ✓ | ✓ |
| `rhino_viewport_preview` (selection-filtered capture, v0.5) | ✗ | ✓ |
| `rhino_render_queue_submit`, `rhino_render_queue_status`, `rhino_render_queue_cancel`, `rhino_render_queue_list` (render queue, v0.5) | ✗ | ✓ |
| `rhino_bridge_list_instances`, `rhino_bridge_select_instance` (multi-Rhino discovery, v0.6) | ✓ | ✓ |
| `gh_connect_many`, `gh_place_slider` (GH parity, v0.6) | ✗ | ✓ |
| `rhino_layer_set_material`, `rhino_probe_intersection`, `rhino_zoom_object`, `rhino_zoom_layer`, `rhino_viewport_image` (UX boost, v0.6) | ✗ | ✓ |
| `rhino_batch_call` (generic N-method bridge dispatch in one round-trip, v0.6.1) | ✗ | ✓ |

In numbers: ~242 standalone tools, ~245 with the C# bridge.
