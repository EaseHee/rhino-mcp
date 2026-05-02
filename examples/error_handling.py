"""Error-handling patterns example.

Shows how to react to tool failures using rhino-mcp's ToolError
hierarchy and ErrorCategory enum.
"""

from rhino_mcp.tools.context import set_runtime
from rhino_mcp.utils.error_handling import ErrorCategory, ToolError
from rhino_mcp.utils.registry import Mode

set_runtime(Mode.STANDALONE, None)


def demo_parameter_error() -> None:
    """Handle an invalid parameter."""
    from rhino_mcp.utils.error_handling import parameter_error

    try:
        raise parameter_error("radius", "must be positive", allowed=">0")
    except ToolError as e:
        print(f"[{e.category.value}] {e.message}")
        print(f"  Hint: {e.hint}")
        print(f"  Details: {e.details}")


def demo_not_found_error() -> None:
    """Handle a missing object lookup."""
    from rhino_mcp.utils.error_handling import not_found_error

    try:
        raise not_found_error("layer", "NonExistentLayer")
    except ToolError as e:
        print(f"\n[{e.category.value}] {e.message}")
        print(f"  Hint: {e.hint}")
        # Branch by category.
        if e.category == ErrorCategory.NOT_FOUND:
            print("  -> can retry after creating the object")


def demo_unsupported_error() -> None:
    """Handle a bridge-only tool called in standalone mode."""
    from rhino_mcp.utils.error_handling import unsupported_in_standalone

    try:
        raise unsupported_in_standalone("rhino_loft_surface")
    except ToolError as e:
        print(f"\n[{e.category.value}] {e.message}")
        print(f"  Hint: {e.hint}")
        if e.category == ErrorCategory.UNSUPPORTED:
            print("  -> switch to Rhino 8 bridge mode")


def demo_error_to_dict() -> None:
    """Convert an error to a JSON-serialisable dict."""
    from rhino_mcp.utils.error_handling import parameter_error

    err = parameter_error("count", "must be between 3 and 256", allowed="3-256")
    error_dict = err.to_dict()
    print(f"\nSerialized error: {error_dict}")


if __name__ == "__main__":
    demo_parameter_error()
    demo_not_found_error()
    demo_unsupported_error()
    demo_error_to_dict()
