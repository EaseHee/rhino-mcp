namespace RhinoMcp
{
    /// <summary>
    /// JSON-RPC error code matrix shared with Python (see
    /// docs/dev/rpc-error-codes.md and src/rhino_mcp/utils/rpc_errors.py).
    /// Both sides keep the symbolic names identical so a release-time
    /// drift check is mechanical.
    /// </summary>
    public static class RpcErrorCodes
    {
        // Standard JSON-RPC 2.0
        public const int ParseError = -32700;
        public const int InvalidRequest = -32600;
        public const int MethodNotFound = -32601;
        public const int InvalidParams = -32602;
        public const int InternalError = -32603;
        public const int HandlerError = -32000;

        // Bridge-domain (-50000 .. -50099)
        public const int BridgeUiTimeout = -50001;
        public const int PayloadTooLarge = -50002;
        public const int ChunkNotFound = -50003;
        public const int TooManyObjectIds = -50004;
        public const int BatchStepFailed = -50005;
        public const int RenderJobUnknown = -50006;
    }
}
