using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.Geometry;

namespace RhinoMCPBridge.Handlers
{
    /// <summary>Surface paneling: panelize, UV grid, panel frames.</summary>
    public class PanelingHandler : HandlerBase
    {
        public JObject Panelize(JObject p)
        {
            var srf = FindSurface(p["object_id"]!.ToString())
                ?? throw new ArgumentException("Surface not found");
            int uCount = p["u_count"]!.Value<int>();
            int vCount = p["v_count"]!.Value<int>();
            string panelType = p["panel_type"]?.ToString() ?? "quad";

            uint undo = Doc.BeginUndoRecord("MCP: panelize");
            try
            {
                var domain_u = srf.Domain(0);
                var domain_v = srf.Domain(1);
                var ids = new JArray();

                for (int i = 0; i < uCount; i++)
                {
                    for (int j = 0; j < vCount; j++)
                    {
                        double u0 = domain_u.ParameterAt((double)i / uCount);
                        double u1 = domain_u.ParameterAt((double)(i + 1) / uCount);
                        double v0 = domain_v.ParameterAt((double)j / vCount);
                        double v1 = domain_v.ParameterAt((double)(j + 1) / vCount);

                        var p00 = srf.PointAt(u0, v0);
                        var p10 = srf.PointAt(u1, v0);
                        var p11 = srf.PointAt(u1, v1);
                        var p01 = srf.PointAt(u0, v1);

                        if (panelType == "triangle")
                        {
                            var m1 = new Mesh();
                            m1.Vertices.Add(p00); m1.Vertices.Add(p10); m1.Vertices.Add(p11);
                            m1.Faces.AddFace(0, 1, 2);
                            m1.Normals.ComputeNormals();
                            ids.Add(Doc.Objects.AddMesh(m1).ToString());

                            var m2 = new Mesh();
                            m2.Vertices.Add(p00); m2.Vertices.Add(p11); m2.Vertices.Add(p01);
                            m2.Faces.AddFace(0, 1, 2);
                            m2.Normals.ComputeNormals();
                            ids.Add(Doc.Objects.AddMesh(m2).ToString());
                        }
                        else // quad (default) or diamond
                        {
                            var m = new Mesh();
                            m.Vertices.Add(p00); m.Vertices.Add(p10);
                            m.Vertices.Add(p11); m.Vertices.Add(p01);
                            m.Faces.AddFace(0, 1, 2, 3);
                            m.Normals.ComputeNormals();
                            ids.Add(Doc.Objects.AddMesh(m).ToString());
                        }
                    }
                }

                Doc.Views.Redraw();
                return new JObject
                {
                    ["summary"] = new JObject { ["object_ids"] = ids, ["panel_count"] = ids.Count },
                    ["text"] = $"Created {ids.Count} {panelType} panel(s)"
                };
            }
            finally { Doc.EndUndoRecord(undo); }
        }

        public JObject UvGrid(JObject p)
        {
            var srf = FindSurface(p["object_id"]!.ToString())
                ?? throw new ArgumentException("Surface not found");
            int uCount = p["u_count"]!.Value<int>();
            int vCount = p["v_count"]!.Value<int>();

            var domain_u = srf.Domain(0);
            var domain_v = srf.Domain(1);

            uint undo = Doc.BeginUndoRecord("MCP: uv_grid");
            try
            {
                var ids = new JArray();
                var points = new JArray();

                for (int i = 0; i <= uCount; i++)
                {
                    for (int j = 0; j <= vCount; j++)
                    {
                        double u = domain_u.ParameterAt((double)i / uCount);
                        double v = domain_v.ParameterAt((double)j / vCount);
                        var pt = srf.PointAt(u, v);
                        var id = Doc.Objects.AddPoint(pt);
                        ids.Add(id.ToString());
                        points.Add(new JObject { ["x"] = pt.X, ["y"] = pt.Y, ["z"] = pt.Z });
                    }
                }

                Doc.Views.Redraw();
                return new JObject
                {
                    ["summary"] = new JObject
                    {
                        ["object_ids"] = ids,
                        ["points"] = points,
                        ["grid_size"] = new JArray(uCount + 1, vCount + 1)
                    },
                    ["text"] = $"Created {ids.Count} grid points ({uCount + 1}×{vCount + 1})"
                };
            }
            finally { Doc.EndUndoRecord(undo); }
        }

        public JObject Frames(JObject p)
        {
            var srf = FindSurface(p["object_id"]!.ToString())
                ?? throw new ArgumentException("Surface not found");
            int uCount = p["u_count"]!.Value<int>();
            int vCount = p["v_count"]!.Value<int>();
            double offset = p["offset"]?.Value<double>() ?? 0;

            var domain_u = srf.Domain(0);
            var domain_v = srf.Domain(1);

            var frames = new JArray();

            for (int i = 0; i < uCount; i++)
            {
                for (int j = 0; j < vCount; j++)
                {
                    double u = domain_u.ParameterAt((i + 0.5) / uCount);
                    double v = domain_v.ParameterAt((j + 0.5) / vCount);

                    var pt = srf.PointAt(u, v);
                    var normal = srf.NormalAt(u, v);

                    if (offset != 0)
                        pt += normal * offset;

                    frames.Add(new JObject
                    {
                        ["origin"] = new JObject { ["x"] = pt.X, ["y"] = pt.Y, ["z"] = pt.Z },
                        ["normal"] = new JObject { ["x"] = normal.X, ["y"] = normal.Y, ["z"] = normal.Z },
                        ["u_index"] = i,
                        ["v_index"] = j
                    });
                }
            }

            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["frame_count"] = frames.Count,
                    ["frames"] = frames
                },
                ["text"] = $"{frames.Count} panel frame(s) computed"
            };
        }
    }
}
