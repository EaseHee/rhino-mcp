using Rhino;
using Rhino.PlugIns;

namespace RhinoMCPBridge
{
    /// <summary>
    /// Rhino 8 native plugin that auto-starts a JSON-RPC 2.0 TCP bridge on load.
    /// The MCP server (<c>rhino-mcp</c>) connects to this bridge to forward tool calls.
    /// </summary>
    public class Plugin : PlugIn
    {
        public static Plugin? Instance { get; private set; }

        public Plugin()
        {
            Instance = this;
        }

        public override PlugInLoadTime LoadTime => PlugInLoadTime.AtStartup;

        protected override LoadReturnCode OnLoad(ref string errorMessage)
        {
            RhinoApp.WriteLine("[RhinoMCPBridge] Plugin loaded");

            var port = 4242;
            var envPort = Environment.GetEnvironmentVariable("RHINO_PORT");
            if (!string.IsNullOrEmpty(envPort) && int.TryParse(envPort, out var p))
                port = p;

            var host = Environment.GetEnvironmentVariable("RHINO_HOST") ?? "127.0.0.1";

            try
            {
                BridgeServer.Instance.Start(host, port);
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"[RhinoMCPBridge] Failed to start bridge: {ex.Message}");
                errorMessage = ex.Message;
                return LoadReturnCode.ErrorShowDialog;
            }

            return LoadReturnCode.Success;
        }

        protected override void OnShutdown()
        {
            BridgeServer.Instance.Stop();
            base.OnShutdown();
        }
    }
}
