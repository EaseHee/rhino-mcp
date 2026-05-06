using System.Collections.Concurrent;

namespace RhinoMcp
{
    /// <summary>
    /// In-memory store for oversized response payloads.
    ///
    /// When a response would exceed <c>RHINO_MCP_CHUNK_THRESHOLD</c>, the
    /// bridge stashes the UTF-8 bytes here under a generated chunk id and
    /// returns metadata to the client instead. The client pulls the bytes
    /// back via <c>rhino.bridge.fetch_chunk</c> in fixed-size slices, then
    /// asks the bridge to release the entry once reassembly succeeds.
    /// </summary>
    public static class BridgeChunkStore
    {
        private sealed class Entry
        {
            public byte[] Data = System.Array.Empty<byte>();
            public DateTime ExpiresAtUtc;
        }

        private static readonly ConcurrentDictionary<Guid, Entry> _store = new();

        public static int Count => _store.Count;

        public static Guid Put(byte[] data, TimeSpan ttl)
        {
            EvictExpired();
            var id = Guid.NewGuid();
            _store[id] = new Entry
            {
                Data = data,
                ExpiresAtUtc = DateTime.UtcNow + ttl,
            };
            return id;
        }

        public static byte[]? Get(Guid id)
        {
            EvictExpired();
            if (_store.TryGetValue(id, out var entry))
            {
                if (entry.ExpiresAtUtc > DateTime.UtcNow)
                    return entry.Data;
                _store.TryRemove(id, out _);
            }
            return null;
        }

        public static bool Release(Guid id)
        {
            return _store.TryRemove(id, out _);
        }

        public static void Clear() => _store.Clear();

        private static void EvictExpired()
        {
            var now = DateTime.UtcNow;
            foreach (var pair in _store)
            {
                if (pair.Value.ExpiresAtUtc <= now)
                    _store.TryRemove(pair.Key, out _);
            }
        }
    }

    /// <summary>
    /// Thrown by handlers to signal a JSON-RPC error with a specific
    /// numeric code (see <see cref="RpcErrorCodes"/>). The bridge
    /// dispatcher converts this into a proper JSON-RPC error envelope.
    /// </summary>
    public sealed class RpcException : Exception
    {
        public int Code { get; }

        public RpcException(int code, string message) : base(message)
        {
            Code = code;
        }
    }
}
