using Newtonsoft.Json.Linq;
using Rhino.Geometry;

namespace RhinoMcp.Handlers
{
    /// <summary>
    /// Geometry validation — surface topology issues that silently break booleans
    /// and exports. RhinoCommon side enumerates naked edges / non-manifold edges
    /// where rhino3dm cannot.
    /// </summary>
    public class ValidationHandler : HandlerBase
    {
        public JObject Brep(JObject p)
        {
            var oid = p["object_id"]!.ToString();
            var brep = FindBrep(oid)
                ?? throw new ArgumentException($"object_id must reference a Brep: {oid}");

            var isValid = brep.IsValidWithLog(out var log);
            var issues = new JArray();
            if (!isValid && !string.IsNullOrEmpty(log))
            {
                foreach (var line in log.Split('\n', StringSplitOptions.RemoveEmptyEntries))
                {
                    issues.Add(new JObject
                    {
                        ["severity"] = "error",
                        ["description"] = line.Trim(),
                    });
                }
            }
            if (!brep.IsSolid)
            {
                issues.Add(new JObject
                {
                    ["severity"] = "warning",
                    ["description"] = "Brep is not closed (open shell)",
                    ["hint"] = "Use rhino_check_naked_edges to locate gaps.",
                });
            }
            int nakedCount = 0;
            foreach (var e in brep.Edges)
            {
                if (e.Valence == EdgeAdjacency.Naked) nakedCount++;
            }
            if (nakedCount > 0)
            {
                issues.Add(new JObject
                {
                    ["severity"] = "warning",
                    ["description"] = $"Brep has {nakedCount} naked edge(s)",
                    ["hint"] = "rhino_check_naked_edges enumerates them by index and length.",
                });
            }

            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["object_id"] = oid,
                    ["is_valid"] = isValid,
                    ["is_solid"] = brep.IsSolid,
                    ["is_manifold"] = brep.IsManifold,
                    ["face_count"] = brep.Faces.Count,
                    ["edge_count"] = brep.Edges.Count,
                    ["naked_edge_count"] = nakedCount,
                    ["issues"] = issues,
                },
                ["text"] = $"Brep {oid}: valid={isValid}, solid={brep.IsSolid}, naked={nakedCount}",
            };
        }

        public JObject NakedEdges(JObject p)
        {
            var oid = p["object_id"]!.ToString();
            var brep = FindBrep(oid)
                ?? throw new ArgumentException($"object_id must reference a Brep: {oid}");
            var edges = new JArray();
            for (int i = 0; i < brep.Edges.Count; i++)
            {
                var e = brep.Edges[i];
                if (e.Valence != EdgeAdjacency.Naked) continue;
                edges.Add(new JObject
                {
                    ["edge_index"] = i,
                    ["length"] = e.GetLength(),
                });
            }
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["object_id"] = oid,
                    ["naked_edge_count"] = edges.Count,
                    ["edges"] = edges,
                },
                ["text"] = $"Brep {oid}: {edges.Count} naked edge(s)",
            };
        }

        public JObject Mesh(JObject p)
        {
            var oid = p["object_id"]!.ToString();
            var mesh = FindMesh(oid)
                ?? throw new ArgumentException($"object_id must reference a Mesh: {oid}");
            var isValid = mesh.IsValidWithLog(out var log);
            var issues = new JArray();
            if (!isValid && !string.IsNullOrEmpty(log))
            {
                foreach (var line in log.Split('\n', StringSplitOptions.RemoveEmptyEntries))
                    issues.Add(new JObject { ["severity"] = "error", ["description"] = line.Trim() });
            }
            if (!mesh.IsClosed)
                issues.Add(new JObject
                {
                    ["severity"] = "warning",
                    ["description"] = "Mesh is not closed",
                    ["hint"] = "Boolean / volume / 3-D-print exports require a closed mesh.",
                });
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["object_id"] = oid,
                    ["is_valid"] = isValid,
                    ["is_closed"] = mesh.IsClosed,
                    ["is_manifold"] = mesh.IsManifold(true, out var oriented, out _) && oriented,
                    ["vertex_count"] = mesh.Vertices.Count,
                    ["face_count"] = mesh.Faces.Count,
                    ["issues"] = issues,
                },
                ["text"] = $"Mesh {oid}: valid={isValid}, closed={mesh.IsClosed}",
            };
        }

        public JObject Curve(JObject p)
        {
            var oid = p["object_id"]!.ToString();
            var crv = FindCurve(oid)
                ?? throw new ArgumentException($"object_id must reference a Curve: {oid}");
            var isValid = crv.IsValidWithLog(out var log);
            var issues = new JArray();
            if (!isValid && !string.IsNullOrEmpty(log))
            {
                foreach (var line in log.Split('\n', StringSplitOptions.RemoveEmptyEntries))
                    issues.Add(new JObject { ["severity"] = "error", ["description"] = line.Trim() });
            }
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["object_id"] = oid,
                    ["is_valid"] = isValid,
                    ["is_closed"] = crv.IsClosed,
                    ["is_planar"] = crv.IsPlanar(),
                    ["is_periodic"] = crv.IsPeriodic,
                    ["span_count"] = crv.SpanCount,
                    ["degree"] = crv.Degree,
                    ["domain"] = new JArray { crv.Domain.T0, crv.Domain.T1 },
                    ["issues"] = issues,
                },
                ["text"] = $"Curve {oid}: closed={crv.IsClosed}, spans={crv.SpanCount}",
            };
        }
    }
}
