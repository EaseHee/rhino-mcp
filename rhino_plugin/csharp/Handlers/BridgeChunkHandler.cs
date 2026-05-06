using Newtonsoft.Json.Linq;

namespace RhinoMcp.Handlers
{
    /// <summary>
    /// Side-channel handlers used to fetch and release chunked responses
    /// (see <see cref="BridgeChunkStore"/>). These are invoked by the
    /// Python BridgeClient transparently when a response is too large for
    /// a single newline-delimited JSON line.
    /// </summary>
    public class BridgeChunkHandler : HandlerBase
    {
        public JObject FetchChunk(JObject p)
        {
            var chunkIdStr = p["chunk_id"]?.ToString();
            if (string.IsNullOrWhiteSpace(chunkIdStr) || !Guid.TryParse(chunkIdStr, out var chunkId))
                throw new System.ArgumentException("fetch_chunk requires a valid 'chunk_id' GUID.");
            var index = p["index"]?.Value<int>() ?? 0;
            if (index < 0)
                throw new System.ArgumentException("'index' must be >= 0.");

            var data = BridgeChunkStore.Get(chunkId)
                ?? throw new RpcException(
                    RpcErrorCodes.ChunkNotFound,
                    $"Chunk {chunkId} not found or expired.");

            var chunkSize = ChunkBytes();
            var start = index * chunkSize;
            if (start >= data.Length)
                throw new System.ArgumentOutOfRangeException(
                    nameof(index),
                    $"index={index} exceeds chunk count for size={data.Length}");

            var length = System.Math.Min(chunkSize, data.Length - start);
            var slice = new byte[length];
            System.Array.Copy(data, start, slice, 0, length);

            return new JObject
            {
                ["chunk_id"] = chunkId.ToString(),
                ["index"] = index,
                ["data_b64"] = System.Convert.ToBase64String(slice),
                ["is_last"] = (start + length) >= data.Length,
            };
        }

        public JObject Release(JObject p)
        {
            var chunkIdStr = p["chunk_id"]?.ToString();
            if (string.IsNullOrWhiteSpace(chunkIdStr) || !Guid.TryParse(chunkIdStr, out var chunkId))
                throw new System.ArgumentException("release requires a valid 'chunk_id' GUID.");
            var removed = BridgeChunkStore.Release(chunkId);
            return new JObject
            {
                ["chunk_id"] = chunkId.ToString(),
                ["released"] = removed,
            };
        }

        public JObject Stats(JObject _)
        {
            return new JObject
            {
                ["entries"] = BridgeChunkStore.Count,
                ["chunk_size_bytes"] = ChunkBytes(),
                ["threshold_bytes"] = ChunkThreshold(),
                ["ttl_seconds"] = ChunkTtlSeconds(),
            };
        }

        public static int ChunkBytes()
        {
            var raw = System.Environment.GetEnvironmentVariable("RHINO_MCP_CHUNK_BYTES");
            if (!string.IsNullOrEmpty(raw) && int.TryParse(raw, out var v) && v >= 4096)
                return v;
            return 512 * 1024;
        }

        public static int ChunkThreshold()
        {
            var raw = System.Environment.GetEnvironmentVariable("RHINO_MCP_CHUNK_THRESHOLD");
            if (!string.IsNullOrEmpty(raw) && int.TryParse(raw, out var v) && v > 0)
                return v;
            return 4 * 1024 * 1024;
        }

        public static int ChunkTtlSeconds()
        {
            var raw = System.Environment.GetEnvironmentVariable("RHINO_MCP_CHUNK_TTL_SEC");
            if (!string.IsNullOrEmpty(raw) && int.TryParse(raw, out var v) && v > 0)
                return v;
            return 60;
        }
    }
}
