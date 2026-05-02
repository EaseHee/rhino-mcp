"""RhinoScript documentation search and browsing tools.

Provides semantic search across the full rhinoscriptsyntax API reference
so that callers can discover correct function signatures before writing
RhinoScript Python code.  Works in both standalone and bridge mode
because the data is bundled as a static JSON file.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static data (loaded once at import time)
# ---------------------------------------------------------------------------

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "rhinoscriptsyntax.json"
_modules: list[dict[str, Any]] = []


def _ensure_loaded() -> list[dict[str, Any]]:
    global _modules
    if not _modules:
        with open(_DATA_PATH, encoding="utf-8") as f:
            _modules = json.load(f)
        logger.info("Loaded rhinoscriptsyntax: %d modules", len(_modules))
    return _modules


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _score_match(query_terms: list[str], text: str) -> int:
    """Score how well *query_terms* match *text*."""
    text_lower = text.lower()
    score = 0
    for term in query_terms:
        if term in text_lower:
            score += 1
            if f" {term} " in f" {text_lower} " or text_lower.startswith(term) or text_lower.endswith(term):
                score += 1
    return score


def _search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    modules = _ensure_loaded()
    terms = query.lower().split()
    results: list[dict[str, Any]] = []

    for module in modules:
        for fn in module["functions"]:
            searchable = f"{fn['Name']} {fn.get('Description', '')}".lower()
            score = _score_match(terms, searchable)
            score += _score_match(terms, fn.get("Signature", "").lower())

            if score > 0:
                results.append({
                    "name": fn["Name"],
                    "signature": fn.get("Signature", fn["Name"] + "()"),
                    "description": fn.get("Description", "")[:300],
                    "module": module["ModuleName"],
                    "_score": score,
                })

    results.sort(key=lambda r: (-r["_score"], r["name"]))
    for r in results:
        del r["_score"]
    return results[:limit]


def _function_details(function_name: str) -> dict[str, Any] | None:
    for module in _ensure_loaded():
        for fn in module["functions"]:
            if fn["Name"].lower() == function_name.lower():
                return {
                    "name": fn["Name"],
                    "module": module["ModuleName"],
                    "signature": fn.get("Signature", ""),
                    "description": fn.get("Description", ""),
                    "parameters": fn.get("ArgumentDesc", ""),
                    "returns": fn.get("Returns", ""),
                    "example": fn.get("Example", []),
                }
    return None


# ---------------------------------------------------------------------------
# Pydantic input models
# ---------------------------------------------------------------------------


class _SearchIn(BaseModel):
    query: str = Field(..., description="Keywords describing what you want to do.")
    limit: int = Field(10, ge=1, le=50, description="Max results to return.")


class _GetDocsIn(BaseModel):
    topic: str = Field(..., description="Goal or topic to look up (e.g. 'loft surface between curves').")
    include_examples: bool = Field(True, description="Include code examples in output.")
    max_functions: int = Field(5, ge=1, le=20, description="Max functions to return docs for.")


class _ModuleNameIn(BaseModel):
    module_name: str = Field(..., description="Module name (e.g. 'curve', 'surface', 'mesh').")


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def register(mcp: Any, mode: str) -> None:
    @mcp.tool(
        annotations={"title": "Search RhinoScript Functions", "readOnlyHint": True},
    )
    def rhino_search_rhinoscript_functions(args: _SearchIn) -> dict[str, Any]:
        """Search RhinoScript functions by keyword or description.

        Use this BEFORE writing any RhinoScript Python code to find correct
        function names and signatures.  Returns matching functions sorted by
        relevance.

        Example queries: "loft surface", "boolean union", "rotate object",
        "create curve", "extrude".
        """
        results = _search(args.query, args.limit)
        if not results:
            return {
                "summary": {"count": 0, "results": []},
                "text": f"No functions found for '{args.query}'. Try broader terms.",
            }
        return {
            "summary": {"count": len(results), "results": results},
            "text": f"Found {len(results)} function(s) matching '{args.query}'.",
        }

    @mcp.tool(
        annotations={"title": "Get RhinoScript Documentation", "readOnlyHint": True},
    )
    def rhino_get_rhinoscript_docs(args: _GetDocsIn) -> dict[str, Any]:
        """Get comprehensive RhinoScript documentation for a topic.

        CRITICAL: You MUST call this tool before using rhino_execute_python.
        Returns full signatures, parameter descriptions, return values, and
        optional code examples for the most relevant functions.
        """
        search_results = _search(args.topic, args.max_functions)
        if not search_results:
            modules = _ensure_loaded()
            available = sorted({m["ModuleName"] for m in modules})
            return {
                "summary": {"found": 0, "documentation": []},
                "text": (
                    f"No functions found for '{args.topic}'. "
                    f"Available modules: {', '.join(available)}"
                ),
            }

        docs: list[dict[str, Any]] = []
        for result in search_results:
            details = _function_details(result["name"])
            if details:
                if not args.include_examples:
                    details.pop("example", None)
                docs.append(details)

        return {
            "summary": {"found": len(docs), "documentation": docs},
            "text": (
                f"Found {len(docs)} function(s) for '{args.topic}'. "
                "Use these EXACT signatures when writing code. "
                "Import with: import rhinoscriptsyntax as rs"
            ),
        }

    @mcp.tool(
        annotations={"title": "List RhinoScript Modules", "readOnlyHint": True},
    )
    def rhino_list_rhinoscript_modules() -> dict[str, Any]:
        """List all available RhinoScript modules with function counts.

        Use this to discover what areas of the API are available when you
        are not sure which module contains the functions you need.
        """
        modules = _ensure_loaded()
        items = sorted(
            [
                {
                    "module": m["ModuleName"],
                    "function_count": len(m["functions"]),
                    "example_functions": [f["Name"] for f in m["functions"][:5]],
                }
                for m in modules
            ],
            key=lambda x: x["module"],
        )
        total_funcs = sum(i["function_count"] for i in items)
        return {
            "summary": {
                "total_modules": len(items),
                "total_functions": total_funcs,
                "modules": items,
            },
            "text": f"{len(items)} modules with {total_funcs} total functions.",
        }

    @mcp.tool(
        annotations={"title": "Get Module Functions", "readOnlyHint": True},
    )
    def rhino_get_module_functions(args: _ModuleNameIn) -> dict[str, Any]:
        """Get all functions in a specific RhinoScript module with signatures.

        Use rhino_list_rhinoscript_modules() first to see available modules,
        then call this to browse a module's full API.
        """
        target = args.module_name.lower()
        for module in _ensure_loaded():
            if module["ModuleName"].lower() == target:
                functions = [
                    {
                        "name": fn["Name"],
                        "signature": fn.get("Signature", fn["Name"] + "()"),
                        "description": fn.get("Description", "")[:150],
                    }
                    for fn in module["functions"]
                ]
                return {
                    "summary": {
                        "module": module["ModuleName"],
                        "function_count": len(functions),
                        "functions": functions,
                    },
                    "text": f"Module '{module['ModuleName']}' has {len(functions)} functions.",
                }

        available = sorted({m["ModuleName"] for m in _ensure_loaded()})
        return {
            "summary": {"module": args.module_name, "function_count": 0, "functions": []},
            "text": f"Module '{args.module_name}' not found. Available: {', '.join(available)}",
        }
