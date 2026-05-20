using Rhino;
using Rhino.PlugIns;
using RhinoMcp.Bridge;

namespace RhinoMcp
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
            RhinoApp.WriteLine("[rhino-mcp] Plugin loaded. Type \"_McpInstall\" to configure Claude Desktop integration.");

            var port = ResolvePort();
            var host = Environment.GetEnvironmentVariable("RHINO_HOST") ?? "127.0.0.1";

            try
            {
                BridgeServer.Instance.Start(host, port);
                AnnouncementWriter.Instance.Start(host, port);
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"[rhino-mcp] Failed to start bridge: {ex.Message}");
                errorMessage = ex.Message;
                return LoadReturnCode.ErrorShowDialog;
            }

            return LoadReturnCode.Success;
        }

        protected override void OnShutdown()
        {
            try { AnnouncementWriter.Instance.Stop(); } catch { /* best-effort */ }
            BridgeServer.Instance.Stop();
            base.OnShutdown();
        }

        /// <summary>
        /// Pick the TCP port: honour RHINO_PORT when set; otherwise probe
        /// 4242, 4243, … upward for a free slot so multiple Rhino instances
        /// on the same machine can co-exist without manual config.
        /// </summary>
        private static int ResolvePort()
        {
            var envPort = Environment.GetEnvironmentVariable("RHINO_PORT");
            if (!string.IsNullOrEmpty(envPort) && int.TryParse(envPort, out var p))
                return p;
            return FindFreePort(4242, 16);
        }

        private static int FindFreePort(int start, int span)
        {
            for (var i = 0; i < span; i++)
            {
                var candidate = start + i;
                if (IsPortFree(candidate)) return candidate;
            }
            return start;
        }

        private static bool IsPortFree(int port)
        {
            try
            {
                var listener = new System.Net.Sockets.TcpListener(System.Net.IPAddress.Loopback, port);
                listener.Start();
                listener.Stop();
                return true;
            }
            catch (System.Net.Sockets.SocketException)
            {
                return false;
            }
        }
    }
}
