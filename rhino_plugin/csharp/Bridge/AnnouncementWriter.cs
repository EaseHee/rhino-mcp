using System;
using System.IO;
using System.Text;
using Newtonsoft.Json.Linq;
using Rhino;

namespace RhinoMcp.Bridge
{
    /// <summary>
    /// Writes a per-process JSON announcement file describing this Rhino
    /// instance's bridge endpoint, so an MCP server (or router) running
    /// outside Rhino can enumerate all live sessions and pick one.
    ///
    /// File path:
    ///   - macOS / Linux: <c>${RHINO_MCP_LISTENER_DIR:-${TMPDIR:-/tmp}/rhino-mcp-listeners}</c>
    ///   - Windows:       <c>${RHINO_MCP_LISTENER_DIR:-%LOCALAPPDATA%/rhino-mcp/listeners}</c>
    ///
    /// File name: <c>{pid}-{port}.json</c>. Contents:
    /// <code>
    /// {
    ///   "pid": 12345,
    ///   "host": "127.0.0.1",
    ///   "port": 4242,
    ///   "doc_path": "/Users/.../site.3dm",
    ///   "doc_title": "site.3dm",
    ///   "rhino_version": "8.10.24228.13001",
    ///   "protocol_version": "1.2",
    ///   "started_at": "2026-05-16T09:00:00Z"
    /// }
    /// </code>
    /// </summary>
    public sealed class AnnouncementWriter
    {
        public static AnnouncementWriter Instance { get; } = new();

        private string? _filePath;
        private string? _host;
        private int _port;
        private readonly object _lock = new();

        public string? FilePath => _filePath;

        public void Start(string host, int port)
        {
            lock (_lock)
            {
                _host = host;
                _port = port;
                try
                {
                    var dir = ResolveListenerDir();
                    Directory.CreateDirectory(dir);
                    var pid = Environment.ProcessId;
                    _filePath = Path.Combine(dir, $"{pid}-{port}.json");
                    WriteAnnouncementLocked();
                    RhinoApp.WriteLine($"[rhino-mcp] announcement written: {_filePath}");
                    // Refresh on document changes so doc_path/doc_title stay current.
                    RhinoDoc.EndOpenDocument += OnDocEvent;
                    RhinoDoc.NewDocument += OnDocEvent;
                    RhinoDoc.CloseDocument += OnDocEvent;
                }
                catch (Exception ex)
                {
                    RhinoApp.WriteLine($"[rhino-mcp] announcement write failed: {ex.Message}");
                    _filePath = null;
                }
            }
        }

        public void Stop()
        {
            lock (_lock)
            {
                RhinoDoc.EndOpenDocument -= OnDocEvent;
                RhinoDoc.NewDocument -= OnDocEvent;
                RhinoDoc.CloseDocument -= OnDocEvent;
                if (_filePath != null)
                {
                    try
                    {
                        if (File.Exists(_filePath)) File.Delete(_filePath);
                    }
                    catch (Exception ex)
                    {
                        RhinoApp.WriteLine($"[rhino-mcp] announcement delete failed: {ex.Message}");
                    }
                    _filePath = null;
                }
            }
        }

        public void Refresh()
        {
            lock (_lock)
            {
                if (_filePath == null) return;
                try
                {
                    WriteAnnouncementLocked();
                }
                catch (Exception ex)
                {
                    RhinoApp.WriteLine($"[rhino-mcp] announcement refresh failed: {ex.Message}");
                }
            }
        }

        private void OnDocEvent(object? sender, EventArgs e) => Refresh();

        private void WriteAnnouncementLocked()
        {
            if (_filePath == null || _host == null) return;
            var doc = RhinoDoc.ActiveDoc;
            var payload = new JObject
            {
                ["pid"] = Environment.ProcessId,
                ["host"] = _host,
                ["port"] = _port,
                ["doc_path"] = doc?.Path ?? "",
                ["doc_title"] = string.IsNullOrEmpty(doc?.Path) ? (doc?.Name ?? "") : Path.GetFileName(doc!.Path),
                ["rhino_version"] = RhinoApp.Version?.ToString() ?? "",
                ["protocol_version"] = BridgeServer.ProtocolVersion,
                ["started_at"] = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"),
            };
            File.WriteAllText(_filePath, payload.ToString(Newtonsoft.Json.Formatting.None), new UTF8Encoding(false));
        }

        private static string ResolveListenerDir()
        {
            var explicitDir = Environment.GetEnvironmentVariable("RHINO_MCP_LISTENER_DIR");
            if (!string.IsNullOrWhiteSpace(explicitDir))
                return explicitDir;

            if (Environment.OSVersion.Platform == PlatformID.Win32NT)
            {
                var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                return Path.Combine(local, "rhino-mcp", "listeners");
            }

            var tmp = Environment.GetEnvironmentVariable("TMPDIR");
            if (string.IsNullOrWhiteSpace(tmp)) tmp = "/tmp";
            return Path.Combine(tmp, "rhino-mcp-listeners");
        }
    }
}
