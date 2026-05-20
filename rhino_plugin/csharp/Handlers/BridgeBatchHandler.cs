using Newtonsoft.Json.Linq;

namespace RhinoMcp.Handlers
{
    /// <summary>
    /// Multi-step dispatcher: execute N JSON-RPC method calls in a single
    /// bridge round-trip. Each step shares Rhino's UI thread serialisation
    /// (the same as N independent calls), but the network/IPC cost is paid
    /// only once.
    ///
    /// Steps run sequentially. ``on_error`` controls behaviour after a
    /// failure: ``"stop"`` (default) returns immediately with an error
    /// envelope, ``"continue"`` records the error and proceeds.
    /// </summary>
    public class BridgeBatchHandler : HandlerBase
    {
        private readonly CommandDispatcher _dispatcher;

        public BridgeBatchHandler(CommandDispatcher dispatcher)
        {
            _dispatcher = dispatcher;
        }

        public JObject Execute(JObject p)
        {
            var stepsTok = p["steps"] as JArray
                ?? throw new System.ArgumentException("'steps' must be a JSON array.");
            if (stepsTok.Count == 0)
                throw new System.ArgumentException("'steps' must contain at least one entry.");

            var maxSteps = MaxBatchSteps();
            if (stepsTok.Count > maxSteps)
                throw new RpcException(
                    RpcErrorCodes.TooManyObjectIds,
                    $"batch.execute steps={stepsTok.Count} exceeds RHINO_MCP_BATCH_MAX_STEPS={maxSteps}.");

            var onError = (p["on_error"]?.ToString() ?? "stop").ToLowerInvariant();
            if (onError != "stop" && onError != "continue")
                throw new System.ArgumentException("'on_error' must be 'stop' or 'continue'.");

            var results = new JArray();
            for (var i = 0; i < stepsTok.Count; i++)
            {
                var step = stepsTok[i] as JObject
                    ?? throw new System.ArgumentException($"steps[{i}] must be an object.");
                var method = step["method"]?.ToString();
                var stepParams = step["params"] as JObject ?? new JObject();
                if (string.IsNullOrEmpty(method))
                    throw new System.ArgumentException($"steps[{i}].method is required.");

                EmitProgress(i, stepsTok.Count, $"step {i + 1}/{stepsTok.Count}: {method}");

                JObject entry;
                try
                {
                    var stepResult = _dispatcher.Dispatch(method!, stepParams);
                    entry = new JObject
                    {
                        ["index"] = i,
                        ["method"] = method,
                        ["status"] = "ok",
                        ["result"] = stepResult,
                    };
                }
                catch (RpcException rpc)
                {
                    entry = new JObject
                    {
                        ["index"] = i,
                        ["method"] = method,
                        ["status"] = "error",
                        ["error"] = new JObject
                        {
                            ["code"] = rpc.Code,
                            ["message"] = rpc.Message,
                        },
                    };
                    results.Add(entry);
                    if (onError == "stop")
                        throw new RpcException(
                            RpcErrorCodes.BatchStepFailed,
                            $"step {i} ({method}) failed: {rpc.Message}");
                    continue;
                }
                catch (System.Exception ex)
                {
                    entry = new JObject
                    {
                        ["index"] = i,
                        ["method"] = method,
                        ["status"] = "error",
                        ["error"] = new JObject
                        {
                            ["code"] = RpcErrorCodes.HandlerError,
                            ["message"] = ex.Message,
                        },
                    };
                    results.Add(entry);
                    if (onError == "stop")
                        throw new RpcException(
                            RpcErrorCodes.BatchStepFailed,
                            $"step {i} ({method}) failed: {ex.Message}");
                    continue;
                }
                results.Add(entry);
            }

            var ok = 0;
            var failed = 0;
            foreach (var r in results)
            {
                if (r["status"]?.ToString() == "ok") ok++;
                else failed++;
            }

            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["total"] = results.Count,
                    ["ok"] = ok,
                    ["failed"] = failed,
                    ["on_error"] = onError,
                },
                ["results"] = results,
            };
        }

        private static int MaxBatchSteps()
        {
            var raw = System.Environment.GetEnvironmentVariable("RHINO_MCP_BATCH_MAX_STEPS");
            if (!string.IsNullOrEmpty(raw) && int.TryParse(raw, out var v) && v > 0)
                return v;
            return 256;
        }
    }
}
