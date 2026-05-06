# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] - 2026-05-06

### Added — bridge transport features

- **Response chunking** for large payloads. When a result exceeds
  ``RHINO_MCP_CHUNK_THRESHOLD`` (default 4 MB) the bridge stashes the
  bytes server-side and returns ``{__chunked__: true, chunk_id, ...}``;
  the Python client transparently calls ``rhino.bridge.fetch_chunk``
  in fixed-size slices and ``rhino.bridge.chunk_release`` to clean up.
  Chunks evict after ``RHINO_MCP_CHUNK_TTL_SEC`` (default 60 s).
- **Opt-in gzip response compression**. The Python client adds
  ``_accept_encoding: ["gzip"]`` to every request unless
  ``RHINO_MCP_GZIP=0``. The bridge gzips results larger than
  ``RHINO_MCP_COMPRESS_THRESHOLD`` (default 16 KB) and returns
  ``{__compressed__: true, encoding: "gzip", data_b64: ...}``.
  Compression and chunking compose: a result is compressed first, then
  the compressed bytes are chunked if still oversized.
- **`rhino.batch.execute`** — single-roundtrip multi-step dispatch.
  Steps run sequentially on the UI thread; the network/IPC cost is paid
  once. ``on_error`` controls "stop on first failure" vs "continue and
  collect errors". Reachable from Python via
  ``_helpers.bridge_call_batch(steps)``.
- **JSON-RPC error code matrix** consolidated in
  ``docs/dev/rpc-error-codes.md`` and mirrored in
  ``src/rhino_mcp/utils/rpc_errors.py`` (Python ``RpcErrorCode`` enum +
  ``raise_rpc_error``) and ``rhino_plugin/csharp/RpcErrorCodes.cs``
  (C# constants). New codes: ``-50002 PayloadTooLarge``,
  ``-50003 ChunkNotFound``, ``-50004 TooManyObjectIds``,
  ``-50005 BatchStepFailed``, ``-50006 RenderJobUnknown``.

### Added — Grasshopper

- **`gh_plugin_list`** enumerates loaded GH plugin libraries (id, name,
  version, author, on-disk path). Lets the LLM detect LunchBox /
  Ladybug / Pufferfish before attempting to drop in a custom component.
- **`gh_components_search`** queries the full GH component catalog
  (built-in + plugin-supplied) by name / nickname / category /
  subcategory / plugin and returns the GUID needed by
  ``gh_add_component``.
- **`gh_data_tree_get_batch` / `gh_data_tree_set_batch`** —  multi-
  branch DataTree access in a single round-trip. The set_batch variant
  suspends the GH solver via ``defer_solve`` so a parameter sweep
  triggers exactly one recompute instead of N.

### Added — BIM / IFC

- **`rhino_bim_pset_get` / `rhino_bim_pset_set` /
  `rhino_bim_pset_delete`** — read, write, and delete PropertySet
  entries (e.g. ``Pset_WallCommon::IsExternal``) on individual objects.
  Persistence uses ``UserString`` keyed as ``<pset>::<key>`` so values
  survive Save/Load and the existing IFC export pipeline picks them up
  unchanged.

### Added — viewport + render

- **`rhino_viewport_preview`** captures the viewport restricted to a
  selection list and/or layer filter. Non-target objects are ghosted
  (default) or hidden for the duration of the capture and restored
  after. Optional ``zoom_to_selection`` re-centres the view.
- **`rhino_render_queue_submit` / `_status` / `_cancel` / `_list`** —
  frame-sequence render queue. Submissions return immediately with a
  ``job_id``; frames are captured on a background worker that hops to
  the UI thread per frame. v0.5 backend uses
  ``_-ViewCaptureToFile``; photo-realistic engine integration is
  tracked separately.

### Changed — input validation

- **Tool-wide ``object_ids`` ceiling**. Every multi-id Pydantic input
  model now applies ``max_length=MAX_OBJECT_IDS`` (default 500,
  override via ``RHINO_MCP_MAX_OBJECT_IDS``). Affects analysis, BIM,
  blocks, deformation, drawing, environment, extraction, layers,
  materials, schedule, transform, freeform/fields. Bad inputs reject
  with ``InvalidParams`` before the call reaches the bridge.
- **Pagination helper** (``_helpers.paginate``,
  ``DEFAULT_PAGE_LIMIT=100``, ``MAX_PAGE_LIMIT=500``) is now exported
  for tool-level adoption. Per-tool migration is incremental — existing
  page implementations (``query.list_objects``) are unchanged.

### Added — observability

- **Request-id trace** in ``SafeRunScript``. When
  ``RHINO_MCP_TRACE_RUNSCRIPT=1`` is set, every wrapped RunScript line
  carries a ``[req:<jsonrpc-id>]`` prefix so the C# command-line trace
  ties back to the originating MCP request. Implemented via
  ``BridgeContext.CurrentRequestId`` (thread-local on the UI thread).

### Changed — environment variables

- New: ``RHINO_MCP_CHUNK_THRESHOLD`` (default 4 MB),
  ``RHINO_MCP_CHUNK_BYTES`` (default 512 KB),
  ``RHINO_MCP_CHUNK_TTL_SEC`` (default 60 s),
  ``RHINO_MCP_COMPRESS_THRESHOLD`` (default 16 KB),
  ``RHINO_MCP_GZIP=0`` to disable opt-in compression,
  ``RHINO_MCP_BATCH_MAX_STEPS`` (default 256),
  ``RHINO_MCP_MAX_OBJECT_IDS`` (default 500).
- Bridge ``protocol_version`` bumped to ``1.2`` (chunking + batch
  + gzip + render-queue).

### Documentation

- ``docs/dev/rpc-error-codes.md`` — code matrix + extension policy.
- ``docs/dev/work-queue-spike.md`` — RhinoCommon thread-affinity
  findings and follow-up plan for ``batch_modify``-style handlers.
- ``docs/dev/runscript-migration.md`` and
  ``docs/dev/manual-verification.md`` (carried over from v0.4.2)
  remain the source of truth for RunScript replacement priorities and
  scenario-level verification.

### Tests

- Total: **254 tests** in standalone (was 213 at v0.3.0).

### 추가 — 브리지 전송 계층 (한글 요약)

- **응답 chunking** — 결과 크기가 ``RHINO_MCP_CHUNK_THRESHOLD`` (기본 4 MB)
  초과 시 bridge에 byte buffer 보관 후 메타데이터만 응답. Python 클라이언트가
  ``rhino.bridge.fetch_chunk`` 루프로 자동 재조립.
- **opt-in gzip 응답 압축** — ``RHINO_MCP_GZIP=0``로 비활성. 16 KB 초과 응답에 대해
  자동 적용. chunking과 결합 가능.
- **`rhino.batch.execute`** — 한 round-trip에 N step 실행. ``on_error=stop|continue``.
- **JSON-RPC error code 매트릭스** — Python/C#/문서 3곳 동기화.

### 추가 — Grasshopper / BIM / 뷰포트 / 렌더

- **`gh_plugin_list` / `gh_components_search`** — 설치된 GH 플러그인 카탈로그 노출.
- **`gh_data_tree_get_batch` / `gh_data_tree_set_batch`** — 단일 솔버 재계산으로
  N branch 일괄 set. ``defer_solve=True`` (기본).
- **`rhino_bim_pset_get` / `_set` / `_delete`** — PropertySet 단위 read/write/delete.
- **`rhino_viewport_preview`** — 선택/레이어 필터 부분 미리보기 + 자동 viewport 복원.
- **`rhino_render_queue_submit/status/cancel/list`** — 프레임 시퀀스 렌더 큐.

### 변경

- 모든 다중 ID 도구에 ``MAX_OBJECT_IDS=500`` 강제. ``RHINO_MCP_MAX_OBJECT_IDS``로 override.
- bridge ``protocol_version`` → ``1.2``.

## [0.4.2] - 2026-05-06

### Fixed — bridge connection stability

- `BridgeServer.cs` no longer silently sends an empty `OK` response when
  the UI-thread dispatch exceeds the wait window. The `done.Wait(...)`
  return value is now respected; on timeout the client receives a
  structured JSON-RPC error (`code = -50001`, message references
  `RHINO_MCP_UI_TIMEOUT`). Previously a long-running command (modal
  dialog, blocking script) would let the dispatch keep running on the UI
  thread while the client believed the call had completed, causing the
  next request to race against stale state and the connection to
  "drop" intermittently.
- `BridgeServer` enables `SO_KEEPALIVE` on every accepted client so the
  OS detects half-closed peers across idle periods. Adds a `SendTimeout`
  (default 30 s, `RHINO_MCP_SEND_TIMEOUT_MS` override) to detect dead
  peers on response writes. `ConnectedClientCount` is now tracked and
  surfaced in the `rhino.ping` reply.
- The Python `BridgeClient` now calls `Transport.reset_buffers()` on the
  error path before tearing down the socket, so a half-read framing line
  cannot corrupt the next reconnect cycle. `TcpTransport.connect` enables
  `SO_KEEPALIVE` plus per-OS keepalive intervals
  (`RHINO_MCP_KEEPALIVE_IDLE/INTERVAL/COUNT`).
- `rhino.ping` reply gains `protocol_version` (currently `1.1`). The
  client logs a warning when a connected plugin advertises an older
  version than required so v0.4.2 stability fixes can be detected at
  connection time.

### Fixed — `_Width` / `_Enter` token leakage on Rhino's command line

- New `HandlerBase.SafeRunScript(...)` wraps every `RhinoApp.RunScript`
  call site. On any exception inside the wrapped block it issues an
  `_Escape` to flush partially-tokenised commands so a half-built
  `_-ViewCaptureToFile "..." _Width=…` can no longer leave `_Width` (or
  any other sub-option) sitting in Rhino's command prompt when validation
  or dispatch fails mid-sequence. Tracing is gated on
  `RHINO_MCP_TRACE_RUNSCRIPT=1` for diagnostics.
- `IOHandler.Screenshot` now validates `path` (non-empty, no double
  quotes) and `width`/`height` (positive integers, ≤ 16384) **before**
  the RunScript line is constructed. The other IO methods
  (`Open`/`Save`/`Import`/`Export*`/`BlockInsert`) gained the same path
  guard. Bad arguments now reject with a structured error and never
  reach the command line.
- Every other handler (`SurfaceHandler`, `SurfaceMatchHandler`,
  `TransformHandler`, `RenderHandler`, `DisplayHandler`,
  `LayerHandler`, `BimIoHandler`, `DrawingHandler`, `AnnotationHandler`,
  `AnalysisHandler`, `GrasshopperHandler`, `ExtractionHandler`)
  routes through `SafeRunScript` instead of calling `RhinoApp.RunScript`
  directly. Phase B of the migration (replace RunScript with direct
  RhinoCommon APIs where available) is tracked in
  `docs/dev/runscript-migration.md`.

### Changed — environment variables

- New: `RHINO_MCP_UI_TIMEOUT` (seconds, default 30),
  `RHINO_MCP_SEND_TIMEOUT_MS` (default 30000),
  `RHINO_MCP_KEEPALIVE_IDLE` / `RHINO_MCP_KEEPALIVE_INTERVAL` /
  `RHINO_MCP_KEEPALIVE_COUNT` (per-OS keepalive tuning, Linux/macOS
  only), `RHINO_MCP_TRACE_RUNSCRIPT=1` to log every wrapped RunScript
  line to Rhino's command window.

### 수정 — 브리지 연결 안정성

- `BridgeServer.cs` UI thread dispatch 타임아웃 시 빈 `OK` 응답 전송 버그 수정.
  `done.Wait(...)` 반환값 검사 추가, 타임아웃 시 JSON-RPC 에러
  (`code = -50001`, `RHINO_MCP_UI_TIMEOUT`) 응답. 이전에는 모달 대화상자
  등 장기 실행 명령이 UI thread를 점유한 동안 클라이언트가 이미 성공으로
  믿고 다음 요청을 보내, race 발생으로 연결이 간헐적 단절.
- 매 클라이언트 연결에 `SO_KEEPALIVE` 활성화. 응답 write 타임아웃
  (`RHINO_MCP_SEND_TIMEOUT_MS`, 기본 30 s) 적용으로 dead peer 감지.
  `ConnectedClientCount` 추적 + `rhino.ping` 응답 노출.
- Python `BridgeClient` 에러 경로에서 `Transport.reset_buffers()` 호출 →
  reconnect 직전 half-read 라인 폐기. `TcpTransport.connect` 에 keepalive
  + per-OS interval (`RHINO_MCP_KEEPALIVE_IDLE/INTERVAL/COUNT`) 적용.
- `rhino.ping` 응답에 `protocol_version` (현재 `1.1`) 추가. 클라이언트가
  연결 시점에 plugin 버전 호환성 경고.

### 수정 — Rhino 명령행에 `_Width`/`_Enter` 토큰 잔류 문제

- `HandlerBase.SafeRunScript(...)` 헬퍼 신설. 모든 RunScript 호출 wrapping,
  예외 발생 시 `_Escape` 강제 송출 → 부분 토큰화된 명령
  (`_-ViewCaptureToFile "..." _Width=…` 같은 미완성)이 더 이상 Rhino
  명령창에 잔류 불가. 디버그 트레이스: `RHINO_MCP_TRACE_RUNSCRIPT=1`.
- `IOHandler.Screenshot`: RunScript 진입 전 `path` (non-empty, 큰따옴표 금지)
  + `width`/`height` (양수, ≤16384) 검증. 다른 IO 메소드
  (`Open`/`Save`/`Import`/`Export*`/`BlockInsert`) 도 동일 path 가드.
  잘못된 인자는 구조화된 에러 반환, 명령창 도달 차단.
- 나머지 모든 handler (`SurfaceHandler`, `SurfaceMatchHandler`,
  `TransformHandler`, `RenderHandler`, `DisplayHandler`, `LayerHandler`,
  `BimIoHandler`, `DrawingHandler`, `AnnotationHandler`,
  `AnalysisHandler`, `GrasshopperHandler`, `ExtractionHandler`) →
  `SafeRunScript` 경유. Phase B (RunScript → RhinoCommon API 점진 전환)
  로드맵: `docs/dev/runscript-migration.md`.

### 변경 — 환경 변수

- 추가: `RHINO_MCP_UI_TIMEOUT` (초, 기본 30),
  `RHINO_MCP_SEND_TIMEOUT_MS` (기본 30000),
  `RHINO_MCP_KEEPALIVE_IDLE` / `RHINO_MCP_KEEPALIVE_INTERVAL` /
  `RHINO_MCP_KEEPALIVE_COUNT` (Linux/macOS keepalive 튜닝),
  `RHINO_MCP_TRACE_RUNSCRIPT=1` (RunScript 라인 trace 활성화).

## [0.4.1] - 2026-05-05

### Added — `_McpInstall` Rhino command

- New `_McpInstall` command (`rhino_plugin/csharp/Commands/McpInstallCommand.cs`)
  bootstraps the PyPI package and runs `rhino-mcp install` from inside
  Rhino so end users no longer need a terminal at all. The command
  resolves a launcher in this order: `uvx` (preferred, ephemeral
  install), an installed `rhino-mcp` console script, then a system
  `python` / `python3` fallback. macOS launches scan
  `~/.local/bin`, `~/.cargo/bin`, `/opt/homebrew/bin`, and
  `/usr/local/bin` because Rhino starts as a GUI app with a thin
  `PATH`. Output is streamed to the Rhino command line; failure
  paths print the canonical `pip install rhino3dm-mcp && rhino-mcp
  install` instructions plus the `uv` install URL. The command is
  non-interactive — the MCP server is always registered with
  `--mode auto`, which lets Claude Desktop attach to the bridge
  when Rhino is running and fall back to standalone (rhino3dm) when
  Rhino is closed. Rhino-design users are never asked about
  "standalone" vs "bridge" terminology.

### Changed — version sync

- `pyproject.toml`, `src/rhino_mcp/__init__.py`,
  `rhino_plugin/csharp/manifest.yml`,
  `rhino_plugin/csharp/RhinoMCPPlugin.csproj`, and the staged
  `yak-stage/{win,mac}/manifest.yml` are all bumped to `0.4.1`
  together. The `csproj` `<Version>` value was lagging at `0.3.1`;
  it is now sync'd with the rest of the build matrix.

### 추가 — `_McpInstall` Rhino 명령

- `rhino_plugin/csharp/Commands/McpInstallCommand.cs` 신규: Rhino 명령창에서
  `_McpInstall` 한 줄 입력 → PyPI 패키지 부트스트랩 + `rhino-mcp install`
  자동 실행. 터미널 사용 0회. launcher 우선순위: `uvx` (선호, ephemeral
  실행) → 설치된 `rhino-mcp` 콘솔 스크립트 → 시스템 `python` / `python3`.
  Rhino 가 GUI 앱으로 시작되어 macOS `PATH` 가 빈약 → `~/.local/bin`,
  `~/.cargo/bin`, `/opt/homebrew/bin`, `/usr/local/bin` 명시 탐색.
  출력은 Rhino 명령창으로 스트리밍, 실패 시 표준 `pip install
  rhino3dm-mcp && rhino-mcp install` 안내 + `uv` 설치 URL 출력.
  비대화형(non-interactive) — MCP 서버는 항상 `--mode auto` 로
  등록. Claude Desktop 실행 시점에 Rhino 가 켜져 있으면 브리지 자동
  연결, 꺼져 있으면 standalone (rhino3dm) 자동 폴백.
  사용자에게 standalone/bridge 같은 용어 선택을 요구하지 않음.

### 변경 — 버전 동기화

- `pyproject.toml`, `src/rhino_mcp/__init__.py`,
  `rhino_plugin/csharp/manifest.yml`,
  `rhino_plugin/csharp/RhinoMCPPlugin.csproj`, 그리고 staged
  `yak-stage/{win,mac}/manifest.yml` 모두 `0.4.1` 로 동기화. csproj
  `<Version>` 이 `0.3.1` 로 뒤쳐져 있던 것 → 빌드 매트릭스와 일치.

## [0.4.0] - 2026-05-05

### Added — packaging and release pipeline

- YAK packaging path for the Rhino bridge plugin: `scripts/publish-yak.sh`
  stages the `.rhp` + `manifest.yml` + icon under `rhino_plugin/csharp/yak-stage/`
  per platform (`win`, `mac`) and drives `yak.exe build` so that the plugin
  ships as a Yak package alongside the raw `.rhp`.
- `.github/workflows/release.yml` gains `build-rhp` (Windows runner,
  `dotnet build -c Release`) and `build-yak` (Yak CLI, optional, attaches
  `.yak` files to the GitHub Release) jobs, so that tagging `v0.4.0`
  produces a single Release containing the Python wheel + sdist
  (PyPI), the `rhino-mcp.rhp` plugin, and the per-platform `.yak`
  packages.

### Added — one-shot Claude Desktop wiring

- New `rhino-mcp install` sub-command writes (or updates) the
  `mcpServers.rhino-mcp` entry inside `claude_desktop_config.json` so
  users no longer have to edit JSON by hand after `pip install`.
  Auto-detects the platform-specific config path (macOS / Windows /
  Linux), preserves any other registered servers, writes a timestamped
  `.bak.*` of the previous file, and is idempotent on re-run.
- Flags: `--mode {auto,standalone,bridge}`,
  `--transport {stdio,http}`, `--name`, `--launcher
  {auto,uvx,rhino-mcp,python}`, `--config-path`, `--force`,
  `--no-backup`, `--dry-run`.

### Changed — PyPI distribution name and version sync

- Renamed PyPI distribution from `rhino-mcp` to `rhino3dm-mcp`: the bare
  `rhino-mcp` name was already registered on PyPI by an unrelated
  project, so the first PyPI release of this server ships as
  `rhino3dm-mcp`. The console-script entry point `rhino-mcp` is kept,
  and a parallel alias `rhino3dm-mcp` is added so that
  `uvx rhino3dm-mcp` resolves a matching script name without `--from`.
- Bumped the Rhino plugin manifest, the Python distribution, and
  `rhino_mcp.__version__` together to `0.4.0` so that the YAK package
  and the PyPI wheel ship as a matched pair.
- Refreshed `pip install` / `uvx` snippets across `README.md`,
  `README.ko.md`, `docs/{en,ko}/installation.md`, and
  `docs/{en,ko}/configuration.md` to use the new distribution name.
  MCP-client `mcpServers` keys, the `rhino-mcp` CLI command, the
  `rhino-mcp.rhp` plugin filename, and the internal `rhino_mcp` Python
  module path all stay unchanged — existing user configs keep working
  with no edits.
- Replaced the legacy `assets/rhino-logo.png` with `assets/rhino-mcp.png`
  (used both in the README header and as the YAK plugin icon).

### 추가 — 패키징 및 릴리스 파이프라인

- Rhino 브리지 플러그인용 YAK 패키징 경로 추가: `scripts/publish-yak.sh`
  가 플랫폼별로 `.rhp` + `manifest.yml` + icon 을
  `rhino_plugin/csharp/yak-stage/{win,mac}/` 으로 stage 후
  `yak.exe build` 호출 → 기존 `.rhp` 와 더불어 Yak 패키지 동시 배포.
- `.github/workflows/release.yml` 에 `build-rhp` (Windows runner,
  `dotnet build -c Release`), `build-yak` (Yak CLI, optional) 잡 추가.
  `v0.4.0` 태그 1회로 PyPI wheel + sdist, `rhino-mcp.rhp`, 플랫폼별
  `.yak` 까지 GitHub Release 단일 산출물로 통합 배포.

### 추가 — Claude Desktop 자동 등록

- `rhino-mcp install` 서브 명령 신규: `claude_desktop_config.json` 의
  `mcpServers.rhino-mcp` 항목 자동 작성/갱신. macOS / Windows / Linux
  config 경로 자동 탐지, 다른 등록 서버 보존, 직전 파일은 타임스탬프
  `.bak.*` 백업, 동일 플래그 재실행 시 no-op (idempotent).
- 플래그: `--mode {auto,standalone,bridge}`,
  `--transport {stdio,http}`, `--name`, `--launcher
  {auto,uvx,rhino-mcp,python}`, `--config-path`, `--force`,
  `--no-backup`, `--dry-run`.

### 변경 — PyPI 배포명 및 버전 동기화

- PyPI 배포명 `rhino-mcp` → `rhino3dm-mcp`. 기존 `rhino-mcp` 가
  타 프로젝트로 선점되어 있어 본 서버 첫 게시 시 명칭 변경 필요.
  콘솔 스크립트 `rhino-mcp` 유지, alias `rhino3dm-mcp` 추가 →
  `uvx rhino3dm-mcp` 단독 호출 가능.
- Rhino 플러그인 manifest, Python 배포, `rhino_mcp.__version__` 모두
  `0.4.0` 으로 동기화 (YAK 패키지 + PyPI wheel 동시 배포 정합성).
- `pip install` / `uvx` 안내 문구 갱신: `README.md`, `README.ko.md`,
  `docs/{en,ko}/installation.md`, `docs/{en,ko}/configuration.md`.
  MCP 클라이언트 `mcpServers` key, `rhino-mcp` CLI 명령, `rhino-mcp.rhp`
  플러그인 파일명, 내부 `rhino_mcp` Python 모듈 경로 모두 유지 —
  기존 사용자 설정 그대로 동작.
- 기존 `assets/rhino-logo.png` 제거, 신규 `assets/rhino-mcp.png` 로 교체
  (README 헤더 + YAK 플러그인 아이콘 공용).

## [0.3.0] - 2026-05-03

### Added — drawing-set and quantity workflow upgrade

- **Drawing-set tools** (`tools/drawing.py`, both modes for sheet /
  title block; bridge for view placement / section cut / PDF export) —
  collapse the "model -> drawing set" workflow into call bundles:
  - `rhino_drawing_sheet_create` writes a sheet rectangle on layer
    `Sheets::<name>` with paper-size and scale metadata stored as
    user_text.
  - `rhino_drawing_view_place` (bridge) projects model objects to a
    chosen world view (Top/Front/Right/...) and translates the wireframe
    onto the sheet at the requested scale.
  - `rhino_drawing_section_cut` (bridge) emits a section trace via
    `Brep.Plane` intersection.
  - `rhino_drawing_title_block_add` draws bottom-right title block,
    top-left north arrow, and bottom-left scale bar in one call.
  - `rhino_drawing_export_pdf` (bridge) wraps Rhino's `_-Print _PDF`.
- **Quantity / schedule tools** (`tools/schedule.py`, both modes):
  - `rhino_schedule_by_layer` aggregates count / area / volume / length
    per layer with optional filter and sublayer merging.
  - `rhino_schedule_by_user_text` groups by any user_text key
    (`function`, `assembly_type`, `material`, ...).
  - `rhino_schedule_by_material` groups by assigned material.
  - `rhino_object_quantity` per-object detail rows with centroid and
    bbox.
  - `rhino_schedule_export_csv` writes any rows to CSV.
  - Bridge mode uses `AreaMassProperties` / `VolumeMassProperties` for
    accurate Brep area + volume.
- **Block / instance reuse** (`tools/blocks.py`, both modes; bridge
  full-feature) — promote the latent C# block routes to a first-class
  Python toolkit:
  - `rhino_block_define`, `rhino_block_insert`, `rhino_block_list`
    work in standalone via `File3dm.InstanceDefinitions` and
    `InstanceReference`.
  - `rhino_block_explode` and `rhino_block_redefine` are bridge only
    because rhino3dm lacks the mutator APIs.
- **Environmental analysis** (`tools/environment.py`, both modes):
  - `rhino_sun_position` — NOAA SPA approximation (~+/- 0.5 deg).
  - `rhino_sun_path` — monthly polylines on a hemisphere of given
    radius around an anchor.
  - `rhino_shadow_project` — AABB-corner shadow polygon onto a
    horizontal ground plane (standalone) / accurate wireframe
    projection (bridge).
  - `rhino_solar_exposure_estimate` (bridge) — ray-cast lit-sample
    ratio against optional obstruction objects.
- **Annotation extensions** (`tools/annotation.py`):
  - `rhino_annotation_north_arrow` (`simple` triangle or `compass`).
  - `rhino_annotation_scale_bar` with division ticks + label.
  - `rhino_annotation_revision_cloud` (bumpy polyline + `Rev <no>`
    label).
  - `rhino_annotation_callout` (`balloon` or `box` style).
  - `rhino_annotation_dimension_style` (bridge — `RhinoDoc.DimStyles`).
- **2 new strategy prompts** in `prompts/strategy.py`:
  - `drawing_documentation` — multi-view sheet workflow with
    title-block + revision-cloud + PDF export.
  - `quantity_takeoff` — per-layer / per-material / per-user_text
    schedule + CSV export.
- **3 new examples**:
  - `examples/drawing_set.py` — sheet + title block + north arrow +
    scale bar (standalone).
  - `examples/schedule_report.py` — disciplined-layer mesh model +
    layer / user_text schedules + CSV export.
  - `examples/sun_study.py` — sun_position + sun_path + shadow_project
    for Seoul defaults.
- **C# handlers** (`rhino_plugin/csharp/Handlers/`):
  - `DrawingHandler.cs` (sheet / view_place / section_cut /
    title_block / export_pdf).
  - `ScheduleHandler.cs` (by_layer / by_user_text / by_material /
    object_quantity).
  - `EnvironmentHandler.cs` (sun_path / shadow_project /
    solar_exposure_estimate).
  - `BlockHandler.cs` (define / insert / list / explode / redefine).
  - `AnnotationHandler.cs` extended with north_arrow / scale_bar /
    revision_cloud / callout / dim_style_create.
  - `CommandDispatcher.cs` registers the new routes (~25 entries).

### Changed

- `tools/layers.py` no longer hosts `rhino_block_create` /
  `rhino_block_insert` stubs; block authoring lives in
  `tools/blocks.py` instead.
- `tools/annotation.py` is now a both-mode module (was bridge-only past
  the text/text-dot pair).
- README / docs / CLAUDE.md updated to document the C# bridge as the
  only supported bridge implementation.

### Removed

- Legacy Python bridge `rhino_plugin/RhinoMCPBridge.py` and its
  installer `rhino_plugin/install.py`. Use the C# plugin
  (`rhino_plugin/csharp/`) — `dotnet build -c Release` then drag-drop
  the `.rhp`.

### Added — BIM interchange, material presets, render automation, daylight precision, release CI

- **BIM interchange** (`tools/bim_io.py` + `BimIoHandler.cs`):
  - `rhino_export_ifc` (bridge) — IFC2x3 / IFC4 / IFC4x3 round-trip;
    auto-tags objects by `function` user_text using a default
    `IfcWallStandardCase` / `IfcSlab` / `IfcRoof` / `IfcColumn` /
    `IfcBeam` / `IfcDoor` / `IfcWindow` / `IfcStair` / `IfcRailing` /
    `IfcFurnishingElement` map. Override via `entity_type_map`.
  - `rhino_import_ifc` (bridge) — buckets imported objects under
    `<root>::<IfcType>` layers with optional whitelist filter.
  - `rhino_export_gbxml` (bridge) — gbXML for thermal / structural
    interchange.
  - `rhino_bim_metadata_set` (both modes) — writes IFC entity +
    `Pset_<name>::<key>` user_text so a subsequent IFC export carries
    BIM properties across.
- **Physical material presets + HDRI environment**
  (`tools/materials.py` + `data/material_presets.json` +
  `MaterialHandler.PresetCreate` / `EnvironmentSet`):
  - 19-entry preset catalogue (concrete CIP / precast, brick,
    brushed steel, anodised aluminium, patinated copper, clear /
    Low-E / frosted glass, oak / CLT / charred timber, granite /
    marble, plaster, carpet, rubber, grass, water) with diffuse /
    transparency / glossiness / reflectivity / IOR tuned for
    architectural visualisation.
  - `rhino_material_preset_list` (filterable by category).
  - `rhino_material_preset_create` (both modes — standalone uses
    rhino3dm's basic Material; bridge sets the same PBR fields plus
    IOR via Rhino's render content engine).
  - `rhino_environment_set` (bridge) — HDRI / EXR scene environment
    with rotation, strength, and lighting / background toggles.
- **Render automation** (`tools/render.py` + `RenderHandler.cs`,
  bridge only):
  - `rhino_camera_set` — viewport position + target + lens length.
  - `rhino_light_add` — point / spot / directional / rectangular /
    linear lights with intensity + colour.
  - `rhino_render_setup` — resolution, samples, engine
    (rhino / cycles / raytraced / vray / active), transparent
    background.
  - `rhino_render_to_file` — execute the configured render and write
    to disk via `_-Render` + `_-SaveRenderWindowAs`.
  - `rhino_turntable_render` — render a frame sequence around a
    target (parametric camera orbit).
- **Daylight precision** (`tools/environment.py`):
  - `rhino_direct_irradiance` — Direct Normal Irradiance (W/m²)
    clear-sky estimate via Bird-style attenuation + Kasten-Young air
    mass with site altitude + Linke turbidity.
  - `rhino_daylight_factor` — BRE simplified daylight factor for
    side-lit rooms with deficient (<2 %) / acceptable (2–5 %) /
    good (≥ 5 %) rating.
- **Release CI**:
  - `.github/workflows/ci.yml` — Python 3.11/3.12/3.13 matrix
    (ruff + pytest) plus C# `dotnet build` on Windows.
  - `.github/workflows/release.yml` — tag-triggered jobs that build
    + publish the wheel to PyPI (Trusted Publishing), build the
    `RhinoMCPBridge.rhp`, and produce a Yak `.yak` package via
    `manifest.yml`. Artefacts attached to the GitHub release.
  - `rhino_plugin/csharp/manifest.yml` — Yak manifest stub
    (name / version / authors / icon / keywords).

### Tests

- v0.3 first wave: `+27` (drawing / schedule / blocks / environment /
  annotation extensions).
- v0.3 second wave: `+20` (`test_bim_io.py`, `test_material_presets.py`,
  `test_render.py`, `test_daylight.py`).
- Total: **213 tests** in standalone.

## [0.2.0] - 2026-05-03

### Added — modeling experience upgrade

- **Composition tools** (`tools/composition.py`, both modes) — one-shot
  multi-object placement so the LLM doesn't have to drive a transform
  loop call-by-call:
  - `rhino_place_grid` — count_x × count_y grid, optional `skip_origin`
    and `name_prefix`.
  - `rhino_stack_floors` — stack copies vertically (architectural
    storey replication).
  - `rhino_scatter` — scatter inside a 2-D AABB with deterministic
    `seed` and optional Z-rotation jitter.
  - `rhino_replicate_along_curve` — distribute copies along a curve at
    evenly spaced parameters, optional tangent alignment.
- **Document hygiene tools** (`tools/document_config.py`, both modes) —
  surface units / tolerances / base point as first-class queryable
  state instead of silent footguns:
  - `rhino_document_units_get` / `rhino_document_units_set`
    (with `scale_existing` flag).
  - `rhino_tolerance_get` / `rhino_tolerance_set`.
  - `rhino_origin_set` (`reference` / `translate` modes).
  - `rhino_document_settings` — bundled summary in one call.
  - `rhino_document_summary` extended with `units`, `tolerances`,
    `base_point`, `layer_tree_depth`.
- **Geometry validation tools** (`tools/geometry_validation.py`) —
  surface topology issues that silently break booleans, exports, and
  fabrication:
  - `rhino_validate_brep` — closed/solid/manifold flags, edge/face
    counts, structured `issues` payload.
  - `rhino_check_naked_edges` (bridge only) — enumerate naked edges
    with index + length.
  - `rhino_report_mesh_health` — closed/manifold/vertex/face report.
  - `rhino_curve_continuity` — span count, planarity, periodic, log.
- **Grasshopper template loader** (`tools/grasshopper/templates.py`):
  - `gh_template_list` (both modes) — manifest-driven catalogue with
    parameter contracts; reports `available` per binary.
  - `gh_load_template` / `gh_bind_template_parameter` /
    `gh_run_template` (bridge only).
  - `src/rhino_mcp/data/gh_templates/manifest.json` ships 4 declared
    templates: `panel_grid`, `morph_to_surface`, `offset_facade`,
    `field_scatter`. Binaries are populated separately (see the
    `README.md` in that folder).
- **3 new strategy prompts** in `prompts/strategy.py`:
  - `parametric_workflow` — iterative slider sweeps + comparable
    variants + validation per variant.
  - `bim_authoring_workflow` — layer tree, grouping, and `user_text`
    metadata conventions for architectural authoring.
  - `design_dialogue_workflow` — multi-turn design checkpoints with
    user-in-the-loop confirmation.
- **3 new examples**:
  - `examples/architectural_massing.py` — site grid + stacked floors +
    BIM metadata + validation (standalone).
  - `examples/iterative_design_exploration.py` — GH template + slider
    sweep + screenshot comparison (bridge only).
  - `examples/validation_workflow.py` — pre-flight Brep / Curve / Mesh
    health check (both modes).
- **Free-form architecture toolkit** — purpose-built for
  doubly-curved / non-rectilinear architectural design:
  - `tools/freeform/skin.py` — `rhino_skin_from_sections` (chain ruled
    surfaces between ordered sections in standalone, true Brep loft on
    bridge), `rhino_section_at_axis` (UV iso-curves both modes; world
    X/Y/Z plane slicing on bridge), `rhino_axis_ribs` (bridge) for
    waffle fabrication.
  - `tools/freeform/paneling.py` — `rhino_uv_grid_panels` (mesh /
    curves / corners output), `rhino_panel_planarity` (per-cell best-
    fit-plane deviation with stats), `rhino_panel_curvature_classify`
    (planar / single_curved_u / single_curved_v / synclastic /
    anticlastic via 4-corner normal heuristic in standalone, true
    Gaussian via `Surface.CurvatureAt` on bridge).
  - `tools/freeform/curvature.py` — `rhino_surface_normal_at`,
    `rhino_surface_developable_score` (0 ≈ developable, 1 ≈ fully
    doubly-curved), and `rhino_surface_curvature_at` (bridge — true
    Gaussian / mean / principal k₁ k₂ + directions).
  - `tools/freeform/fields.py` — `rhino_attractor_displace_points`
    (linear / inverse / gaussian falloff; point or curve attractor),
    `rhino_smooth_polyline` (Laplacian smoothing with optional
    endpoint pinning).
- **4 new strategy prompts** in `prompts/strategy.py`:
  - `parametric_workflow` — iterative slider sweeps + comparable
    variants + validation per variant.
  - `bim_authoring_workflow` — layer tree, grouping, and `user_text`
    metadata conventions for architectural authoring.
  - `design_dialogue_workflow` — multi-turn design checkpoints with
    user-in-the-loop confirmation.
  - `freeform_workflow` — 6-step guide for non-rectilinear authoring:
    shape → curvature check → panelise → refine → fabricate → report.
- **4 new examples**:
  - `examples/architectural_massing.py` — site grid + stacked floors +
    BIM metadata + validation (standalone).
  - `examples/iterative_design_exploration.py` — GH template + slider
    sweep + screenshot comparison (bridge only).
  - `examples/validation_workflow.py` — pre-flight Brep / Curve / Mesh
    health check (both modes).
  - `examples/freeform_canopy.py` — varying-radius arc sections →
    multi-segment skin → per-segment panelisation + classification →
    aggregate panel report (standalone).
- **C# bridge handlers** (`rhino_plugin/csharp/Handlers/`):
  - `CompositionHandler` (4 methods).
  - `DocumentConfigHandler` (6 methods, base point persisted via
    document strings since RhinoCommon does not expose
    `ModelBasePoint` uniformly across Rhino 8 builds).
  - `ValidationHandler` (4 methods, with naked-edge enumeration).
  - `GhTemplatesHandler` (3 methods, name-based parameter binding).
  - `FreeformHandler` (12 methods — true Gaussian curvature, Brep /
    mesh plane slicing, RhinoCommon `Brep.CreateFromLoft`).
  - `CommandDispatcher.cs` adds 28 new `Register(...)` entries.

### Changed

- `pyproject.toml` version bumped to `0.2.0`; `__init__.py` mirrors.
- Hatch wheel `artifacts` extended to ship
  `src/rhino_mcp/data/gh_templates/*.json|*.gh|*.md`.
- `register(mcp, mode)` on `tools/grasshopper/templates.py` registers
  `gh_template_list` in both modes and the loader / bind / run trio
  only when the bridge is reachable, so standalone clients can still
  discover the catalogue.
- `_register_prompts` now exports 7 prompts (was 3 in v0.1).

### Fixed (uncovered while wiring v0.2 tests)

- `tools/query.py:rhino_object_info` used `.Faces.Count` /
  `.Edges.Count` / `.Vertices.Count` — rhino3dm 8.x's binding does not
  expose these as `Count` properties, so every `rhino_object_info`
  call against a Brep / Mesh in standalone raised `AttributeError`.
  Now uses `len(...)`.
- `tools/query.py` layer iteration accessed `lay.Color.R` etc., but
  rhino3dm's `Layer.Color` is a 4-tuple of ints rather than a struct
  with named fields. `rhino_document_summary` and `rhino_layer_list`
  now read `(r, g, b)` defensively from either shape.

### Tests

- 38 new tests, total 166 passed:
  - `tests/tools/test_composition.py` (8)
  - `tests/tools/test_document_config.py` (6)
  - `tests/tools/test_geometry_validation.py` (5)
  - `tests/tools/test_gh_templates.py` (4)
  - `tests/tools/test_freeform.py` (12)
  - `tests/test_prompts.py` extended with 4 prompt-coverage tests
    (now 9 tests in that file).

### Verification

- `uv run pytest tests/ -q` → 166 passed.
- `uv run ruff check src/ tests/` → All checks passed.
- `dotnet build rhino_plugin/csharp/ -c Release` → 0 errors / 0 warnings.

## [0.1.0 — pre-release notes (was Unreleased)]

### Added
- Project logo at `assets/rhino-mcp.png` referenced from both READMEs;
  `pyproject.toml` sdist `include` now ships the `assets/` directory.
- MCP prompts package (`src/rhino_mcp/prompts/strategy.py`) with three
  guides: `general_strategy`, `rhinoscript_workflow`, `viewport_workflow`.
- `rhino_screenshot(as_base64=True)` returns the PNG bytes inline as
  `image_base64` for LLM visual verification.
- `rhino_object_select` filter matrix: `name_pattern`, `layer`, `color`,
  `object_type`, `user_text`, `deselect_first` — combined with AND.
- `rhino_list_objects` carries a `pagination` block
  (`total`, `offset`, `limit`, `returned`, `has_more`).
- Async tool variants for `rhino_list_objects`, `rhino_document_summary`,
  `rhino_layer_list` using `BridgeClient.async_call`.
- `Transport.is_alive()` non-destructive liveness probe with `MSG_PEEK`
  (TCP/Unix) and `PeekNamedPipe` (Windows).
- Reconnect backoff jitter: `RHINO_MCP_RECONNECT_BASE_DELAY`,
  `RHINO_MCP_RECONNECT_JITTER`.
- `tools/_helpers.bridge_call` / `bridge_call_async` wrappers emitting
  DEBUG-level input/output traces.
- 17 new tests (`test_prompts.py`, `test_query.py`,
  `test_select_filters.py`, three new bridge connection tests).
- Thread-safe runtime context with lock protection (`tools/context.py`)
- Bridge auto-reconnection with configurable retries (`RHINO_MCP_RECONNECT_RETRIES`)
- Bridge health check: `ping()`, `is_healthy`, `reconnect()` methods
- `ErrorCategory.TIMEOUT` for timeout-specific error handling
- Transport buffer clearing on connection failure (all 3 transports)
- Request ID mismatch detection (raises error instead of warning)
- Docker compose health check configuration
- CLAUDE.md project documentation
- CONTRIBUTING.md with tool creation guide
- 33 new tests: bridge edge cases, Grasshopper tools, display/surface tools

### Changed
- README.md / README.ko.md largely rewritten: launch-mode matrix,
  per-OS Claude Desktop config-file paths, Cursor IDE example,
  claude.ai remote-connector walkthrough, base64 screenshot /
  pagination / rich-select usage examples, four new env vars
  documented, troubleshooting expanded.
- All Korean comments and docstrings in `src/`, `tests/`, and the C#
  plugin replaced with English to match the project convention.
- Pydantic `Field(...)` descriptions filled in across every tool module
  so parameter help surfaces in MCP clients.
- Removed private FastMCP API access (`_tool_manager._tools`) from server.py
- `send_line` now wraps OSError as ConnectionError across all transports
- `recv_line` now distinguishes TimeoutError from ConnectionError
- `register_tools()` logs warning when zero tools match the runtime mode
- Startup errors now show user-friendly messages with distinct exit codes
- Shared helper functions (`find_layer_index`, `find_material_index`) in `_helpers.py`

### Fixed
- `query.py` used `File3dmObjectTable.Count` which the rhino3dm 8.x
  binding does not expose, raising `AttributeError` on every standalone
  `list_objects` / `document_summary` / `layer_list`. Now uses `len(...)`.
- C# `IOHandler.Screenshot` previously read `output_path` while the
  Python tool sent `path` — both keys are now accepted.
- Global `_RUNTIME` state race condition under concurrent access
- Silent fallback to STANDALONE mode masking configuration errors
- Stale `_connected` flag not updated on transport failure
- Partial buffer data persisting after connection loss

## [0.1.0] - 2025-04-25

### Added
- Initial release
- 51 standalone tools (rhino3dm) + 119 bridge tools (RhinoCommon + Grasshopper)
- Dual-mode architecture: standalone and bridge
- Three transport types: named pipes (Windows), Unix sockets (macOS/Linux), TCP
- FastMCP server with stdio and Streamable HTTP transports
- Docker support with docker-compose
- Bilingual documentation (English + Korean)
- 62 pytest tests with 70% coverage threshold
- 3 example scripts: basic modeling, Grasshopper workflow, parametric facade
