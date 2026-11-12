# Contributing to rhino-mcp

rhino-mcp에 기여해 주셔서 감사합니다.

## Development Setup

```bash
# Python 3.11+ 필요
git clone https://github.com/EaseHee/rhino-mcp.git
cd rhino-mcp
uv sync
uv pip install -e '.[dev]'
```

## Running Tests

```bash
uv run pytest tests/ -v                    # 전체 테스트
uv run pytest tests/ --cov=src/rhino_mcp   # 커버리지 포함
uv run pytest -m "not live" tests/         # Live Rhino 없이
```

## Code Quality

```bash
uv run ruff check src/ tests/   # 린트
uv run ruff format src/ tests/  # 포매팅
uv run mypy src/rhino_mcp       # 타입 체크
```

## Adding a New Tool

### 1. 도구 모듈 작성

`src/rhino_mcp/tools/<category>.py`에 추가:

```python
from pydantic import BaseModel, Field
from rhino_mcp.tools._helpers import doc, add_object_with_attrs, object_summary, text_for
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.registry import Mode

class _DocArg(BaseModel):
    doc_id: str = Field("active")

class _MyToolIn(_DocArg):
    param: float = Field(..., gt=0, description="Description for LLM.")

def register(mcp, mode: Mode) -> None:
    @mcp.tool(annotations={"title": "My Tool", "readOnlyHint": False})
    def rhino_my_tool(args: _MyToolIn) -> dict:
        if runtime().mode is Mode.BRIDGE:
            return runtime().require_bridge().call("rhino.my.tool", args.model_dump())
        # standalone implementation
        h = doc(args.doc_id)
        # ... rhino3dm logic ...
        return {"summary": object_summary(h, gid, "MyType"), "text": text_for("MyType", gid)}
```

### 2. 서버에 등록

`server.py`의 `_tool_specs()`에 추가:

```python
from rhino_mcp.tools import my_module
# ...
(Mode.BOTH, my_module.register),  # or Mode.BRIDGE for bridge-only
```

### 3. 테스트 작성

`tests/tools/test_<category>.py`:

```python
def test_my_tool(server_standalone):
    mcp, tools = server_standalone
    result = call_tool(tools, "rhino_my_tool", {"param": 5.0})
    assert "summary" in result
```

### 4. 에러 처리

- `parameter_error(name, message)`: 입력 검증 실패
- `not_found_error(what, identifier)`: 객체 미발견
- `unsupported_in_standalone(tool_name)`: Bridge 전용 도구

## Conventions

- **언어**: 코드 주석은 한글, 기술 용어/코드는 원문 유지
- **반환 형식**: `{"summary": {...}, "text": "..."}`
- **Input 모델**: Pydantic BaseModel + `Field(description=...)` (LLM이 읽을 설명)
- **공유 로직**: `_helpers.py`에 배치
- **커밋 메시지**: 영문 제목 + 한글 본문

## Plug-in GUID

`rhino_plugin/csharp/RhinoMCPPlugin.csproj` 의 `PluginGuid`(`880c2dd9-2cb2-4d7f-a3bc-880f628beb87`)는 Rhino 가 이 플러그인을 구별하는 고정 식별자임.
비밀값이 아니며 배포된 `.rhp` 에서도 그대로 보이는 값임.
이 저장소에서는 절대 변경 금지. 바꾸면 설치된 모든 사본이 다른 플러그인으로 취급되고, `tests/test_developer_metadata.py` 가 실패함.

- **포크해서 별도 배포하는 경우 새 GUID 생성 필수** (`uuidgen` 또는 `[guid]::NewGuid()`).
  같은 GUID 로 배포하면 두 플러그인을 함께 설치한 사용자에게서 "ID already in use" 충돌 발생.
  테스트의 `PLUGIN_GUID` 도 함께 변경.
- **개발 PC 주의**: 로컬 빌드와 Package Manager 설치본이 같은 ID 라 동시에 로드 불가.
  로컬 빌드를 Rhino 에서 시험하려면 먼저 Package Manager 설치본 제거.
  설치본을 유지하는 동안에는 `-p:SkipPluginCopy=true`(또는 `build-plugin.sh --no-install`)로 빌드해 두 번째 사본이 Rhino 설치 경로에 들어가지 않게 함.

## Pull Request Guidelines

1. 기존 테스트가 모두 통과하는지 확인
2. 새 도구에는 반드시 테스트 추가
3. `ruff check`와 `mypy` 통과 필수
4. PR 설명에 변경 이유와 테스트 방법 명시
