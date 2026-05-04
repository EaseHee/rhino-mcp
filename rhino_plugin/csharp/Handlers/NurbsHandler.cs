using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.Geometry;

namespace RhinoMcp.Handlers
{
    /// <summary>
    /// NURBS editing: rebuild, surface from points, unroll, closest point, evaluate.
    /// </summary>
    public class NurbsHandler : HandlerBase
    {
        public JObject RebuildCurve(JObject p)
        {
            var crv = FindCurve(p["object_id"]!.ToString())
                ?? throw new ArgumentException("Curve not found");
            int ptCount = p["point_count"]!.Value<int>();
            int degree = p["degree"]?.Value<int>() ?? 3;

            uint undo = Doc.BeginUndoRecord("MCP: rebuild_curve");
            try
            {
                var nc = crv.Rebuild(ptCount, degree, false);
                if (nc == null)
                    throw new InvalidOperationException("Rebuild failed");

                var id = FindId(p["object_id"]!.ToString());
                Doc.Objects.Replace(id, nc);
                Doc.Views.Redraw();

                return ObjectResult(id, "NurbsCurve");
            }
            finally { Doc.EndUndoRecord(undo); }
        }

        public JObject RebuildSurface(JObject p)
        {
            var srf = FindSurface(p["object_id"]!.ToString())
                ?? throw new ArgumentException("Surface not found");
            int uCount = p["point_count_u"]!.Value<int>();
            int vCount = p["point_count_v"]!.Value<int>();
            int uDeg = p["degree_u"]?.Value<int>() ?? 3;
            int vDeg = p["degree_v"]?.Value<int>() ?? 3;

            uint undo = Doc.BeginUndoRecord("MCP: rebuild_surface");
            try
            {
                var ns = srf.Rebuild(uDeg, vDeg, uCount, vCount);
                if (ns == null)
                    throw new InvalidOperationException("Surface rebuild failed");

                var id = FindId(p["object_id"]!.ToString());
                Doc.Objects.Replace(id, ns);
                Doc.Views.Redraw();

                return ObjectResult(id, "NurbsSurface");
            }
            finally { Doc.EndUndoRecord(undo); }
        }

        public JObject SurfaceFromPoints(JObject p)
        {
            var rows = p["points"] as JArray
                ?? throw new ArgumentException("points grid required");
            int uDeg = p["degree_u"]?.Value<int>() ?? 3;
            int vDeg = p["degree_v"]?.Value<int>() ?? 3;

            int rowCount = rows.Count;
            int colCount = ((JArray)rows[0]).Count;

            // Flatten 2D grid into 1D list for the API
            var ptsList = new List<Point3d>();
            for (int i = 0; i < rowCount; i++)
            {
                var row = (JArray)rows[i];
                for (int j = 0; j < colCount; j++)
                    ptsList.Add(ToPoint(row[j]));
            }

            uint undo = Doc.BeginUndoRecord("MCP: surface_from_points");
            try
            {
                var ns = NurbsSurface.CreateFromPoints(ptsList, rowCount, colCount, uDeg, vDeg);
                if (ns == null)
                    throw new InvalidOperationException("Surface creation from points failed");

                var id = AddObject(ns, p);
                Doc.Views.Redraw();
                return ObjectResult(id, "NurbsSurface");
            }
            finally { Doc.EndUndoRecord(undo); }
        }

        public JObject Unroll(JObject p)
        {
            var brep = FindBrep(p["object_id"]!.ToString())
                ?? throw new ArgumentException("Surface/polysurface not found");
            bool explode = p["explode"]?.Value<bool>() ?? false;

            uint undo = Doc.BeginUndoRecord("MCP: unroll");
            try
            {
                var unroller = new Unroller(brep);
                unroller.ExplodeOutput = explode;

                var unrolled = unroller.PerformUnroll(out _, out _, out _);
                if (unrolled == null || unrolled.Length == 0)
                    throw new InvalidOperationException("Unroll failed");

                var ids = new JArray();
                foreach (var b in unrolled)
                {
                    var id = Doc.Objects.AddBrep(b);
                    ids.Add(id.ToString());
                }

                Doc.Views.Redraw();
                return new JObject
                {
                    ["summary"] = new JObject { ["object_ids"] = ids },
                    ["text"] = $"Unrolled into {ids.Count} piece(s)"
                };
            }
            finally { Doc.EndUndoRecord(undo); }
        }

        public JObject ClosestPoint(JObject p)
        {
            var srf = FindSurface(p["object_id"]!.ToString())
                ?? throw new ArgumentException("Surface not found");
            var testPt = ToPoint(p["test_point"]!);

            if (!srf.ClosestPoint(testPt, out double u, out double v))
                throw new InvalidOperationException("Closest point computation failed");

            var pt3d = srf.PointAt(u, v);
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["u"] = u, ["v"] = v,
                    ["point"] = new JObject { ["x"] = pt3d.X, ["y"] = pt3d.Y, ["z"] = pt3d.Z },
                    ["distance"] = testPt.DistanceTo(pt3d)
                },
                ["text"] = $"Closest point at u={u:F4}, v={v:F4}"
            };
        }

        public JObject Evaluate(JObject p)
        {
            var srf = FindSurface(p["object_id"]!.ToString())
                ?? throw new ArgumentException("Surface not found");
            double u = p["u"]!.Value<double>();
            double v = p["v"]!.Value<double>();

            var pt = srf.PointAt(u, v);
            var normal = srf.NormalAt(u, v);

            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["point"] = new JObject { ["x"] = pt.X, ["y"] = pt.Y, ["z"] = pt.Z },
                    ["normal"] = new JObject { ["x"] = normal.X, ["y"] = normal.Y, ["z"] = normal.Z }
                },
                ["text"] = $"Evaluated at u={u:F4}, v={v:F4}"
            };
        }
    }
}
