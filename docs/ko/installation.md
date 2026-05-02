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

체크아웃에서 개발 실행:

```bash
git clone https://github.com/easehee/rhino-mcp.git
cd rhino-mcp
uv sync
uv run rhino-mcp --help
```

### `pip` 사용

```bash
pip install rhino-mcp
rhino-mcp --version
```

Windows에서 named pipe 전송을 쓰려면 옵션 패키지를 설치하세요:

```bash
pip install 'rhino-mcp[windows]'
```

## Rhino 측 브리지 플러그인 설치

브리지는 Rhino 8 내부에서 실행되어 RhinoCommon + Grasshopper를 소켓으로 노출하는 단일 Python 파일(`rhino_plugin/RhinoMCPBridge.py`)입니다.

```bash
python rhino_plugin/install.py
```

스크립트는 Rhino의 scripts 디렉터리에 브리지를 복사합니다:

| OS       | 경로 |
|----------|------|
| Windows  | `%APPDATA%\McNeel\Rhinoceros\8.0\scripts\RhinoMCPBridge.py` |
| macOS    | `~/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/RhinoMCPBridge.py` |
| Linux    | `~/.config/Rhino/8.0/scripts/RhinoMCPBridge.py` |

Rhino 안에서:

```
_-RunPythonScript "<위 경로>"
```

ScriptEditor에 붙여넣어 실행해도 됩니다. 브리지는 시작 시 listening 중인 transport URL을 출력합니다.

## Claude Desktop 설정

`claude_desktop_config.json` 편집(Claude Desktop → *Settings → Developer → Edit Config*):

```json
{
  "mcpServers": {
    "rhino-mcp": {
      "command": "uvx",
      "args": ["rhino-mcp"],
      "env": {
        "RHINO_MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

Claude Desktop을 재시작하면 도구 팔레트(palette)에 `rhino_*`/`gh_*` 도구가 표시됩니다.

## 동작 확인

```bash
RHINO_MCP_FORCE_MODE=standalone uv run rhino-mcp --help
```

또는 MCP Inspector로:

```bash
npx @modelcontextprotocol/inspector uv run rhino-mcp
```
