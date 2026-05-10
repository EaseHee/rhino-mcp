using System;
using System.IO;
using System.Threading;

namespace RhinoMcp.Bridge
{
    /// <summary>
    /// Writes a <c>rhino.heartbeat</c> JSON-RPC notification to the client
    /// stream every <see cref="_interval"/>.  Used to wrap long-running
    /// handlers (make2d, render, script execution) that would otherwise
    /// leave the socket idle long enough to trip OS / app-level keepalive
    /// timeouts on the Python client.
    ///
    /// The notification has no <c>id</c>, so the Python <c>BridgeClient</c>
    /// drops it on the floor — its only purpose is to put bytes on the
    /// wire and keep the connection lively.
    ///
    /// Thread-safe write coordination is the caller's responsibility:
    /// <see cref="HeartbeatSender"/> takes the same <see cref="_writeLock"/>
    /// the response-sending path uses, so notifications and the final
    /// response never interleave in the middle of a JSON line.
    /// </summary>
    public sealed class HeartbeatSender : IDisposable
    {
        private const string HeartbeatLine =
            "{\"jsonrpc\":\"2.0\",\"method\":\"rhino.heartbeat\"}";

        private readonly StreamWriter _writer;
        private readonly object _writeLock;
        private readonly TimeSpan _interval;
        private readonly CancellationTokenSource _cts = new();
        private readonly Thread _thread;
        private int _disposed;

        public HeartbeatSender(StreamWriter writer, object writeLock, TimeSpan interval)
        {
            _writer = writer ?? throw new ArgumentNullException(nameof(writer));
            _writeLock = writeLock ?? throw new ArgumentNullException(nameof(writeLock));
            if (interval <= TimeSpan.Zero)
                throw new ArgumentOutOfRangeException(nameof(interval));
            _interval = interval;
            _thread = new Thread(Loop)
            {
                IsBackground = true,
                Name = "rhino-mcp-Heartbeat",
            };
        }

        public void Start() => _thread.Start();

        private void Loop()
        {
            try
            {
                while (!_cts.IsCancellationRequested)
                {
                    if (_cts.Token.WaitHandle.WaitOne(_interval))
                        break;
                    try
                    {
                        lock (_writeLock)
                        {
                            _writer.WriteLine(HeartbeatLine);
                        }
                    }
                    catch (IOException)
                    {
                        // Peer is gone or stream is closed — no point continuing.
                        break;
                    }
                    catch (ObjectDisposedException)
                    {
                        break;
                    }
                }
            }
            catch
            {
                // Background thread must never propagate.
            }
        }

        public void Dispose()
        {
            if (Interlocked.Exchange(ref _disposed, 1) != 0) return;
            try
            {
                _cts.Cancel();
            }
            catch (ObjectDisposedException)
            {
                // already cancelled
            }
            try
            {
                _thread.Join(TimeSpan.FromSeconds(2));
            }
            catch
            {
                // best-effort
            }
            _cts.Dispose();
        }
    }
}
