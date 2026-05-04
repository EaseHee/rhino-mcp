using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.Geometry;

namespace RhinoMcp.Handlers
{
    /// <summary>Control point get/set for NURBS curves and surfaces.</summary>
    public class ControlPointHandler : HandlerBase
    {
        public JObject Get(JObject p)
        {
            var obj = FindObject(p["object_id"]!.ToString())
                ?? throw new ArgumentException("Object not found");
            var geom = obj.Geometry;

            var points = new JArray();
            var weights = new JArray();

            if (geom is NurbsCurve nc)
            {
                for (int i = 0; i < nc.Points.Count; i++)
                {
                    var cp = nc.Points[i];
                    points.Add(new JObject
                    {
                        ["x"] = cp.Location.X,
                        ["y"] = cp.Location.Y,
                        ["z"] = cp.Location.Z
                    });
                    weights.Add(cp.Weight);
                }
            }
            else if (geom is NurbsSurface ns)
            {
                for (int i = 0; i < ns.Points.CountU; i++)
                {
                    for (int j = 0; j < ns.Points.CountV; j++)
                    {
                        var cp = ns.Points.GetControlPoint(i, j);
                        points.Add(new JObject
                        {
                            ["x"] = cp.Location.X,
                            ["y"] = cp.Location.Y,
                            ["z"] = cp.Location.Z,
                            ["u_index"] = i,
                            ["v_index"] = j
                        });
                        weights.Add(cp.Weight);
                    }
                }
            }
            else
            {
                throw new ArgumentException("Object must be a NurbsCurve or NurbsSurface");
            }

            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["point_count"] = points.Count,
                    ["points"] = points,
                    ["weights"] = weights
                },
                ["text"] = $"{points.Count} control point(s)"
            };
        }

        public JObject Set(JObject p)
        {
            var obj = FindObject(p["object_id"]!.ToString())
                ?? throw new ArgumentException("Object not found");
            var geom = obj.Geometry;

            var pts = p["points"] as JArray
                ?? throw new ArgumentException("points array required");
            var wts = p["weights"] as JArray;

            uint undo = Doc.BeginUndoRecord("MCP: set_control_points");
            try
            {
                if (geom is NurbsCurve nc)
                {
                    var dup = nc.Duplicate() as NurbsCurve
                        ?? throw new InvalidOperationException("Failed to duplicate curve");

                    for (int i = 0; i < Math.Min(pts.Count, dup.Points.Count); i++)
                    {
                        var pt = ToPoint(pts[i]);
                        double w = wts != null && i < wts.Count
                            ? wts[i].Value<double>()
                            : dup.Points[i].Weight;
                        dup.Points.SetPoint(i, pt, w);
                    }

                    Doc.Objects.Replace(obj.Id, dup);
                }
                else if (geom is NurbsSurface ns)
                {
                    var dup = ns.Duplicate() as NurbsSurface
                        ?? throw new InvalidOperationException("Failed to duplicate surface");

                    int idx = 0;
                    for (int i = 0; i < dup.Points.CountU && idx < pts.Count; i++)
                    {
                        for (int j = 0; j < dup.Points.CountV && idx < pts.Count; j++)
                        {
                            var pt = ToPoint(pts[idx]);
                            double w = wts != null && idx < wts.Count
                                ? wts[idx].Value<double>()
                                : dup.Points.GetControlPoint(i, j).Weight;
                            dup.Points.SetPoint(i, j, pt, w);
                            idx++;
                        }
                    }

                    Doc.Objects.Replace(obj.Id, dup);
                }
                else
                {
                    throw new ArgumentException("Object must be a NurbsCurve or NurbsSurface");
                }

                Doc.Views.Redraw();
                return new JObject
                {
                    ["summary"] = new JObject
                    {
                        ["object_id"] = p["object_id"]!.ToString(),
                        ["point_count"] = pts.Count
                    },
                    ["text"] = $"Set {pts.Count} control point(s)"
                };
            }
            finally { Doc.EndUndoRecord(undo); }
        }
    }
}
