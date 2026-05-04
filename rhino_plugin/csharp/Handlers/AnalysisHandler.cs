using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.Geometry;

namespace RhinoMcp.Handlers
{
    public class AnalysisHandler : HandlerBase
    {
        public JObject BoundingBox(JObject p)
        {
            var ids = p["object_ids"]!.Select(t => FindId(t.ToString())).ToList();
            var bbox = Rhino.Geometry.BoundingBox.Empty;
            foreach (var id in ids)
            {
                var obj = Doc.Objects.FindId(id);
                if (obj != null) bbox.Union(obj.Geometry.GetBoundingBox(true));
            }
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["min"] = new JObject { ["x"] = bbox.Min.X, ["y"] = bbox.Min.Y, ["z"] = bbox.Min.Z },
                    ["max"] = new JObject { ["x"] = bbox.Max.X, ["y"] = bbox.Max.Y, ["z"] = bbox.Max.Z },
                    ["diagonal"] = bbox.Diagonal.Length
                }
            };
        }

        public JObject Volume(JObject p)
        {
            var brep = FindBrep(p["object_id"]!.ToString());
            var mesh = FindMesh(p["object_id"]!.ToString());
            double vol = 0;
            if (brep != null) vol = brep.GetVolume();
            else if (mesh != null) vol = mesh.Volume();
            else throw new KeyNotFoundException("Brep or Mesh not found");
            return new JObject { ["summary"] = new JObject { ["volume"] = vol } };
        }

        public JObject Area(JObject p)
        {
            var brep = FindBrep(p["object_id"]!.ToString());
            var mesh = FindMesh(p["object_id"]!.ToString());
            double area = 0;
            if (brep != null) area = brep.GetArea();
            else if (mesh != null)
            {
                var mp = AreaMassProperties.Compute(mesh);
                area = mp?.Area ?? 0;
            }
            else throw new KeyNotFoundException("Object not found");
            return new JObject { ["summary"] = new JObject { ["area"] = area } };
        }

        public JObject Distance(JObject p)
        {
            var pt1 = ToPoint(p["point_a"]!);
            var pt2 = ToPoint(p["point_b"]!);
            return new JObject { ["summary"] = new JObject { ["distance"] = pt1.DistanceTo(pt2) } };
        }

        public JObject Curvature(JObject p)
        {
            var curve = FindCurve(p["object_id"]!.ToString())
                ?? throw new KeyNotFoundException("Curve not found");
            var t = p["t"]!.Value<double>();
            var vec = curve.CurvatureAt(t);
            var kappa = vec.Length;
            var radius = kappa > 0 ? 1.0 / kappa : double.PositiveInfinity;
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["curvature"] = kappa,
                    ["radius"] = radius,
                    ["vector"] = new JObject { ["x"] = vec.X, ["y"] = vec.Y, ["z"] = vec.Z }
                }
            };
        }

        public JObject DraftAngle(JObject p)
        {
            RhinoApp.RunScript("_DraftAngleAnalysis", false);
            return StatusOk("DraftAngle analysis activated");
        }

        public JObject Section(JObject p)
        {
            var origin = ToPoint(p["plane_origin"]!);
            var normal = p["plane_normal"] != null ? ToVector(p["plane_normal"]!) : Vector3d.ZAxis;
            var plane = new Plane(origin, normal);
            var ids = p["object_ids"]!.Select(t => FindId(t.ToString())).ToList();
            var resultIds = new JArray();
            foreach (var id in ids)
            {
                var brep = FindBrep(id.ToString());
                if (brep == null) continue;
                var sections = Rhino.Geometry.Intersect.Intersection.BrepPlane(
                    brep, plane, Doc.ModelAbsoluteTolerance,
                    out var curves, out _);
                if (curves != null)
                    foreach (var crv in curves)
                        resultIds.Add(AddObject(crv, p).ToString());
            }
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject { ["section_ids"] = resultIds },
                ["text"] = $"Section: {resultIds.Count} curves"
            };
        }

        public JObject Contour(JObject p)
        {
            RhinoApp.RunScript("_Contour", false);
            return StatusOk("Contour command invoked");
        }

        public JObject Zebra(JObject p)
        {
            RhinoApp.RunScript("_Zebra", false);
            return StatusOk("Zebra analysis activated");
        }
    }
}
