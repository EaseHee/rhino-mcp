# C# Work-Queue Spike — RhinoCommon UI Thread Affinity

## Question

Can long-running bridge handlers (e.g. `batch_modify` over thousands of objects) move parts of their work off Rhino's UI thread to reduce the serial bottleneck `BridgeServer` enforces today?

## Answer

**Largely no.** RhinoCommon does not formally expose thread-safe guarantees for `Doc.Objects.*` mutation paths.
The official guidance is to perform every document write — and in practice every read that crosses the active document — on the UI thread.
Background-thread reads work in many cases but are not contractually safe across Rhino 8 minor releases.

The narrow set of operations that *are* documented to be thread-safe:

- Pure RhinoCommon math (`Vector3d`, `Plane`, `Brep` math without
  document attachment).
- `Doc.Strings.GetString` / `SetString` (document-level user_text).
- Reading a snapshotted `BoundingBox` after the geometry has been
  cloned with `Geometry.Duplicate()`.

## What we already do efficiently

`BridgeServer.ProcessRequest` only blocks the UI thread for the actual `_dispatcher.Dispatch(method, params)` call:

```csharp
RhinoApp.InvokeOnUiThread(new Action(() =>
{
    try { result = _dispatcher.Dispatch(method!, parameters); }
    catch (Exception ex) { uiError = ex; }
    finally { done.Set(); }
}));
done.Wait(uiTimeout);
// ↓ everything below this line runs on the worker thread
if (uiError ...) return ...;
var compressed = MaybeCompress(...);   // gzip on worker thread
return MaybeChunk(id, method!, compressed);  // size + slicing on worker
```

That means JSON serialisation, gzip, and chunk splitting (the most CPU heavy non-RhinoCommon work) already run off the UI thread.
The only piece still locked to the UI thread is the dispatch itself.

## Verdict for v0.5.x

We do not introduce a generalised work-queue layer in this release.
The existing serialisation-on-worker pattern is the right baseline; adding a queue would primarily benefit handlers that internally fan out RhinoCommon operations (e.g. `batch_modify` looping over 10 k objects).

If a future plan tackles `batch_modify` specifically, the pattern is:

1. **Phase 1 (UI thread)**: snapshot the work plan (clone geometry,
   collect attribute changes into plain CLR types).
2. **Phase 2 (worker thread)**: do all pure-math computation on the
   snapshot.
3. **Phase 3 (UI thread)**: apply the resulting deltas back to
   `Doc.Objects` in a single pass.

This is the only known pattern that demonstrably stays inside RhinoCommon's thread-safety contract.

## Action items captured for follow-up

- [ ] Add a benchmark (`benchmarks/bench_batch_modify.py`) that
  measures the UI-blocking duration of `batch_modify` on 10 k objects
  before any restructuring.
- [ ] When the time exceeds a chosen budget (e.g. 500 ms P95), file a
  dedicated plan applying the three-phase pattern to that single
  handler.
- [ ] Track Rhino 8.x release notes for any new thread-safety contract
  on `Doc.Objects` accessors that would unlock background reads.
