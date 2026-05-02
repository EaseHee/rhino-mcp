"""에러 처리 패턴 예제.

rhino-mcp의 ToolError 계층과 ErrorCategory를 활용하여
도구 호출 실패 시 적절히 대응하는 방법을 보여준다.
"""

from rhino_mcp.tools.context import set_runtime
from rhino_mcp.utils.error_handling import ErrorCategory, ToolError
from rhino_mcp.utils.registry import Mode

set_runtime(Mode.STANDALONE, None)


def demo_parameter_error() -> None:
    """잘못된 파라미터 처리."""
    from rhino_mcp.utils.error_handling import parameter_error

    try:
        raise parameter_error("radius", "must be positive", allowed=">0")
    except ToolError as e:
        print(f"[{e.category.value}] {e.message}")
        print(f"  Hint: {e.hint}")
        print(f"  Details: {e.details}")


def demo_not_found_error() -> None:
    """존재하지 않는 객체 처리."""
    from rhino_mcp.utils.error_handling import not_found_error

    try:
        raise not_found_error("layer", "NonExistentLayer")
    except ToolError as e:
        print(f"\n[{e.category.value}] {e.message}")
        print(f"  Hint: {e.hint}")
        # 카테고리별 분기 처리
        if e.category == ErrorCategory.NOT_FOUND:
            print("  → 객체 생성 후 재시도 가능")


def demo_unsupported_error() -> None:
    """Bridge 전용 도구의 standalone 호출 처리."""
    from rhino_mcp.utils.error_handling import unsupported_in_standalone

    try:
        raise unsupported_in_standalone("rhino_loft_surface")
    except ToolError as e:
        print(f"\n[{e.category.value}] {e.message}")
        print(f"  Hint: {e.hint}")
        if e.category == ErrorCategory.UNSUPPORTED:
            print("  → Rhino 8 Bridge 모드로 전환 필요")


def demo_error_to_dict() -> None:
    """에러를 JSON 직렬화 가능한 dict로 변환."""
    from rhino_mcp.utils.error_handling import parameter_error

    err = parameter_error("count", "must be between 3 and 256", allowed="3-256")
    error_dict = err.to_dict()
    print(f"\nSerialized error: {error_dict}")


if __name__ == "__main__":
    demo_parameter_error()
    demo_not_found_error()
    demo_unsupported_error()
    demo_error_to_dict()
