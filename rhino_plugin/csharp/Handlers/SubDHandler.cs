using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.Geometry;

namespace RhinoMcp.Handlers
{
    /// <summary>SubD operations: create from mesh, convert to NURBS.</summary>
    public class SubDHandler : HandlerBase
    {
        public JObject Create(JObject p)
        {
            var mesh = FindMesh(p["mesh_id"]!.ToString())
                ?? throw new ArgumentException("Mesh not found");

            uint undo = Doc.BeginUndoRecord("MCP: subd_create");
            try
            {
                var subd = SubD.CreateFromMesh(mesh);
                if (subd == null)
                    throw new InvalidOperationException("SubD creation from mesh failed");

                var id = AddObject(subd, p);
                Doc.Views.Redraw();
                return ObjectResult(id, "SubD");
            }
            finally { Doc.EndUndoRecord(undo); }
        }

        public JObject ToNurbs(JObject p)
        {
            var obj = FindObject(p["object_id"]!.ToString())
                ?? throw new ArgumentException("Object not found");
            var geom = obj.Geometry;

            if (geom is not SubD subd)
                throw new ArgumentException("Object is not a SubD");

            uint undo = Doc.BeginUndoRecord("MCP: subd_to_nurbs");
            try
            {
                var brep = subd.ToBrep(SubDToBrepOptions.Default);
                if (brep == null)
                    throw new InvalidOperationException("SubD to NURBS conversion failed");

                var id = AddObject(brep, p);
                Doc.Views.Redraw();
                return ObjectResult(id, "Brep");
            }
            finally { Doc.EndUndoRecord(undo); }
        }

        /// <summary>
        /// Read-only SubD topology report; mirrors the standalone
        /// <c>subd_summary</c> payload in <c>tools/subd.py</c>.
        /// </summary>
        public JObject Inspect(JObject p)
        {
            var objectId = p["object_id"]!.ToString();
            var obj = FindObject(objectId) ?? throw new ArgumentException("Object not found");
            if (obj.Geometry is not SubD subd)
                throw new ArgumentException($"object_id must reference a SubD (got {obj.Geometry?.GetType().Name})");

            var includeCreases = p["include_creases"]?.Value<bool>() ?? true;
            var limit = p["limit"]?.Value<int>() ?? 200;

            var vertexTags = new SortedDictionary<string, int>();
            var edgeTags = new SortedDictionary<string, int>();
            var faceSides = new SortedDictionary<int, int>();
            int vertexCount = 0, edgeCount = 0, faceCount = 0;
            int corners = 0, darts = 0, boundary = 0, creaseCount = 0, sharpCount = 0;
            var maxSharpness = 0.0;
            var creases = new JArray();
            var cornerList = new JArray();

            for (var v = subd.Vertices.First; v != null; v = v.Next)
            {
                vertexCount++;
                Bump(vertexTags, v.Tag.ToString());
                if (v.Tag == SubDVertexTag.Corner)
                {
                    corners++;
                    if (includeCreases && cornerList.Count < limit)
                    {
                        var pt = v.ControlNetPoint;
                        cornerList.Add(new JObject
                        {
                            ["vertex_id"] = (long)v.Id,
                            ["point"] = new JObject { ["x"] = pt.X, ["y"] = pt.Y, ["z"] = pt.Z },
                        });
                    }
                }
                else if (v.Tag == SubDVertexTag.Dart)
                {
                    darts++;
                }
            }

            foreach (var e in subd.Edges)
            {
                edgeCount++;
                Bump(edgeTags, e.Tag.ToString());
                if (e.FaceCount == 1) boundary++;
                var isCrease = e.Tag == SubDEdgeTag.Crease;
                var isSharp = e.IsSharp;
                double s0 = 0.0, s1 = 0.0;
                if (isSharp)
                {
                    sharpCount++;
                    s0 = e.EndSharpness(0, false);
                    s1 = e.EndSharpness(1, false);
                    maxSharpness = Math.Max(maxSharpness, Math.Max(s0, s1));
                }
                if (isCrease) creaseCount++;
                if ((isCrease || isSharp) && includeCreases && creases.Count < limit)
                    creases.Add(new JObject
                    {
                        ["edge_id"] = (long)e.Id,
                        ["tag"] = e.Tag.ToString(),
                        ["is_sharp"] = isSharp,
                        ["end_sharpness"] = new JArray(s0, s1),
                    });
            }

            foreach (var f in subd.Faces)
            {
                faceCount++;
                faceSides[f.EdgeCount] = faceSides.TryGetValue(f.EdgeCount, out var n) ? n + 1 : 1;
            }

            var sides = new JObject();
            foreach (var kv in faceSides) sides[kv.Key.ToString()] = kv.Value;

            var summary = new JObject
            {
                ["object_id"] = objectId,
                ["vertex_count"] = vertexCount,
                ["edge_count"] = edgeCount,
                ["face_count"] = faceCount,
                ["is_solid"] = subd.IsSolid,
                ["vertex_tags"] = JObject.FromObject(vertexTags),
                ["edge_tags"] = JObject.FromObject(edgeTags),
                ["face_side_counts"] = sides,
                ["boundary_edge_count"] = boundary,
                ["crease_edge_count"] = creaseCount,
                ["sharp_edge_count"] = sharpCount,
                ["max_edge_sharpness"] = maxSharpness,
                ["corner_vertex_count"] = corners,
                ["dart_vertex_count"] = darts,
            };
            var bbox = subd.GetBoundingBox(true);
            summary["bounding_box"] = new JObject
            {
                ["min"] = new JObject { ["x"] = bbox.Min.X, ["y"] = bbox.Min.Y, ["z"] = bbox.Min.Z },
                ["max"] = new JObject { ["x"] = bbox.Max.X, ["y"] = bbox.Max.Y, ["z"] = bbox.Max.Z },
            };
            if (includeCreases)
            {
                summary["creases"] = creases;
                summary["corners"] = cornerList;
            }

            return new JObject
            {
                ["status"] = "ok",
                ["summary"] = summary,
                ["text"] = $"SubD {objectId}: {vertexCount} vertices, {edgeCount} edges, "
                    + $"{faceCount} faces, {creaseCount} crease edge(s)",
            };
        }

        private static void Bump(SortedDictionary<string, int> counts, string key)
        {
            counts[key] = counts.TryGetValue(key, out var n) ? n + 1 : 1;
        }
    }
}
