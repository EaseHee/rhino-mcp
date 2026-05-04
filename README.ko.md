<div align="center">

<img src="https://raw.githubusercontent.com/EaseHee/rhino-mcp/refs/heads/main/assets/rhino-mcp.png" alt="rhino-logo"/>

# rhino-mcp

**McNeel Rhino 8과 Grasshopper를 Model Context Protocol(MCP)을 통해 Claude에서 제어합니다.**

![PyPI](https://img.shields.io/pypi/v/rhino3dm-mcp)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Rhino](https://img.shields.io/badge/Rhino-8-red)
![MCP](https://img.shields.io/badge/MCP-compatible-purple)
![Platform](https://img.shields.io/badge/platform-windows%20%7C%20macos%20%7C%20linux-lightgrey)

[English](./README.md) · [한국어](./README.ko.md)

</div>

---

## 개요(Overview)

`rhino-mcp`는 Claude(또는 임의의 MCP 클라이언트)가 자연어 도구 호출만으로 Rhino 8을 조작할 수 있도록 만드는 Model Context Protocol 서버입니다. 형상 생성, 레이어·머티리얼·블록 관리, Grasshopper 베이크, STEP/IGES/STL/OBJ 내보내기 등을 모두 지원합니다. 두 가지 실행 모드를 제공합니다.

- **Standalone(독립 실행)**: [`rhino3dm`](https://github.com/mcneel/rhino3dm) 라이브러리로 헤드리스 `.3dm` 파일 직접 작성. Rhino 미설치 환경에서도 동작, **약 126개 도구** 노출(v0.3 기준 — 구성 단축, 도큐먼트 위생, 지오메트리 검증, GH 템플릿 카탈로그, 비정형 skin / 패널 합리화 / 곡률 / 필드, **도면 시트 + 표제란, 면적 / 자재 산출, 블록 정의, 일조 위치 + 그림자 투영, IFC 메타 태깅, 19종 물리 머티리얼 프리셋, BRE 주광율 + Bird DNI 청천공 모델** 포함).
- **Bridge(브리지)**: Rhino 8 안에서 C# 브리지 플러그인 로드 시 모든 호출(부울 연산, 로프트, 스윕, 뷰포트, 렌더, 스크립트 실행, 변형, NURBS 편집, SubD, 패널링, 정확한 가우스 곡률을 포함한 비정형 분석, **다중 뷰 도면 배치 / 단면 / PDF 내보내기, AreaMassProperties 기반 Brep 면적 산출, 블록 폭파·재정의, ray-cast 일조 노출, IFC / gbXML 입출력, HDRI 환경, 카메라 / 라이트 / 렌더 / 턴테이블 자동화**, 모든 Grasshopper 명령 + 템플릿)을 라이브 Rhino로 투명 전달. **약 223개 도구** 활성.

## 기능(Features)

- **전체 지오메트리 카탈로그(geometry catalogue)** — 점·선·폴리라인(polyline)·아크(arc)·원(circle)·타원(ellipse)·다각형(polygon)·헬릭스(helix)·NURBS 커브(curve)·리빌드(rebuild).
- **솔리드(solid) / 메쉬(mesh)** — 박스·구·실린더·콘·토러스(torus)·메쉬 박스. 부울 / 스윕 / 로프트 / 필렛(fillet)은 브리지에서 사용.
- **변환(transform)** — 이동·회전·스케일·미러(mirror)·평면-평면 오리엔트(orient)·선형/방사형/직사각 어레이(array).
- **스크립트 실행(scripting)** — 라이브 Rhino에서 임의의 RhinoScript Python(IronPython) 또는 RhinoCommon C#(Roslyn) 코드 실행. 내장 RhinoScript API 문서 검색(899개 함수).
- **고급 모델링(advanced modeling)** — 변형(bend/twist/taper/flow), NURBS 편집(rebuild/unroll/evaluate), SubD, 서피스 매칭, 추출(dup edge/border/isocurve/Make2D), 컨트롤 포인트, 패널링.
- **도면 세트(drawing set)** — standalone에서 시트/표제란/북쪽화살/스케일바 작성. 브리지에서 다중 뷰 배치, 단면 추출, PDF 내보내기까지.
- **수량 / 스케줄(quantity & schedule)** — 레이어/머티리얼/`user_text` 기준 집계 + CSV 내보내기. 브리지는 `AreaMassProperties`/`VolumeMassProperties` 기반 정확한 Brep 면적·체적 측정.
- **블록 / 인스턴스 재사용(blocks)** — standalone에서 정의/삽입/조회. 브리지에서 폭파·재정의로 일관된 컴포넌트 편집.
- **환경 분석(environment)** — NOAA SPA 근사로 일조 위치 + 월별 sun-path + 그림자 투영. 브리지에서 ray-cast 기반 일조 노출 추정. Bird 청천공 DNI(Kasten-Young air mass + Linke turbidity) + BRE 단순 주광율(daylight factor) 보강.
- **BIM 입출력(bim-io)** — IFC2x3 / IFC4 / IFC4x3 import & export, gbXML export, IFC PropertySet 메타 태깅(`user_text` 라운드트립).
- **머티리얼 프리셋 + HDRI(materials+)** — 19종 물리 프리셋(콘크리트 / 벽돌 / 강철 / 알루미늄 / 유리 / 목재 / 석재 / 플라스터 / 직물 / 조경) 카테고리별 분류. 브리지에서 HDRI 환경 + IOR 포함 PBR 적용.
- **렌더 자동화(render)** — 카메라 / 라이트 / 렌더 엔진 설정, 파일 출력, 매개변수 카메라 궤도(turntable) 시퀀스(브리지 전용).
- **실행 취소(undo/redo) / 일괄 작업(batch)** — 모든 브리지 작업에 undo 레코드 적용. 일괄 수정으로 다수 객체를 단일 호출로 변경.
- **레이어(layer)·머티리얼(material)·블록(block)·그룹(group)** — 도큐먼트 속성을 완전 제어.
- **파일 입출력(File I/O)** — `.3dm` 열기/저장, OBJ/STL은 standalone에서, STEP/IGES/DXF·스크린샷은 브리지에서.
- **인라인 base64 스크린샷** — `rhino_screenshot(as_base64=True)`가 PNG 데이터를 응답에 직접 포함해 LLM이 즉시 시각 검증 가능.
- **풍부한 객체 선택 필터** — `rhino_object_select`가 이름 glob 패턴, 레이어, RGB 색상, 객체 타입, user-text 키/값 조합으로 필터.
- **대량 조회 페이지네이션** — `rhino_list_objects` 응답에 `pagination: {total, offset, limit, returned, has_more}` 블록 포함, 큰 도면에서도 컨텍스트 폭발 없음.
- **장면 구성 단축 도구**(v0.2) — `rhino_place_grid`, `rhino_stack_floors`, `rhino_scatter`, `rhino_replicate_along_curve`로 "loop + transform" 패턴을 단일 호출로 압축.
- **도큐먼트 위생 도구**(v0.2) — 단위·공차·기준점을 직접 조회/설정(`rhino_document_units_*`, `rhino_tolerance_*`, `rhino_origin_set`). `rhino_document_summary`가 이를 노출하여 LLM이 지오메트리 호출 전에 스케일을 검증할 수 있음.
- **지오메트리 검증**(v0.2) — `rhino_validate_brep`, `rhino_report_mesh_health`, `rhino_curve_continuity`, 그리고 브리지 전용 `rhino_check_naked_edges`로 부울/내보내기 전 토폴로지 진단.
- **Grasshopper 템플릿 로더**(v0.2) — `gh_template_list`로 사전 와이어링된 템플릿 카탈로그 조회. `gh_load_template`/`gh_bind_template_parameter`/`gh_run_template`(브리지)로 로드·파라미터 바인딩·베이크.
- **비정형 건축 설계 툴킷** — `rhino_skin_from_sections`, `rhino_uv_grid_panels`, `rhino_panel_planarity`, `rhino_panel_curvature_classify`, `rhino_surface_developable_score`, `rhino_attractor_displace_points`, `rhino_smooth_polyline`. 브리지 모드에서는 정확한 가우스/평균/주곡률, 월드 축 슬라이싱, waffle ribs까지 추가.
- **LLM 전략 가이드 프롬프트** — `general_strategy`, `rhinoscript_workflow`, `viewport_workflow`, `parametric_workflow`, `bim_authoring_workflow`, `design_dialogue_workflow`, `freeform_workflow` 7개 `@mcp.prompt()`로 도구 선택 가이드, hallucination 방지, 사용자-인-더-루프 디자인 결정.
- **비동기 도구** — read-only 쿼리 도구가 `async def`로 노출되어 동시 브리지 호출이 MCP 전송을 막지 않음.
- **견고한 연결 계층** — named pipe / Unix socket / TCP 위 JSON-RPC. `MSG_PEEK` liveness probe와 jitter 적용 지수 백오프 재연결.
- **Grasshopper 자동화** — `.gh` 열기, 컴포넌트(component) 추가·연결·삭제, 슬라이더(slider)/패널(panel)/토글(toggle) 설정, 솔루션 실행, 베이크(bake), DataTree 읽기.
- **3가지 전송 방식(transport)** — stdio(Claude Desktop), Streamable HTTP, Docker/TCP.
- **능력 기반 등록(capability-aware registration)** — 브리지 전용 도구는 브리지가 없을 때 아예 등록되지 않습니다. stub 함수는 절대 만들지 않습니다.
- **실행 가능한(actionable) 에러** — 모든 실패에 카테고리·해결 힌트·세부 정보가 포함됩니다.

## 아키텍처(Architecture)

```
┌──────────────┐     stdio | HTTP      ┌────────────────┐
│  Claude /    │ ◀──────────────────▶ │   rhino-mcp    │
│  MCP client  │                      │   (Python)     │
└──────────────┘                      └─────┬──────────┘
                                            │
                              JSON-RPC 2.0  │   (named pipe / unix socket / TCP)
                                            │
                                  ┌──────────▼──────────┐
                                  │  rhino-mcp.rhp │
                                  │  (Rhino 8 C# 플러그인) │
                                  │  ─────────────────  │
                                  │  RhinoCommon        │
                                  │  Grasshopper        │
                                  └─────────────────────┘
```

**Standalone** 모드에서는 우측이 인-프로세스(in-process) `rhino3dm.File3dm`로 대체되며, 브리지 전용 도구는 등록되지 않습니다.

## 요구 사항(Requirements)

- Python 3.11 이상
- `rhino3dm >= 8.9`, `mcp[cli] >= 1.2`, `pydantic >= 2.6` (자동 설치)
- 선택: McNeel Rhino 8 — 브리지 모드에서만 필요
- 선택: Windows에서 named pipe 사용 시 `pywin32`

## 설치(Installation)

### uv 사용(권장)

```bash
uv tool install rhino-mcp
# 또는 체크아웃 후:
uv sync && uv run rhino-mcp
```

### pip 사용

```bash
pip install rhino3dm-mcp
rhino-mcp --version
```

### Claude Desktop 자동 등록

패키지 설치 후 `claude_desktop_config.json` 수동 편집 대신 단일 명령으로 등록 가능:

```bash
rhino-mcp install                         # 런처 자동 감지(uvx / rhino-mcp / python)
rhino-mcp install --mode bridge           # env 블록에 bridge 강제 모드 기록
rhino-mcp install --force                 # 동일 이름 항목 덮어쓰기
rhino-mcp install --dry-run               # 파일 변경 없이 JSON 미리보기
```

기존 설정 파일은 타임스탬프 `.bak.*` 백업 후 저장. 동일 플래그 재실행 시 no-op (idempotent). 변경 적용 위해 Claude Desktop 재시작 필요.

### Docker

```bash
docker compose -f docker/docker-compose.yml up --build
```

컨테이너는 Streamable HTTP 전송으로 TCP `:8765`에서 서비스합니다.

## 서버 실행(Running the server)

`rhino-mcp`는 보통 MCP 클라이언트(Claude Desktop / Cursor / claude.ai 커넥터)가 config에 등록된 `command + args`로 자동 실행합니다. 디버깅 목적으로는 직접 실행도 가능합니다.

### 실행 모드

| 사용 사례                                | 명령어                                                                            |
|------------------------------------------|----------------------------------------------------------------------------------|
| Stdio (Claude Desktop 기본)              | `uvx rhino3dm-mcp` *또는* `rhino-mcp`                                           |
| Streamable HTTP (로컬 / Cursor)          | `rhino-mcp --transport http --host 127.0.0.1 --port 8765`                        |
| Streamable HTTP (claude.ai 커넥터)       | `rhino-mcp --transport http --host 0.0.0.0 --port 8765 --allow-external --stateless` |
| Docker (HTTP `:8765`)                    | `docker compose -f docker/docker-compose.yml up --build`                         |
| Standalone 강제 (Rhino 불필요)           | `RHINO_MCP_FORCE_MODE=standalone rhino-mcp`                                      |
| Bridge 강제 (Rhino 미동작 시 즉시 실패)   | `RHINO_MCP_FORCE_MODE=bridge rhino-mcp`                                          |
| Bridge 강제 + HTTP fallback              | `RHINO_MCP_FORCE_MODE=bridge RHINO_MCP_BRIDGE_OPTIONAL=1 rhino-mcp --transport http` |
| 모든 CLI 플래그 보기                     | `rhino-mcp --help`                                                                |

HTTP 엔드포인트는 `http://<host>:<port>/mcp`. `--allow-external`은 ngrok/Cloudflare Tunnel 등으로 외부 노출할 때만 사용하세요(DNS rebinding 보호 비활성화).

### Claude Desktop (stdio)

`claude_desktop_config.json` 위치:

| OS      | 경로                                                                                    |
|---------|----------------------------------------------------------------------------------------|
| macOS   | `~/Library/Application Support/Claude/claude_desktop_config.json`                       |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json`                                           |
| Linux   | `~/.config/Claude/claude_desktop_config.json`                                           |

`mcpServers` 아래에 다음 항목을 추가:

```json
{
  "mcpServers": {
    "rhino-mcp": {
      "command": "uvx",
      "args": ["rhino3dm-mcp"],
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

체크아웃에서 직접 실행하려면 `command`를 `uv`로 바꿉니다:

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

Claude Desktop을 재시작하면 도구 팔레트와 3개 전략 프롬프트(`general_strategy`, `rhinoscript_workflow`, `viewport_workflow`)가 노출됩니다.

### Cursor IDE

Cursor는 `~/.cursor/mcp.json`(전역) 또는 `<project>/.cursor/mcp.json`(프로젝트별)을 읽습니다:

```json
{
  "mcpServers": {
    "rhino-mcp": {
      "command": "uvx",
      "args": ["rhino3dm-mcp"],
      "env": { "RHINO_MCP_FORCE_MODE": "bridge" }
    }
  }
}
```

### claude.ai 원격 커넥터 (Streamable HTTP)

1. 외부 접근 허용 옵션으로 서버 실행:

   ```bash
   rhino-mcp --transport http --host 0.0.0.0 --port 8765 --allow-external --stateless
   ```

2. 터널링(예: `ngrok http 8765`) 후 공개 HTTPS URL 확보.

3. claude.ai → 설정 → Connectors → *Add custom connector*에서 URL을 `https://<터널>/mcp`로 등록.

### 일반 stdio MCP 클라이언트

mcp-inspector, Continue, Claude Code 등 서브프로세스를 spawn할 수 있는 모든 MCP 호환 클라이언트에서 동작 — `uvx rhino3dm-mcp` 또는 설치된 `rhino-mcp` 엔트리포인트 경로 지정, 아래 환경 변수 표 참고.

### Rhino 측 C# 브리지 플러그인 (권장)

130개 이상의 도구를 모두 사용하려면 C# 플러그인을 빌드해 설치합니다. 헬퍼 스크립트가 `dotnet build`를 감싸고 설치 위치를 검증합니다:

```bash
./scripts/build-plugin.sh             # debug 빌드 + 설치
./scripts/build-plugin.sh --release   # release 빌드
./scripts/build-plugin.sh --clean     # 클린 후 재빌드

# 또는 직접:
dotnet build rhino_plugin/csharp/RhinoMCPPlugin.csproj -c Release
```

PostBuild 단계에서 `.rhp`가 자동 복사되는 위치:

| OS      | 경로                                                                                  |
|---------|--------------------------------------------------------------------------------------|
| macOS   | `/Applications/Rhino 8.app/Contents/PlugIns/rhino-mcp.rhp`                       |
| Windows | `%APPDATA%/McNeel/Rhinoceros/8.0/Plug-ins/rhino-mcp/rhino-mcp.rhp`           |

Rhino 8을 재시작하면 브리지가 자동으로 시작합니다(기본 TCP `:4242`). `rhino-mcp`를 재시작하거나 `RHINO_MCP_FORCE_MODE=bridge`를 설정하면 브리지 전용 도구가 활성화됩니다.


## 빠른 시작(Quick Start)

```python
# Claude Desktop에 rhino-mcp가 설정된 상태에서 Claude에게:
#   "원점에 반지름 10인 구를 만들고 /tmp/demo.3dm으로 저장해."
# 내부적으로 Claude가 rhino_sphere → rhino_save 순으로 도구를 호출합니다.
```

### 전략 프롬프트(strategy prompts)

3개 MCP 프롬프트가 자동으로 등록되어 클라이언트의 프롬프트 선택 UI에 노출됩니다:

| 프롬프트                | 사용 시점                                                                                            |
|-------------------------|-----------------------------------------------------------------------------------------------------|
| `general_strategy`      | 도큐먼트 파악 → 도구 선택 의사결정 트리 → 베스트 프랙티스(이름 부여, 배치, 레이어, undo, 검증).      |
| `rhinoscript_workflow`  | `rhino_execute_python` 호출 **전** 반드시 따라야 할 워크플로(API hallucination 방지).                |
| `viewport_workflow`     | `rhino_zoom_extent` + `rhino_screenshot(as_base64=True)`로 시각 검증하는 패턴.                       |

긴 세션에서는 "general_strategy 프롬프트를 먼저 보고 시작해"라고 지시하면 도구 선택 품질이 크게 향상됩니다.

### base64 스크린샷으로 시각 검증

```text
"'Demo' 레이어에 5x5x5 박스를 만들고, 1280x720 base64 스크린샷을 찍어 결과를 확인해."
```

Claude가 `rhino_box → rhino_zoom_extent → rhino_screenshot(as_base64=True)`을 호출하고 응답의 `image_base64` 필드에서 PNG를 직접 읽어 다음 턴에 활용합니다.

### 페이지네이션 & 풍부한 필터링

```text
"'Walls' 레이어의 커브 50개만 먼저 보여주고, 그 다음 'Structure' 레이어에서 이름이 'Pillar_*'인 객체를 모두 선택해."
```

`rhino_list_objects`는 `pagination` 블록을 반환합니다. `has_more`가 `false`가 될 때까지 `offset += pagination.returned`로 순회하세요. `rhino_object_select`는 `name_pattern`, `layer`, `color`, `object_type`, `user_text`, `deselect_first`를 받습니다.

쉘에서 standalone 스모크(smoke) 실행:

```bash
RHINO_MCP_FORCE_MODE=standalone uv run python - <<'PY'
import asyncio
from rhino_mcp.server import build_server
from rhino_mcp.utils.registry import Mode

mcp, count = build_server(runtime_mode=Mode.STANDALONE, bridge_client=None)
print(f"등록된 도구: {count}")
sphere = asyncio.run(
    mcp._tool_manager._tools["rhino_sphere"].run(
        {"args": {"center": {"x": 0, "y": 0, "z": 0}, "radius": 10.0}}
    )
)
print(sphere)
PY
```

## 도구 레퍼런스(Tools Reference) — 요약

| 카테고리       | Standalone | + Bridge  | 주요 도구 |
|----------------|------------|-----------|-----------|
| Geometry       | 13         | 13        | `rhino_point`, `rhino_circle`, `rhino_helix`, `rhino_nurbs_curve` |
| Curves         | 3          | 3         | `rhino_curve_length`, `rhino_curve_point_at`, `rhino_curve_split` |
| Solids         | 5          | 10        | `rhino_box`, `rhino_sphere`, `rhino_boolean_union`(브리지) |
| Surfaces       | 0          | 11        | `rhino_loft`, `rhino_sweep1`, `rhino_revolve` |
| Mesh           | 1          | 8         | `rhino_mesh_box`, `rhino_weld_mesh`(브리지) |
| Transform      | 9          | 11        | `rhino_array_polar`, `rhino_orient`, `rhino_flow`(브리지) |
| Annotation     | 2          | 8         | `rhino_text_dot`, `rhino_dimension_linear`(브리지) |
| Layer / Object | 6          | 8         | `rhino_layer_create`, `rhino_block_insert`(브리지) |
| Material       | 2          | 3         | `rhino_material_create`, `rhino_render_viewport`(브리지) |
| File I/O       | 5          | 9         | `rhino_save`, `rhino_export_step`(브리지) |
| Analysis       | 4          | 9         | `rhino_volume`, `rhino_zebra`(브리지) |
| Display        | 0          | 5         | `rhino_zoom_extent`, `rhino_named_view_save` |
| Grasshopper    | 0          | 22        | `gh_set_slider`, `gh_bake_to_rhino`, `gh_data_tree_get` |
| **Drawing**    | **2**      | **5**     | **`rhino_drawing_sheet_create`**, **`rhino_drawing_title_block_add`**, **`rhino_drawing_view_place`**(브리지) |
| **Schedule**   | **5**      | **5**     | **`rhino_schedule_by_layer`**, **`rhino_schedule_by_user_text`**, **`rhino_object_quantity`** |
| **Blocks**     | **3**      | **5**     | **`rhino_block_define`**, **`rhino_block_insert`**, **`rhino_block_explode`**(브리지) |
| **Environment**| **3**      | **4**     | **`rhino_sun_position`**, **`rhino_sun_path`**, **`rhino_shadow_project`** |
| **Freeform**   | **8**      | **11**    | **`rhino_skin_from_sections`**, **`rhino_panel_curvature_classify`**, **`rhino_attractor_displace_points`** |
| **BIM I/O**    | **1**      | **4**     | **`rhino_bim_metadata_set`**, **`rhino_export_ifc`**(브리지), **`rhino_import_ifc`**(브리지), **`rhino_export_gbxml`**(브리지) |
| **Materials+** | **2**      | **3**     | **`rhino_material_preset_list`**, **`rhino_material_preset_create`**, **`rhino_environment_set`**(브리지) |
| **Render**     | 0          | **5**     | **`rhino_camera_set`**, **`rhino_light_add`**, **`rhino_render_setup`**, **`rhino_render_to_file`**, **`rhino_turntable_render`** |
| **Daylight**   | **2**      | **2**     | **`rhino_direct_irradiance`**, **`rhino_daylight_factor`** |

자세한 시그니처는 [docs/ko/tools-reference.md](docs/ko/tools-reference.md)를 참고하세요.

## Grasshopper 연동

```text
1. Rhino 8 실행 → Grasshopper 열기 → `.gh` 정의 로드.
2. C# 브리지 플러그인(`rhino-mcp.rhp`)이 Rhino에 로드된 상태인지 확인.
3. `RHINO_MCP_FORCE_MODE=bridge` 설정 후 rhino-mcp 재시작.
4. Claude에 요청:
   - "/work/wing.gh를 열고 'span' 슬라이더를 12.5로 설정한 뒤 실행하고 'Wing' 레이어로 베이크해."
   - "'Voronoi' 컴포넌트의 출력을 DataTree로 읽어줘."
```

캔버스(canvas)/컴포넌트/클러스터(cluster) 사용 패턴은 [docs/ko/grasshopper-guide.md](docs/ko/grasshopper-guide.md)에 정리되어 있습니다.

## 환경 설정(Configuration)

모든 옵션은 환경 변수로 제어합니다. 가능한 경우 CLI 플래그가 환경 변수를 덮어씁니다.

| 변수                                | 기본값                | 설명 |
|-------------------------------------|----------------------|------|
| `RHINO_MCP_TRANSPORT`               | `stdio`              | `stdio` 또는 `http`(Streamable HTTP) |
| `RHINO_MCP_FORCE_MODE`              | _(자동)_             | `standalone` 또는 `bridge` 강제 |
| `RHINO_MCP_BRIDGE_OPTIONAL`         | `0`                  | `1`이면 `RHINO_MCP_FORCE_MODE=bridge` 상태에서도 브리지 미연결 시 standalone으로 fallback (HTTP 커넥터 권장). |
| `RHINO_MCP_TRANSPORT_KIND`          | _(자동)_             | 브리지 전송 선택: `pipe` / `unix` / `tcp` |
| `RHINO_HOST`, `RHINO_PORT`          | `localhost:4242`     | TCP 전송 엔드포인트 |
| `RHINO_MCP_PIPE`                    | `rhino_mcp`          | Windows named pipe 이름 |
| `RHINO_MCP_SOCKET`                  | _(XDG runtime)_      | Unix socket 경로 오버라이드 |
| `RHINO_MCP_BRIDGE_TIMEOUT`          | `1` (auto), `5` (강제) | 브리지 ping 대기 초 |
| `RHINO_MCP_RECONNECT_RETRIES`       | `1`                  | transport 일시 실패 후 재연결 시도 횟수 |
| `RHINO_MCP_RECONNECT_BASE_DELAY`    | `0.5`                | 지수 백오프 기준 시간(초) |
| `RHINO_MCP_RECONNECT_JITTER`        | `0.25`               | 대칭 jitter 비율 (`0`이면 비활성, 테스트용) |
| `RHINO_MCP_LOG_LEVEL`               | `INFO`               | stderr 로그 레벨. `DEBUG`로 모든 브리지 JSON-RPC 호출 추적. |

## 개발(Development)

```bash
git clone https://github.com/easehee/rhino-mcp.git
cd rhino-mcp
uv venv && source .venv/bin/activate
uv pip install -e '.[dev]'

# 테스트 + 커버리지
uv run pytest --cov=src/rhino_mcp

# 린트 + 타입 체크
uv run ruff check src/ tests/
uv run mypy src/rhino_mcp

# C# 브리지 플러그인 빌드(macOS/Windows에서 자동 설치)
./scripts/build-plugin.sh --release

# Wheel + sdist 패키지 빌드
./scripts/build.sh
```

### 실행 중인 서버에 수동 스모크 테스트

```bash
# 터미널 A — verbose 로그로 서버 실행
RHINO_MCP_LOG_LEVEL=DEBUG rhino-mcp --transport http --port 8765

# 터미널 B — MCP inspector 또는 curl로 도구 목록 확인
npx @modelcontextprotocol/inspector http://127.0.0.1:8765/mcp
```

## 문제 해결(Troubleshooting)

| 증상                                       | 원인 / 해결 |
|--------------------------------------------|------------|
| `Cannot reach Rhino bridge.`               | Rhino 8에 C# 브리지 플러그인이 로드되어 있는지, `RHINO_HOST`/`RHINO_PORT`가 맞는지 확인. |
| 브리지 전용 도구가 Claude에 보이지 않음     | Standalone 모드입니다. 브리지 플러그인을 로드하거나 `RHINO_MCP_FORCE_MODE=bridge`를 설정하세요. |
| `Invalid parameter: axis`(cylinder)        | Standalone은 `{x:0,y:0,z:1}`만 지원합니다. 임의 축이 필요하면 브리지 모드를 쓰세요. |
| `non-3DM` import 에러                      | Standalone import는 `.3dm` 전용입니다. STEP/IGES/DXF는 브리지가 필요합니다. |
| `transport failure on tcp://...`           | 브리지가 죽었거나 Rhino가 종료된 경우 — `rhino-mcp`가 지수 백오프(`RHINO_MCP_RECONNECT_RETRIES`)로 자동 재연결 시도합니다. |
| stdio 전송 시 stdout 깨짐                   | 항상 stderr로 로깅해야 합니다. rhino-mcp는 그렇게 동작합니다 — 외부 라이브러리가 stdout으로 출력하지 않는지 확인하세요. |
| 스크린샷 응답에 `image_base64`가 없음        | 호출 시 `as_base64=False`(기본값)였거나 파일 쓰기에 실패한 경우 — `summary.path`와 `base64_error` 필드를 확인하세요. |
| 페이지네이션 무한 루프                      | `offset`을 `limit`이 아니라 `pagination.returned`만큼 증가시키세요. 마지막 페이지는 부분일 수 있습니다. |
| `rhino_object_select` 결과가 0개            | 필터들은 AND로 결합됩니다. 하나씩 제거해 보세요. `color` 필터는 `ColorSource=ColorFromObject`인 객체에만 동작합니다. |

더 많은 사례는 [docs/ko/troubleshooting.md](docs/ko/troubleshooting.md)에 있습니다.

## 라이선스(License)

MIT — [LICENSE](./LICENSE)
