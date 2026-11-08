"""Progress forwarding must not deadlock with a sync bridge tool on the loop.

``BridgeClient`` calls ``on_progress`` while holding its request lock, and
FastMCP runs sync tools directly on the event loop. If the progress hook
waited for the loop, a sync tool blocked on the same lock from the loop
thread would never let it finish.
"""

from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace
from typing import Any

from rhino_mcp.tools._helpers import run_with_progress


class _FakeCtx:
    def __init__(self) -> None:
        self.request_context = SimpleNamespace(meta=SimpleNamespace(progressToken="tok"))
        self.reported: list[tuple[float, float | None, str | None]] = []

    async def report_progress(self, progress: float, total: float | None, message: str | None) -> None:
        self.reported.append((progress, total, message))


def test_sync_tool_on_loop_does_not_deadlock_with_progress_hook() -> None:
    bridge_lock = threading.Lock()
    hook_entered = threading.Event()

    def bridge_call(*, on_progress: Any) -> str:
        # Mirrors BridgeClient: progress frames are dispatched under the lock.
        with bridge_lock:
            hook_entered.set()
            # Let the loop thread reach bridge_lock.acquire() before the first frame.
            time.sleep(0.2)
            on_progress(1, 3, "step 1")
            on_progress(None, None, "message only")
            on_progress(3, 3, "done")
        return "ok"

    async def scenario() -> tuple[str, bool, list[Any]]:
        ctx = _FakeCtx()
        task = asyncio.create_task(run_with_progress(ctx, bridge_call))  # type: ignore[arg-type]
        while not hook_entered.is_set():
            await asyncio.sleep(0.001)
        # A sync tool now blocks the loop thread on the bridge lock.
        start = time.monotonic()
        acquired = bridge_lock.acquire(timeout=2.0)
        if acquired:
            bridge_lock.release()
        blocked_for = time.monotonic() - start
        result = await asyncio.wait_for(task, timeout=5.0)
        return result, acquired and blocked_for < 1.5, ctx.reported

    result, lock_released_promptly, reported = asyncio.run(scenario())
    assert result == "ok"
    assert lock_released_promptly, "progress hook held the bridge lock while waiting on the loop"
    import math

    # The message-only frame is nudged just above the previous value to stay strictly increasing.
    assert reported == [(1, 3, "step 1"), (math.nextafter(1, math.inf), None, "message only"), (3, 3, "done")]


def test_no_progress_token_skips_forwarding() -> None:
    seen: list[Any] = []

    def bridge_call(*, on_progress: Any) -> str:
        seen.append(on_progress)
        return "ok"

    ctx = _FakeCtx()
    ctx.request_context = SimpleNamespace(meta=None)
    assert asyncio.run(run_with_progress(ctx, bridge_call)) == "ok"  # type: ignore[arg-type]
    assert seen == [None]
