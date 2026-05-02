using System.Net;
using System.Net.Sockets;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Rhino;

namespace RhinoMCPBridge
{
    /// <summary>
    /// TCP server that accepts newline-delimited JSON-RPC 2.0 requests and
    /// dispatches them to <see cref="CommandDispatcher"/>.
    /// Runs entirely on background threads; RhinoCommon calls are marshalled
    /// onto the UI thread via <see cref="RhinoApp.InvokeOnUiThread"/>.
    /// </summary>
    public sealed class BridgeServer
    {
        public static BridgeServer Instance { get; } = new();

        private TcpListener? _listener;
        private CancellationTokenSource? _cts;
        private Thread? _acceptThread;
        private readonly CommandDispatcher _dispatcher = new();

        public bool IsRunning => _listener != null;

        public void Start(string host, int port)
        {
            if (IsRunning) return;

            _cts = new CancellationTokenSource();
            _listener = new TcpListener(IPAddress.Parse(host), port);
            _listener.Start();

            _acceptThread = new Thread(() => AcceptLoop(_cts.Token))
            {
                IsBackground = true,
                Name = "RhinoMCPBridge-Accept"
            };
            _acceptThread.Start();

            RhinoApp.WriteLine($"[RhinoMCPBridge] listening on tcp://{host}:{port}");
        }

        public void Stop()
        {
            _cts?.Cancel();
            _listener?.Stop();
            _listener = null;
            RhinoApp.WriteLine("[RhinoMCPBridge] stopped");
        }

        private void AcceptLoop(CancellationToken ct)
        {
            while (!ct.IsCancellationRequested)
            {
                try
                {
                    var client = _listener!.AcceptTcpClient();
                    var addr = client.Client.RemoteEndPoint;
                    RhinoApp.WriteLine($"[RhinoMCPBridge] Connected to client: {addr}");
                    var thread = new Thread(() => HandleClient(client, ct))
                    {
                        IsBackground = true,
                        Name = $"RhinoMCPBridge-Client-{addr}"
                    };
                    thread.Start();
                    RhinoApp.WriteLine("[RhinoMCPBridge] Client handler started");
                }
                catch (SocketException) when (ct.IsCancellationRequested)
                {
                    break;
                }
                catch (Exception ex)
                {
                    RhinoApp.WriteLine($"[RhinoMCPBridge] Accept error: {ex.Message}");
                }
            }
        }

        private void HandleClient(TcpClient client, CancellationToken ct)
        {
            using var stream = client.GetStream();
            using var reader = new StreamReader(stream, Encoding.UTF8);
            using var writer = new StreamWriter(stream, new UTF8Encoding(false)) { AutoFlush = true };

            try
            {
                while (!ct.IsCancellationRequested)
                {
                    var line = reader.ReadLine();
                    if (line == null) break;       // client disconnected
                    if (string.IsNullOrWhiteSpace(line)) continue;

                    var response = ProcessRequest(line);
                    writer.WriteLine(response);
                }
            }
            catch (IOException)
            {
                // client disconnected
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"[RhinoMCPBridge] Client error: {ex.Message}");
            }
            finally
            {
                client.Close();
                RhinoApp.WriteLine("[RhinoMCPBridge] Client disconnected");
            }
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

            if (string.IsNullOrEmpty(method))
                return JsonRpc.Error(id, -32600, "Invalid Request: missing method");

            try
            {
                // Execute on Rhino's UI thread
                JObject? result = null;
                Exception? uiError = null;

                var done = new ManualResetEventSlim(false);

                RhinoApp.InvokeOnUiThread(new Action(() =>
                {
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
                        done.Set();
                    }
                }));

                done.Wait(TimeSpan.FromSeconds(30));

                if (uiError != null)
                    return JsonRpc.Error(id, -32000, uiError.Message,
                        new JObject { ["trace"] = uiError.StackTrace });

                return JsonRpc.Ok(id, result ?? new JObject());
            }
            catch (Exception ex)
            {
                return JsonRpc.Error(id, -32603, $"Internal error: {ex.Message}");
            }
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
