# Troubleshooting

## Quick diagnostic

```bash
./scripts/check-bridge.sh
```

항목별 PASS / FAIL / WARN 결과와 수정 방법을 출력합니다.

---

## Bridge 연결 설정 (Rhino 내부)

서버가 standalone 모드로 시작되는 가장 흔한 원인 — **C# 브리지 플러그인이 Rhino 8에 미로드된 상태**.

### 1단계 — 플러그인 빌드 (최초 1회)

```bash
dotnet build rhino_plugin/csharp -c Release
```

산출물 경로: `rhino_plugin/csharp/bin/Release/net8.0/rhino-mcp.rhp`.

### 2단계 — Rhino 8에 .rhp 로드

`.rhp` 파일을 Rhino 뷰포트로 드래그-앤-드롭하거나 `_PluginManager` → *Install...* 로 1회 로드 → 이후 Rhino 재시작에도 유지. `_-PluginManager`에서 `rhino-mcp` 항목 확인 시 정상.

**성공 시** Rhino CommandHistory 창에 출력:

```
[rhino-mcp] listening on unix:///tmp/rhino_mcp.sock    ← macOS/Linux
[rhino-mcp] listening on \\.\pipe\rhino_mcp            ← Windows
[rhino-mcp] listening on tcp://127.0.0.1:4242          ← TCP 강제 시
```

### 3단계 — 서버 연결 확인

```bash
./scripts/check-bridge.sh
```

"Bridge responded to ping" 메시지와 함께 Rhino/GH 버전이 출력되면 정상입니다.

---

## Transport별 연결 방식

| 플랫폼    | 기본 Transport | 소켓/파이프 경로 |
|-----------|----------------|------------------|
| macOS     | Unix socket    | `/tmp/rhino_mcp.sock` (또는 `$RHINO_MCP_SOCKET`) |
| Linux     | Unix socket    | `$XDG_RUNTIME_DIR/rhino_mcp.sock` 또는 `/tmp/rhino_mcp.sock` |
| Windows   | Named pipe     | `\\.\pipe\rhino_mcp` |
| 모든 플랫폼 | TCP (선택)   | `$RHINO_HOST:$RHINO_PORT` (기본 `localhost:4242`) |

TCP를 강제로 사용하려면:

```bash
# Rhino 환경에서 (bridge 측)
export RHINO_MCP_TRANSPORT_KIND=tcp  # 또는 Windows: set

# MCP 서버 측
RHINO_MCP_TRANSPORT_KIND=tcp uv run rhino-mcp
```

소켓 경로를 직접 지정하려면:

```bash
export RHINO_MCP_SOCKET=/custom/path/rhino.sock  # bridge + server 양쪽에 동일하게 설정
```

---

## 자주 발생하는 오류

### "Cannot reach Rhino bridge."

```
Error: server startup failed — Cannot reach Rhino bridge.
```

체크리스트:

1. **Rhino 8이 실행 중인지** 확인
2. **Bridge가 실행 중인지** 확인 (`_-RunPythonScript` 실행 여부)
3. **소켓 파일 존재 여부** 확인 (macOS):
   ```bash
   ls -la /tmp/rhino_mcp.sock
   ```
4. **포트/경로 일치 여부** — `RHINO_HOST` / `RHINO_PORT` / `RHINO_MCP_SOCKET`이 bridge와 서버 양쪽에서 같은지 확인
5. **진단 스크립트** 실행:
   ```bash
   ./scripts/check-bridge.sh
   ```

### Bridge가 실행 중이지만 서버가 인식하지 못함

macOS에서 Unix 소켓 파일이 있지만 연결이 안 될 때:

```bash
# 소켓 상태 확인
ls -la /tmp/rhino_mcp.sock
file /tmp/rhino_mcp.sock   # → "socket" 타입이어야 함

# TCP로 전환하여 테스트
RHINO_MCP_TRANSPORT_KIND=tcp ./scripts/check-bridge.sh --tcp
```

Rhino를 재시작했다면 브리지도 다시 실행해야 합니다 (소켓이 새로 생성됨).

### "Tool 'X' requires Rhino bridge mode."

서버가 standalone으로 시작된 뒤 bridge-only 도구를 호출할 때:

1. Rhino 8에서 bridge를 시작하고
2. `rhino-mcp` 서버를 재시작:
   ```bash
   ./scripts/run.sh --bridge
   # 또는 connector 모드 (자동 fallback 있음):
   ./scripts/run.sh --connector --bridge
   ```

### Grasshopper 베이크가 비어있음

- `gh_bake_to_rhino` 전에 `gh_run` 실행
- `gh_get_parameter`로 컴포넌트 출력 확인
- 일부 컴포넌트는 geometry가 아닌 data만 생성

### stdio transport 손상 (Claude Desktop)

Claude Desktop에서 JSON 디코드 오류가 나타나면 stdout에 출력이 발생 중입니다.

```bash
RHINO_MCP_LOG_LEVEL=DEBUG uv run rhino-mcp  # 모든 로그가 stderr인지 확인
```

`rhino-mcp`는 stdout을 MCP 프레임 전용으로 예약하고, 로그는 항상 stderr로 씁니다.

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

# Bridge 모드에서 디버그 로그:
RHINO_MCP_FORCE_MODE=bridge RHINO_MCP_LOG_LEVEL=DEBUG uv run rhino-mcp

# MCP Inspector로 도구 목록 확인:
npx @modelcontextprotocol/inspector uv run rhino-mcp
```
