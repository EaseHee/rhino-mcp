"""Bench rhino_batch_call vs direct sequential calls against a live bridge.

Requires a running Rhino 8 with the rhino-mcp bridge plugin loaded.
Connect to it through ``BridgeClient.auto()`` and time:

  1. N direct ``rhino.layer.create`` calls (one round-trip each).
  2. One ``rhino.batch.execute`` call with the same N steps.

Run with ``RHINO_MCP_LOG_LEVEL=DEBUG`` to also surface the
``bridge progress: req=... progress=n/N msg=step n+1/N: rhino.layer.create``
DEBUG lines emitted by ``BridgeBatchHandler.EmitProgress``.

Usage::

    RHINO_MCP_LOG_LEVEL=DEBUG uv run python examples/batch_call_benchmark.py --n 50
"""

from __future__ import annotations

import argparse
import time

from rhino_mcp.bridge.rhino_connection import BridgeClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=10, help="number of layers")
    parser.add_argument(
        "--prefix",
        default="_BENCH_BATCHCALL",
        help="layer name prefix (cleaned up after the run)",
    )
    args = parser.parse_args()

    client = BridgeClient.auto(timeout=5.0)
    if client is None:
        raise SystemExit("No bridge reachable — start Rhino 8 with the plugin loaded.")

    direct_names = [f"{args.prefix}_D_{i:03d}" for i in range(args.n)]
    batch_names = [f"{args.prefix}_B_{i:03d}" for i in range(args.n)]

    t0 = time.perf_counter()
    for name in direct_names:
        client.call("rhino.layer.create", {"name": name, "color": {"r": 200, "g": 200, "b": 200}})
    t_direct = time.perf_counter() - t0

    t0 = time.perf_counter()
    client.call(
        "rhino.batch.execute",
        {
            "steps": [
                {
                    "method": "rhino.layer.create",
                    "params": {"name": name, "color": {"r": 120, "g": 200, "b": 200}},
                }
                for name in batch_names
            ],
            "on_error": "stop",
        },
    )
    t_batch = time.perf_counter() - t0

    print(f"N={args.n}")
    print(f"  direct:   {t_direct:8.3f}s ({t_direct / args.n * 1000:6.1f} ms/op)")
    print(f"  batched:  {t_batch:8.3f}s ({t_batch / args.n * 1000:6.1f} ms/op)")
    print(f"  speedup:  {t_direct / t_batch:5.2f}x")
    print(f"  per-op saved: {(t_direct - t_batch) / args.n * 1000:6.1f} ms")

    # Cleanup
    cleanup_steps = [
        {"method": "rhino.layer.delete", "params": {"name": name}}
        for name in direct_names + batch_names
    ]
    client.call("rhino.batch.execute", {"steps": cleanup_steps, "on_error": "continue"})
    print(f"  cleanup:  {len(cleanup_steps)} layers deleted via batch.")


if __name__ == "__main__":
    main()
