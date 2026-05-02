# 도구 레퍼런스(Tools Reference)

모든 도구는 다음 형태의 구조화된 페이로드(payload)를 반환합니다.

```json
{
  "summary": { "...도구별...": "..." },
  "text":    "사람이 읽을 한 줄 요약"
}
```

오류는 `ToolError`로 발생되며 `category`, `message`, `hint`, `details`를 포함합니다.

“capability” 컬럼이 등록 모드를 나타냅니다.

- **standalone** — 인-프로세스 `rhino3dm.File3dm`에서 실행
- **bridge** — Rhino 측 브리지가 도달 가능할 때만 등록
- **both** — 두 모드 모두 동작(본문이 분기)

## 형상(Geometry, 생성)

| 도구                          | Capability | 입력 |
|-------------------------------|------------|------|
| `rhino_point`                 | both       | `point: Point3d`, `doc_id`, `layer`, `name` |
| `rhino_line`                  | both       | `start`, `end` |
| `rhino_polyline`              | both       | `points: list[Point3d]`, `closed` |
| `rhino_arc`                   | both       | `center`, `radius`, `angle_degrees`(0–360) |
| `rhino_circle`                | both       | `center`, `radius`, 선택 `plane` |
| `rhino_ellipse`               | both       | `center`, `radius_x`, `radius_y` |
| `rhino_rectangle`             | both       | `corner`, `width`, `height` |
| `rhino_polygon`               | both       | `center`, `radius`, `sides`, `inscribed` |
| `rhino_helix`                 | both       | `center`, `radius`, `pitch`, `turns`, `points_per_turn` |
| `rhino_spiral`                | both       | `center`, `start_radius`, `end_radius`, `pitch`, `turns` |
| `rhino_nurbs_curve`           | both       | `control_points`(≥ degree+1), `degree` |
| `rhino_interpolate_curve`     | both       | `points`, `degree` |
| `rhino_rebuild_curve`         | both       | `object_id`, `point_count`, `degree` |

### 커브(Curves, 질의)

| 도구                     | Capability | 입력 |
|--------------------------|------------|------|
| `rhino_curve_length`     | both       | `object_id` |
| `rhino_curve_point_at`   | both       | `object_id`, `t`(Domain 내부) |
| `rhino_curve_split`      | both       | `object_id`, `parameters: list[float]` |

## 솔리드(Solids)

| 도구                          | Capability | 입력 |
|-------------------------------|------------|------|
| `rhino_box`                   | both       | `corner`, `size_x/y/z` |
| `rhino_sphere`                | both       | `center`, `radius` |
| `rhino_cylinder`              | both       | `base_center`, `radius`, `height`, `axis`(standalone은 Z만), `capped` |
| `rhino_cone`                  | both       | `base_center`, `radius`, `height`(standalone은 mesh) |
| `rhino_torus`                 | both       | `center`, `major_radius`, `minor_radius`(standalone은 mesh) |
| `rhino_boolean_union`         | bridge     | `a_ids`, `b_ids` |
| `rhino_boolean_difference`    | bridge     | `a_ids`, `b_ids` |
| `rhino_boolean_intersection`  | bridge     | `a_ids`, `b_ids` |
| `rhino_shell`                 | bridge     | `object_id`, `thickness`, `open_face_indices` |
| `rhino_cap_holes`             | bridge     | `object_id` |

## 서피스(Surfaces, 브리지 전용)

`rhino_plane_surface`, `rhino_extrude`, `rhino_revolve`, `rhino_loft`,
`rhino_sweep1`, `rhino_sweep2`, `rhino_network_surface`, `rhino_patch`,
`rhino_blend_surface`, `rhino_fillet_surface`, `rhino_offset_surface`.

## 메쉬(Mesh)

| 도구                              | Capability | 입력 |
|-----------------------------------|------------|------|
| `rhino_mesh_box`                  | both       | `corner`, `size_x/y/z`, `divisions_x/y/z` |
| `rhino_mesh_from_surface`         | bridge     | `object_id`, `quality` |
| `rhino_mesh_from_brep`            | bridge     | `object_id`, `quality` |
| `rhino_weld_mesh`                 | bridge     | `object_id` |
| `rhino_unweld_mesh`               | bridge     | `object_id` |
| `rhino_reduce_mesh`               | bridge     | `object_id`, `target_face_count` |
| `rhino_mesh_boolean_union`        | bridge     | `a_ids`, `b_ids` |
| `rhino_mesh_boolean_difference`   | bridge     | `a_ids`, `b_ids` |

## 변환(Transforms)

| 도구                         | Capability | 입력 |
|------------------------------|------------|------|
| `rhino_move`                 | both       | `object_ids`, `translation`, `make_copy` |
| `rhino_rotate`               | both       | `object_ids`, `center`, `axis`, `angle_degrees`, `make_copy` |
| `rhino_scale`                | both       | `object_ids`, `center`, `factor_x/y/z`, `make_copy` |
| `rhino_mirror`               | both       | `object_ids`, `plane`, `make_copy` |
| `rhino_array_linear`         | both       | `object_ids`, `direction`, `spacing`, `count` |
| `rhino_array_polar`          | both       | `object_ids`, `center`, `axis`, `count`, `total_angle_degrees` |
| `rhino_array_rectangular`    | both       | `object_ids`, `count_x/y/z`, `spacing_x/y/z` |
| `rhino_orient`               | both       | `object_ids`, `from_plane`, `to_plane`, `make_copy` |
| `rhino_flow`                 | bridge     | `object_ids`, `base_curve_id`, `target_curve_id` |
| `rhino_cage_edit`            | bridge     | `object_ids`, `cage_object_id` |
| `rhino_selection_bbox`       | both       | `doc_id` |

## 주석(Annotation)

| 도구                          | Capability  |
|-------------------------------|-------------|
| `rhino_text_dot`              | both        |
| `rhino_text`                  | both(standalone은 text-dot 폴백) |
| `rhino_dimension_linear`      | bridge      |
| `rhino_dimension_aligned`     | bridge      |
| `rhino_dimension_angular`     | bridge      |
| `rhino_leader`                | bridge      |
| `rhino_hatch`                 | bridge      |
| `rhino_clipping_plane`        | bridge      |

## 레이어(Layer) / 객체(Object)

| 도구                            | Capability |
|---------------------------------|------------|
| `rhino_layer_create`            | both       |
| `rhino_layer_delete`            | both       |
| `rhino_layer_set_color`         | both       |
| `rhino_object_move_to_layer`    | both       |
| `rhino_object_select`           | both       |
| `rhino_object_delete`           | both       |
| `rhino_group`                   | both       |
| `rhino_block_create`            | bridge     |
| `rhino_block_insert`            | bridge     |

## 머티리얼(Material)

| 도구                          | Capability |
|-------------------------------|------------|
| `rhino_material_create`       | both       |
| `rhino_material_assign`       | both       |
| `rhino_render_viewport`       | bridge     |

## 파일 입출력(File I/O)

| 도구                          | Capability |
|-------------------------------|------------|
| `rhino_open`                  | both       |
| `rhino_save`                  | both       |
| `rhino_export_obj`            | both       |
| `rhino_export_stl`            | both       |
| `rhino_import`                | both(standalone은 `.3dm` 전용) |
| `rhino_export_step`           | bridge     |
| `rhino_export_iges`           | bridge     |
| `rhino_export_dxf`            | bridge     |
| `rhino_screenshot`            | bridge     |

## 분석(Analysis)

| 도구                          | Capability |
|-------------------------------|------------|
| `rhino_area`                  | both(standalone은 mesh만) |
| `rhino_volume`                | both(standalone은 mesh만) |
| `rhino_bounding_box`          | both       |
| `rhino_distance`              | both       |
| `rhino_curvature_analysis`    | bridge     |
| `rhino_draft_angle`           | bridge     |
| `rhino_zebra`                 | bridge     |
| `rhino_section`               | bridge     |
| `rhino_contour`               | bridge     |

## 디스플레이(Display, 브리지 전용)

`rhino_view_set`, `rhino_zoom_extent`, `rhino_named_view_save`, `rhino_display_mode_set`, `rhino_turntable`.

## Grasshopper(브리지 전용)

| 도구                       | 입력(요약) |
|----------------------------|-----------|
| `gh_open_file`             | `path` |
| `gh_save_file`             | `path`(없으면 현재 파일) |
| `gh_new_canvas`            | `name` |
| `gh_run`                   | `new_solution: bool` |
| `gh_reset`                 | — |
| `gh_preview_toggle`        | `component_ids?`, `enabled` |
| `gh_bake_to_rhino`         | `component_ids`, `layer?` |
| `gh_add_component`         | `name`, `x`, `y` |
| `gh_connect_components`    | `from_component`, `from_output`, `to_component`, `to_input` |
| `gh_delete_component`      | `component_id` |
| `gh_component_list`        | `filter?` |
| `gh_cluster_create`        | `component_ids`, `name` |
| `gh_cluster_expand`        | `cluster_id` |
| `gh_get_parameter`         | `component_id`, `output` |
| `gh_set_parameter`         | `component_id`, `input`, `value: GhParameterValue` |
| `gh_set_slider`            | `component_id`, `value: float` |
| `gh_set_panel`             | `component_id`, `text` |
| `gh_set_toggle`            | `component_id`, `value: bool` |
| `gh_data_tree_get`         | `component_id`, `output` |
| `gh_data_tree_set`         | `component_id`, `input`, `branches: list[(path, values)]` |
