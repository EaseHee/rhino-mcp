# Troubleshooting

## Quick diagnostic

```bash
./scripts/check-bridge.sh
```

브리지 감지 단계(TCP 포트, JSON-RPC ping, 모드 판정)별 PASS / FAIL / WARN 결과와 수정 방법 출력.
브리지가 응답하면 실행 중인 Rhino 메이저 버전과 플러그인 빌드 대상 메이저 버전도 출력하고, 둘이 다르면 경고.

---

## Bridge 연결 설정 (Rhino 8 / Rhino 9)

서버가 standalone 모드로 시작되는 가장 흔한 원인은 **C# 브리지 플러그인이 Rhino 에 로드되지 않은 상태**.

### 1단계 — 플러그인 준비

Rhino Package Manager 에서 설치(Rhino 9 는 `rh9`, Rhino 8 은 `rh8` 패키지)하거나 로컬 빌드:

```bash
./scripts/build-plugin.sh --release              # Rhino 9 (기본)
./scripts/build-plugin.sh --release --rhino=8    # Rhino 8
./scripts/build-plugin.sh --release --rhino=both --no-install   # 빌드만
```

스크립트는 `dotnet build rhino_plugin/csharp -c Release -p:RhinoMajor=<8|9>` 를 감싸며 산출물 경로는 `rhino_plugin/csharp/bin/rh<N>/Release/net8.0/rhino-mcp.rhp`.
`/Applications/Rhino <N>.app`(macOS) 또는 `%APPDATA%/McNeel/Rhinoceros/<N>.0/`(Windows) 가 있으면 빌드 후 그 위치로 자동 복사.

### 2단계 — .rhp 로드

`.rhp` 파일을 Rhino 뷰포트로 드래그-앤-드롭하거나 `_PluginManager` → *Install...* 로 1회 로드.
이후 Rhino 재시작에도 유지.
`_-PluginManager` 에서 `rhino-mcp` 항목이 보이면 정상.

**성공 시** Rhino CommandHistory 창 출력:

```
[rhino-mcp] Plugin loaded. Type "_McpInstall" to register rhino-mcp with Claude Desktop, Claude Code, Codex or Antigravity.
[rhino-mcp] listening on tcp://127.0.0.1:4242 (protocol=...)
```

두 번째 Rhino 인스턴스는 다음 빈 포트(4243, 4244, … 최대 4257) 사용.

### 3단계 — MCP 클라이언트 등록

Rhino 에서 `_McpInstall` 입력 후 클라이언트 선택, 또는 터미널에서 `rhino-mcp install --client detected`.
클라이언트별 대상과 옵션은 [installation.md](installation.md) 참고.

### 4단계 — 서버 연결 확인

```bash
./scripts/check-bridge.sh
```

"Bridge responded to ping" 메시지와 함께 Rhino/GH 버전이 출력되면 정상.

---

## Transport별 연결 방식

C# 플러그인은 **TCP 전용**으로 수신: `127.0.0.1:4242`, 여러 Rhino 인스턴스가 있으면 4257 까지의 다음 빈 포트.
서버는 listener 공지 파일(아래 *다중 Rhino 인스턴스* 참고)과 `RHINO_HOST` / `RHINO_PORT`(기본 `localhost:4242`)로 인스턴스 탐색.

v0.4 이전 Python 브리지와의 호환을 위해 서버는 TCP 이전에 Unix socket(macOS / Linux 에서 `/tmp/rhino_mcp.sock` 파일이 있을 때) 또는 named pipe(Windows `\\.\pipe\rhino_mcp`)도 시도.
현재 플러그인은 둘 다 제공하지 않으므로, 기동이 느리면 이 탐색을 생략:

```bash
RHINO_MCP_TRANSPORT_KIND=tcp uv run rhino-mcp
```

---

## 자주 발생하는 오류

### "Cannot reach Rhino bridge."

체크리스트:

1. **Rhino 8 또는 Rhino 9 실행 여부** 확인.
2. **`rhino-mcp.rhp` C# 플러그인 로드 여부**: Rhino 패키지 매니저 설치 또는 로컬 빌드(`./scripts/build-plugin.sh --release`).
   플러그인 OnLoad 시점에 브리지 자동 시작, 별도 스크립트 실행 불필요.
3. **TCP 포트 도달 가능 여부**: 기본 `127.0.0.1:4242`. `nc -z 127.0.0.1 4242` 로 확인.
4. **환경 변수 일치**: 기본값을 바꿨다면 `RHINO_HOST` / `RHINO_PORT` 가 원하는 인스턴스를 가리키는지 확인.
5. **진단 스크립트**: `./scripts/check-bridge.sh`.

### Bridge 실행 중이지만 서버가 인식하지 못함

v0.5.1+: 플러그인이 응답 가능해진 뒤 첫 bridge 전용 도구 호출 시 lazy promotion 으로 BRIDGE 모드 자동 전환.
v0.7.0 부터는 standalone 경로로 처리할 수 없는 요청을 받은 양모드 도구도 브리지를 재탐색해 bridge 경로로 재실행.
MCP 서버 재시작 불필요.

Promotion 미발생 시:

```bash
# Rhino 명령창에서 _PluginManager 입력 → "rhino-mcp" 항목 "Loaded" 상태 확인
# 진단 재실행:
./scripts/check-bridge.sh
```

`RHINO_MCP_FORCE_MODE=standalone` 에서는 MCP 리소스와 양모드 도구 모두 승격하지 않음. bridge 전용 도구는 호출 시 브리지 연결을 계속 시도.

### "Tool 'X' requires Rhino bridge mode."

해당 작업에 RhinoCommon 이 필요한데(예: 비-3DM 파일 `rhino_import`, `rhino_export_step`) 도달 가능한 브리지가 없는 상태.
서버는 이 오류를 반환하기 전에 브리지를 재탐색(최대 `RHINO_MCP_REDETECT_COOLDOWN` 초마다 1회, 기본 5)하고, 플러그인이 응답하면 그 도구를 bridge 경로로 실행.
플러그인 로드 후 같은 도구를 다시 호출하면 됨. 곧바로 같은 오류가 나면 cooldown 경과 후 재호출.
`RHINO_MCP_FORCE_MODE=standalone` 에서는 재탐색하지 않으므로 이 값을 지우고 서버 재시작.

### "Plug-in was built for Rhino N" 경고

```
Bridge on tcp://... runs in Rhino 9 but the plug-in was built for Rhino 8. Install the rh9 package from the Rhino Package Manager.
```

다른 메이저용 `net8.0` 빌드도 대개 로드됨(Rhino 9 는 .NET 10 위에서 roll-forward). 다만 RhinoCommon API 차이는 보장 범위 밖.
맞는 패키지를 설치하거나 `./scripts/build-plugin.sh --release --rhino=<실행 중인 메이저>` 로 재빌드.
플러그인 로드 시 Rhino 명령창에도 같은 안내 출력.

### 플러그인은 로드되지만 플러그인 관리자에 없음 (0.7.0 ~ 0.7.2)

브리지는 켜진 뒤 Rhino 가 `Object reference not set to an instance of an object` 와 "개발자가 연락처 정보를 포함하지 않았습니다" 문구를 띄우고, 플러그인 관리자 목록에 rhino-mcp 가 없음.
해당 빌드에는 어셈블리 GUID 가 없어 Rhino 가 플러그인 ID 를 `00000000-0000-0000-0000-000000000000` 으로 읽고, `OnLoad` 직후 등록에 실패함.
Package Manager 에서 0.7.3 이상으로 업데이트.
수동 정리는 불필요함. 이전 빌드는 등록된 적이 없고, Package Manager 가 업데이트 때 이전 버전 폴더를 지움.

### 플러그인 로드 시 "ID already in use"

같은 GUID 의 플러그인이 이미 로드된 상태.
0.7.3 부터 로컬 빌드와 Package Manager 설치본이 같은 고정 ID 를 쓰므로, 개발 PC 에서 둘이 함께 있을 때 주로 발생.
한 번에 하나만 로드되므로, 로컬 빌드를 로드하기 전에 Package Manager 에서 패키지 제거.
패키지를 유지하는 동안에는 `-p:SkipPluginCopy=true`(또는 `./scripts/build-plugin.sh --no-install`)로 빌드해 Rhino 설치 경로에 두 번째 사본이 생기지 않게 함. 충돌은 피하지만 로컬 빌드를 로드할 수는 없음.
`./scripts/build-plugin.sh` 는 Package Manager 설치본을 발견하면 경고 출력.
포크가 같은 GUID 로 배포된 경우라면 그 포크 쪽에서 새 GUID 를 생성해야 함 (`CONTRIBUTING.md` 참고).

### `_McpInstall` 이 "No launcher provides rhino-mcp X or newer" 출력

`_McpInstall` 은 플러그인 버전 이상의 서버가 필요함.
찾은 런처마다 `--version` 을 실행(uvx 는 `--from rhino3dm-mcp>=<플러그인 버전>`, 이어서 PATH 와 `~/.local/bin` 의 모든 `rhino-mcp` 스크립트, 마지막으로 모든 `python3` / `python` 의 `-m rhino_mcp.server`)해 조건을 만족하는 첫 런처를 사용.
건너뛴 런처는 사유와 함께 출력. 예: `no rhino3dm-mcp>=0.7.0 on PyPI yet`, `server 0.6.0 is older than 0.7.0`.

만족하는 런처가 없으면(대개 PyPI 배포 전) 로컬 체크아웃에서 서버를 설치한 뒤 `_McpInstall` 재실행:

```bash
uv tool install --force --from /path/to/rhino-mcp rhino3dm-mcp   # ~/.local/bin 에 rhino-mcp 설치
```

PyPI 배포 이후에는 `uv tool upgrade rhino3dm-mcp`(또는 `uvx --refresh rhino3dm-mcp --version`)로 충분.
등록되는 항목은 검사를 통과한 런처 기준: `uvx --from rhino3dm-mcp>=<버전> rhino3dm-mcp` 또는 해당 설치본 자신의 `rhino-mcp` 스크립트 절대 경로.

### 클라이언트에 rhino-mcp 도구가 보이지 않음

- 등록 상태 확인: `rhino-mcp install --list-clients`.
  `error` 는 설정 파일 파싱 실패. 파일을 고치거나 옆의 `.bak.<timestamp>` 백업으로 복원.
- 설치 후 클라이언트 재시작(Claude Desktop·Codex·Antigravity 는 시작 시 설정을 읽음).
- Claude Code: `claude mcp list` 에 user scope 로 `rhino-mcp` 가 보여야 정상.
- 항목 `env` 의 `RHINO_MCP_TOOLSETS` 가 그룹을 숨기는 경우. 값을 지우거나 필요한 그룹(`core,bim,freeform,gh,render,scripting,docs`) 추가.

### Rhino 에서는 열리는 3dm 이 standalone 에서 안 열림

rhino3dm 8.35 는 archive version 90(Rhino 9)까지 읽기 가능.
그보다 새 파일은 오류에 `archive_version` 이 표시되고 bridge 모드 사용이나 구버전 형식 재저장을 안내.
버전은 알려진 값인데 `unreadable or corrupt` 라면 대개 잘린 파일.

### McNeel RhinoMCP 와 함께 설치된 경우

Rhino 9 내장 RhinoMCP(`MCPStart` / `MCPConnect`)는 HTTP 10500, rhino-mcp 는 TCP 4242 이상을 사용하므로 동시 실행 가능.
MCP 클라이언트에는 서로 다른 이름으로 등록(rhino-mcp 기본 이름은 `rhino-mcp`)해 항목이 서로 덮어쓰지 않게 함.

### 뷰포트 캡처가 이미지를 반환하지 않음

`rhino_screenshot`, `rhino_viewport_preview`, `rhino_viewport_image` 가 "Viewport capture returned no image" 로 실패하면 플러그인이 이미지 데이터를 보내지 않은 상태.
구버전 플러그인은 인라인 이미지 요청을 무시하므로 서버와 같은 버전으로 플러그인 갱신.
플러그인이 최신이면 뷰포트가 보이는 상태인지 확인 후 재시도.
이미지 반환 없이 파일만 저장하려면 `path` 와 함께 `include_image=false` 지정.

### `rhino_cylinder` 에서 "Invalid parameter: axis"

standalone 모드의 `rhino3dm` 은 임의 평면에 원을 배치하지 못함.
world-Z 축(`{x:0,y:0,z:1}`)을 쓰거나 bridge 모드로 전환.

### "non-3DM" import 오류

standalone 의 `rhino_import` 는 `.3dm` 만 처리.
STEP/IGES/DXF import 는 Rhino importer 가 필요하므로 bridge 모드 사용.

### stdio transport 손상

MCP 클라이언트에서 JSON 디코드 오류가 나면 stdout 으로 출력이 새는 상태.

```bash
RHINO_MCP_LOG_LEVEL=DEBUG uv run rhino-mcp  # 모든 로그가 stderr인지 확인
```

`rhino-mcp` 는 stdout 을 MCP 프레임 전용으로 쓰고 로그는 항상 stderr 로 출력.

### Grasshopper 베이크가 비어있음

- `gh_bake_to_rhino` 전에 `gh_run` 실행
- `gh_get_parameter` 로 컴포넌트 출력 확인
- 일부 컴포넌트는 geometry 가 아닌 data 만 생성

### 다중 Rhino 인스턴스 — 의도한 문서가 응답 안 함 (v0.6)

증상: 도구가 *다른* Rhino 도큐먼트를 편집하거나, 2개 이상 떠 있는데 `rhino_bridge_list_instances` 가 0/1개만 반환.

점검:

1. `RHINO_MCP_LISTENER_DIR` 디렉토리에서 listener 파일 확인.
   기본값: POSIX `${TMPDIR:-/tmp}/rhino-mcp-listeners`, Windows `%LOCALAPPDATA%/rhino-mcp/listeners`.

   ```bash
   ls /tmp/rhino-mcp-listeners/
   ```

   인스턴스당 `{pid}-{port}.json` 1개 기대.

2. Rhino 2개 중 1개만 파일이 보이면 그 Rhino 는 v0.6 이전 플러그인 빌드(announcement writer 미포함).
   재빌드 + 재로드:

   ```bash
   ./scripts/build-plugin.sh --release --rhino=9   # 또는 --rhino=8
   ```

3. 활성 인스턴스 전환:

   ```text
   rhino_bridge_list_instances()
   rhino_bridge_select_instance(doc_path_contains="site.3dm")
   ```

4. stale 항목 정리(Rhino crash 로 청소 못한 경우): 다음 `rhino_bridge_list_instances` 호출 시 `stale_cleanup=true`(기본)로 PID 가 사라진 JSON 자동 삭제.

### `rhino_execute_csharp` 실행 전 거절

에러 메시지에 `C# execution is disabled. Set RHINO_MCP_ALLOW_CSHARP=1` 포함.
opt-in 환경변수 게이트는 **rhino-mcp 서버**가 읽으므로 MCP 클라이언트 항목의 `env` 블록(또는 서버를 띄우는 셸)에 설정한 뒤 서버 재시작:

```json
"env": { "RHINO_MCP_TRANSPORT": "stdio", "RHINO_MCP_ALLOW_CSHARP": "1" }
```

`rhino-mcp install --force` 는 이렇게 사용자가 추가한 env 키를 보존.
게이트는 의도적 설계. Roslyn 스크립트는 RhinoCommon 전체 접근 권한 보유.

---

## Error categories

| Category         | Meaning |
|------------------|---------|
| `connection`     | Bridge unreachable |
| `timeout`        | Bridge response timeout |
| `parameter`      | Input value rejected (range/type error) |
| `not_found`      | Document/object/layer identifier not found |
| `unsupported`    | Tool requires bridge mode, server is standalone |
| `gh_component`   | Grasshopper component name match failed |
| `internal`       | Bridge raised exception; `details` contains Python trace |

---

## Diagnostics

```bash
# Bridge 연결 전체 점검:
./scripts/check-bridge.sh

# Standalone 모드에서 도구 목록 확인:
RHINO_MCP_FORCE_MODE=standalone uv run python -c \
  "from rhino_mcp.server import build_server; from rhino_mcp.utils.registry import Mode; \
   m,c=build_server(runtime_mode=Mode.STANDALONE); \
   import pprint; mgr=getattr(m,'_tool_manager',None); \
   pprint.pprint(sorted(mgr._tools.keys()) if mgr else [])"

# 일부 도구 그룹만 등록:
./scripts/run.sh --toolsets core,gh

# Bridge 모드에서 디버그 로그:
RHINO_MCP_FORCE_MODE=bridge RHINO_MCP_LOG_LEVEL=DEBUG uv run rhino-mcp

# 클라이언트 등록 상태:
uv run rhino-mcp install --list-clients

# MCP Inspector로 도구 목록 확인:
npx @modelcontextprotocol/inspector uv run rhino-mcp
```
