using System.IO;
using System.IO.Compression;
using System.Net;
using System.Net.Sockets;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Rhino;

namespace RhinoMcp
{
    /// <summary>
    /// TCP server that accepts newline-delimited JSON-RPC 2.0 requests and
    /// dispatches them to <see cref="CommandDispatcher"/>.
    /// Runs entirely on background threads; RhinoCommon calls are marshalled
    /// onto the UI thread via <see cref="RhinoApp.InvokeOnUiThread"/>.
    /// </summary>
    public sealed class BridgeServer
    {
        public const string ProtocolVersion = "1.2";

        public static BridgeServer Instance { get; } = new();

        private TcpListener? _listener;
        private CancellationTokenSource? _cts;
        private Thread? _acceptThread;
        private readonly CommandDispatcher _dispatcher = new();
        private int _connectedClientCount;

        public bool IsRunning => _listener != null;

        public int ConnectedClientCount => Volatile.Read(ref _connectedClientCount);

        private static int UiTimeoutSeconds
        {
            get
            {
                var raw = Environment.GetEnvironmentVariable("RHINO_MCP_UI_TIMEOUT");
                if (!string.IsNullOrEmpty(raw) && int.TryParse(raw, out var v) && v > 0)
                    return v;
                return 30;
            }
        }

        private static int SendTimeoutMs
        {
            get
            {
                var raw = Environment.GetEnvironmentVariable("RHINO_MCP_SEND_TIMEOUT_MS");
                if (!string.IsNullOrEmpty(raw) && int.TryParse(raw, out var v) && v > 0)
                    return v;
                return 30_000;
            }
        }

        public void Start(string host, int port)
        {
            if (IsRunning) return;

            _cts = new CancellationTokenSource();
            _listener = new TcpListener(IPAddress.Parse(host), port);
            _listener.Start();

            _acceptThread = new Thread(() => AcceptLoop(_cts.Token))
            {
                IsBackground = true,
                Name = "rhino-mcp-Accept"
            };
            _acceptThread.Start();

            RhinoApp.WriteLine($"[rhino-mcp] listening on tcp://{host}:{port} (protocol={ProtocolVersion})");
        }

        public void Stop()
        {
            _cts?.Cancel();
            _listener?.Stop();
            _listener = null;
            RhinoApp.WriteLine("[rhino-mcp] stopped");
        }

        private void AcceptLoop(CancellationToken ct)
        {
            while (!ct.IsCancellationRequested)
            {
                try
                {
                    var client = _listener!.AcceptTcpClient();
                    ConfigureClient(client);
                    var addr = client.Client.RemoteEndPoint;
                    Interlocked.Increment(ref _connectedClientCount);
                    RhinoApp.WriteLine($"[rhino-mcp] Connected: {addr} (active={_connectedClientCount})");
                    var thread = new Thread(() => HandleClient(client, ct))
                    {
                        IsBackground = true,
                        Name = $"rhino-mcp-Client-{addr}"
                    };
                    thread.Start();
                }
                catch (SocketException) when (ct.IsCancellationRequested)
                {
                    break;
                }
                catch (Exception ex)
                {
                    RhinoApp.WriteLine($"[rhino-mcp] Accept error: {ex.Message}");
                }
            }
        }

        private static void ConfigureClient(TcpClient client)
        {
            // SO_KEEPALIVE lets the OS detect a dead peer when the connection
            // is idle for an extended period. Default OS keepalive intervals
            // (typically ~2 hours) are fine for a developer-tools bridge.
            try
            {
                client.Client.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.KeepAlive, true);
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"[rhino-mcp] keepalive setup failed: {ex.Message}");
            }

            // SendTimeout protects against half-closed peers when we try to
            // write a response. Receive is left at infinite — idle clients
            // are expected; SO_KEEPALIVE catches genuinely-dead peers.
            try
            {
                client.SendTimeout = SendTimeoutMs;
            }
            catch
            {
                // best-effort
            }
        }

        private void HandleClient(TcpClient client, CancellationToken ct)
        {
            try
            {
                using var stream = client.GetStream();
                using var reader = new StreamReader(stream, Encoding.UTF8);
                using var writer = new StreamWriter(stream, new UTF8Encoding(false)) { AutoFlush = true };

                while (!ct.IsCancellationRequested)
                {
                    string? line;
                    try
                    {
                        line = reader.ReadLine();
                    }
                    catch (IOException ex) when (IsTimeout(ex))
                    {
                        // Send-side timeout surfaces here too; treat as recoverable.
                        RhinoApp.WriteLine($"[rhino-mcp] read timeout: {ex.Message}");
                        break;
                    }
                    if (line == null) break;
                    if (string.IsNullOrWhiteSpace(line)) continue;

                    var response = ProcessRequest(line);
                    try
                    {
                        writer.WriteLine(response);
                    }
                    catch (IOException ex)
                    {
                        RhinoApp.WriteLine($"[rhino-mcp] write failed: {ex.Message}");
                        break;
                    }
                }
            }
            catch (IOException)
            {
                // client disconnected
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"[rhino-mcp] Client error: {ex.Message}");
            }
            finally
            {
                try { client.Close(); } catch { /* best-effort */ }
                var remaining = Interlocked.Decrement(ref _connectedClientCount);
                RhinoApp.WriteLine($"[rhino-mcp] Disconnected (active={remaining})");
            }
        }

        private static bool IsTimeout(Exception ex)
        {
            for (var e = ex; e != null; e = e.InnerException!)
            {
                if (e is SocketException se && se.SocketErrorCode == SocketError.TimedOut) return true;
                if (e.InnerException == null) break;
            }
            return false;
        }

        private string ProcessRequest(string line)
        {
            JObject? request;
            try
            {
                request = JObject.Parse(line);
            }
            catch (JsonException)
            {
                return JsonRpc.Error(null, -32700, "Parse error");
            }

            var id = request["id"];
            var method = request["method"]?.ToString();
            var parameters = request["params"] as JObject ?? new JObject();
            var acceptEncoding = (request["_accept_encoding"] as JArray)?
                .Select(t => t?.ToString()?.ToLowerInvariant() ?? "")
                .ToHashSet() ?? new HashSet<string>();

            if (string.IsNullOrEmpty(method))
                return JsonRpc.Error(id, -32600, "Invalid Request: missing method");

            try
            {
                JObject? result = null;
                Exception? uiError = null;
                var done = new ManualResetEventSlim(false);

                var requestIdStr = id?.ToString() ?? "";
                RhinoApp.InvokeOnUiThread(new Action(() =>
                {
                    var prevContext = BridgeContext.CurrentRequestId;
                    BridgeContext.CurrentRequestId = requestIdStr;
                    try
                    {
                        result = _dispatcher.Dispatch(method!, parameters);
                    }
                    catch (Exception ex)
                    {
                        uiError = ex;
                    }
                    finally
                    {
                        BridgeContext.CurrentRequestId = prevContext;
                        done.Set();
                    }
                }));

                var timeoutSec = UiTimeoutSeconds;
                var completed = done.Wait(TimeSpan.FromSeconds(timeoutSec));
                if (!completed)
                {
                    return JsonRpc.Error(
                        id,
                        RpcErrorCodes.BridgeUiTimeout,
                        $"UI thread dispatch exceeded {timeoutSec}s",
                        new JObject
                        {
                            ["method"] = method,
                            ["timeout_seconds"] = timeoutSec,
                            ["hint"] = "Rhino UI thread is busy (modal dialog or long command). Increase RHINO_MCP_UI_TIMEOUT or interrupt the foreground command."
                        });
                }

                if (uiError is RpcException rpc)
                    return JsonRpc.Error(id, rpc.Code, rpc.Message);

                if (uiError != null)
                    return JsonRpc.Error(id, RpcErrorCodes.HandlerError, uiError.Message,
                        new JObject { ["trace"] = uiError.StackTrace });

                var resultObj = result ?? new JObject();
                var compressed = MaybeCompress(method!, resultObj, acceptEncoding);
                return MaybeChunk(id, method!, compressed);
            }
            catch (Exception ex)
            {
                return JsonRpc.Error(id, RpcErrorCodes.InternalError, $"Internal error: {ex.Message}");
            }
        }

        private static readonly HashSet<string> _chunkingExempt = new()
        {
            "rhino.bridge.fetch_chunk",
            "rhino.bridge.chunk_release",
            "rhino.bridge.chunk_stats",
            "rhino.batch.execute",
            "rhino.ping",
        };

        private static int CompressThreshold()
        {
            var raw = Environment.GetEnvironmentVariable("RHINO_MCP_COMPRESS_THRESHOLD");
            if (!string.IsNullOrEmpty(raw) && int.TryParse(raw, out var v) && v > 0)
                return v;
            return 16 * 1024;
        }

        private static JObject MaybeCompress(string method, JObject result, HashSet<string> acceptEncoding)
        {
            // Only the bridge utility methods bypass compression so the
            // chunk-fetch loop never receives a recursively-wrapped payload.
            if (_chunkingExempt.Contains(method)) return result;
            if (acceptEncoding.Count == 0) return result;
            if (!acceptEncoding.Contains("gzip")) return result;

            var json = result.ToString(Formatting.None);
            var bytes = Encoding.UTF8.GetBytes(json);
            if (bytes.Length < CompressThreshold()) return result;

            using var ms = new MemoryStream();
            using (var gz = new GZipStream(ms, CompressionLevel.Fastest, leaveOpen: true))
            {
                gz.Write(bytes, 0, bytes.Length);
            }
            var compressed = ms.ToArray();
            // Skip if compression made the payload bigger (rare, but happens
            // for already-compressed binary blobs hex-encoded inside JSON).
            if (compressed.Length >= bytes.Length) return result;

            return new JObject
            {
                ["__compressed__"] = true,
                ["encoding"] = "gzip",
                ["original_size"] = bytes.Length,
                ["compressed_size"] = compressed.Length,
                ["data_b64"] = Convert.ToBase64String(compressed),
            };
        }

        private static string MaybeChunk(JToken? id, string method, JObject result)
        {
            // Avoid recursion: chunk-fetching and ping must always be sent inline.
            if (_chunkingExempt.Contains(method))
                return JsonRpc.Ok(id, result);

            var resultJson = result.ToString(Newtonsoft.Json.Formatting.None);
            var resultBytes = Encoding.UTF8.GetByteCount(resultJson);
            var threshold = Handlers.BridgeChunkHandler.ChunkThreshold();
            if (resultBytes <= threshold)
                return JsonRpc.Ok(id, result);

            var bytes = Encoding.UTF8.GetBytes(resultJson);
            var ttl = TimeSpan.FromSeconds(Handlers.BridgeChunkHandler.ChunkTtlSeconds());
            var chunkId = BridgeChunkStore.Put(bytes, ttl);
            var chunkSize = Handlers.BridgeChunkHandler.ChunkBytes();
            var totalChunks = (bytes.Length + chunkSize - 1) / chunkSize;

            var meta = new JObject
            {
                ["__chunked__"] = true,
                ["chunk_id"] = chunkId.ToString(),
                ["size"] = bytes.Length,
                ["chunk_size"] = chunkSize,
                ["total_chunks"] = totalChunks,
                ["encoding"] = "json",
                ["original_method"] = method,
            };
            RhinoApp.WriteLine($"[rhino-mcp] chunked response method={method} bytes={bytes.Length} chunks={totalChunks}");
            return JsonRpc.Ok(id, meta);
        }
    }

    internal static class JsonRpc
    {
        public static string Ok(JToken? id, JObject result)
        {
            var resp = new JObject
            {
                ["jsonrpc"] = "2.0",
                ["id"] = id,
                ["result"] = result
            };
            return resp.ToString(Formatting.None);
        }

        public static string Error(JToken? id, int code, string message, JObject? data = null)
        {
            var err = new JObject
            {
                ["code"] = code,
                ["message"] = message
            };
            if (data != null) err["data"] = data;

            var resp = new JObject
            {
                ["jsonrpc"] = "2.0",
                ["id"] = id,
                ["error"] = err
            };
            return resp.ToString(Formatting.None);
        }
    }
}
