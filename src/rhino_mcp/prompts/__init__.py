"""MCP prompt definitions exposed to clients (e.g. Claude Desktop).

Prompts are short, opinionated guides the LLM can read before issuing tool
calls. Keeping them in their own package mirrors the ``tools/`` layout so
adding new prompts only requires registering a function here.
"""

from rhino_mcp.prompts.strategy import (
    general_strategy,
    rhinoscript_workflow,
    viewport_workflow,
)

__all__ = [
    "general_strategy",
    "rhinoscript_workflow",
    "viewport_workflow",
]
