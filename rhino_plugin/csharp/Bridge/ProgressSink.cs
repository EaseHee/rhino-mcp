using System;
using System.Globalization;
using System.IO;
using System.Text;

namespace RhinoMcp.Bridge
{
    /// <summary>
    /// Writes a <c>rhino.progress</c> JSON-RPC notification onto the
    /// client stream while a long-running handler is still on the UI
    /// thread. Notifications carry the in-flight request id plus
    /// optional ``progress`` / ``total`` / ``message`` fields.
    ///
    /// Thread safety: handlers may call <see cref="Report"/> from the
    /// UI thread while <see cref="HeartbeatSender"/> writes from a
    /// background thread. Both take the same <c>_writeLock</c> so a
    /// notification line never interleaves with the eventual response.
    /// </summary>
    public sealed class ProgressSink : IProgressSink
    {
        private readonly StreamWriter _writer;
        private readonly object _writeLock;
        private readonly string _requestId;

        public ProgressSink(StreamWriter writer, object writeLock, string requestId)
        {
            _writer = writer ?? throw new ArgumentNullException(nameof(writer));
            _writeLock = writeLock ?? throw new ArgumentNullException(nameof(writeLock));
            _requestId = requestId ?? string.Empty;
        }

        public void Report(double? progress, double? total = null, string? message = null)
        {
            // Build the JSON-RPC notification line by hand: hot-path, single
            // allocation, no Newtonsoft dependency required. The fields are
            // tightly bounded so manual formatting cannot misquote.
            var sb = new StringBuilder(128);
            sb.Append("{\"jsonrpc\":\"2.0\",\"method\":\"rhino.progress\",\"params\":{\"request_id\":");
            AppendJsonString(sb, _requestId);
            if (progress.HasValue)
            {
                sb.Append(",\"progress\":");
                sb.Append(progress.Value.ToString("R", CultureInfo.InvariantCulture));
            }
            if (total.HasValue)
            {
                sb.Append(",\"total\":");
                sb.Append(total.Value.ToString("R", CultureInfo.InvariantCulture));
            }
            if (!string.IsNullOrEmpty(message))
            {
                sb.Append(",\"message\":");
                AppendJsonString(sb, message!);
            }
            sb.Append("}}");

            var line = sb.ToString();
            try
            {
                lock (_writeLock)
                {
                    _writer.WriteLine(line);
                }
            }
            catch (IOException)
            {
                // Peer gone — swallow; the dispatch path will surface the
                // failure on the eventual response write.
            }
            catch (ObjectDisposedException)
            {
                // Stream torn down between report and write; same rationale.
            }
        }

        private static void AppendJsonString(StringBuilder sb, string value)
        {
            sb.Append('"');
            foreach (var c in value)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    case '\b': sb.Append("\\b"); break;
                    case '\f': sb.Append("\\f"); break;
                    default:
                        if (c < 0x20)
                            sb.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                        else
                            sb.Append(c);
                        break;
                }
            }
            sb.Append('"');
        }
    }
}
