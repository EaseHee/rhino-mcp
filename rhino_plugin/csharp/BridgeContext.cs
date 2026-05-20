namespace RhinoMcp
{
    /// <summary>
    /// Per-dispatch context carried on the Rhino UI thread so handlers can
    /// surface the originating JSON-RPC request id in trace logs and emit
    /// out-of-band progress notifications without threading the values
    /// through every helper signature.
    /// </summary>
    public static class BridgeContext
    {
        [System.ThreadStatic]
        private static string? _requestId;

        [System.ThreadStatic]
        private static IProgressSink? _progressSink;

        public static string? CurrentRequestId
        {
            get => _requestId;
            set => _requestId = value;
        }

        public static IProgressSink? CurrentProgressSink
        {
            get => _progressSink;
            set => _progressSink = value;
        }
    }

    /// <summary>
    /// Emits an out-of-band JSON-RPC progress notification on the same
    /// socket as the in-flight request. Implementations must serialise
    /// writes against the same lock the final response uses so a
    /// notification cannot tear an in-progress response line.
    /// </summary>
    public interface IProgressSink
    {
        void Report(double? progress, double? total = null, string? message = null);
    }
}
