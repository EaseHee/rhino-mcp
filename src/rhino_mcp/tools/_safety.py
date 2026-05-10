"""Static safety checks for user-supplied script payloads.

These run before a payload is forwarded to the Rhino bridge.  They block
calls that are known to break the JSON-RPC transport (modal Rhino commands
that wait for stdin, selection-set side-effects that bypass the
RhinoCommon API, etc.) so that a single bad ``rhino_execute_python`` call
does not knock the bridge offline for the rest of the session.

The check is opt-out via ``RHINO_MCP_ALLOW_MODAL_COMMAND=1`` for cases
where the caller has accepted the risk.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from rhino_mcp.utils.error_handling import parameter_error


@dataclass(frozen=True)
class _Pattern:
    rx: re.Pattern[str]
    hint: str


# Patterns match `rs.Command("_Verb ...")` / `rs.Command('_Verb ...')` —
# i.e. the modal command keyword is the literal first token of an inline
# string argument.  This deliberately excludes:
#   - cases where the command string is built into a variable
#     (still risky, but harder to statically prove without an AST)
#   - mentions inside docstrings / help text that don't follow rs.Command
#   - method names like rs.MoveObjects (no _Move keyword inside the call)
_INLINE_CMD_STRING = r"""rs\.Command\s*\(\s*['"]\s*"""

_DANGEROUS_PATTERNS: list[_Pattern] = [
    _Pattern(
        re.compile(_INLINE_CMD_STRING + r"_Move\b", re.IGNORECASE),
        "use rs.MoveObjects(ids, vector) instead — modal _Move blocks the bridge thread",
    ),
    _Pattern(
        re.compile(_INLINE_CMD_STRING + r"_Mirror\b", re.IGNORECASE),
        "use rs.MirrorObjects(ids, start, end, copy) instead",
    ),
    _Pattern(
        re.compile(_INLINE_CMD_STRING + r"_Rotate\b", re.IGNORECASE),
        "use rs.RotateObjects(ids, center, angle, axis, copy) instead",
    ),
    _Pattern(
        re.compile(_INLINE_CMD_STRING + r"_Copy\b", re.IGNORECASE),
        "use rs.CopyObjects(ids, vector) instead",
    ),
    _Pattern(
        re.compile(_INLINE_CMD_STRING + r"_Scale\b", re.IGNORECASE),
        "use rs.ScaleObjects(ids, origin, scale, copy) instead",
    ),
    _Pattern(
        re.compile(_INLINE_CMD_STRING + r"_SelLayer\b", re.IGNORECASE),
        "use rs.ObjectsByLayer(name) to enumerate, then call the API directly",
    ),
    _Pattern(
        re.compile(_INLINE_CMD_STRING + r"_Layer\s+_Assign\b", re.IGNORECASE),
        "use rs.ObjectLayer(ids, layer) — note the 500 ids/call practical cap",
    ),
]


def check_python_payload(code: str) -> None:
    """Reject payloads that contain bridge-hostile rs.Command patterns.

    Raises ``parameter_error`` on the first match so the caller gets a
    clear, single-source remediation hint.  Set
    ``RHINO_MCP_ALLOW_MODAL_COMMAND=1`` in the environment to bypass.
    """
    if os.environ.get("RHINO_MCP_ALLOW_MODAL_COMMAND") == "1":
        return
    for pat in _DANGEROUS_PATTERNS:
        m = pat.rx.search(code)
        if m is not None:
            raise parameter_error(
                "code",
                (
                    f"Pattern '{m.group(0)}' is known to break the bridge — {pat.hint}. "
                    "Set RHINO_MCP_ALLOW_MODAL_COMMAND=1 to bypass at your own risk"
                ),
            )
