using Rhino;
using Rhino.PlugIns;
using RhinoMcp.Bridge;

namespace RhinoMcp
{
    /// <summary>
    /// Rhino 8 / 9 native plugin that auto-starts a JSON-RPC 2.0 TCP bridge on load.
    /// The MCP server (<c>rhino-mcp</c>) connects to this bridge to forward tool calls.
    /// </summary>
    public class Plugin : PlugIn
    {
        public static Plugin? Instance { get; private set; }

        public Plugin()
        {
            Instance = this;
        }

        /// <summary>Rhino major version this assembly was compiled against (RhinoMajor MSBuild property).</summary>
#if RHINO9
        public const int BuiltForRhinoMajor = 9;
#else
        public const int BuiltForRhinoMajor = 8;
#endif

        public override PlugInLoadTime LoadTime => PlugInLoadTime.AtStartup;

        protected override LoadReturnCode OnLoad(ref string errorMessage)
        {
            RhinoApp.WriteLine("[rhino-mcp] Plugin loaded. Type \"_McpInstall\" to register rhino-mcp with Claude Desktop, Claude Code, Codex or Antigravity.");
            if (RhinoApp.ExeVersion != BuiltForRhinoMajor)
                RhinoApp.WriteLine($"[rhino-mcp] Note: this build targets Rhino {BuiltForRhinoMajor} but is running in Rhino {RhinoApp.ExeVersion}. Install the rh{RhinoApp.ExeVersion} package from the Package Manager for full compatibility.");

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
