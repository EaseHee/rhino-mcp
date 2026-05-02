# Contributing to rhino-mcp

rhino-mcp에 기여해 주셔서 감사합니다.

## Development Setup

```bash
# Python 3.11+ 필요
git clone https://github.com/easehee/rhino-mcp.git
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

## Pull Request Guidelines

1. 기존 테스트가 모두 통과하는지 확인
2. 새 도구에는 반드시 테스트 추가
3. `ruff check`와 `mypy` 통과 필수
4. PR 설명에 변경 이유와 테스트 방법 명시
