namespace RhinoMcp
{
    /// <summary>
    /// Per-dispatch context carried on the Rhino UI thread so handlers can
    /// surface the originating JSON-RPC request id in trace logs without
    /// threading the value through every helper signature.
    /// </summary>
    public static class BridgeContext
    {
        [System.ThreadStatic]
        private static string? _requestId;

        public static string? CurrentRequestId
        {
            get => _requestId;
            set => _requestId = value;
        }
    }
}
