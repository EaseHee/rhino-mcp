# 능력 매트릭스(Capability Matrix)

각 도구의 동작 모드와 그 이유.

`rhino3dm`은 OpenNURBS 파일 포맷과 일부 형상 생성자만 제공하므로 다음을 수행하지 못합니다.

- Brep/메쉬 부울 연산(union/difference/intersection).
- 서피스 로프트, 1/2-rail 스윕, 네트워크 서피스, 패치, 블렌드, 필렛, 오프셋.
- Brep/Surface로부터 메쉬 생성, 메쉬 weld/reduce/메쉬 부울.
- 뷰포트(viewport) 상호작용(named view, display mode, zoom-extent, render).
- Grasshopper.

위 기능은 Rhino 8 안의 브리지 플러그인이 필요합니다. 다음 표가 정리한 것입니다.

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
| `rhino_block_create`, `rhino_block_insert` | ✗ | ✓ |
| `rhino_material_create`, `rhino_material_assign` | ✓ | ✓ |
| `rhino_render_viewport` | ✗ | ✓ |
| `rhino_open`, `rhino_save`, `rhino_export_obj`, `rhino_export_stl` | ✓ | ✓ |
| `rhino_import`(.3dm) | ✓ | ✓ |
| `rhino_import`(STEP/IGES/DXF), `rhino_export_step/iges/dxf`, `rhino_screenshot` | ✗ | ✓ |
| `rhino_area`, `rhino_volume`(mesh 입력) | ✓ | ✓ |
| `rhino_bounding_box`, `rhino_distance` | ✓ | ✓ |
| `rhino_curvature_analysis`, `rhino_draft_angle`, `rhino_zebra`, `rhino_section`, `rhino_contour` | ✗ | ✓ |
| `rhino_view_set`, `rhino_zoom_extent`, `rhino_named_view_save`, `rhino_display_mode_set`, `rhino_turntable` | ✗ | ✓ |
| 모든 `gh_*`(22개) | ✗ | ✓ |
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

요약: standalone 약 89개, C# 브리지 활성 시 156개 이상.
