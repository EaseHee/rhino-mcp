# 설치(Installation)

## 사전 요구 사항(Prerequisites)

- Python 3.11 이상.
- (선택) McNeel Rhino 8 — **브리지(bridge) 모드**에서만 필요(RhinoCommon, viewport, render, Grasshopper).
- (선택) Docker — 컨테이너로 실행하려는 경우.

## 서버 설치

### `uv` 사용(권장)

```bash
uv tool install rhino-mcp
```

git clone본에서 개발 실행:

```bash
git clone https://github.com/easehee/rhino-mcp.git
cd rhino-mcp
uv sync
uv run rhino-mcp --help
```

### `pip` 사용

```bash
pip install rhino3dm-mcp
rhino-mcp --version
```

Windows에서 named pipe 전송 사용 시 옵션 패키지 설치 필요:

```bash
pip install 'rhino3dm-mcp[windows]'
```

## Rhino 측 브리지 플러그인 설치

브리지: Rhino 8 내부에서 실행되며 RhinoCommon + Grasshopper를 JSON-RPC 소켓으로 노출하는 C# Rhino 플러그인(`rhino_plugin/csharp/`).

```bash
dotnet build rhino_plugin/csharp -c Release
```

빌드 산출물 경로: `rhino_plugin/csharp/bin/Release/net8.0/rhino-mcp.rhp`.
Rhino 8 뷰포트에 `.rhp` 드래그-앤-드롭(또는 `_PluginManager`)으로 1회 로드 → 플러그인이 플랫폼 기본 transport(Windows: 명명된 파이프, macOS/Linux: Unix domain socket)에서 JSON-RPC 리스너 시작.
MCP 서버 기동 시 자동 감지.

## Claude Desktop 설정

`claude_desktop_config.json` 편집(Claude Desktop → *Settings → Developer → Edit Config*):

```json
{
  "mcpServers": {
    "rhino-mcp": {
      "command": "uvx",
      "args": ["rhino3dm-mcp"],
      "env": {
        "RHINO_MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

Claude Desktop 재시작 후 도구 팔레트(palette)에 `rhino_*`/`gh_*` 도구 표시.

## 동작 확인

```bash
RHINO_MCP_FORCE_MODE=standalone uv run rhino-mcp --help
```

또는 MCP Inspector로:

```bash
npx @modelcontextprotocol/inspector uv run rhino-mcp
```
