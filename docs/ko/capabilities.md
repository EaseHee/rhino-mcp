# 능력 매트릭스(Capability Matrix)

각 도구의 동작 모드와 그 이유.

`rhino3dm`은 OpenNURBS 파일 포맷과 일부 형상 생성자만 제공 → 다음 동작 불가.

- Brep/메쉬 부울 연산(union/difference/intersection).
- 서피스 로프트, 1/2-rail 스윕, 네트워크 서피스, 패치, 블렌드, 필렛, 오프셋.
- Brep/Surface로부터 메쉬 생성, 메쉬 weld/reduce/메쉬 부울.
- 뷰포트(viewport) 상호작용(named view, display mode, zoom-extent, render).
- Grasshopper.

위 기능은 Rhino 8 내부 브리지 플러그인 필요.
정리표는 아래.

| 도구                                | Standalone(rhino3dm) | Bridge(Rhino 8 + RhinoCommon/Grasshopper) |
|-------------------------------------|:-------------------:|:-----------------------------------------:|
| `rhino_point` … `rhino_rebuild_curve` | ✓ | ✓ |
| `rhino_curve_length/point_at/split` | ✓ | ✓ |
| `rhino_box`, `rhino_sphere`, `rhino_cylinder`(Z축) | ✓ | ✓ |
| `rhino_cone`, `rhino_torus` | ✓(mesh) | ✓(Brep) |
| `rhino_boolean_union/difference/intersection` | ✗ | ✓ |
| `rhino_shell`, `rhino_cap_holes` | ✗ | ✓ |
| `rhino_plane_surface` … `rhino_offset_surface`(서피스 11개) | ✗ | ✓ |
| `rhino_mesh_box` | ✓ | ✓ |
| `rhino_mesh_from_*`, weld/unweld/reduce/메쉬 부울 | ✗ | ✓ |
| `rhino_move/rotate/scale/mirror/orient/array_*/selection_bbox` | ✓ | ✓ |
| `rhino_flow`, `rhino_cage_edit` | ✗ | ✓ |
| `rhino_text_dot` | ✓ | ✓ |
| `rhino_text` | ✓(text-dot 폴백) | ✓(true text) |
| `rhino_dimension_*`, `rhino_leader`, `rhino_hatch`, `rhino_clipping_plane` | ✗ | ✓ |
| `rhino_layer_create/delete/set_color`, `rhino_object_*`, `rhino_group` | ✓ | ✓ |
| `rhino_block_define`, `rhino_block_insert`, `rhino_block_list` (v0.3) | ✓ | ✓ |
| `rhino_block_explode`, `rhino_block_redefine` (v0.3) | ✗ | ✓ |
| `rhino_material_create`, `rhino_material_assign` | ✓ | ✓ |
| `rhino_render_viewport` | ✗ | ✓ |
| `rhino_open`, `rhino_save`, `rhino_export_obj`, `rhino_export_stl` | ✓ | ✓ |
| `rhino_import`(.3dm) | ✓ | ✓ |
| `rhino_import`(STEP/IGES/DXF), `rhino_export_step/iges/dxf`, `rhino_screenshot` | ✗ | ✓ |
| `rhino_area`, `rhino_volume`(mesh 입력) | ✓ | ✓ |
| `rhino_bounding_box`, `rhino_distance` | ✓ | ✓ |
| `rhino_curvature_analysis`, `rhino_draft_angle`, `rhino_zebra`, `rhino_section`, `rhino_contour` | ✗ | ✓ |
| `rhino_view_set`, `rhino_zoom_extent`, `rhino_named_view_save`, `rhino_display_mode_set`, `rhino_turntable` | ✗ | ✓ |
| 모든 `gh_*`(26개) | ✗ | ✓ |
| `rhino_execute_python`, `rhino_execute_csharp` (스크립트 실행) | ✗ | ✓ |
| `rhino_search_rhinoscript_functions`, `rhino_get_rhinoscript_docs` 등 4개 (RS 문서) | ✓ | ✓ |
| `rhino_undo`, `rhino_redo` (실행 취소) | ✗ | ✓ |
| `rhino_batch_modify` (일괄 수정) | ✗ | ✓ |
| `rhino_bend`, `rhino_twist`, `rhino_taper`, `rhino_flow_along_curve` (변형) | ✗ | ✓ |
| `rhino_rebuild_surface`, `rhino_unroll`, `rhino_surface_from_points` 등 5개 (NURBS) | ✗ | ✓ |
| `rhino_create_subd`, `rhino_subd_to_nurbs` (SubD) | ✗ | ✓ |
| `rhino_match_surface`, `rhino_blend_surface_edges`, `rhino_merge_surfaces` (서피스 매칭) | ✗ | ✓ |
| `rhino_dup_edge`, `rhino_dup_border`, `rhino_isocurve`, `rhino_make2d` (추출) | ✗ | ✓ |
| `rhino_get_control_points`, `rhino_set_control_points` (컨트롤 포인트) | ✗ | ✓ |
| `rhino_panelize_surface`, `rhino_create_uv_grid`, `rhino_panel_frames` (패널링) | ✗ | ✓ |
| `rhino_place_grid`, `rhino_stack_floors`, `rhino_scatter`, `rhino_replicate_along_curve` (구성, v0.2) | ✓ | ✓ |
| `rhino_document_units_get/set`, `rhino_tolerance_get/set`, `rhino_origin_set`, `rhino_document_settings` (도큐먼트 위생, v0.2) | ✓ | ✓ |
| `rhino_validate_brep`, `rhino_report_mesh_health`, `rhino_curve_continuity` (검증, v0.2) | ✓ | ✓ |
| `rhino_check_naked_edges` (naked edge 열거, v0.2) | ✗ | ✓ |
| `gh_template_list` (템플릿 카탈로그, v0.2) | ✓ | ✓ |
| `gh_load_template`, `gh_bind_template_parameter`, `gh_run_template` (v0.2) | ✗ | ✓ |
| `rhino_skin_from_sections`, `rhino_section_at_axis(u/v)` (비정형 skin, v0.2) | ✓ | ✓ |
| `rhino_section_at_axis(x/y/z)`, `rhino_axis_ribs` (월드 축 슬라이싱·waffle, v0.2) | ✗ | ✓ |
| `rhino_uv_grid_panels`, `rhino_panel_planarity`, `rhino_panel_curvature_classify` (패널 합리화, v0.2) | ✓ | ✓ |
| `rhino_surface_normal_at`, `rhino_surface_developable_score` (곡률 분석, v0.2) | ✓ | ✓ |
| `rhino_surface_curvature_at` (정확한 가우스/평균/주곡률, v0.2) | ✗ | ✓ |
| `rhino_attractor_displace_points`, `rhino_smooth_polyline` (필드 변형, v0.2) | ✓ | ✓ |
| `rhino_drawing_sheet_create`, `rhino_drawing_title_block_add` (도면 시트, v0.3) | ✓ | ✓ |
| `rhino_drawing_view_place`, `rhino_drawing_section_cut`, `rhino_drawing_export_pdf` (v0.3) | ✗ | ✓ |
| `rhino_schedule_by_layer/by_user_text/by_material`, `rhino_object_quantity`, `rhino_schedule_export_csv` (수량/스케줄, v0.3) | ✓ | ✓ |
| `rhino_sun_position`, `rhino_sun_path`, `rhino_shadow_project` (환경 분석, v0.3) | ✓ | ✓ |
| `rhino_solar_exposure_estimate` (ray-cast 일조 노출, v0.3) | ✗ | ✓ |
| `rhino_annotation_north_arrow/scale_bar/revision_cloud/callout` (주석, v0.3) | ✓ | ✓ |
| `rhino_annotation_dimension_style` (DimStyle 테이블, v0.3) | ✗ | ✓ |
| `rhino_bim_metadata_set` (IFC entity + Pset 태깅, v0.3) | ✓ | ✓ |
| `rhino_export_ifc`, `rhino_import_ifc`, `rhino_export_gbxml` (BIM I/O, v0.3) | ✗ | ✓ |
| `rhino_material_preset_list`, `rhino_material_preset_create` (물리 프리셋, v0.3) | ✓ | ✓ |
| `rhino_environment_set` (HDRI 환경, v0.3) | ✗ | ✓ |
| `rhino_camera_set`, `rhino_light_add`, `rhino_render_setup`, `rhino_render_to_file`, `rhino_turntable_render` (렌더, v0.3) | ✗ | ✓ |
| `rhino_direct_irradiance`, `rhino_daylight_factor` (정밀 주광, v0.3) | ✓ | ✓ |
| `gh_plugin_list`, `gh_components_search` (GH 플러그인 카탈로그, v0.5) | ✗ | ✓ |
| `gh_data_tree_get_batch`, `gh_data_tree_set_batch` (DataTree 일괄 접근, v0.5) | ✗ | ✓ |
| `rhino_bim_pset_get`, `rhino_bim_pset_set`, `rhino_bim_pset_delete` (IFC PropertySet 단위 읽기/쓰기/삭제, v0.5) | ✓ | ✓ |
| `rhino_viewport_preview` (선택/레이어 필터 부분 캡처, v0.5) | ✗ | ✓ |
| `rhino_render_queue_submit`, `rhino_render_queue_status`, `rhino_render_queue_cancel`, `rhino_render_queue_list` (렌더 큐, v0.5) | ✗ | ✓ |
| `rhino_bridge_list_instances`, `rhino_bridge_select_instance` (다중 Rhino 발견, v0.6) | ✓ | ✓ |
| `gh_connect_many`, `gh_place_slider` (GH 보강, v0.6) | ✗ | ✓ |
| `rhino_layer_set_material`, `rhino_probe_intersection`, `rhino_zoom_object`, `rhino_zoom_layer`, `rhino_viewport_image` (UX 보강, v0.6) | ✗ | ✓ |
| `rhino_batch_call` (한 라운드트립으로 N개 bridge method 디스패치, v0.6.1) | ✗ | ✓ |

요약: standalone 약 242개, C# 브리지 활성 시 245개.
